# PostgreSQL recovery rotation collection and snapshot classifier

`POSTGRES-RECOVERY-ROTATION-DRYRUN-001` (A7) Phase 1은 명시적인 inventory/evidence snapshot, policy, Human-managed pin snapshot을 deterministic advisory report로 변환한다. 구현은 [`recovery.rotation_dryrun`](../../src/recovery/rotation_dryrun.py)에 있으며, filesystem, PostgreSQL, R2, scheduler 또는 현재 시각을 읽지 않는 Python API다. Phase 2 collection adapter는 별도 [`recovery.rotation_collect`](../../src/recovery/rotation_collect.py)에 있다. CLI, persistent pin store 또는 deletion executor는 제공하지 않는다.

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

A1/A2의 기존 return object 자체에는 모든 binding field가 들어 있지 않다. Phase 2 collector는 실제 verifier 결과와 그 검증 대상 manifest bytes, timestamp, 안정성 관찰을 연결한다. Phase 1의 `VerificationEvidence`는 그 연결을 명시하는 caller-supplied attestation이다. `evidence_ref`나 digest가 존재한다는 사실만으로 실제 artifact 검증, source authenticity 또는 current production health를 증명하지 않는다. Synthetic tests의 PASS도 실제 inventory evidence가 아니다.

`local_complete`, `r2_complete`, `stable`은 정확한 `True`여야 하며 대응 evidence reference가 필요하다. `None`, `False`, 누락된 authority/reference는 전체 candidate set을 차단한다. `limitations`는 report에 그대로 남기는 관찰 한계다. Completeness 또는 stability를 부정하는 한계가 있으면 호출자는 대응 state를 `True`로 전달해서는 안 된다. Collector의 pagination, concurrent change, verification binding과 안정성 확보 방법은 아래 Phase 2 contract를 따르며 별도 Fresh-context review 대상이다.

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

## Phase 2 collection API

`collect_inventory(...)`는 explicit `recovery_root`, 새 `attempt_dir`, 주입된 `InventoryStore`, `CollectionAuthority`, `CollectionLimits`, `PinSnapshot`, `snapshot_id`, `evidence_ref`를 받는다. Ambient environment, credential file, production target 또는 pin store를 탐색하지 않는다. Client 구성과 외부 authority 확인은 호출자의 책임이다. API의 reference 문자열은 permission enforcement나 Human approval 자체가 아니다.

`CollectionAuthority`에는 `handoff_ref`, `target_ref`, `r2_read_only_ref`, `local_identity_ref`, `local_write_capable`을 명시한다. Missing reference 또는 미확인 local write capability는 I/O 전에 거부한다. Provider-enforced R2 read-only 권한을 검증한 reference가 필요하며, application이 GET만 호출한다는 이유로 publish credential을 재사용하지 않는다. Local identity가 source에 write capability를 가지면 `local_write_capable=True`로 private evidence에 드러낸다. 이 field는 OS 권한을 변경하거나 capability를 제거하지 않는다.

`CollectionLimits`는 `max_local_entries`, `max_dump_bytes`, `max_local_bytes`, `max_pages`, `max_objects`, `page_size`, `max_page_bytes`다. Local entry limit는 각 directory enumeration에, local byte budget는 각 local pass 전체에, LIST page/object budget는 각 R2 pass에 적용한다. Manifest는 64 KiB, checksum은 256 bytes로 제한한다. Dump는 A2의 기존 supported size boundary를 넘지 않는다. A2 GET은 verified local manifest/checksum/dump bounds를 유지한다. Page/object/byte budget는 wall-clock deadline이 아니며 transport의 시간 제한이나 중단은 별도 execution 환경의 책임이다.

한 호출은 다음 순서를 정확히 한 번 수행한다.

```text
L0 → R0 → V → R1 → L1
```

