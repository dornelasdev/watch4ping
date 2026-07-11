import pytest

from watch4ping.cli import (
    build_parser,
    build_start_message,
    normalize_formats,
    normalize_targets,
    parse_duration_seconds,
    parse_target,
    resolve_monitor_settings,
    resolve_report_formats,
)
from watch4ping.config import ProfileConfig
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


def test_parser_accepts_profile_flags():
    args = build_parser().parse_args(
        ["--config", "custom.toml", "--profile", "home", "--list-profiles"]
    )

    assert str(args.config) == "custom.toml"
    assert args.profile == "home"
    assert args.list_profiles is True


def test_parser_accepts_prompt_control_flags():
    yes_args = build_parser().parse_args(["--yes"])
    no_report_args = build_parser().parse_args(["--no-report"])

    assert yes_args.yes is True
    assert yes_args.no_report is False
    assert no_report_args.yes is False
    assert no_report_args.no_report is True


def test_normalize_formats_defaults_to_all_formats():
    assert normalize_formats(None) == ("json", "csv", "md", "html")


def test_normalize_formats_expands_all():
    assert normalize_formats(["all"]) == ("json", "csv", "md", "html")


def test_normalize_formats_preserves_selected_formats():
    assert normalize_formats(["json", "csv"]) == ("json", "csv")


def test_resolve_report_formats_uses_explicit_formats():
    args = build_parser().parse_args(["--format", "json", "--format", "html"])

    assert resolve_report_formats(args) == ("json", "html")


def test_resolve_report_formats_yes_defaults_to_all_formats():
    args = build_parser().parse_args(["--yes"])

    assert resolve_report_formats(args) == ("json", "csv", "md", "html")


def test_resolve_report_formats_no_report_skips_reports():
    args = build_parser().parse_args(["--no-report", "--format", "all"])

    assert resolve_report_formats(args) is None


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


def test_resolve_monitor_settings_uses_profile_values():
    args = build_parser().parse_args(["--profile", "home"])
    profile = ProfileConfig(
        name="home",
        targets=(Target(label="router", host="192.168.1.1"),),
        interval_seconds=5,
        timeout_seconds=2,
        fail_threshold=4,
    )

    config = resolve_monitor_settings(args, profile)

    assert config.targets == (Target(label="router", host="192.168.1.1"),)
    assert config.interval_seconds == 5
    assert config.timeout_seconds == 2
    assert config.fail_threshold == 4


def test_resolve_monitor_settings_prefers_cli_values_over_profile_values():
    args = build_parser().parse_args(
        ["-t", "cloudflare=1.1.1.1", "-i", "1", "-w", "1", "--fail-threshold", "2"]
    )
    profile = ProfileConfig(
        name="home",
        targets=(Target(label="router", host="192.168.1.1"),),
        interval_seconds=5,
        timeout_seconds=2,
        fail_threshold=4,
    )

    config = resolve_monitor_settings(args, profile)

    assert config.targets == (Target(label="cloudflare", host="1.1.1.1"),)
    assert config.interval_seconds == 1
    assert config.timeout_seconds == 1
    assert config.fail_threshold == 2


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
