# Category-To-Game Alias / Manual Hint Real-Data Gate

Status: implementation gate
Ticket: CATEGORY-MAPPING-ALIAS-HINT-REAL-DATA-GATE-001
Documented: 2026-05-24 (KST)

## Purpose

이 문서는 synthetic/test-only alias/manual hint dry-run support 이후 real-data
alias/manual hint 작업을 열 수 있는지에 대한 decision boundary를 고정한다.

이 gate는 real-data smoke를 실행하지 않는다. 이 gate는 code implementation,
API call, DB query, service start/stop/restart, scheduler action, live fetch, DB
write, SQL change, API/web/serving change, 또는 `Combined` semantics를 수행하거나
승인하지 않는다.

목적은 future `CATEGORY-MAPPING-ALIAS-HINT-REAL-DATA-SMOKE-001` ticket이 열린다면
read-only, no-write, sanitized aggregate smoke로만 제한되도록 source boundary,
public artifact boundary, stop condition을 먼저 고정하는 것이다.

## Prior Decision Basis

이 gate는 아래 prior decision chain을 따른다.

- `CATEGORY-MAPPING-CANDIDATE-GENERATION-DRY-RUN-001` added synthetic exact-match
  dry-run support.
- Real-data exact-match smoke produced no useful candidate signal.
- `CATEGORY-MAPPING-NON-EXACT-MATCHING-GATE-001` kept fuzzy matching and automatic
  alias discovery forbidden.
- `CATEGORY-MAPPING-ALIAS-HINT-CONTRACT-GATE-001` defined
  `hint_kind = "alias" | "manual_hint"` as a synthetic/test-only contract family.
- `CATEGORY-MAPPING-ALIAS-HINT-DRY-RUN-001` implemented synthetic/test-only
  alias/manual hint dry-run support.

Allowed aggregate evidence from the exact-match real-data smoke:

- exact-match real-data candidate proposal count: `0`
- exact-match real-data unresolved proposal count: `200`
- DB write performed: `false`
- candidate insert performed: `false`

이 aggregate evidence는 raw category name, raw game name, raw alias/hint row, raw
API response, raw SQL output, raw command transcript, private runtime material을
포함하지 않는다.

## Decision

Real-data alias/manual hint work may be opened only as a future read-only,
no-write, sanitized aggregate smoke. Real category/game names and real hint rows
remain private/local evidence and must not be added to public artifacts.

이 결정은 아래를 의미한다.

- real-data alias/manual hint work는 future smoke로만 열 수 있다.
- future smoke는 read-only, no-write, sanitized aggregate output only여야 한다.
- real category/game names, real alias names, real manual hint rows는
  private/local evidence로만 남는다.
- real alias/manual hint source는 local/private operator-controlled evidence여야 한다.
- 이 gate는 arbitrary local data access를 승인하지 않는다.
- 이 gate는 real-data alias/manual hint implementation을 승인하지 않는다.
- DB write, candidate insert, trusted mapping, API/web/serving, and `Combined`는
  계속 future Human Gate 뒤로 deferred 상태를 유지한다.
- fuzzy matching, automatic alias discovery, automatic matching은 계속 forbidden이다.

## Real-Data Source Boundary

Real alias/manual hint source는 local/private operator-controlled evidence다. 이
source는 public fixture, tracked public docs table, serving contract, 또는 automatic
discovery output이 아니다.

Future smoke가 source를 읽을 수 있는 조건은 아래로 제한한다.

- future ticket에서 explicitly approved read-only local/private source path 또는
  command를 지정해야 한다.
- 지정된 source는 real alias/manual hint evidence를 operator-controlled evidence로만
  제공해야 한다.
- 지정된 source는 public artifact에 raw value를 출력하지 않는 방식으로만 읽어야 한다.
- source shape가 ambiguous하면 smoke를 중단해야 한다.
- aggregate-only reporting을 보장할 수 없으면 smoke를 중단해야 한다.

이 gate는 아래를 승인하지 않는다.

- arbitrary local data access
- public fixture로 real alias/manual hint source 추가
- public docs table로 real alias/manual hint source 추가
- serving contract로 real alias/manual hint source 정의
- real alias/manual hint source automatic inference
- `.env` values, credentials, private paths, raw provider payloads를 public output에
  포함하는 source access
