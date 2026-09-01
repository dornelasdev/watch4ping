from io import StringIO

from watch4ping.dashboard import (
    DashboardHTTPServer,
    format_dashboard_html,
    format_terminal_link,
    open_dashboard_browser,
    resolve_html_report,
)


def test_dashboard_server_reuses_address_and_closes_request_threads():
    assert DashboardHTTPServer.allow_reuse_address is True
    assert DashboardHTTPServer.daemon_threads is True


def test_format_terminal_link_preserves_visible_url_and_plain_fallback():
    url = "http://127.0.0.1:8765"

    assert format_terminal_link(url) == (
        f"\033]8;;{url}\033\\{url}\033]8;;\033\\"
    )
    assert format_terminal_link(url, enabled=False) == url


def test_open_dashboard_browser_reports_success():
    stream = StringIO()
    opened_urls = []

    opened = open_dashboard_browser(
        "http://127.0.0.1:8765",
        opener=lambda url: opened_urls.append(url) or True,
        stream=stream,
    )

    assert opened is True
    assert opened_urls == ["http://127.0.0.1:8765"]
    assert stream.getvalue() == "Opened dashboard in the default browser.\n"


def test_open_dashboard_browser_keeps_manual_fallback_on_failure():
    stream = StringIO()

    opened = open_dashboard_browser(
        "http://127.0.0.1:8765",
        opener=lambda _url: False,
        stream=stream,
    )

    assert opened is False
    assert "Open the URL above manually." in stream.getvalue()


def test_format_dashboard_html_lists_sessions_newest_first_and_escapes_values():
    html = format_dashboard_html(
        {
            "updated_at": "2026-08-11T14:17:11+00:00",
            "sessions": [
                build_session("2026-08-11T14:00:00+00:00", "office", 100, 0, 0),
                build_session(
                    "2026-08-11T14:05:00+00:00",
                    "home<script>",
                    95.5,
                    2,
                    1,
                    html_report="watch4ping home.html",
                ),
            ],
        }
    )

    assert "watch4ping dashboard" in html
    assert "2 sessions" in html
    assert html.index("<td>home&lt;script&gt;</td>") < html.index("<td>office</td>")
    assert "home&lt;script&gt;" in html
    assert "home<script>" not in html
    assert "95.50%" in html
    assert "20.5 ms" in html
    assert "cloudflare=1.1.1.1" in html
    assert 'href="/reports/watch4ping%20home.html"' in html
    assert "View report" in html
    assert "Not available" in html


def test_format_dashboard_html_shows_empty_state():
    html = format_dashboard_html({"updated_at": None, "sessions": []})

    assert "0 sessions" in html
    assert "No report sessions yet." in html
    assert "Generate a report to populate this dashboard." in html


def test_format_dashboard_html_filters_sessions_by_profile():
    html = format_dashboard_html(
        {
            "sessions": [
                build_session("2026-08-11T14:00:00+00:00", "office", 100, 0, 0),
                build_session("2026-08-11T14:05:00+00:00", "home", 95, 1, 1),
            ],
        },
        profile_name="home",
    )

    assert "1 session" in html
    assert "<td>home</td>" in html
    assert "<td>office</td>" not in html
    assert '<option value="home" selected>' in html
    assert '<a class="clear-filter" href="/">Clear</a>' in html


def test_format_dashboard_html_compares_two_selected_sessions():
    previous = build_session(
        "2026-08-11T14:00:00+00:00",
        "home",
        90,
        3,
        2,
        avg_latency_ms=20,
    )
    current = build_session(
        "2026-08-11T14:05:00+00:00",
        "home",
        100,
        0,
        0,
        avg_latency_ms=15.5,
    )
    html = format_dashboard_html(
        {"sessions": [previous, current]},
        selected_session_ids=[previous["started_at"], current["started_at"]],
        comparison_requested=True,
    )

    assert "Session comparison" in html
    assert "90.00% -> 100.00%" in html
    assert "+10.00 pp" in html
    assert "3 -> 0" in html
    assert "2 -> 0" in html
    assert "20.0 ms -> 15.5 ms" in html
    assert html.count(" checked") == 2


def test_format_dashboard_html_requires_exactly_two_sessions_for_comparison():
    session = build_session("2026-08-11T14:00:00+00:00", "home", 100, 0, 0)

    html = format_dashboard_html(
        {"sessions": [session]},
        selected_session_ids=[session["started_at"]],
        comparison_requested=True,
    )

    assert "Select exactly two sessions to compare." in html


def test_resolve_html_report_allows_only_indexed_reports(tmp_path):
    report_path = tmp_path / "session.html"
    report_path.write_text("<h1>report</h1>", encoding="utf-8")
    unrelated_path = tmp_path / "unrelated.html"
    unrelated_path.write_text("<h1>private</h1>", encoding="utf-8")
    index_data = {
        "sessions": [{"reports": {"html": "session.html"}}],
    }

    assert resolve_html_report(tmp_path, "session.html", index_data) == report_path
    assert resolve_html_report(tmp_path, "unrelated.html", index_data) is None
    assert resolve_html_report(tmp_path, "../unrelated.html", index_data) is None


def test_resolve_html_report_handles_missing_indexed_file(tmp_path):
    index_data = {
        "sessions": [{"reports": {"html": "missing.html"}}],
    }

    assert resolve_html_report(tmp_path, "missing.html", index_data) is None


def build_session(
    started_at: str,
    profile: str,
    uptime_percent: float,
    failed_samples: int,
    alert_count: int,
    html_report: str | None = None,
    avg_latency_ms: float = 20.5,
) -> dict:
    return {
        "started_at": started_at,
        "profile": profile,
        "targets": [{"label": "cloudflare", "host": "1.1.1.1"}],
        "summary": {
            "uptime_percent": uptime_percent,
            "avg_latency_ms": avg_latency_ms,
            "failed_samples": failed_samples,
            "alert_count": alert_count,
        },
        "reports": {"html": html_report} if html_report else {"json": "report.json"},
    }
