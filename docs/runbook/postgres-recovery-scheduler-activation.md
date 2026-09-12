# PostgreSQL recovery scheduler production activation plan

이 문서는 A6 `POSTGRES-RECOVERY-SCHEDULER-ACTIVATE-001`의 production activation
계약을 정의한다. Phase 1은 완료되었고 Gate A는 별도 Human evidence로 승인되었지만,
Gate A production execution은 아직 수행하지 않았다. Gate B와 recurring activation은 Pending이다.

```text
Risk Level: High
Review Level: Fresh-context
Human Gate Required: Yes
Phase 1: Complete
Phase 1 Independent Review Status: Passed
Gate A Status: Approved
Gate B Status: Pending
Production recurring recovery: Inactive
Gate A production execution performed: No
```

Gate B가 `Pending`이므로 전체 Human Gate 작업과 A6는 아직 완료되지 않았다.

## Phase 1 readiness

Read-only production inspection에서 다음 readiness를 확인했다.

- A6 service/timer candidate 이름은 현재 production에 존재하지 않는다.
- Existing PMTS recurring timer 네 개는 scheduled 상태이고 failed unit은 없었다.
- Existing recovery root와 `completed`/`staging` 구조가 존재한다.
- Recovery root와 lock parent는 local XFS에 있고 현재 capacity/inode pressure가 없다.
- 현재 completed generation 크기는 약 21.6 MB이며 nominal 4 runs/day 기준 30-day
  no-rotation 신규 volume은 destination별 약 2.59 GB다.
- Existing recovery-specific PostgreSQL/R2 credential source는 root-only regular file이며
  systemd `EnvironmentFile=`의 conservative syntax check를 통과했다.
- PostgreSQL recovery connection은 IPv4 loopback의 dedicated role/database SCRAM rule을
  선택해야 한다.
- Production host는 systemd 239, Python 3.12, PostgreSQL 16 `pg_dump`를 제공한다.
- SELinux는 Disabled다. 이 사실은 readiness evidence일 뿐이며 SELinux mutation을
  승인하지 않는다.

Historical recovery tree의 이름이나 내용, credential value, provider endpoint/account,
private host identity는 public readiness evidence에 포함하지 않는다. Capacity projection은
현재 크기에 근거한 planning estimate이며 future growth 또는 provider cost를 보장하지 않는다.

```text
A6_PHASE1_READINESS=PASS
ADDITIONAL_PRODUCTION_INSPECTION_REQUIRED=NO
```

## A5 revision and execution boundary

Production recovery execution은 다음 A5 merged revision으로 고정한다.

```text
85ff91fc4613dc54e15673ac8eeedf6f06bd2c8d
```

Canonical one-run entrypoint는 `python -m recovery.scheduled_backup`이다. Production
application checkout 또는 기존 `/home/pmts` 아래 repository/worktree는 A6 execution
source로 사용하지 않는다. 해당 위치와 Git object store는 service identity가 변경할 수
있으므로, 사후 `chown`만으로 trusted provenance를 주장할 수 없다.

Gate A 뒤 다음 dedicated root-controlled checkout을 준비한다.

```text
/opt/pmts-recovery/revisions/85ff91fc4613dc54e15673ac8eeedf6f06bd2c8d
```

Primary materialization은 root-controlled empty destination에서 authoritative public GitHub
repository로부터 exact commit을 fresh fetch한 뒤 detached checkout하는 방식이다. Clean
process environment를 사용하고 interactive credential prompt, local-file transport, Git
template/hook, URL rewrite, alternate object directory를 허용하지 않는다. Submodule도
recursively materialize하지 않는다.

Production host가 authoritative remote를 fetch할 수 없으면 trusted operator environment에서
authoritative remote로부터 만든 self-contained Git bundle을 사용한다. Bundle은 prerequisite
object가 없어야 하고, empty verification repository에서 commit/object integrity를 확인하며,
독립적으로 기록한 SHA-256과 production transfer 뒤 digest가 일치해야 한다. Transfer와
함께 제공된 checksum만으로 provenance를 증명하지 않는다.

두 방식 모두 다음을 Gate A execution 전에 검증한다.

```text
HEAD = 85ff91fc4613dc54e15673ac8eeedf6f06bd2c8d
clean tracked tree
Git object integrity PASS
independent Git storage
no alternates/shared objects/linked-worktree dependency
root-controlled ownership
pmts cannot modify or replace code or code-bearing ancestors
```

