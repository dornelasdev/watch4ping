# watch4ping

`watch4ping` is a small professional CLI tool for monitoring an internet connection.
It pings a target repeatedly until interrupted with `Ctrl-C`, then writes a portable
session report.

## Status

Early project scaffold. The first storage format is file-based:

- JSON: full report and raw samples
- CSV: raw samples for spreadsheets and analysis
- Markdown: human-readable summary
- HTML: self-contained visual report
- `reports/index.json`: compact history of generated report sessions

SQLite is intentionally left for a future history/dashboard mode.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
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

Report writing still completes before the command exits. A run without triggered
alerts returns `0`; invalid CLI usage returns `2`.

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

## Development

```bash
pytest
```
