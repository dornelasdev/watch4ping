from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .models import SessionReport, TargetReport
from .report import format_html_report, format_markdown_report


REPORT_INDEX_SCHEMA_VERSION = "1"


def write_reports(
    report: SessionReport,
    output_dir: Path,
    formats: Iterable[str],
    profile_name: str | None = None,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = build_report_base_name(report, profile_name)
    written: list[Path] = []
    written_by_format: dict[str, Path] = {}

    for report_format in formats:
        if report_format == "json":
            path = output_dir / f"{base_name}.json"
            path.write_text(json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8")
        elif report_format == "csv":
            path = output_dir / f"{base_name}.csv"
            write_csv(report, path)
        elif report_format == "md":
            path = output_dir / f"{base_name}.md"
            path.write_text(format_markdown_report(report), encoding="utf-8")
        elif report_format == "html":
            path = output_dir / f"{base_name}.html"
            path.write_text(format_html_report(report), encoding="utf-8")
        else:
            raise ValueError(f"Unsupported report format: {report_format}")
        written.append(path)
        written_by_format[report_format] = path

    update_report_index(report, output_dir, written_by_format, profile_name)
    return written


def build_report_base_name(report: SessionReport, profile_name: str | None = None) -> str:
    timestamp = report.session.started_at.strftime("%Y%m%d-%H%M%S")
    profile_slug = slugify_profile_name(profile_name)
    if profile_slug:
        return f"watch4ping-{profile_slug}-{timestamp}"
    return f"watch4ping-{timestamp}"


def slugify_profile_name(profile_name: str | None) -> str | None:
    if profile_name is None:
        return None

    slug = re.sub(r"[^a-z0-9]+", "-", profile_name.strip().lower()).strip("-")
    return slug or None


def write_csv(report: SessionReport, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as csv_file:
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


def update_report_index(
    report: SessionReport,
    output_dir: Path,
    written_by_format: dict[str, Path],
    profile_name: str | None = None,
) -> Path:
    index_path = output_dir / "index.json"
    index_data = read_report_index(index_path)
    index_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    index_data["sessions"].append(
        build_report_index_entry(report, output_dir, written_by_format, profile_name)
    )
    index_path.write_text(json.dumps(index_data, indent=2) + "\n", encoding="utf-8")
    return index_path


def read_report_index(index_path: Path) -> dict:
    if not index_path.exists():
        return {
            "schema_version": REPORT_INDEX_SCHEMA_VERSION,
            "updated_at": None,
            "sessions": [],
        }

    index_data = json.loads(index_path.read_text(encoding="utf-8"))
    if not isinstance(index_data, dict) or not isinstance(index_data.get("sessions"), list):
        raise ValueError(f"Invalid report index: {index_path}")
    index_data.setdefault("schema_version", REPORT_INDEX_SCHEMA_VERSION)
    index_data.setdefault("updated_at", None)
    return index_data


def build_report_index_entry(
    report: SessionReport,
    output_dir: Path,
    written_by_format: dict[str, Path],
    profile_name: str | None = None,
) -> dict:
    summary = report.summary
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
