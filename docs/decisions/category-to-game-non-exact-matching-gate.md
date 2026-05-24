# Category-To-Game Non-Exact Matching Gate

Status: implementation gate
Ticket: CATEGORY-MAPPING-NON-EXACT-MATCHING-GATE-001
Documented: 2026-05-24 (KST)

## Purpose

이 문서는 category-to-game candidate generation을 `normalized exact match only` 밖으로
확장할 수 있는지에 대한 decision boundary를 고정한다.

이 gate는 non-exact matching 구현을 승인하지 않는다. 목적은 exact match only smoke
결과를 근거로, 다음에 검토할 수 있는 방향과 여전히 금지되는 matching 방식을 분리하는
것이다.

## Evidence Basis

최근 read-only smoke는 sanitized aggregate evidence만 제공했다. Public artifact에는 raw
category name, raw game name, raw API response, raw SQL output, raw command
transcript, private runtime material을 포함하지 않는다.

Allowed aggregate facts:

- input category count: `200`
- input game count: `154`
- generated proposal count: `200`
- candidate proposal count: `0`
- unresolved proposal count: `200`
- no-match proposal count: `200`
- ambiguous proposal count: `0`
- skipped/unknown source count: `0`
- DB write performed: `false`
- candidate insert performed: `false`

해석:

- 현재 exact normalized matching은 false positive를 만들지 않는 safe baseline이다.
- 하지만 위 aggregate result는 exact-only 방식이 useful proposal signal을 만들지
  못했음을 보여준다.
- 이 evidence는 non-exact implementation, trusted mapping, DB write, API/web exposure,
  serving semantics, 또는 `Combined` semantics를 승인하지 않는다.

## Decision

Exact normalized matching remains safe but insufficient for useful proposal signal. The next expansion may consider curated alias/manual hint policy only as untrusted review evidence. Fuzzy matching and automatic alias discovery remain forbidden.

이 결정은 아래를 의미한다.

- exact normalized matching은 현재 safe baseline으로 유지한다.
- future work는 curated alias/manual hint policy를 검토할 수 있다.
- alias/manual hint는 untrusted review evidence로만 취급한다.
- fuzzy matching은 계속 금지한다.
- automatic alias discovery는 계속 금지한다.
- automatic trusted mapping은 계속 금지한다.

## Allowed Next Direction

다음 방향은 curated alias/manual hint policy를 문서로 먼저 정의하는 것이다.

Future ticket은 implementation ticket이 아니라 synthetic/test-only contract gate여야 한다.
그 contract는 public-safe input shape, review-only output meaning, stop condition,
validation을 먼저 고정해야 한다.

## Alias / Manual Hint Boundary

`alias`는 사람이 curated한 alternate label이다. 이 label은 candidate proposal을 만드는
데 도움을 줄 수 있는 review-only evidence일 뿐이다.

`manual hint`는 사람이 제공한 review hint다. 이 hint도 candidate proposal을 만드는 데
도움을 줄 수 있는 review-only evidence일 뿐이다.

`trusted mapping`은 future Human Gate에서 별도로 승인해야 하는 state다. Alias 또는
manual hint는 trusted mapping을 만들거나 대체하지 않는다.

Future alias/manual hint input contract는 아래 조건을 모두 만족해야 한다.

- synthetic/test-first
- public-safe
- no real raw provider payloads in fixtures
- no private runtime evidence
- no hidden automatic identity assertion
- no direct promotion to `trusted` / `approved`
- no DB write
- no API/web/serving/`Combined`

Future alias/manual hint support가 열리더라도 아래 boundary는 유지해야 한다.

- alias/manual hint may only produce untrusted proposal candidates.
- alias/manual hint must not create trusted mapping.
- alias/manual hint must not write to serving views.
- alias/manual hint must not affect API/web/`Combined`.
- alias/manual hint must preserve human review boundary.
- alias/manual hint implementation is not approved by this ticket.
- Real category/game names must not appear in public artifacts.

## Fuzzy Matching Boundary

Fuzzy matching은 계속 forbidden이다.

금지 사유:

- false positive를 만들 수 있다.
- review-only proposal이 automatic matching처럼 보일 수 있다.
- score threshold, review UX, audit trail, false-positive handling policy가 없다.
- category evidence를 canonical game identity처럼 보이게 할 위험이 있다.

이 gate는 아래를 승인하지 않는다.

- fuzzy matching
- similarity score
- punctuation-insensitive matching
- phonetic matching
- transliteration
- approximate string matching
- partial matching
- automatic matching

## Automatic Alias Discovery Boundary

Automatic alias discovery는 계속 forbidden이다.

금지 사유:

- 자동 생성된 alias는 hidden identity assumption을 만들 수 있다.
- 자동 생성 alias가 provider-to-game mapping evidence처럼 보일 수 있다.
- alias source, provenance, review status, conflict handling, audit trail이 아직
  정의되지 않았다.

