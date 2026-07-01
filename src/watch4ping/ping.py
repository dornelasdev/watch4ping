from __future__ import annotations

import platform
import re
import subprocess

from .models import PingResult


TIME_RE = re.compile(r"time[=<]\s*(?P<latency>\d+(?:\.\d+)?)\s*ms", re.IGNORECASE)


class SystemPingProbe:
    def __init__(self, timeout_seconds: float = 1.0) -> None:
        self.timeout_seconds = timeout_seconds

    def ping(self, target: str) -> PingResult:
        command = build_ping_command(target, self.timeout_seconds)
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                check=False,
                text=True,
                timeout=self.timeout_seconds + 1,
            )
        except subprocess.TimeoutExpired:
            return PingResult(ok=False, error="ping command timed out")
        except OSError as exc:
            return PingResult(ok=False, error=str(exc))

        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
        latency_ms = parse_latency_ms(output)

        if completed.returncode == 0:
            return PingResult(ok=True, latency_ms=latency_ms)

        error = summarize_ping_error(output)
        return PingResult(ok=False, error=error)


def build_ping_command(target: str, timeout_seconds: float) -> list[str]:
    system = platform.system().lower()

    if system == "windows":
        timeout_ms = max(1, int(timeout_seconds * 1000))
        return ["ping", "-n", "1", "-w", str(timeout_ms), target]

    if system == "darwin":
        timeout_ms = max(1, int(timeout_seconds * 1000))
        return ["ping", "-c", "1", "-W", str(timeout_ms), target]

    timeout_whole_seconds = max(1, int(round(timeout_seconds)))
    return ["ping", "-c", "1", "-W", str(timeout_whole_seconds), target]


def parse_latency_ms(output: str) -> float | None:
    match = TIME_RE.search(output)
    if not match:
        return None
    return float(match.group("latency"))


def summarize_ping_error(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if not lines:
        return "no response"
    return lines[-1]

