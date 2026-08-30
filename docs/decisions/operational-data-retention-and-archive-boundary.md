# Operational Data Retention and Archive Boundary

## Status

Status: accepted target direction, docs-only  
Date: 2026-08-30 (KST)

이 결정은 PMTS의 operational/source evidence, off-host retained evidence,
PostgreSQL recovery, long-term archive 사이의 책임과 retention 경계를 고정한다.

이번 문서는 architecture/retention contract를 정의한다. archive copy,
compression, manifest/checksum generation, recovery scheduling, pruning,
R2 object mutation, Desktop HDD copy, incident tooling 구현은 별도 follow-up
gate 뒤에서 수행한다.

## Context

PMTS의 operational authority와 PostgreSQL authoritative state는 Cloud Linux
환경을 중심으로 운영하는 방향으로 전환되었다.

기존 문서들은 다음 두 경계를 이미 정의했다.

- PostgreSQL facts, dimensions, mappings, serving views는 persistent
  authoritative state다.
- full local runtime tree를 off-host에 그대로 mirror하지 않고,
  selected artifact만 S3-compatible object boundary에 publish한다.

하지만 다음 항목은 별도 follow-up decision으로 남아 있었다.

- recent local evidence를 얼마 동안 보관할지
- historical exact reacquisition이 어려운 source evidence를 어떻게 보존할지
- rebuildable/operational artifact를 언제 prune할지
- R2와 Desktop HDD의 역할을 어떻게 나눌지
- PostgreSQL recovery의 RPO/RTO와 generation retention
- abnormal run과 incident evidence를 장기적으로 어떻게 남길지
- 기존 Desktop/MacBook shared-artifact contract를 Cloud authority 이후
  topology에서 어떻게 해석할지

이 ADR은 위 경계를 통합해 current retention/archive direction을 고정한다.

## Decision Drivers

- historical exact reacquisition이 어려운 point-in-time source evidence를
  불필요하게 잃지 않는다.
- PostgreSQL authoritative state와 runtime artifact를 혼동하지 않는다.
- recent retry/debug value만 있는 artifact를 indefinite archive하지 않는다.
- rebuildable artifact는 retained authoritative/source input으로 재생성
  가능성이 검증되면 독립적인 long-term archive로 승격하지 않는다.
- Cloud local disk가 uncontrolled artifact archive가 되지 않게 한다.
- off-host recovery와 long-term source archive의 책임을 분리한다.
- R2 Free-tier capacity를 PostgreSQL recovery와 small/high-value evidence에
  우선 사용한다.
- Desktop HDD는 bulk/deep-cold archive로 활용하되 단일 HDD durability
  limitation을 숨기지 않는다.
- deletion은 age만으로 결정하지 않고 verified downstream copy 이후에만
  허용한다.
- incident 발생 당시의 machine-observed fact와 사후 human analysis를
  분리한다.

## Storage Responsibility

### PostgreSQL

Production PostgreSQL은 current structured domain state의 authoritative
persistent storage다.

- facts, dimensions, mappings, serving views를 age만으로 자동 tier-out하지
  않는다.
- Parquet/R2/HDD archive가 PostgreSQL authority를 대체하지 않는다.
- analytical/archive representation은 별도 secondary copy일 수 있다.

### Cloud local filesystem

Cloud local filesystem은 다음을 담당한다.

- active/hot runtime state
- recent source evidence
- recent derived/operational evidence
- retry, replay, troubleshooting, incident investigation에 필요한 working set

대부분의 source/derived/operational artifact에 대한 기본 recent window는
`30일`이다.

단, 다음 경우에는 30일을 넘겨도 prune하지 않는다.

- required archive copy가 아직 verified되지 않음
- reconstruction/prune prerequisite가 충족되지 않음
- unresolved incident 조사에 필요한 forensic evidence
- legacy provenance gap 때문에 자동 cleanup 대상에서 제외된 artifact

### S3-compatible off-host storage / Cloudflare R2

R2는 general-purpose full runtime mirror가 아니다.

우선순위는 다음과 같다.

1. PostgreSQL recovery
2. compact abnormal-run / closed incident evidence
3. selected high-value source evidence
4. optional retained artifacts

R2 Standard Free-tier capacity 안에서 운영하는 것을 기본 목표로 한다.

