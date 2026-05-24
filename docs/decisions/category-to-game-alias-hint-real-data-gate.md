# Category-To-Game Alias / Manual Hint Real-Data Gate

Status: implementation gate
Ticket: CATEGORY-MAPPING-ALIAS-HINT-REAL-DATA-GATE-001
Documented: 2026-05-24 (KST)

## Purpose

이 문서는 synthetic/test-only alias/manual hint dry-run support 이후 real-data alias/manual hint 작업을 열 수 있는지에 대한 decision boundary를 고정한다.

이 gate는 real-data smoke를 실행하지 않는다. 이 gate는 code implementation, API call, DB query, service start/stop/restart, scheduler action, live fetch, DB write, SQL change, API/web/serving change, 또는 `Combined` semantics를 수행하거나 승인하지 않는다.

목적은 future `CATEGORY-MAPPING-ALIAS-HINT-REAL-DATA-SMOKE-001` ticket이 열린다면 read-only, no-write, sanitized aggregate smoke로만 제한되도록 source boundary, public artifact boundary, stop condition을 먼저 고정하는 것이다.

## Prior Decision Basis

이 gate는 아래 prior decision chain을 따른다.

- `CATEGORY-MAPPING-CANDIDATE-GENERATION-DRY-RUN-001`은 synthetic exact-match dry-run support를 추가했다.
- Real-data exact-match smoke는 유용한 candidate signal을 생성하지 못했다.
- `CATEGORY-MAPPING-NON-EXACT-MATCHING-GATE-001`은 fuzzy matching 및 automatic alias discovery를 금지(forbidden) 상태로 유지했다.
- `CATEGORY-MAPPING-ALIAS-HINT-CONTRACT-GATE-001`은 `hint_kind = "alias" | "manual_hint"`를 synthetic/test-only contract family로 정의했다.
- `CATEGORY-MAPPING-ALIAS-HINT-DRY-RUN-001`은 synthetic/test-only alias/manual hint dry-run support를 구현했다.

exact-match real-data smoke에서 허용된 aggregate evidence:

- exact-match real-data candidate proposal count: `0`
- exact-match real-data unresolved proposal count: `200`
- DB write performed: `false`
- candidate insert performed: `false`

이 aggregate evidence는 raw category name, raw game name, raw alias/hint row, raw API response, raw SQL output, raw command transcript, private runtime material을 포함하지 않는다.

## Decision

Real-data alias/manual hint work may be opened only as a future read-only, no-write, sanitized aggregate smoke. Real category/game names and real hint rows remain private/local evidence and must not be added to public artifacts.

즉, real-data alias/manual hint 작업은 오직 향후의 read-only, no-write, sanitized aggregate smoke로서만 오픈될 수 있다. Real category/game names 및 real hint rows는 private/local evidence로 남아야 하며, public artifacts에 추가되어서는 안 된다.

이 결정은 아래를 의미한다.

- real-data alias/manual hint 작업은 future smoke로만 열 수 있다.
- future smoke는 read-only, no-write, sanitized aggregate output only여야 한다.
- real category/game names, real alias names, real manual hint rows는 private/local evidence로만 남는다.
- real alias/manual hint source는 local/private operator-controlled evidence여야 한다.
- 이 gate는 arbitrary local data access를 승인하지 않는다.
- 이 gate는 real-data alias/manual hint implementation을 승인하지 않는다.
- DB write, candidate insert, trusted mapping, API/web/serving, 그리고 `Combined`는 계속 future Human Gate 뒤로 deferred 상태를 유지한다.
- fuzzy matching, automatic alias discovery, automatic matching은 계속 forbidden이다.

## Real-Data Source Boundary

Real alias/manual hint source는 local/private operator-controlled evidence다. 이 source는 public fixture, tracked public docs table, serving contract, 또는 automatic discovery output이 아니다.

Future smoke가 source를 읽을 수 있는 조건은 아래로 제한한다.

