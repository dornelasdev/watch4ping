from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import Iterable

from .exporters import write_reports
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
        "-t",
        "--target",
        default="1.1.1.1",
        help="Host or IP address to ping. Defaults to 1.1.1.1.",
    )
    parser.add_argument(
        "-i",
        "--interval",
        type=float,
        default=2.0,
        help="Seconds between ping attempts. Defaults to 2.",
    )
    parser.add_argument(
        "-w",
        "--timeout",
        type=float,
        default=1.0,
        help="Seconds to wait for one ping response. Defaults to 1.",
    )
    parser.add_argument(
        "--fail-threshold",
        type=int,
        default=3,
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
        "--format",
        dest="formats",
        action="append",
        choices=("json", "csv", "md", "html", "all"),
        help="Report format to write without prompting. May be repeated.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Only print start and final report information.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.interval <= 0:
        parser.error("--interval must be greater than 0")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than 0")
    if args.fail_threshold <= 0:
        parser.error("--fail-threshold must be greater than 0")

    config = MonitorConfig(
        target=args.target,
        interval_seconds=args.interval,
        timeout_seconds=args.timeout,
        fail_threshold=args.fail_threshold,
        duration_seconds=args.duration,
    )
    formats = normalize_formats(args.formats)

    print(build_start_message(config))

    session = run_monitor(
        config=config,
        probe=SystemPingProbe(timeout_seconds=config.timeout_seconds),
        quiet=args.quiet,
    )
    report = build_report(session)

    print()
    print(format_console_summary(report))

    if args.formats:
        written = write_reports(report, args.output_dir, formats)
        print_written_reports(written)
        return 0

    if prompt_yes_no("Write a report? [y/n]: "):
        selected_formats = prompt_report_formats()
        written = write_reports(report, args.output_dir, selected_formats)
        print_written_reports(written)
    else:
        print()
        print("No report written.")

    return 0


def print_written_reports(paths: Iterable[Path]) -> None:
    print()
    for path in paths:
        print(f"Wrote {path}")


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
        f"Monitoring {config.target} every {config.interval_seconds:g}s "
        f"(timeout {config.timeout_seconds:g}s){duration}. {stop_hint}"
    )


def format_duration_argument(duration_seconds: float) -> str:
    if duration_seconds % 3600 == 0:
        return f"{duration_seconds / 3600:g}h"
    if duration_seconds % 60 == 0:
        return f"{duration_seconds / 60:g}m"
    return f"{duration_seconds:g}s"
