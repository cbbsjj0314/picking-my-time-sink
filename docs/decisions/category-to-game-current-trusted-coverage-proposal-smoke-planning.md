# Category-To-Game Current Trusted Coverage / Proposal Smoke Planning Contract

Status: planning contract
Execution target: `CATEGORY-MAPPING-CANDIDATE-REAL-DATA-PROPOSAL-SMOKE-001`
Gate authority: `CATEGORY-MAPPING-REAL-DATA-PROPOSAL-SMOKE-GATE-001`
Date: 2026-10-07 (KST)

## Purpose

이 문서는 Trusted mapping coverage expansion의 첫 slice를 current real-data mapping coverage audit / proposal smoke로 제한하는 canonical planning contract다.

Human-selected direction은 trusted mapping을 바로 추가하는 것이 아니라, 현재 persisted Chzzk observed category population을 기준으로 이미 trusted mapping이 있는 category와 아직 trusted mapping이 없는 category를 구분하고, 아직 trusted하지 않은 category에 existing normalized exact-match semantics를 적용했을 때 review-only `candidate`와 `unresolved`이 어떤 분포를 갖는지 read-only로 측정하는 것이다.

이 문서는 smoke를 실행하지 않는다. Trusted insert, candidate insert, candidate-to-trusted promotion, DB write, API/Web/serving 변경, `Combined` 변경도 수행하거나 승인하지 않는다.

## Authority And Current Repository Evidence

이 contract는 아래 authority를 따른다.

- `docs/decisions/category-to-game-real-data-proposal-smoke-gate.md`의 `CATEGORY-MAPPING-REAL-DATA-PROPOSAL-SMOKE-GATE-001`
- `docs/decisions/category-to-game-mapping-contract.md`
- `docs/data-governance.md`
- current `fact_chzzk_category_30m`, `dim_game`, `srv_chzzk_category_game_mapping` contracts
- existing `src/chzzk/mapping/category_game_candidate_generation.py` exact-match dry-run semantics
- Human-selected current direction: trusted insert보다 current real-data mapping coverage audit / proposal smoke를 먼저 수행한다.

Existing gate는 future `CATEGORY-MAPPING-CANDIDATE-REAL-DATA-PROPOSAL-SMOKE-001`이 explicit read-only command/path를 가진 no-write sanitized smoke로 열리는 것만 허용한다. 이 문서는 그 gate를 확장하지 않고, 해당 future ticket의 exact source, classification, output, validation boundary를 현재 repository state에 맞춰 구체화한다.

Current repository에서 `srv_chzzk_category_game_mapping`은 `mapping_status = 'trusted'`인 `chzzk_category_game_mapping` row만 읽는 internal read-only trusted identity surface다. `Useful Combined v1`을 포함한 current Combined consumers도 이 trusted serving view를 identity input으로 사용한다. 따라서 current trusted membership을 read-only로 분리하는 것은 audit input으로 허용하되, 이 smoke에서 trusted row를 생성·수정·삭제하거나 proposal 결과를 `Combined` input으로 승격하는 것은 금지한다.

## Historical Evidence Note

2026-05의 prior exact-match real-data smoke는 sanitized aggregate evidence로 exact-match proposal signal을 확인했지만, 당시 public evidence는 bounded `/chzzk/categories/overview?limit=200` input과 historical population을 기반으로 했다.

Current code에서도 `/chzzk/categories/overview`와 `GET /chzzk/category-game-mappings`는 각각 최대 `limit=200`이다. Category overview는 aggregate metrics 기준 정렬 뒤 limit을 적용한다. 따라서 이 endpoint들은 현재 persisted observed category universe 또는 trusted mapping universe 전체를 완전하게 partition하는 source로 사용할 수 없다.

이 contract는 historical result를 current result로 재해석하지 않는다. 후속 smoke는 current database snapshot을 새로 읽어 current coverage를 다시 측정한다.

## Decision

Future `CATEGORY-MAPPING-CANDIDATE-REAL-DATA-PROPOSAL-SMOKE-001`은 아래 boundary의 read-only, no-write, sanitized current coverage / proposal smoke로만 실행할 수 있다.