- fixed age expiry를 기본 retention mechanism으로 사용하지 않는다.
- capacity pressure가 생기면 verified Desktop HDD copy가 있는 오래된
  selected source evidence부터 R2에서 줄인다.
- PostgreSQL recovery와 compact incident evidence를 source-evidence cache보다
  우선 보호한다.
- 유료 사용이 필요해지는 경우 별도 owner approval을 요구한다.

### Desktop HDD

Desktop HDD는 bulk/deep-cold long-term archive를 담당한다.

대표 대상:

- 오래된 Chzzk provider/source evidence
- selected Steam provider-near/source evidence
- 중요한 incident의 full forensic bundle

Desktop HDD는 long retention에 유리하지만 단일 physical disk는 indefinite
durability를 보장하지 않는다.

archive value가 커지거나 failure risk가 받아들이기 어려워지면 저비용 cloud
cold storage 또는 additional replica를 별도 decision으로 검토한다.

## Archive Safety Contract

Archive와 prune은 다음 순서를 따른다.

```text
copy
→ inventory / manifest
→ size / checksum / integrity verification
→ archive completion 확인
→ 그 이후에만 source-tier copy prune
```

다음은 허용하지 않는다.

- downstream archive 확인 없이 age만으로 destructive prune
- first archive rollout과 first destructive rollout을 같은 gate로 취급
- R2 automatic lifecycle expiration을 verified-copy condition의 대체물로 사용

Archive creation/verification과 deletion authority는 별도 rollout으로 취급한다.

## Data Classification Rule

Retention 판단은 filename보다 실제 semantics를 우선한다.

### Long-term source evidence

다음 성격을 가진 artifact다.

- historical exact reacquisition이 불가능하거나 문서화되지 않음
- downstream fact/Silver에서 information loss가 있음
- future parser/schema/replay value가 있음

기본 direction:

```text
Cloud recent window
→ Desktop HDD long-term archive
→ R2 capacity가 허용되는 동안 additional off-host copy
```

### Bounded source / operational evidence

다음 성격을 가진 artifact다.

- retry/debug/triage에는 가치가 있음
- authoritative state 또는 long-term source input은 아님
- 장기 보존의 추가 가치가 제한적임

기본 direction:

```text
Cloud recent window
→ required consumer/triage window 종료
→ prune
```

### Rebuildable artifact

Retained authoritative/source input과 historical transform semantics로
재생성 가능한 artifact다.

기본 direction:

```text
recent working window
→ reconstruction prerequisite 검증
→ prune
```

### Disposable runtime state

locks, caches, atomic temp, triage scratch 등 historical information value가
없는 coordination state다.

장기 archive 대상이 아니다.

## Chzzk Retention

### `raw/page-*.json`

`raw/page-*.json`은 run에서 실제 fetch한 point-in-time provider response
page다.

- bounded pagination으로 fetch한 page만 보존하므로 전체 Chzzk population의
  완전 snapshot이라고 해석하지 않는다.
- 동일 과거 시점의 response를 다시 획득하는 historical contract는 없다.
- downstream fact보다 더 많은 provider fields를 보존한다.

Retention:

```text
Cloud local: 30일
Desktop HDD: long-term archive
R2: capacity가 허용되는 동안 additional copy
```

### `summary.json`

`summary.json`은 raw와 함께 long-term retained source context로 취급한다.

이 파일은 raw payload에 없는 다음 run context를 보존한다.

- collection time
- fetch/failure/result context
- pagination/bounded-cutoff context
- derived artifact 생성 가능성을 해석하는 run context

Retention은 대응 raw와 동일하다.

### Historical code identity

Future Chzzk run에는 최소 다음 application provenance를 기록하는 방향을
채택한다.

```text
code_revision
code_dirty
```

현재 목표는 byte-perfect reproduction이 아니라 semantic replay다.

별도 `parser_version`은 parser contract 자체의 versioning 필요가 실제로
생길 때 도입한다.

Provenance 개선 이전 historical run에는 new pruning contract를 자동 소급하지
않는다.

### `category-result.jsonl`

Classification:

`bounded operational/derived evidence`

Retention:

```text
Cloud: 30일 + prune prerequisite
R2: long-term no
Desktop HDD: no
```

Prune prerequisite에는 최소 다음이 포함된다.

