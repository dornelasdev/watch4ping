from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10
    import tomli as tomllib

from .models import Target


DEFAULT_CONFIG_PATH = Path("watch4ping.toml")


@dataclass(frozen=True)
class ProfileConfig:
    name: str
    targets: tuple[Target, ...] | None = None
    interval_seconds: float | None = None
    timeout_seconds: float | None = None
    fail_threshold: int | None = None


@dataclass(frozen=True)
class Watch4PingConfig:
    profiles: dict[str, ProfileConfig]


def load_config(path: Path) -> Watch4PingConfig:
    if not path.exists():
        return Watch4PingConfig(profiles={})

    try:
        with path.open("rb") as config_file:
            data = tomllib.load(config_file)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid TOML in {path}: {exc}") from exc

    profiles_data = data.get("profile", {})
    if not isinstance(profiles_data, dict):
        raise ValueError("config field [profile] must be a table")

    profiles = {
        name: parse_profile_config(name, value)
        for name, value in profiles_data.items()
    }
    return Watch4PingConfig(profiles=profiles)


def parse_profile_config(name: str, data: Any) -> ProfileConfig:
    if not isinstance(data, dict):
        raise ValueError(f"profile {name!r} must be a table")

    targets = data.get("targets")
    interval = data.get("interval")
    timeout = data.get("timeout")
    fail_threshold = data.get("fail_threshold")

    return ProfileConfig(
        name=name,
        targets=parse_targets_config(name, targets) if targets is not None else None,
        interval_seconds=parse_positive_number(name, "interval", interval)
        if interval is not None
        else None,
        timeout_seconds=parse_positive_number(name, "timeout", timeout)
        if timeout is not None
        else None,
        fail_threshold=parse_positive_int(name, "fail_threshold", fail_threshold)
        if fail_threshold is not None
        else None,
    )


def parse_targets_config(name: str, value: Any) -> tuple[Target, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"profile {name!r} targets must be a non-empty list")

    targets = []
    for target in value:
        if not isinstance(target, str):
            raise ValueError(f"profile {name!r} targets must contain only strings")
        targets.append(parse_target_config(target))

    return tuple(targets)


def parse_target_config(value: str) -> Target:
    raw_value = value.strip()
    if not raw_value:
        raise ValueError("target cannot be empty")

    if "=" in raw_value:
        label, host = (part.strip() for part in raw_value.split("=", 1))
        if not label or not host:
            raise ValueError("labeled target must look like label=host")
        return Target(label=label, host=host)

    return Target(label=raw_value, host=raw_value)


def parse_positive_number(profile_name: str, key: str, value: Any) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"profile {profile_name!r} {key} must be greater than 0")
    return float(value)


def parse_positive_int(profile_name: str, key: str, value: Any) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"profile {profile_name!r} {key} must be a positive integer")
    return value

