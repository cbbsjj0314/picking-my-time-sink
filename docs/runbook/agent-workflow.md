# Agent Workflow Runbook

## Default workflow

Ordinary bounded work는 Human의 구체적인 요청에서 시작한다. 작은 UI/docs/bugfix처럼 scope와 성공 기준이 명확하고 아래 escalation 원칙에 해당하지 않는 작업은 다음 흐름을 따른다.

```text
repo / clean-worktree preflight
→ short plan when useful
→ narrow implementation
→ relevant focused tests
→ ./scripts/check.sh when code changed
→ Draft PR / applicable CI
→ Human review / merge
```

Non-trivial change는 편집 전에 짧은 plan과 최소 observable success criteria를 제시한다. 현재 code, tests, durable docs를 확인하고 요청에 필요한 최소 boundary에서 구현한다. 관련 없는 refactor, cleanup 또는 다른 작업 선택으로 scope를 넓히지 않는다.

Ordinary work에는 canonical ticket, full handoff envelope, `Risk Level`, `Review Level`, `Human Gate Required`, Fresh-context review, AC → evidence mapping 또는 private planning-state update를 일괄 요구하지 않는다. `Default`는 별도로 입력하거나 등록할 mode/status field가 아니다. 기존 ticket과 historical record는 migration하거나 backfill하지 않는다.

Codex는 요청된 scope를 구현하고 검증한 뒤 집중된 branch/commit과 Draft PR을 준비한다. 별도의 local-only, read-only 또는 publication 제한이 있으면 그 제한을 따른다. Human은 위험한 scope를 승인하고, review와 최종 merge 및 release를 결정한다.

## Repository Identity Preflight

편집 전에 intended repository, 현재 branch/base/HEAD와 clean worktree를 확인한다.

```bash
git rev-parse --show-toplevel
git remote get-url origin
git branch --show-current
git rev-parse HEAD
git status --short
```

Repository-root와 remote의 host / owner / repository를 함께 확인한다. HTTPS / SSH 표기 차이는 같은 repository identity로 비교한다. Root basename이나 clean worktree만으로 repository 일치를 판단하지 않는다. Expected root 또는 revision이 주어지면 실제 값과 대조한다. `git status --short` output이 없어야 clean-worktree verification을 통과한다.

Intended repository가 불명확하거나 실제 identity가 불일치하거나 확인할 수 없거나 worktree가 clean하지 않으면 편집 전에 멈추고 상태를 보고한다. 다른 repository로 암묵적으로 이동하거나 수정하지 않는다. Human의 clarification 또는 corrected handoff를 받은 뒤 나머지 scope/authority 조건을 확인한다. Ordinary request에 별도 handoff form을 작성할 필요는 없다.

## Escalated / Gated workflow

Escalation은 작업 시작 시 한 번의 분류로 끝나지 않는다. 시작 전 또는 구현 도중 다음이 드러나면 default path를 중단한다.

- 결과나 허용 범위를 바꾸는 material ambiguity.
- 되돌릴 수 없거나 복구 비용이 큰 effect.
- Production 또는 external system에 대한 authority가 필요한 작업.
- Security/privacy boundary의 위험.
- Durable data 또는 trusted data semantics의 위험.

일반 원칙은 현재 요청과 evidence만으로 안전한 scope, 영향 또는 권한을 확정할 수 없으면 계속하지 않는 것이다. 위 원칙과 다음 예시는 exhaustive taxonomy가 아니다. 목록에 없다는 이유로 ordinary work로 간주하지 않는다.

Concrete examples에는 production/external mutation, destructive operation, DB schema/migration, backfill/reingest/live write, scheduler/recurring execution, auth/secrets/permissions, deploy/release, public/private evidence boundary, trusted mapping/`Combined`/KPI/recommendation semantics, 비용이 큰 cross-subsystem/architecture change가 포함된다. 요청된 통상적인 Git branch push와 Draft PR 생성은 아래 publication 경계 안에서 수행한다. 이것이 production/external mutation 권한을 주지는 않는다.

발견한 위험과 부족한 authority/evidence를 보고하고 planning으로 돌아간다. 필요한 최소 stronger execution contract를 Human과 확정한 뒤 그 범위에서만 재개한다. 위험을 발견한 작업을 계속하거나 자체 재분류하여 gate를 낮추지 않는다. 이미 정해진 ticket, Risk / Review / Human Gate와 operational contract는 계속 준수한다.

### Scoped authority and handoff

Escalated work는 위험과 evidence value에 비례하여 scope, out of scope, 성공 기준, validation, 허용된 phase와 차단된 action을 명확히 한다. Ticket, Risk / Review / Human Gate, Fresh-context review, private durable note는 필요한 경우에만 사용한다. 모든 escalated work에 동일한 form이나 review layer를 추가하지 않는다.

