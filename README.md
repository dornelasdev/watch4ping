# watch4ping

`watch4ping` is a professional CLI tool for monitoring an internet connection.
It pings one or more targets until interrupted with `Ctrl-C` or a configured
duration ends, then analyzes the session and writes portable reports.

## Status

Version `1.0.0` is the first stable release. It provides:

- Continuous or duration-limited monitoring of one or more labeled targets
- Live packet-loss and average-latency statistics
- Outage, latency percentile, jitter, spike, diagnosis, and alert analysis
- JSON, CSV, Markdown, and self-contained HTML reports
- File-based report history, comparison, retention cleanup, and a local dashboard
- TOML profiles and stable exit codes for scripts and CI jobs

Report storage remains file-based by design: individual reports are portable,
while `reports/index.json` provides the compact session history used by CLI and
dashboard views.

## Installation

watch4ping requires Python 3.10 or newer and the operating system's `ping`
utility. Linux, macOS, and Windows are supported.

Install from a local clone into a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install .
watch4ping --version
```

On Windows PowerShell, activate the environment with:

```powershell
.venv\Scripts\Activate.ps1
```

The standard `ping` utility is normally included with each supported operating
system. Run `watch4ping doctor` after installation to verify the environment.

## Quick Start

```bash
watch4ping -t 1.1.1.1 -i 2 -w 1
```

Targets may be labeled and repeated:

```bash
watch4ping -t router=192.168.1.1 -t cloudflare=1.1.1.1 -t dns=google.com
```

Multi-target reports include per-target summaries and basic diagnosis hints for
local network, ISP/WAN, and DNS-style failure patterns.

Live output is grouped by monitoring round:

```text
[1] 2026-07-11 12:00:00 UTC
  router      OK    2.5 ms   | ok 1  fail 0  loss 0.0%  avg 2.5 ms
  cloudflare  OK    18.4 ms  | ok 1  fail 0  loss 0.0%  avg 18.4 ms
  dns         OK    20.1 ms  | ok 1  fail 0  loss 0.0%  avg 20.1 ms
```

The values after `|` are running per-target statistics for the current session.
Use `--quiet` to suppress live rounds while retaining the final summary and reports.

Stop the monitor with `Ctrl-C`. The tool prints a summary, then asks whether to
write a report and which format to use.

For bounded monitoring, pass a duration:

```bash
watch4ping -t 1.1.1.1 -i 2 -w 1 --duration 5m
```

Set per-target packet-loss and average-latency alert thresholds when you want the
report to call out unacceptable results:

```bash
watch4ping --profile home --duration 5m --alert-loss 5 --alert-latency 150
```

The values are a loss percentage and milliseconds, respectively. Alert results
are included in JSON, Markdown, and HTML reports.

For scripts, scheduled checks, and CI jobs, return exit code `1` when an alert is
triggered:

```bash
watch4ping --profile home --duration 5m --alert-loss 5 --alert-latency 150 \
  --fail-on-alert --format json
```

The CLI uses stable exit codes for automation:

| Code | Meaning |
| ---: | --- |
| `0` | Command completed successfully |
| `1` | A configured alert threshold was reached with `--fail-on-alert` |
| `2` | Invalid command arguments or configuration |
| `3` | Runtime failure, such as an unavailable port or unwritable report directory |

Report writing still completes before the command exits. A run without triggered
alerts returns `0`; invalid CLI usage returns `2`.

The commands, stream behavior, precedence rules, and compatibility guarantees
for automation are documented in the [CLI contract](docs/cli-contract.md).

For non-interactive use, pass one or more report formats:

```bash
watch4ping -t 1.1.1.1 -i 2 -w 1 --duration 30s --format all
```

You can also write all report formats without prompting:

```bash
watch4ping --profile home --duration 30s --yes
```

Profile runs include the profile name in report filenames, such as
`watch4ping-home-20260718-120000.html`.
JSON, Markdown, and HTML reports also include the selected profile and config
path as report metadata.

Or skip report writing:

```bash
watch4ping --profile home --duration 30s --no-report
```

Profiles can be stored in `watch4ping.toml`. The included `home` profile checks
external IP and DNS reachability by default. Add your router/gateway IP to the
`targets` TOML array to enable local router checks.

Profiles may also define alert defaults:

```toml
[profile.home]
alert_loss = 5
alert_latency = 150
```

These values represent packet-loss percentage and average latency in
milliseconds. `--alert-loss` and `--alert-latency` override profile values when
passed explicitly, and `--fail-on-alert` works with either source.

Then run:

```bash
watch4ping --profile home --duration 30s --yes
```

List available profiles:

```bash
watch4ping --list-profiles
```

Validate the selected TOML config:

```bash
watch4ping config validate
watch4ping config validate --config custom.toml
```

Show recent report history from `reports/index.json`:

```bash
watch4ping history
watch4ping history --last 5
watch4ping history --profile home
```

History rows include each session's alert count. Indexes created before v0.7 are
read as zero-alert sessions and upgraded to index schema v2 on the next write.

Compare recent report sessions:

```bash
watch4ping compare
watch4ping compare --last 2
watch4ping compare --profile home
```

Comparisons include the alert-count change alongside uptime, failures, latency,
and the worst target.

Start the local report dashboard:

```bash
watch4ping dashboard
```

Open it automatically in the default browser:

```bash
watch4ping dashboard --open
```

Then open `http://127.0.0.1:8765` in a browser. The dashboard reads the selected
output directory's `index.json`, displays report sessions newest first, and is
only available from the local machine. In supported terminals, `Cmd`+click the
printed URL to open it. Use `--port` or `--output-dir` when needed:

```bash
watch4ping dashboard --port 9000 --output-dir custom-reports
```

Sessions with an HTML export include a `View report` link. JSON-only sessions
remain visible in the dashboard but do not have a browser report to open.

Use the profile menu to narrow the session table. Select exactly two sessions
and choose `Compare selected` to view uptime, failure, alert, and average-latency
changes directly in the dashboard.

Clean up old report sessions:

```bash
watch4ping cleanup --dry-run --keep 20
watch4ping cleanup --keep 20
```

Check whether the local environment is ready to monitor and store reports:

```bash
watch4ping doctor
watch4ping doctor --profile home
```

The diagnostic checks Python, platform support, the system `ping` command,
configuration and profile validity, output access, and the report index. It does
not contact monitoring targets or change report history.

## Development

Install the project and development tools in an active virtual environment:

```bash
python -m pip install -e ".[dev]"
```

Run the test suite:

```bash
pytest
```

Build and validate release distributions:

```bash
python -m build
python -m twine check dist/*
python scripts/verify_release.py
```

GitHub Actions runs the tests on Python 3.10 through 3.14 on Ubuntu, adds macOS
and Windows coverage on Python 3.14, and verifies a clean wheel installation.
See the [changelog](CHANGELOG.md),
[CLI contract](docs/cli-contract.md),
[report schema notes](docs/report-schema.md), and
[release checklist](docs/releasing.md) for project maintenance details.
