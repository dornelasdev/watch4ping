from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from .models import MonitorSession, PingResult, PingSample


class PingProbe(Protocol):
    def ping(self, target: str) -> PingResult:
        """Ping a target once and return the result."""


@dataclass(frozen=True)
class MonitorConfig:
    target: str
    interval_seconds: float = 2.0
    timeout_seconds: float = 1.0
    fail_threshold: int = 3


def run_monitor(
    config: MonitorConfig,
    probe: PingProbe,
    quiet: bool = False,
) -> MonitorSession:
    started_at = datetime.now(timezone.utc)
    samples: list[PingSample] = []
    sequence = 1
    next_probe_at = time.monotonic()

    try:
        while True:
            sleep_seconds = next_probe_at - time.monotonic()
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

            timestamp = datetime.now(timezone.utc)
            result = probe.ping(config.target)
            sample = PingSample(
                sequence=sequence,
                timestamp=timestamp,
                ok=result.ok,
                latency_ms=result.latency_ms,
                error=result.error,
            )
            samples.append(sample)

            if not quiet:
                print_sample(sample)

            sequence += 1
            next_probe_at += config.interval_seconds
    except KeyboardInterrupt:
        ended_at = datetime.now(timezone.utc)
        return MonitorSession(
            target=config.target,
            interval_seconds=config.interval_seconds,
            timeout_seconds=config.timeout_seconds,
            fail_threshold=config.fail_threshold,
            started_at=started_at,
            ended_at=ended_at,
            samples=tuple(samples),
        )


def print_sample(sample: PingSample) -> None:
    if sample.ok:
        latency = f"{sample.latency_ms:.1f} ms" if sample.latency_ms is not None else "ok"
        message = f"[{sample.sequence}] OK {latency}"
    else:
        message = f"[{sample.sequence}] FAIL {sample.error or 'no response'}"
    print(message, file=sys.stderr)

