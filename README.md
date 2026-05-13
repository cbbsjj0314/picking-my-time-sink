# Picking My Time Sink

Steam과 Chzzk의 데이터를 수집하여 "지금 어떤 게임에 시간을 쓰거나 구매할 만한가"를 판단하기 위해 구축한 MVP 형태의 대시보드(evidence dashboard)다.

현재는 Steam 전용 데이터를 기반으로 사용 가능한 베이스라인(Steam-only usable baseline)을 구축하는 데 집중하고 있으며, Chzzk 데이터는 관측된 지표(observed source evidence)와 소스 뷰 확장(source-view expansion)을 단계적으로 연동하고 있다.

로컬 및 프라이빗 운영 데이터, API 제공자의 raw payload, 인증 정보(credentials), 호스트 및 경로의 세부 정보, 스케줄러의 XML/stdout, 행 수준의 사용자 생성 콘텐츠(UGC)는 저장소에 포함하지 않는다.

## 현재 구현 범위

### Steam-only Baseline

Steam-only baseline은 현재 레포지토리에서 실제 사용 가능한 주요 베이스라인이다.

Steam source view, API, 그리고 serving view를 연결하여 누구나 읽기 전용으로 데이터를 탐색할 수 있는 브라우저 형태로 제공하는 것을 목표로 했으며, 현재 다음과 같은 흐름이 구현되어 있다.

* Steam provider 데이터 수집 및 주기별 데이터 적재(cadence-specific ingestion) 구현
* 추적 대상인 Steam 게임 목록(tracked Steam universe) 유지
* rankings, CCU, price, reviews 데이터 적재 및 정규화(normalization) 수행
* Postgres serving view 및 FastAPI 기반의 읽기 전용 endpoint 제공
* 웹 source view에서 `Explore` 및 `Top Selling` 모드 구현
* null, warmup, missing, free-price 등의 데이터 상태를 임의의 값(fake fallback)으로 덮어쓰지 않고 있는 그대로 표시하는 UI 구현

Steam `Explore` 모드는 `/games/explore/overview` API를 중심으로 현재 CCU, 최근 7일 지표, 관측된 누적 플레이 시간(player-hours), 리뷰 증감 추이, 가격 데이터를 한 화면에서 비교할 수 있도록 제공한다.

`Top Selling` 모드는 현재 Steam의 주간 최고 판매량(weekly top sellers) 스냅샷을 기준으로 데이터를 제공한다.

### Chzzk Implemented Evidence

Chzzk 데이터는 아직 Steam baseline처럼 완성된 형태의 프로덕트 베이스라인으로 제공하지 않는다.

현재 구현된 데이터 수집 및 제공 범위는 다음과 같이 제한된다.

* Chzzk 카테고리 관측 데이터(observed facts)
* Chzzk 카테고리별 채널 관측 데이터
* 읽기 전용 관측 소스 API: `/chzzk/categories/overview`
* 쓰기 방어(guarded-write)가 적용된 로컬 수집 파이프라인 관측

`/chzzk/categories/overview` endpoint는 카테고리 단위로 샘플링된 관측 지표를 반환한다.

채널 데이터는 카테고리 관측 주기(observed bucket)와 일치할 경우에 한해, `unique_channels_observed`와 같은 nullable 지표를 보강하는 용도로만 사용된다.

이 API는 provider의 raw payload, 채널명, 방송 제목, 썸네일, 인증 정보, Steam 데이터와의 매핑 정보, 통합 필드(combined fields)를 노출하지 않는다.

데이터 수집 경로(guarded-write collection path)는 로컬 스케줄러 환경에서 실제 실행을 통한 관측(observation)으로 검증을 마쳤다.

공개된 README에서는 이를 "제한적인 로컬 운영 관측(bounded local operational observation)이 진행된 수집 경로"로만 요약하며, 스케줄러의 raw 데이터나 프라이빗 런타임의 세부 구현은 공개하지 않는다.

### Chzzk Source-View Expansion

Chzzk source view는 현재 개발이 진행 중인(work in progress) 영역이다.

API 및 웹의 일부 단위 기능(slice)은 검증을 마쳤으나, Steam-only baseline 수준의 완성된 사용 가능 베이스라인으로 간주하지는 않는다.

현재 의미 있는 성과는 Chzzk 카테고리 테이블이 관측된 지표를 읽어오고, 제한된 샘플링으로 인한 주의점(bounded sample caveat)과 데이터 수집 범위(coverage status)를 명확히 분리하여 보여주는 방향성을 검증했다는 점이다.

정기 수집(regular collection)의 안정화, source view의 완성, 그리고 카테고리와 게임 간의 매핑(category-to-game mapping)은 향후 과제(future work)로 남겨두었다.

## Architecture

현재 MVP의 아키텍처는 거대한 플랫폼을 구축하기보다, 작지만 확실히 검증 가능한 수직적 기능 단위(vertical slice)를 구현하는 데 우선순위를 둔다.

