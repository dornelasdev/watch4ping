# Report Schemas

watch4ping stores monitoring data in individual report files and keeps a compact
history in `reports/index.json`. Schema versions are strings so consumers should
compare them as identifiers, not numeric values.

## JSON Report Schema 5

JSON reports are the canonical machine-readable session export. Their top-level
fields are:

| Field | Purpose |
| --- | --- |
| `schema_version` | Report schema identifier; currently `"5"` |
| `metadata` | Selected profile name and config path |
| `alert_thresholds` | Configured packet-loss and average-latency limits |
| `alerts` | Threshold violations recorded for individual targets |
| `session` | Targets, timing settings, UTC timestamps, and raw ping samples |
| `summary` | Aggregate availability and latency metrics |
| `outages` | Session-wide detected outage periods |
| `latency_spikes` | Session-wide latency spike samples |
| `target_reports` | Per-target summaries, outages, and spikes |
| `diagnoses` | High-level multi-target connection diagnosis results |

Machine timestamps use ISO 8601 and include their UTC offset. The additional
`formatted_timestamp` sample field is intended for display. UTC values are not
altered by local daylight-saving transitions.

Consumers should preserve unknown fields and reject unsupported
`schema_version` values rather than assuming their meaning. Markdown and HTML
reports are presentation formats and should not be parsed as stable schemas.

## CSV Export

CSV is a flat raw-sample export without a schema marker. Its columns are:

```text
sequence,target_label,target_host,timestamp,formatted_timestamp,ok,latency_ms,error
```

Use JSON when aggregate metrics, diagnoses, thresholds, or schema-aware
processing are required.

## Report Index Schema 2

`reports/index.json` contains `schema_version`, `updated_at`, and a `sessions`
array. Each session stores enough information for history, comparison, cleanup,
and dashboard views without reopening every report.

The reader accepts indexes with no schema version, schema `"1"`, or schema
`"2"`. Older entries that do not contain an alert count are treated as having
zero alerts. The next index write records schema `"2"`. Unknown schema versions,
malformed JSON, and invalid session structures are rejected with a clear error.

Report paths in the index are relative to the selected output directory. The
dashboard serves only indexed HTML files that remain inside that directory and
still exist; missing files return `404`.
