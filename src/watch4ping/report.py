from __future__ import annotations

from html import escape
from statistics import fmean, pstdev

from .models import LatencySpike, MonitorSession, Outage, PingSample, ReportSummary, SessionReport


REPORT_SCHEMA_VERSION = "1"


def build_report(session: MonitorSession) -> SessionReport:
    outages = detect_outages(session)
    latencies = [
        sample.latency_ms
        for sample in session.samples
        if sample.ok and sample.latency_ms is not None
    ]
    total_samples = len(session.samples)
    successful_samples = sum(1 for sample in session.samples if sample.ok)
    failed_samples = total_samples - successful_samples
    duration_seconds = (session.ended_at - session.started_at).total_seconds()
    p50_latency_ms = percentile(latencies, 50)
    p95_latency_ms = percentile(latencies, 95)
    p99_latency_ms = percentile(latencies, 99)
    avg_latency_ms = fmean(latencies) if latencies else None
    jitter_ms = pstdev(latencies) if len(latencies) > 1 else None
    latency_spike_threshold_ms = calculate_latency_spike_threshold(
        avg_latency_ms=avg_latency_ms,
        p95_latency_ms=p95_latency_ms,
    )
    latency_spikes = detect_latency_spikes(session.samples, latency_spike_threshold_ms)

    summary = ReportSummary(
        duration_seconds=max(0.0, duration_seconds),
        total_samples=total_samples,
        successful_samples=successful_samples,
        failed_samples=failed_samples,
        uptime_percent=(successful_samples / total_samples * 100) if total_samples else 0.0,
        outage_count=len(outages),
        longest_outage_seconds=max((outage.duration_seconds for outage in outages), default=0.0),
        min_latency_ms=min(latencies) if latencies else None,
        avg_latency_ms=avg_latency_ms,
        max_latency_ms=max(latencies) if latencies else None,
        p50_latency_ms=p50_latency_ms,
        p95_latency_ms=p95_latency_ms,
        p99_latency_ms=p99_latency_ms,
        jitter_ms=jitter_ms,
        latency_spike_count=len(latency_spikes),
        latency_spike_threshold_ms=latency_spike_threshold_ms,
    )
    return SessionReport(
        schema_version=REPORT_SCHEMA_VERSION,
        session=session,
        summary=summary,
        outages=tuple(outages),
        latency_spikes=tuple(latency_spikes),
    )


def percentile(values: list[float], percent: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]

    sorted_values = sorted(values)
    rank = (len(sorted_values) - 1) * (percent / 100)
    lower_index = int(rank)
    upper_index = min(lower_index + 1, len(sorted_values) - 1)
    fraction = rank - lower_index

    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    return lower_value + (upper_value - lower_value) * fraction


def calculate_latency_spike_threshold(
    avg_latency_ms: float | None,
    p95_latency_ms: float | None,
) -> float | None:
    if avg_latency_ms is None or p95_latency_ms is None:
        return None
    return max(p95_latency_ms, avg_latency_ms * 2)


def detect_latency_spikes(
    samples: tuple[PingSample, ...],
    threshold_ms: float | None,
) -> list[LatencySpike]:
    if threshold_ms is None:
        return []

    return [
        LatencySpike(
            sequence=sample.sequence,
            timestamp=sample.timestamp,
            formatted_timestamp=sample.formatted_timestamp,
            latency_ms=sample.latency_ms,
            threshold_ms=threshold_ms,
        )
        for sample in samples
        if sample.ok and sample.latency_ms is not None and sample.latency_ms >= threshold_ms
    ]


def detect_outages(session: MonitorSession) -> list[Outage]:
    outages: list[Outage] = []
    failed_run: list[PingSample] = []

    for sample in session.samples:
        if not sample.ok:
            failed_run.append(sample)
            continue

        if len(failed_run) >= session.fail_threshold:
            outages.append(outage_from_failed_run(failed_run, session.interval_seconds))
        failed_run = []

    if len(failed_run) >= session.fail_threshold:
        outages.append(outage_from_failed_run(failed_run, session.interval_seconds))

    return outages


def outage_from_failed_run(failed_run: list[PingSample], interval_seconds: float) -> Outage:
    started_at = failed_run[0].timestamp
    ended_at = failed_run[-1].timestamp
    observed_duration = (ended_at - started_at).total_seconds()
    duration_seconds = observed_duration + interval_seconds
    return Outage(
        started_at=started_at,
        ended_at=ended_at,
        duration_seconds=max(interval_seconds, duration_seconds),
        failed_samples=len(failed_run),
    )


def format_console_summary(report: SessionReport) -> str:
    summary = report.summary
    lines = [
        "watch4ping report",
        f"Target: {report.session.target}",
        f"Duration: {format_duration(summary.duration_seconds)}",
        f"Samples: {summary.total_samples} "
        f"({summary.successful_samples} ok, {summary.failed_samples} failed)",
        f"Uptime: {summary.uptime_percent:.2f}%",
        f"Outages: {summary.outage_count}",
        f"Longest outage: {format_duration(summary.longest_outage_seconds)}",
        f"Latency: {format_latency_summary(summary)}",
        f"Latency spikes: {summary.latency_spike_count}",
    ]
    return "\n".join(lines)


