# Category-To-Game Real-Data Proposal Smoke Gate

Status: implementation gate
Ticket: CATEGORY-MAPPING-REAL-DATA-PROPOSAL-SMOKE-GATE-001
Documented: 2026-05-24 (KST)

## Purpose

이 문서는 synthetic/test-only dry-run proposal builder 이후의 다음 category-to-game
mapping 단계를 열 수 있는지 결정한다.

이 gate는 실제 smoke를 실행하지 않는다. 이 gate는 API call, DB query, service
start/stop/restart, scheduler action, live fetch, data capture, code change, SQL change,
API/web/serving change를 수행하거나 승인하지 않는다.

목적은 future `CATEGORY-MAPPING-CANDIDATE-REAL-DATA-PROPOSAL-SMOKE-001` ticket이
열릴 수 있는 최소 boundary를 read-only, no-write, sanitized proposal smoke로만
제한하는 것이다.

## Decision

The next implementation may be opened only as a read-only, no-write, sanitized real observed-data proposal smoke.

이 결정은 future `CATEGORY-MAPPING-CANDIDATE-REAL-DATA-PROPOSAL-SMOKE-001`에만
적용되는 gate다. 이 문서는 arbitrary local data access를 승인하지 않는다. Future
ticket은 사용할 read-only command와 read-only path 또는 listener boundary를
명시해야 하며, 명시되지 않은 local data, private runtime material, API response,
SQL output, scheduler output은 읽거나 public artifact로 옮길 수 없다.

이 gate는 아래 항목을 승인하지 않는다.

- DB write
- candidate table insert
- trusted mapping
- API/web/serving exposure
- `Combined`

## Allowed Next Smoke

Future `CATEGORY-MAPPING-CANDIDATE-REAL-DATA-PROPOSAL-SMOKE-001`은 아래 범위에서만
열 수 있다.

- 이미 안전하게 접근 가능한 source에 대해 future ticket에 명시된 read-only command
  또는 path만 사용한다.
- 이미 실행 중인 read-only `/chzzk/categories/overview` listener가 안전하게
  제공되는 경우에만 사용할 수 있다.
- service를 새로 시작하거나 변경하지 않는다.
- observed Chzzk category evidence를 기존 dry-run proposal builder input shape에
  맞추는 adapter boundary를 둘 수 있다.
- 안전한 read-only path로 사용 가능한 경우에만 `dim_game`-like canonical game name
  source를 사용할 수 있다.
- output은 sanitized aggregate proposal summary only다.
- public artifact에는 raw row value를 포함하지 않는다.

허용 가능한 summary counter는 aggregate 값으로만 제한한다.

- input category count
- input game count
- `candidate` proposal count
- `unresolved` proposal count
- ambiguous proposal count
- no-match proposal count
- skipped/unknown source count
- latest observed evidence timestamp, 단 이미 aggregate로 안전하게 제공되는 경우만

## Input Source Boundary

Preferred Chzzk input for the first real-data smoke는 future ticket에서 명시적으로
승인된 read-only command/path가 있을 때만 아래 중 하나를 쓸 수 있다.

- 이미 떠 있는 read-only `/chzzk/categories/overview`
- 안전한 env-backed read-only access가 이미 있고 future ticket에 command/path가
  명시된 DB aggregate/source rows

이 gate는 아래 행위를 승인하지 않는다.

- service start
- service mutation
- scheduler run 또는 scheduler mutation
- live fetch
- secret inspection 또는 secret printing
- raw API response를 public docs/PR에 복사
- raw SQL output을 public docs/PR에 복사
- 명시되지 않은 local/private file, artifact, log, output 접근

Steam side for the first real-data smoke는 safe read-only source가 명시된 경우에만
`dim_game` read-only source를 선호한다.

다음 source는 첫 real-data proposal smoke에서 사용하지 않는다.

- `game_external_id`
- tracked_universe
- App Catalog
- alias source
- manual hint source

## Output Boundary

Future smoke output은 아래 속성을 모두 만족해야 한다.

- dry-run proposal summary only
- sanitized
- aggregate-oriented
- public-safe
- no-write

Future smoke output은 아래 항목을 포함할 수 없다.

- raw category names
- raw game names
- channel names
- display names
- live titles
- thumbnails
- raw provider payloads
- raw API response
- raw SQL output
- credentials or `.env` values
- private host/path/runtime details
- raw command transcript
- scheduler XML/stdout
- raw runtime logs
- screenshots
- row-level UGC
- raw Grafana/Prometheus responses

## Public / Private Safety

Public artifact는 sanitized aggregate summary와 durable boundary text만 포함한다.

Private/local-only로 남아야 하는 항목은 raw provider payload, raw API response, raw
SQL output, raw row value, credential, `.env` value, private path, scheduler
XML/stdout, raw runtime log, screenshot, row-level UGC, category/channel/display
value, real game name, live title, thumbnail, and raw Grafana/Prometheus response다.

Future smoke가 local/private material을 읽어야 한다면, future ticket은 최소한 아래를
명시해야 한다.

- 사용할 read-only command
- 사용할 read-only path 또는 listener
- public artifact에 남길 sanitized aggregate field
- raw/private value를 출력하지 않는 validation 방법
- stop condition

