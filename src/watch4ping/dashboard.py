from __future__ import annotations

import sys
import webbrowser
from datetime import datetime
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, TextIO
from urllib.parse import parse_qs, quote, unquote, urlsplit

from .exporters import read_report_index


DEFAULT_DASHBOARD_HOST = "127.0.0.1"
DEFAULT_DASHBOARD_PORT = 8765
MANUAL_PROFILE_FILTER = "__manual__"


class DashboardHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve_dashboard(
    output_dir: Path,
    port: int = DEFAULT_DASHBOARD_PORT,
    stream: TextIO | None = None,
    open_browser: bool = False,
    browser_opener: Callable[[str], bool] | None = None,
) -> None:
    stream = stream or sys.stdout
    server = create_dashboard_server(output_dir, port)
    url = f"http://{DEFAULT_DASHBOARD_HOST}:{server.server_port}"
    link = format_terminal_link(url, enabled=stream.isatty())
    print(f"Dashboard running at {link}", file=stream, flush=True)
    print("Press Ctrl-C to stop.", file=stream, flush=True)
    if open_browser:
        open_dashboard_browser(
            url,
            opener=browser_opener or webbrowser.open,
            stream=stream,
        )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard stopped.", file=stream)
    finally:
        server.server_close()


def open_dashboard_browser(
    url: str,
    opener: Callable[[str], bool],
    stream: TextIO,
) -> bool:
    try:
        opened = opener(url)
    except (OSError, webbrowser.Error):
        opened = False

    if opened:
        print("Opened dashboard in the default browser.", file=stream, flush=True)
    else:
        print(
            "Could not open the browser automatically. Open the URL above manually.",
            file=stream,
            flush=True,
        )
    return opened


def format_terminal_link(url: str, enabled: bool = True) -> str:
    if not enabled:
        return url
    return f"\033]8;;{url}\033\\{url}\033]8;;\033\\"


def create_dashboard_server(
    output_dir: Path,
    port: int = DEFAULT_DASHBOARD_PORT,
) -> DashboardHTTPServer:
    handler = build_dashboard_handler(output_dir)
    return DashboardHTTPServer((DEFAULT_DASHBOARD_HOST, port), handler)


def build_dashboard_handler(output_dir: Path) -> type[BaseHTTPRequestHandler]:
    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            request = urlsplit(self.path)
            path = request.path
            query = parse_qs(request.query)
            if path == "/":
                self.send_dashboard(profile_name=first_query_value(query, "profile"))
                return
            if path == "/compare":
                self.send_dashboard(
                    profile_name=first_query_value(query, "profile"),
                    selected_session_ids=query.get("session", []),
                    comparison_requested=True,
                )
                return
            if path.startswith("/reports/"):
                self.send_html_report(unquote(path.removeprefix("/reports/")))
                return
            if path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            self.send_error(404, "Not Found")

        def send_dashboard(
            self,
            profile_name: str | None = None,
            selected_session_ids: list[str] | None = None,
            comparison_requested: bool = False,
        ) -> None:
            try:
                index_data = read_report_index(output_dir / "index.json")
                body = format_dashboard_html(
                    index_data,
                    profile_name=profile_name,
                    selected_session_ids=selected_session_ids,
                    comparison_requested=comparison_requested,
                ).encode("utf-8")
            except (OSError, ValueError) as exc:
                body = format_dashboard_error(exc).encode("utf-8")
                self.send_response(500)
            else:
                self.send_response(200)

            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def send_html_report(self, requested_path: str) -> None:
            try:
                index_data = read_report_index(output_dir / "index.json")
                report_path = resolve_html_report(
                    output_dir,
                    requested_path,
                    index_data,
                )
                if report_path is None:
                    self.send_error(404, "Report Not Found")
                    return
                body = report_path.read_bytes()
            except (OSError, ValueError):
                self.send_error(404, "Report Not Found")
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
            )
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args) -> None:
            return

    return DashboardHandler


