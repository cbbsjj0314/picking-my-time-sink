# Agent Workflow Runbook

이 repo는 작은 PR-native workflow를 사용한다.

Spec -> Ticket -> Agent implementation -> PR -> CI -> Review -> Human Gate -> Release.

## 역할

- ChatGPT/planning session은 product spec을 정의하고, 작업을 ticket으로 나누며, human의 active ticket 선택을 지원하고 acceptance criteria를 명확히 한다.
- Codex는 human이 planning flow를 통해 명시적으로 선택·전달한 하나의 ticket을 구현하고, 집중된 branch/commit을 준비하며, ticket이 PR-native 실행으로 승인되면 작은 PR을 연다.
- 사람은 위험한 scope를 승인하고, PR을 review하며, merge를 결정하고, release를 제어한다.

## Ticket 내용

Ticket은 `User Decision`, scope, out of scope, requirements, acceptance criteria, required checks, manual QA, `Risk Level`, `Human Gate Required`, `Review Level`, `Review Reason`, suggested branch name, suggested PR title을 명시해야 한다. Behavior 또는 semantics에 적용할 수 있으면 `User Acceptance Examples`도 포함한다.

`Risk Level`, `Human Gate Required`, `Review Level`은 implementation 전에 확정한다. Implementation agent는 사전 결정된 세 값을 임의로 낮추지 않는다. 구현 중 scope 또는 위험이 커져 더 강한 gate가 필요해지면 구현을 계속하거나 자체 재분류하지 않고 planning 흐름으로 되돌린다.

하나의 ticket은 보통 하나의 PR에 대응한다. Ticket이 서로 관련 없는 runtime, schema, API, web, operations 변경을 섞고 있다면 구현 전에 작업을 나눈다.

## Ticket 선택 및 handoff

- Human이 planning flow에서 한 번에 하나의 active ticket을 명시적으로 선택한다.
- Codex는 선택된 ticket을 명시적으로 전달받은 뒤에만 implementation을 시작한다.
- Planning board, queue, candidate list는 execution context일 수 있지만 다른 ticket을 선택하거나 승격할 권한을 주지 않는다.
- Current ticket이 끝나거나 stronger planning decision이 필요해지면 Codex는 다음 ticket을 스스로 선택하지 않고 planning 흐름으로 되돌린다.

## Ticket 유형

Planning, review, execution boundary가 명확하도록 명시적인 ticket 유형을 사용한다.

- `Atomic ticket`: 기본 단위이며, 보통 하나의 PR에 대응한다.
- `Bounded polish batch`: 같은 screen/user flow/product boundary를 공유하고 같은 validation scope 아래에서 review할 수 있는 여러 관련 low/medium-risk 항목을 하나의 PR에 담는 유형이다.
- `Read-only review`: 같은 ticket 안에서 구현으로 확장해서는 안 되는 review-only 작업이다.
- `Planning-contract ticket`: scope/acceptance/validation을 확정하기 위한 planning-only 작업이며, 같은 ticket 안에서 구현으로 확장해서는 안 된다.

High-risk 작업은 보통 `Planning-contract ticket` 또는 `Read-only review`로 시작해야 한다. 승인된 ticket이 implementation scope와 Human Gate approval을 명시적으로 정의하지 않는 한 high-risk 작업을 곧바로 구현으로 전환하지 않는다.

## Codex 경계

Codex는 다음을 수행해야 한다.

- Ticket을 기준으로 작업하고 diff를 집중된 상태로 유지한다.
- 기존 MVP, security, validation guardrail을 보존한다.
- 구현이 해석에 의존할 때는 assumption을 명시한다.
- Code change에는 repo root에서 `./scripts/check.sh`를 실행한다.
- Ticket이 PR-native 실행으로 승인되면 branch 생성, commit, push, PR 생성을 수행한다.

### Codex Preflight

편집 전에 다음을 수행한다.

- repo/branch를 확인한다.
- `git status --short`를 실행한다.
- 관련 없는 dirty change가 있으면 중단한다.

Codex는 다음을 수행해서는 안 된다.

- Ticket 없이 인접한 product feature로 scope를 확장하지 않는다.
- Ticket이 명시적으로 요구하지 않는 한 scheduler, DB, provider fetch, schema, API, web behavior를 변경하지 않는다.
- 현재 docs가 그렇게 말하지 않는 한 local 또는 private runtime evidence를 live scheduler authority로 취급하지 않는다.
- 기본적으로 local checkpoint를 만들거나 private planning state를 정리·갱신하지 않는다.

## Review

`Fresh-context` review는 implementation conversation과 분리된 별도 read-only conversation에서 수행한다. Reviewer는 accepted contract, ticket, diff, tests, validation evidence를 검토하되 파일을 직접 수정하지 않고 다음을 보고한다.

- Blocking findings.
- Non-blocking findings.
- Missing required evidence.
- Remaining uncertainty.
- Final status.

