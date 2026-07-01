# watch4ping

`watch4ping` is a small professional CLI tool for monitoring an internet connection.
It pings a target repeatedly until interrupted with `Ctrl-C`, then writes a portable
session report.

## Status

Early project scaffold. The first storage format is file-based:

- JSON: full report and raw samples
- CSV: raw samples for spreadsheets and analysis
- Markdown: human-readable summary

SQLite is intentionally left for a future history/dashboard mode.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
watch4ping -t 1.1.1.1 -i 2 -w 1
```

Stop the monitor with `Ctrl-C`. The tool prints a summary, then asks whether to
write a report and which format to use.

For non-interactive use, pass one or more report formats:

```bash
watch4ping -t 1.1.1.1 -i 2 -w 1 --format all
```

## Development

```bash
pytest
```