명시되지 않은 local/private material은 이 gate로 승인된 source가 아니다.

## Matching Boundary

Future smoke는 기존 dry-run builder semantics를 유지해야 한다.

Allowed normalization은 아래 세 가지뿐이다.

- `strip`
- `casefold`
- whitespace collapse

아래 matching technique은 허용하지 않는다.

- fuzzy matching
- alias matching
- partial matching
- punctuation-insensitive matching
- similarity score
- manual hints

Classification은 아래와 같이 유지한다.

- `candidate`: exactly one normalized exact match
- `unresolved`: zero matches or two or more matches
- `rejected`: not generated automatically

`candidate`, `unresolved`, `rejected`는 모두 untrusted review evidence state다.

`category_type=GAME`은 provider category type evidence only다.

- canonical identity를 만들 수 없다.
- candidate proposal을 조용히 filter하는 precondition이 될 수 없다.
- caveat, counter, metadata로만 report할 수 있다.

## Explicit Non-Goals

이 gate는 아래 항목을 승인하거나 구현하지 않는다.

- real-data candidate write
- DB write
- insert into `chzzk_category_game_candidate`
- trusted mapping
- promotion/demotion workflow
- `game_external_id`
- tracked_universe
- App Catalog
- fuzzy/alias/partial matching
- manual hints
- API endpoint changes
- web UI changes
- serving semantics
- `Combined`
- live fetch
- scheduler mutation
- backfill/reingest
- schema/DDL changes
- raw/private evidence promotion
- code implementation
- smoke execution
- API call
- DB query
- service start/stop/restart
- data capture

## Required Validation For The Next Smoke

Future `CATEGORY-MAPPING-CANDIDATE-REAL-DATA-PROPOSAL-SMOKE-001`은 최소한 아래
validation을 가져야 한다.

- ticket에 명시된 read-only command/path 또는 listener만 사용했는지 확인한다.
- DB write가 발생하지 않았음을 확인한다.
- insert into `chzzk_category_game_candidate`가 발생하지 않았음을 확인한다.
- output이 sanitized aggregate summary only인지 확인한다.
- public artifact에 raw category/game/channel/display value가 없는지 확인한다.
- public artifact에 raw API response, raw SQL output, raw provider payload,
  credentials, `.env` value, private path, scheduler XML/stdout, raw runtime log,
  screenshot, row-level UGC, live title, thumbnail이 없는지 확인한다.
- existing dry-run builder matching semantics가 유지되는지 확인한다.
- `category_type=GAME`이 canonical identity나 silent filter가 되지 않는지 확인한다.
- `rejected`가 자동 생성되지 않는지 확인한다.
- API/web/serving/`Combined` surface가 변경되지 않았는지 확인한다.

## Stop Conditions For The Next Smoke

Future smoke는 아래 조건 중 하나라도 발생하면 중단해야 한다.

- future ticket에 explicit read-only command/path 또는 listener boundary가 없다.
- read-only access인지 확인할 수 없다.
- service start, service mutation, scheduler action, live fetch가 필요하다.
- DB write 또는 candidate table insert가 필요하다.
- raw/private evidence를 public artifact에 넣어야 진행할 수 있다.
- raw category/game/channel/display value를 출력해야 진행할 수 있다.
- secret, `.env` value, credential, private path를 inspect하거나 print해야 한다.
- `game_external_id`, tracked_universe, App Catalog, alias, manual hint가 필요하다.
- fuzzy/alias/partial/punctuation-insensitive matching 또는 similarity score가 필요하다.
- API/web/serving exposure 또는 `Combined` 변경이 필요하다.
- trusted mapping, promotion/demotion, schema/DDL, backfill/reingest가 필요하다.
- validation에서 scope creep 또는 public-safety leakage가 발견된다.

## Why This Does Not Approve Trusted Mapping Or `Combined`

Real observed-data proposal smoke는 review-only dry-run proposal summary를 만드는
boundary일 뿐이다.

이 gate는 category evidence를 canonical game identity로 승격하지 않는다.
`candidate`와 `unresolved`는 trusted mapping이 아니며, `rejected`는 automatic
generation status가 아니다. 어떤 proposal도 serving truth, hidden join,
ranking/sorting/KPI, API response, web UI, or `Combined` semantics에 사용할 수 없다.

Trusted mapping, promotion/demotion workflow, API/web/serving exposure, and
`Combined`는 future Human Gate가 별도로 승인해야 한다.

## Next Ticket

Recommended next ticket, only if this gate is accepted:

`CATEGORY-MAPPING-CANDIDATE-REAL-DATA-PROPOSAL-SMOKE-001`

다음 ticket은 아래 범위로만 작성해야 한다.

- read-only
- no-write
- no API/web/serving exposure
- no `Combined`
- sanitized aggregate report only
- no public raw values
- explicit read-only command/path or listener boundary required

## Deferred Items

- smoke execution
- real-data candidate write
- DB write
- insert into `chzzk_category_game_candidate`
- trusted mapping
- promotion/demotion workflow
- `game_external_id`
- tracked_universe
- App Catalog
- API/web/serving changes
- `Combined`
- live fetch
- scheduler mutation
- backfill/reingest
- schema/DDL changes
- raw/private evidence promotion
