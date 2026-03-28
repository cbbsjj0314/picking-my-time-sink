# AGENTS.md

## Working style
- Work in small, focused steps.
- Keep diffs small and easy to review.
- Preserve the existing project style whenever possible.
- Do not expand scope beyond the requested MVP path.

## Planning and reporting
- Before making changes, show a short plan.
- Use `docs/NEXT.local.md` as the current execution priority board when it applies.
- If a task changes current status or closes a Now/Next item, update `docs/NEXT.local.md` in the same slice.
- If a change alters schema, API, or data semantics, update the related durable doc and regression tests in the same slice.
- After making changes, summarize:
  - files changed
  - what was implemented
  - what was explicitly deferred
  - how to run and verify it

## Validation
- After code changes, run:
  - `poetry run ruff check .`
  - `poetry run pytest`
- Fix validation failures before finishing when they are caused by your changes.

## Project structure
- Follow the existing `src/` and `tests/` layout.
- Keep new files aligned with the current directory conventions.
- Prefer small, reusable modules over large files.

## Configuration and secrets
- Never hardcode secrets or environment-specific values.
- Use environment variables or configuration files.
- Keep local-only values out of version-controlled source files.

## Comments and documentation
- Use short English comments only when needed.
- Explain why, constraints, or caveats.
- Do not add comments that only restate obvious code.
- Use concise docstrings for entrypoints, public functions, and non-obvious behavior.

## Scope guardrails
- Implement the minimum successful path first.
- Avoid speculative abstractions unless they are required by the current task.
- Prefer repo-grounded facts and existing boundaries over early generalization.
- Separate implemented scope from explicitly deferred follow-ups.
- Do not pull in the “next natural slice” unless it is required for the current task.
- Do not introduce heavy new tooling unless explicitly requested.

## Git conventions
- Prefer one branch per Now item.
- Merge to `main` at natural completion points (task close or checkpoint).
- Use commit messages in this format:
  - `type(scope): summary`
- Suggested types:
  - `feat`
  - `fix`
  - `chore`
  - `docs`
  - `refactor`
  - `test`

## Current project focus
- This repository is currently in MVP mode.
- Prioritize the Steam-only vertical slice first.
- Treat the current Steam-only runtime baseline as the default boundary.
- Prefer follow-up slices on top of the current baseline, such as App Catalog, tracked_universe, and Price/Reviews wiring.
- For streaming expansion, start from provider-specific probe/ingest work instead of generalizing Steam service/API layers first.
- Prefer end-to-end progress over broad platform expansion.
- Do not implement real Chzzk integration unless explicitly requested.
