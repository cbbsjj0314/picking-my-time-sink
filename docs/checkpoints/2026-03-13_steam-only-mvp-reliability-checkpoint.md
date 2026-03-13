# Steam-only MVP Reliability 체크포인트

작성일: 2026-03-13  
작성 시점 브랜치: `feat/probe-hygiene`  
상태: `checkpoint / reliability-baseline-complete`

---

## 1. 문서 목적

이번 체크포인트의 목적은 **Steam-only MVP가 단순히 한 번 동작한 상태를 넘어서, 최소 신뢰성/관측/문서 계약까지 포함한 기준선으로 닫혔는지 기록하는 것**이다.

2026-03-07 체크포인트에서는 Steam CCU first vertical slice가 기능적으로 닫혔는지 확인했다.  
이번 문서는 그 이후 남아 있던 후속 보완 항목들, 즉 아래 3가지를 닫은 상태를 기록한다.

- 관측 / 신뢰성 최소 셋 보강
- probe hygiene 정리
- API 시간 의미 정리

즉, 이번 체크포인트는 **“Steam-only MVP 신뢰성 기반 완성”** 상태를 남기는 문서다.

---

## 2. 이번 체크포인트의 범위

이번 체크포인트에서 닫는 범위는 아래까지다.

- observability / retry-backoff / 최소 회귀 체크리스트를 checkpoint 밖 durable doc으로 고정
- probe representative sample / KST 수집 시각 / Price(KR) 정상 샘플 정리
- latest CCU API의 `bucket_time` 의미를 durable doc에 고정
- API 응답 예시 1개를 checkpoint 밖 문서에 고정
- latest CCU API의 현재 직렬화 동작에 대한 최소 regression test 추가
- `ruff` / `pytest` 통과 확인

이번 문서는 새로운 기능 확장을 기록하는 문서가 아니라,  
**기존 Steam-only MVP vertical slice가 “운영/검증 가능한 최소 기준”까지 올라왔는지**를 기록하는 체크포인트다.

---

## 3. 현재 판단 요약

**결론: Steam-only MVP는 현재 시점에서 “신뢰성 기반 완성” 상태로 판단 가능하다.**

판단 근거는 아래와 같다.

- Steam CCU vertical slice는 이미 기능적으로 닫혀 있었다.
- observability / retry / backoff / 최소 회귀 기준이 별도 durable doc에 정리됐다.
- probe representative sample 정리와 KST 수집 시각 보강이 완료됐다.
- Price(KR) 정상 가격 샘플이 확보됐다.
- latest CCU API의 `bucket_time` 의미와 wire-format 해석이 checkpoint 밖 durable doc에 고정됐다.
- latest CCU API의 현재 직렬화 동작을 잠그는 최소 regression test가 추가됐다.
- `ruff` / `pytest` 기준으로 현재 변경이 통과했다.

즉, 지금 상태는 **“한 번 동작했다” 수준이 아니라, 최소한의 관측/회귀/계약 문서까지 갖춘 Steam-only MVP 기준선**으로 볼 수 있다.

---

## 4. 이번 체크포인트에서 닫힌 항목

### 4.1 관측 / 신뢰성 최소 셋 보강

이번 단계에서 아래 항목을 닫았다.

- execution meta 문구 / 기준을 현재 구현과 맞게 정리
- 429 / timeout 비율 산식과 표시 방식 정리
- retry / backoff 규칙을 durable doc 1곳에 고정
- CCU vertical slice 기준 최소 회귀 체크리스트를 checkpoint 밖 문서로 정리

현재 durable doc은 아래다.

- `docs/decisions/steam-ccu-observability.md`

이 문서는 현재 Steam CCU Now 1 observability rules를 고정하고,  
실행 메타 필드 의미 / 429·timeout 비율 해석 / retry-backoff 규칙 / 최소 회귀 체크리스트를 문서화한다.

---

### 4.2 Probe hygiene 정리

이번 단계에서 아래 항목을 닫았다.

- representative sample 고정 파일명 정리
- 일부 probe 파일에 KST 수집 시각 필드 보강
- Price(KR) 정상 가격 샘플 확보

현재 메모:

- `ccu` / `reviews` / `rankings_*` / `getapplist` / `price_kr` representative sample 정리 완료
- committed `docs/probe/steam/getapplist/representative.json`에 `collected_at_kst` 포함
- committed `docs/probe/steam/price_kr/representative.json`에 정상 가격 샘플 반영 완료

즉, probe 쪽은 이제  
**“샘플이 있긴 한데 이름/의미가 흔들리는 상태”** 에서  
**“대표 샘플과 일부 핵심 시간 필드가 정리된 상태”** 로 올라왔다.

---

### 4.3 API 시간 의미 정리

