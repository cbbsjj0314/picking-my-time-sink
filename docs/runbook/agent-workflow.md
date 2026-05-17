# Agent Workflow Runbook

This repo uses a small PR-native workflow:

Spec -> Ticket -> Agent implementation -> PR -> CI -> Review -> Human Gate -> Release.

## Roles

- ChatGPT/planning sessions define product specs, split work into tickets, and clarify acceptance criteria.
- Codex implements one ticket at a time and prepares a small PR-ready diff.
- Humans approve risky scope, review PRs, decide merges, and control releases.

## Ticket Contents

A ticket should name the goal, scope, out of scope, requirements, acceptance criteria, required checks, manual QA, risk level, Human Gate requirement, suggested branch name, and suggested PR title.

One ticket normally maps to one PR. Split work before implementation when a ticket mixes unrelated runtime, schema, API, web, or operations changes.

## Codex Boundaries

Codex should:

- Work from the ticket and keep the diff focused.
- Preserve existing MVP, security, and validation guardrails.
- State assumptions when implementation depends on interpretation.
- Run `./scripts/check.sh` from the repo root for code changes.

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

This runs Ruff and Pytest only. Add heavier checks only when a ticket explicitly requires them.

## Local Docs And Checkpoints

Local docs and checkpoints are not default deliverables. Create them only for large slice completion, risky operational evidence, or explicit user request. Do not propose checkpoint index sync or NEXT hygiene as default follow-up work.
