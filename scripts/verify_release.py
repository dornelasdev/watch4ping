#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = PROJECT_ROOT / "dist"
VERSION_FILE = PROJECT_ROOT / "src" / "watch4ping" / "_version.py"


class VerificationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def read_source_version() -> str:
    match = re.search(
        r'^__version__\s*=\s*"(?P<version>[^"\s]+)"$',
        VERSION_FILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    require(match is not None, f"could not read version from {VERSION_FILE}")
    version = match.group("version")
    require(
        re.fullmatch(r"\d+\.\d+\.\d+", version) is not None,
        f"source version is not MAJOR.MINOR.PATCH: {version}",
    )
    return version


def verify_artifact_set(version: str) -> tuple[Path, Path]:
    wheel = DIST_DIR / f"watch4ping-{version}-py3-none-any.whl"
    source = DIST_DIR / f"watch4ping-{version}.tar.gz"
    expected = {wheel.name, source.name}
    actual = {path.name for path in DIST_DIR.iterdir() if path.is_file()}
    require(
        actual == expected,
        f"dist must contain only {sorted(expected)}; found {sorted(actual)}",
    )
    return wheel, source


def verify_wheel(wheel: Path, version: str) -> None:
    dist_info = f"watch4ping-{version}.dist-info"
    required_files = {
        "watch4ping/__init__.py",
        "watch4ping/__main__.py",
        "watch4ping/_version.py",
        "watch4ping/cli.py",
        "watch4ping/doctor.py",
        f"{dist_info}/METADATA",
        f"{dist_info}/entry_points.txt",
    }

    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        missing = sorted(required_files - names)
        require(not missing, f"wheel is missing files: {missing}")
        require(
            any(name.endswith(".dist-info/licenses/LICENSE") for name in names),
            "wheel is missing LICENSE",
        )

        metadata = Parser().parsestr(
            archive.read(f"{dist_info}/METADATA").decode("utf-8")
        )
        require(metadata["Name"] == "watch4ping", "wheel project name is incorrect")
        require(metadata["Version"] == version, "wheel version does not match source")
        require(metadata["Requires-Python"] == ">=3.10", "Requires-Python is incorrect")

        project_urls = metadata.get_all("Project-URL", [])
        require(
            any("github.com/dornelasdev/watch4ping" in value for value in project_urls),
            "wheel metadata is missing the repository URL",
        )

        entry_points = archive.read(f"{dist_info}/entry_points.txt").decode("utf-8")
        require(
            "watch4ping = watch4ping.cli:main" in entry_points,
            "wheel console entry point is incorrect",
        )


def verify_source_distribution(source: Path, version: str) -> None:
    prefix = f"watch4ping-{version}"
    required_files = {
        f"{prefix}/CHANGELOG.md",
        f"{prefix}/LICENSE",
        f"{prefix}/README.md",
        f"{prefix}/docs/cli-contract.md",
        f"{prefix}/docs/releasing.md",
        f"{prefix}/docs/report-schema.md",
        f"{prefix}/pyproject.toml",
        f"{prefix}/scripts/verify_release.py",
        f"{prefix}/src/watch4ping/_version.py",
        f"{prefix}/src/watch4ping/doctor.py",
        f"{prefix}/tests/test_doctor.py",
        f"{prefix}/watch4ping.toml",
    }

    with tarfile.open(source, mode="r:gz") as archive:
        names = set(archive.getnames())

    missing = sorted(required_files - names)
    require(not missing, f"source distribution is missing files: {missing}")
    require(
        not any(name.startswith(f"{prefix}/.github/") for name in names),
        "source distribution contains repository workflow files",
    )


def main() -> int:
    try:
        require(DIST_DIR.is_dir(), f"distribution directory not found: {DIST_DIR}")
        version = read_source_version()
        wheel, source = verify_artifact_set(version)
        verify_wheel(wheel, version)
        verify_source_distribution(source, version)
    except (
        OSError,
        ValueError,
        EOFError,
        tarfile.TarError,
        zipfile.BadZipFile,
        VerificationError,
    ) as exc:
        print(f"Release verification failed: {exc}", file=sys.stderr)
        return 1

    print(f"Release artifacts verified for watch4ping {version}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
