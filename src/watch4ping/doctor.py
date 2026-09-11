from __future__ import annotations

import platform
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from .config import load_config
from .exporters import read_report_index


SUPPORTED_SYSTEMS = {"Darwin", "Linux", "Windows"}


@dataclass(frozen=True)
class DiagnosticCheck:
    status: str
    name: str
    message: str


def run_doctor(
    config_path: Path,
    output_dir: Path,
    profile_name: str | None = None,
) -> tuple[DiagnosticCheck, ...]:
    return (
        check_python_version(sys.version_info),
        check_platform(platform.system()),
        check_ping_command(shutil.which("ping")),
        check_config(config_path, profile_name),
        check_output_directory(output_dir),
        check_report_index(output_dir),
    )


def check_python_version(version_info) -> DiagnosticCheck:
    version = f"{version_info.major}.{version_info.minor}.{version_info.micro}"
    if version_info[:2] < (3, 10):
        return DiagnosticCheck("FAIL", "Python", f"{version}; requires Python 3.10+")
    return DiagnosticCheck("OK", "Python", version)


def check_platform(system: str) -> DiagnosticCheck:
    if system not in SUPPORTED_SYSTEMS:
        label = system or "unknown"
        return DiagnosticCheck("FAIL", "Platform", f"{label} is not supported")
    return DiagnosticCheck("OK", "Platform", system)


def check_ping_command(command_path: str | None) -> DiagnosticCheck:
    if command_path is None:
        return DiagnosticCheck("FAIL", "Ping", "system ping command not found on PATH")
    return DiagnosticCheck("OK", "Ping", command_path)


def check_config(config_path: Path, profile_name: str | None) -> DiagnosticCheck:
    try:
        config = load_config(config_path)
    except (OSError, ValueError) as exc:
        return DiagnosticCheck("FAIL", "Config", str(exc))

    if not config_path.exists():
        if profile_name:
            return DiagnosticCheck(
                "FAIL",
                "Config",
                f"profile {profile_name!r} unavailable; {config_path} was not found",
            )
        return DiagnosticCheck("WARN", "Config", f"{config_path} not found; using defaults")

    if profile_name and profile_name not in config.profiles:
        return DiagnosticCheck(
            "FAIL",
            "Config",
            f"profile {profile_name!r} not found in {config_path}",
        )

    profile_count = len(config.profiles)
    message = f"{config_path}; {profile_count} profile{'s' if profile_count != 1 else ''}"
    if profile_name:
        message += f"; selected {profile_name!r}"
    return DiagnosticCheck("OK", "Config", message)


def check_output_directory(output_dir: Path) -> DiagnosticCheck:
    if output_dir.exists() and not output_dir.is_dir():
        return DiagnosticCheck("FAIL", "Output", f"{output_dir} is not a directory")

    probe_directory = output_dir if output_dir.exists() else nearest_existing_parent(output_dir)
    if probe_directory is None or not probe_directory.is_dir():
        return DiagnosticCheck("FAIL", "Output", f"cannot access a parent of {output_dir}")

    try:
        with NamedTemporaryFile(
            prefix=".watch4ping-doctor-",
            dir=probe_directory,
        ):
            pass
    except OSError as exc:
        return DiagnosticCheck("FAIL", "Output", f"{output_dir} is not writable: {exc}")

    if output_dir.exists():
        message = f"{output_dir} is writable"
    else:
        message = f"{output_dir} can be created"
    return DiagnosticCheck("OK", "Output", message)


def nearest_existing_parent(path: Path) -> Path | None:
    candidate = path.parent
    while not candidate.exists():
        parent = candidate.parent
        if parent == candidate:
            return None
        candidate = parent
    return candidate


def check_report_index(output_dir: Path) -> DiagnosticCheck:
    if output_dir.exists() and not output_dir.is_dir():
        return DiagnosticCheck("WARN", "Index", "not checked; output path is not a directory")

    index_path = output_dir / "index.json"
    if not index_path.exists():
        return DiagnosticCheck("OK", "Index", f"{index_path} not present; created on first report")

    try:
        index_data = read_report_index(index_path)
    except (OSError, ValueError) as exc:
        return DiagnosticCheck("FAIL", "Index", str(exc))

    session_count = len(index_data["sessions"])
    return DiagnosticCheck(
        "OK",
        "Index",
        f"{index_path}; {session_count} session{'s' if session_count != 1 else ''}",
    )


def format_doctor(checks: tuple[DiagnosticCheck, ...]) -> str:
    lines = ["watch4ping doctor"]
    lines.extend(
        f"{check.status:<4}  {check.name:<8}  {check.message}" for check in checks
    )
    counts = {
        status: sum(check.status == status for check in checks)
        for status in ("OK", "WARN", "FAIL")
    }
    lines.append(
        f"Summary: {counts['OK']} OK, {counts['WARN']} WARN, {counts['FAIL']} FAIL"
    )
    return "\n".join(lines)


def doctor_has_failures(checks: tuple[DiagnosticCheck, ...]) -> bool:
    return any(check.status == "FAIL" for check in checks)