Fetch/transfer, destination, object integrity 중 하나라도 예상과 다르면 materialization을
중단한다. `/home/pmts` repository에서 copy/fetch하거나 그 object store를 참조하는 fallback은
허용하지 않는다.

## Service identity and trusted layout

Proposed service identity는 existing production pattern을 재사용한다.

```text
User=pmts
Group=pmts
DynamicUser=no
SupplementaryGroups=
UMask=0027
```

`pmts`는 recovery artifact root에 필요한 read/write/traverse access를 이미 가진다. 새 account
또는 group을 만들지 않는다.

이 선택에는 explicit residual risk가 있다. Root-only environment file을 systemd가 읽은 뒤
credential은 recovery process environment가 된다. 같은 UID로 실행되는 다른 PMTS process가
host의 process-access boundary에 따라 이를 inspect할 가능성이 있으며, A5의 `pg_dump` child도
process environment를 상속한다. Root-only source file과 service sandbox는 same-UID runtime
exposure를 제거하지 않는다.

또한 `/var/lib/pmts`는 `pmts`가 쓸 수 있고 current approved recovery root도 `pmts`가 쓸 수
있는 상태다. 그 사이 recovery parent가 root-owned라는 사실만으로 writable-ancestor risk가
해결되지는 않는다. Human은 Gate A에서 이 shared-UID와 writable-ancestor residual risk를
명시적으로 승인해야 한다. 더 강한 isolation이 필요하면 A6 execution을 중단하고 별도
identity/access planning으로 돌아간다.

Pinned A5와 service sandbox를 함께 만족하려면 host filesystem permission은 다음 contract를
가져야 한다.

```text
approved recovery root:
- root-controlled
- service identity가 traverse 가능
- pmts가 write 불가능

approved recovery root/staging:
- pmts가 write/traverse 가능

approved recovery root/completed:
- pmts가 write/traverse 가능
```

Exact production owner/group/mode는 Gate A durable evidence에서 검증하고 승인한다. Current
recovery root가 `pmts` writable이므로 Gate A에서 root 자체를 non-writable로 만드는 narrow
ownership/permission handoff가 필요할 수 있다. 이 mutation은 Gate A 전에 수행하지 않는다.
또한 recursive하게 적용하거나 existing recovery evidence를 delete, move, truncate, rename,
rewrite해서는 안 된다. Existing `staging`과 `completed`는 pinned A5가 요구하는 access를
유지해야 한다.

이 boundary를 broader permission mutation 없이 설정할 수 없거나 existing recovery behavior를
깨뜨리면 중단하고 planning으로 돌아간다. Recovery root의 owner/mode 변경만으로 그 위
`/var/lib/pmts` writable-ancestor risk가 사라졌다고 주장하지 않는다.

Trusted execution layout은 다음 boundary를 사용한다.

| Artifact class | Owner/group and mode |
| --- | --- |
| `/opt/pmts-recovery`와 `revisions` directory | `root:root/0755` |
| Checkout directory / ordinary file | `root:root/0755`, `root:root/0644` |
| Git administrative directory / file | `root:root/0700`, `root:root/0600` |
| `/usr/local/libexec/pmts-postgres-recovery-launcher.py` | `root:root/0755` |
| `/etc/systemd/system/pmts-postgres-recovery.service` | `root:root/0644` |
| Authoritative lock file | `pmts:pmts/0600` |

Gate A validation은 owner/mode뿐 아니라 effective access, ACL, symlink target과 replaceable
ancestor를 확인한다. Launcher, checkout code, interpreter, imported standard-library/native
components 중 `pmts`가 변경하거나 교체할 수 있는 항목이 있으면 execution을 차단한다.

Production interpreter는 `/usr/bin/python3.12`, dump executable은 `/usr/bin/pg_dump`로
고정한다. A5의 existing `--pg-dump-executable` interface로 exact dump path를 전달하며 PATH
lookup에 의존하지 않는다. Virtualenv, dependency install 또는 A5 code change를 추가하지 않는다.

## Credential launcher contract

Systemd의 privileged service setup은 controlled evidence에서 승인한 root-only PostgreSQL과
R2 environment file을 읽는다. 두 source는 `root:root/0600`을 유지하고 copy, rewrite,
permission weakening 또는 rotation하지 않는다. Older rclone-era environment contract는 A6에
사용하지 않는다.