- future ticket에서 explicitly approved read-only local/private source path 또는 command를 지정해야 한다.
- 지정된 source는 real alias/manual hint evidence를 operator-controlled evidence로만 제공해야 한다.
- 지정된 source는 public artifact에 raw value를 출력하지 않는 방식으로만 읽어야 한다.
- source shape가 ambiguous하면 smoke를 중단해야 한다.
- aggregate-only reporting을 보장할 수 없으면 smoke를 중단해야 한다.

이 gate는 아래를 승인하지 않는다.

- arbitrary local data access
- public fixture로 real alias/manual hint source 추가
- public docs table로 real alias/manual hint source 추가
- serving contract로 real alias/manual hint source 정의
- real alias/manual hint source automatic inference
- `.env` values, credentials, private paths, raw provider payloads를 public output에 포함하는 source access
- 명시되지 않은 local/private files, artifacts, logs, outputs 접근

Future smoke는 public output을 만들기 위해 `.env` values, credentials, private paths, raw provider payloads, raw API responses, raw SQL output, raw runtime logs를 inspect하거나 print해서는 안 된다.

## Public Artifact Boundary

Public artifacts include:

Public artifacts는 다음을 포함한다.

- PR body
- public docs
- tests
- fixtures/examples
- repo에 커밋된 logs/reports
- public PR에 복사될 수 있는 Codex completion reports

Public artifacts는 다음과 같이 위생화된 집계 출력(sanitized aggregate output)만 포함할 수 있다:

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

Public artifacts는 다음을 포함해서는 안 된다:

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

Future smoke는 위생화된 집계 제안 수(sanitized aggregate proposal counts)만 공개적으로 리포트할 수 있다.

허용되는 public summary fields는 aggregate counters 및 aggregate timestamps로 제한된다:

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

Future smoke는 실제 이름(real names)을 포함하는 public row-level proposals를 생성해서는 안 된다.
Future smoke는 real category/game names, real alias names, real manual hint rows, channel/display values, live titles, thumbnails, raw provider payloads, raw API responses, raw SQL output, private paths, credentials, `.env` values, scheduler XML/stdout, raw runtime logs, screenshots, row-level UGC, raw command transcript, 또는 raw Grafana/Prometheus responses를 출력(print)해서는 안 된다.

## Private / Local Evidence Boundary

Real alias/manual hint evidence는 향후 명시적인 public-safe strategy가 존재하기 전까지 오직 private/local operator evidence로만 존재할 수 있다.

- Private/local evidence must not be copied into public docs or tests. 즉, private/local evidence는 public docs나 tests에 복사되어서는 안 된다.
- Public docs는 private/local evidence를 `source class, not by value` 원칙에 따라 value가 아닌 source class로만 참조할 수 있다.
- Future smoke가 private/local evidence를 사용하는 경우, completion report는 aggregate counts only 원칙에 따라 오직 aggregate counts만 요약해야 한다.
- If aggregate-only reporting cannot be guaranteed, future smoke는 중단되어야 한다.
- Raw/private evidence는 public fixtures, public examples, public docs, PR bodies, 또는 커밋된 reports로 승격(promote)되어서는 안 된다.

## Alias / Manual Hint Boundary

`alias` is a curated alternate label that may help propose a review candidate. 즉, `alias`는 검토 후보(review candidate)를 제안하는 데 도움이 될 수 있는 curated alternate label이다.

`manual_hint`는 사람이 제공한 검토 힌트(human-provided review hint)로서 검토 후보를 제안할 수 있다.

Both remain untrusted review evidence. 즉, 둘 다 신뢰할 수 없는 검토 증거로 남는다.

- Neither creates trusted mapping.
- Neither creates serving truth.
- Neither bypasses review.
- Neither directly produces `trusted` / `approved`.
- 둘 다 canonical game identity를 생성하지 않는다.
- 둘 다 DB write 또는 candidate insert를 허용하지 않는다.
- 둘 다 API/web/serving/`Combined` 노출을 허용하지 않는다.

Future real-data smoke는 오직 alias/manual hint evidence가 유용한 신뢰할 수 없는 제안 수(untrusted proposal counts)를 생성할 수 있는지 여부만 테스트할 수 있다.

## Proposal Output Boundary