이 gate는 automatic alias discovery 구현을 승인하지 않는다. 허용되는 다음 단계는 오직
synthetic/test-only alias/manual hint contract gate다.

## Proposal Classification Boundary

현재 proposal state semantics는 유지한다.

- `candidate`: untrusted review proposal only.
- `unresolved`: untrusted unresolved evidence only.
- `rejected`: not generated automatically; reserved for future human review workflow.
- `trusted` / `approved`: future Human Gate terminology only.

Alias/manual hint가 later gate에서 열리더라도 review를 건너뛰면 안 된다. 어떤 proposal도
serving truth, canonical game identity, hidden join, ranking/sorting/KPI, API response,
web UI, 또는 `Combined` semantics에 사용할 수 없다.

## Matching Semantics To Preserve

Current exact-match semantics remain valid baseline.

- normalization: `strip`, `casefold`, whitespace collapse only
- exact match candidate behavior remains safe baseline
- non-exact extension must be explicit and separately tested

Future alias/manual hint support must not silently change exact-match behavior.

## Public / Private Safety

Public docs, tests, PR bodies는 public-safe artifact만 포함해야 한다.

Public artifact에는 아래 항목을 포함하지 않는다.

- secrets
- `.env` values
- credentials
- raw provider payloads
- raw API responses
- raw SQL output
- private paths
- scheduler XML/stdout
- raw runtime logs
- screenshots
- row-level UGC
- category/channel/display values
- real game names
- live titles
- thumbnails
- raw command transcript
- raw Grafana/Prometheus responses

Examples가 필요하면 아래처럼 sanitized placeholder만 사용한다.

- `Synthetic Category A`
- `Synthetic Game A`
- `Synthetic Alias A`
- `Synthetic Manual Hint A`

## Explicit Non-Goals

이 gate는 아래 항목을 승인하거나 구현하지 않는다.

- code implementation
- alias table implementation
- manual hint workflow implementation
- fuzzy matching implementation
- similarity score
- automatic alias discovery
- automatic matching
- trusted mapping
- promotion/demotion workflow
- DB write
- insert into `chzzk_category_game_candidate`
- schema/DDL changes
- `game_external_id`
- tracked_universe
- App Catalog
- API endpoint changes
- web UI changes
- serving semantics
- `Combined`
- live fetch
- scheduler mutation
- backfill/reingest
- raw/private evidence promotion

## Required Validation For Future Work

Future alias/manual hint contract gate는 최소한 아래를 검증해야 한다.

- input fixture가 synthetic/test-only인지 확인한다.
- public artifact에 real raw provider payloads, private runtime evidence, raw category
  values, raw game values가 없는지 확인한다.
- alias/manual hint가 untrusted proposal candidate만 만들 수 있는지 확인한다.
- alias/manual hint가 `trusted` / `approved`로 직접 승격되지 않는지 확인한다.
- exact normalized matching semantics가 silently changed 되지 않았는지 확인한다.
- DB write, candidate insert, API/web/serving/`Combined` exposure가 없는지 확인한다.
- fuzzy matching과 automatic alias discovery가 여전히 forbidden인지 확인한다.

## Stop Conditions For Future Work

Future work는 아래 조건 중 하나라도 발생하면 중단해야 한다.

- concrete alias storage/schema/API behavior를 선택해야 진행할 수 있다.
- real category/game/channel/display value가 필요하다.
- raw/private evidence가 필요하다.
- fuzzy matching 또는 automatic alias discovery가 필요하다.
- automatic matching, trusted mapping, promotion/demotion이 필요하다.
- DB write 또는 insert into `chzzk_category_game_candidate`가 필요하다.
- API/web/serving/`Combined` 변경이 필요하다.
- `game_external_id`, tracked_universe, App Catalog 사용이 필요하다.
- validation에서 public-safety leakage 또는 boundary contradiction이 발견된다.

## Next Ticket

Recommended next ticket:

`CATEGORY-MAPPING-ALIAS-HINT-CONTRACT-GATE-001`

Next ticket goal:

`Define a synthetic/test-only curated alias/manual hint input contract before any implementation.`

The next ticket must remain:

- docs/decision first
- no implementation
- synthetic/test-only
- no real raw values in public artifacts
- no DB write
- no trusted mapping
- no API/web/serving/`Combined`
- fuzzy matching forbidden
- automatic alias discovery forbidden

Do not recommend an implementation ticket as the immediate next ticket.

## Deferred Items

- alias/manual hint input contract
- alias/manual hint implementation
- fuzzy matching
- automatic alias discovery
- automatic matching
- trusted mapping
- promotion/demotion workflow
- DB write
- insert into `chzzk_category_game_candidate`
- schema/DDL changes
- `game_external_id`
- tracked_universe
- App Catalog
- API/web/serving changes
- `Combined`
- live fetch
- scheduler mutation
- backfill/reingest
- raw/private evidence promotion