Launcher는 `pmts`로 실행되며 credential file을 직접 열지 않는다. 완전한 normative contract는
다음과 같다.

- Arbitrary command, executable path 또는 user-controlled argument를 받지 않는다.
- Approved service identity와 required input key set을 확인한다.
- PostgreSQL user가 approved recovery role인지 확인하되 supplied value를 출력하지 않는다.
- `PMTS_RECOVERY_POSTGRES_USER`를 `PGUSER`로 mapping한다.
- `PMTS_RECOVERY_POSTGRES_PASSWORD`를 수정하거나 strip하지 않고 `PGPASSWORD`로 mapping한다.
- `PGHOST=127.0.0.1`, `PGPORT=5432`를 고정한다.
- `PGCONNECT_TIMEOUT`을 설정하지 않는다.
- Inherited environment를 복사하지 않고 explicit allowlist로 새 environment를 구성한다.
- Custom PostgreSQL input 두 개는 final A5 environment에서 제거한다.
- Unapproved libpq selector, application credential, proxy, Python startup override를 제외한다.
- Missing/invalid input은 A5 실행 전에 fixed sanitized category와 exit code `1`로 거부한다.
- Secret, supplied value, raw exception 또는 private endpoint를 argv/stdout/stderr/journal에
  출력하지 않는다.
- `/bin/sh -c` 또는 다른 shell evaluation 없이 fixed `os.execve`를 사용한다.
- Lock, dump, publish, verification, retry, cleanup을 직접 구현하지 않고 A5에 위임한다.

Final environment allowlist는 다음과 같다.

```text
PGUSER
PGPASSWORD
PGHOST
PGPORT

PMTS_RECOVERY_R2_ENDPOINT_URL
PMTS_RECOVERY_R2_BUCKET
PMTS_RECOVERY_R2_REGION
PMTS_RECOVERY_R2_ACCESS_KEY_ID
PMTS_RECOVERY_R2_SECRET_ACCESS_KEY

PATH=/usr/bin:/bin
LANG=C.UTF-8
LC_ALL=C.UTF-8
TZ=UTC
TMPDIR=/tmp
PYTHONPATH=<exact-root-controlled-A5-checkout>/src
```

`PMTS_RECOVERY_R2_KEY_PREFIX`는 승인된 current source에 없으므로 final environment에도 넣지
않는다. 기존 empty-prefix behavior를 유지하며 optional setting 추가는 별도 reviewed approval이
필요하다.

Fixed A5 exec semantics는 다음과 같다.

```text
/usr/bin/python3.12 -S -B -P -u -m recovery.scheduled_backup
  --root <approved-recovery-root>
  --database-logical-name <approved-plain-database-name>
  --lock-path <approved-authoritative-lock-path>
  --pg-dump-executable /usr/bin/pg_dump
```

`-S`, `-B`, `-P`로 site initialization, bytecode write, automatic working-directory prepend를
제외한다. Credential value는 command argument에 포함하지 않는다.

## Authoritative shared lock

Gate A에서 controlled evidence로 승인한 existing trusted parent 아래에 하나의 lock file을
exclusive no-follow 방식으로 precreate한다. Parent permission은 바꾸지 않는다. File은 empty
regular file, `pmts:pmts/0600`이어야 하며 unexpected existing entry가 있으면 중단한다.

생성 직후 device/inode/path/metadata를 기록한다. Gate A manual execution과 이후 Gate B timer
execution은 모두 같은 service와 approved path/inode를 사용한다. A5 runner가 nonblocking
exclusive `flock`을 acquisition하고 `pg_dump` child까지 descriptor를 상속한다.

Lock file은 active/inactive 상태와 관계없이 unlink, truncate, replace, recreate 또는 cleanup하지
않는다. Standalone A1/A3 CLI는 이 lock contract에 포함되지 않으므로 production recurring/manual
A6 path에서 사용하지 않는다.

## systemd 239 service contract

Production service 이름은 `pmts-postgres-recovery.service`다. Rendered unit은 controlled
evidence에서 승인한 private environment paths와 canonical execution paths를 결합하되 다음
semantic contract를 정확히 유지한다.

