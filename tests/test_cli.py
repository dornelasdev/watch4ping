from datetime import datetime, timedelta, timezone

import pytest

from watch4ping import __version__
from watch4ping.cli import (
    EXIT_RUNTIME_ERROR,
    EXIT_USAGE,
    build_parser,
    build_start_message,
    format_cleanup_result,
    format_compare,
    format_history,
    main,
    normalize_formats,
    normalize_targets,
    parse_duration_seconds,
    parse_target,
    resolve_monitor_settings,
    resolve_report_formats,
    validate_config,
)
from watch4ping.config import ProfileConfig
from watch4ping.models import MonitorSession, PingSample, Target
from watch4ping.monitor import MonitorConfig
from watch4ping.ping import PingCommandError


def test_parser_prints_package_version(capsys):
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(["--version"])

    assert exc_info.value.code == 0
    assert capsys.readouterr().out == f"watch4ping {__version__}\n"


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
            "--alert-loss",
            "5",
            "--alert-latency",
            "150",
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
    assert args.alert_loss == 5
    assert args.alert_latency == 150


def test_parser_accepts_fail_on_alert():
    args = build_parser().parse_args(["--alert-loss", "5", "--fail-on-alert"])

    assert args.fail_on_alert is True


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--alert-loss", "0"),
        ("--alert-loss", "101"),
        ("--alert-loss", "nan"),
        ("--alert-latency", "0"),
        ("--alert-latency", "inf"),
    ],
)
def test_parser_rejects_invalid_alert_thresholds(flag, value):
    with pytest.raises(SystemExit):
        build_parser().parse_args([flag, value])


def test_main_rejects_fail_on_alert_without_threshold():
    with pytest.raises(SystemExit) as exc_info:
        main(["--fail-on-alert"])

    assert exc_info.value.code == EXIT_USAGE