- Chzzk input은 current Postgres `fact_chzzk_category_30m`의 persisted category evidence를 read-only로 사용한다.
- Steam canonical game input은 `dim_game`만 read-only로 사용한다.
- Existing trusted membership은 `srv_chzzk_category_game_mapping`만 read-only로 사용한다.
- 세 source는 하나의 repeatable-read, read-only transaction snapshot에서 읽는다.
- `game_external_id`, `tracked_game` / tracked_universe, App Catalog, candidate table, alias/manual hint source는 읽지 않는다.
- Current trusted category는 proposal matching 대상에서 제외하고 `already_trusted` audit partition으로만 센다.
- Not-currently-trusted category에만 existing normalized exact-match proposal semantics를 적용한다.
- Public output은 sanitized aggregate summary만 허용한다.
- Smoke result는 trusted mapping write/promotion 또는 다음 implementation을 자동 승인하지 않는다.

## Exact Future Command Boundary

후속 execution ticket은 repo-owned bounded runner를 아래 command boundary로 구현하고 실행한다.

```bash
python -m chzzk.mapping.category_game_real_data_proposal_smoke
```

Runner implementation은 `src/chzzk/mapping/category_game_real_data_proposal_smoke.py`에 한정하는 방향을 기본 contract로 삼는다. 필요하면 focused tests를 함께 추가할 수 있다.

Runner는 repository의 existing `POSTGRES_*` environment convention을 사용해 connection을 구성할 수 있다. Credential 또는 `.env` value를 print, log, public artifact에 serialize하지 않는다. Missing authorized DB access를 우회하기 위해 credential을 탐색하거나 다른 host/path를 추측하지 않는다.

Database connection은 실제 source rows를 읽기 전에 read-only와 repeatable-read snapshot을 보장해야 한다. Equivalent psycopg mechanism을 사용할 수 있으나 observable requirement는 아래와 같다.

- transaction은 read-only다.
- 세 approved source read가 하나의 repeatable-read snapshot 안에서 수행된다.
- SQL은 `SELECT`만 수행한다.
- write-capable fallback, temp table, DDL, advisory mutation, insert/update/delete/upsert를 사용하지 않는다.

Authorized database relation은 정확히 아래 세 개다.

- `fact_chzzk_category_30m`
- `dim_game`
- `srv_chzzk_category_game_mapping`

다른 table/view, local file, API response, scheduler output, provider endpoint는 이 smoke의 input authority가 아니다.

## Chzzk Observed Input Boundary

Current observed population은 smoke snapshot 시점에 `fact_chzzk_category_30m`에 persisted evidence가 하나 이상 존재하는 distinct `chzzk_category_id` 전체다.

이 population은 “현재 live 중인 category” 또는 “provider의 complete category universe”를 뜻하지 않는다. Persisted observed universe이며 bounded collection caveat를 유지한다. Recency, `category_type`, bucket coverage, viewer count로 silent filter하지 않는다.

각 category의 adapter input은 current serving/view ordering과 같은 latest-row selection으로 아래 최소 field만 private in-memory evidence로 읽는다.

```sql
SELECT DISTINCT ON (chzzk_category_id)
    chzzk_category_id,
    category_name,
    category_type,
    bucket_time AS latest_bucket_time
FROM fact_chzzk_category_30m
ORDER BY
    chzzk_category_id,
    bucket_time DESC,
    collected_at DESC,
    ingested_at DESC;
```

Allowed semantic use:

- `chzzk_category_id`: observed population identity와 trusted membership partition
- `category_name`: exact normalized proposal comparison
- `category_type`: provider evidence only; identity/filter 근거가 아님
- `latest_bucket_time`: optional aggregate latest observed evidence timestamp 계산

Raw category id/name/type/timestamp row는 public output에 포함하지 않는다.

`/chzzk/categories/overview`는 current endpoint limit 때문에 이 whole-population audit의 input source로 사용하지 않는다. Endpoint behavior를 변경하는 것도 이 ticket 범위가 아니다.

## Steam Canonical Game Input Boundary

Canonical game universe는 current `dim_game` 전체를 아래 최소 field로 read-only 사용한다.

```sql
SELECT
    canonical_game_id,
    canonical_name
FROM dim_game
ORDER BY canonical_game_id ASC;
```

`canonical_name`은 unique key가 아니다. 따라서 normalization 이후 같은 name에 둘 이상의 `canonical_game_id`가 매칭되면 자동 winner를 선택하지 않고 ambiguous `unresolved`로 분류한다.