```ini
[Unit]
Description=PMTS PostgreSQL recovery
After=network.target postgresql.service

[Service]
Type=oneshot
User=pmts
Group=pmts
DynamicUser=no
SupplementaryGroups=
UMask=0027

EnvironmentFile=<approved-root-only-postgres-recovery-environment-file>
EnvironmentFile=<approved-root-only-r2-recovery-environment-file>
WorkingDirectory=/opt/pmts-recovery/revisions/85ff91fc4613dc54e15673ac8eeedf6f06bd2c8d
ExecStart=/usr/bin/python3.12 -I -S -B /usr/local/libexec/pmts-postgres-recovery-launcher.py

Restart=no
TimeoutStartSec=1h
TimeoutStopSec=2min
KillMode=control-group
LimitCORE=0

NoNewPrivileges=yes
CapabilityBoundingSet=
PrivateTmp=yes
PrivateDevices=yes
ProtectSystem=strict
ProtectHome=yes
InaccessiblePaths=<approved-private-credential-directory>
ReadWritePaths=<approved-recovery-root>
ReadWritePaths=<approved-authoritative-lock-path>
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6

StandardOutput=journal
StandardError=journal
SyslogIdentifier=pmts-postgres-recovery
```

Unit에는 `[Install]` section이 없으며 service 자체를 enable하지 않는다. `After=`는 ordering만
정의하고 PostgreSQL을 start dependency로 끌어오지 않는다. Recovery root 하나를 common
writable mount exception으로 사용하는 것은 pinned A5 compatibility requirement다. A5는
`staging/<generation>`을 `renameat2(..., RENAME_NOREPLACE)`로
`completed/<generation>`에 atomic finalization한다. Source와 destination은 service mount
namespace에서 같은 mount에 있어야 하므로 separate `ReadWritePaths=` mount로 분리하지 않는다.
A5 implementation이나 atomic no-replace contract를 변경하지 않는다.

Common-root writable mount exception은 `pmts`에게 recovery root top-level mutation permission을
부여하는 계약이 아니다. Systemd mount namespace가 root를 writable하게 제공하더라도 앞에서
정의한 host filesystem permission이 top-level create/rename/delete를 막고 `staging`과
`completed` 내부 access만 허용해야 한다. Separate writable lock boundary는 그대로 유지한다.

`PrivateTmp=yes`는 A2 snapshot과 remote verification의 transient workspace를 제공하지만 recovery
evidence deletion을 승인하지 않는다.

이 contract는 systemd 239-compatible conservative directive만 사용한다. Materialized candidate를
native `systemd-analyze verify`로 확인하며 unknown/unsupported directive 또는 sandbox mismatch가
있으면 install/execution을 중단한다. Modern systemd credential feature 또는 newer-only hardening을
추가하지 않는다. SELinux가 Disabled이므로 `restorecon`, `semanage`, `chcon` 등 labeling mutation을
수행하지 않는다.

Timeout 또는 signal은 approved attempt의 failure다. `KillMode=control-group`은 dump child도 같은
failure boundary에 포함한다. Exit code `75` overlap은 success로 취급하지 않으며 automatic
restart/retry는 없다.

Success는 exit code `0`과 다음 sanitized output을 모두 요구한다.

```text
generation=<safe-generation-id>
local_verification=PASS
remote_verification=PASS
scheduled_recovery=PASS
```

다른 failure는 A5/launcher의 fixed sanitized category만 출력한다. Raw exception, credential,
private endpoint/provider response 또는 private path를 journal에 출력하지 않는다.

## Review and Human Gate sequence

### Before Gate A

Phase 1은 다음 sequence로 제한한다.

```text
read-only readiness
→ docs-only activation plan
→ Phase 1 Fresh-context review
→ Final status: Passed
→ durable human-authored GitHub review evidence
→ Gate A request
```

Phase 1 reviewer는 canonical A6 ticket, pinned A5 implementation/contract, sanitized readiness,
이 문서의 diff, complete normative launcher/service contract, trusted source-provenance requirements,
Gate A materialization/validation procedure와 residual risk를 검토한다.

`Final status: Passed`와 human-authored GitHub evidence 전에는 Gate A를 요청하지 않는다.
Launcher, service unit, lock file 또는 production A6 checkout은 Gate A 전에 materialize하지 않는다.
별도 private executable-reference review bundle도 만들지 않는다.

### Gate A conditional authorization

Gate A는 다음 exact mutation class만 승인할 수 있다.

- Approved `/opt/pmts-recovery` directory와 root-controlled independent checkout materialization.
- Approved launcher와 service candidate materialization.
- Approved authoritative lock의 exclusive creation과 owner/mode assignment.
- Approved recovery root의 root-non-writable/children-writable contract에 필요한 narrow,
  non-recursive ownership/permission handoff.