def format_markdown_report(report: SessionReport) -> str:
    summary = report.summary
    lines = [
        "# watch4ping report",
        "",
        f"- Target: `{report.session.target}`",
        f"- Started: `{report.session.started_at.isoformat()}`",
        f"- Ended: `{report.session.ended_at.isoformat()}`",
        f"- Duration: `{format_duration(summary.duration_seconds)}`",
        f"- Interval: `{report.session.interval_seconds:g}s`",
        f"- Timeout: `{report.session.timeout_seconds:g}s`",
        f"- Fail threshold: `{report.session.fail_threshold}`",
        "",
        "## Summary",
        "",
        f"- Samples: `{summary.total_samples}`",
        f"- Successful samples: `{summary.successful_samples}`",
        f"- Failed samples: `{summary.failed_samples}`",
        f"- Uptime: `{summary.uptime_percent:.2f}%`",
        f"- Outages: `{summary.outage_count}`",
        f"- Longest outage: `{format_duration(summary.longest_outage_seconds)}`",
        f"- Latency: `{format_latency_summary(summary)}`",
        f"- Latency spikes: `{summary.latency_spike_count}`",
        "",
        "## Outages",
        "",
    ]

    if report.outages:
        lines.extend(
            [
                "| Started | Ended | Duration | Failed samples |",
                "| --- | --- | ---: | ---: |",
            ]
        )
        for outage in report.outages:
            lines.append(
                f"| `{outage.started_at.isoformat()}` | `{outage.ended_at.isoformat()}` | "
                f"`{format_duration(outage.duration_seconds)}` | `{outage.failed_samples}` |"
            )
    else:
        lines.append("No outages detected.")

    lines.extend(["", "## Latency Spikes", ""])
    if report.latency_spikes:
        lines.extend(
            [
                "| Sequence | Timestamp | Latency | Threshold |",
                "| ---: | --- | ---: | ---: |",
            ]
        )
        for spike in report.latency_spikes:
            lines.append(
                f"| `{spike.sequence}` | `{spike.timestamp.isoformat()}` | "
                f"`{spike.latency_ms:.1f} ms` | `{spike.threshold_ms:.1f} ms` |"
            )
    else:
        lines.append("No latency spikes detected.")

    lines.append("")
    return "\n".join(lines)