* **Collectors / probes**: Steam의 ranking, CCU, price, reviews 데이터 수집과 Chzzk의 라이브 목록 및 카테고리 데이터 탐색(probe)을 담당한다.
* **Loaders / write paths**: provider의 아티팩트(artifacts)를 bronze/silver/gold 계층이나 fact table 형태로 정규화하여 Postgres에 적재한다.
* **Postgres serving / metadata DB**: fact table, 집계 테이블(aggregate tables), 최신 serving view 및 API의 읽기 모델(read model)을 관리하는 메인 저장소다.
* **API layer**: FastAPI 라우터(routers)를 통해 Steam 및 Chzzk의 읽기 전용 endpoint를 제공한다.
* **Web source views**: React와 Vite 기반의 대시보드로 Steam의 `Explore` 및 `Top Selling` 화면과 Chzzk의 관측된 카테고리 source view를 표시한다.
* **Runtime**: 주기적인 실행 환경(recurring runtime)은 Windows Task Scheduler가 WSL2 명령어를 호출하는 가벼운 스케줄러 구조(thin scheduler boundary)를 사용한다.
* **Artifact handoff**: R2는 현재 공식 저장소 런타임이 아니라, 원격 작업과 휴대 가능한 최신 스냅샷 검토를 돕기 위한 로컬 운영 보조 경로로 활용한다.
* **Local observability**: 로컬 스케줄러의 상태와 데이터의 최신화 상태(freshness visibility)를 모니터링하기 위해 Prometheus와 Grafana를 관측 도구로 활용한다.
* **DuckDB**: 프로덕션 serving을 대체하는 용도가 아니며, 로컬이나 프라이빗 환경에 보관된 아티팩트를 재계산하거나 문제 상황을 분석(triage)하기 위한 제한적인 읽기 전용 도구(bounded read-only helper)로 사용한다.

## 현재 API

현재 API 목록은 레포지토리의 라우터에 실제 구현되어 있는 endpoint만 포함하고 있다.

### Steam

* `GET /games/explore/overview`
* `GET /games/rankings/latest`
* `GET /games/ccu/latest`
* `GET /games/{canonical_game_id}/ccu/latest`
* `GET /games/{canonical_game_id}/ccu/daily-90d`
* `GET /games/price/latest`
* `GET /games/{canonical_game_id}/price/latest`
* `GET /games/reviews/latest`
* `GET /games/{canonical_game_id}/reviews/latest`

### Chzzk

* `GET /chzzk/categories/overview`

Combined API는 아직 구현된 API가 아니다.

통합된 소스 및 KPI 체계(combined source/KPI semantics) 구축은 예정된 작업(planned work)으로 분리해 두었다.

## 검증과 품질 관리

주요 변경은 성격에 따라 `poetry run ruff check .`, `poetry run pytest`, `cd web && npm run build` 같은 명령으로 확인한다.

운영 관련 확인은 local read-only smoke와 checkpoint 중심으로 수행하며, public README에는 raw payload, private runtime detail, credential, scheduler XML/stdout, row-level UGC를 남기지 않는다.

## 향후 작업

다음 항목들은 향후 개발을 목표로 하는 과제이며, 아직 구현되지 않았다.

* Chzzk regular collection 안정화
* Chzzk source view completion
* category-to-game mapping
* Combined source/KPI semantics
* dbt Core bounded modeling, tests, docs
* Dagster 중심의 orchestration/control-plane pilot

## 조건부 도입 도구 후보

아래 도구들은 현재 구현되어 있거나 운영 중인 런타임에 포함되어 있지 않으며, 특정 조건이 충족될 때 도입을 검토할 향후 방향성(future direction)이다.

* **DuckDB**: 현재는 프로덕션 serving이 아니라 제한적인 읽기 전용 재계산 및 점검 도구로 사용한다. 이후 Parquet 기반 아티팩트나 구체적인 재계산 경로가 필요해질 때 활용 범위를 확장할 수 있다.
* **Dagster**: 현재 정기 실행의 기준은 Windows Task Scheduler와 WSL2이며, 이를 바로 대체하는 런타임은 아니다. Steam과 Chzzk의 정기 수집 경로가 안정화된 뒤, 개발 및 운영 제어를 돕는 작은 pilot으로 검토한다. Airflow는 같은 문제를 해결할 수 있는 대체 orchestrator 후보로만 본다.
* **Loki**: Prometheus와 Grafana를 통한 지표 관측이 안정화된 후, 반복적인 파일 로그(recurring file logs) 관리가 운영상 병목을 일으킬 때 도입을 검토할 중앙 집중식 로그 관리(centralized logs) 후보군이다.
* **ClickHouse**: Postgres와 DuckDB의 범위를 넘어서는 대규모 과거 데이터에 대한 OLAP 병목 현상이 실제로 확인될 경우 도입을 검토한다.
* **Garage**: 현재 운영 중인 아티팩트 런타임은 아니며, 향후 S3 호환 아티팩트 저장소에 대해 자체 호스팅(self-hosted) 기반의 대안이나 마이그레이션이 필요할 때 고려할 옵션이다.
