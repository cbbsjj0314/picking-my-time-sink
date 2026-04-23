문서 목적: source별 probe 체크리스트, schema/parser/test 기준점, provider 확장 진입 기준 기록
버전: v0.13 (public 한국어 톤 정리)
최종 수정일: 2026-04-24 (KST)

## 0. 공통 원칙

- 실패/빈값/429는 “발생할 수 있다”를 전제로 하고, 재시도/백오프/관측 로그를 남긴다.
- public에는 sanitized fixture와 durable contract만 남긴다. raw capture, UGC-heavy payload, credential, 내부 운영 절차, exact local schedule은 local/private에 둔다.
- 스트리밍 확장은 첫 provider-specific source probe/ingest 후보를 좁혀 시작한다. Chzzk/Twitch 공통 인터페이스나 generalized provider abstraction은 실제 provider probe가 안정화된 뒤 별도 slice에서 검토한다.
- Source-level data governance boundary는 `docs/data-governance.md` 를 따른다. Public source docs에는 endpoint shape, field meaning, cadence, null/error semantics를 남기고, raw provider response와 live runtime evidence는 local/private로 둔다.

### 0.1 Provider boundary (현재 repo 기준)

- 문서 기준:
    - 현재 runtime scope는 Steam-only 이다.
    - streaming 확장은 provider-specific source probe/ingest에서 시작한다. Steam service/API 범위를 먼저 일반화하지 않는다.
- 현재 repo 관찰:
    - 현재 repo에는 Chzzk live-list parser fixture
      `tests/fixtures/chzzk/lives/representative.json`, parser/upsert 후보
      `src/chzzk/normalize/category_lives.py`, DDL 후보
      `sql/postgres/015_fact_chzzk_category_30m.sql` 이 있다.
    - Chzzk real runtime package, scheduler job, API serving, UI wiring은 없다.
    - Twitch probe 산출물, runtime package, DDL은 없다.
    - 외부 ID 연결의 현재 grounded contract는 `game_external_id.source` 이며, tracked provenance는 `tracked_game.sources` 에 기록된다.
- 첫 provider-specific probe/ingest 후보:
    - 첫 후보는 Chzzk category live-list probe 준비다.
    - source boundary는 Chzzk live/category payload에서 category type/id/name, live concurrent, channel id/name만 category-level evidence로 읽는 데 한정한다.
    - category evidence는 browser 후보로만 해석한다. `categoryType=GAME` 이 있어도 canonical game semantics, Steam mapping, API/UI column, Combined semantics로 확장하지 않는다.
    - category-level 30분 fact 방향은 `(chzzk_category_id, bucket_time)` 단위의 category type/name, concurrent 합계, live_count, top channel evidence다.
    - sanitized parser fixture는 `tests/fixtures/chzzk/lives/` 아래에 고정한다.
    - 현재 fixture는 official live-list response shape를 대표하는 synthetic/sanitized payload이며, live raw capture가 아니다.
    - raw/probe 책임은 provider 응답과 수집 메타데이터를 local/private 경계에 보존하는 것이다.
    - ingest 책임은 한 provider payload를 category 30분 row로 정규화하는 데 그친다. canonical game mapping, serving API, UI wiring, Combined semantics는 만들지 않는다.
- real integration 전 필요 조건:
    - Chzzk live-list temporal coverage와 category-missing behavior 추가 확인
    - local-only raw-to-category result artifact contract 확정
    - secrets는 환경 변수로 주입하고 토큰/쿠키/개인 헤더를 fixture, 로그, 문서에 저장하지 않는 운영 규칙 확정
    - `fact_chzzk_category_30m` 후보 DDL, parser fixture test, idempotent upsert test를 같은 thin slice에서 추가
    - category-to-game mapping workflow와 Twitch fallback 여부는 별도 slice에서 결정
- 명시적 비범위:
    - scheduled real Chzzk API 호출, Twitch 구현, provider abstraction layer, streaming serving API, web dashboard streaming UI wiring, Combined/relationship KPI

## 1. Steam (MVP 핵심)

### 1.1 App Catalog (전체 appid 카탈로그)

- 목적: 전체 appid/메타 변경 감지의 기준. details는 “추적 대상(tracked)”만.
- 엔드포인트: IStoreService/GetAppList
- 인증: Steam Web API Key 필요(사용자가 발급)
- 주기: 주 1회(기본) + 필요 시 증분(변경분만)
- 주요 키/필드(예상): appid, last_modified, price_change_number(있을 경우)
- 실패/주의:
    - 페이지네이션(대량 결과) 처리 필요
    - 결과 필드/형식은 실제 probe로 확정
    - 네트워크/일시 오류 시 재시도, 중간 체크포인트(last_appid 등) 필요
