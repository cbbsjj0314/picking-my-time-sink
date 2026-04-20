# Steam CCU Observability

This document fixes the current Steam CCU observability rules as implemented today. It documents current behavior only and does not change runtime behavior.

## Execution Meta Contract

Current emitted execution-meta fields:

| Field | Current meaning |
| --- | --- |
| `job_name` | Runner name for the current job. |
| `started_at_utc` | UTC ISO timestamp captured at run start. |
| `finished_at_utc` | UTC ISO timestamp captured at run end. |
| `duration_ms` | Whole-run wall-clock duration in milliseconds. |
| `success` | Runner-reported success flag. |
| `http_status` | Runner-reported final HTTP status or `null`. |
| `retry_count` | Extra attempts beyond the initial attempt. |
| `timeout_count` | Count of attempts whose error text indicates `timeout` or `timed out`. |
| `rate_limit_count` | Count of attempts with HTTP 429. |
| `records_in` | Runner-reported input record count. |
| `records_out` | Runner-reported output record count. |
| `error_type` | Final error type when the run fails, otherwise `null`. |
| `error_message` | Final error message when the run fails, otherwise `null`. |

Current runner-specific notes:

- For `fetch_ccu_30m`, `http_status` is populated only for single-target runs. Multi-target runs leave it `null`.
- For `fetch_ccu_30m`, `success` means all output records have `missing_reason == None`.
- Execution meta timestamps stay in UTC.

## 429 / Timeout Ratio

This is a documented interpretation only for `fetch_ccu_30m`. It is not a persisted execution-meta field.

- `attempt_count = records_in + retry_count`
- `timeout_rate = timeout_count / attempt_count`
- `rate_limit_rate = rate_limit_count / attempt_count`

Display format:

- `count/attempt_count (pct)`
- Example: `1/3 (33.3%)`

Ratio is a documented formula, not an emitted field.

## Retry / Backoff Rules

Shared helper defaults:

- Retry HTTP `429`
- Retry HTTP `>=500`
- Retry `URLError`
- Retry `TimeoutError`
- Retry payload anomalies only when the caller provides `response_retry_reason`

CCU fetch override:

- Retryable statuses: `{404, 429, 500, 502, 503, 504}`
- Payload anomaly reasons:
  - `empty_body`
  - `invalid_json`
  - `missing_player_count`

Strategy:

- exponential backoff
- jitter
- retry cap

Path rule:

- Routine per-run execution meta stays local/private.
- Raw representative captures stay under ignored local data paths.
- Parser or ingest regression inputs must be minimal sanitized fixtures under `tests/fixtures/...`.
- Public docs retain durable contracts only.

## Minimal Regression Checklist

- `tests/steam/probe/test_common.py`: shared retry/backoff baseline for 429, timeout, 404 opt-in, and payload retry behavior.
- `tests/steam/ingest/test_fetch_ccu_30m.py`: CCU fetch missing semantics for final 404 and abnormal payloads.
- `tests/normalize/test_upsert_idempotent.py`: fact upsert rerun safety for repeated input.
- `tests/api/test_games_latest_ccu.py`: latest CCU API serving-view semantics and response mapping.

Local operator checks belong in `docs/local/` runbooks. At the contract level, CCU execution meta should continue to include `duration_ms`, `success`, `http_status`, `retry_count`, `timeout_count`, and `rate_limit_count`.

Notes:

- Ratio is a documented formula, not an emitted field.
- Latest CCU API reads serving-view semantics, not raw fact directly.

## Prometheus Exporter Baseline

The current local observability baseline adds a small Python `/metrics` exporter.
It reads scheduler result evidence and Postgres freshness directly; it does not
move the Steam scheduler, ingest runtime, API, or Postgres into Docker.

Current durable metric semantics live in `docs/metrics-definitions.md`:

- latest scheduler run presence, status, finish timestamp, duration, and partial-success flag
- latest `ccu-30m` missing evidence count
- latest `daily` reviews skipped count
- Postgres dataset latest timestamp and freshness age
- optional App Catalog latest summary existence and status

Prometheus and Grafana are local observability consumers for these metrics. Host
paths, ports, dashboard URLs, Compose commands, and DB credentials remain
local/private operator details under `docs/local/`.
