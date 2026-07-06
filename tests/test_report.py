from datetime import datetime, timedelta, timezone

import pytest

from watch4ping.models import MonitorSession, PingSample, Target
from watch4ping.report import (
    build_report,
    format_duration,
    format_html_report,
    format_markdown_report,
    percentile,
)


def test_ping_sample_includes_formatted_timestamp():
    timestamp = datetime(2026, 7, 1, 12, 34, 56, tzinfo=timezone.utc)
    sample = PingSample(1, timestamp, True, 10.0)

    assert sample.to_dict()["formatted_timestamp"] == "2026-07-01 12:34:56 UTC"


def test_ping_sample_includes_target_fields():
    timestamp = datetime(2026, 7, 1, 12, 34, 56, tzinfo=timezone.utc)
    sample = PingSample(
        1,
        timestamp,
        True,
        10.0,
        target_label="cloudflare",
        target_host="1.1.1.1",
    )

    assert sample.to_dict()["target_label"] == "cloudflare"
    assert sample.to_dict()["target_host"] == "1.1.1.1"


def test_monitor_session_includes_targets():
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    session = MonitorSession(
        targets=(
            Target(label="router", host="192.168.1.1"),
            Target(label="cloudflare", host="1.1.1.1"),
        ),
        interval_seconds=2,
        timeout_seconds=1,
        fail_threshold=3,
        started_at=start,
        ended_at=start + timedelta(seconds=10),
    )

    session_data = session.to_dict()

    assert session.target == "192.168.1.1"
    assert session_data["target"] == "192.168.1.1"
    assert session_data["targets"] == [
        {"label": "router", "host": "192.168.1.1"},
        {"label": "cloudflare", "host": "1.1.1.1"},
    ]


def test_build_report_detects_thresholded_outages():
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    samples = (
        PingSample(1, start, True, 10.0),
        PingSample(2, start + timedelta(seconds=2), False, error="timeout"),
        PingSample(3, start + timedelta(seconds=4), False, error="timeout"),
        PingSample(4, start + timedelta(seconds=6), False, error="timeout"),
        PingSample(5, start + timedelta(seconds=8), True, 20.0),
    )
    session = MonitorSession(
        targets=(Target(label="cloudflare", host="1.1.1.1"),),
        interval_seconds=2,
        timeout_seconds=1,
        fail_threshold=3,
        started_at=start,
        ended_at=start + timedelta(seconds=10),
        samples=samples,
    )

    report = build_report(session)

    assert report.summary.total_samples == 5
    assert report.summary.successful_samples == 2
    assert report.summary.failed_samples == 3
    assert report.summary.uptime_percent == 40
    assert report.summary.outage_count == 1
    assert report.outages[0].failed_samples == 3


def test_build_report_includes_schema_version_and_latency_percentiles():
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    samples = (
        PingSample(1, start, True, 10.0),
        PingSample(2, start + timedelta(seconds=2), True, 20.0),
        PingSample(3, start + timedelta(seconds=4), True, 30.0),
        PingSample(4, start + timedelta(seconds=6), True, 40.0),
        PingSample(5, start + timedelta(seconds=8), True, 200.0),
    )
    session = MonitorSession(
        targets=(Target(label="cloudflare", host="1.1.1.1"),),
        interval_seconds=2,
        timeout_seconds=1,
        fail_threshold=3,
        started_at=start,
        ended_at=start + timedelta(seconds=10),
        samples=samples,
    )

    report = build_report(session)
    report_data = report.to_dict()

    assert report.schema_version == "3"
    assert report_data["schema_version"] == "3"
    assert report.summary.p50_latency_ms == 30
    assert report.summary.p95_latency_ms == pytest.approx(168)
    assert report.summary.p99_latency_ms == pytest.approx(193.6)


def test_build_report_detects_latency_spikes():
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    samples = (
        PingSample(1, start, True, 10.0),
        PingSample(2, start + timedelta(seconds=2), True, 20.0),
        PingSample(3, start + timedelta(seconds=4), True, 30.0),
        PingSample(4, start + timedelta(seconds=6), True, 40.0),
        PingSample(5, start + timedelta(seconds=8), True, 200.0),
    )
    session = MonitorSession(
        targets=(Target(label="cloudflare", host="1.1.1.1"),),
        interval_seconds=2,
        timeout_seconds=1,
        fail_threshold=3,
        started_at=start,
        ended_at=start + timedelta(seconds=10),
        samples=samples,
    )

    report = build_report(session)

    assert report.summary.latency_spike_count == 1
    assert report.summary.latency_spike_threshold_ms == pytest.approx(168)
    assert report.latency_spikes[0].sequence == 5
    assert report.latency_spikes[0].latency_ms == 200


