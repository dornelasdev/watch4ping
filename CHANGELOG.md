# Changelog

Notable changes to watch4ping are recorded here. Package versions use semantic
versioning; repository tags use the shorter matching form, such as package
version `1.0.0` and tag `v1.0`.

## Unreleased

## 1.0.0 - 2026-09-12

### Added

- Atomic report and index writes with cleanup after failed replacements.
- Collision-safe report filenames for sessions starting in the same second.
- Cross-platform ping fixtures and macOS/Windows GitHub Actions coverage.
- `watch4ping doctor` environment diagnostics for platform, configuration,
  output access, and report-index readiness.
- A documented stable CLI, exit-code, and report compatibility contract.
- Automated release-artifact inspection and a complete manual smoke checklist.

### Changed

- Package status advanced from Beta to Production/Stable.
- End-user installation and supported-platform guidance now cover Linux, macOS,
  and Windows.

## 0.9.0 - 2026-09-01

### Added

- Central package version metadata and `watch4ping --version`.
- GitHub Actions tests for Python 3.10 through 3.14.
- Automated wheel and source-distribution validation with a clean wheel install.
- Stable CLI exit-code documentation and release maintenance notes.

### Changed

- Runtime failures now return exit code `3` with concise stderr messages.
- Argument and configuration failures remain distinct with exit code `2`.
- Report-index validation now identifies malformed JSON, unsupported schemas,
  and invalid session structures.
- Failure to launch the operating system's `ping` utility now stops monitoring
  immediately instead of appearing as connection loss.

## Earlier Milestones

- `0.8`: Added the local browser dashboard, report filtering, comparisons, and
  automatic browser opening.
- `0.7`: Added live running statistics, packet-loss and latency alerts, alert
  exit status, and alert history comparisons.
- `0.6`: Added report metadata, profile/config attribution, configuration
  validation, and stronger cleanup behavior.
- `0.5`: Added the report index, history, comparison, and retention cleanup.
- `0.4`: Added TOML profiles and non-interactive monitoring controls.
- `0.3`: Added labeled multi-target monitoring and diagnosis patterns.
- `0.2`: Added connection metrics, latency analysis, and HTML reports.
- `0.1`: Introduced continuous subprocess-based ping monitoring and portable
  session reports.