- 명시되지 않은 local/private files, artifacts, logs, outputs 접근

Future smoke는 public output을 만들기 위해 `.env` values, credentials, private
paths, raw provider payloads, raw API responses, raw SQL output, raw runtime logs를
inspect하거나 print해서는 안 된다.

## Public Artifact Boundary

Public artifacts include:

- PR body
- public docs
- tests
- fixtures/examples
- logs/reports committed to the repo
- Codex completion reports that may be copied into public PRs

Public artifacts may include only sanitized aggregate output, such as:

- input category count
- input game count
- alias/manual hint row count
- candidate proposal count
- unresolved proposal count
- ambiguous/conflict count
- no-match count
- skipped/unknown count
- latest observed timestamp, aggregate only
- DB write performed: `false`
- candidate insert performed: `false`
- raw values printed: `false`

Public artifacts must not include:

- real category names
- real game names
- real alias names
- real manual hint rows
- real channel/display values
- live titles
- thumbnails
- raw provider payloads
- raw API responses
- raw SQL output
- private paths
- credentials
- `.env` values
- scheduler XML/stdout
- raw runtime logs
- screenshots
- row-level UGC
- raw command transcript
- raw Grafana/Prometheus responses

## Allowed Future Smoke Output

Future smoke may publicly report only sanitized aggregate proposal counts.

Allowed public summary fields are limited to aggregate counters and aggregate
timestamps:

- input category count
- input game count
- alias/manual hint row count
- candidate proposal count
- unresolved proposal count
- ambiguous/conflict count
- no-match count
- skipped/unknown count
- latest observed timestamp, aggregate only
- DB write performed: `false`
- candidate insert performed: `false`
- raw values printed: `false`

Future smoke must not produce public row-level proposals containing real names.
Future smoke must not print real category/game names, real alias names, real manual
hint rows, channel/display values, live titles, thumbnails, raw provider payloads,
raw API responses, raw SQL output, private paths, credentials, `.env` values,
scheduler XML/stdout, raw runtime logs, screenshots, row-level UGC, raw command
transcript, or raw Grafana/Prometheus responses.

## Private / Local Evidence Boundary

Real alias/manual hint evidence may exist only as private/local operator evidence
before a future explicit public-safe strategy exists.

- Private/local evidence must not be copied into public docs or tests.
- Public docs may refer to private/local evidence only as a source class, not by
  value.
- If future smoke uses private/local evidence, the completion report must summarize
  aggregate counts only.
- If aggregate-only reporting cannot be guaranteed, the future smoke must stop.
- Raw/private evidence must not be promoted into public fixtures, public examples,
  public docs, PR bodies, or committed reports.

## Alias / Manual Hint Boundary

`alias` is a curated alternate label that may help propose a review candidate.

`manual_hint` is a human-provided review hint that may suggest a review candidate.

Both remain untrusted review evidence.

- Neither creates trusted mapping.
- Neither creates serving truth.
- Neither bypasses review.
- Neither directly produces `trusted` / `approved`.
- Neither creates canonical game identity.
- Neither permits DB write or candidate insert.
- Neither permits API/web/serving/`Combined` exposure.

Future real-data smoke may only test whether alias/manual hint evidence can produce
useful untrusted proposal counts.

## Proposal Output Boundary

Future smoke may publicly report only aggregate proposal counts.

Future smoke must not produce public row-level proposals containing real names.

Future smoke must not perform:

- DB write
- insert into `chzzk_category_game_candidate`
- trusted mapping
- promotion/demotion
- API/web exposure
- serving changes
- `Combined`

Why DB write and candidate insert remain forbidden:

- Real-data alias/manual hint evidence is still untrusted review evidence.
- The future smoke goal is signal detection, not storage mutation.
- Candidate storage semantics, write policy, audit trail, and review workflow remain
  Human Gate controlled.
- Writing rows would make private/local evidence look like durable candidate state
  before the source and review policy are approved.

Why trusted mapping remains forbidden:

- Alias/manual hint evidence may suggest a review candidate, but it is not canonical
  game identity.
