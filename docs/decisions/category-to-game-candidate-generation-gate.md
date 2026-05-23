# Category-To-Game Candidate Generation Gate

Status: implementation gate
Ticket: CATEGORY-MAPPING-CANDIDATE-GENERATION-GATE-001
Approved: 2026-05-23 (KST)
Documented: 2026-05-24 (KST)

## Purpose

이 문서는 category-to-game candidate generation의 첫 implementation boundary를 고정한다.

기존 `chzzk_category_game_candidate` storage foundation은 review-only 후보 저장소이며,
candidate generation, automatic matching, trusted mapping, serving semantics, 또는
`Combined` semantics를 승인하지 않았다. 이 gate는 그 다음 implementation step을
DB-write-free synthetic/test-only dry-run proposal builder로만 제한한다.

## Decision

First implementation may proceed only as a DB-write-free synthetic/test-only dry-run
proposal builder.

이 결정은 real observed-data candidate generation, DB write, API/web exposure,
serving semantics, trusted mapping, promotion/demotion workflow, 또는 `Combined`를
열지 않는다.

## First Implementation Scope

- 입력은 synthetic/test-only input만 허용한다.
- DB write는 disabled 상태여야 한다.
- real observed Chzzk data read는 하지 않는다.
- API, DB, runtime, service, scheduler access는 하지 않는다.
- `chzzk_category_game_candidate`에 candidate row를 insert하지 않는다.

## Input Contract

- Chzzk-side synthetic input은 future real row adapter가 붙을 수 있는 generic
  dataclass/list-style shape로 둔다.
- Steam-side synthetic input은 future `dim_game`-like row adapter가 붙을 수 있는
  generic dataclass/list-style shape로 둔다.
- fixture와 docs에는 real category, channel, display, 또는 game name을 쓰지 않는다.
- `game_external_id`, tracked_universe, App Catalog, provider-specific raw payload는
  input으로 쓰지 않는다.

## Normalization Rule

Allowed normalization은 아래 세 가지뿐이다.

- `strip`
- `casefold`
- whitespace collapse

아래 matching technique은 허용하지 않는다.

- fuzzy matching
- alias matching
- partial matching
- similarity score
- manual hints

## Classification Rule

- `candidate`: normalized exact match count가 정확히 1개일 때만 생성한다.
- `unresolved`: normalized exact match count가 0개이거나 2개 이상일 때 생성한다.
- `rejected`: dry-run builder가 자동 생성하지 않는다. Human review workflow를 위한
  later state로 예약한다.

`candidate`, `unresolved`, `rejected`는 모두 untrusted review evidence state다.
`trusted` / `approved`는 future Human Gate terminology로만 남긴다.

`category_type=GAME`은 provider category type evidence이지 canonical identity
evidence가 아니다. Dry-run output에서 non-identity caveat/counter로 보고할 수는
있지만, canonical game identity를 만들 수 없고 future explicit decision 없이
candidate를 조용히 filter하는 precondition으로 쓰면 안 된다.

## Output Boundary

- Output은 dry-run proposal output only다.
- DB insert는 하지 않는다.
- API/web response shape를 정의하지 않는다.
- Serving semantics를 정의하지 않는다.
- `Combined` semantics를 정의하지 않는다.
- Output은 aggregate/synthetic data만으로 test 가능해야 한다.

## Explicit Non-Goals

이 gate는 아래 항목을 승인하거나 정의하지 않는다.

- real observed-data candidate generation
- DB write
- write workflow
- automatic matching
- fuzzy matching
- alias matching
- partial matching
- similarity scoring
- manual hints
- trusted mapping
- promotion/demotion workflow
- `game_external_id` use
- tracked_universe use
- App Catalog use
- API/web exposure
- serving semantics
- `Combined`

## Next Ticket

Recommended next ticket:

`CATEGORY-MAPPING-CANDIDATE-GENERATION-DRY-RUN-001`

다음 ticket은 synthetic/test-only dry-run proposal builder를 구현한다. Required tests는
exact match, no match, ambiguous match, normalization, `category_type=GAME`
non-identity caveat/counter, silent filter 없음, and no leakage into API/web/serving/
`Combined`를 포함해야 한다.

## Deferred Items

- real observed-data read-only proposal smoke
- candidate write smoke
- promotion/demotion workflow
- trusted mapping
- API/web exposure
- serving semantics
- `Combined`

## Public / Private Safety

Public docs와 fixtures에는 durable contract와 synthetic examples만 둔다.

아래 항목은 public docs, fixtures, PR text에 포함하지 않는다.

- real category/channel/display values
- real game names
- live titles
- thumbnails
- row-level UGC
- raw provider payload
- raw API response
- raw SQL output
- raw command transcript
- credential, secret, `.env` value
- private path
- scheduler XML/stdout
- raw runtime logs
- screenshots
- raw Grafana/Prometheus responses