- Exact service unit installation과 그 unit을 위한 `daemon-reload`.
- Credential-free disposable mount-topology fixture의 temporary creation과 fixture-only removal.
- Review/validation 조건을 모두 만족한 뒤 exactly one manual service execution.
- 그 한 번의 production `pg_dump`, A1 staging/completed generation, conditional R2 publish 또는
  byte-identical reconciliation, independent remote verification.
- A2 transient workspace lifecycle와 normal systemd/journal record.

Gate A에서는 exact revision, source acquisition, execution layout, service identity, credential
handoff, recovery-root permission handoff, lock, service semantics, shared-UID/writable-ancestor risk,
disposable validation의 exact command/path, capacity/cost decision, mutation set과 execution count를
모두 사용 전에 review하고 승인해야 한다. Human-authored GitHub Gate evidence에는 public-safe
approved scope와 decision, review/result status, sanitized identifier를 기록한다. Public-safe하지
않은 exact operational selection은 사용 전에 configured private PMTS control plane에 durably
기록하고 review하며, public Gate evidence는 private value를 재출력하지 않고 그 controlled
evidence를 reference할 수 있다. Public evidence와 referenced private durable evidence를 합친
evidence set은 무엇을 승인했고 실제로 무엇을 사용했는지 재구성할 수 있어야 한다. Public
GitHub evidence에 private operational value를 재현하는 것은 Gate contract 충족 조건이 아니다.
이 구분은 evidence placement만 변경하며 Gate A mutation authority, execution sequence와 operational
safety requirement를 변경하지 않는다. 또한 execution은 다음 post-materialization review
condition에 종속된다고 명시해야 한다.

```text
materialize approved artifacts
→ STOP
→ exact-artifact Fresh-context review
→ Final status: Passed
→ durable human-authored GitHub evidence
→ credential-free disposable mount-topology validation
→ dummy-only synthetic validation
→ remaining pre-execution validation
→ exactly one production service execution
```

Gate A approval 자체는 이 condition을 bypass하는 권한이 아니다.

### Post-materialization exact-artifact review

Materialization 뒤 production execution 전에 새로운 Fresh-context read-only review를 수행한다.
Reviewer는 installed launcher, rendered/installed service unit, exact root-controlled A5 checkout을
직접 검토한다.

Required review scope:

- Exact launcher source와 rendered service unit.
- 이 문서의 normative contract conformance와 scope expansion 부재.
- Credential mapping, explicit environment filtering, fixed PGHOST/PGPORT.
- Secret-free argv/log behavior와 shell evaluation 부재.
- Exact A5 revision/path, trusted source provenance, independent Git storage.
- systemd 239 compatibility와 filesystem sandbox semantics.
- Trusted execution ancestry와 `pmts` non-writability.
- Shared lock path/inode contract와 unchanged A5 behavior.

Required reviewer output:

```text
Blocking findings
Non-blocking findings
Missing required evidence
Remaining uncertainty
Final status
```

Production execution은 `Final status: Passed`와 별도 durable human-authored GitHub evidence 전까지
금지한다. Reviewed launcher 또는 unit byte가 변경되면 review status는 `Pending`으로 돌아가고
production execution을 차단한다. 변경 artifact는 새 Fresh-context review가 필요하다.

### Disposable mount-topology validation

Exact-artifact review가 Passed이고 durable human-authored evidence가 기록된 뒤, production
execution 전에 credential-free transient validation을 수행한다. `systemd-analyze verify`만으로는
service mount namespace 안의 cross-directory rename topology를 증명할 수 없으므로 이 runtime
check가 필수다.

Exact command와 disposable path는 사용 전에 review한다. Production-specific exact command/path가
public-safe하지 않으면 configured private PMTS control plane의 durable evidence에 기록하고 review한다.
Public GitHub approval/review record에는 sanitized reference, approved validation class/boundary와
result/status를 기록하며 private exact command/path를 재출력할 필요가 없다. Mechanism은 persistent
unit을 install하지 않는 transient/disposable systemd execution이어야 하며 다음을 만족해야 한다.