- There is no approved promotion rule, reviewer workflow, conflict policy, or
  serving contract.
- `trusted` / `approved` remain future Human Gate terminology only.

Why API/web/serving/`Combined` remain forbidden:

- Current Chzzk API/web surfaces are category-only observed evidence.
- Candidate proposals are not serving truth.
- Exposing candidate proposals could imply Steam-Chzzk mapping, ranking, sorting,
  KPI, or relationship semantics that have not been approved.
- `Combined` remains blocked until trusted mapping and serving semantics are
  separately approved.

## Explicit Non-Goals

이 gate는 아래 항목을 승인하거나 구현하지 않는다.

- code implementation
- real-data smoke execution
- API call
- DB query
- service start/stop/restart
- scheduler action
- live fetch
- DB write
- insert into `chzzk_category_game_candidate`
- schema/DDL changes
- SQL migration
- real-data alias/manual hint implementation
- public fixture with real names
- fuzzy matching
- automatic alias discovery
- automatic matching
- trusted mapping
- promotion/demotion workflow
- `game_external_id`
- tracked_universe
- App Catalog
- API endpoint changes
- web UI changes
- serving semantics
- `Combined`
- backfill/reingest
- raw/private evidence promotion

## Required Validation For Future Smoke

Future `CATEGORY-MAPPING-ALIAS-HINT-REAL-DATA-SMOKE-001` must:

- be read-only
- be no-write
- use explicitly approved source commands/paths only
- not start/stop/restart services
- not mutate scheduler/runtime
- not inspect or print credentials/`.env` values
- not commit any public file containing real values
- report sanitized aggregate output only
- confirm DB write performed: `false`
- confirm candidate insert performed: `false`
- confirm raw values printed: `false`
- stop if source shape is ambiguous
- stop if aggregate-only reporting cannot be maintained

The future smoke validation must also confirm that no public artifact contains real
category/game/channel/display values, real alias names, real manual hint rows, live
titles, thumbnails, raw provider payloads, raw API responses, raw SQL output,
private paths, credentials, `.env` values, scheduler XML/stdout, raw runtime logs,
screenshots, row-level UGC, raw command transcript, or raw Grafana/Prometheus
responses.

## Stop Conditions For Future Smoke

Future smoke must stop if:

- source requires raw provider payload printing
- source requires real category/game names in public output
- source requires credentials or `.env` value inspection
- source requires DB write or candidate insert
- source requires API/web/serving changes
- source requires `Combined`
- source requires fuzzy matching or automatic alias discovery
- source requires automatic matching, approximate matching, similarity score,
  phonetic/transliteration matching, or partial/punctuation-insensitive matching
- source requires ambiguous private/local paths that cannot be described safely
- source produces row-level output that cannot be sanitized
- source shape is ambiguous
- aggregate-only reporting cannot be guaranteed

## Next Ticket

Recommended next ticket:

`CATEGORY-MAPPING-ALIAS-HINT-REAL-DATA-SMOKE-001`

Next ticket goal:

`Run a read-only, no-write, sanitized aggregate smoke using approved local/private real-data alias/manual hint evidence to see whether useful untrusted candidate proposal signal exists.`

The next ticket must remain:

- read-only
- no-write
- aggregate-only public output
- no real names in public artifacts
- no DB write
- no candidate insert
- no trusted mapping
- no API/web/serving/`Combined`
- fuzzy matching forbidden
- automatic alias discovery forbidden
- no real-data alias/manual hint implementation beyond the approved smoke boundary

## Deferred Items

- real-data smoke execution
- real-data alias/manual hint implementation
- public-safe real-data alias/manual hint strategy
- DB write
- insert into `chzzk_category_game_candidate`
- trusted mapping
- promotion/demotion workflow
- candidate storage/write policy
- API/web/serving changes
- `Combined`
- fuzzy matching
- automatic alias discovery
- automatic matching
- approximate matching
- similarity score
- phonetic/transliteration matching
- partial/punctuation-insensitive matching
- `game_external_id`
- tracked_universe
- App Catalog
- backfill/reingest
- live fetch
- scheduler mutation
- raw/private evidence promotion
