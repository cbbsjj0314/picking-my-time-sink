# Steam CCU First Vertical Slice 체크포인트

작성일: 2026-03-07

작성 시점 브랜치: feat/steam-ccu-api

상태: checkpoint / in-progress

### 1. 문서 목적

이번 체크포인트의 목적은 **Steam-only 기준 첫 번째 의미 있는 vertical slice가 실제로 닫혔는지 확인하는 것**임.

현재 프로젝트는 Steam + Chzzk 전체 MVP를 목표로 하나, 실제 구현 순서는 **Steam-only를 먼저 관통**하는 방식으로 진행 중임.

이번 문서는 그중 **Steam CCU vertical slice** 기준으로 작성함.

---

### 2. 이번 체크포인트의 범위

범위는 아래까지임.

- Probe 샘플 저장 확인
- Gold DDL 생성 확인
- 최소 seed 데이터 입력 확인
- CCU fetch → bronze → silver → gold 1회 실행 확인
- `srv_game_latest_ccu` 조회 확인
- FastAPI 엔드포인트 실제 응답 확인

즉, **수집 → 적재 → 서빙 → API**까지 실제 동작했는지 확인하는 체크포인트임.

---

### 3. 현재 판단 요약

**결론: Steam CCU first vertical slice는 기능적으로 완료 상태임.**

완료 근거는 아래와 같음.

- Steam probe 샘플 파일이 실제로 저장됨
- Postgres DDL 객체 생성 확인됨
- 최소 seed 데이터 입력 확인됨
- `fact_steam_ccu_30m`에 실제 CCU 적재 확인됨
- `srv_game_latest_ccu`에서 최신값 조회 확인됨
- FastAPI 엔드포인트 2개 실제 응답 확인됨

즉, **첫 번째 의미 있는 vertical slice는 실제로 닫혔다고 판단 가능함.**

---

### 4. 이번 체크포인트에서 완료한 항목

### 4.1 개발 환경 및 작업 규칙 정리

- `Poetry + pyproject.toml + Ruff + pytest` 도입함
- `AGENTS.md` 추가함
- 브랜치 / 커밋 / 주석 규칙 정리함
- Codex 5단계 방식으로 구현 진행함

### 4.2 Git 진행 상태

현재 브랜치: `feat/steam-ccu-api`

최근 커밋 흐름:

- `feat(api): latest CCU 조회 API 추가`
- `feat(ccu): 30분 버킷 적재와 delta 계산 구현`
- `feat(sql): Steam CCU 최소 DDL 및 serving 뷰 추가`
- `feat(probe): Steam probe 스크립트와 샘플 저장 로직 추가`
- `docs(repo): add AGENTS.md for codex workflow`
- `chore: bootstrap poetry, ruff, and pytest`

브랜치를 작은 단계로 나눠 진행한 점은 좋았음.

---

### 5. Probe 상태 요약

### 5.1 실제 생성 파일

생성된 probe 파일은 아래와 같음.

- `docs/probe/steam/ccu/20260306T214141Z.json`
- `docs/probe/steam/getapplist/20260306T214556Z.json`
- `docs/probe/steam/reviews/20260306T214606Z.json`
- `docs/probe/steam/price_kr/20260306T214610Z.json`
- `docs/probe/steam/rankings_topsellers_global/20260306T214613Z.json`
- `docs/probe/steam/rankings_topsellers_kr/20260306T214614Z.json`
- `docs/probe/steam/rankings_mostplayed_global/20260306T214614Z.json`
- `docs/probe/steam/rankings_mostplayed_kr/20260306T214614Z.json`

### 5.2 Probe 전체 판정 요약

- **CCU:** 성공 샘플 확보
- **Reviews:** 성공 샘플 확보
- **Price(KR):** edge-case 샘플 확보
- **App Catalog:** 실패 샘플만 확보
- **Rankings:** raw HTML 저장 성공, 파싱 실패

### 5.3 Probe 세부 판정

**CCU**

- 저장 성공함
- HTTP 200 확인됨
- `player_count` 확인 가능함
- 성공 샘플로 판단 가능함

**Reviews**

- 저장 성공함
- HTTP 200 확인됨
- `query_summary.total_reviews / total_positive / total_negative` 확인 가능함
- 성공 샘플로 판단 가능함

**Price(KR)**

- 저장 성공함
- HTTP 200 확인됨
- 다만 가격 핵심 필드가 비어 있었음
- 정상 가격 샘플이라기보다 edge-case 샘플에 가까움

**App Catalog**

- 저장 구조와 실패 메타는 확보됨
- 다만 성공 probe는 확보하지 못함
- 엔드포인트/호출 방식 수정 필요함
    - 직접 원인은 잘못된 엔드포인트 호출(`ISteamApps/GetAppList/v2/`)로 보이며, 문서 기준 정식 대상은 `IStoreService/GetAppList`임
    - 또한 App Catalog는 Steam Web API Key 사용이 전제되어 있어, 후속 수정 시 key 설정도 함께 필요함

**Rankings**

- KR/global, top_selling/top_played 4개 HTML 저장 성공함
- 그러나 `parsed_rows=[]` 상태임
- 즉 raw HTML 저장까진 성공, 파서는 현재 실패 상태임

### 5.4 Probe 공통 보완점

- 대표 샘플 고정 파일명 미정리 상태임
- 일부 파일은 `collected_at_utc`만 있고 KST 수집 시각 필드는 별도 보완 필요함

---

### 6. DB 객체 및 seed 상태

### 6.1 DB 객체 확인 결과

아래 객체 존재 확인 완료함.

