from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Protocol, TextIO

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
    alert_loss_percent: float | None = None
    alert_latency_ms: float | None = None

    @property
    def target(self) -> str:
        return self.targets[0].host


@dataclass
class LiveTargetStats:
    successful_samples: int = 0
    failed_samples: int = 0
    latency_total_ms: float = 0.0
    latency_samples: int = 0

    @property
    def total_samples(self) -> int:
        return self.successful_samples + self.failed_samples

    @property
    def loss_percent(self) -> float:
        if not self.total_samples:
            return 0.0
        return self.failed_samples / self.total_samples * 100

    @property
    def avg_latency_ms(self) -> float | None:
        if not self.latency_samples:
            return None
        return self.latency_total_ms / self.latency_samples

    def add(self, sample: PingSample) -> None:
        if sample.ok:
            self.successful_samples += 1
            if sample.latency_ms is not None:
                self.latency_total_ms += sample.latency_ms
                self.latency_samples += 1
            return

        self.failed_samples += 1


def run_monitor(
    config: MonitorConfig,
    probe: PingProbe,
    quiet: bool = False,
) -> MonitorSession:
    started_at = datetime.now(timezone.utc)
    samples: list[PingSample] = []
    live_stats: dict[tuple[str | None, str | None], LiveTargetStats] = {}
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
                update_live_stats(live_stats, samples_for_sequence)
                print_sample_group(samples_for_sequence, live_stats=live_stats)

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


def update_live_stats(
    live_stats: dict[tuple[str | None, str | None], LiveTargetStats],
    samples: list[PingSample],
) -> None:
    for sample in samples:
        stats = live_stats.setdefault(sample_target_key(sample), LiveTargetStats())
        stats.add(sample)


def print_sample_group(
    samples: list[PingSample],
    stream: TextIO = sys.stderr,
    live_stats: Mapping[tuple[str | None, str | None], LiveTargetStats] | None = None,
) -> None:
    if not samples:
        return

    if live_stats is None:
        current_stats: dict[tuple[str | None, str | None], LiveTargetStats] = {}
        update_live_stats(current_stats, samples)
        live_stats = current_stats

    sequence = samples[0].sequence
    timestamp = samples[0].formatted_timestamp
    print(f"[{sequence}] {timestamp}", file=stream)

    target_width = max(len(format_sample_target(sample)) for sample in samples)
    result_width = max(len(format_sample_result(sample)) for sample in samples)
    for sample in samples:
        line = format_sample_line(
            sample,
            target_width,
            result_width,
            live_stats.get(sample_target_key(sample)),
        )
        print(f"  {line}", file=stream)


def format_sample_line(
    sample: PingSample,
    target_width: int | None = None,
    result_width: int | None = None,
    stats: LiveTargetStats | None = None,
) -> str:
    target = format_sample_target(sample)
    if target_width is not None:
        target = target.ljust(target_width)

    status = "OK  " if sample.ok else "FAIL"
    result = format_sample_result(sample)
    if result_width is not None:
        result = result.ljust(result_width)

    line = f"{target}  {status}  {result}"
    if stats is not None:
        line += f"  | {format_live_stats(stats)}"
    return line


def format_sample_result(sample: PingSample) -> str:
    if sample.ok:
        return f"{sample.latency_ms:.1f} ms" if sample.latency_ms is not None else "ok"
    return sample.error or "no response"


def format_live_stats(stats: LiveTargetStats) -> str:
    avg_latency = (
        f"{stats.avg_latency_ms:.1f} ms"
        if stats.avg_latency_ms is not None
        else "n/a"
    )
    return (
        f"ok {stats.successful_samples}  fail {stats.failed_samples}  "
        f"loss {stats.loss_percent:.1f}%  avg {avg_latency}"
    )


def sample_target_key(sample: PingSample) -> tuple[str | None, str | None]:
    return sample.target_label, sample.target_host


def format_sample_target(sample: PingSample) -> str:
    if sample.target_label:
        return sample.target_label
    if sample.target_host:
        return sample.target_host
    return "target"
