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
  router      OK    2.5 ms
  cloudflare  OK    18.4 ms
  dns         OK    20.1 ms
```

Stop the monitor with `Ctrl-C`. The tool prints a summary, then asks whether to
write a report and which format to use.

For bounded monitoring, pass a duration:

```bash
watch4ping -t 1.1.1.1 -i 2 -w 1 --duration 5m
```

For non-interactive use, pass one or more report formats:

```bash
watch4ping -t 1.1.1.1 -i 2 -w 1 --duration 30s --format all
```

You can also write all report formats without prompting:

```bash
watch4ping --profile home --duration 30s --yes
```

Or skip report writing:

```bash
watch4ping --profile home --duration 30s --no-report
```

Profiles can be stored in `watch4ping.toml`. The included `home` profile checks
external IP and DNS reachability by default. Add your router/gateway IP to the
`targets` TOML array to enable local router checks.

Then run:

```bash
watch4ping --profile home --duration 30s --yes
```

List available profiles:

```bash
watch4ping --list-profiles
```

## Development

```bash
pytest
```
