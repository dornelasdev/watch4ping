from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterable

from .models import SessionReport, TargetReport
from .report import format_html_report, format_markdown_report


REPORT_INDEX_SCHEMA_VERSION = "2"


def write_reports(
    report: SessionReport,
    output_dir: Path,
    formats: Iterable[str],
    profile_name: str | None = None,
) -> list[Path]:
    formats = tuple(formats)
    unsupported_formats = set(formats) - {"json", "csv", "md", "html"}
    if unsupported_formats:
        unsupported = sorted(unsupported_formats)[0]
        raise ValueError(f"Unsupported report format: {unsupported}")

    output_dir.mkdir(parents=True, exist_ok=True)
    index_data = read_report_index(output_dir / "index.json")
    profile_name = profile_name if profile_name is not None else report.metadata.profile_name
    base_name = find_available_report_base_name(
        output_dir,
        build_report_base_name(report, profile_name),
        index_data,
    )
    written: list[Path] = []
    written_by_format: dict[str, Path] = {}

    for report_format in formats:
        if report_format == "json":
            path = output_dir / f"{base_name}.json"
            atomic_write_text(path, json.dumps(report.to_dict(), indent=2) + "\n")
        elif report_format == "csv":
            path = output_dir / f"{base_name}.csv"
            write_csv(report, path)
        elif report_format == "md":
            path = output_dir / f"{base_name}.md"
            atomic_write_text(path, format_markdown_report(report))
        elif report_format == "html":
            path = output_dir / f"{base_name}.html"
            atomic_write_text(path, format_html_report(report))
        written.append(path)
        written_by_format[report_format] = path

    update_report_index(
        report,
        output_dir,
        written_by_format,
        profile_name,
        index_data=index_data,
    )
    return written


def cleanup_reports(output_dir: Path, keep: int, dry_run: bool = False) -> dict:
    if keep < 0:
        raise ValueError("--keep must be 0 or greater")

    index_path = output_dir / "index.json"
    index_data = read_report_index(index_path)
    sessions = index_data.get("sessions", [])
    kept_sessions = sessions[-keep:] if keep else []
    removed_sessions = sessions[: len(sessions) - len(kept_sessions)]
    removed_files = sorted(collect_report_paths(output_dir, removed_sessions))

    if not dry_run:
        for path in removed_files:
            if path.exists() and path.is_file():
                path.unlink()
        index_data["sessions"] = kept_sessions
        index_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        output_dir.mkdir(parents=True, exist_ok=True)
        atomic_write_text(index_path, json.dumps(index_data, indent=2) + "\n")

    return {
        "dry_run": dry_run,
        "kept_sessions": len(kept_sessions),
        "removed_sessions": len(removed_sessions),
        "removed_files": [str(path) for path in removed_files],
    }


def collect_report_paths(output_dir: Path, sessions: list[dict]) -> set[Path]:
    paths: set[Path] = set()
    for session in sessions:
        reports = session.get("reports", {})
        if not isinstance(reports, dict):
            continue
        for relative_path in reports.values():
            if not isinstance(relative_path, str):
                continue
            report_path = Path(relative_path)
            if report_path.is_absolute() or ".." in report_path.parts:
                continue
            paths.add(output_dir / report_path)
    return paths


def build_report_base_name(report: SessionReport, profile_name: str | None = None) -> str:
    timestamp = report.session.started_at.strftime("%Y%m%d-%H%M%S")
    profile_slug = slugify_profile_name(profile_name)
    if profile_slug:
        return f"watch4ping-{profile_slug}-{timestamp}"
    return f"watch4ping-{timestamp}"


def find_available_report_base_name(
    output_dir: Path,
    base_name: str,
    index_data: dict,
) -> str:
    occupied_names = collect_indexed_report_names(index_data)
    candidate = base_name
    suffix = 2

    while candidate in occupied_names or any(output_dir.glob(f"{candidate}.*")):
        candidate = f"{base_name}-{suffix}"
        suffix += 1
    return candidate


def collect_indexed_report_names(index_data: dict) -> set[str]:
    names: set[str] = set()
    for session in index_data.get("sessions", []):
        reports = session.get("reports", {})
        if not isinstance(reports, dict):
            continue
        for report_path in reports.values():
            if isinstance(report_path, str):
                names.add(Path(report_path).stem)
    return names


def slugify_profile_name(profile_name: str | None) -> str | None:
    if profile_name is None:
        return None

    slug = re.sub(r"[^a-z0-9]+", "-", profile_name.strip().lower()).strip("-")
    return slug or None