- `L0`: authoritative root의 `completed` direct children 전체를 열거하고 directory/file identity, size, mtime/ctime, SHA-256을 관찰한다. Source directory는 lexical absolute path의 각 component를 `dir_fd`와 `O_NOFOLLOW`로 연다. Regular file만 bounded read하며 symlink/special file, unsafe ID, duplicate-key/malformed manifest, missing/extra file, inaccessible entry 또는 budget failure를 정상 inventory에서 제외하고 계속 성공으로 표시하지 않는다. 읽은 동일 bytes를 private capture에 새로 기록한다.
- `R0`: `postgres-recovery/v1/` 전체를 첫 token 없이 pagination한다. Generation ID나 `scheduled-*` filter를 사용하지 않는다. Grouping과 exact manifest/dump/checksum key shape는 collector가 소유한다. Configured S3 `key_prefix`는 transport에서 한 번 매핑하고 결과는 portable key로 반환한다.
- `V`: 각 valid capture에서 actual A1 `verify_generation(...)`을 호출한다. A1 PASS가 있으면 actual A2 `verify_remote_generation(...)`을 호출해 독립 GET/read-back과 기존 remote-derived A1 verification을 수행한다. Live source는 이 verification에 다시 전달하지 않는다. Evidence는 exact manifest SHA-256, generation ID, verified completion timestamp, actual verification timestamp, verifier name, PASS/FAIL과 sanitized issue를 보존한다. LIST metadata는 A2 PASS를 만들지 않는다.
- `R1`: 이전 token을 재사용하지 않고 prefix 전체를 다시 pagination한다.
- `L1`: source를 다시 열어 completed inventory와 fingerprints를 비교한다. `staging`은 두 local pass에서 별도 name/type/identity observation으로 남기며 retention quota에 넣지 않는다. Staging 내부 bytes는 읽지 않고 staging 변화 자체를 completed instability로 취급하지 않는다. Staging observation이 실패하면 local completeness를 주장하지 않는다.

