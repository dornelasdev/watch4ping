import pytest

from watch4ping.cli import (
    build_parser,
    build_start_message,
    normalize_formats,
    parse_duration_seconds,
)
from watch4ping.monitor import MonitorConfig


def test_parser_accepts_short_monitoring_flags():
    args = build_parser().parse_args(
        ["-t", "8.8.8.8", "-i", "5", "-w", "2", "-d", "30s", "--format", "html"]
    )

    assert args.target == "8.8.8.8"
    assert args.interval == 5
    assert args.timeout == 2
    assert args.duration == 30
    assert args.formats == ["html"]


def test_normalize_formats_defaults_to_all_formats():
    assert normalize_formats(None) == ("json", "csv", "md", "html")


def test_normalize_formats_expands_all():
    assert normalize_formats(["all"]) == ("json", "csv", "md", "html")


def test_normalize_formats_preserves_selected_formats():
    assert normalize_formats(["json", "csv"]) == ("json", "csv")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("30", 30),
        ("30s", 30),
        ("5m", 300),
        ("1h", 3600),
        ("0.5m", 30),
    ],
)
def test_parse_duration_seconds(value, expected):
    assert parse_duration_seconds(value) == expected


@pytest.mark.parametrize("value", ["", "abc", "1d", "0", "-1s"])
def test_parse_duration_seconds_rejects_invalid_values(value):
    with pytest.raises(Exception):
        parse_duration_seconds(value)


def test_build_start_message_includes_duration():
    config = MonitorConfig(
        target="1.1.1.1",
        interval_seconds=2,
        timeout_seconds=1,
        fail_threshold=3,
        duration_seconds=300,
    )

    message = build_start_message(config)

    assert "for 5m" in message
    assert "Press Ctrl-C to stop early." in message
