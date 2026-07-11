from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TextIO, Protocol

from .models import MonitorSession, PingResult, PingSample, Target


class PingProbe(Protocol):
    def ping(self, target: str) -> PingResult:
        """Ping a target once and return the result."""


@dataclass(frozen=True)
class MonitorConfig:
    targets: tuple[Target, ...]
    interval_seconds: float = 2.0
    timeout_seconds: float = 1.0
    fail_threshold: int = 3
    duration_seconds: float | None = None

    @property
    def target(self) -> str:
        return self.targets[0].host


def run_monitor(
    config: MonitorConfig,
    probe: PingProbe,
    quiet: bool = False,
) -> MonitorSession:
    started_at = datetime.now(timezone.utc)
    samples: list[PingSample] = []
    sequence = 1
    started_monotonic = time.monotonic()
    next_probe_at = started_monotonic
    stop_at = (
        started_monotonic + config.duration_seconds
        if config.duration_seconds is not None
        else None
    )

    try:
        while True:
            current_monotonic = time.monotonic()
            if should_stop_before_next_sample(
                next_probe_at=next_probe_at,
                stop_at=stop_at,
                has_samples=bool(samples),
                current_monotonic=current_monotonic,
            ):
                break

            sleep_seconds = next_probe_at - current_monotonic
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)

            samples_for_sequence = probe_targets(
                sequence=sequence,
                targets=config.targets,
                probe=probe,
            )
            samples.extend(samples_for_sequence)

            if not quiet:
                print_sample_group(samples_for_sequence)

            sequence += 1
            next_probe_at += config.interval_seconds
    except KeyboardInterrupt:
        pass

    ended_at = datetime.now(timezone.utc)
    return MonitorSession(
        targets=config.targets,
        interval_seconds=config.interval_seconds,
        timeout_seconds=config.timeout_seconds,
        fail_threshold=config.fail_threshold,
        started_at=started_at,
        ended_at=ended_at,
        samples=tuple(samples),
    )


def probe_targets(
    sequence: int,
    targets: tuple[Target, ...],
    probe: PingProbe,
) -> list[PingSample]:
    samples: list[PingSample] = []

    for target in targets:
        timestamp = datetime.now(timezone.utc)
        result = probe.ping(target.host)
        samples.append(
            PingSample(
                sequence=sequence,
                timestamp=timestamp,
                ok=result.ok,
                latency_ms=result.latency_ms,
                error=result.error,
                target_label=target.label,
                target_host=target.host,
            )
        )

    return samples


def should_stop_before_next_sample(
    next_probe_at: float,
    stop_at: float | None,
    has_samples: bool,
    current_monotonic: float,
) -> bool:
    return (
        stop_at is not None
        and has_samples
        and (next_probe_at > stop_at or current_monotonic > stop_at)
    )


def print_sample_group(samples: list[PingSample], stream: TextIO = sys.stderr) -> None:
    if not samples:
        return

    sequence = samples[0].sequence
    timestamp = samples[0].formatted_timestamp
    print(f"[{sequence}] {timestamp}", file=stream)

    target_width = max(len(format_sample_target(sample)) for sample in samples)
    for sample in samples:
        print(f"  {format_sample_line(sample, target_width)}", file=stream)


def format_sample_line(sample: PingSample, target_width: int | None = None) -> str:
    target = format_sample_target(sample)
    if target_width is not None:
        target = target.ljust(target_width)

    if sample.ok:
        latency = f"{sample.latency_ms:.1f} ms" if sample.latency_ms is not None else "ok"
        return f"{target}  OK    {latency}"

    return f"{target}  FAIL  {sample.error or 'no response'}"


def format_sample_target(sample: PingSample) -> str:
    if sample.target_label:
        return sample.target_label
    if sample.target_host:
        return sample.target_host
    return "target"