Stronger execution contract를 문서화할 때 기존 `docs/ticket-template.md`를 사용할 수 있다. Ordinary work의 mandatory entrypoint는 아니다. Ticket을 사용하는 작업은 Human이 선택·전달한 ticket에 한정한다. Board, queue, candidate list는 다른 ticket 선택이나 승격 권한을 주지 않는다.

Handoff는 해당 작업에 필요한 repository identity, accepted contract/reference, authorized phase, required review/gate와 실제 temporary constraint를 전달한다. Stable workflow와 전체 requirements를 복제하지 않는다. Canonical authority가 지정되었는데 접근 불가능하거나 material ambiguity가 있으면 재구성하지 않고 멈춘다. 이미 확정된 `Risk Level`, `Review Level`, `Human Gate Required`는 implementation agent가 낮추지 않는다.

Read-only review는 inspect/report만 수행하며 파일을 수정하지 않는다. Planning-contract는 scope/acceptance/validation을 확정하는 데 한정한다. 이러한 제한이 있는 session에서 implementation으로 암묵적으로 확장하지 않으며, 별도 explicit implementation handoff와 session으로 전환한다. Ordinary implementation에 이 Mode field를 의무화하지 않는다.

A8 같은 destructive recovery rotation/delete는 별도 Human selection과 explicit stronger authority가 필요하다. Default workflow, 이전 phase의 PASS 또는 PR merge는 그 권한을 만들지 않는다.

## Draft PR Invariant

Codex가 생성하는 모든 PR은 Draft로 연다. Human이 Ready for review 여부와 최종 merge 여부를 결정한다. Codex는 PR을 Ready로 전환하거나 merge하지 않는다. `main` 직접 push, force-push, release/tag 생성도 하지 않는다. 별도 task의 specific Human override는 명시적으로 승인한 범위에만 적용한다.

`Draft`는 required validation, CI, review 또는 Human Gate evidence를 생략한다는 뜻이 아니다. Draft PR 준비와 implementation evidence 작성은 acceptance 또는 merge-ready 판정과 다르다.

## Completion Contract

`.github/PULL_REQUEST_TEMPLATE.md`를 canonical completion interface로 사용한다. Ordinary PR은 Summary / Changes / Validation 중심으로 구현한 scope, 변경 이유, 수행한 checks의 exact results를 짧게 기록한다. 필요한 deferred scope, documentation impact와 concrete uncertainty도 기록한다. 실행하지 않은 checks를 통과한 것으로 표현하지 않는다.

Ticket / Spec reference, Risk / Review / Human Gate, independent review status/evidence, AC → evidence mapping은 해당 accepted contract가 요구할 때만 추가한다. Ticket 전체를 PR body에 복제하지 않는다. Required Fresh-context review가 미완료이면 `Pending`이며 implementation agent의 자체 검증은 independent review가 아니다.

Schema / API / data semantics / operational contract가 바뀌면 관련 durable docs와 regression evidence를 같은 slice에 포함한다. Documentation impact는 갱신한 문서를 적거나 기존 문서가 여전히 정확한 이유를 짧게 설명한다. Trivial change마다 새 문서를 만들 필요는 없다.

## Exploration and Verification Sufficiency

요청과 accepted contract를 이해하는 데 필요한 최소 repository surface부터 확인한다. 탐색 확대는 material ambiguity, discovered dependency, failing validation, new concrete risk 또는 missing required evidence가 있을 때만 한다.

Relevant focused regression checks를 수행하고, code change는 final code state에서 repo-root `./scripts/check.sh`로 full validation을 마친다. 실행 및 failure 처리는 아래 Check 규칙을 따른다. Docs-only change는 runtime/code path가 바뀌지 않으면 runtime validation을 생략할 수 있지만 required static checks와 applicable contract evidence는 충족해야 한다.

Required task checks와 applicable canonical validation을 충족하고, 요구된 acceptance evidence와 documentation impact가 확인되며 concrete unresolved concern이 없으면 검증을 멈춘다. 모든 ordinary PR에 AC mapping을 만들라는 뜻은 아니다.

추가 또는 반복 validation은 check failure, 성공 뒤 relevant change, new concrete inconsistency/risk, missing required evidence 또는 reviewer 요청이 있을 때 수행한다. 이 stopping rule은 required CI, Fresh-context review나 Human Gate를 면제하지 않는다.

## Codex boundaries

`AGENTS.md`의 security/privacy/data boundaries와 `docs/data-governance.md`를 유지한다. Secrets, credential, raw/private runtime evidence를 public diff나 PR body에 넣지 않는다. Local/private evidence를 current durable docs의 binding 없이 live scheduler authority로 취급하지 않는다. Scope 밖의 scheduler, DB, provider fetch, schema, API 또는 web behavior를 변경하지 않는다.

