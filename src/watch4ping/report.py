from __future__ import annotations

from html import escape
from ipaddress import ip_address
from statistics import fmean, pstdev

from .models import (
    Diagnosis,
    LatencySpike,
    MonitorSession,
    Outage,
    PingSample,
    ReportSummary,
    SessionReport,
    Target,
    TargetReport,
)


REPORT_SCHEMA_VERSION = "3"


def build_report(session: MonitorSession) -> SessionReport:
    target_reports = build_target_reports(session)
    outages = detect_outages(session.samples, session.fail_threshold, session.interval_seconds)
    latency_spikes = detect_latency_spikes(
        session.samples,
        calculate_latency_spike_threshold_for_samples(session.samples),
    )

    summary = build_summary(
        samples=session.samples,
        duration_seconds=(session.ended_at - session.started_at).total_seconds(),
        outage_count=len(outages),
        longest_outage_seconds=max((outage.duration_seconds for outage in outages), default=0.0),
        latency_spike_count=len(latency_spikes),
        latency_spike_threshold_ms=calculate_latency_spike_threshold_for_samples(session.samples),
    )
    return SessionReport(
        schema_version=REPORT_SCHEMA_VERSION,
        session=session,
        summary=summary,
        outages=tuple(outages),
        latency_spikes=tuple(latency_spikes),
        target_reports=tuple(target_reports),
        diagnoses=tuple(diagnose_session(session, target_reports)),
    )


def build_target_reports(session: MonitorSession) -> list[TargetReport]:
    reports: list[TargetReport] = []
    duration_seconds = (session.ended_at - session.started_at).total_seconds()

    for target in session.targets:
        samples = samples_for_target(session, target)
        outages = detect_outages(samples, session.fail_threshold, session.interval_seconds)
        latency_spike_threshold_ms = calculate_latency_spike_threshold_for_samples(samples)
        latency_spikes = detect_latency_spikes(samples, latency_spike_threshold_ms)
        reports.append(
            TargetReport(
                target=target,
                summary=build_summary(
                    samples=samples,
                    duration_seconds=duration_seconds,
                    outage_count=len(outages),
                    longest_outage_seconds=max(
                        (outage.duration_seconds for outage in outages),
                        default=0.0,
                    ),
                    latency_spike_count=len(latency_spikes),
                    latency_spike_threshold_ms=latency_spike_threshold_ms,
                ),
                outages=tuple(outages),
                latency_spikes=tuple(latency_spikes),
            )
        )

    return reports


def build_summary(
    samples: tuple[PingSample, ...],
    duration_seconds: float,
    outage_count: int,
    longest_outage_seconds: float,
    latency_spike_count: int,
    latency_spike_threshold_ms: float | None,
) -> ReportSummary:
    latencies = [
        sample.latency_ms
        for sample in samples
        if sample.ok and sample.latency_ms is not None
    ]
    total_samples = len(samples)
    successful_samples = sum(1 for sample in samples if sample.ok)
    failed_samples = total_samples - successful_samples
    p50_latency_ms = percentile(latencies, 50)
    p95_latency_ms = percentile(latencies, 95)
    p99_latency_ms = percentile(latencies, 99)
    avg_latency_ms = fmean(latencies) if latencies else None
    jitter_ms = pstdev(latencies) if len(latencies) > 1 else None

    return ReportSummary(
        duration_seconds=max(0.0, duration_seconds),
        total_samples=total_samples,
        successful_samples=successful_samples,
        failed_samples=failed_samples,
        uptime_percent=(successful_samples / total_samples * 100) if total_samples else 0.0,
        outage_count=outage_count,
        longest_outage_seconds=longest_outage_seconds,
        min_latency_ms=min(latencies) if latencies else None,
        avg_latency_ms=avg_latency_ms,
        max_latency_ms=max(latencies) if latencies else None,
        p50_latency_ms=p50_latency_ms,
        p95_latency_ms=p95_latency_ms,
        p99_latency_ms=p99_latency_ms,
        jitter_ms=jitter_ms,
        latency_spike_count=latency_spike_count,
        latency_spike_threshold_ms=latency_spike_threshold_ms,
    )


def samples_for_target(session: MonitorSession, target: Target) -> tuple[PingSample, ...]:
    return tuple(
        sample
        for sample in session.samples
        if sample_matches_target(sample, target, session.targets[0])
    )


def sample_matches_target(sample: PingSample, target: Target, default_target: Target) -> bool:
    sample_label = sample.target_label or default_target.label
    sample_host = sample.target_host or default_target.host
    return sample_label == target.label and sample_host == target.host