- 대응 raw/summary archive verified
- historical code identity available
- retry/load/troubleshooting requirement 종료
- representative raw-to-derived reconstruction validation
- legacy provenance exception이 아님

### `channel-result.jsonl`

Classification:

`rebuildable artifact`

`category-result.jsonl`과 같은 Cloud recent/prune safety boundary를 적용하고
R2/HDD long-term archive 대상에서는 제외한다.

### Routine operational result/meta

Routine successful `result.json`, loader summary/meta와 유사 execution
evidence는 `bounded operational evidence`다.

Retention:

```text
Cloud: 30일
R2: blanket long-term no
Desktop HDD: blanket long-term no
```

Failure/incident evidence는 아래 incident contract를 따른다.

### Locks / temp

Coordination lock, atomic temp, stale owner text 등은 disposable runtime state다.

## Steam Retention

### `price.bronze.jsonl`

Classification:

`long-term source evidence`

이유:

- provider-near decoded payload와 request/fallback/error context를 보존
- downstream Silver/PostgreSQL에서 provider-specific context가 소실
- 동일 historical payload를 as-of 시점으로 다시 얻는 contract가
  문서화되지 않음

Retention:

```text
Cloud: 30일
Desktop HDD: long-term archive
R2: capacity가 허용되는 동안 additional copy
```

현재 direction은 hourly generation을 sampling해서 버리는 것보다
lossless compression과 duplicated representation 축소를 먼저 검토한다.

### Ranking payloads

대상:

```text
mostplayed_global.payload.json
mostplayed_kr.payload.json
topsellers_global.payload.json
topsellers_kr.payload.json
```

Classification:

`long-term source evidence`

이유:

- point-in-time decoded provider payload
- downstream ranking fact에서 extra fields/order/excluded rows가 소실
- historical as-of re-fetch contract가 문서화되지 않음
- volume이 비교적 작음

Retention:

```text
Cloud: 30일
Desktop HDD: long-term archive
R2: selected source evidence 중 높은 priority
```

### App Catalog completed snapshot

`app_catalog.snapshot.jsonl`은 raw page archive가 아니라 normalized Bronze
snapshot이다.

그럼에도 historical catalog population/name/change metadata가 downstream
state에서 완전히 복원되지 않으므로 retention responsibility는 long-term
source evidence로 둔다.

Future/re-enabled collection에서:

```text
Cloud: recent/current referenced generation
Desktop HDD: completed weekly generations long-term
R2: capacity가 허용되는 동안 additional copy
```

Current Cloud runtime에서 App Catalog recurring collection이 활성화되지 않은
경우 이 contract는 future/re-enabled collection에 적용한다.

Completed checkpoint는 resume responsibility가 끝난 뒤 disposable하다.

### CCU Bronze/Silver

Artifacts:

```text
ccu.bronze.jsonl
ccu.silver.jsonl
```

Classification:

`bounded source/operational evidence`

정상적으로 적재된 historical CCU value의 authoritative state는 PostgreSQL
fact에 남는다.

Bronze/Silver의 추가 장기 가치는 주로 retry/missing/skip/normalization
context이므로 routine generations 전체를 indefinite archive하지 않는다.

Retention:

```text
Cloud: 30일
R2: long-term no
Desktop HDD: no
```

Important abnormal/missing history는 abnormal-run / incident evidence로
장기 추적한다.

### Reviews Bronze/Silver

Artifacts:

```text
reviews.bronze.jsonl
reviews.silver.jsonl
```

Classification:

`bounded source/operational evidence`

Recurring Reviews Bronze는 full review object raw archive가 아니라 cumulative
count 중심의 intermediate evidence다.

Retention:

```text
Cloud: 30일
R2: long-term no
Desktop HDD: no
```

### Rebuildable / routine Steam artifacts

다음 artifact는 long-term source archive 대상이 아니다.

```text
price.silver.jsonl
price.gold-result.jsonl
reviews.gold-result.jsonl
rankings.payload-to-gold-result.jsonl
tracked_universe.update-result.jsonl
routine result.json
routine execution meta
routine logs
```

기본 direction은 recent operational/working window 이후 prune이다.

### `ccu.daily-rollup-result.jsonl`

이 파일은 source evidence가 아니라 full-history rollup execution artifact다.

기존 direction을 유지한다.

```text
Cloud: latest 5 generations target
R2: no
Desktop HDD: no
```