@pytest.mark.parametrize(("threshold", "expected_exit_code"), [("1", 1), ("100", 0)])
def test_main_writes_report_before_returning_alert_status(
    monkeypatch,
    tmp_path,
    threshold,
    expected_exit_code,
):
    start = datetime(2026, 8, 11, tzinfo=timezone.utc)
    session = MonitorSession(
        targets=(Target(label="cloudflare", host="1.1.1.1"),),
        interval_seconds=2,
        timeout_seconds=1,
        fail_threshold=3,
        started_at=start,
        ended_at=start + timedelta(seconds=2),
        samples=(PingSample(1, start, True, 20.0),),
    )
    written_reports = []

    monkeypatch.setattr("watch4ping.cli.run_monitor", lambda **_kwargs: session)
    monkeypatch.setattr(
        "watch4ping.cli.write_reports",
        lambda report, *_args: written_reports.append(report) or [],
    )

    exit_code = main(
        [
            "--duration",
            "1s",
            "--alert-latency",
            threshold,
            "--fail-on-alert",
            "--format",
            "json",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == expected_exit_code
    assert len(written_reports) == 1
    assert bool(written_reports[0].alerts) is bool(expected_exit_code)


def test_main_returns_runtime_error_when_report_cannot_be_written(
    monkeypatch, tmp_path, capsys
):
    start = datetime(2026, 8, 11, tzinfo=timezone.utc)
    session = MonitorSession(
        targets=(Target(label="cloudflare", host="1.1.1.1"),),
        interval_seconds=2,
        timeout_seconds=1,
        fail_threshold=3,
        started_at=start,
        ended_at=start + timedelta(seconds=2),
        samples=(PingSample(1, start, True, 20.0),),
    )
    monkeypatch.setattr("watch4ping.cli.run_monitor", lambda **_kwargs: session)

    def fail_to_write(*_args, **_kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr("watch4ping.cli.write_reports", fail_to_write)

    exit_code = main(
        [
            "--duration",
            "1s",
            "--format",
            "json",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == EXIT_RUNTIME_ERROR
    assert capsys.readouterr().err == (
        "watch4ping: error: could not write reports: permission denied\n"
    )


def test_main_returns_runtime_error_when_ping_command_is_unavailable(
    monkeypatch, capsys
):
    def unavailable(**_kwargs):
        raise PingCommandError("system ping command is unavailable")

    monkeypatch.setattr("watch4ping.cli.run_monitor", unavailable)

    exit_code = main(["--duration", "1s", "--no-report"])

    assert exit_code == EXIT_RUNTIME_ERROR
    assert capsys.readouterr().err == (
        "watch4ping: error: system ping command is unavailable\n"
    )


def test_main_uses_profile_alert_threshold_for_exit_status(monkeypatch, tmp_path):
    config_path = tmp_path / "watch4ping.toml"
    config_path.write_text(
        """
[profile.home]
targets = ["cloudflare=1.1.1.1"]
alert_latency = 1
""",
        encoding="utf-8",
    )
    start = datetime(2026, 8, 11, tzinfo=timezone.utc)
    session = MonitorSession(
        targets=(Target(label="cloudflare", host="1.1.1.1"),),
        interval_seconds=2,
        timeout_seconds=1,
        fail_threshold=3,
        started_at=start,
        ended_at=start + timedelta(seconds=2),
        samples=(PingSample(1, start, True, 20.0),),
    )
    written_reports = []
    monkeypatch.setattr("watch4ping.cli.run_monitor", lambda **_kwargs: session)
    monkeypatch.setattr(
        "watch4ping.cli.write_reports",
        lambda report, *_args: written_reports.append(report) or [],
    )

    exit_code = main(
        [
            "--config",
            str(config_path),
            "--profile",
            "home",
            "--duration",
            "1s",
            "--fail-on-alert",
            "--format",
            "json",
        ]
    )

    assert exit_code == 1
    assert written_reports[0].alert_thresholds.avg_latency_ms == 1


def test_parser_accepts_profile_flags():
    args = build_parser().parse_args(
        ["--config", "custom.toml", "--profile", "home", "--list-profiles"]
    )

    assert str(args.config) == "custom.toml"
    assert args.profile == "home"
    assert args.list_profiles is True


def test_parser_accepts_history_command():
    args = build_parser().parse_args(
        ["history", "--output-dir", "custom-reports", "--last", "3", "--profile", "home"]
    )

    assert args.command == "history"
    assert str(args.output_dir) == "custom-reports"
    assert args.last == 3
    assert args.profile == "home"


def test_parser_accepts_compare_command():
    args = build_parser().parse_args(["compare", "--output-dir", "custom-reports", "--last", "2"])

    assert args.command == "compare"
    assert str(args.output_dir) == "custom-reports"
    assert args.last == 2


def test_parser_accepts_config_validate_command():
    args = build_parser().parse_args(["config", "validate", "--config", "custom.toml"])

    assert args.command == "config"
    assert args.config_action == "validate"
    assert str(args.config) == "custom.toml"


def test_parser_accepts_cleanup_command():
    args = build_parser().parse_args(
        ["cleanup", "--output-dir", "custom-reports", "--keep", "3", "--dry-run"]
    )

    assert args.command == "cleanup"
    assert str(args.output_dir) == "custom-reports"
    assert args.keep == 3
    assert args.dry_run is True


def test_parser_accepts_dashboard_command():
    args = build_parser().parse_args(
        ["dashboard", "--output-dir", "custom-reports", "--port", "9000", "--open"]
    )

    assert args.command == "dashboard"
    assert str(args.output_dir) == "custom-reports"
    assert args.port == 9000
    assert args.open is True


@pytest.mark.parametrize("port", ["0", "65536", "abc"])
def test_parser_rejects_invalid_dashboard_port(port):
    with pytest.raises(SystemExit):
        build_parser().parse_args(["dashboard", "--port", port])


def test_main_starts_dashboard_without_loading_monitor_config(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        "watch4ping.cli.serve_dashboard",
        lambda output_dir, port, open_browser=False: calls.append(
            (output_dir, port, open_browser)
        ),
    )

    exit_code = main(
        ["dashboard", "--output-dir", str(tmp_path), "--port", "9000", "--open"]
    )

    assert exit_code == 0
    assert calls == [(tmp_path, 9000, True)]


def test_main_returns_runtime_error_when_dashboard_cannot_start(
    monkeypatch, tmp_path, capsys
):
    def fail_to_start(*_args, **_kwargs):
        raise OSError("address already in use")

    monkeypatch.setattr("watch4ping.cli.serve_dashboard", fail_to_start)

    exit_code = main(["dashboard", "--output-dir", str(tmp_path)])

    assert exit_code == EXIT_RUNTIME_ERROR
    assert capsys.readouterr().err == (
        "watch4ping: error: could not start dashboard: address already in use\n"
    )


def test_parser_leaves_last_unset_by_default():
    args = build_parser().parse_args(["compare"])

    assert args.last is None


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
        alert_loss_percent=5,
        alert_latency_ms=150,
    )

    config = resolve_monitor_settings(args, profile)

    assert config.targets == (Target(label="router", host="192.168.1.1"),)
    assert config.interval_seconds == 5
    assert config.timeout_seconds == 2
    assert config.fail_threshold == 4
    assert config.alert_loss_percent == 5
    assert config.alert_latency_ms == 150


def test_resolve_monitor_settings_prefers_cli_values_over_profile_values():
    args = build_parser().parse_args(
        [
            "-t",
            "cloudflare=1.1.1.1",
            "-i",
            "1",
            "-w",
            "1",
            "--fail-threshold",
            "2",
            "--alert-loss",
            "10",
            "--alert-latency",
            "100",
        ]
    )
    profile = ProfileConfig(
        name="home",
        targets=(Target(label="router", host="192.168.1.1"),),
        interval_seconds=5,
        timeout_seconds=2,
        fail_threshold=4,
        alert_loss_percent=5,
        alert_latency_ms=150,
    )

    config = resolve_monitor_settings(args, profile)

    assert config.targets == (Target(label="cloudflare", host="1.1.1.1"),)
    assert config.interval_seconds == 1
    assert config.timeout_seconds == 1
    assert config.fail_threshold == 2
    assert config.alert_loss_percent == 10
    assert config.alert_latency_ms == 100


def test_validate_config_reports_missing_config(tmp_path):
    message = validate_config(tmp_path / "missing.toml")

    assert message.endswith("missing.toml not found; no profiles loaded.")


def test_validate_config_reports_empty_config(tmp_path):
    config_path = tmp_path / "watch4ping.toml"
    config_path.write_text("", encoding="utf-8")

    message = validate_config(config_path)

    assert message.endswith("watch4ping.toml (0 profiles)")


def test_validate_config_reports_profiles(tmp_path):
    config_path = tmp_path / "watch4ping.toml"
    config_path.write_text(
        """
[profile.home]
targets = ["cloudflare=1.1.1.1"]

[profile.office]
targets = ["dns=google.com"]
""",
        encoding="utf-8",
    )

    message = validate_config(config_path)

    assert message.endswith("watch4ping.toml (2 profiles: home, office)")


def test_format_cleanup_result_prints_dry_run_summary():
    result = format_cleanup_result(
        {
            "dry_run": True,
            "kept_sessions": 2,
            "removed_sessions": 1,
            "removed_files": ["reports/old.json"],
        }
    )

    assert result.splitlines() == [
        "watch4ping cleanup",
        "Kept sessions: 2",
        "Would remove sessions: 1",
        "Would remove files: 1",
        "- reports/old.json",
    ]


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


def test_format_history_prints_recent_sessions_first():
    history = format_history(
        {
            "sessions": [
                {
                    "started_at": "2026-07-18T12:00:00+00:00",
                    "profile": "home",
                    "targets": [{"label": "cloudflare", "host": "1.1.1.1"}],
                    "summary": {"uptime_percent": 100.0, "failed_samples": 0},
                    "reports": {"html": "watch4ping-home-20260718-120000.html"},
                },
                {
                    "started_at": "2026-07-18T12:05:00+00:00",
                    "profile": None,
                    "targets": [{"label": "dns", "host": "google.com"}],
                    "summary": {
                        "uptime_percent": 50.0,
                        "failed_samples": 2,
                        "alert_count": 2,
                    },
                    "reports": {"json": "watch4ping-20260718-120500.json"},
                },
            ]
        },
        last=2,
    )

    lines = history.splitlines()

    assert lines[0] == "watch4ping history"
    assert "2026-07-18T12:05:00+00:00 profile=manual" in lines[1]
    assert "uptime=50.00% failed=2 alerts=2 targets=dns=google.com reports=json" in lines[1]
    assert "2026-07-18T12:00:00+00:00 profile=home" in lines[2]


def test_format_history_handles_empty_index():
    assert format_history({"sessions": []}) == "No report history found."


def test_format_history_filters_by_profile():
    history = format_history(
        {
            "sessions": [
                build_history_session("first", "office", 100.0, 0, 10.0),
                build_history_session("second", "home", 95.0, 1, 20.0),
                build_history_session("third", "home", 90.0, 2, 30.0),
            ]
        },
        last=10,
        profile_name="home",
    )

    lines = history.splitlines()

    assert lines[0] == "watch4ping history profile=home"
    assert "third profile=home" in lines[1]
    assert "second profile=home" in lines[2]
    assert "first" not in history


def test_format_history_handles_empty_filtered_results():
    history = format_history(
        {"sessions": [build_history_session("first", "office", 100.0, 0, 10.0)]},
        profile_name="home",
    )

    assert history == "No report history found for profile=home."


def test_format_compare_prints_deltas_between_selected_sessions():
    comparison = format_compare(
        {
            "sessions": [
                build_history_session(
                    started_at="2026-07-18T12:00:00+00:00",
                    profile="home",
                    uptime_percent=90.0,
                    failed_samples=3,
                    avg_latency_ms=20.0,
                    alert_count=2,
                    worst_target={"label": "dns", "host": "google.com"},
                ),
                build_history_session(
                    started_at="2026-07-18T12:05:00+00:00",
                    profile="home",
                    uptime_percent=100.0,
                    failed_samples=0,
                    avg_latency_ms=15.5,
                    alert_count=0,
                    worst_target={"label": "cloudflare", "host": "1.1.1.1"},
                ),
            ]
        },
        last=2,
    )

    assert comparison.splitlines() == [
        "watch4ping compare",
        "Previous: 2026-07-18T12:00:00+00:00 profile=home",
        "Current:  2026-07-18T12:05:00+00:00 profile=home",
        "Uptime: 90.00% -> 100.00% (+10 pp)",
        "Failed samples: 3 -> 0 (-3)",
        "Alerts: 2 -> 0 (-2)",
        "Avg latency: 20.0 ms -> 15.5 ms (-4.50 ms)",
        "Worst target: dns=google.com -> cloudflare=1.1.1.1",
    ]


def test_format_compare_uses_last_window():
    comparison = format_compare(
        {
            "sessions": [
                build_history_session("first", None, 100.0, 0, 10.0),
                build_history_session("second", None, 95.0, 1, 20.0),
                build_history_session("third", None, 90.0, 2, 30.0),
            ]
        },
        last=2,
    )

    assert "Previous: second profile=manual" in comparison
    assert "Current:  third profile=manual" in comparison


def test_format_compare_handles_missing_latency():
    comparison = format_compare(
        {
            "sessions": [
                build_history_session("first", None, 100.0, 0, None),
                build_history_session("second", None, 100.0, 0, 10.0),
            ]
        },
        last=2,
    )

    assert "Avg latency: n/a" in comparison


def test_format_compare_requires_two_sessions():
    assert format_compare({"sessions": []}) == "Need at least 2 report sessions to compare."


def test_format_compare_filters_by_profile():
    comparison = format_compare(
        {
            "sessions": [
                build_history_session("office", "office", 100.0, 0, 5.0),
                build_history_session("home-one", "home", 90.0, 2, 30.0),
                build_history_session("home-two", "home", 95.0, 1, 20.0),
            ]
        },
        last=2,
        profile_name="home",
    )

    assert "watch4ping compare profile=home" in comparison
    assert "Previous: home-one profile=home" in comparison
    assert "Current:  home-two profile=home" in comparison
    assert "office" not in comparison


def test_format_compare_requires_two_filtered_sessions():
    comparison = format_compare(
        {
            "sessions": [
                build_history_session("office-one", "office", 100.0, 0, 5.0),
                build_history_session("home-one", "home", 90.0, 2, 30.0),
            ]
        },
        profile_name="home",
    )

    assert comparison == "Need at least 2 report sessions to compare for profile=home."


def build_history_session(
    started_at,
    profile,
    uptime_percent,
    failed_samples,
    avg_latency_ms,
    alert_count=0,
    worst_target=None,
):
    return {
        "started_at": started_at,
        "profile": profile,
        "targets": [{"label": "cloudflare", "host": "1.1.1.1"}],
        "summary": {
            "uptime_percent": uptime_percent,
            "failed_samples": failed_samples,
            "avg_latency_ms": avg_latency_ms,
            "alert_count": alert_count,
        },
        "worst_target": {"target": worst_target} if worst_target else None,
        "reports": {"json": "report.json"},
    }