def calculate_latency_spike_threshold_for_samples(
    samples: tuple[PingSample, ...],
) -> float | None:
    latencies = [
        sample.latency_ms
        for sample in samples
        if sample.ok and sample.latency_ms is not None
    ]
    return calculate_latency_spike_threshold(
        avg_latency_ms=fmean(latencies) if latencies else None,
        p95_latency_ms=percentile(latencies, 95),
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
            target_label=sample.target_label,
            target_host=sample.target_host,
        )
        for sample in samples
        if sample.ok and sample.latency_ms is not None and sample.latency_ms >= threshold_ms
    ]


def detect_outages(
    samples: tuple[PingSample, ...],
    fail_threshold: int,
    interval_seconds: float,
) -> list[Outage]:
    outages: list[Outage] = []
    failed_run: list[PingSample] = []

    for sample in samples:
        if not sample.ok:
            failed_run.append(sample)
            continue

        if len(failed_run) >= fail_threshold:
            outages.append(outage_from_failed_run(failed_run, interval_seconds))
        failed_run = []

    if len(failed_run) >= fail_threshold:
        outages.append(outage_from_failed_run(failed_run, interval_seconds))

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


def diagnose_session(
    _session: MonitorSession,
    target_reports: list[TargetReport],
) -> list[Diagnosis]:
    if len(target_reports) < 2:
        return [
            Diagnosis(
                code="single_target",
                message="Single target monitored; add router, external IP, and hostname targets for diagnosis.",
            )
        ]

    router_report = find_router_report(target_reports)
    external_ip_report = find_external_ip_report(target_reports, exclude=router_report)
    hostname_report = find_hostname_report(target_reports)

    diagnoses: list[Diagnosis] = []
    if router_report and router_report.summary.failed_samples > 0:
        diagnoses.append(
            Diagnosis(
                code="local_network_issue",
                message=(
                    f"{router_report.target.label} had failures; likely local network, Wi-Fi, "
                    "Ethernet, or router issue."
                ),
            )
        )

    if (
        router_report
        and external_ip_report
        and router_report.summary.uptime_percent == 100
        and external_ip_report.summary.failed_samples > 0
    ):
        diagnoses.append(
            Diagnosis(
                code="wan_or_isp_issue",
                message=(
                    f"{router_report.target.label} stayed reachable while "
                    f"{external_ip_report.target.label} failed; likely ISP/WAN issue."
                ),
            )
        )

    if (
        external_ip_report
        and hostname_report
        and external_ip_report.summary.uptime_percent == 100
        and hostname_report.summary.failed_samples > 0
    ):
        diagnoses.append(
            Diagnosis(
                code="dns_or_hostname_issue",
                message=(
                    f"{external_ip_report.target.label} stayed reachable while "
                    f"{hostname_report.target.label} failed; likely DNS or hostname resolution issue."
                ),
            )
        )

    failed_target_reports = [
        target_report
        for target_report in target_reports
        if target_report.summary.failed_samples > 0
    ]
    if not diagnoses and failed_target_reports:
        failed_targets = ", ".join(
            format_target(target_report.target)
            for target_report in failed_target_reports
        )
        diagnoses.append(
            Diagnosis(
                code="target_reachability_issue",
                message=(
                    f"{failed_targets} had failures without a router/ISP/DNS pattern; "
                    "likely target-specific reachability issue."
                ),
            )
        )

    if not diagnoses:
        diagnoses.append(
            Diagnosis(
                code="no_clear_issue",
                message="No clear network issue pattern detected from the configured targets.",
            )
        )

    return diagnoses


def find_router_report(target_reports: list[TargetReport]) -> TargetReport | None:
    for target_report in target_reports:
        label = target_report.target.label.lower()
        if "router" in label or "gateway" in label:
            return target_report

    return None


def find_external_ip_report(
    target_reports: list[TargetReport],
    exclude: TargetReport | None,
) -> TargetReport | None:
    for target_report in target_reports:
        if target_report is exclude:
            continue
        if is_ip(target_report.target.host) and not is_private_ip(target_report.target.host):
            return target_report
    return None


def find_hostname_report(target_reports: list[TargetReport]) -> TargetReport | None:
    for target_report in target_reports:
        if not is_ip(target_report.target.host):
            return target_report
    return None


def is_ip(host: str) -> bool:
    try:
        ip_address(host)
    except ValueError:
        return False
    return True


def is_private_ip(host: str) -> bool:
    try:
        return ip_address(host).is_private
    except ValueError:
        return False