Future smoke may publicly report only aggregate proposal counts. 즉, future smoke는 오직 aggregate proposal counts만 공개적으로 리포트할 수 있다.

Future smoke는 실제 이름(real names)을 포함하는 public row-level proposals를 생성해서는 안 된다.

Future smoke는 다음을 수행해서는 안 된다:

- DB write
- insert into `chzzk_category_game_candidate`
- trusted mapping
- promotion/demotion
- API/web exposure
- serving changes
- `Combined`

Why DB write and candidate insert remain forbidden:
- Real-data alias/manual hint evidence는 여전히 신뢰할 수 없는 검토 증거(untrusted review evidence)이다.
- Future smoke의 목표는 storage mutation이 아닌 signal detection이다.
- Candidate storage semantics, write policy, audit trail, 그리고 review workflow는 Human Gate 제어 하에 유지된다.
- Writing rows would make private/local evidence look like durable candidate state before the source and review policy are approved.
- 즉, row를 작성하는 것은 source 및 review policy가 승인되기 전에 private/local evidence를 영구적인 candidate state처럼 보이게 만들 수 있다.

Why trusted mapping remains forbidden:
- Alias/manual hint evidence는 검토 후보를 제안할 수 있지만, canonical game identity는 아니다.
- 승인된 promotion rule, reviewer workflow, conflict policy, 또는 serving contract가 없다.
- `trusted` / `approved`는 계속 향후의 Human Gate 용어로만 남는다.

Why API/web/serving/`Combined` remain forbidden:
- 현재 Chzzk API/web surfaces는 category-only 관측 증거(observed evidence)이다.
- Candidate proposals는 serving truth가 아니다.
- Candidate proposals를 노출하는 것은 승인되지 않은 Steam-Chzzk mapping, ranking, sorting, KPI, 또는 관계 의미론(relationship semantics)을 내포할 수 있다.
- `Combined`는 trusted mapping 및 serving semantics가 별도로 승인될 때까지 차단된 상태를 유지한다.

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
- 실제 이름을 포함한 public fixture
- fuzzy matching
- automatic alias discovery
- automatic matching
- trusted mapping
- promotion/demotion workflow
- `game_external_id`
- tracked_universe
- App Catalog
- API endpoint 변경
- web UI 변경
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

Future smoke validation은 또한 어떠한 public artifact도 real category/game/channel/display values, real alias names, real manual hint rows, live titles, thumbnails, raw provider payloads, raw API responses, raw SQL output, private paths, credentials, `.env` values, scheduler XML/stdout, raw runtime logs, screenshots, row-level UGC, raw command transcript, 또는 raw Grafana/Prometheus responses를 포함하지 않음을 확인해야 한다.

## Stop Conditions For Future Smoke

Future smoke must stop if:

Future smoke는 다음과 같은 경우 중단되어야 한다.

- source requires raw provider payload printing
- source requires real category/game names in public output
- source requires credentials or `.env` value inspection
- source requires DB write or candidate insert
- source requires API/web/serving changes
- source가 `Combined`를 요구하는 경우
- source requires fuzzy matching or automatic alias discovery
- source가 automatic matching, approximate matching, similarity score, phonetic/transliteration matching, 또는 partial/punctuation-insensitive matching을 요구하는 경우
- source가 안전하게 기술될 수 없는 모호한(ambiguous) private/local paths를 요구하는 경우
- source produces row-level output that cannot be sanitized
- source shape가 ambiguous한 경우
- aggregate-only reporting이 보장될 수 없는 경우

## Next Ticket

Recommended next ticket:

`CATEGORY-MAPPING-ALIAS-HINT-REAL-DATA-SMOKE-001`

Next ticket goal:

`Run a read-only, no-write, sanitized aggregate smoke using approved local/private real-data alias/manual hint evidence to see whether useful untrusted candidate proposal signal exists.`
(승인된 local/private real-data alias/manual hint evidence를 사용하여 유용한 신뢰할 수 없는 candidate proposal signal이 존재하는지 확인하기 위해 read-only, no-write, sanitized aggregate smoke를 실행한다.)

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
- 승인된 smoke boundary를 벗어나는 real-data alias/manual hint implementation 금지

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
