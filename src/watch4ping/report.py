from __future__ import annotations

from statistics import fmean, pstdev

from .models import MonitorSession, Outage, ReportSummary, SessionReport


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

    summary = ReportSummary(
        duration_seconds=max(0.0, duration_seconds),
        total_samples=total_samples,
        successful_samples=successful_samples,
        failed_samples=failed_samples,
        uptime_percent=(successful_samples / total_samples * 100) if total_samples else 0.0,
        outage_count=len(outages),
        longest_outage_seconds=max((outage.duration_seconds for outage in outages), default=0.0),
        min_latency_ms=min(latencies) if latencies else None,
        avg_latency_ms=fmean(latencies) if latencies else None,
        max_latency_ms=max(latencies) if latencies else None,
        jitter_ms=pstdev(latencies) if len(latencies) > 1 else None,
    )
    return SessionReport(session=session, summary=summary, outages=tuple(outages))


def detect_outages(session: MonitorSession) -> list[Outage]:
    outages: list[Outage] = []
    failed_run = []

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


def outage_from_failed_run(failed_run, interval_seconds: float) -> Outage:
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

    lines.append("")
    return "\n".join(lines)


def format_latency_summary(summary: ReportSummary) -> str:
    if summary.avg_latency_ms is None:
        return "n/a"

    jitter = f", jitter {summary.jitter_ms:.1f} ms" if summary.jitter_ms is not None else ""
    return (
        f"avg {summary.avg_latency_ms:.1f} ms, "
        f"min {summary.min_latency_ms:.1f} ms, "
        f"max {summary.max_latency_ms:.1f} ms"
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