def format_console_summary(report: SessionReport) -> str:
    summary = report.summary
    lines = [
        "watch4ping report",
        f"Targets: {format_session_targets(report.session)}",
        f"Duration: {format_duration(summary.duration_seconds)}",
        f"Samples: {summary.total_samples} "
        f"({summary.successful_samples} ok, {summary.failed_samples} failed)",
        f"Uptime: {summary.uptime_percent:.2f}%",
        f"Outages: {summary.outage_count}",
        f"Longest outage: {format_duration(summary.longest_outage_seconds)}",
        f"Latency: {format_latency_summary(summary)}",
        f"Latency spikes: {summary.latency_spike_count}",
        f"Diagnosis: {report.diagnoses[0].message if report.diagnoses else 'n/a'}",
    ]
    return "\n".join(lines)


def format_markdown_report(report: SessionReport) -> str:
    summary = report.summary
    lines = [
        "# watch4ping report",
        "",
        f"- Targets: `{format_session_targets(report.session)}`",
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
        "## Diagnosis",
        "",
    ]

    lines.extend(f"- {diagnosis.message}" for diagnosis in report.diagnoses)
    lines.extend(
        [
            "",
            "## Targets",
            "",
            "| Target | Samples | Uptime | Outages | Avg latency | Spikes |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for target_report in report.target_reports:
        lines.append(format_markdown_target_row(target_report))

    lines.extend(
        [
            "",
            "## Outages",
            "",
        ]
    )

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
  <title>watch4ping report - {escape(format_session_targets(report.session))}</title>
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
        Targets {escape(format_session_targets(report.session))} from {escape(report.session.started_at.isoformat())}
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
      <h2>Diagnosis</h2>
      {format_html_diagnoses(report)}
    </section>

    <section>
      <h2>Targets</h2>
      {format_html_target_table(report)}
    </section>

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


def format_session_targets(session: MonitorSession) -> str:
    return ", ".join(
        f"{target.label}={target.host}" if target.label != target.host else target.host
        for target in session.targets
    )


def format_markdown_target_row(target_report: TargetReport) -> str:
    summary = target_report.summary
    avg_latency = (
        f"{summary.avg_latency_ms:.1f} ms"
        if summary.avg_latency_ms is not None
        else "n/a"
    )
    target = format_target(target_report.target)
    return (
        f"| `{target}` | `{summary.total_samples}` | `{summary.uptime_percent:.2f}%` | "
        f"`{summary.outage_count}` | `{avg_latency}` | `{summary.latency_spike_count}` |"
    )


def format_target(target: Target) -> str:
    if target.label == target.host:
        return target.host
    return f"{target.label}={target.host}"


def format_html_diagnoses(report: SessionReport) -> str:
    if not report.diagnoses:
        return '<p class="empty">No diagnosis available.</p>'

    items = "\n".join(
        f"<li>{escape(diagnosis.message)}</li>"
        for diagnosis in report.diagnoses
    )
    return f"<ul>{items}</ul>"


def format_html_target_table(report: SessionReport) -> str:
    rows = "\n".join(
        "<tr>"
        f"<td>{escape(format_target(target_report.target))}</td>"
        f"<td>{target_report.summary.total_samples}</td>"
        f"<td>{target_report.summary.uptime_percent:.2f}%</td>"
        f"<td>{target_report.summary.outage_count}</td>"
        f"<td>{format_optional_latency(target_report.summary.avg_latency_ms)}</td>"
        f"<td>{target_report.summary.latency_spike_count}</td>"
        "</tr>"
        for target_report in report.target_reports
    )
    return (
        "<table><thead><tr><th>Target</th><th>Samples</th><th>Uptime</th>"
        f"<th>Outages</th><th>Avg latency</th><th>Spikes</th></tr></thead><tbody>{rows}</tbody></table>"
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
        f"<td>{escape(format_sample_target(sample))}</td>"
        f"<td>{escape(sample.formatted_timestamp)}</td>"
        f"{format_html_sample_status(sample.ok)}"
        f"<td>{format_optional_latency(sample.latency_ms)}</td>"
        f"<td>{escape(sample.error or '')}</td>"
        "</tr>"
        for sample in report.session.samples
    )
    return (
        "<table><thead><tr><th>Sequence</th><th>Target</th><th>Timestamp</th><th>Status</th>"
        f"<th>Latency</th><th>Error</th></tr></thead><tbody>{rows}</tbody></table>"
    )


def format_sample_target(sample: PingSample) -> str:
    if not sample.target_label and not sample.target_host:
        return ""
    if sample.target_label == sample.target_host or not sample.target_label:
        return sample.target_host or ""
    return f"{sample.target_label}={sample.target_host}"


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
