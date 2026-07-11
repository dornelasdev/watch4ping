from datetime import datetime, timezone
from io import StringIO

from watch4ping.models import PingResult, PingSample, Target
from watch4ping.monitor import (
    format_sample_line,
    print_sample_group,
    probe_targets,
    should_stop_before_next_sample,
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
        "  router      OK    2.5 ms\n"
        "  cloudflare  FAIL  timeout\n"
    )


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
