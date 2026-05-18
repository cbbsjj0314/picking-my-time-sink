# Agent Workflow Runbook

This repo uses a small PR-native workflow:

Spec -> Ticket -> Agent implementation -> PR -> CI -> Review -> Human Gate -> Release.

## Roles

- ChatGPT/planning sessions define product specs, split work into tickets, and clarify acceptance criteria.
- Codex implements one ticket at a time, prepares a focused branch/commit, and opens a small PR when the ticket is approved for PR-native execution.
- Humans approve risky scope, review PRs, decide merges, and control releases.

## Ticket Contents

A ticket should name the goal, scope, out of scope, requirements, acceptance criteria, required checks, manual QA, risk level, Human Gate requirement, suggested branch name, and suggested PR title.

One ticket normally maps to one PR. Split work before implementation when a ticket mixes unrelated runtime, schema, API, web, or operations changes.

## Ticket Types

Use explicit ticket types so planning, review, and execution boundaries are clear:

- `Atomic ticket`: the default unit; normally maps to one PR.
- `Bounded polish batch`: multiple related low/medium-risk items in one PR when they share the same screen/user flow/product boundary and can be reviewed under the same validation scope.
- `Read-only review`: review-only work that must not be expanded into implementation in the same ticket.
- `Planning-contract ticket`: planning-only work to lock scope/acceptance/validation that must not be expanded into implementation in the same ticket.

High-risk work should usually start as a `Planning-contract ticket` or `Read-only review`. Do not convert high-risk work directly into implementation unless the approved ticket explicitly defines implementation scope and Human Gate approval.

## Codex Boundaries

Codex should:

- Work from the ticket and keep the diff focused.
- Preserve existing MVP, security, and validation guardrails.
- State assumptions when implementation depends on interpretation.
- Run `./scripts/check.sh` from the repo root for code changes.
- Create a branch, commit, push, and open a PR when the ticket is approved for PR-native execution.

### Codex Preflight

Before editing:

- Confirm repo/branch.
- Run `git status --short`.
- Stop if unrelated dirty changes are present.

Codex should not:

- Expand into adjacent product features without a ticket.
- Change scheduler, DB, provider fetches, schema, API, or web behavior unless the ticket explicitly asks for it.
- Treat local or private runtime evidence as live scheduler authority unless current docs say so.
- Create local checkpoints or cleanup `docs/local/NEXT.md` by default.

## Human Gate

Human Gate is required for risky or operationally meaningful decisions, including:

- DB schema, migration, or persistent data semantics.
- Scheduler mutation or production-like recurring runtime changes.
- Live fetch/write, backfill, reingest, bootstrap, or DDL.
- Secrets, auth, deploy, CI permissions beyond read-only, or release decisions.
- Category-to-game trusted semantics, Combined semantics, or broad tooling adoption.

## Checks

For code changes, the default repo-root local check is:

```bash
./scripts/check.sh
```

This is the full gate and runs the focused Python and web checks in order. Codex may run a ticket-relevant focused check first:

```bash
./scripts/check-python.sh
./scripts/check-web.sh
```

`./scripts/check-web.sh` runs web ESLint lint and then the TypeScript/Vite build.

In Codex, run `./scripts/check.sh` with sandbox escalation/approval. Restricted sandbox execution has previously stalled during FastAPI/Starlette TestClient pytest cases, while approved `./scripts/check.sh` and GitHub Actions CI passed. If the approved run or CI fails, treat it as a real validation failure.

## Local Docs And Checkpoints

Local docs and checkpoints are not default deliverables. Create them only for large slice completion, risky operational evidence, or explicit user request. Do not propose checkpoint index sync or NEXT hygiene as default follow-up work.
