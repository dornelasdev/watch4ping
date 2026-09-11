import subprocess

import pytest

from watch4ping.ping import (
    PingCommandError,
    SystemPingProbe,
    build_ping_command,
    parse_latency_ms,
    summarize_ping_error,
)


@pytest.mark.parametrize(
    ("system", "timeout", "expected"),
    [
        ("Windows", 1.6, ["ping", "-n", "1", "-w", "1600", "1.1.1.1"]),
        ("Darwin", 1.6, ["ping", "-c", "1", "-W", "1600", "1.1.1.1"]),
        ("Linux", 1.6, ["ping", "-c", "1", "-W", "2", "1.1.1.1"]),
    ],
)
def test_build_ping_command_uses_platform_specific_arguments(
    monkeypatch, system, timeout, expected
):
    monkeypatch.setattr("watch4ping.ping.platform.system", lambda: system)

    assert build_ping_command("1.1.1.1", timeout) == expected


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("64 bytes from 1.1.1.1: icmp_seq=0 ttl=57 time=12.345 ms", 12.345),
        ("64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 time<1 ms", 1.0),
        ("Reply from 1.1.1.1: bytes=32 time=14ms TTL=57", 14.0),
        ("Reply from 1.1.1.1: bytes=32 time<1ms TTL=57", 1.0),
    ],
)
def test_parse_latency_ms_from_platform_outputs(output, expected):
    assert parse_latency_ms(output) == expected


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        (
            "PING example.invalid\nping: cannot resolve example.invalid: Unknown host\n",
            "ping: cannot resolve example.invalid: Unknown host",
        ),
        (
            "ping: example.invalid: Name or service not known\n",
            "ping: example.invalid: Name or service not known",
        ),
        (
            "Ping request could not find host example.invalid. Please check the name.\n",
            "Ping request could not find host example.invalid. Please check the name.",
        ),
    ],
)
def test_summarize_ping_error_uses_last_non_empty_line(output, expected):
    assert summarize_ping_error(output) == expected


def test_system_ping_probe_records_network_failure(monkeypatch):
    completed = subprocess.CompletedProcess(
        args=["ping"],
        returncode=2,
        stdout="",
        stderr="ping: example.invalid: Name or service not known\n",
    )
    monkeypatch.setattr(subprocess, "run", lambda *_args, **_kwargs: completed)

    result = SystemPingProbe().ping("example.invalid")

    assert result.ok is False
    assert result.error == "ping: example.invalid: Name or service not known"


def test_system_ping_probe_records_command_timeout(monkeypatch):
    def time_out(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd=["ping"], timeout=2)

    monkeypatch.setattr(subprocess, "run", time_out)

    result = SystemPingProbe().ping("1.1.1.1")

    assert result.ok is False
    assert result.error == "ping command timed out"


def test_system_ping_probe_fails_when_ping_command_is_unavailable(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise FileNotFoundError("ping")

    monkeypatch.setattr(subprocess, "run", unavailable)

    with pytest.raises(PingCommandError, match="system ping command is unavailable"):
        SystemPingProbe().ping("1.1.1.1")


def test_system_ping_probe_fails_when_command_cannot_execute(monkeypatch):
    def denied(*_args, **_kwargs):
        raise PermissionError("permission denied")

    monkeypatch.setattr(subprocess, "run", denied)

    with pytest.raises(PingCommandError, match="could not execute.*permission denied"):
        SystemPingProbe().ping("1.1.1.1")
