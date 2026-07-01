from datetime import datetime, timedelta, timezone

from watch4ping.models import MonitorSession, PingSample
from watch4ping.report import build_report, format_duration


def test_ping_sample_includes_formatted_timestamp():
    timestamp = datetime(2026, 7, 1, 12, 34, 56, tzinfo=timezone.utc)
    sample = PingSample(1, timestamp, True, 10.0)

    assert sample.to_dict()["formatted_timestamp"] == "2026-07-01 12:34:56 UTC"


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
        target="1.1.1.1",
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


def test_build_report_ignores_short_failure_runs():
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    samples = (
        PingSample(1, start, True, 10.0),
        PingSample(2, start + timedelta(seconds=2), False, error="timeout"),
        PingSample(3, start + timedelta(seconds=4), True, 12.0),
    )
    session = MonitorSession(
        target="1.1.1.1",
        interval_seconds=2,
        timeout_seconds=1,
        fail_threshold=2,
        started_at=start,
        ended_at=start + timedelta(seconds=6),
        samples=samples,
    )

    report = build_report(session)

    assert report.summary.outage_count == 0


def test_format_duration():
    assert format_duration(5) == "5s"
    assert format_duration(65) == "1m 5s"
    assert format_duration(3665) == "1h 1m 5s"