이 smoke는 아래 source를 사용하지 않는다.

- `game_external_id`
- `tracked_game`
- tracked_universe
- App Catalog
- Steam ranking/price/review/CCU serving source

Raw canonical game id/name row 또는 real game name은 public output에 포함하지 않는다.

## Existing Trusted Mapping Boundary

Current trusted coverage membership은 `srv_chzzk_category_game_mapping`의 category identity만 read-only로 사용한다.

```sql
SELECT chzzk_category_id
FROM srv_chzzk_category_game_mapping
ORDER BY chzzk_category_id ASC;
```

이 view는 current contract상 `mapping_status = 'trusted'`인 storage row만 읽는 trusted identity surface이므로, audit runner가 `chzzk_category_game_mapping`의 provenance 또는 storage internals를 직접 재구성할 필요가 없다.

Observed `chzzk_category_id`가 이 set에 있으면 `already_trusted` audit partition으로 센다. 없으면 `not_currently_trusted` partition으로 센다.

`already_trusted`와 `not_currently_trusted`는 persisted mapping status가 아니다. 이 smoke의 coverage partition label일 뿐이며 `candidate`, `unresolved`, `rejected`, `trusted`의 existing meaning을 변경하지 않는다.

Trusted category는 exact-match proposal builder에 다시 넣지 않는다. 이 smoke는 existing trusted mapping과 latest observed category name 사이의 consistency audit, remap suggestion, demotion suggestion을 수행하지 않는다.

`GET /chzzk/category-game-mappings`는 current endpoint limit 때문에 whole trusted-membership source로 사용하지 않는다.

## Matching And Proposal Semantics

Only `not_currently_trusted` categories enter proposal matching.

Existing builder semantics를 그대로 유지한다. Normalization은 정확히 아래 세 가지다.

- `strip`
- `casefold`
- whitespace collapse

후속 runner가 existing `build_category_game_candidate_dry_run_proposals(...)`를 adapter boundary 뒤에서 재사용할 경우 `alias_hints=None` 또는 동등한 empty input으로 호출해야 한다.

허용하지 않는 matching은 아래와 같다.

- fuzzy matching
- partial matching
- punctuation-insensitive matching
- similarity score
- phonetic/transliteration matching
- automatic alias discovery
- alias matching
- manual hint matching
- inferred/guessed mapping
- automatic mapping
- automatic trusted promotion

Classification은 existing proposal state semantics를 보존하면서 aggregate reporting에서 unresolved reason을 분리한다.

- `candidate`: normalized exact match가 정확히 하나다. Existing untrusted review proposal 의미를 그대로 유지한다.
- `unresolved_no_match`: existing `unresolved` 중 exact match count가 `0`인 aggregate reporting subtype이다.
- `unresolved_ambiguous`: existing `unresolved` 중 exact match count가 `2+`인 aggregate reporting subtype이다.
- `rejected`: 자동 생성하지 않는다.
- `trusted`: current trusted view에서 읽는 existing persisted mapping meaning만 유지하며 proposal output state로 생성하지 않는다.

`unresolved_no_match`와 `unresolved_ambiguous`는 새 persisted status가 아니다.

`category_type=GAME` 또는 다른 category type은 canonical identity evidence가 아니며 silent filtering, priority, promotion 근거로 사용하지 않는다.

## Successful Smoke Invariants

Successful smoke는 source validation error나 partial skip 없이 audited population 전체를 partition해야 한다.

```text
already_trusted_category_count
+ candidate_count
+ unresolved_no_match_count
+ unresolved_ambiguous_count
= observed_input_category_count
```

또한 아래 관계가 성립해야 한다.

```text
already_trusted_category_count
+ not_currently_trusted_category_count
= observed_input_category_count

candidate_count
+ unresolved_no_match_count
+ unresolved_ambiguous_count
= not_currently_trusted_category_count
```

Invalid category/game input, unavailable approved source, transaction consistency failure가 있으면 row를 조용히 skip해서 위 invariant를 맞추지 않는다. Smoke를 failed/blocked로 종료하고 sanitized failure category/count만 public-safe하게 보고한다.