`ListObjectsV2` page operation은 기존 S3-compatible signing/transport를 재사용한다. Bucket path와 canonical query를 서명하고 opaque `NextContinuationToken`을 변형 없이 다음 요청에 전달한다. XML/page shape, returned prefix/bucket/count, missing token, repeated/cyclic token, duplicate/unaccountable key, incomplete chain과 budget exhaustion은 fail closed한다. Protocol reference는 [AWS ListObjectsV2](https://docs.aws.amazon.com/AmazonS3/latest/API/API_ListObjectsV2.html)다.

`L0/L1` completed fingerprints 또는 `R0/R1` object metadata가 다르면 `stable=False`다. Partial inventory를 합치거나 새 generation을 기존 snapshot에 편입하지 않는다. Scheduler lock, stop/pause/delay, retry/stabilization loop는 없다. 이 관찰은 여러 page/GET 전체의 transactional snapshot을 증명하지 않으며 관찰 사이에 발생했다 사라진 ABA change를 배제하지 않는다. 한계는 frozen input/report에 남는다.

Local/R2-only, partial/ambiguous state와 실패한 verification을 보존한다. R2-only generation에는 local authoritative reference가 없으므로 A2 PASS를 부여하지 않는다. LIST file set/size와 capture가 충돌하면 R2 completeness를 주장하지 않는다. Required A1/A2 evidence가 하나라도 없거나 FAIL이면 adapter가 `InventorySnapshot.authority_ref=None`으로 collection attestation을 보류한다. Phase 1의 기존 `inventory_authority_missing` blocker와 `required_verification_authority_missing` limitation이 전체 candidate set을 차단한다. 원래 handoff reference와 개별 evidence는 private evidence에 남는다. Phase 1 classification/retention semantics는 변경하지 않는다.

## Private capture와 replay

`attempt_dir`는 authoritative recovery root와 ancestor/descendant 관계가 없는 새 private directory여야 한다. 기존 directory를 재사용하거나 output을 overwrite하지 않는다. Directory는 `0700`으로 새로 생성하며 source file/permission/ownership은 변경하지 않는다. Parent destination은 호출자가 미리 승인한 trusted private boundary여야 한다. Collector는 다음 파일을 exclusive create한다.

| Artifact | Role |
| --- | --- |
| `captures/<generation_id>/...` | L0에서 실제 읽은 manifest/checksum/dump bytes; A1/A2 local reference |
| `input.json` | `postgres-recovery-rotation-collection/v1` envelope의 frozen Phase 1 inventory, pins, accepted policy |
| `report.json` | Phase 1 `render_report` 결과; advisory classification |
| `evidence.json` | Authority/limits, observation 시각과 `L0/R0/V/R1/L1`, staging, private references, input/report digest |

`evidence_ref`는 이 attempt의 private `evidence.json` reference로 지정한다. `#V/<generation_id>/local`과 `/r2`는 `V` row의 verifier evidence를, `#completeness`와 `#stability`는 두 pass 및 issue 비교를 가리키는 논리적 selector다. Raw keys, target mapping, pin input, capture와 generated artifacts는 private operational evidence이며 public repository나 `dev-notes`에 commit하지 않는다. Public evidence에는 revision, synthetic validation/review 결과, sanitized aggregate와 private reference만 남긴다.

Collector는 capture를 삭제하거나 정리하지 않는다. 예외로 중단된 attempt도 partial private directory를 남길 수 있으며 재사용/자동 retry하지 않는다. 기존 A2 내부 temporary verification materialization의 lifecycle은 유지한다. Source recovery generation과 R2 object에는 mutation을 수행하지 않는다.

`replay_frozen_input(payload)`는 JSON string을 받아 동일한 Phase 1 report string을 반환한다. Filesystem, network, PostgreSQL, scheduler, clock을 읽지 않는다. Duplicate JSON key와 unsupported envelope는 거부한다. Frozen input은 caller-supplied attestation이며 replay 성공이나 artifact hash가 source authenticity를 증명하지 않는다. 같은 frozen input의 report는 collection 이후에도 동일하며 input enumeration 순서에도 독립적이다.

## Phase 3 preconditions

Phase 2 implementation/synthetic validation은 production access 또는 A7 closure를 승인하지 않는다. 별도 read-only Fresh-context review와 Human merge decision 뒤에도 Phase 3에는 새로운 explicit production read-only handoff가 필요하다. Handoff는 exact target/root, execution identity, R2 target, provider-enforced read-only credential과 safe injection evidence, Human-confirmed pins, limits, private destination과 정확히 한 collection attempt를 고정해야 한다.

Read-only identity가 있으면 우선 사용한다. Credential/injection, user/group, ownership, permission/ACL, sudo/policy 또는 launcher preparation이 필요하면 별도 authority decision으로 되돌린다. Collector API는 이를 provision하거나 production 준비를 자동 확인하지 않는다. Scheduler는 계속 active한 baseline이며 coordination lock을 획득하지 않는다. Unstable attempt의 추가 실행에는 새 handoff가 필요하다.

A7 전체 `PASS / CLOSED`에는 reviewed/merged Phase 2 외에도 승인된 Phase 3 actual inventory evidence, deterministic replay, expected retained set의 independent comparison과 unresolved global blocker 부재가 필요하다. Empty candidate set 자체는 PASS가 아니다. Phase 2 완료 시 A7은 open이며 Phase 3 production handoff/actual dry-run은 별도로 남는다. A8은 선택하거나 시작하지 않는다.

## Validation과 completion boundary

```bash
poetry run pytest tests/recovery/test_rotation_dryrun.py tests/recovery/test_rotation_collect.py tests/steam/ingest/test_s3_compat.py
./scripts/check.sh
git diff --check
```

Focused tests는 latest-8, sparse observed buckets, ISO week-year, 대표 generation, overlapping reasons, timestamp ties/input permutations, invalid/conflicting verification, pin authority와 binding failure, incomplete/unstable inventory, empty-but-blocked report를 검증한다. I/O guard test는 classifier와 renderer가 filesystem/network/process operation 또는 destructive operation을 호출하지 않는지 확인한다.

Phase 2 tests는 synthetic source와 fake HTTP transport에서 actual A1/A2 호출, exact-bytes binding, full-prefix pagination, malformed response/token/budget failure, source 변화, pin authority와 replay를 검증한다. Production access나 current inventory evidence를 사용하지 않는다.

Phase 1/2 구현·fixture validation은 A7 전체 `PASS / CLOSED`가 아니다. Fresh-context review는 별도 read-only session에서 수행한다. 이후 local/R2 collection path review, explicit production read-only handoff, actual current-inventory dry-run evidence가 필요하다. 이 module은 production 접근, scheduler invocation, persistent pin 관리, 실제 rotation 또는 A8 선택·실행을 승인하지 않는다.
