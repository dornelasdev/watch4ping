import json

from watch4ping.doctor import (
    DiagnosticCheck,
    check_config,
    check_output_directory,
    check_platform,
    check_python_version,
    check_report_index,
    doctor_has_failures,
    format_doctor,
    run_doctor,
)


def test_run_doctor_reports_healthy_environment(tmp_path, monkeypatch):
    config_path = tmp_path / "watch4ping.toml"
    config_path.write_text(
        '[profile.home]\ntargets = ["cloudflare=1.1.1.1"]\n',
        encoding="utf-8",
    )
    output_dir = tmp_path / "reports"
    output_dir.mkdir()
    monkeypatch.setattr("watch4ping.doctor.platform.system", lambda: "Darwin")
    monkeypatch.setattr("watch4ping.doctor.shutil.which", lambda _command: "/sbin/ping")

    checks = run_doctor(config_path, output_dir, "home")

    assert [check.status for check in checks] == ["OK"] * 6
    assert doctor_has_failures(checks) is False
    assert list(output_dir.iterdir()) == []


def test_check_python_version_rejects_unsupported_version():
    class PythonVersion(tuple):
        major = 3
        minor = 9
        micro = 18

    check = check_python_version(PythonVersion((3, 9, 18)))

    assert check == DiagnosticCheck("FAIL", "Python", "3.9.18; requires Python 3.10+")


def test_check_platform_rejects_unknown_system():
    assert check_platform("Plan9") == DiagnosticCheck(
        "FAIL", "Platform", "Plan9 is not supported"
    )


def test_check_config_warns_when_optional_config_is_missing(tmp_path):
    check = check_config(tmp_path / "missing.toml", None)

    assert check.status == "WARN"
    assert "using defaults" in check.message


def test_check_config_fails_when_requested_profile_is_missing(tmp_path):
    config_path = tmp_path / "watch4ping.toml"
    config_path.write_text("", encoding="utf-8")

    check = check_config(config_path, "home")

    assert check.status == "FAIL"
    assert "profile 'home' not found" in check.message


def test_check_output_directory_rejects_file_path(tmp_path):
    output_path = tmp_path / "reports"
    output_path.write_text("not a directory", encoding="utf-8")

    check = check_output_directory(output_path)

    assert check == DiagnosticCheck(
        "FAIL", "Output", f"{output_path} is not a directory"
    )


def test_check_report_index_reports_invalid_index(tmp_path):
    index_path = tmp_path / "index.json"
    index_path.write_text('{"sessions": [', encoding="utf-8")

    check = check_report_index(tmp_path)

    assert check.status == "FAIL"
    assert "malformed JSON" in check.message


def test_check_report_index_counts_valid_sessions(tmp_path):
    index_path = tmp_path / "index.json"
    index_path.write_text(
        json.dumps({"schema_version": "2", "sessions": [{"summary": {}}]}),
        encoding="utf-8",
    )

    check = check_report_index(tmp_path)

    assert check.status == "OK"
    assert check.message.endswith("1 session")


def test_format_doctor_prints_status_rows_and_summary():
    checks = (
        DiagnosticCheck("OK", "Python", "3.14.0"),
        DiagnosticCheck("WARN", "Config", "not found; using defaults"),
        DiagnosticCheck("FAIL", "Ping", "not found on PATH"),
    )

    output = format_doctor(checks)

    assert output.splitlines() == [
        "watch4ping doctor",
        "OK    Python    3.14.0",
        "WARN  Config    not found; using defaults",
        "FAIL  Ping      not found on PATH",
        "Summary: 1 OK, 1 WARN, 1 FAIL",
    ]
    assert doctor_has_failures(checks) is True