## Review

Ordinary work는 Human PR review를 따른다. Fresh-context review는 concrete risk와 필요한 independent evidence에 따라 accepted contract에서 요구할 때 수행한다. 기존 required review를 자체 판단으로 생략하지 않는다.

`Fresh-context` review는 implementation conversation과 분리된 별도 read-only conversation에서 수행한다. Reviewer는 accepted contract, 해당 ticket, diff, tests, validation evidence를 검토하되 파일을 직접 수정하지 않고 다음을 보고한다.

- Blocking findings.
- Non-blocking findings.
- Missing required evidence.
- Remaining uncertainty.
- Final status.

수정이 필요하면 원래 implementation 흐름으로 되돌린다. Implementation agent가 수정했다는 사실만으로 review를 통과한 것으로 보지 않는다. 수정 뒤 Fresh-context reviewer가 blocking findings와 required evidence가 해결됐는지 다시 확인해야 한다.

Fresh-context review의 원본 ChatGPT conversation은 public independent review evidence로 사용하지 않는다. 대신 검토한 contract와 해당 ticket, blocking findings, missing evidence, remaining uncertainty, final status를 포함한 짧은 review 결과를 human-authored GitHub PR comment 또는 GitHub review로 기록한다. Implementation agent 자신의 완료 보고, 자체 검토 또는 자체 수정 결과는 independent review evidence가 될 수 없다.

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

Trigger 후보는 자동 의무가 아니며 모든 PR에 Fresh-context review를 요구하지 않는다. Review가 필요한 작업은 gated execution 전에 accepted contract에서 review 범위와 이유를 확정한다. 구현 중 새 위험이 발견되면 default path를 멈추고 review 필요성도 다시 확정한다. Ordinary PR에 `Review Level`이나 `Review Reason` 입력을 요구하지 않는다.

### Independent Review Status

Independent review evidence가 요구될 때 다음 네 값을 사용한다. Ordinary PR은 이 field를 생략한다.

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

Human Gate가 implementation merge 뒤의 mutation 또는 execution boundary에 적용되면 해당 implementation PR의 post-merge human-authored GitHub comment 또는 review를 approval evidence로 사용할 수 있다. 이 evidence는 승인하는 exact gated scope를 명시해야 한다. Implementation PR merge 자체는 Human Gate approval evidence가 아니다.

Human-authored GitHub approval evidence가 없으면 Human Gate는 `Pending`이다. 기본적으로 Pending 상태의 PR은 accepted 또는 merge-ready로 취급하지 않는다.

Phase-scoped pre-gate merge는 canonical ticket이 implementation 전에 다음을 모두 명시한 경우에만 사용할 수 있다.

```text
Human Gate Scope:
<Human approval이 차단하는 exact later mutation/execution boundary>

Pre-Gate Allowed Work:
<Human Gate가 Pending인 동안 허용되는 exact work>

Pre-Gate Merge Allowed:
Yes
```

`Pre-Gate Allowed Work`에는 implementation PR merge가 명시되어야 한다. 또한 merged implementation 자체가 gated live mutation 또는 authority를 실행하거나 자동 활성화하지 않아야 하고, ticket과 repo가 요구하는 validation 및 CI와 required review gate가 충족되어야 하며, blocking finding 또는 required evidence gap이 남아 있지 않아야 한다. `Review Level: Fresh-context`이면 `Independent Review Status: Passed`여야 한다. 이 조건을 모두 충족해도 human이 별도의 PR merge decision을 내려야만 implementation PR을 merge할 수 있다.

`Pre-Gate Merge Allowed: Yes`는 automatic merge, Codex 또는 implementation agent의 merge authority, required validation·CI·review 생략, human merge decision 생략, Human Gate approval, whole-ticket acceptance, ticket closure, release approval 또는 live mutation/execution authorization을 의미하지 않는다.

Gate scope 또는 pre-gate allowed work가 모호하거나, pre-gate merge permission이 없거나, 위 조건 중 하나라도 충족되지 않으면 phase-scoped pre-gate merge를 적용하지 않는다. Explicit declaration이 없는 legacy ticket에도 자동 소급하지 않으며 기존 fail-closed default를 유지한다.

Phase-scoped Human Gate에서 implementation PR merge는 implementation prerequisite를 사용할 수 있게 할 뿐이다. `implementation PR merged`는 `Human Gate approved`, whole-ticket acceptance 또는 ticket closure와 같지 않다. Human Gate가 `Pending`인 동안 gated live mutation/execution은 계속 금지되며, `Human Gate Required: Yes`인 ticket은 gated acceptance criteria를 포함한 모든 acceptance criteria가 충족될 때까지 `PASS / CLOSED`로 취급하지 않는다.

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
