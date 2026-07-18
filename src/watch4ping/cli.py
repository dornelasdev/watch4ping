from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import Iterable

from .config import DEFAULT_CONFIG_PATH, ProfileConfig, load_config
from .exporters import read_report_index, write_reports
from .models import Target
from .monitor import MonitorConfig, run_monitor
from .ping import SystemPingProbe
from .report import build_report, format_console_summary


DURATION_RE = re.compile(r"^(?P<value>\d+(?:\.\d+)?)(?P<unit>s|m|h)?$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="watch4ping",
        description="Monitor an internet connection until Ctrl-C and write a report.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=("monitor", "history", "compare"),
        default="monitor",
        help="Command to run. Defaults to monitor.",
    )
    parser.add_argument(
        "-t",
        "--target",
        dest="targets",
        action="append",
        type=parse_target,
        help=(
            "Host or labeled target to ping, such as 1.1.1.1 or "
            "cloudflare=1.1.1.1. May be repeated. Defaults to 1.1.1.1."
        ),
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=float,
        default=None,
        help="Seconds between ping attempts. Defaults to 2.",
    )
    parser.add_argument(
        "-w",
        "--timeout",
        type=float,
        default=None,
        help="Seconds to wait for one ping response. Defaults to 1.",
    )
    parser.add_argument(
        "--fail-threshold",
        type=int,
        default=None,
        help="Consecutive failed samples required to count as an outage. Defaults to 3.",
    )
    parser.add_argument(
        "-d",
        "--duration",
        type=parse_duration_seconds,
        help="Stop automatically after a duration, such as 30s, 5m, or 1h.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("reports"),
        help="Directory where reports will be written. Defaults to reports/.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to a watch4ping TOML config file. Defaults to watch4ping.toml.",
    )
    parser.add_argument(
        "--profile",
        help="Config profile to use from the selected config file.",
    )
    parser.add_argument(
        "--list-profiles",
        action="store_true",
        help="List profiles from the selected config file and exit.",
    )
    parser.add_argument(
        "--format",
        dest="formats",
        action="append",
        choices=("json", "csv", "md", "html", "all"),
        help="Report format to write without prompting. May be repeated.",
    )
    report_prompt_group = parser.add_mutually_exclusive_group()
    report_prompt_group.add_argument(
        "-y",
        "--yes",
        action="store_true",
        help="Write reports without prompting. Uses all formats unless --format is provided.",
    )
    report_prompt_group.add_argument(
        "--no-report",
        action="store_true",
        help="Do not prompt and do not write reports.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print start and final report information.",
    )
    parser.add_argument(
        "--last",
        type=int,
        default=None,
        help="Number of recent entries to show or compare. Defaults to 10 for history and 2 for compare.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "history":
        try:
            print_history(args.output_dir, args.last)
        except ValueError as exc:
            parser.error(str(exc))
        return 0

    if args.command == "compare":
        try:
            print_compare(args.output_dir, args.last)
        except ValueError as exc:
            parser.error(str(exc))
        return 0

    try:
        loaded_config = load_config(args.config)
    except ValueError as exc:
        parser.error(str(exc))

    if args.list_profiles:
        print_profiles(loaded_config.profiles)
        return 0

    profile = None
    if args.profile:
        profile = loaded_config.profiles.get(args.profile)
        if profile is None:
            parser.error(f"profile {args.profile!r} not found in {args.config}")

    try:
        settings = resolve_monitor_settings(args, profile)
    except argparse.ArgumentTypeError as exc:
        parser.error(str(exc))

    config = MonitorConfig(
        targets=settings.targets,
        interval_seconds=settings.interval_seconds,
        timeout_seconds=settings.timeout_seconds,
        fail_threshold=settings.fail_threshold,
        duration_seconds=args.duration,
    )

    print(build_start_message(config))

    session = run_monitor(
        config=config,
        probe=SystemPingProbe(timeout_seconds=config.timeout_seconds),
        quiet=args.quiet,
    )
    report = build_report(session)

    print()
    print(format_console_summary(report))

    report_formats = resolve_report_formats(args)
    if report_formats:
        written = write_reports(report, args.output_dir, report_formats, profile_name=args.profile)
        print_written_reports(written)
        return 0

    print()
    print("No report written.")

    return 0


def print_written_reports(paths: Iterable[Path]) -> None:
    print()
    for path in paths:
        print(f"Wrote {path}")


def print_history(output_dir: Path, last: int | None) -> None:
    last = 10 if last is None else last
    if last <= 0:
        raise ValueError("--last must be greater than 0")

    index_data = read_report_index(output_dir / "index.json")
    print(format_history(index_data, last))


def print_compare(output_dir: Path, last: int | None) -> None:
    last = 2 if last is None else last
    if last < 2:
        raise ValueError("--last must be at least 2 for compare")

    index_data = read_report_index(output_dir / "index.json")
    print(format_compare(index_data, last))


def format_history(index_data: dict, last: int = 10) -> str:
    sessions = index_data.get("sessions", [])
    if not sessions:
        return "No report history found."

    recent_sessions = list(reversed(sessions[-last:]))
    lines = ["watch4ping history"]
    for index, session in enumerate(recent_sessions, start=1):
        summary = session.get("summary", {})
        profile = session.get("profile") or "manual"
        targets = format_history_targets(session.get("targets", []))
        reports = format_history_reports(session.get("reports", {}))
        lines.append(
            f"{index}. {session.get('started_at', 'unknown')} "
            f"profile={profile} uptime={summary.get('uptime_percent', 0):.2f}% "
            f"failed={summary.get('failed_samples', 0)} targets={targets} reports={reports}"
        )
    return "\n".join(lines)


def format_compare(index_data: dict, last: int = 2) -> str:
    sessions = index_data.get("sessions", [])
    if len(sessions) < 2:
        return "Need at least 2 report sessions to compare."

    selected_sessions = sessions[-last:]
    previous = selected_sessions[0]
    current = selected_sessions[-1]
    previous_summary = previous.get("summary", {})
    current_summary = current.get("summary", {})

    lines = [
        "watch4ping compare",
        f"Previous: {previous.get('started_at', 'unknown')} profile={previous.get('profile') or 'manual'}",
        f"Current:  {current.get('started_at', 'unknown')} profile={current.get('profile') or 'manual'}",
        f"Uptime: {format_percent_delta(previous_summary, current_summary, 'uptime_percent')}",
        f"Failed samples: {format_number_delta(previous_summary, current_summary, 'failed_samples')}",
        f"Avg latency: {format_latency_delta(previous_summary, current_summary)}",
        f"Worst target: {format_worst_target_change(previous, current)}",
    ]
    return "\n".join(lines)


def format_percent_delta(previous: dict, current: dict, key: str) -> str:
    previous_value = float(previous.get(key, 0.0) or 0.0)
    current_value = float(current.get(key, 0.0) or 0.0)
    return f"{previous_value:.2f}% -> {current_value:.2f}% ({format_signed(current_value - previous_value)} pp)"


def format_number_delta(previous: dict, current: dict, key: str) -> str:
    previous_value = int(previous.get(key, 0) or 0)
    current_value = int(current.get(key, 0) or 0)
    return f"{previous_value} -> {current_value} ({format_signed(current_value - previous_value)})"


def format_latency_delta(previous: dict, current: dict) -> str:
    previous_value = previous.get("avg_latency_ms")
    current_value = current.get("avg_latency_ms")
    if previous_value is None or current_value is None:
        return "n/a"
    previous_latency = float(previous_value)
    current_latency = float(current_value)
    return (
        f"{previous_latency:.1f} ms -> {current_latency:.1f} ms "
        f"({format_signed(current_latency - previous_latency)} ms)"
    )


def format_signed(value: float) -> str:
    if float(value).is_integer():
        return f"{int(value):+d}"
    return f"{value:+.2f}"


def format_worst_target_change(previous: dict, current: dict) -> str:
    previous_target = format_index_worst_target(previous.get("worst_target"))
    current_target = format_index_worst_target(current.get("worst_target"))
    return f"{previous_target} -> {current_target}"


def format_index_worst_target(worst_target: dict | None) -> str:
    if not worst_target:
        return "n/a"
    target = worst_target.get("target", {})
    label = target.get("label")
    host = target.get("host")
    if label and host and label != host:
        return f"{label}={host}"
    return str(host or label or "n/a")


def format_history_targets(targets: list[dict]) -> str:
    if not targets:
        return "n/a"
    return ", ".join(
        f"{target.get('label')}={target.get('host')}"
        if target.get("label") != target.get("host")
        else str(target.get("host"))
        for target in targets
    )


def format_history_reports(reports: dict) -> str:
    if not reports:
        return "n/a"
    return ", ".join(sorted(reports))


def print_profiles(profiles: dict[str, ProfileConfig]) -> None:
    if not profiles:
        print("No profiles found.")
        return

    for name in sorted(profiles):
        print(name)


def prompt_yes_no(prompt: str) -> bool:
    while True:
        try:
            answer = input(prompt).strip().lower()
        except EOFError:
            print()
            return False

        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please answer y or n.")


def prompt_report_formats() -> tuple[str, ...]:
    valid_formats = {"json", "csv", "md", "html"}

    while True:
        try:
            answer = input("Format [json/csv/md/html/all]: ").strip().lower()
        except EOFError:
            print()
            return ("json",)

        if answer == "all":
            return ("json", "csv", "md", "html")

        selected = tuple(part.strip() for part in answer.split(",") if part.strip())
        if selected and all(part in valid_formats for part in selected):
            return selected

        print("Please enter json, csv, md, html, all, or a comma-separated list.")


def normalize_formats(formats: Iterable[str] | None) -> tuple[str, ...]:
    if not formats or "all" in formats:
        return ("json", "csv", "md", "html")
    return tuple(formats)


def resolve_report_formats(args) -> tuple[str, ...] | None:
    if args.no_report:
        return None
    if args.formats or args.yes:
        return normalize_formats(args.formats)
    if prompt_yes_no("Write a report? [y/n]: "):
        return prompt_report_formats()
    return None


def resolve_monitor_settings(args, profile: ProfileConfig | None) -> MonitorConfig:
    targets = normalize_targets(
        args.targets if args.targets is not None else (profile.targets if profile else None)
    )
    interval_seconds = args.interval
    if interval_seconds is None:
        interval_seconds = profile.interval_seconds if profile else None
    if interval_seconds is None:
        interval_seconds = 2.0

    timeout_seconds = args.timeout
    if timeout_seconds is None:
        timeout_seconds = profile.timeout_seconds if profile else None
    if timeout_seconds is None:
        timeout_seconds = 1.0

    fail_threshold = args.fail_threshold
    if fail_threshold is None:
        fail_threshold = profile.fail_threshold if profile else None
    if fail_threshold is None:
        fail_threshold = 3

    if interval_seconds <= 0:
        raise argparse.ArgumentTypeError("--interval must be greater than 0")
    if timeout_seconds <= 0:
        raise argparse.ArgumentTypeError("--timeout must be greater than 0")
    if fail_threshold <= 0:
        raise argparse.ArgumentTypeError("--fail-threshold must be greater than 0")

    return MonitorConfig(
        targets=targets,
        interval_seconds=interval_seconds,
        timeout_seconds=timeout_seconds,
        fail_threshold=fail_threshold,
        duration_seconds=args.duration,
    )


def parse_target(value: str) -> Target:
    raw_value = value.strip()
    if not raw_value:
        raise argparse.ArgumentTypeError("target cannot be empty")

    if "=" in raw_value:
        label, host = (part.strip() for part in raw_value.split("=", 1))
        if not label or not host:
            raise argparse.ArgumentTypeError("labeled target must look like label=host")
        return Target(label=label, host=host)

    return Target(label=raw_value, host=raw_value)


def normalize_targets(targets: Iterable[Target] | None) -> tuple[Target, ...]:
    normalized = tuple(targets or (Target(label="1.1.1.1", host="1.1.1.1"),))
    labels = [target.label for target in normalized]
    duplicate_labels = {label for label in labels if labels.count(label) > 1}
    if duplicate_labels:
        duplicates = ", ".join(sorted(duplicate_labels))
        raise argparse.ArgumentTypeError(f"target labels must be unique: {duplicates}")
    return normalized


def parse_duration_seconds(value: str) -> float:
    match = DURATION_RE.match(value.strip().lower())
    if not match:
        raise argparse.ArgumentTypeError("duration must look like 30s, 5m, 1h, or 60")

    amount = float(match.group("value"))
    if amount <= 0:
        raise argparse.ArgumentTypeError("duration must be greater than 0")

    unit = match.group("unit") or "s"
    multipliers = {"s": 1, "m": 60, "h": 3600}
    return amount * multipliers[unit]


def build_start_message(config: MonitorConfig) -> str:
    duration = (
        f" for {format_duration_argument(config.duration_seconds)}"
        if config.duration_seconds is not None
        else ""
    )
    stop_hint = "Press Ctrl-C to stop early." if config.duration_seconds else "Press Ctrl-C to stop."
    return (
        f"Monitoring {format_targets_summary(config.targets)} every {config.interval_seconds:g}s "
        f"(timeout {config.timeout_seconds:g}s){duration}. {stop_hint}"
    )


def format_targets_summary(targets: tuple[Target, ...]) -> str:
    if len(targets) == 1:
        return targets[0].host
    return f"{len(targets)} targets ({format_target_list(targets)})"


def format_target_list(targets: tuple[Target, ...]) -> str:
    return ", ".join(
        f"{target.label}={target.host}" if target.label != target.host else target.host
        for target in targets
    )


def format_duration_argument(duration_seconds: float) -> str:
    if duration_seconds % 3600 == 0:
        return f"{duration_seconds / 3600:g}h"
    if duration_seconds % 60 == 0:
        return f"{duration_seconds / 60:g}m"
    return f"{duration_seconds:g}s"
