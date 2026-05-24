# Category-To-Game Alias / Manual Hint Contract Gate

Status: implementation gate
Ticket: CATEGORY-MAPPING-ALIAS-HINT-CONTRACT-GATE-001
Documented: 2026-05-24 (KST)

## Purpose

이 문서는 category-to-game alias/manual hint support를 구현하기 전에 future input contract boundary를 고정한다.

이 gate는 alias/manual hint implementation, storage schema, API shape, DB table shape, runtime contract, trusted mapping, serving semantics, 또는 `Combined` semantics를 승인하지 않는다. 목적은 다음 implementation ticket이 열린다면 synthetic/test-only dry-run extension으로만 제한되도록 입력, 출력, conflict, public-safety 경계를 정의하는 것이다.

## Prior Decision Basis

이 gate는 `CATEGORY-MAPPING-NON-EXACT-MATCHING-GATE-001`의 prior decision을 따른다.

- exact normalized matching은 안전하지만 유용한 proposal 시그널을 만들기에는 불충분한 상태로 남는다.
- curated alias/manual hint는 신뢰할 수 없는 검토 증거(untrusted review evidence)로만 고려될 수 있다.
- fuzzy matching은 계속 금지(forbidden) 상태로 남는다.
- automatic alias discovery는 계속 금지(forbidden) 상태로 남는다.
- 해당 체크포인트에서는 구현(implementation)이 승인되지 않았다.

이전 gate에서 허용된 aggregate evidence:

- candidate proposal count: `0`
- unresolved proposal count: `200`
- no-match proposal count: `200`
- DB write performed: `false`
- candidate insert performed: `false`

이 aggregate evidence는 raw category name, raw game name, raw API response, raw SQL output, raw command transcript, private runtime material을 포함하지 않는다.

## Decision

Alias and manual hint belong to one future synthetic/test-only contract family, distinguished by `hint_kind = "alias" | "manual_hint"`. This gate defines only the contract boundary; it does not approve implementation.

이 결정은 아래를 의미한다.

- `alias`와 `manual_hint`는 하나의 future contract family에 속한다.
- 두 입력은 `hint_kind`로만 구분한다.
- contract는 synthetic/test-only first다.
- public artifact에는 real category/game/channel/display value를 포함하지 않는다.
- next implementation이 나중에 승인되더라도 synthetic/test-only dry-run extension으로만 시작해야 한다.
- fuzzy matching, automatic alias discovery, automatic matching은 계속 forbidden이다.
- DB write, candidate insert, trusted mapping, API/web/serving, and `Combined`는 future Human Gate 뒤로 deferred 상태를 유지한다.

## Contract Family

`alias`는 curated alternate label이다. 이 label은 review candidate proposal을 만드는 데 도움을 줄 수 있는 untrusted review evidence일 뿐이다.

`manual_hint`는 human-provided review hint다. 이 hint도 review candidate proposal을 만드는 데 도움을 줄 수 있는 untrusted review evidence일 뿐이다.

공통 boundary:

- 둘 다 untrusted review evidence다.
- 둘 다 trusted mapping을 만들지 않는다.
- 둘 다 serving truth를 만들지 않는다.
- 둘 다 review를 skip할 수 없다.
- 둘 다 `trusted` / `approved`를 직접 만들 수 없다.
- 둘 다 DB write 또는 serving view 변경을 승인하지 않는다.

## Synthetic/Test-Only Input Contract

향후 구현(Future synthetic/test-only implementation)은 개념적으로 아래 fields만 입력으로 고려할 수 있다.

- `hint_kind`: curated alias와 manual hint를 구분한다. Allowed values는 `alias`, `manual_hint`뿐이다.
- `synthetic_chzzk_category_label`: tests only category-side label이다. Public artifact에 real category/channel/display value를 넣지 않기 위한 synthetic placeholder다.
- `synthetic_canonical_game_name`: tests only game-side name이다. Public artifact에 real game name을 넣지 않기 위한 synthetic placeholder다.
- `reason`: hint가 왜 존재하는지 설명하는 public-safe explanation이다.
- `source_note`: public-safe provenance/caveat note다. Private/raw source를 포함하지 않는다.

Allowed `hint_kind` values:

- `alias`
- `manual_hint`

이 contract는 storage schema, API shape, DB table shape, final runtime contract가 아니다.
Field name은 future dry-run input concept를 설명하기 위한 durable boundary이며, column name, JSON key, request/response field, table grain, persisted metadata로 확정되지 않는다.

향후 구현(Future implementation)이 테스트(tests)에서 synthetic IDs를 사용하더라도, 해당 IDs는 synthetic/test-only fixtures일 뿐 실제 canonical identity claim이 아니다.

## Alias Boundary

Alias는 curated input이어야 하며 automatically discovered input이 아니다.

- Alias는 신뢰할 수 없는 proposal candidates를 생성하는 데만 도움을 줄 수 있다.
- Alias의 source/provenance는 반드시 public-safe해야 한다.
- Alias conflict는 자동으로 해결되어서는 안 된다.
- Alias가 canonical identity를 내포해서는 안 된다.
- Alias가 DB 또는 serving views에 write를 수행해서는 안 된다.
- Alias는 raw provider payloads, raw API responses, 또는 private runtime evidence로부터 유추되어서는 안 된다.
- Alias가 `chzzk_category_game_candidate`를 생성하거나 업데이트해서는 안 된다.

## Manual Hint Boundary

Manual hint는 human-provided review evidence다.

