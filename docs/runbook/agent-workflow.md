# Agent Workflow Runbook

이 repo는 작은 PR-native workflow를 사용한다.

Spec -> Ticket -> Agent implementation -> PR -> CI -> Review -> Human Gate -> Release.

## 역할

- ChatGPT/planning session은 product spec을 정의하고, 작업을 ticket으로 나누며, acceptance criteria를 명확히 한다.
- Codex는 한 번에 하나의 ticket을 구현하고, 집중된 branch/commit을 준비하며, ticket이 PR-native 실행으로 승인되면 작은 PR을 연다.
- 사람은 위험한 scope를 승인하고, PR을 review하며, merge를 결정하고, release를 제어한다.

## Ticket 내용

Ticket은 goal, scope, out of scope, requirements, acceptance criteria, required checks, manual QA, risk level, Human Gate requirement, suggested branch name, suggested PR title을 명시해야 한다.

하나의 ticket은 보통 하나의 PR에 대응한다. Ticket이 서로 관련 없는 runtime, schema, API, web, operations 변경을 섞고 있다면 구현 전에 작업을 나눈다.

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
- 기본적으로 local checkpoint를 만들거나 `docs/local/NEXT.md`를 cleanup하지 않는다.

## Human Gate

다음을 포함해 위험하거나 운영상 의미 있는 결정에는 Human Gate가 필요하다.

- DB schema, migration, persistent data semantics.
- Scheduler mutation 또는 production-like recurring runtime 변경.
- Live fetch/write, backfill, reingest, bootstrap, DDL.
- Secrets, auth, deploy, read-only를 넘는 CI permission, release decision.
- Category-to-game trusted semantics, Combined semantics, broad tooling adoption.

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

Local docs와 checkpoint는 기본 deliverable이 아니다. 큰 slice 완료, 위험한 operational evidence, 명시적인 사용자 요청이 있을 때만 만든다. Checkpoint index sync 또는 NEXT hygiene을 기본 follow-up work로 제안하지 않는다.