- `dim_game`
- `game_external_id`
- `tracked_game`
- `fact_steam_ccu_30m`
- `srv_game_latest_ccu`

즉, CCU vertical slice에 필요한 핵심 DB 객체는 모두 준비된 상태임.

### 6.2 seed 데이터 확인 결과

최소 seed 데이터 입력 완료함.

- `dim_game`
    - `canonical_game_id=1`
    - `canonical_name=Counter-Strike 2`
- `game_external_id`
    - `source=steam`
    - `external_id=730`
    - `canonical_game_id=1`
- `tracked_game`
    - `canonical_game_id=1`
    - `is_active=true`
    - `priority=3`
    - `sources={steam}`

즉, 최소 추적 대상 1개가 준비된 상태임.

---

### 7. CCU 파이프라인 실행 결과

### 7.1 생성된 중간 산출물

로컬 실행 과정에서 아래 파일 생성됨.

- `tmp/ccu/bronze_ccu.jsonl`
- `tmp/ccu/silver_ccu.jsonl`
- `tmp/ccu/gold_result.jsonl`

### 7.2 실행 결과 요약

- fetch 실행됨
- bronze 파일 생성됨
- bronze → silver 변환됨
- silver → gold upsert 수행됨
- `fact_steam_ccu_30m` 적재 확인됨

즉, **fetch → bronze → silver → gold 파이프라인 1회 실행 성공 상태임.**

---

### 8. 대표 실행 결과 3개

### 8.1 Gold fact 적재 확인

실행 결과:

```
canonical_game_id=1
bucket_time=2026-03-07 14:00:00 +0900
ccu=858325
collected_at=2026-03-07 14:13:55 +0900
```

판단:

- `fact_steam_ccu_30m`에 실제 데이터 적재됨
- `bucket_time`은 KST 기준 30분 버킷 의미를 유지함
- 현재 vertical slice 기준 핵심 fact 적재 성공함

### 8.2 Serving view 확인

실행 결과:

```
canonical_game_id=1
canonical_name=Counter-Strike 2
steam_external_id=730
priority=3
sources={steam}
bucket_time=2026-03-07 14:00:00 +0900
latest_ccu=858325
prev_day_same_bucket_ccu=NULL
delta_ccu_day=NULL
```

판단:

- 최신 `ccu` 조회 성공함
- 전일 동일 버킷 데이터가 아직 없으므로 `delta_ccu_day=NULL` 상태임
- 현재 시점에서는 정상 결과로 판단 가능함

### 8.3 API 실제 응답 확인

실행 결과:

```
{
  "canonical_game_id":1,
  "canonical_name":"Counter-Strike 2",
  "bucket_time":"2026-03-07T05:00:00Z",
  "ccu":858325,
  "delta_ccu_abs":null,
  "delta_ccu_pct":null,
  "missing_flag":true
}
```

판단:

- API 실제 응답 성공함
- 단건 API / 목록 API 모두 동작 확인됨
- 현재는 전일 비교값이 없어서 `delta_* = null`, `missing_flag = true` 상태임
- 이는 현 시점 데이터 상태상 정상 해석 가능함

---

### 9. 현재 남은 이슈

판단 원칙은 아래와 같음.

**vertical slice는 완료 상태로 보되, 일부 probe/직렬화 이슈는 후속 보완 과제로 둠**

### 9.1 Probe 관련

- App Catalog 성공 probe 미확보 상태임
- Price(KR) 정상 가격 필드 성공 샘플 미확보 상태임
- Rankings는 raw HTML 저장까진 성공했으나 파싱 결과는 실패 상태임
- 대표 샘플 고정 파일명 미정리 상태임
- 일부 probe 파일은 KST 수집 시각 필드 보완 필요함

### 9.2 API 직렬화 관련

- DB에서는 `bucket_time = 2026-03-07 14:00:00 +0900`
- API 응답에서는 `2026-03-07T05:00:00Z`
- 두 값은 같은 시각임
- 기능상 문제는 없지만, API 응답에서 KST semantics를 어떻게 표현할지 명확화 필요함

### 9.3 관측/신뢰성 최소 셋

- 실패 / 지연 / 성공률 정리 강화 필요함
- 429 / timeout 비율 기록 정리 필요함
- 재시도 / 백오프 정책 문서화 보강 필요함
- idempotent 적재 확인 항목 정리 필요함

---

### 10. Git 및 산출물 관리 정책

### 10.1 `docs/probe/steam/...`

**Git 추적 및 push 대상임**

이유:

- probe 샘플은 프로젝트 문맥상 회귀 테스트 기준점 역할을 함
- 문서화 가치가 있음
- 리포에 고정 저장하는 편이 맞음

### 10.2 `tmp/ccu/...`

**로컬 실행 산출물로 간주, Git 추적 제외 권장함**

이유:

- 실행 확인용 임시 산출물 성격이 강함
- probe 샘플과 달리 리포에 고정 저장할 대상은 아님
- `.gitignore`로 제외하는 편이 적절함

---

### 11. 다음 단계 제안

현재 vertical slice 완료 이후 우선순위는 아래와 같음.

1. 관측 / 신뢰성 최소 셋 보강
2. Rankings 파서 수정
3. tracked_universe 자동화
4. Price(KR) 정상 샘플 확보 및 Gold 연계
5. Reviews Gold 연계
6. 90일 rollup 준비

즉, 다음 기능 추가 전에 **신뢰성/관측/Probe 품질 보완**이 먼저 오는 편이 좋음.

---

### 12. 최종 판정

**Steam CCU first vertical slice는 기능적으로 완료 상태임.**

다만 probe 일부 항목과 시간 직렬화 표현은 후속 보완 과제로 남아 있음.