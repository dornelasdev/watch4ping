from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class PingResult:
    ok: bool
    latency_ms: float | None = None
    error: str | None = None


@dataclass(frozen=True)
class PingSample:
    sequence: int
    timestamp: datetime
    ok: bool
    latency_ms: float | None = None
    error: str | None = None

    @property
    def formatted_timestamp(self) -> str:
        return self.timestamp.strftime("%Y-%m-%d %H:%M:%S %Z")

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp.isoformat(),
            "formatted_timestamp": self.formatted_timestamp,
            "ok": self.ok,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


@dataclass(frozen=True)
class MonitorSession:
    target: str
    interval_seconds: float
    timeout_seconds: float
    fail_threshold: int
    started_at: datetime
    ended_at: datetime
    samples: tuple[PingSample, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "interval_seconds": self.interval_seconds,
            "timeout_seconds": self.timeout_seconds,
            "fail_threshold": self.fail_threshold,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "samples": [sample.to_dict() for sample in self.samples],
        }


@dataclass(frozen=True)
class Outage:
    started_at: datetime
    ended_at: datetime
    duration_seconds: float
    failed_samples: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat(),
            "duration_seconds": self.duration_seconds,
            "failed_samples": self.failed_samples,
        }


@dataclass(frozen=True)
class ReportSummary:
    duration_seconds: float
    total_samples: int
    successful_samples: int
    failed_samples: int
    uptime_percent: float
    outage_count: int
    longest_outage_seconds: float
    min_latency_ms: float | None
    avg_latency_ms: float | None
    max_latency_ms: float | None
    jitter_ms: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "duration_seconds": self.duration_seconds,
            "total_samples": self.total_samples,
            "successful_samples": self.successful_samples,
            "failed_samples": self.failed_samples,
            "uptime_percent": self.uptime_percent,
            "outage_count": self.outage_count,
            "longest_outage_seconds": self.longest_outage_seconds,
            "min_latency_ms": self.min_latency_ms,
            "avg_latency_ms": self.avg_latency_ms,
            "max_latency_ms": self.max_latency_ms,
            "jitter_ms": self.jitter_ms,
        }


@dataclass(frozen=True)
class SessionReport:
    session: MonitorSession
    summary: ReportSummary
    outages: tuple[Outage, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "session": self.session.to_dict(),
            "summary": self.summary.to_dict(),
            "outages": [outage.to_dict() for outage in self.outages],
        }
