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
class Target:
    label: str
    host: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "host": self.host,
        }


@dataclass(frozen=True)
class PingSample:
    sequence: int
    timestamp: datetime
    ok: bool
    latency_ms: float | None = None
    error: str | None = None
    target_label: str | None = None
    target_host: str | None = None

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
            "target_label": self.target_label,
            "target_host": self.target_host,
        }


@dataclass(frozen=True)
class MonitorSession:
    targets: tuple[Target, ...]
    interval_seconds: float
    timeout_seconds: float
    fail_threshold: int
    started_at: datetime
    ended_at: datetime
    samples: tuple[PingSample, ...] = field(default_factory=tuple)

    @property
    def target(self) -> str:
        return self.targets[0].host

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "targets": [target.to_dict() for target in self.targets],
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
class LatencySpike:
    sequence: int
    timestamp: datetime
    formatted_timestamp: str
    latency_ms: float
    threshold_ms: float
    target_label: str | None = None
    target_host: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "timestamp": self.timestamp.isoformat(),
            "formatted_timestamp": self.formatted_timestamp,
            "latency_ms": self.latency_ms,
            "threshold_ms": self.threshold_ms,
            "target_label": self.target_label,
            "target_host": self.target_host,
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
    p50_latency_ms: float | None
    p95_latency_ms: float | None
    p99_latency_ms: float | None
    jitter_ms: float | None
    latency_spike_count: int
    latency_spike_threshold_ms: float | None

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
            "p50_latency_ms": self.p50_latency_ms,
            "p95_latency_ms": self.p95_latency_ms,
            "p99_latency_ms": self.p99_latency_ms,
            "jitter_ms": self.jitter_ms,
            "latency_spike_count": self.latency_spike_count,
            "latency_spike_threshold_ms": self.latency_spike_threshold_ms,
        }


@dataclass(frozen=True)
class TargetReport:
    target: Target
    summary: ReportSummary
    outages: tuple[Outage, ...]
    latency_spikes: tuple[LatencySpike, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target.to_dict(),
            "summary": self.summary.to_dict(),
            "outages": [outage.to_dict() for outage in self.outages],
            "latency_spikes": [spike.to_dict() for spike in self.latency_spikes],
        }


@dataclass(frozen=True)
class Diagnosis:
    code: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True)
class ReportMetadata:
    profile_name: str | None = None
    config_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_name": self.profile_name,
            "config_path": self.config_path,
        }


@dataclass(frozen=True)
class SessionReport:
    schema_version: str
    session: MonitorSession
    summary: ReportSummary
    outages: tuple[Outage, ...]
    latency_spikes: tuple[LatencySpike, ...]
    target_reports: tuple[TargetReport, ...]
    diagnoses: tuple[Diagnosis, ...]
    metadata: ReportMetadata = field(default_factory=ReportMetadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "metadata": self.metadata.to_dict(),
            "session": self.session.to_dict(),
            "summary": self.summary.to_dict(),
            "outages": [outage.to_dict() for outage in self.outages],
            "latency_spikes": [spike.to_dict() for spike in self.latency_spikes],
            "target_reports": [target_report.to_dict() for target_report in self.target_reports],
            "diagnoses": [diagnosis.to_dict() for diagnosis in self.diagnoses],
        }