수정이 필요하면 원래 implementation 흐름으로 되돌린다. Implementation agent가 수정했다는 사실만으로 review를 통과한 것으로 보지 않는다. 수정 뒤 Fresh-context reviewer가 blocking findings와 required evidence가 해결됐는지 다시 확인해야 한다.

Fresh-context review의 원본 ChatGPT conversation은 public independent review evidence로 사용하지 않는다. 대신 검토한 contract와 ticket, blocking findings, missing evidence, remaining uncertainty, final status를 포함한 짧은 review 결과를 human-authored GitHub PR comment 또는 GitHub review로 기록한다. Implementation agent 자신의 완료 보고, 자체 검토 또는 자체 수정 결과는 independent review evidence가 될 수 없다.

### Fresh-context trigger 후보

다음은 implementation 전에 Fresh-context review 여부를 판단하는 후보다.

- Canonical identity와 trusted mapping.
- Steam–Chzzk join, row grain, cardinality.
- `Combined` semantics.
- KPI, score, recommendation.
- Incomplete, unknown, `partial_success` 의미.
- DB schema, migration, deletion, backfill, reingest.
- Scheduler, retry, concurrency, recurring 또는 automatic write.
- Privacy와 public/private evidence boundary.

Trigger 후보는 자동 의무가 아니며 모든 PR에 Fresh-context review를 요구하지 않는다. 최종 `Review Level`은 ticket에서 implementation 전에 확정한다. Trigger 후보에 해당하지만 `Standard`를 선택하면 `Review Reason`에 기존 contract를 그대로 따르는 이유를 적는다.

### Independent Review Status

다음 네 값만 사용한다.

- `Not required`: `Review Level: Standard`이며 `Independent Review Evidence: N/A`를 사용한다.
- `Pending`: Fresh-context review가 필요하지만 아직 완료되지 않았다. `Independent Review Evidence`에는 아직 evidence가 없음을 표시한다.
- `Findings open`: Blocking finding 또는 required evidence 누락이 남아 있다. `Independent Review Evidence`는 finding이 기록된 human-authored GitHub PR comment 또는 GitHub review를 가리킨다.
- `Passed`: Fresh-context reviewer가 blocking findings와 required evidence가 해결됐음을 최종 재확인했다. `Independent Review Evidence`는 최종 재확인 결과가 기록된 human-authored GitHub PR comment 또는 GitHub review를 가리킨다.

Implementation agent가 수정한 사실만으로 `Passed`가 되지 않으며, Fresh-context reviewer의 재확인 없이 `Findings open`을 `Passed`로 바꾸지 않는다. Implementation agent 자신의 완료 보고나 자체 수정 결과, Fresh-context review의 원본 ChatGPT conversation은 independent review evidence가 아니다.

## Human Gate

다음을 포함해 위험하거나 운영상 의미 있는 결정에는 Human Gate가 필요하다.

- DB schema, migration, persistent data semantics.
- Scheduler mutation 또는 production-like recurring runtime 변경.
- Live fetch/write, backfill, reingest, bootstrap, DDL.
- Secrets, auth, deploy, read-only를 넘는 CI permission, release decision.
- Category-to-game trusted semantics, Combined semantics, broad tooling adoption.

`Human Gate Required: Yes`의 실제 approval evidence는 human-authored GitHub PR comment 또는 human-authored GitHub review로 제한한다. PR 본문에 기입된 상태값이나 implementation agent의 자기 보고만으로는 Human Gate approval을 증명할 수 없다. ChatGPT conversation, ChatGPT conversation을 가리키는 모호한 decision reference, implementation agent의 완료 보고도 approval evidence가 아니다.

Human-authored GitHub approval evidence가 없으면 Human Gate는 `Pending`이다. Pending 상태의 PR은 accepted 또는 merge-ready로 취급하지 않는다.

## Check 규칙

Code change에 대한 기본 repo-root local check는 다음과 같다.

```bash
./scripts/check.sh
```

이것이 full gate이며, focused Python check와 web check를 순서대로 실행한다. Codex는 ticket과 관련된 focused check를 먼저 실행할 수 있다.

```bash
./scripts/check-python.sh
./scripts/check-web.sh
```

`./scripts/check-web.sh`는 web ESLint lint를 실행한 뒤 TypeScript/Vite build를 실행한다.

Codex에서는 sandbox escalation/approval을 사용해 `./scripts/check.sh`를 실행한다. Restricted sandbox 실행은 과거 FastAPI/Starlette TestClient pytest case에서 멈춘 적이 있지만, 승인된 `./scripts/check.sh`와 GitHub Actions CI는 통과했다. 승인된 실행 또는 CI가 실패하면 실제 validation failure로 취급한다.

## Local Docs 및 Checkpoint

`docs/local/**`는 필요할 때 non-authoritative local/private scratch로 사용할 수 있으며 execution authorization source로 취급하지 않는다.

Local docs와 checkpoint는 기본 deliverable이 아니다. 큰 slice 완료, 위험한 operational evidence, 명시적인 사용자 요청이 있을 때만 만든다. Checkpoint index sync 또는 private planning-state hygiene을 기본 follow-up work로 제안하지 않는다.
