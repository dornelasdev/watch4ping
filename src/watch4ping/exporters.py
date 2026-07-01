from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from .models import SessionReport
from .report import format_html_report, format_markdown_report


def write_reports(
    report: SessionReport,
    output_dir: Path,
    formats: Iterable[str],
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"watch4ping-{report.session.started_at.strftime('%Y%m%d-%H%M%S')}"
    written: list[Path] = []

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

    return written


def write_csv(report: SessionReport, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=(
                "sequence",
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
                    "timestamp": sample.timestamp.isoformat(),
                    "formatted_timestamp": sample.formatted_timestamp,
                    "ok": sample.ok,
                    "latency_ms": sample.latency_ms,
                    "error": sample.error,
                }
            )