def write_csv(report: SessionReport, path: Path) -> None:
    csv_file = StringIO(newline="")
    writer = csv.DictWriter(
        csv_file,
        fieldnames=(
            "sequence",
            "target_label",
            "target_host",
            "timestamp",
            "formatted_timestamp",
            "ok",
            "latency_ms",
            "error",
        ),
    )
    writer.writeheader()
    for sample in report.session.samples:
        writer.writerow(
            {
                "sequence": sample.sequence,
                "target_label": sample.target_label,
                "target_host": sample.target_host,
                "timestamp": sample.timestamp.isoformat(),
                "formatted_timestamp": sample.formatted_timestamp,
                "ok": sample.ok,
                "latency_ms": sample.latency_ms,
                "error": sample.error,
            }
        )
    atomic_write_text(path, csv_file.getvalue(), newline="")


def atomic_write_text(path: Path, content: str, newline: str | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline=newline,
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    except BaseException:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def update_report_index(
    report: SessionReport,
    output_dir: Path,
    written_by_format: dict[str, Path],
    profile_name: str | None = None,
    index_data: dict | None = None,
) -> Path:
    index_path = output_dir / "index.json"
    if index_data is None:
        index_data = read_report_index(index_path)
    index_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    index_data["sessions"].append(
        build_report_index_entry(report, output_dir, written_by_format, profile_name)
    )
    atomic_write_text(index_path, json.dumps(index_data, indent=2) + "\n")
    return index_path


def read_report_index(index_path: Path) -> dict:
    if not index_path.exists():
        return {
            "schema_version": REPORT_INDEX_SCHEMA_VERSION,
            "updated_at": None,
            "sessions": [],
        }

    try:
        raw_index = index_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"Invalid report index {index_path}: file must be UTF-8 encoded"
        ) from exc

    try:
        index_data = json.loads(raw_index)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid report index {index_path}: malformed JSON at "
            f"line {exc.lineno}, column {exc.colno}"
        ) from exc

    if not isinstance(index_data, dict) or not isinstance(index_data.get("sessions"), list):
        raise ValueError(
            f"Invalid report index {index_path}: expected an object with a sessions list"
        )

    schema_version = index_data.get("schema_version")
    if schema_version not in (None, "1", REPORT_INDEX_SCHEMA_VERSION):
        raise ValueError(
            f"Invalid report index {index_path}: unsupported schema version "
            f"{schema_version!r}"
        )

    index_data["schema_version"] = REPORT_INDEX_SCHEMA_VERSION
    index_data.setdefault("updated_at", None)
    for position, session in enumerate(index_data["sessions"], start=1):
        if not isinstance(session, dict):
            raise ValueError(
                f"Invalid report index {index_path}: session {position} must be an object"
            )
        summary = session.setdefault("summary", {})
        if not isinstance(summary, dict):
            raise ValueError(
                f"Invalid report index {index_path}: session {position} summary must be an object"
            )
        summary.setdefault("alert_count", 0)
        reports = session.get("reports")
        if reports is not None and not isinstance(reports, dict):
            raise ValueError(
                f"Invalid report index {index_path}: session {position} reports must be an object"
            )
    return index_data


def build_report_index_entry(
    report: SessionReport,
    output_dir: Path,
    written_by_format: dict[str, Path],
    profile_name: str | None = None,
) -> dict:
    summary = report.summary
    profile_name = profile_name if profile_name is not None else report.metadata.profile_name
    return {
        "started_at": report.session.started_at.isoformat(),
        "ended_at": report.session.ended_at.isoformat(),
        "profile": profile_name,
        "duration_seconds": summary.duration_seconds,
        "targets": [target.to_dict() for target in report.session.targets],
        "summary": {
            "total_samples": summary.total_samples,
            "failed_samples": summary.failed_samples,
            "uptime_percent": summary.uptime_percent,
            "avg_latency_ms": summary.avg_latency_ms,
            "outage_count": summary.outage_count,
            "latency_spike_count": summary.latency_spike_count,
            "alert_count": len(report.alerts),
        },
        "worst_target": format_worst_target(find_worst_target_report(report)),
        "reports": {
            report_format: str(path.relative_to(output_dir))
            for report_format, path in sorted(written_by_format.items())
        },
    }


def find_worst_target_report(report: SessionReport) -> TargetReport | None:
    if not report.target_reports:
        return None

    return max(
        report.target_reports,
        key=lambda target_report: (
            target_report.summary.failed_samples,
            -target_report.summary.uptime_percent,
            target_report.summary.avg_latency_ms or 0.0,
        ),
    )


def format_worst_target(target_report: TargetReport | None) -> dict | None:
    if target_report is None:
        return None

    summary = target_report.summary
    return {
        "target": target_report.target.to_dict(),
        "failed_samples": summary.failed_samples,
        "uptime_percent": summary.uptime_percent,
        "avg_latency_ms": summary.avg_latency_ms,
    }
