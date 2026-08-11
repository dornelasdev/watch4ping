from datetime import datetime, timezone
from io import StringIO

import pytest

from watch4ping.models import PingResult, PingSample, Target
from watch4ping.monitor import (
    LiveTargetStats,
    format_live_stats,
    format_sample_line,
    print_sample_group,
    probe_targets,
    should_stop_before_next_sample,
    update_live_stats,
)


class FakeProbe:
    def __init__(self):
        self.calls = []

    def ping(self, target: str) -> PingResult:
        self.calls.append(target)
        if target == "192.168.1.1":
            return PingResult(ok=True, latency_ms=2.5)
        return PingResult(ok=False, error="timeout")


def test_probe_targets_records_one_sample_per_target():
    probe = FakeProbe()
    targets = (
        Target(label="router", host="192.168.1.1"),
        Target(label="cloudflare", host="1.1.1.1"),
    )

    samples = probe_targets(sequence=7, targets=targets, probe=probe)

    assert probe.calls == ["192.168.1.1", "1.1.1.1"]
    assert [sample.sequence for sample in samples] == [7, 7]
    assert [sample.target_label for sample in samples] == ["router", "cloudflare"]
    assert [sample.target_host for sample in samples] == ["192.168.1.1", "1.1.1.1"]
    assert samples[0].ok is True
    assert samples[0].latency_ms == 2.5
    assert samples[1].ok is False
    assert samples[1].error == "timeout"


def test_format_sample_line_formats_successful_sample():
    sample = PingSample(
        sequence=1,
        timestamp=datetime(2026, 7, 11, tzinfo=timezone.utc),
        ok=True,
        latency_ms=12.345,
        target_label="cloudflare",
        target_host="1.1.1.1",
    )

    assert format_sample_line(sample) == "cloudflare  OK    12.3 ms"


def test_live_target_stats_track_success_failure_loss_and_average():
    stats = LiveTargetStats()
    timestamp = datetime(2026, 7, 11, tzinfo=timezone.utc)

    stats.add(PingSample(1, timestamp, True, 10.0))
    stats.add(PingSample(2, timestamp, False, error="timeout"))
    stats.add(PingSample(3, timestamp, True, 30.0))

    assert stats.total_samples == 3
    assert stats.successful_samples == 2
    assert stats.failed_samples == 1
    assert stats.loss_percent == pytest.approx(100 / 3)
    assert stats.avg_latency_ms == 20
    assert format_live_stats(stats) == "ok 2  fail 1  loss 33.3%  avg 20.0 ms"


def test_print_sample_group_formats_round_output():
    stream = StringIO()
    samples = [
        PingSample(
            sequence=2,
            timestamp=datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc),
            ok=True,
            latency_ms=2.5,
            target_label="router",
            target_host="192.168.1.1",
        ),
        PingSample(
            sequence=2,
            timestamp=datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc),
            ok=False,
            error="timeout",
            target_label="cloudflare",
            target_host="1.1.1.1",
        ),
    ]

    print_sample_group(samples, stream=stream)

    assert stream.getvalue() == (
        "[2] 2026-07-11 12:00:00 UTC\n"
        "  router      OK    2.5 ms   | ok 1  fail 0  loss 0.0%  avg 2.5 ms\n"
        "  cloudflare  FAIL  timeout  | ok 0  fail 1  loss 100.0%  avg n/a\n"
    )


def test_print_sample_group_uses_cumulative_live_stats():
    stream = StringIO()
    timestamp = datetime(2026, 7, 11, 12, 0, 0, tzinfo=timezone.utc)
    first_sample = PingSample(
        sequence=1,
        timestamp=timestamp,
        ok=True,
        latency_ms=10.0,
        target_label="cloudflare",
        target_host="1.1.1.1",
    )
    second_sample = PingSample(
        sequence=2,
        timestamp=timestamp,
        ok=False,
        error="timeout",
        target_label="cloudflare",
        target_host="1.1.1.1",
    )
    live_stats = {}
    update_live_stats(live_stats, [first_sample])
    update_live_stats(live_stats, [second_sample])

    print_sample_group([second_sample], live_stats=live_stats, stream=stream)

    assert "ok 1  fail 1  loss 50.0%  avg 10.0 ms" in stream.getvalue()


def test_should_stop_before_next_sample_allows_initial_sample():
    assert not should_stop_before_next_sample(
        next_probe_at=100,
        stop_at=90,
        has_samples=False,
        current_monotonic=101,
    )


def test_should_stop_before_next_sample_allows_sample_at_exact_duration():
    assert not should_stop_before_next_sample(
        next_probe_at=100,
        stop_at=100,
        has_samples=True,
        current_monotonic=99,
    )


def test_should_stop_before_next_sample_stops_when_next_sample_exceeds_duration():
    assert should_stop_before_next_sample(
        next_probe_at=102,
        stop_at=100,
        has_samples=True,
        current_monotonic=99,
    )


def test_should_stop_before_next_sample_stops_after_duration_elapsed():
    assert should_stop_before_next_sample(
        next_probe_at=99,
        stop_at=100,
        has_samples=True,
        current_monotonic=101,
    )
