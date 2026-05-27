# Category-To-Game Mapping Contract

Status: docs-only planning boundary  
Date: 2026-05-19 (KST)

CATEGORY-MAPPING-TRUSTED-STORAGE-CONTRACT-001 이후, `trusted`는 `chzzk_category_game_mapping.mapping_status`에만 저장되는 값이다. 

`chzzk_category_game_candidate.status`, API/UI state, serving exposure에는 사용하지 않는다.

이 문서는 Chzzk category observed evidence를 Steam canonical game에 연결하기 위한 첫 planning boundary를 고정한다.

이 결정은 schema, API, runtime, loader, scheduler, web, DB write, 또는 Combined semantics 구현 승인이 아니다.

현재 durable context는 `README.md`, `docs/source-inventory.md`, `docs/data-model-spec.md` 를 따른다.

## Purpose

목적은 Chzzk category와 Steam canonical game 사이의 연결을 어떻게 시작할지 정하는 것이다.

첫 boundary는 "자동 매핑"이 아니라 "review 가능한 mapping 후보와 판단 기록"이다.

Chzzk category evidence는 canonical game identity가 아니며, 사람이 검토하거나 검토 가능한 workflow를 거치기 전에는 trusted game mapping으로 쓰지 않는다.

Candidate evidence는 Combined KPI, canonical game semantics, 또는 serving semantics에 쓰지 않는다.

## Current State

- Steam-only baseline은 구현된 현재 runtime baseline이다.
- Chzzk는 category-level observed facts와 read-only `/chzzk/categories/overview` source API로 제한되어 있다.
- Chzzk category observed evidence는 category browser evidence일 뿐이며, Steam game mapping, canonical game semantics, Combined KPI로 승격되지 않았다.
- Steam-Chzzk mapping과 Combined semantics는 아직 구현되지 않았다.
- `categoryType=GAME` 은 Chzzk provider의 category type evidence이며, `dim_game` 의 canonical game identity가 아니다.

## Proposed MVP Boundary

MVP mapping boundary는 manual 또는 reviewable workflow first로 둔다.

- mapping 후보는 Chzzk `category id`, `category name`, `category type` 을 Steam canonical game 후보와 비교하는 방향에서 시작한다.
- candidate relation은 existing canonical boundary인 `dim_game` 과 `game_external_id` 방향으로 검토한다.
- 이 문서는 relation direction만 기록하며, `game_external_id` schema나 persisted metadata column을 추가하지 않는다.
- ambiguous alias, renamed category, regional title, franchise collision, same-name collision은 자동 확정하지 않고 `unresolved` 상태로 남긴다.
- `categoryType=GAME` 만으로는 Steam canonical game identity를 판단하기에 충분하지 않다.
- mapping이 trusted semantics로 사용되려면 별도 승인된 implementation slice와 promotion gate가 먼저 필요하다.

## Candidate Workflow Contract

Candidate workflow의 목적은 Chzzk category observed evidence를 Steam canonical game 후보와 비교할 수 있는 review 대상으로 만드는 것이다.
이 workflow는 trusted mapping을 만들거나 승인하는 구현이 아니다.

State 의미는 planning contract로만 정의한다.

- `candidate`: review 가능한 mapping 가능성이다. 이 상태만으로 trusted mapping, Combined KPI, canonical game semantics에 사용할 수 없다.
- `unresolved`: 판단에 필요한 ambiguity가 남아 있다. guessed mapping, automatic matching, auto-promotion을 허용하지 않는다.
- `rejected`: 검토 결과 의도적으로 수용하지 않은 후보다. rejected evidence도 trusted mapping으로 되살리지 않는다.
- `trusted` / `approved`: future implementation gate 이름으로만 언급한다. 이 PR은 이를 현재 repo에 존재하는 persisted state, schema value, API field, UI field로 정의하지 않는다.

CATEGORY-MAPPING-TRUSTED-STORAGE-CONTRACT-001 이후에도 위 historical statement는 `approved`, `chzzk_category_game_candidate.status`, API/UI/serving exposure에 대해서는 계속 유효하다.

`trusted` 는 이제 `chzzk_category_game_mapping.mapping_status`에만 저장되는 값이다.

## Current Trusted Storage Contract

`CATEGORY-MAPPING-TRUSTED-STORAGE-CONTRACT-001` 별도의 trusted storage를 추가:

- `chzzk_category_game_candidate.status` remains limited to `candidate`,
  `unresolved`, `rejected`.