Scheduled full-history row output 자체는 compact summary로 줄이는 방향을
별도 implementation slice에서 다룬다.

## Abnormal-run Evidence

모든 정상 expected work를 완료하지 못했거나 expected execution evidence
contract를 만족하지 못한 invocation에는 compact abnormal-run record를
남기는 방향을 채택한다.

대표 trigger:

- `failed`
- `partial_success`
- hard failure
- lock busy
- required result missing/unreadable/truncated
- unexpected exit/timeout/signal
- scheduler/service failure
- expected phase/result contract violation

Abnormal-run record는 machine-observed execution fact만 담는 compact immutable
evidence다.

대표 field category:

- record/run identity
- occurred/recorded time
- status / failure class / failed phase
- hard-failure / lock-busy / partial-commit fact
- write outcome counts
- scheduler/service invocation correlation
- application code provenance
- evidence references

Root cause, resolution, human notes, full traceback, full stderr, provider raw
payload는 abnormal-run record에 복제하지 않는다.

Retention:

```text
R2: fixed expiry 없이 long-term
Cloud recent copy: durable off-host verification 이후 cleanup 가능
```

## Incident Evidence

Abnormal run 중 다음 성격을 가진 사건은 incident로 승격할 수 있다.

Controlled promotion reasons:

```text
partial_commit
data_integrity_risk
repeated_failure
unknown_cause
manual_intervention
missed_expected_execution
monitoring_gap
recovery_or_rollback_required
unexpected_termination_or_evidence_loss
operational_decision_significance
```

### Human-managed incident record

Open incident의 canonical human record는 public PMTS repo가 아니라 private,
version-controlled operator store에 둔다.

Machine evidence와 human interpretation을 분리한다.

- abnormal-run record:
  - machine-generated
  - immutable
  - 발생 당시 fact
- incident record:
  - human-managed
  - mutable
  - promotion reason, impact, root cause, mitigation, resolution, follow-up

Incident status vocabulary:

```text
open
mitigated
resolved
closed
```

Root-cause status vocabulary:

```text
unknown
suspected
confirmed
inconclusive
```

Incident가 closed되기 전에는 조사에 필요한 forensic evidence를 age만으로
prune하지 않는다.

Closed incident의 final snapshot은 R2에 long-term 보존할 수 있다.

중요한 incident만 full forensic bundle을 Desktop HDD에 selected archive한다.

모든 failure tree를 blanket long-term archive하지 않는다.

## PostgreSQL Recovery

PostgreSQL recovery는 R2의 최우선 responsibility다.

Current recovery objective:

```text
RPO = 6시간
RTO = 24시간
```

초기 mechanism은 verified logical dump + off-host R2 storage다.

Sub-hour RPO가 실제 requirement가 되기 전에는 WAL archiving/PITR를 기본
contract로 도입하지 않는다.

### Recovery generation baseline

```text
6-hourly: 최근 8 generations
daily:    7
weekly:   4
monthly:  3
milestone: migration/cutover/중요 변경 시 explicit pin
```

Rotation은 다음 조건 뒤에만 허용한다.

```text
new backup
→ dump/checksum/manifest verification
→ R2 copy verification
→ older generation rotation
```

Recovery artifact는 실제 restore 가능성이 검증되어야 한다.

Restore smoke는 recovery implementation 이후 수행하며 recovery procedure 또는
schema가 의미 있게 바뀌면 재검토한다.

## Relationship to `garage-shared-artifact-contract.md`

이 ADR은
[`garage-shared-artifact-contract.md`](./garage-shared-artifact-contract.md)의
전체 history를 폐기하지 않는다.

Preserve:

- S3-compatible portable object boundary
- full runtime directory mirror가 아닌 selected artifact inventory 원칙
- immutable run-scoped object를 사용할 수 있는 contract

Supersede for current retention responsibility:

- Desktop authority가 R2 writer이고 MacBook이 read-only consumer라는
  topology assumption
- shared-development transport artifact와 long-term retention artifact를
  동일한 inventory로 보는 해석
- historical shared subset을 current indefinite R2 responsibility로 보는
  해석

Current R2 responsibility는 PostgreSQL recovery와 selected retained evidence가
우선한다.

