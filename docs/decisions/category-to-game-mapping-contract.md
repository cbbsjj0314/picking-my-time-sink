# Category-To-Game Mapping Contract

Status: docs-only planning boundary  
Date: 2026-05-17 (KST)

이 문서는 Chzzk category observed evidence를 Steam canonical game에 연결하기 위한 첫 planning boundary를 고정한다.
이 결정은 schema, API, runtime, loader, scheduler, web, DB write, 또는 Combined semantics 구현 승인이 아니다.

현재 durable context는 `README.md`, `docs/source-inventory.md`, `docs/data-model-spec.md` 를 따른다.

## Purpose

목적은 Chzzk category와 Steam canonical game 사이의 연결을 어떻게 시작할지 정하는 것이다.

첫 boundary는 "자동 매핑"이 아니라 "review 가능한 mapping 후보와 판단 기록"이다.
Chzzk category evidence는 canonical game identity가 아니며, 사람이 검토하거나 검토 가능한 workflow를 거치기 전에는 trusted game mapping으로 쓰지 않는다.

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
- ambiguous alias, renamed category, regional title, franchise collision, same-name collision은 자동 확정하지 않고 unresolved 상태로 남긴다.
- mapping이 trusted semantics로 사용되기 전에는 reviewer/operator가 검토할 수 있는 evidence와 note가 있어야 한다.

Future implementation slice에서 검토할 metadata candidates:

- `mapping_status`
- `mapping_method`
- `confidence`
- `evidence`
- reviewer/operator note
- created/updated/reviewed timestamps

위 항목은 후보일 뿐이며, 이 문서는 column name, JSON shape, table grain, API field, 또는 UI field를 확정하지 않는다.

## Success Criteria For Later Slices

나중에 implementation slice를 열려면 아래 조건을 먼저 만족해야 한다.

- mapping은 trusted 상태로 쓰이기 전에 review 가능해야 한다.
- ambiguous alias/collision은 guessed mapping이 아니라 unresolved 상태로 남아야 한다.
- Chzzk `categoryType=GAME` 은 canonical game identity로 취급하지 않아야 한다.
- Combined view는 mapping contract와 serving semantics가 별도 승인될 때까지 blocked 상태로 남아야 한다.

## Explicit Non-Goals

이번 slice에서는 아래 작업을 하지 않는다.

- schema, SQL, migration, model, API, web, loader, scheduler, runtime behavior 변경
- DB write, backfill, reingest, bootstrap, DDL
- live Chzzk fetch
- category search API probe unless separately approved
- Combined semantics
- `gold_stream_game_30m`
- generalized provider abstraction
- automatic category-to-game matching
- raw provider payloads, UGC, credentials, private paths, local scheduler evidence, screenshots, raw API responses를 public docs에 추가

## Public Boundary

Public docs에는 durable planning contract만 둔다.
Mapping 판단의 근거가 되는 raw provider response, category/channel display values, live title, thumbnail, credential, private runtime path, local scheduler evidence, screenshot, raw API response는 local/private boundary에 둔다.

이 contract를 바꾸거나 mapping을 실제 schema/API/runtime semantics로 승격하려면 별도 implementation slice에서 관련 durable docs와 regression tests를 함께 갱신한다.
