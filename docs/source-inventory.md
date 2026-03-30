문서 목적: probe(샘플 검증) 실행 체크리스트 + 이후 스키마/파서/테스트의 기준점 + repo-grounded provider 확장 진입 기준 기록
버전: v0.2 (provider-boundary 정리 반영)
작성일: 2026-03-28 (KST)

## 0. 공통 원칙

- 실패/빈값/429는 “발생할 수 있다”를 전제로 하고, 재시도/백오프/관측 로그를 남긴다.
- 프로브 산출물(샘플 JSON)은 리포지토리에 고정 저장해 “회귀 테스트” 기준으로 사용한다.
- Chzzk가 인증/호출 안정성 측면에서 막히면 Twitch로 전환 가능하도록, 스트리밍 수집은 Provider 인터페이스를 분리한다.

### 0.1 Provider boundary (current repo-grounded)

- durable doc facts:
    - current runtime scope는 Steam-only 이다.
    - streaming 확장은 provider-specific source probe/ingest에서 시작하고, Steam service/API 범위를 먼저 일반화하지 않는다.
- current repo observations:
    - 현재 repo에는 Chzzk/Twitch probe 산출물, runtime package, DDL이 없다.
    - 외부 ID 연결의 현재 grounded contract는 `game_external_id.source` 이며, tracked provenance는 `tracked_game.sources` 에 기록된다.
- still undecided items:
    - Chzzk auth/쿼터/필드 안정성
    - Chzzk vs Twitch 중 실제 첫 구현 provider
    - provider-specific raw/category fact 이후의 generalized serving/API shape

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
- current repo-grounded resume/output precedence:
    - checkpoint가 `in_progress` 이면 checkpoint의 `snapshot_path`를 resume 대상으로 재사용하며, explicit `--output-path` 보다 우선한다.
    - checkpoint가 `completed` 이거나 checkpoint가 없으면 fresh start 이며, explicit `--output-path` 가 있으면 그 경로에 새 snapshot을 쓰고 없으면 timestamped default path를 사용한다.
    - fresh start에서 explicit `--output-path` 가 기존 completed snapshot과 같은 경로여도 첫 요청 전에 빈 JSONL로 즉시 다시 쓰며, single-page terminal fetch는 그 fresh snapshot을 `completed`로 마감한다.

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
- 주기: 1일 1회(03:20 KST)
- 입력 키: steam_appid
- 주요 필드(예상):
    - query_summary: total_reviews, total_positive, total_negative 등
    - (선택) 리뷰 텍스트/태그 분류는 MVP 이후 단계로 둔다(비용/용량 이슈)
- 실패/주의:
    - 대량 호출 시 차단/429 가능 → tracked 대상만, 백오프 필수
    - 언어/필터 조건은 probe에서 최소 옵션 확정

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
- 소스: Steam Charts(웹 페이지 파싱)
- 범위: KR + global 둘 다 저장
- 주기: 1일 1회(03:10 KST)
- 출력 필드(예상): rank_type, rank_position, steam_appid(또는 추출된 appid), snapshot_market(KR/global)
- 실패/주의:
    - HTML 구조 변경 가능 → 파서 회귀 테스트 필수
    - 파싱 실패 시: 이전 스냅샷 유지 + 알림/리트라이

## 2. Chzzk (MVP에서는 “가능하면”, 실패 시 Twitch로 대체)

### 2.1 Live 목록

- 목적: 카테고리(게임)별 시청/방송/Top streamer 집계의 원천
- 엔드포인트: GET /open/v1/lives
- 인증: (미확정) Client 인증/토큰 필요 가능성 있음 → probe로 확정
- 주기: 30분(00/30)
- 주요 필드(예상): concurrentUserCount, liveCategory(카테고리 정보), channelId, channelName
- 파생 집계(카테고리 단위):
    - concurrent 합(또는 평균), 방송 수, top streamer(최대 concurrent)
- 실패/주의:
    - 인증/쿼터/필드 안정성이 미확정 → Provider 전환 가능하도록 설계
    - API 실패 시: 해당 버킷 누락 처리 + 재시도 + 알림

### 2.2 Category 검색 (매핑 보조)

- 목적: Chzzk 카테고리 ↔ Steam 게임명 후보 추천에 활용
- 엔드포인트: GET /open/v1/categories/search
- 인증: (미확정)
- 주기: 주 1회 + 수동 보정 작업 시 사용(상시 수집은 불필요)
- 실패/주의: 검색 결과 품질/중복/별칭이 많을 수 있어 자동 확정 금지

## 3. Twitch (대체 Provider, 2단계 확장)

- 목적: Chzzk가 막히는 경우 동일한 지표(시청/방송/Top) 제공
- 상태: 미착수(TBD). Provider 인터페이스만 먼저 정의하고, 실제 엔드포인트/인증은 도입 시점에 인벤토리 확장.

## 4. Probe 산출물(샘플 JSON) 저장 규칙

- 저장 위치(권장):
    - docs/probe/steam/getapplist_YYYYMMDD.json
    - docs/probe/steam/ccu_30m_sample.json
    - docs/probe/steam/appreviews_daily_sample.json
    - docs/probe/steam/appdetails_price_kr_sample.json
    - docs/probe/steam/charts_rank_kr_global_sample.html(or.json)
    - docs/probe/chzzk/lives_30m_sample.json
- 샘플 파일에는 다음 메타를 함께 기록:
    - 수집 시각(KST), 요청 파라미터, 응답 HTTP 코드, 레이트리밋 관련 헤더(있다면), 실패 시 에러 바디

## 5. 공통 실패 처리 정책(초안)

- 429/timeout:
    - 지수 백오프 + jitter
    - retry 횟수 상한 + 쿨다운
- 빈값/누락:
    - “NULL 허용 컬럼”과 “NULL이면 실패 처리 컬럼”을 구분(데이터 계약 문서로 분리 가능)
- 파서 오류:
    - 샘플 고정 + 회귀 테스트로 구조 변경 조기 감지
