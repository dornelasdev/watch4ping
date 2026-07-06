import pytest

from watch4ping.cli import (
    build_parser,
    build_start_message,
    normalize_formats,
    normalize_targets,
    parse_duration_seconds,
    parse_target,
)
from watch4ping.models import Target
from watch4ping.monitor import MonitorConfig


def test_parser_accepts_short_monitoring_flags():
    args = build_parser().parse_args(
        [
            "-t",
            "router=192.168.1.1",
            "-t",
            "cloudflare=1.1.1.1",
            "-i",
            "5",
            "-w",
            "2",
            "-d",
            "30s",
            "--format",
            "html",
        ]
    )

    assert args.targets == [
        Target(label="router", host="192.168.1.1"),
        Target(label="cloudflare", host="1.1.1.1"),
    ]
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


def test_parse_target_accepts_unlabeled_target():
    assert parse_target("1.1.1.1") == Target(label="1.1.1.1", host="1.1.1.1")


def test_parse_target_accepts_labeled_target():
    assert parse_target("cloudflare=1.1.1.1") == Target(label="cloudflare", host="1.1.1.1")


@pytest.mark.parametrize("value", ["", "=", "router=", "=1.1.1.1"])
def test_parse_target_rejects_invalid_targets(value):
    with pytest.raises(Exception):
        parse_target(value)


def test_normalize_targets_defaults_to_cloudflare_dns():
    assert normalize_targets(None) == (Target(label="1.1.1.1", host="1.1.1.1"),)


def test_normalize_targets_rejects_duplicate_labels():
    with pytest.raises(Exception):
        normalize_targets(
            (
                Target(label="dns", host="1.1.1.1"),
                Target(label="dns", host="8.8.8.8"),
            )
        )


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
        targets=(Target(label="cloudflare", host="1.1.1.1"),),
        interval_seconds=2,
        timeout_seconds=1,
        fail_threshold=3,
        duration_seconds=300,
    )

    message = build_start_message(config)

    assert "for 5m" in message
    assert "Press Ctrl-C to stop early." in message


def test_build_start_message_mentions_multiple_targets():
    config = MonitorConfig(
        targets=(
            Target(label="router", host="192.168.1.1"),
            Target(label="cloudflare", host="1.1.1.1"),
        ),
        interval_seconds=2,
        timeout_seconds=1,
        fail_threshold=3,
    )

    message = build_start_message(config)

    assert "2 targets (router=192.168.1.1, cloudflare=1.1.1.1)" in message
