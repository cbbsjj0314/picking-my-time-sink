# PostgreSQL recovery scheduler contract

이 문서는 A5 scheduler-facing recovery runner의 durable execution contract와
A6 production activation 경계를 정의한다. A5 구현 자체는 production scheduler를
설치하거나 활성화하지 않는다.

## One-run boundary

외부 scheduler 또는 사람이 다음 CLI를 한 번 호출하면 recovery generation 하나를
생성하고 독립적인 remote verification까지 완료한다.

```bash
python -m recovery.scheduled_backup \
  --root <recovery-root> \
  --database-logical-name <plain-database-name> \
  --lock-path <shared-lock-file>
```

실행 순서는 다음과 같다.

```text
shared overlap guard
→ actual invocation start의 UTC generation ID
→ A1 create_generation(...)
→ A1 verify_generation(...)
→ A3 run_preflight(...)
→ A3 publish_generation(...)
→ A2 conditional publish + independent GET/read-back verification
→ scheduled_recovery=PASS
```

각 단계가 성공해야 다음 단계로 진행한다. Local verification 전에는 R2 client를
생성하거나 publish하지 않는다. Remote read-back verification이 성공하지 않으면
전체 invocation은 PASS가 아니다.

Generation ID는 실제 invocation start를 나타내는 다음 형식이다.

```text
scheduled-YYYYMMDDTHHMMSSZ
```

Invocation 동안 같은 ID를 local staging/completed directory와 R2 namespace에
사용한다. 같은 초의 local 또는 remote collision은 overwrite, delete, suffix 생성,
다른 generation 선택 없이 fail-closed한다. Missed schedule의 과거 slot timestamp를
generation ID로 사용하지 않는다.

## Overlap and failure behavior

모든 scheduled/manual A5 invocation은 root가 달라도 같은 `--lock-path`를 사용해야
한다. Runner는 existing trusted parent 아래에서 symlink가 아닌 regular lock file을
안전하게 열거나 만들고 nonblocking exclusive `flock`을 획득한다. Lock file은
unlink, replace, truncate하지 않으며 credential, path, process metadata를 기록하지 않는다.

Guard는 generation identity 결정 전부터 remote verification 완료까지 유지한다.
Default `pg_dump` child도 lock descriptor를 상속하므로 runner parent가 비정상 종료해도
살아 있는 dump child가 종료될 때까지 겹치는 A5 invocation이 차단된다. Standalone A1/A3
CLI는 이 shared A5 lock contract에 포함되지 않는다.

Lock contention은 다음 sanitized 결과와 exit code `75`를 반환한다.

```text
ERROR: scheduled recovery failed: overlap
```

다른 실패는 exit code `1`과 고정된 sanitized category를 반환한다. Raw exception,
provider response, credential, private path는 stdout/stderr에 포함하지 않는다. 성공은
다음 네 줄과 exit code `0`으로만 확정한다.

```text
generation=<safe-generation-id>
local_verification=PASS
remote_verification=PASS
scheduled_recovery=PASS
```

Runner에는 automatic retry, restart loop, cleanup, generation rotation/delete, restore,
generation switching이 없다. 실패 시 A1/A2 contract에 따라 남은 local evidence와 이미
검증된 remote object를 삭제하지 않는다. 다음 schedule opportunity 또는 별도 승인된
manual follow-up이 다음 invocation을 소유한다.

## Scheduler semantics and RPO

현재 nominal target은 UTC 기준 하루 네 번의 opportunity다.

```text
00:00 UTC
06:00 UTC
12:00 UTC
18:00 UTC
```

이 cadence는 runner business logic에 들어 있지 않다. Host/timer downtime으로 하나
이상의 opportunity를 놓치면 scheduler는 필요할 때 최대 한 번 catch-up하고 과거 slot을
모두 replay하지 않아야 한다.

```text
6-hour timer configured != RPO <= 6h proven
```

RPO evidence는 remote-verified generation의 실제 age/cadence와 `pg_dump`부터 independent
verification까지 걸린 시간을 기준으로 판단한다. A6에서 첫 recurring evidence를 측정하고
필요하면 production cadence를 6시간보다 짧게 조정한다.

## Credential and A6 deployment boundary

Runner는 기존 `PMTS_RECOVERY_R2_*` environment contract와 libpq/`pg_dump` credential
boundary를 재사용한다. Application code는 root-only credential file을 직접 읽지 않으며
secret을 argv 또는 output에 넣지 않는다.

A6는 production host에서 다음 prerequisite와 exact deployment를 결정하고 Human Gate 뒤에
수행한다.

- 하나의 authoritative shared lock path와 existing trusted parent
- `flock` semantics가 적합한 local Linux filesystem
- least-privilege service identity와 credential/environment handoff
- exact recovery root, checkout revision, service/timer definition, UTC cadence
- `Type=oneshot`, automatic restart 없음, one-catch-up/no-backlog-replay semantics
- capacity readiness, existing scheduler interaction, first recurring execution evidence
- `systemd-analyze calendar`를 통한 exact `OnCalendar=` 검증

A5는 filesystem type을 probe하지 않고 systemd unit template을 제공하지 않는다. Production
unit install, daemon reload, enable/start, service identity/permission/config mutation, recurring
execution은 모두 A6 범위다. A5 merge는 이러한 mutation을 승인하지 않는다.
