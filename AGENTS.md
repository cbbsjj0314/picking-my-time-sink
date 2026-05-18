# AGENTS.md

## Working style
- Work in small, focused steps.
- Keep diffs small and easy to review.
- Preserve the existing project style whenever possible.
- Do not expand scope beyond the requested MVP path.

## Planning and reporting
- Before making changes, show a short plan.
- Use `docs/local/NEXT.md` as the current execution priority board when it is present locally and applies.
- If a task changes current status or closes a Now/Next item, update `docs/local/NEXT.md` in the same slice when that local board is present.
- If a change alters schema, API, or data semantics, update the related durable doc and regression tests in the same slice.
- Follow the default delivery flow: Spec -> Ticket -> Agent implementation -> PR -> CI -> Review -> Human Gate -> Release.
- Treat ChatGPT/planning sessions as the place to define product specs and tickets.
- Treat Codex implementation sessions as one-ticket-at-a-time execution toward a focused branch/commit and PR when the ticket is approved for PR-native execution.
- Codex must not merge PRs, create releases/tags, force-push, or push directly to `main`; humans own those decisions unless the user explicitly overrides this for a specific task.
- Leave risky scope approval, merge decisions, and release decisions to humans.
- Local docs, checkpoints, and `docs/local/NEXT.md` cleanup are not default deliverables.
- Create local checkpoints only for large slice completion, risky operational evidence, or explicit user request.
- Do not propose checkpoint index sync or NEXT hygiene as default follow-up work.
- After making changes, summarize:
  - files changed
  - what was implemented
  - what was explicitly deferred
  - how to run and verify it

## Ambiguity and assumptions
- Do not silently choose an interpretation when the request, data contract, runtime boundary, or ownership boundary is ambiguous.
- State the ambiguity and ask for clarification before implementation unless the task is small and the safest repo-grounded interpretation is obvious.
- When proceeding with an assumption, make the assumption explicit in the plan and final summary.
- Prefer repo-grounded evidence from existing code, tests, docs, and local boards over memory or generic best practice.
- Do not treat local/private runtime evidence from another host as live scheduler health unless the current docs explicitly connect that evidence to the authority runtime.

## Success criteria
- For non-trivial changes, define the smallest observable success criteria before editing.
- Prefer tests or read-only smoke checks that prove the requested behavior, not broad validation for unrelated areas.
- If the requested behavior cannot be fully verified in the current environment, state what was verified, what was not verified, and why.
- Do not claim a slice is complete just because code changed; completion requires the relevant docs, tests, or smoke evidence expected by the slice.

## Validation
- After code changes, run the default full local check from the repo root:
  - `./scripts/check.sh`
- `./scripts/check.sh` runs the focused checks in order:
  - `./scripts/check-python.sh`
  - `./scripts/check-web.sh` (web lint + TypeScript/Vite build)
- Codex may run a ticket-relevant focused check first, but must run `./scripts/check.sh` before finishing code changes.
- In Codex, run the exact repo-root command `./scripts/check.sh` with sandbox escalation/approval.
- Restricted sandbox execution has previously stalled during FastAPI/Starlette TestClient pytest cases, while approved `./scripts/check.sh` and GitHub Actions CI passed.
- Use escalation/approval only for this validation command, not for unrelated commands.
- If approved `./scripts/check.sh` or GitHub Actions CI fails, treat it as a real validation failure and investigate.
- If the current Codex exec environment cannot run validation because of PATH, Poetry, or sandbox issues, use the closest equivalent Ruff/Pytest command and report the exact command used.
- For docs-only changes, validation may be skipped if no runtime/code path changed.
- Fix validation failures before finishing when they are caused by your changes.
- Report the exact command, whether escalation/approval was used, and the exact result.

## Project structure
- Follow the existing `src/` and `tests/` layout.
- Keep new files aligned with the current directory conventions.
- Prefer small, reusable modules over large files.

## Configuration and secrets
- Never hardcode secrets or environment-specific values.
- Use environment variables or configuration files.
- Keep local-only values out of version-controlled source files.
- Prefer sanitized representative fixtures in tracked public paths; keep fuller raw third-party or UGC-heavy captures local/private when possible.

## Security and dependency hygiene
- Treat internet-connected services, CI jobs, and automation entrypoints as production attack surface, even in MVP stage.
- Keep runtime and developer dependencies anchored by committed lockfiles or explicit pins. Do not make incidental or floating upgrades on security-sensitive paths.
- Keep secrets out of source code, prompts, logs, screenshots, and issue/PR text. Prefer environment-injected credentials or secret managers over checked-in files.
- Prefer least privilege and credential isolation by default. Use separate credentials per service/environment when possible, and avoid broad shared keys.
- Treat external text consumed by automation or LLM-assisted workflows as untrusted input. Do not let issues, PR text, docs, or user content directly trigger privileged behavior without validation.
- If a compromised package, action, image, or tool may have run in this repo or CI, assume exposure assessment and secret rotation are required until proven otherwise. Identify affected paths and document concrete remediation.
- For security-related changes, summarize separately:
  - what was exposed or potentially exposed
  - what was rotated, revoked, or escalated
  - what was patched, pinned, or isolated
  - what remains explicitly deferred

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

## Surgical edits
- Every material change should trace directly to the current request or the validation needed for it.
- Do not refactor, reformat, rename, or clean up adjacent code unless it is required by the current slice.
- If unrelated dead code, naming drift, formatting drift, or cleanup is noticed, mention it as deferred instead of changing it.
- Keep mechanical formatting changes separate from behavior changes when they are unavoidable.
- Prefer modifying the narrowest existing module, function, or API boundary over introducing a new abstraction.

## Git conventions
- Prefer one branch per Now item.
- Merge to `main` at natural completion points (task close or checkpoint).
- Use commit messages in this format:
  - `type(scope): summary`
- Write commit subjects that are specific and clear.
- Keep commit subjects concise without dropping essential context.
- Avoid vague summaries such as `fix bug`, `update code`, or `misc cleanup`.
- Prefer subjects that make the changed behavior, target area, or reason clear.
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
- Do not expand Chzzk beyond approved observed source-view / guarded-write / observability boundaries unless explicitly requested.