def format_dashboard_html(
    index_data: dict,
    profile_name: str | None = None,
    selected_session_ids: list[str] | None = None,
    comparison_requested: bool = False,
) -> str:
    all_sessions = [
        session
        for session in index_data.get("sessions", [])
        if isinstance(session, dict)
    ]
    sessions = [
        session
        for session in reversed(all_sessions)
        if session_matches_profile(session, profile_name)
    ]
    selected_ids = selected_session_ids or []
    session_rows = "\n".join(
        format_session_row(session, selected_ids)
        for session in sessions
    )
    table = (
        '<form method="get" action="/compare">'
        f"{format_profile_hidden_input(profile_name)}"
        "<div class=\"table-wrap\"><table><thead><tr>"
        "<th class=\"select-column\">Compare</th><th>Started</th><th>Profile</th>"
        "<th>Targets</th><th>Uptime</th>"
        "<th>Avg latency</th><th>Failed</th><th>Alerts</th><th>Report</th>"
        f"</tr></thead><tbody>{session_rows}</tbody></table></div>"
        '<div class="table-actions"><button type="submit">Compare selected</button></div>'
        "</form>"
        if sessions
        else (
            f'<div class="empty"><strong>{format_empty_dashboard_title(profile_name)}</strong>'
            f"<span>{format_empty_dashboard_message(profile_name)}</span></div>"
        )
    )
    updated_at = format_dashboard_timestamp(index_data.get("updated_at"))
    session_label = "session" if len(sessions) == 1 else "sessions"
    profile_filter = format_profile_filter(all_sessions, profile_name)
    comparison = format_dashboard_comparison(
        [
            session
            for session in all_sessions
            if session_matches_profile(session, profile_name)
        ],
        selected_ids,
        comparison_requested,
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>watch4ping dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4f6f8;
      --surface: #ffffff;
      --text: #18212b;
      --muted: #667085;
      --line: #d8dee6;
      --green: #16794c;
      --red: #b42318;
      --amber: #9a6700;
      --navy: #16324f;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 14px;
      line-height: 1.45;
    }}
    header {{
      background: var(--navy);
      color: #ffffff;
      border-bottom: 3px solid #2c7a7b;
    }}
    .header-inner, main {{
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
    }}
    .header-inner {{
      min-height: 72px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
    }}
    .brand {{ font-size: 20px; font-weight: 700; }}
    .host {{ color: #cbd5e1; font-family: ui-monospace, SFMono-Regular, monospace; }}
    main {{ padding: 30px 0 48px; }}
    .section-head {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 20px;
      margin-bottom: 14px;
    }}
    h1 {{ margin: 0; font-size: 24px; letter-spacing: 0; }}
    .meta {{ margin: 4px 0 0; color: var(--muted); }}
    .count {{ color: var(--muted); white-space: nowrap; }}
    .filters {{
      display: flex;
      align-items: end;
      gap: 10px;
      margin-bottom: 18px;
    }}
    .field {{ display: grid; gap: 5px; }}
    label {{ color: #475467; font-size: 12px; font-weight: 650; }}
    select, button {{
      min-height: 36px;
      border: 1px solid #aeb8c4;
      border-radius: 4px;
      background: var(--surface);
      color: var(--text);
      font: inherit;
    }}
    select {{ min-width: 180px; padding: 6px 30px 6px 10px; }}
    button {{
      padding: 6px 12px;
      background: var(--navy);
      border-color: var(--navy);
      color: #ffffff;
      cursor: pointer;
      font-weight: 650;
    }}
    button:hover {{ background: #234c70; }}
    .clear-filter {{ color: #175cd3; line-height: 36px; text-decoration: none; }}
    .clear-filter:hover {{ text-decoration: underline; }}
    .table-wrap {{
      overflow-x: auto;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 6px;
    }}
    table {{ border-collapse: collapse; width: 100%; min-width: 1040px; }}
    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      white-space: nowrap;
    }}
    th {{
      background: #eef1f4;
      color: #475467;
      font-size: 12px;
      font-weight: 650;
      text-transform: uppercase;
    }}
    tbody tr:last-child td {{ border-bottom: 0; }}
    tbody tr:hover {{ background: #f8fafc; }}
    .targets {{ white-space: normal; min-width: 220px; }}
    .select-column {{ width: 72px; text-align: center; }}
    td.select-column {{ vertical-align: middle; }}
    input[type="checkbox"] {{ width: 17px; height: 17px; margin: 0; }}
    .metric-ok {{ color: var(--green); font-weight: 650; }}
    .metric-bad {{ color: var(--red); font-weight: 650; }}
    .metric-warn {{ color: var(--amber); font-weight: 650; }}
    .report-link {{
      display: inline-block;
      color: #175cd3;
      font-weight: 650;
      text-decoration: none;
    }}
    .report-link:hover {{ text-decoration: underline; }}
    .unavailable {{ color: var(--muted); }}
    .table-actions {{ display: flex; justify-content: flex-end; margin-top: 12px; }}
    .comparison {{
      margin: 0 0 22px;
      padding: 18px 0 20px;
      border-top: 1px solid var(--line);
      border-bottom: 1px solid var(--line);
    }}
    .comparison h2 {{ margin: 0 0 12px; font-size: 18px; letter-spacing: 0; }}
    .comparison-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(150px, 1fr));
      gap: 1px;
      overflow: hidden;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: var(--line);
    }}
    .comparison-cell {{ background: var(--surface); padding: 12px; }}
    .comparison-label {{ color: var(--muted); font-size: 12px; }}
    .comparison-value {{ margin-top: 3px; font-size: 16px; font-weight: 650; }}
    .comparison-error {{ color: var(--red); font-weight: 650; }}
    .empty {{
      min-height: 210px;
      display: grid;
      place-content: center;
      gap: 6px;
      text-align: center;
      background: var(--surface);
      border: 1px solid var(--line);
      border-radius: 6px;
    }}
    .empty span {{ color: var(--muted); }}
    @media (max-width: 640px) {{
      .header-inner, main {{ width: min(100% - 24px, 1180px); }}
      .header-inner {{ min-height: 64px; }}
      .host {{ display: none; }}
      main {{ padding-top: 22px; }}
      .section-head {{ align-items: start; flex-direction: column; gap: 6px; }}
      .filters {{ align-items: stretch; flex-direction: column; }}
      .clear-filter {{ line-height: 24px; }}
      .comparison-grid {{ grid-template-columns: 1fr 1fr; }}
      h1 {{ font-size: 21px; }}
    }}
  </style>
</head>
<body>
  <header>
    <div class="header-inner">
      <div class="brand">watch4ping</div>
      <div class="host">local dashboard</div>
    </div>
  </header>
  <main>
    <div class="section-head">
      <div>
        <h1>Report sessions</h1>
        <p class="meta">Last index update: {escape(updated_at)}</p>
      </div>
      <div class="count">{len(sessions)} {session_label}</div>
    </div>
    {profile_filter}
    {comparison}
    {table}
  </main>
</body>
</html>
"""


def format_session_row(session: dict, selected_session_ids: list[str]) -> str:
    summary = session.get("summary")
    summary = summary if isinstance(summary, dict) else {}
    uptime = number_or_default(summary.get("uptime_percent"))
    failed = integer_or_default(summary.get("failed_samples"))
    alerts = integer_or_default(summary.get("alert_count"))
    avg_latency = optional_number(summary.get("avg_latency_ms"))

    uptime_class = "metric-ok" if uptime >= 99.0 else "metric-warn"
    failed_class = "metric-bad" if failed else "metric-ok"
    alert_class = "metric-bad" if alerts else "metric-ok"
    latency_label = f"{avg_latency:.1f} ms" if avg_latency is not None else "n/a"
    started_at = str(session.get("started_at") or "")
    checked = " checked" if started_at in selected_session_ids else ""
    checkbox = (
        f'<input type="checkbox" name="session" value="{escape(started_at)}"'
        f' aria-label="Select session {escape(format_dashboard_timestamp(started_at))}"{checked}>'
        if started_at
        else '<input type="checkbox" disabled aria-label="Session unavailable">'
    )

    return (
        "<tr>"
        f'<td class="select-column">{checkbox}</td>'
        f"<td>{escape(format_dashboard_timestamp(session.get('started_at')))}</td>"
        f"<td>{escape(str(session.get('profile') or 'manual'))}</td>"
        f'<td class="targets">{escape(format_targets(session.get("targets")))}</td>'
        f'<td class="{uptime_class}">{uptime:.2f}%</td>'
        f"<td>{escape(latency_label)}</td>"
        f'<td class="{failed_class}">{failed}</td>'
        f'<td class="{alert_class}">{alerts}</td>'
        f"<td>{format_report_action(session)}</td>"
        "</tr>"
    )


def first_query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values and values[0] else None


def session_matches_profile(session: dict, profile_name: str | None) -> bool:
    if profile_name is None:
        return True
    if profile_name == MANUAL_PROFILE_FILTER:
        return not session.get("profile")
    return session.get("profile") == profile_name


def format_profile_filter(sessions: list[dict], profile_name: str | None) -> str:
    profile_names = sorted(
        {
            str(session.get("profile"))
            for session in sessions
            if session.get("profile")
        },
        key=str.lower,
    )
    has_manual_sessions = any(not session.get("profile") for session in sessions)
    options = [format_profile_option("", "All profiles", profile_name)]
    options.extend(
        format_profile_option(name, name, profile_name)
        for name in profile_names
    )
    if has_manual_sessions:
        options.append(
            format_profile_option(
                MANUAL_PROFILE_FILTER,
                "Manual",
                profile_name,
            )
        )

    clear_link = (
        '<a class="clear-filter" href="/">Clear</a>'
        if profile_name is not None
        else ""
    )
    return (
        '<form class="filters" method="get" action="/">'
        '<div class="field"><label for="profile">Profile</label>'
        f'<select id="profile" name="profile">{"".join(options)}</select></div>'
        '<button type="submit">Apply</button>'
        f"{clear_link}</form>"
    )


def format_profile_option(value: str, label: str, selected_value: str | None) -> str:
    selected = " selected" if value == (selected_value or "") else ""
    return (
        f'<option value="{escape(value)}"{selected}>'
        f"{escape(label)}</option>"
    )


def format_profile_hidden_input(profile_name: str | None) -> str:
    if profile_name is None:
        return ""
    return f'<input type="hidden" name="profile" value="{escape(profile_name)}">'


def format_empty_dashboard_message(profile_name: str | None) -> str:
    if profile_name is not None:
        return "No sessions match this profile."
    return "Generate a report to populate this dashboard."


def format_empty_dashboard_title(profile_name: str | None) -> str:
    if profile_name is not None:
        return "No matching sessions."
    return "No report sessions yet."


def format_dashboard_comparison(
    sessions: list[dict],
    selected_session_ids: list[str],
    comparison_requested: bool,
) -> str:
    if not comparison_requested:
        return ""

    distinct_ids = set(selected_session_ids)
    if len(distinct_ids) != 2:
        return (
            '<section class="comparison"><h2>Session comparison</h2>'
            '<div class="comparison-error">Select exactly two sessions to compare.</div>'
            "</section>"
        )

    selected_sessions = sorted(
        (
            session
            for session in sessions
            if session.get("started_at") in distinct_ids
        ),
        key=lambda session: str(session.get("started_at") or ""),
    )
    if len(selected_sessions) != 2:
        return (
            '<section class="comparison"><h2>Session comparison</h2>'
            '<div class="comparison-error">One or more selected sessions are unavailable.</div>'
            "</section>"
        )

    previous, current = selected_sessions
    previous_summary = dashboard_summary(previous)
    current_summary = dashboard_summary(current)
    previous_time = escape(format_dashboard_timestamp(previous.get("started_at")))
    current_time = escape(format_dashboard_timestamp(current.get("started_at")))

    metrics = "".join(
        (
            format_comparison_metric(
                "Uptime",
                number_or_default(previous_summary.get("uptime_percent")),
                number_or_default(current_summary.get("uptime_percent")),
                unit="%",
                decimals=2,
                delta_unit=" pp",
            ),
            format_comparison_metric(
                "Failed samples",
                integer_or_default(previous_summary.get("failed_samples")),
                integer_or_default(current_summary.get("failed_samples")),
            ),
            format_comparison_metric(
                "Alerts",
                integer_or_default(previous_summary.get("alert_count")),
                integer_or_default(current_summary.get("alert_count")),
            ),
            format_latency_comparison(previous_summary, current_summary),
        )
    )
    return (
        '<section class="comparison"><h2>Session comparison</h2>'
        f'<p class="meta">Previous: {previous_time} | Current: {current_time}</p>'
        f'<div class="comparison-grid">{metrics}</div></section>'
    )


def dashboard_summary(session: dict) -> dict:
    summary = session.get("summary")
    return summary if isinstance(summary, dict) else {}


def format_comparison_metric(
    label: str,
    previous_value: float,
    current_value: float,
    unit: str = "",
    decimals: int = 0,
    delta_unit: str = "",
) -> str:
    previous_label = f"{previous_value:.{decimals}f}{unit}"
    current_label = f"{current_value:.{decimals}f}{unit}"
    delta = current_value - previous_value
    delta_label = f"{delta:+.{decimals}f}{delta_unit}"
    return (
        '<div class="comparison-cell">'
        f'<div class="comparison-label">{escape(label)}</div>'
        f'<div class="comparison-value">{previous_label} -> {current_label}</div>'
        f'<div class="meta">{delta_label}</div></div>'
    )


def format_latency_comparison(previous_summary: dict, current_summary: dict) -> str:
    previous = optional_number(previous_summary.get("avg_latency_ms"))
    current = optional_number(current_summary.get("avg_latency_ms"))
    if previous is None or current is None:
        return (
            '<div class="comparison-cell"><div class="comparison-label">Avg latency</div>'
            '<div class="comparison-value">n/a</div></div>'
        )
    return format_comparison_metric(
        "Avg latency",
        previous,
        current,
        unit=" ms",
        decimals=1,
        delta_unit=" ms",
    )


def format_report_action(session: dict) -> str:
    reports = session.get("reports")
    if not isinstance(reports, dict):
        return '<span class="unavailable">Not available</span>'

    report_path = reports.get("html")
    if not is_safe_html_report_path(report_path):
        return '<span class="unavailable">Not available</span>'

    href = f"/reports/{quote(report_path, safe='/')}"
    return (
        f'<a class="report-link" href="{escape(href)}" target="_blank" '
        'rel="noopener noreferrer">View report</a>'
    )


def resolve_html_report(
    output_dir: Path,
    requested_path: str,
    index_data: dict,
) -> Path | None:
    if not is_safe_html_report_path(requested_path):
        return None

    allowed_paths = {
        reports.get("html")
        for session in index_data.get("sessions", [])
        if isinstance(session, dict)
        for reports in [session.get("reports")]
        if isinstance(reports, dict) and is_safe_html_report_path(reports.get("html"))
    }
    if requested_path not in allowed_paths:
        return None

    output_root = output_dir.resolve()
    report_path = (output_dir / requested_path).resolve()
    if not report_path.is_relative_to(output_root) or not report_path.is_file():
        return None
    return report_path


def is_safe_html_report_path(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    report_path = Path(value)
    return (
        not report_path.is_absolute()
        and ".." not in report_path.parts
        and report_path.suffix.lower() == ".html"
    )


def format_targets(value: object) -> str:
    if not isinstance(value, list):
        return "n/a"

    targets: list[str] = []
    for target in value:
        if not isinstance(target, dict):
            continue
        label = str(target.get("label") or "")
        host = str(target.get("host") or "")
        if label and host and label != host:
            targets.append(f"{label}={host}")
        elif host or label:
            targets.append(host or label)
    return ", ".join(targets) or "n/a"


def format_dashboard_timestamp(value: object) -> str:
    if not isinstance(value, str) or not value:
        return "unknown"
    try:
        timestamp = datetime.fromisoformat(value)
    except ValueError:
        return value
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone()
    return timestamp.strftime("%Y-%m-%d %H:%M:%S %Z").strip()


def number_or_default(value: object, default: float = 0.0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return default


def optional_number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def integer_or_default(value: object) -> int:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return int(value)
    return 0


def format_dashboard_error(error: Exception) -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        "<title>watch4ping dashboard error</title></head><body>"
        "<main><h1>Dashboard unavailable</h1>"
        f"<p>{escape(str(error))}</p></main></body></html>"
    )