`skipped` class는 successful partition의 정상 상태로 두지 않는다. Future implementation에서 source adapter가 invalid input을 발견하면 partial success로 축소하지 않고 stop condition으로 취급한다.

## Public Aggregate Output Contract

Successful smoke가 public docs/PR/evidence에 남길 수 있는 field는 아래 aggregate에 한정한다.

- result status
- observed input category count
- canonical game input count
- already trusted category count
- not-currently-trusted category count
- exact-match `candidate` count
- unresolved no-match count
- unresolved ambiguous count
- DB write performed: `false`
- candidate insert performed: `false`
- trusted mapping mutation performed: `false`
- latest observed evidence timestamp, 단 `fact_chzzk_category_30m` input의 aggregate max timestamp로만 계산하고 row identity와 함께 노출하지 않는다.

Failure/blocked result는 필요할 때 아래 sanitized field를 추가할 수 있다.

- source availability status
- invalid input count
- sanitized failure reason category

Public artifact에 ratio가 필요하면 위 aggregate count로 계산 가능한 설명만 할 수 있다. 새로운 product KPI, score, ranking 또는 serving metric으로 정의하지 않는다.

Public output에는 아래를 포함하지 않는다.

- real category name/id/type row
- real game name/id row
- category-to-game proposed pair
- existing trusted category-to-game pair
- normalized real label
- raw row
- raw API response
- raw SQL output
- raw command transcript
- raw provider payload
- channel/display name
- live title/thumbnail
- credentials, secret, `.env` value
- private host/path/runtime detail
- scheduler XML/stdout
- raw runtime log
- screenshot
- row-level UGC
- raw Grafana/Prometheus response

Private in-memory row evidence는 proposal classification 계산에만 사용할 수 있고 public artifact로 serialize하지 않는다.

## Validation For The Future Smoke

Future `CATEGORY-MAPPING-CANDIDATE-REAL-DATA-PROPOSAL-SMOKE-001` implementation과 execution은 최소한 아래를 증명해야 한다.

- runner가 approved command/module boundary만 사용한다.
- database access가 repeatable-read, read-only transaction이고 approved three relations에 대한 `SELECT`만 수행한다.
- `/chzzk/categories/overview` 또는 `GET /chzzk/category-game-mappings`의 bounded API result를 whole-universe input처럼 사용하지 않는다.
- `game_external_id`, `tracked_game`, tracked_universe, App Catalog를 읽지 않는다.
- current trusted membership은 `srv_chzzk_category_game_mapping`만 사용하며 storage write/provenance mutation을 하지 않는다.
- trusted categories는 proposal matching에서 제외한다.
- not-currently-trusted categories에만 existing `strip` / `casefold` / whitespace-collapse exact match를 적용한다.
- alias/manual hint input은 사용하지 않는다.
- `category_type=GAME`을 identity/filter로 사용하지 않는다.
- `rejected` 또는 `trusted` proposal status를 생성하지 않는다.
- successful aggregate invariants가 모두 성립한다.
- DB write, candidate insert, trusted mutation이 없음을 확인한다.
- API/Web/serving/`Combined` behavior가 바뀌지 않는다.
- public artifact가 aggregate-only이며 real row/pair/raw/private value를 포함하지 않는다.

Runner implementation이 code를 추가한다면 final code state는 repository canonical `./scripts/check.sh`와 focused regression tests를 통과해야 한다.

## Risk / Review / Human Gate

### This docs-only planning-contract PR

- Risk Level: Medium
- Review Level: Fresh-context
- Human Gate Required: No
- Reason: 이 PR은 code/runtime/data를 변경하거나 smoke를 실행하지 않지만, canonical/trusted identity partition과 public/private real-data evidence boundary를 future execution contract로 고정한다. Fresh-context reviewer가 source completeness, trusted membership, classification/invariant, sanitization boundary를 독립적으로 확인해야 한다.

Human의 Ready/merge 결정은 repository standard PR authority를 따른다. 이 docs-only PR merge 자체는 future live database smoke execution approval이 아니다.

### Future real-data smoke execution

- Risk Level: Medium
- Review Level: Fresh-context
- Human Gate Required: Yes

Human Gate Scope:

```text
Execute CATEGORY-MAPPING-CANDIDATE-REAL-DATA-PROPOSAL-SMOKE-001 against the authorized
current Postgres environment using only the exact read-only/repeatable-read source boundary
defined by this contract, then publish only the sanitized aggregate result.
```