def test_build_report_includes_per_target_summaries_and_diagnosis():
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    samples = (
        PingSample(
            1,
            start,
            True,
            2.0,
            target_label="router",
            target_host="192.168.1.1",
        ),
        PingSample(
            1,
            start + timedelta(milliseconds=20),
            False,
            error="timeout",
            target_label="cloudflare",
            target_host="1.1.1.1",
        ),
        PingSample(
            2,
            start + timedelta(seconds=2),
            True,
            2.5,
            target_label="router",
            target_host="192.168.1.1",
        ),
        PingSample(
            2,
            start + timedelta(seconds=2, milliseconds=20),
            False,
            error="timeout",
            target_label="cloudflare",
            target_host="1.1.1.1",
        ),
    )
    session = MonitorSession(
        targets=(
            Target(label="router", host="192.168.1.1"),
            Target(label="cloudflare", host="1.1.1.1"),
        ),
        interval_seconds=2,
        timeout_seconds=1,
        fail_threshold=2,
        started_at=start,
        ended_at=start + timedelta(seconds=4),
        samples=samples,
    )

    report = build_report(session)

    assert len(report.target_reports) == 2
    assert report.target_reports[0].summary.uptime_percent == 100
    assert report.target_reports[1].summary.uptime_percent == 0
    assert report.target_reports[1].summary.outage_count == 1
    assert report.diagnoses[0].code == "wan_or_isp_issue"
    assert "likely ISP/WAN issue" in report.diagnoses[0].message


def test_build_report_detects_dns_diagnosis():
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    samples = (
        PingSample(
            1,
            start,
            True,
            12.0,
            target_label="cloudflare",
            target_host="1.1.1.1",
        ),
        PingSample(
            1,
            start + timedelta(milliseconds=20),
            False,
            error="cannot resolve",
            target_label="dns",
            target_host="google.com",
        ),
    )
    session = MonitorSession(
        targets=(
            Target(label="cloudflare", host="1.1.1.1"),
            Target(label="dns", host="google.com"),
        ),
        interval_seconds=2,
        timeout_seconds=1,
        fail_threshold=1,
        started_at=start,
        ended_at=start + timedelta(seconds=2),
        samples=samples,
    )

    report = build_report(session)

    assert report.diagnoses[0].code == "dns_or_hostname_issue"


def test_build_report_does_not_treat_unlabeled_private_ip_as_router():
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    samples = (
        PingSample(
            1,
            start,
            True,
            12.0,
            target_label="cloudflare",
            target_host="1.1.1.1",
        ),
        PingSample(
            1,
            start + timedelta(milliseconds=20),
            False,
            error="timeout",
            target_label="foo",
            target_host="10.255.255.1",
        ),
    )
    session = MonitorSession(
        targets=(
            Target(label="cloudflare", host="1.1.1.1"),
            Target(label="foo", host="10.255.255.1"),
        ),
        interval_seconds=2,
        timeout_seconds=1,
        fail_threshold=1,
        started_at=start,
        ended_at=start + timedelta(seconds=2),
        samples=samples,
    )

    report = build_report(session)

    assert report.diagnoses[0].code == "target_reachability_issue"
    assert "target-specific reachability issue" in report.diagnoses[0].message


def test_markdown_report_includes_diagnosis_and_target_summary():
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    samples = (
        PingSample(
            1,
            start,
            True,
            2.0,
            target_label="router",
            target_host="192.168.1.1",
        ),
    )
    session = MonitorSession(
        targets=(Target(label="router", host="192.168.1.1"),),
        interval_seconds=2,
        timeout_seconds=1,
        fail_threshold=3,
        started_at=start,
        ended_at=start + timedelta(seconds=2),
        samples=samples,
    )

    markdown = format_markdown_report(build_report(session))

    assert "## Diagnosis" in markdown
    assert "## Targets" in markdown
    assert "`router=192.168.1.1`" in markdown


def test_format_html_report_includes_summary_chart_and_samples():
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    samples = (
        PingSample(1, start, True, 10.0),
        PingSample(2, start + timedelta(seconds=2), False, error="timeout"),
        PingSample(3, start + timedelta(seconds=4), True, 20.0),
    )
    session = MonitorSession(
        targets=(Target(label="example", host="example.test"),),
        interval_seconds=2,
        timeout_seconds=1,
        fail_threshold=2,
        started_at=start,
        ended_at=start + timedelta(seconds=6),
        samples=samples,
    )

    html = format_html_report(build_report(session))

    assert "<!doctype html>" in html
    assert "watch4ping report" in html
    assert "example.test" in html
    assert "Latency" in html
    assert "<svg" in html
    assert "timeout" in html


def test_build_report_ignores_short_failure_runs():
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    samples = (
        PingSample(1, start, True, 10.0),
        PingSample(2, start + timedelta(seconds=2), False, error="timeout"),
        PingSample(3, start + timedelta(seconds=4), True, 12.0),
    )
    session = MonitorSession(
        targets=(Target(label="cloudflare", host="1.1.1.1"),),
        interval_seconds=2,
        timeout_seconds=1,
        fail_threshold=2,
        started_at=start,
        ended_at=start + timedelta(seconds=6),
        samples=samples,
    )

    report = build_report(session)

    assert report.summary.outage_count == 0


def test_percentile_interpolates_sorted_values():
    assert percentile([200, 10, 40, 20, 30], 50) == 30
    assert percentile([200, 10, 40, 20, 30], 95) == pytest.approx(168)


def test_format_duration():
    assert format_duration(5) == "5s"
    assert format_duration(65) == "1m 5s"
    assert format_duration(3665) == "1h 1m 5s"
