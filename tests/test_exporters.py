import json
from datetime import datetime, timedelta, timezone

from watch4ping.exporters import slugify_profile_name, write_reports
from watch4ping.models import MonitorSession, PingSample, Target
from watch4ping.report import build_report


def test_write_reports_creates_report_index(tmp_path):
    start = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
    report = build_sample_report(start)

    written = write_reports(report, tmp_path, ("json", "html"))

    index_path = tmp_path / "index.json"
    index_data = json.loads(index_path.read_text(encoding="utf-8"))
    session_entry = index_data["sessions"][0]

    assert written == [
        tmp_path / "watch4ping-20260718-120000.json",
        tmp_path / "watch4ping-20260718-120000.html",
    ]
    assert index_data["schema_version"] == "1"
    assert session_entry["started_at"] == "2026-07-18T12:00:00+00:00"
    assert session_entry["targets"] == [
        {"label": "cloudflare", "host": "1.1.1.1"},
        {"label": "dns", "host": "google.com"},
    ]
    assert session_entry["summary"]["total_samples"] == 4
    assert session_entry["summary"]["failed_samples"] == 2
    assert session_entry["worst_target"]["target"] == {
        "label": "dns",
        "host": "google.com",
    }
    assert session_entry["reports"] == {
        "html": "watch4ping-20260718-120000.html",
        "json": "watch4ping-20260718-120000.json",
    }


def test_write_reports_appends_to_existing_report_index(tmp_path):
    first_start = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
    second_start = datetime(2026, 7, 18, 12, 5, 0, tzinfo=timezone.utc)

    write_reports(build_sample_report(first_start), tmp_path, ("json",))
    write_reports(build_sample_report(second_start), tmp_path, ("md",))

    index_data = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))

    assert [entry["started_at"] for entry in index_data["sessions"]] == [
        "2026-07-18T12:00:00+00:00",
        "2026-07-18T12:05:00+00:00",
    ]
    assert index_data["sessions"][0]["reports"] == {
        "json": "watch4ping-20260718-120000.json"
    }
    assert index_data["sessions"][1]["reports"] == {
        "md": "watch4ping-20260718-120500.md"
    }


def test_write_reports_includes_profile_name_in_filenames_and_index(tmp_path):
    start = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
    report = build_sample_report(start)

    written = write_reports(report, tmp_path, ("json",), profile_name="Home WiFi")

    index_data = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))

    assert written == [tmp_path / "watch4ping-home-wifi-20260718-120000.json"]
    assert index_data["sessions"][0]["profile"] == "Home WiFi"
    assert index_data["sessions"][0]["reports"] == {
        "json": "watch4ping-home-wifi-20260718-120000.json"
    }


def test_slugify_profile_name_makes_filename_safe_slugs():
    assert slugify_profile_name("Home WiFi") == "home-wifi"
    assert slugify_profile_name("  office/main  ") == "office-main"
    assert slugify_profile_name("!!!") is None
    assert slugify_profile_name(None) is None


def build_sample_report(start: datetime):
    samples = (
        PingSample(
            1,
            start,
            True,
            12.0,
            target_label="cloudflare",
            target_host="1.1.1.1",
        ),
        PingSample(
            1,
            start + timedelta(milliseconds=20),
            False,
            error="timeout",
            target_label="dns",
            target_host="google.com",
        ),
        PingSample(
            2,
            start + timedelta(seconds=2),
            True,
            13.0,
            target_label="cloudflare",
            target_host="1.1.1.1",
        ),
        PingSample(
            2,
            start + timedelta(seconds=2, milliseconds=20),
            False,
            error="timeout",
            target_label="dns",
            target_host="google.com",
        ),
    )
    session = MonitorSession(
        targets=(
            Target(label="cloudflare", host="1.1.1.1"),
            Target(label="dns", host="google.com"),
        ),
        interval_seconds=2,
        timeout_seconds=1,
        fail_threshold=2,
        started_at=start,
        ended_at=start + timedelta(seconds=4),
        samples=samples,
    )
    return build_report(session)