- Manual hint는 신뢰할 수 없는 proposal candidates를 생성하는 데만 도움을 줄 수 있다.
- Manual hint는 반드시 public-safe한 `reason`과 `source_note`를 포함해야 한다.
- Manual hint가 검토(review)를 우회해서는 안 된다.
- Manual hint가 직접 trusted mapping을 생성해서는 안 된다.
- Manual hint가 DB 또는 serving views에 write를 수행해서는 안 된다.
- Manual hint가 `chzzk_category_game_candidate`를 생성하거나 업데이트해서는 안 된다.
- Manual hint가 raw/private evidence로부터 public artifacts로 승격(promoted)되어서는 안 된다.

## Conflict / Ambiguity Boundary

Conflict handling은 contract level에서 unresolved/ambiguous로 남긴다.

- same synthetic category hinting multiple synthetic games must remain unresolved/ambiguous.
- same synthetic alias pointing to multiple synthetic games must remain unresolved/ambiguous.
- conflicting hints must not auto-select a winner.
- conflict resolution은 향후 Human Gate의 작업이다.
- `rejected` is not generated automatically.
- `trusted` / `approved` remain future Human Gate terminology only.

Conflict가 발견되면 future dry-run output은 winner를 고르지 않고 public-safe caveat/counter로 보고해야 한다. Contract는 conflict resolution workflow, reviewer UI, promotion/demotion rules를 정의하지 않는다.

## Proposal Output Boundary

Future implementation may only produce:

- untrusted `candidate` proposals
- untrusted `unresolved` proposals
- public-safe한 caveats/counters

Future implementation must not produce:

- `rejected` automatically
- `trusted`
- `approved`
- serving의 진실 공급원(serving truth)
- API/web-visible mapping fields
- `Combined` rows/KPI/sorting/ranking

어떤 proposal도 canonical game identity, hidden join, ranking/sorting/KPI, API response, web UI behavior, 또는 `Combined` semantics에 사용할 수 없다.

## Fuzzy And Automatic Alias Discovery Boundary

Fuzzy matching remains forbidden.

Automatic alias discovery remains forbidden.

아래 matching 또는 discovery technique은 계속 금지한다.

- fuzzy matching
- automatic alias discovery
- approximate matching
- similarity score
- phonetic/transliteration matching
- partial/punctuation-insensitive matching
- automatic matching

금지 사유:

- false positive를 만들 수 있다.
- review-only proposal이 automatic matching처럼 보일 수 있다.
- score threshold, audit trail, conflict policy, false-positive handling policy가 없다.
- category-side evidence를 canonical game identity처럼 보이게 할 위험이 있다.
- automatically discovered alias는 hidden identity assertion을 만들 수 있다.

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

Examples가 필요하면 아래처럼 sanitized placeholders만 사용한다.

- `Synthetic Category A`
- `Synthetic Game A`
- `Synthetic Alias A`
- `Synthetic Manual Hint A`
- `Synthetic Reason A`

## Explicit Non-Goals

이 gate는 아래 항목을 승인하거나 구현하지 않는다.

- code implementation
- alias/manual hint implementation
- alias table implementation
- manual hint workflow implementation
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
- API endpoint changes
- web UI changes
- serving semantics
- `Combined`
- live fetch
- scheduler mutation
- backfill/reingest
- raw/private evidence promotion

## Required Validation For Future Implementation

Future `CATEGORY-MAPPING-ALIAS-HINT-DRY-RUN-001`은 최소한 아래를 검증해야 한다.

- input fixture가 synthetic/test-only인지 확인한다.
- `hint_kind`가 `alias` 또는 `manual_hint`만 허용하는지 확인한다.
- public artifact에 real category/game/channel/display value가 없는지 확인한다.
- public artifact에 raw provider payload, raw API response, raw SQL output, credentials, `.env` value, private path, scheduler XML/stdout, raw runtime log, screenshot, row-level UGC, live title, thumbnail이 없는지 확인한다.
- alias/manual hint가 untrusted `candidate` 또는 `unresolved` proposal만 만들 수 있는지 확인한다.
- conflict가 winner auto-selection 없이 unresolved/ambiguous로 남는지 확인한다.
- `rejected`가 자동 생성되지 않는지 확인한다.
- `trusted` / `approved`가 직접 생성되지 않는지 확인한다.
- DB write, insert into `chzzk_category_game_candidate`, API/web/serving/`Combined` exposure가 없는지 확인한다.
- fuzzy matching, approximate matching, similarity score, phonetic/transliteration matching, partial/punctuation-insensitive matching, automatic alias discovery가 계속 forbidden인지 확인한다.

## Stop Conditions For Future Implementation

Future implementation은 아래 조건 중 하나라도 발생하면 중단해야 한다.

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

권장되는 다음 티켓(Recommended next ticket):

`CATEGORY-MAPPING-ALIAS-HINT-DRY-RUN-001`

다음 티켓 목표(Next ticket goal):

`Implement a synthetic/test-only alias/manual hint dry-run extension that uses the contract defined by CATEGORY-MAPPING-ALIAS-HINT-CONTRACT-GATE-001.`

The next implementation must remain:

- synthetic/test-only
- no real raw values in public artifacts
- no DB write
- no candidate insert
- no trusted mapping
- no API/web/serving/`Combined`
- fuzzy matching forbidden
- automatic alias discovery forbidden
- no real observed-data alias/hint use

## Deferred Items

- alias/manual hint implementation
- real-data alias/manual hint use
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