Existing shared objects를 이 ADR만으로 즉시 삭제하지 않는다. Current consumer
verification과 별도 destructive Human Gate 뒤에서 cleanup한다.

## Relationship to `cloud-runtime-authority-and-off-host-recovery-boundary.md`

이 ADR은
[`cloud-runtime-authority-and-off-host-recovery-boundary.md`](./cloud-runtime-authority-and-off-host-recovery-boundary.md)
가 후속 contract로 남겨둔 retention/recovery 항목을 구체화한다.

구체적으로 다음을 채운다.

- Cloud local bounded retention
- source/derived/rebuildable/disposable classification
- PostgreSQL RPO/RTO
- recovery generation retention
- off-host selected evidence
- Desktop HDD long-term archive
- archive verification-before-prune boundary

PostgreSQL authoritative-state boundary와 provider-portable Linux/S3-compatible
방향은 유지한다.

## Consequences / Trade-offs

- Historical source evidence를 모두 PostgreSQL에 억지로 넣지 않고 source
  archive responsibility를 별도로 유지한다.
- 일부 source evidence는 HDD에서 매우 오래 보존될 수 있지만 단일-disk
  durability risk가 남는다.
- R2는 더 durable한 additional copy를 제공할 수 있지만 Free-tier budget
  때문에 전체 archive authority로 사용하지 않는다.
- Routine result/meta/log를 long-term archive하지 않으므로 old execution
  detail 일부는 의도적으로 사라진다.
- Abnormal/incident evidence를 별도로 compact하게 보존해 그 손실을 완화한다.
- 30일 local window는 simple baseline이지만 unresolved incident와 archive
  verification condition 때문에 hard TTL은 아니다.
- PostgreSQL logical-dump recovery는 현재 규모에 단순하지만 continuous PITR과
  동일한 recovery capability를 제공하지 않는다.
- Archive/prune contract를 운영하려면 manifest/checksum, verification,
  observability, Human Gate가 필요하다.

## Explicit Non-goals

- PostgreSQL historical facts를 age-based cold tier로 이동하기
- R2를 production database 또는 serving authority로 사용하기
- full `tmp/` 또는 full runtime filesystem mirror
- automatic age-only destructive lifecycle
- Parquet/Iceberg를 production authority로 승격
- Airflow/Dagster adoption 또는 orchestration rewrite
- persistent journald/Loki/centralized logging 도입
- archive compression format의 final implementation 선택
- bucket name, exact prefix, shell/Python implementation, systemd timer name 확정
- backup/pruning/archive mutation을 이 ADR 자체로 승인

## Implementation Boundary

Implementation은 작은 slices로 분리한다.

후속 candidate:

1. Chzzk `code_revision` / `code_dirty` provenance
2. abnormal-run record generation
3. private incident-record template/contract
4. source archive copy + manifest + checksum verification
5. Chzzk cleanup dry-run
6. Steam cleanup dry-run
7. guarded first production pruning
8. abnormal/closed-incident R2 publish
9. PostgreSQL 6-hourly recovery schedule + rotation
10. PostgreSQL restore smoke
11. historical shared-artifact consumer verification / retirement
12. Price Bronze compression/representation optimization
13. `ccu.daily-rollup-result.jsonl` compact-summary replacement

Archive creation/verification과 destructive prune을 첫 implementation slice에
함께 묶지 않는다.

## Human Gate

다음은 별도 Human Gate 없이 실행하지 않는다.

- first production Cloud artifact deletion/pruning
- R2 object deletion
- legacy shared-object cleanup
- first destructive PostgreSQL recovery rotation
- R2 Free-tier를 넘어서는 paid usage
- WAL/PITR/replication 같은 recovery topology 확대

## Revisit Triggers

다음 상황에서 이 결정을 재검토한다.

- R2 Free-tier capacity가 current priority를 감당하지 못함
- Desktop HDD 단일-copy durability가 더 이상 받아들일 수 없음
- source artifact growth가 current archive strategy를 압박함
- historical replay에서 retained metadata/provenance가 부족함이 확인됨
- RPO/RTO requirement가 강화됨
- App Catalog 또는 다른 deferred source collection이 다시 활성화됨
- current rebuildability assumption이 replay smoke에서 깨짐
- privacy/provider terms가 raw/source evidence의 장기 보존을 제한함
- incident evidence가 current compact schema로 충분하지 않음
