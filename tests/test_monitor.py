from watch4ping.models import PingResult, Target
from watch4ping.monitor import probe_targets, should_stop_before_next_sample


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