def format_html_report(report: SessionReport) -> str:
    summary = report.summary
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>watch4ping report - {escape(report.session.target)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --text: #20242a;
      --muted: #667085;
      --panel: #ffffff;
      --line: #d9dee7;
      --ok: #16794c;
      --bad: #c24136;
      --accent: #2266aa;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.45;
    }}
    main {{
      max-width: 1120px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    header {{
      border-bottom: 1px solid var(--line);
      margin-bottom: 24px;
      padding-bottom: 18px;
    }}
    h1, h2 {{ margin: 0; }}
    h1 {{ font-size: 28px; }}
    h2 {{ font-size: 18px; margin-bottom: 12px; }}
    .subtitle {{ color: var(--muted); margin-top: 6px; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 24px;
    }}
    .metric, section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
    }}
    .metric {{ padding: 14px; }}
    .label {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
    }}
    .value {{
      font-size: 22px;
      font-weight: 700;
      margin-top: 4px;
    }}
    section {{
      margin-top: 16px;
      padding: 16px;
      overflow-x: auto;
    }}
    svg {{
      display: block;
      width: 100%;
      min-width: 620px;
      height: 240px;
      border: 1px solid var(--line);
      background: #fbfcfe;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      min-width: 680px;
      font-size: 14px;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 8px 10px;
      text-align: left;
      white-space: nowrap;
    }}
    th {{ color: var(--muted); font-weight: 600; }}
    .ok {{ color: var(--ok); font-weight: 600; }}
    .fail {{ color: var(--bad); font-weight: 600; }}
    .empty {{ color: var(--muted); margin: 0; }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>watch4ping report</h1>
      <div class="subtitle">
        Target {escape(report.session.target)} from {escape(report.session.started_at.isoformat())}
        to {escape(report.session.ended_at.isoformat())}
      </div>
    </header>

    <div class="grid">
      {html_metric("Duration", format_duration(summary.duration_seconds))}
      {html_metric("Uptime", f"{summary.uptime_percent:.2f}%")}
      {html_metric("Samples", str(summary.total_samples))}
      {html_metric("Outages", str(summary.outage_count))}
      {html_metric("Longest outage", format_duration(summary.longest_outage_seconds))}
      {html_metric("Latency spikes", str(summary.latency_spike_count))}
    </div>

    <section>
      <h2>Latency</h2>
      {format_latency_chart(report)}
      <p class="subtitle">{escape(format_latency_summary(summary))}</p>
    </section>

    <section>
      <h2>Outages</h2>
      {format_html_outage_table(report)}
    </section>

    <section>
      <h2>Latency Spikes</h2>
      {format_html_spike_table(report)}
    </section>

    <section>
      <h2>Samples</h2>
      {format_html_sample_table(report)}
    </section>
  </main>
</body>
</html>
"""


def html_metric(label: str, value: str) -> str:
    return (
        '<div class="metric">'
        f'<div class="label">{escape(label)}</div>'
        f'<div class="value">{escape(value)}</div>'
        "</div>"
    )


def format_latency_chart(report: SessionReport) -> str:
    samples = [
        sample
        for sample in report.session.samples
        if sample.ok and sample.latency_ms is not None
    ]
    if not samples:
        return '<p class="empty">No successful latency samples recorded.</p>'

    width = 960
    height = 240
    padding = 28
    max_latency = max(sample.latency_ms for sample in samples) or 1
    x_step = (width - padding * 2) / max(1, len(samples) - 1)

    points: list[tuple[float, float]] = []
    for index, sample in enumerate(samples):
        x = padding + index * x_step
        y = height - padding - ((sample.latency_ms / max_latency) * (height - padding * 2))
        points.append((x, y))

    point_marks = "\n".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="#2266aa" />'
        for x, y in points
    )
    path = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    max_label = escape(f"{max_latency:.1f} ms")

    return f"""<svg viewBox="0 0 {width} {height}" role="img" aria-label="Latency chart">
  <line x1="{padding}" y1="{height - padding}" x2="{width - padding}" y2="{height - padding}" stroke="#d9dee7" />
  <line x1="{padding}" y1="{padding}" x2="{padding}" y2="{height - padding}" stroke="#d9dee7" />
  <text x="{padding + 4}" y="{padding - 8}" fill="#667085" font-size="12">{max_label}</text>
  <polyline points="{path}" fill="none" stroke="#2266aa" stroke-width="2" />
  {point_marks}
</svg>"""


def format_html_outage_table(report: SessionReport) -> str:
    if not report.outages:
        return '<p class="empty">No outages detected.</p>'

    rows = "\n".join(
        "<tr>"
        f"<td>{escape(outage.started_at.isoformat())}</td>"
        f"<td>{escape(outage.ended_at.isoformat())}</td>"
        f"<td>{escape(format_duration(outage.duration_seconds))}</td>"
        f"<td>{outage.failed_samples}</td>"
        "</tr>"
        for outage in report.outages
    )
    return (
        "<table><thead><tr><th>Started</th><th>Ended</th><th>Duration</th>"
        f"<th>Failed samples</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def format_html_spike_table(report: SessionReport) -> str:
    if not report.latency_spikes:
        return '<p class="empty">No latency spikes detected.</p>'

    rows = "\n".join(
        "<tr>"
        f"<td>{spike.sequence}</td>"
        f"<td>{escape(spike.formatted_timestamp)}</td>"
        f"<td>{spike.latency_ms:.1f} ms</td>"
        f"<td>{spike.threshold_ms:.1f} ms</td>"
        "</tr>"
        for spike in report.latency_spikes
    )
    return (
        "<table><thead><tr><th>Sequence</th><th>Timestamp</th><th>Latency</th>"
        f"<th>Threshold</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def format_html_sample_table(report: SessionReport) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{sample.sequence}</td>"
        f"<td>{escape(sample.formatted_timestamp)}</td>"
        f"{format_html_sample_status(sample.ok)}"
        f"<td>{format_optional_latency(sample.latency_ms)}</td>"
        f"<td>{escape(sample.error or '')}</td>"
        "</tr>"
        for sample in report.session.samples
    )
    return (
        "<table><thead><tr><th>Sequence</th><th>Timestamp</th><th>Status</th>"
        f"<th>Latency</th><th>Error</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def format_optional_latency(latency_ms: float | None) -> str:
    if latency_ms is None:
        return ""
    return escape(f"{latency_ms:.1f} ms")


def format_html_sample_status(ok: bool) -> str:
    status_class = "ok" if ok else "fail"
    status_label = "OK" if ok else "FAIL"
    return f'<td class="{status_class}">{status_label}</td>'


def format_latency_summary(summary: ReportSummary) -> str:
    if summary.avg_latency_ms is None:
        return "n/a"

    jitter = f", jitter {summary.jitter_ms:.1f} ms" if summary.jitter_ms is not None else ""
    percentiles = (
        f", p50 {summary.p50_latency_ms:.1f} ms, "
        f"p95 {summary.p95_latency_ms:.1f} ms, "
        f"p99 {summary.p99_latency_ms:.1f} ms"
        if summary.p50_latency_ms is not None
        and summary.p95_latency_ms is not None
        and summary.p99_latency_ms is not None
        else ""
    )
    return (
        f"avg {summary.avg_latency_ms:.1f} ms, "
        f"min {summary.min_latency_ms:.1f} ms, "
        f"max {summary.max_latency_ms:.1f} ms"
        f"{percentiles}"
        f"{jitter}"
    )


def format_duration(seconds: float) -> str:
    seconds = int(round(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"