이번 단계에서 아래 항목을 닫았다.

- `bucket_time`의 KST semantics vs wire-format 해석 원칙을 checkpoint 밖 durable doc 1곳에 고정
- API 응답 예시 1개를 checkpoint 기준으로 durable doc에 고정

현재 durable doc은 아래다.

- `docs/metrics-definitions.md`

핵심 정리는 아래와 같다.

- Steam CCU의 internal / DB 의미에서 `bucket_time`은 KST half-hour bucket instant다.
- latest CCU API의 `bucket_time` wire output은 같은 instant를 표현한 timezone-aware ISO datetime string으로 본다.
- 현재 API 런타임은 timezone-aware `datetime`을 그대로 직렬화하며, UTC-only serialization을 강제하지 않는다.
- 따라서 checkpoint의 `Z` 예시는 실제 관측된 wire example이지만, current runtime이 보장하는 유일한 timezone representation은 아니다.

즉, 이번 단계에서  
**DB 의미(KST 버킷 semantics)** 와  
**API 표현(timezone-aware ISO wire output)** 을 분리해서 읽는 계약이 문서로 고정됐다.

---

## 5. Git 진행 상태

현재 브랜치: `feat/probe-hygiene`

최근 마감 흐름에서 핵심 커밋은 아래 성격을 포함한다.

- probe representative sample 정리
- durable metrics definitions 문서 추가
- `bucket_time` contract 문서화 + API regression test 추가

메모:

- 이번 Now 1~3 마감 작업은 `feat/probe-hygiene` 브랜치에서 연속 진행했다.
- 브랜치명은 Now 2 시작 시점 기준으로 남아 있지만, 실제 diff 범위는 observability / probe hygiene / API time semantics 정리까지 포함한다.
- 커밋 메시지 단위로는 작업 구분이 가능하므로, 이번 체크포인트에서는 브랜치를 새로 분리하지 않고 그대로 유지했다.

---

## 6. 대표 결과 요약

### 6.1 Observability durable doc 고정

현재 기준 문서:

- `docs/decisions/steam-ccu-observability.md`

현재 문서화된 내용:

- execution meta contract
- 429 / timeout ratio 해석
- retry / backoff rules
- minimal regression checklist

판단:

- Now 1 범위였던 “관측 / 신뢰성 최소 셋”은 문서 기준으로 닫힘
- runtime 확장보다 현재 구현 해석을 고정하는 데 초점을 맞춤
- 이후 변경 시 이 문서를 기준으로 drift를 확인할 수 있음

---

### 6.2 Probe representative sample 정리

현재 representative sample 체계는 probe별로 고정 파일명 기준이 정리된 상태다.

특히 이번 단계에서 중요했던 점은 아래다.

- representative sample 파일명이 흔들리지 않도록 정리됨
- 일부 probe는 KST 수집 시각 필드까지 보강됨
- Price(KR) 정상 가격 샘플이 확보됨

판단:

- probe 결과를 durable reference처럼 읽기 쉬워짐
- “샘플은 있는데 어떤 게 기준 파일인지 불명확”한 상태가 해소됨
- 이후 probe 회귀 확인 시 기준점으로 쓰기 쉬워짐

---

### 6.3 API 시간 의미 durable contract 고정

현재 기준 문서:

- `docs/metrics-definitions.md`

고정한 대표 예시는 아래다.

```json
{
  "canonical_game_id": 1,
  "canonical_name": "Counter-Strike 2",
  "bucket_time": "2026-03-07T05:00:00Z",
  "ccu": 858325,
  "delta_ccu_abs": null,
  "delta_ccu_pct": null,
  "missing_flag": true
}
```

같이 고정한 해석은 아래다.

- 위 `"bucket_time":"2026-03-07T05:00:00Z"` 는 KST bucket/view 값 `2026-03-07 14:00:00 +0900` 와 같은 시각이다.
- 이 예시는 실제 관측된 wire example이다.
- 하지만 current runtime이 보장하는 유일한 timezone representation은 아니다.

판단:

- 2026-03-07 checkpoint에서 남아 있던 “API에서 KST semantics를 어떻게 표현할지” 공백이 닫힘
- 기능을 바꾸지 않고, 의미 계약을 checkpoint 밖 durable doc으로 옮겨 고정함
- `missing_flag`를 포함한 current response shape 기준이 유지됨

---

### 6.4 Latest CCU API 최소 regression test 고정

현재 추가된 최소 회귀 고정은 아래 성격이다.

- 단건 endpoint test에서 `bucket_time` 직렬화 문자열을 직접 검증
- fixture-path 기준 KST-aware 입력이 현재 어떻게 직렬화되는지를 잠금
- UTC-only wire contract를 강제하지는 않음

현재 고정된 코드:

