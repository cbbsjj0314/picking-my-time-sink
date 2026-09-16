# PostgreSQL recovery rotation snapshot classifier

`POSTGRES-RECOVERY-ROTATION-DRYRUN-001` (A7) Phase 1은 명시적인 inventory/evidence snapshot, policy, Human-managed pin snapshot을 deterministic advisory report로 변환한다. 구현은 [`recovery.rotation_dryrun`](../../src/recovery/rotation_dryrun.py)에 있으며, filesystem, PostgreSQL, R2, scheduler 또는 현재 시각을 읽지 않는 Python API다. Collector, CLI, persistent pin store 또는 deletion executor는 제공하지 않는다.

Retention 기준은 [accepted ADR](../decisions/operational-data-retention-and-archive-boundary.md#recovery-generation-baseline)이다. [Scheduler contract](./postgres-recovery-scheduler.md)의 generation 생성·publish·cadence·retry·restore behavior는 변경하지 않는다.

## Input과 authority

호출자는 다음 frozen dataclass로 하나의 retention 대상 inventory를 명시한다. Collection 경계, snapshot authority와 verification evidence를 확보하는 책임은 호출자에게 있다. Phase 1은 이를 수집하거나 reference를 dereference하지 않는다. 이 API는 typed in-memory input을 받으며 외부 JSON을 검증·변환하는 adapter가 아니다.

| Input | Required content |
| --- | --- |
| `InventorySnapshot` | `snapshot_id`, `authority_ref`, `generations`, `local_complete`, `r2_complete`, `stable`, `completeness_evidence_ref`, `stability_evidence_ref`, `limitations` |
| `GenerationSnapshot` | `generation_id`, `manifest_sha256`, `completed_at_utc`, `local`, `r2` |
| `VerificationEvidence` | `verifier`, `status`, `evidence_ref`, `generation_id`, `manifest_sha256`, `completed_at_utc`, `verified_at_utc`, `issues` |
| `PinSnapshot` | Human confirmation을 가리키는 `authority_ref`, `confirmed`, 명시적인 `pins` tuple |
| `MilestonePin` | `generation_id` + `manifest_sha256` |
| `RetentionPolicy` | `recent=8`, `daily=7`, `weekly=4`, `monthly=3` |

`generation_id`는 A1과 같은 safe identifier이고 manifest SHA-256은 정확한 manifest bytes의 lowercase 64-character digest다. Timestamp는 A1과 같은 second-precision `YYYY-MM-DDTHH:MM:SSZ`다. `completed_at_utc`는 검증된 A1 manifest field이며 generation 이름, object modification time, collection time 또는 verification time에서 추정하지 않는다. `verified_at_utc`는 해당 evidence의 검증 시점이며 completion보다 이르면 충돌이다.

`local`은 A1 `recovery.postgres_artifact.verify_generation`의 성공 결과에 bind한다. 이는 manifest contract, generation identity, timestamp, custom dump, size, dump checksum과 checksum file의 일치를 검증한 결과다. `r2`는 A2 `recovery.r2_publish.verify_remote_generation`의 성공 결과에 bind한다. A2는 독립적으로 GET/read-back한 manifest/checksum/dump를 materialize하고 A1 verification 및 local과의 manifest/checksum bytes·dump checksum 일치를 확인한다. Phase 1은 두 함수를 호출하지 않는다.

두 evidence 모두 `status="PASS"`, 비어 있지 않은 `evidence_ref`, 빈 `issues`, generation과 일치하는 ID/digest/completion timestamp, 유효한 verification timestamp를 가져야 `verified`로 분류한다. Missing 또는 failed evidence, unsupported verifier, invalid timestamp, missing reference는 `keep_unverified`다. R2 LIST, object existence, ETag, manifest의 `verification_status`, scheduler의 요약 PASS 문자열은 이 evidence를 대체하지 않는다.

A1/A2의 기존 return object 자체에는 모든 binding field가 들어 있지 않다. 후속 reviewed collector는 실제 verifier 결과와 그 검증 대상 manifest bytes, timestamp, 안정성 관찰을 연결해야 한다. Phase 1의 `VerificationEvidence`는 그 연결을 명시하는 caller-supplied attestation이다. `evidence_ref`나 digest가 존재한다는 사실만으로 실제 artifact 검증, source authenticity 또는 current production health를 증명하지 않는다. Synthetic tests의 PASS도 실제 inventory evidence가 아니다.

`local_complete`, `r2_complete`, `stable`은 정확한 `True`여야 하며 대응 evidence reference가 필요하다. `None`, `False`, 누락된 authority/reference는 전체 candidate set을 차단한다. `limitations`는 report에 그대로 남기는 관찰 한계다. Completeness 또는 stability를 부정하는 한계가 있으면 호출자는 대응 state를 `True`로 전달해서는 안 된다. 후속 collector의 pagination, concurrent change, verification binding과 안정성 확보 방법은 별도 review 대상이다.

Confirmed empty pins는 `PinSnapshot(authority_ref="<human-evidence-reference>", confirmed=True, pins=())`다. `pins=None`, missing authority 또는 미확인 `confirmed`는 empty list와 다르며 전체 candidate set을 차단한다. Pin은 매칭되는 verified generation이 있어야 한다. Missing/ambiguous generation, manifest mismatch, invalid binding, conflicting pins 또는 unverifiable pinned generation도 전체 set을 차단한다. 정상적으로 확인된 다른 pin의 `keep_milestone` reason은 advisory report에 보존한다.

## Deterministic retention

현재 지원하는 policy는 integer `8/7/4/3`뿐이다. 다른 값이나 bool/float quota는 `ValueError`로 거부한다. Policy를 암묵적으로 바꾸거나 TTL로 치환하지 않는다.

1. Verified generation을 `completed_at_utc` 내림차순, 동률이면 `generation_id` 오름차순으로 정렬한다.
2. 최신 8개에 `keep_recent`를 부여한다. `6-hourly`는 count-based latest-8이며 48-hour TTL이 아니다.
3. Verified generation이 있는 최근 observed UTC date 7개, ISO week-year/week 4개, calendar month 3개를 고른다. Empty bucket은 quota를 소비하지 않는다.
4. 각 bucket에서 같은 정렬의 첫 generation 하나에 `keep_daily`, `keep_weekly`, `keep_monthly`를 부여한다.
5. Matching explicit pins에 `keep_milestone`을 부여하고 모든 keep reason의 합집합을 보존한다.

`keep_unverified` generation은 calendar representative나 recent quota를 소비하지 않으며 age/count만으로 candidate가 되지 않는다. Duplicate generation ID는 동일 bytes로 반복되어도 ambiguous inventory로 취급한다. 두 row를 모두 report에 남기고 전체 candidate set을 차단한다. Evidence의 ID/digest/completion binding mismatch, PASS와 nonempty issues의 충돌, completion보다 이른 verification도 `conflicting_verification_evidence`로 전체 set을 차단한다.

모든 global prerequisite가 충족되고 verified이며 keep reason이 없는 generation에만 `eligible_for_rotation`을 부여한다. Global blocker가 있으면 이 generation은 `rotation_blocked`이고 `advisory_candidates`는 항상 비어 있다. 보존 대상은 기존 keep reason을 유지한다. Candidate가 비었다는 사실은 PASS 판정이 아니다.

## API와 report

```python
from recovery.rotation_dryrun import RetentionPolicy, classify_snapshot, render_report

# inventory and pins are explicit, caller-supplied typed snapshots.
report = classify_snapshot(inventory, policy=RetentionPolicy(), pins=pins)
report_json = render_report(report)
```

`classify_snapshot`은 input을 변경하지 않고 dictionary를 반환한다. `render_report`는 canonical JSON string과 마지막 newline만 반환하며 파일에 쓰거나 command를 출력·실행하지 않는다. Test fixture 구성 예시는 [`test_rotation_dryrun.py`](../../tests/recovery/test_rotation_dryrun.py)에 있다.

| Report field | Meaning |
| --- | --- |
| `contract_version` | `postgres-recovery-rotation-dryrun/v1` |
| `advisory_only` | 항상 `true`; destructive authority가 아님 |
| `input_sha256` | 정규화한 inventory/evidence, policy, pins의 SHA-256; authenticity proof가 아님 |
| `newest_order`, `policy` | 적용한 정렬 및 retention quota |
| `inventory`, `pins` | Snapshot/pin authority, completeness/stability state와 evidence reference, limitations |
| `candidate_set_status` | `advisory` 또는 `blocked`; production dry-run PASS/FAIL이나 A7 closure 상태가 아님 |
| `candidate_set_blocking_reasons` | 전체 candidate set 차단 reason 목록 |
| `generations` | 원래 binding/evidence, `verification`, `verification_reasons`, 모든 `classifications` |
| `advisory_candidates` | Advisory ID/digest bindings만 포함하며 path/object key/deletion command는 없음 |

Generation rows는 ID, manifest digest, normalized evidence 순서로 정렬한다. Pins, issues, limitations 및 reason 목록도 정규화하므로 같은 input의 enumeration 순서와 실행 시각은 report bytes에 영향을 주지 않는다. Report에는 생성 시각을 추가하지 않는다.

Report는 caller가 제공한 reference와 metadata를 보존한다. 실제 운영 input/report는 private evidence로 다루며 credentials, raw dataset, private provider detail을 input에 넣거나 public fixture·durable public note에 복사하지 않는다. Public validation은 synthetic identifiers와 references만 사용한다.

## Validation과 completion boundary

```bash
poetry run pytest tests/recovery/test_rotation_dryrun.py
./scripts/check.sh
git diff --check
```

Focused tests는 latest-8, sparse observed buckets, ISO week-year, 대표 generation, overlapping reasons, timestamp ties/input permutations, invalid/conflicting verification, pin authority와 binding failure, incomplete/unstable inventory, empty-but-blocked report를 검증한다. I/O guard test는 classifier와 renderer가 filesystem/network/process operation 또는 destructive operation을 호출하지 않는지 확인한다.

Phase 1 구현·fixture validation은 A7 전체 `PASS / CLOSED`가 아니다. Fresh-context review는 별도 read-only session에서 수행한다. 이후 local/R2 collection path review, explicit production read-only handoff, actual current-inventory dry-run evidence가 필요하다. 이 module은 production 접근, scheduler invocation, persistent pin 관리, 실제 rotation 또는 A8 선택·실행을 승인하지 않는다.
