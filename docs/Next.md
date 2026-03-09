# NEXT

마지막 업데이트: 2026-03-09 (KST)  
현재 브랜치: feat/steam-ccu-api

## 목적
이 문서는 **지금 바로 할 일 / 다음 할 일 / 나중에 할 일 / 막힌 일**만 짧게 관리하는 살아 있는 작업판이다.  
체크포인트 문서처럼 “시점 기록”을 남기는 용도가 아니라, 현재 실행 우선순위를 잊지 않기 위한 용도다.

---

## Now

### 1) 관측 / 신뢰성 최소 셋 보강
- [ ] probe / ingest 공통 실행 결과 구조 정리
  - success / fail / latency_ms 기록
  - HTTP status 기록
  - collected_at_kst 포함 여부 점검
- [ ] 429 / timeout 비율 집계 추가
- [ ] retry / backoff 규칙 명문화
- [ ] idempotent 적재 확인 항목 정리
  - fact 계열 PK upsert 재실행 안전성 확인
- [ ] CCU vertical slice 기준 최소 회귀 체크리스트 문서화
  - fact_steam_ccu_30m 적재 확인
  - srv_game_latest_ccu 조회 확인
  - /games/ccu/latest 응답 확인
  - /games/1/ccu/latest 응답 확인

### 2) probe hygiene 정리
- [ ] 대표 샘플 고정 파일명 정리
- [ ] 일부 probe 파일에 KST 수집 시각 필드 보강
- [ ] App Catalog 성공 probe 확보
- [ ] Price(KR) 정상 가격 샘플 확보

### 3) API 시간 의미 정리
- [ ] `bucket_time`의 KST semantics vs UTC ISO 직렬화 표현 원칙 문서화
- [ ] API 응답 예시 1개를 문서에 고정

---

## Next

### 4) Rankings 파서 수정
- [ ] raw HTML → parsed_rows 파싱 로직 수정
- [ ] KR / global, top_selling / top_played 샘플 기준 회귀 테스트 추가
- [ ] `parsed_rows=[]` 실패 케이스 재현 후 수정 확인

### 5) tracked_universe 자동화
- [ ] seed 입력 규칙 정리
- [ ] 전체 app catalog vs tracked 대상 분리 규칙 정리
- [ ] 랭킹/지표 기반 tracked 대상 갱신 초안 만들기

---

## Later

### 6) Price / Reviews Gold 연계
- [ ] fact_steam_price_1h 적재 안정화
- [ ] fact_steam_reviews_daily 적재 안정화
- [ ] latest serving view 초안 검토

### 7) 90일 rollup 준비
- [ ] agg_steam_ccu_daily 초안
- [ ] 90일 조회 패턴 기준 인덱스 / rollup 점검

### 8) Chzzk / Provider 확장 준비
- [ ] Provider 인터페이스 명세 재확인
- [ ] Steam-only 범위 안정화 후 착수 여부 판단

---

## Blocked

### App Catalog
- [ ] `IStoreService/GetAppList` 성공 probe 확보 전까지 자동화 보류
- 메모:
  - 기존 실패 원인은 잘못된 엔드포인트 호출 가능성 있음
  - Steam Web API Key 설정 필요

### Rankings
- [ ] parser fix 전까지 rank_daily 후속 적재 보류

---

## Done

### Steam CCU first vertical slice
- [x] probe / DDL / ingest / API 1차 구현 완료
- [x] fact_steam_ccu_30m 적재 확인
- [x] srv_game_latest_ccu 조회 확인
- [x] /games/ccu/latest 응답 확인
- [x] /games/1/ccu/latest 응답 확인

---

## 작업 원칙

- 한 항목은 가능하면 **반나절~1일 안에 끝나는 크기**로 유지
- 완료 시 체크하고, 필요하면 옆에 브랜치/커밋 메모만 짧게 남김
- 상세한 판단/회고는 `docs/checkpoints/...` 문서에 남김
- probe 샘플 산출물은 계속 `docs/probe/...` 아래에 저장