```python
# Locks current behavior; UTC-only wire format needs deliberate runtime change and test update.
assert body["bucket_time"] == "2026-03-07T12:30:00+09:00"
```

해석:

- 이 assertion은 checkpoint 예시의 instant를 다시 검증하는 테스트가 아니다.
- 이 assertion은 **현재 테스트 fixture input이 어떤 wire value로 직렬화되는지**를 잠그는 최소 regression test다.
- 따라서 checkpoint 예시 instant와 test fixture instant가 서로 달라도 충돌이 아니다.

판단:

- 문서 계약과 현재 직렬화 동작 사이의 최소 연결고리가 생김
- 이후 누가 UTC-only wire behavior로 바꾸려면 runtime change + test update를 의도적으로 해야 함

---

## 7. 검증 상태

이번 단계에서 확인한 검증 기준은 아래다.

- `poetry run ruff check .`
- `poetry run pytest`

실행 결과:

- `poetry run ruff check .` → `All checks passed!`
- `poetry run pytest` → `59 passed in 0.42s`

판단:

- Now 1~3 마감 기준으로 최소 정적 검사 / 테스트 기준이 통과한 상태다.
- 체크포인트 문서 작성 시점 기준으로, Steam-only MVP는 기능 + 최소 신뢰성 문서화 + 최소 회귀 기준을 함께 만족한다.

---

## 8. 이번 체크포인트 시점의 상태 정리

이번 시점에서 아래는 완료 상태로 본다.

- Steam CCU first vertical slice
- observability / retry / backoff / 최소 회귀 체크리스트 정리
- probe hygiene 정리
- API 시간 의미 정리

반면 아래는 아직 후속 범위로 남는다.

- App Catalog automation 정리
- tracked_universe broader scheduled pipeline 연결
- Price / Reviews Gold 연계
- 90일 rollup 준비
- Chzzk / Provider 확장 준비

즉, 지금 상태는  
**Steam-only MVP를 더 넓히는 단계 전, 현재 Steam 기준선을 신뢰성 있게 고정한 상태** 로 보는 게 맞다.

---

## 9. 이전 체크포인트 대비 달라진 점

2026-03-07 체크포인트 시점에는 아래가 후속 이슈였다.

- App Catalog 성공 probe 미확보
- Price(KR) 정상 가격 샘플 미확보
- Rankings parser repair 미완료
- representative sample 고정 파일명 미정리
- 일부 probe의 KST 수집 시각 보강 필요
- API `bucket_time` KST semantics 표현 원칙 미고정
- observability / retry / timeout / idempotent 관련 문서 보강 필요

현재 시점에서는 그중 아래가 닫혔다.

- App Catalog success probe 확보
- Rankings parser offline fixture 기준 repair 완료
- representative sample 고정 파일명 정리 완료
- 일부 probe KST 수집 시각 보강 완료
- Price(KR) 정상 가격 샘플 확보 완료
- observability / retry-backoff / regression checklist durable doc 고정 완료
- `bucket_time` API 의미 계약 durable doc 고정 완료

즉, 첫 번째 checkpoint가  
**“기능적으로 한 번 관통됐다”** 는 기록이었다면,  
이번 checkpoint는  
**“그 vertical slice를 최소 신뢰성 기준까지 끌어올렸다”** 는 기록이다.

---

## 10. 현재 판단 결론

**결론: Steam-only MVP는 현재 시점에서 “신뢰성 기반 완성(reliability baseline complete)” 상태로 판단 가능하다.**

이 판단은 아래를 전제로 한다.

- Steam-only 범위 안에서 핵심 vertical slice는 이미 기능적으로 닫혀 있음
- 이후 남아 있던 Now 1~3 후속 보완 항목이 모두 닫힘
- 관측 / probe / API 의미 계약 / 최소 regression test가 checkpoint 밖 durable doc과 테스트로 고정됨
- 아직 남아 있는 것은 기능 확장/범위 확대 성격의 작업이지, 현재 Steam-only 기준선의 의미/신뢰성 공백은 아님

---

## 11. 다음 단계 제안

현재 Steam-only 기준선은 신뢰성 기반까지 고정됐다고 볼 수 있으므로, 다음 우선순위는 **기준선 재정의가 아니라 범위 확장/연결** 쪽이다.

추천 우선순위는 아래와 같다.

1. App Catalog automation 정리
2. tracked_universe scheduled pipeline 연결
3. Price / Reviews Gold 연계
4. 90일 rollup 준비
5. Chzzk / Provider 확장 준비

즉, 다음 단계는 **현재 Steam-only baseline을 다시 손보는 것보다, 이미 닫힌 기준선 위에 다음 기능/파이프라인을 연결하는 작업**으로 넘어가는 편이 맞다.