- 현재 repo 기준 resume/output 우선순위:
    - checkpoint가 `in_progress` 이면 checkpoint의 `snapshot_path`를 resume 대상으로 재사용하며, explicit `--output-path` 보다 우선한다.
    - checkpoint가 `completed` 이거나 checkpoint가 없으면 fresh start 이며, explicit `--output-path` 가 있으면 그 경로에 새 snapshot을 쓰고 없으면 timestamped default path를 사용한다.
    - fresh start에서 explicit `--output-path` 가 기존 completed snapshot과 같은 경로여도 첫 요청 전에 빈 JSONL로 즉시 다시 쓰며, single-page terminal fetch는 그 fresh snapshot을 `completed`로 마감한다.
- 현재 repo 기준 runtime latest summary:
    - successful weekly fetch는 resumable JSONL snapshot과 별도로 local/private latest summary JSON을 갱신한다.
    - latest summary top-level contract는 `job_name`, `status`, `started_at_utc`, `finished_at_utc`, `snapshot_path` 이다.
    - downstream consumer contract는 `response.payload_excerpt_or_json` 아래의 `app_count`, `pagination`, `top_level_keys`, `apps_excerpt` 요약 shape를 재사용한다.
    - `update_tracked_universe.py` 와 `run_tracked_universe_scheduled.py` 의 optional consumer default는 위 latest summary path를 사용하며, 파일이 없거나 읽기 실패여도 non-blocking 으로 건너뛴다.
    - `update_tracked_universe.py` 의 현재 thin-slice consumer rule은 `pagination.have_more_results = false` 인 completed summary만 신뢰하고, 그 `snapshot_path` JSONL에 없는 ranking seed appid는 `tracked_game.is_active = false` 로 upsert 한다.
    - shared object boundary가 필요할 때도 현재 consumer entrypoint는 위 latest summary를 그대로 유지한다. Shared key/object inventory rule은 `docs/decisions/garage-shared-artifact-contract.md` 를 따른다.
    - shared read-only reuse에서 summary가 가리키는 run-scoped snapshot object는 `tmp/steam/jobs/app-catalog-weekly/{run_id}/app_catalog.snapshot.jsonl` 에 대응하는 S3-compatible key로만 노출한다.
    - local/mock shared replay smoke는 `src/steam/ingest/shared_artifact_replay.py` 에서 writer가 latest manifest/summary entrypoint를 publish하고 read-only consumer가 같은 entrypoint를 reread하는 단일 경로로 고정한다.
    - 현재 remote portable-cache path는 `src/steam/ingest/shared_artifact_store.py` 에서 같은 latest manifest/latest summary entrypoint를 S3-compatible object storage로 publish/download 한다.
    - 현재 object-store config parsing and signing boundary는 `src/steam/ingest/s3_compat.py` 이며, bucket-local prefix가 있더라도 published manifest/summary의 portable `object_key` shape는 유지한다.
    - downloaded cache는 same object-key layout under one local cache root를 유지하므로 existing replay readers가 별도 adapter 없이 그대로 reread 한다.
    - App Catalog latest summary는 현재 runtime에서 optional local/private artifact다. external weekly scheduling 운영화는 아직 현재 baseline에 포함하지 않는다.
    - 현재 ranking seed에서 사라진 기존 tracked row와 오래 관측되지 않은 tracked row는 App Catalog consumer가 자동 deactivate/delete 하지 않는다.
    - `tracked_game.last_seen_at` 은 staleness lifecycle timer가 아니며, 현재 price/reviews/ccu fetch cadence는 `tracked_game.is_active = true` 여부만 따른다.

### 1.2 CCU (동접)

- 목적: “살아있나/뜨나” 핵심 지표(30분)
- 엔드포인트: ISteamUserStats/GetNumberOfCurrentPlayers
- 인증: (원칙) Key 없이도 동작 가능하나, 운영 일관성 위해 키 포함 호출도 허용
- 주기: 30분(00/30)
- 입력 키: steam_appid
- 주요 필드(예상): player_count
- 실패/주의:
    - 404/빈 응답/일시 실패 가능 → 재시도 + 해당 버킷 누락 표시
    - 레이트리밋/429 가능성 → 지수 백오프 + jitter, 필요 시 appid 배치 크기 조절