- `chzzk_category_game_mapping.mapping_status` is limited to `trusted`.
- Candidate row는 trusted storage에 자동으로 채워지지 않는다.
- 현재 local 17개 candidate는 이 ticket에서 insert하거나 promotion하지 않는다.
- API/web/serving/`Combined` exposure remains deferred.
- candidate를 trusted mapping으로 승격하는 작업은 후속 Human Gate ticket으로 남긴다.

Updated by `CATEGORY-MAPPING-TRUSTED-MAPPING-SERVING-VIEW-001`: trusted mapping storage에는 내부 read-only DB serving view contract인 `srv_chzzk_category_game_mapping`이 추가됐다.


이 view는 `mapping_status` = `'trusted'` 인 `chzzk_category_game_mapping` row만 읽고, `dim_game` 을 join하며, nullable latest `fact_chzzk_category_30m` context를 붙일 수 있다.

이 PR은 내부 read-only DB serving view contract만 추가한다.

API 노출, web 노출, product serving behavior, `Combined` semantics는 추가하지 않는다.

`chzzk_category_game_candidate`는 읽지 않으며, `reviewed_by`, raw manual-hint evidence, candidate status, row-level private evidence도 노출하지 않는다.

아래 ambiguity는 자동 확정하지 않는다.

- ambiguous alias
- renamed category
- regional title
- franchise collision
- same-name collision

위 경우는 review 가능 evidence가 있어도 `unresolved` 로 남겨야 하며, 사람이 검토할 수 있는 별도 promotion rule이 승인되기 전까지 mapping 사용을 열지 않는다.

Future implementation slice에서 검토할 metadata candidates:

- `mapping_status`
- `mapping_method`
- `confidence`
- `evidence`
- reviewer/operator note
- created/updated/reviewed timestamps

위 항목은 metadata category 후보일 뿐이다.

이 문서는 column name, JSON shape, table grain, API field, UI field, note format, 또는 public evidence example을 확정하지 않는다.

## Future Implementation Checklist

나중에 implementation ticket을 열려면 아래 결정을 별도로 내려야 한다.

- storage shape, status metadata, evidence format, reviewer/operator note shape, timestamp behavior
- promotion/demotion rules와 rejected/unresolved 재검토 규칙
- `categoryType=GAME` 이 canonical game identity로 취급되지 않음을 증명하는 durable docs와 regression tests
- Combined semantics를 trusted mapping과 serving semantics가 별도 승인될 때까지 blocked 상태로 유지하는 acceptance criteria

## Success Criteria For Later Slices

나중에 implementation slice를 열려면 아래 조건을 먼저 만족해야 한다.

- mapping은 trusted semantics로 쓰이기 전에 review 가능해야 한다.
- ambiguous alias/collision은 guessed mapping이 아니라 `unresolved` 상태로 남아야 한다.
- Chzzk `categoryType=GAME` 은 canonical game identity로 취급하지 않아야 한다.
- Combined view는 mapping contract와 serving semantics가 별도 승인될 때까지 blocked 상태로 남아야 한다.

## Explicit Non-Goals

Historical note: 아래 original planning non-goals는 CATEGORY-MAPPING-TRUSTED-STORAGE-CONTRACT-001 이전에 작성됐다.
그 이후 ticket은 `chzzk_category_game_mapping` SQL/DDL storage contract만 supersede한다.
Trusted insert,
Trusted insert, promotion, API/web exposure, product serving behavior, `Combined`는 여전히 non-goal이다.

이번 slice에서는 아래 작업을 하지 않는다.

- schema, SQL, migration, model, API, web, loader, scheduler, runtime behavior 변경
- DB write, backfill, reingest, bootstrap, DDL
- live Chzzk fetch
- 별도 승인 없는 category search API probe
- Combined semantics
- `gold_stream_game_30m`
- generalized provider abstraction
- automatic category-to-game matching
- raw provider payloads, UGC, credentials, private paths, local scheduler evidence, screenshots, raw API responses를 public docs에 추가

## Public Boundary

Public docs에는 durable planning contract만 둔다.

State 의미와 promotion gate의 존재는 public docs에 남길 수 있다.

Mapping 판단의 근거가 되는 raw provider response, row-level UGC, category/channel display values, live title, thumbnail, credential, private runtime path, local scheduler evidence, screenshot, raw API response는 local/private boundary에 둔다.

이 contract를 바꾸거나 mapping을 실제 schema/API/runtime semantics로 승격하려면 별도 implementation slice에서 관련 durable docs와 regression tests를 함께 갱신한다.
