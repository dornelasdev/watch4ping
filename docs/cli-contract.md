# CLI Contract

This document defines the stable command-line behavior introduced with
watch4ping 1.0. Compatible 1.x releases may add commands, options, output fields,
or diagnostics, but will not remove or reinterpret the behavior described here
without prior deprecation.

## Commands

Running `watch4ping` without a command is equivalent to `watch4ping monitor`.
The stable commands are:

| Command | Contract |
| --- | --- |
| `monitor` | Sample configured targets and optionally write session reports |
| `history` | List indexed report sessions without modifying them |
| `compare` | Compare two indexed report sessions without modifying them |
| `config validate` | Validate a TOML configuration without monitoring |
| `cleanup` | Remove sessions beyond the requested retention count |
| `dashboard` | Serve indexed HTML reports on the local loopback interface |
| `doctor` | Diagnose the local environment without contacting targets |

`--version` prints `watch4ping MAJOR.MINOR.PATCH` to stdout and exits successfully.
`--help` and argument-validation failures follow standard argparse behavior.

## Exit Codes

| Code | Meaning |
| ---: | --- |
| `0` | The command completed successfully, including warning-only diagnostics |
| `1` | A monitor alert was reached while `--fail-on-alert` was enabled |
| `2` | Command arguments or configuration are invalid |
| `3` | An operational dependency or requested runtime action failed |

Report writing is attempted before an alert run returns `1`. A report-writing
failure takes precedence and returns `3`.

## Output Streams

- Final summaries, history, comparisons, validation, cleanup, dashboard startup,
  diagnostics, version output, and written-report paths use stdout.
- Live monitoring rounds use stderr so stdout can be consumed separately.
- Argument errors and runtime errors use stderr.

Human-readable wording may be refined in compatible releases. Automation should
use exit codes and JSON/CSV reports instead of parsing prose output.

## Configuration Precedence

Monitoring values are resolved in this order:

1. Explicit CLI option
2. Selected TOML profile value
3. Built-in default

Repeated `--target` options replace profile targets as one CLI-provided target
set. `--format`, `--yes`, and `--no-report` provide non-interactive report
control. Invalid explicit values do not fall back silently.

## Compatibility

watch4ping follows semantic versioning for the package version:

- Patch releases fix defects without intentionally changing the public contract.
- Minor 1.x releases may add backward-compatible behavior.
- Breaking CLI or configuration changes require a new major version.

JSON reports and the report index have independent schema identifiers. Their
compatibility rules are documented in [report-schema.md](report-schema.md).