### 1.3 Reviews (리뷰 스냅샷)

- 목적: “살 만한가” 지표(1일 스냅샷)
- 엔드포인트: Steam Store Reviews (appreviews)
- 인증: 보통 Key 불필요
- 주기: daily
- 입력 키: steam_appid
- 현재 repo 기준 request params:
    - `json=1`
    - `filter=all`
    - `language=all`
    - `purchase_type=all`
    - `num_per_page=20`
- 주요 필드(예상):
    - query_summary: total_reviews, total_positive, total_negative 등
    - (선택) 리뷰 텍스트/태그 분류는 MVP 이후 단계로 둔다(비용/용량 이슈)
- 현재 metric contract:
    - `query_summary` cumulative totals를 all languages / all purchases / all reviews canonical daily snapshot으로 적재한다.
    - 현재 gold fact에는 위 request-param provenance 컬럼이 없으므로, 여러 review series를 병렬 보존해야 하면 schema/ingest 확장이 필요하다.
- 실패/주의:
    - 대량 호출 시 차단/429 가능 → tracked 대상만, 백오프 필수
    - 언어/필터 조건은 위 현재 request params로 고정한다.

### 1.4 Price (가격/할인)

- 목적: “구매 타이밍(할인+모멘텀)” 및 가격 변동
- 엔드포인트: Steam Store appdetails (price_overview)
- 인증: 보통 Key 불필요(스토어 엔드포인트)
- 주기: 1시간(정시), MVP는 KR만
- 입력 키: steam_appid + region(cc=kr)
- 주요 필드(예상): currency, initial, final, discount_percent
- 실패/주의:
    - 스토어 엔드포인트는 공식 Web API보다 정책 변화 가능 → probe 샘플 고정 및 회귀 테스트 필요
    - 무료/미판매/지역 미지원 등 다양한 edge case → NULL 정책 사전 정의

### 1.5 Ranking (랭킹 스냅샷)

- 목적: 추적 대상 유니버스(seed) 생성 + “오늘의 상위 게임”
- 소스:
    - `IStoreTopSellersService/GetWeeklyTopSellers/v1`
    - `ISteamChartsService/GetGamesByConcurrentPlayers/v1`
- 범위: KR + global 둘 다 저장
- 주기: daily
- runtime artifact:
    - ranking refresh는 top sellers global, top sellers KR, most played global, most played KR 4종 local/private payload를 쓴다.
- 출력 필드(예상): rank_type, rank_position, steam_appid(또는 추출된 appid), snapshot_market(KR/global)
- 실패/주의:
    - runtime은 fixture-compatible JSON payload contract를 사용하고, legacy HTML behavior는 sanitized fixture로만 회귀 테스트한다.
    - payload fetch 실패/빈 ranks 시: tracked_universe seed 갱신 중단 + 알림/리트라이

## 2. Chzzk (첫 provider-specific probe/ingest 후보; real integration 미착수)

### 2.1 Live 목록

- 목적: category-level 시청/방송/Top streamer 집계 후보 원천
- 엔드포인트: `GET https://openapi.chzzk.naver.com/open/v1/lives`
- 요청 파라미터:
    - `size`: optional, 1-20, default 20
    - `next`: optional pagination cursor from `page.next`
- 인증:
    - 공식 문서는 애플리케이션 등록 후 `Client-Id` / `Client-Secret` 기반 Client 인증이 필요하다고 설명한다.
    - credential은 환경 변수 또는 secret manager로 주입한다. public fixture, 로그, 문서에는 저장하지 않는다.
    - quota limit은 아직 public contract가 아니다. 공식 공통 에러 문서는 `429 TOO_MANY_REQUESTS` 를 quota 제한 초과로 둔다.
- 응답 형태 기준:
    - wrapper 후보: `code`, `message`, `content.data`, `content.page.next`
    - public parser fixture는 official response shape를 대표하는 synthetic/sanitized payload만 사용한다.
    - 현재 parser fixture는 `categoryType`, `liveCategory`, `liveCategoryValue`, `concurrentUserCount`, `channelId`, `channelName` 만 사용한다.
    - `adult`, `channelImageUrl`, `liveThumbnailImageUrl`, `liveTitle`, `openDate`, `tags` 같은 UGC-heavy/provider raw field는 public fixture에 원문으로 보존하지 않는다.
