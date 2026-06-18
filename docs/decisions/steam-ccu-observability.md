# Steam CCU Observability

이 문서는 현재 구현된 Steam CCU observability rule을 고정한다. 현재 동작만 문서화하며 runtime behavior를 변경하지 않는다.

## Execution Meta Contract

현재 실행 결과에 포함되어 노출되는 `execution-meta` field:

| Field | 현재 의미 |
| --- | --- |
| `job_name` | 현재 job의 runner 이름. |
| `started_at_utc` | Run 시작 시점에 captured된 UTC ISO timestamp. |
| `finished_at_utc` | Run 종료 시점에 captured된 UTC ISO timestamp. |
| `duration_ms` | 전체 run의 wall-clock duration, millisecond 단위. |
| `success` | Runner가 보고한 success flag. |
| `http_status` | Runner가 보고한 final HTTP status 또는 `null`. |
| `retry_count` | 최초 attempt 이후의 추가 attempt 수. |
| `timeout_count` | error text가 `timeout` 또는 `timed out`을 나타내는 attempt 수. |
| `rate_limit_count` | HTTP 429가 발생한 attempt 수. |
| `records_in` | Runner가 보고한 input record count. |
| `records_out` | Runner가 보고한 output record count. |
| `error_type` | Run이 실패했을 때의 final error type, 그렇지 않으면 `null`. |
| `error_message` | Run이 실패했을 때의 final error message, 그렇지 않으면 `null`. |

현재 runner별 note:

- `fetch_ccu_30m`에서 `http_status`는 single-target run에서만 채워진다. Multi-target run에서는 `null`로 둔다.
- `fetch_ccu_30m`에서 `success`는 모든 output record가 `missing_reason == None`임을 의미한다.
- `execution-meta` timestamp는 UTC로 유지된다.

## 429 / Timeout Ratio

이는 `fetch_ccu_30m`에 대해서만 문서화된 해석이다. Persisted `execution-meta` field가 아니다.

- `attempt_count = records_in + retry_count`
- `timeout_rate = timeout_count / attempt_count`
- `rate_limit_rate = rate_limit_count / attempt_count`

Display format:

- `count/attempt_count (pct)`
- Example: `1/3 (33.3%)`

`Ratio`는 문서에 설명된 계산식/formula일 뿐이고, 실제 실행 결과에 포함되어 출력·노출되는 field는 아니다.

## Retry / Backoff 규칙

Shared helper 기본값:

- HTTP `429` retry
- HTTP `>=500` retry
- `URLError` retry
- `TimeoutError` retry
- Caller가 `response_retry_reason`을 제공한 경우에만 payload anomaly retry

CCU fetch override:

- Retryable status: `{404, 429, 500, 502, 503, 504}`
- Payload anomaly reason:
  - `empty_body`
  - `invalid_json`
  - `missing_player_count`

전략:

- exponential backoff
- jitter
- retry cap

경로 규칙:

- 각 job/run 실행마다 생기는 일반 실행 메타데이터(`execution-meta`)는 local/private에 유지한다.
- Raw representative capture는 ignored local data path 아래에 유지한다.
- Parser 또는 ingest regression input은 `tests/fixtures/...` 아래의 최소 sanitized fixture여야 한다.
- Public docs에는 durable contract만 유지한다.

## 최소 Regression Checklist

- `tests/steam/probe/test_common.py`: 429, timeout, 404 opt-in, payload retry behavior에 대한 shared retry/backoff baseline.
- `tests/steam/ingest/test_fetch_ccu_30m.py`: final 404와 abnormal payload에 대한 CCU fetch missing semantics.
- `tests/normalize/test_upsert_idempotent.py`: 반복 input에 대한 fact upsert rerun safety.
- `tests/api/test_games_latest_ccu.py`: latest CCU API serving-view semantics와 response mapping.

Local operator check는 `docs/local/` runbook에 둔다. Contract level에서 CCU execution meta는 `duration_ms`, `success`, `http_status`, `retry_count`, `timeout_count`, `rate_limit_count`를 계속 포함해야 한다.

Notes:

- `Ratio`는 문서에 설명된 formula일 뿐이고, 실제 실행 결과에 포함되어 출력·노출되는 field는 아니다.
- Latest CCU API는 raw fact를 직접 읽지 않고 serving-view semantics를 읽는다.

## Prometheus Exporter Baseline

현재 local observability baseline은 작은 Python `/metrics` exporter를 추가한다. 이는 scheduler result evidence와 Postgres freshness를 직접 읽으며, Steam scheduler, ingest runtime, API, Postgres를 Docker로 옮기지 않는다.

현재 durable metric semantics는 `docs/metrics-definitions.md`에 있다.

- latest scheduler run presence, status, finish timestamp, duration, partial-success flag
- latest `ccu-30m` missing evidence count
- latest `daily` reviews skipped count
- Postgres dataset latest timestamp와 freshness age
- optional App Catalog latest summary existence와 status

Prometheus와 Grafana는 이 metric의 local observability consumer다. Host path, port, dashboard URL, Compose command, DB credential은 `docs/local/` 아래의 local/private operator detail로 유지한다.