- Production PostgreSQL/R2 credential file 또는 environment를 load하지 않는다.
- `pg_dump`, PostgreSQL authentication, R2 request를 수행하지 않는다.
- Actual recovery root를 inaccessible하게 만들고 그 아래 generation을 사용하지 않는다.
- Unique disposable root 아래에 `staging`과 `completed`를 만들고, 필요하면 separate disposable
  lock boundary를 만든다.
- systemd 239에서 `ProtectSystem=strict`, 하나의 common writable disposable root,
  separate lock exception이라는 relevant topology를 재현한다.
- Disposable `staging/<generation>`을 disposable `completed/<generation>`으로
  `RENAME_NOREPLACE` atomic rename하고 success를 확인한다.
- `EXDEV`, collision 또는 다른 unexpected result는 fail closed한다.
- Validation이 생성한 unique fixture만 bounded cleanup하고 actual recovery evidence는 inspect,
  rename, truncate, delete 또는 rewrite하지 않는다.

Transient validation을 위해 persistent service unit이나 Gate A 밖 mutation이 필요하면 즉석에서
추가하지 않고 planning으로 돌아간다. Validation failure는 production execution을 차단한다.

### Synthetic and remaining pre-execution validation

Exact-artifact review와 disposable mount-topology validation이 모두 Passed인 뒤 dummy value만
사용하는 transient synthetic validation을 수행한다. Test harness는 `os.execve` boundary를
intercept하며 production credential file, actual A5 runner, `pg_dump`, PostgreSQL authentication
또는 R2 operation을 사용하지 않는다.

Synthetic validation은 다음을 확인한다.

- Fixed argv와 exact `/usr/bin/pg_dump` argument.
- Literal value preservation과 custom PostgreSQL key removal.
- Exact final environment allowlist와 `PGCONNECT_TIMEOUT` 부재.
- Expected-user enforcement, missing-input rejection, sanitized failure.
- Shell evaluation과 secret-bearing argv/log 부재.

Synthetic test는 independent source/unit review를 대체하지 않는다. 실패하면 production
execution 전에 중단한다.

Remaining pre-execution checks:

1. Artifact path, hash, owner/mode, ACL과 symlink identity.
2. Exact commit, clean tree, Git integrity, no alternates와 trusted ancestry.
3. Recovery root의 root-non-writable/children-writable filesystem contract.
4. Disposable mount-topology atomic no-replace rename PASS evidence.
5. Secret-free CLI/import load with exact interpreter and site loading disabled.
6. Native `systemd-analyze verify` and loaded non-secret unit-property match.
7. Credential file metadata/syntax, lock device/inode/access, filesystem capacity.
8. Timer absent/inactive, no active recovery invocation, acceptable workload/failed-unit baseline.
9. PostgreSQL loopback listener continuity.

어느 check라도 실패하면 exactly-one service execution을 수행하지 않는다.

## Gate A one-time execution and evidence

Approved service를 exactly one time manual start한다. 다음을 기록한다.

- Runner revision, service identity, lock device/inode.
- Invocation start UTC와 generation identity.
- Local generation size와 verification result.
- Independent remote verification completion UTC.
- Start-to-remote-verification end-to-end duration.
- Service `Result`, `ExecMainStatus`, sanitized output.

Acceptance는 exit `0`, `Result=success`, `ExecMainStatus=0`, one fresh completed generation,
local A1 verification, remote-derived verification, unchanged lock identity와 no retry를 모두
요구한다.

Post-run에는 PostgreSQL listener, existing PMTS workload/timer health, failed units, filesystem
capacity, A6 timer absence를 확인한다. 실패 또는 incomplete result는 evidence를 보존하고
Human/planning으로 돌아간다. 같은 Gate A approval로 두 번째 run을 수행하지 않는다.

2026-09-12 Human 관측 기준 current R2 usage는 included tier 안에 있고 current billable usage는
`$0.00`이다. Current A6 30-day planning envelope도 current free storage boundary 아래에 있다.
이 sanitized current-state observation은 장기 paid R2 accumulation을 승인하지 않는다. R2
capacity/cost는 Gate B recurring activation 전에 다시 평가한다. Retention/rotation과 Desktop HDD
archive는 deferred boundary로 유지한다.

## Gate B recurring timer boundary

Gate B는 successful Gate A generation, independent remote verification, measured end-to-end
duration, workload sanity, capacity/cost reassessment 후에만 요청한다.

Gate B만 다음을 승인한다.