- 주기 방향: real ingest가 생기면 30분(00/30) bucket으로 정규화한다.
- 주요 필드 후보:
    - `categoryType`: `GAME`, `SPORTS`, `ENTERTAINMENT`, `ETC`
    - `liveCategory`: 카테고리 식별자
    - `liveCategoryValue`: 카테고리 이름
    - `concurrentUserCount`: 라이브 현재 시청자 수
    - `channelId`: 채널 식별자
    - `channelName`: 채널명
- 파생 집계(카테고리 단위):
    - concurrent 합(또는 평균), 방송 수, top streamer(최대 concurrent)
- 실패/주의:
    - 인증/쿼터/필드 안정성이 미확정이다.
    - 빈 category id/name/type row를 synthetic unknown category로 채우지 않는다.
      category-level fact 후보에서는 skip evidence로 남긴다.
    - local/private probe artifact contract는 strict parser result와 probe reporting을 분리한다.
    - `category-result.jsonl` 은 category-fact-eligible live row만 모은 strict candidate result다.
    - `summary.json` / `temporal-summary.json` 은 `run_status`, `result_status`, `pagination.bounded_page_cutoff`, `pagination.last_page_next_present`, `skip_counts`, `skip_evidence.blank_category_page_indexes`, `coverage.status` 로 skip/pagination/coverage caveat를 설명한다.
    - quota/HTTP failure, request error, invalid JSON, malformed page, partial fetch는 local/private `failure.kind`, `failure.http_status_code`, `failure.page_index` 수준으로만 요약하고 category result는 생성하지 않는다.
    - bounded probe는 full live-list population이나 pagination exhaustion 근거가 아니다.
    - category result는 evidence browser 후보로만 읽는다. category-to-game mapping, API/UI column semantics, Combined semantics는 이 source inventory에서 열지 않는다.
    - real integration 전 raw capture는 local/private에 두고 parser regression은 sanitized fixture로 먼저 고정한다.
    - API 실패 시의 재시도/알림은 Chzzk-specific runtime slice에서 구현한다.
    - public fixture는 synthetic/sanitized payload만 둔다. live title, channel name, thumbnail URL 같은 raw UGC/provider response는 public에 그대로 남기지 않는다.

### 2.2 Category 검색 (매핑 보조)

- 목적: Chzzk 카테고리 ↔ Steam 게임명 후보 추천에 활용할 수 있는 보조 source
- 엔드포인트 후보: GET /open/v1/categories/search
- 인증: 미확정
- 상태: first probe/ingest slice에는 포함하지 않는다. 수동 매핑 workflow가 필요해질 때 별도 slice에서 검토한다.
- 실패/주의: 검색 결과 품질/중복/별칭이 많을 수 있어 자동 확정 금지

## 3. Twitch (fallback candidate, 미착수)

- 목적: Chzzk가 막히는 경우 동일한 지표(시청/방송/Top) 제공
- 상태: 미착수(TBD). Chzzk-specific probe 결과가 막혔을 때 별도 source inventory/probe slice에서 검토한다.
- 현재 rule: Twitch 때문에 먼저 generalized provider interface를 만들지 않는다.

## 4. Probe 산출물(샘플 JSON) 저장 규칙

- 저장 기준:
    - raw JSON/HTML capture와 provider 응답 원문성 자료는 ignored `data/local/probe/<provider>/...` 아래에 둔다.
    - 문서, 판단 메모, 스캔 결과, local 실행 기록은 `docs/local/` 아래에 둔다.
    - parser/ingest regression이 의존하는 입력은 local/ignored 경로가 아니라 `tests/fixtures/<provider>/...` 아래의 최소 sanitized fixture로 둔다.
    - public docs에는 endpoint shape, field meaning, cadence, null/error semantics 같은 durable contract만 둔다.
- 샘플 파일 기준:
    - public fixture에는 인증 토큰, 쿠키, 개인 식별 헤더, UGC 원문, raw HTML excerpt, 내부 운영 detail을 저장하지 않는다.
    - ambiguous한 probe 산출물은 public에 둘 근거가 명확해질 때까지 local/private first로 둔다.

## 5. 공통 실패 처리 정책(초안)

- 429/timeout:
    - 지수 백오프 + jitter
    - retry 횟수 상한 + 쿨다운
- 빈값/누락:
    - “NULL 허용 컬럼”과 “NULL이면 실패 처리 컬럼”을 구분(데이터 계약 문서로 분리 가능)
- 파서 오류:
    - 샘플 고정 + 회귀 테스트로 구조 변경 조기 감지