Pre-Gate Allowed Work:

```text
Implement the bounded runner/adapter and focused tests, complete canonical validation/CI,
and complete required Fresh-context review. Do not connect the runner to real/private
Postgres evidence for the smoke until the Human Gate is Approved.
```

Pre-Gate Merge Allowed:

```text
Yes, if the implementation is inert with respect to automatic/runtime execution and all
required validation/review requirements are satisfied. Merge does not authorize execution.
```

Human Gate evidence는 exact execution scope를 승인하는 human-authored GitHub PR comment 또는 GitHub review여야 한다. Existing gate, planning-contract merge, implementation merge, agent completion report, ChatGPT conversation은 real-data execution approval evidence가 아니다.

Authorized read-only DB access가 이미 존재하지 않거나 새 credential/permission/host access가 필요하면 execution을 중단하고 별도 Human authority를 받는다.

Trusted insert, candidate-to-trusted promotion, mapping update/delete 또는 current `Combined` input을 바꾸는 행위는 이 Human Gate에도 포함되지 않는다. 그런 future mutation은 별도의 explicit Human-selected contract와 Human Gate가 필요하다.

## Stop Conditions

Future smoke는 아래 조건 중 하나라도 발생하면 중단한다.

- exact approved command/module boundary 밖의 data access가 필요하다.
- approved three DB relations 이외의 source가 필요하다.
- read-only 또는 repeatable-read transaction을 보장할 수 없다.
- live provider fetch, service start/restart, scheduler action이 필요하다.
- DB write, temp mutation, candidate insert, trusted mapping mutation이 필요하다.
- raw/private row 또는 real category/game pair를 public artifact에 노출해야 진행할 수 있다.
- credential, secret, `.env` value, private path를 inspect/print해야 한다.
- invalid input을 silent skip해야만 result를 만들 수 있다.
- alias/manual hint, fuzzy/partial/punctuation-insensitive/similarity matching이 필요하다.
- `category_type=GAME`을 identity/filter로 사용해야 한다.
- API/Web/serving/`Combined` behavior 변경이 필요하다.
- proposal result를 automatic trusted promotion 근거로 사용해야 한다.
- required Fresh-context review 또는 Human Gate execution evidence가 없다.

## Explicit Non-Goals

이 planning task와 future first smoke는 아래를 승인하지 않는다.

- insert into `chzzk_category_game_candidate`
- insert/update/delete in `chzzk_category_game_mapping`
- candidate-to-trusted promotion
- trusted mapping automatic creation
- DB write
- schema/DDL/migration
- backfill/reingest/bootstrap
- live provider fetch
- scheduler/service/runtime mutation
- API endpoint/response behavior change
- Web behavior change
- serving semantics change
- `Combined` behavior/identity/activity change
- KPI/score/ranking/recommendation change
- fuzzy/inferred/guessed mapping
- alias/manual-hint real-data application
- raw/private evidence publication
- trusted mapping consistency/remap/demotion audit

Smoke 결과가 useful해 보여도 다음 promotion/write step을 자동 승인하지 않는다.

## Acceptance And Next Human Decision

이 contract의 observable success는 future smoke가 aggregate-only evidence로 아래 질문에 답할 수 있는 것이다.

1. Current persisted observed Chzzk category 중 existing trusted mapping으로 덮이는 규모는 얼마인가?
2. 아직 trusted하지 않은 category 중 normalized exact match 하나로 untrusted review `candidate`가 되는 규모는 얼마인가?
3. Exact match가 없거나 ambiguous해서 `unresolved`로 남는 규모는 얼마인가?
4. 이 분포가 human-reviewed trusted promotion workflow를 별도 planning하는 데 충분히 가치 있는가?
5. 아니면 alias/manual review seeding 같은 별도 problem을 먼저 해결해야 하는가?

이 contract는 4 또는 5의 결론을 미리 정하지 않는다.

Future smoke 실행 전에 Human이 별도로 해야 하는 결정은 exact Human Gate scope를 human-authored GitHub comment/review로 승인하는 것이다. 실행 환경에는 이미 authorized read-only Postgres access가 있어야 한다. 새 access provision이 필요하면 그 access approval은 별도 authority다.