- `pmts-postgres-recovery.timer` definition과 exact UTC cadence/tolerance.
- Timer unit installation과 그 unit을 위한 `daemon-reload`.
- Timer enable/start와 unattended recurring execution.
- Initial recurring cadence observation.

Timer는 `Persistent=true`, downtime 뒤 at most one catch-up, no missed-slot backlog replay,
no automatic retry를 유지한다. Install 전에 exact unit을 `systemd-analyze verify`와
`systemd-analyze calendar`로 검증한다.

Nominal four-slot UTC cadence는 sizing candidate일 뿐 Gate B approval 또는 `RPO <= 6h` proof가
아니다. Gate A measured duration을 반영해 Human이 exact cadence를 승인한다.

Timer start만으로 A6를 완료하지 않는다. 서로 연속된 scheduler-triggered remote-verified
generation 두 개에 대해 invocation start, verification completion, duration, start-to-start와
verification-to-verification interval을 기록한다. Manual start는 recurring evidence를 대신하지
않는다.

Conservative recovery-age proxy는 다음과 같다.

```text
new verification completion
- previous successful generation invocation start
```

이 값을 accepted six-hour RPO target과 비교한다. Initial observation은 bounded evidence이며
모든 failure mode에서 장기 RPO를 보장한다는 의미가 아니다. Target을 만족하지 못하면 A6를
close하지 않고 cadence decision을 planning/Human Gate로 되돌린다.

## Failure, rollback, and deferred scope

어느 phase에서도 automatic service retry, `Restart=always`, retry loop, credential rotation,
stale-lock unlink, cadence auto-adjustment 또는 existing workload pause를 수행하지 않는다.

Gate B 뒤 blocking failure가 발견되면 Human에게 future scheduling stop/disable decision을
제시한다. Rollback은 future scheduling을 중지하는 것이며 생성된 local/R2 evidence를 삭제하는
것이 아니다.

다음은 A6 out of scope이며 별도 planning/Human approval을 요구한다.

```text
production application checkout mutation
A5 runner or application code change
new OS identity or broad permission redesign
unrelated or recursive ownership/permission mutation
PostgreSQL schema/data mutation or restore
recovery generation rotation/delete
R2 overwrite/delete/lifecycle mutation
credential creation/rotation/permission expansion
retention/archive implementation
A7/A8 work
```

A6 closure는 rotation/delete를 승인하거나 다음 ticket을 자동 선택하지 않는다.

## Public/private evidence boundary

Public evidence에는 다음 public-safe 정보를 기록할 수 있다.

```text
canonical/public revision identifiers
public-safe service/contract identifiers
generic/canonical deployment contract
sanitized aggregate capacity/cost conclusion
Human Gate decision and approved mutation class
review status/result
sanitized operational result
```

Production-specific exact detail이 public disclosure에 불필요하거나 안전하지 않으면 사용 전에
configured private PMTS control plane에 durably 기록하고 review한다. Private durable evidence에는
해당되는 경우 다음을 둔다.

```text
private credential/config source paths
private endpoint/account identifiers
exact host-specific operational selections
exact disposable fixture paths/commands
raw inspection output
raw journal/runtime evidence
other private runtime details
```

다음은 public document, PR body, review comment에 포함하지 않는다.

```text
credential/password/access-key value or value hash
private R2 endpoint/account identifier
private host identifier
raw credential/config contents
raw provider response or authorization header
unnecessary private filesystem identity
raw inspection transcript or raw journal
```

Public runbook의 exactness를 이유로 private detail을 복사하지 않는다. Human-authored public
Gate/review evidence는 reviewed private durable evidence를 sanitized reference로 가리킬 수 있지만
private/secret value를 재출력하지 않는다. Combined evidence set은 승인된 gated scope와 실제 사용한
operational selection을 재구성할 수 있어야 한다.

Private durable evidence만으로 Human Gate approval을 대체할 수 없다. Approval은 gated scope를
명확히 승인한 human-authored GitHub PR comment 또는 GitHub review여야 한다. Implementation agent의
completion report, self-review, synthetic test 결과 또는 ChatGPT conversation은 independent
review/Human Gate evidence가 아니다.

Phase-scoped pre-gate merge는 required validation, CI, Phase 1 Fresh-context `Passed`, blocking
finding/required-evidence gap 부재와 별도 Human merge decision을 모두 요구한다. Merge는 Gate A
approval이 아니며 A6는 Gate A/Gate B 및 recurring evidence 완료 전까지 open 상태다.
