import subprocess

import pytest

from watch4ping.ping import (
    PingCommandError,
    SystemPingProbe,
    parse_latency_ms,
    summarize_ping_error,
)


def test_parse_latency_ms_from_common_ping_output():
    output = "64 bytes from 1.1.1.1: icmp_seq=0 ttl=57 time=12.345 ms"

    assert parse_latency_ms(output) == 12.345


def test_parse_latency_ms_from_less_than_one_ms_output():
    output = "64 bytes from 192.168.1.1: icmp_seq=1 ttl=64 time<1 ms"

    assert parse_latency_ms(output) == 1.0


def test_summarize_ping_error_uses_last_non_empty_line():
    output = "\nPING example.invalid\nping: cannot resolve example.invalid: Unknown host\n"

    assert summarize_ping_error(output) == "ping: cannot resolve example.invalid: Unknown host"


def test_system_ping_probe_fails_when_ping_command_is_unavailable(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise FileNotFoundError("ping")

    monkeypatch.setattr(subprocess, "run", unavailable)

    with pytest.raises(PingCommandError, match="system ping command is unavailable"):
        SystemPingProbe().ping("1.1.1.1")
