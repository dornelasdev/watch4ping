from watch4ping.monitor import should_stop_before_next_sample


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
