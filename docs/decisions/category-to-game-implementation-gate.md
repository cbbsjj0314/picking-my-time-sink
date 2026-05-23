# Category-To-Game Implementation Gate

Status: docs-only decision checkpoint  
Ticket: CATEGORY-MAPPING-IMPLEMENTATION-GATE-001  
Date: 2026-05-23 (KST)

이 문서는 category-to-game mapping 구현을 시작하기 전에 필요한 decision gate를 고정한다.
이 결정은 schema, API, runtime, DB, web, storage, serving, trusted mapping, automatic matching, 또는 `Combined` semantics 구현 승인이 아니다.

## Current Boundary Summary

- 현재 구현 baseline은 Steam 중심이며, Chzzk는 category-level observed evidence와 read-only `/chzzk/categories/overview` boundary로 제한된다.
- `/chzzk/categories/overview` 는 category-only observed evidence surface다. Steam mapping, canonical game identity, trusted mapping state, 또는 `Combined` field를 노출하지 않는다.
- `categoryType=GAME` 은 Chzzk provider category type evidence일 뿐이며 canonical game identity나 Steam-Chzzk mapping 근거가 아니다.
- `candidate`, `unresolved`, `rejected` 는 decision-level review evidence 상태다. 이 상태만으로 trusted mapping, canonical game semantics, serving semantics, ranking/sorting/KPI, 또는 `Combined` 를 만들 수 없다.
- `trusted` / `approved` 는 future Human Gate / promotion gate 용어로만 둔다. 이 문서는 이를 persisted state, schema value, API field, UI field, runtime behavior로 정의하지 않는다.
- `Combined` 는 trusted mapping, serving semantics, API response shape, regression expectations, Human Gate가 별도 승인될 때까지 blocked/pending 상태로 남는다.

## Existing Docs Reviewed

- `README.md`
- `docs/source-inventory.md`
- `docs/data-model-spec.md`
- `docs/data-governance.md`
- `docs/metrics-definitions.md`
- `docs/decisions/category-to-game-mapping-contract.md`
- `docs/decisions/category-to-game-storage-contract-planning.md`
- `docs/decisions/category-to-game-serving-contract-planning.md`
- `docs/decisions/category-to-game-implementation-surface-review.md`
- `docs/decisions/combined-source-view-readiness-contract.md`
- `docs/runbook/agent-workflow.md`
- `docs/ticket-template.md`

## Decision

- Implementation readiness: `conditional`
- Reason:
  - Existing docs already define the candidate-only, trusted mapping, serving, and `Combined` boundaries.
  - Real observed-data candidate work still depends on current Chzzk category coverage/freshness confidence.
  - Therefore the first implementation that uses real observed Chzzk category data to seed, store, prioritize, or review category-to-game candidates is not ready until the proposed future audit below answers its required questions.
- Required prior action:
  - `CHZZK-COVERAGE-FRESHNESS-AUDIT-001` is required before implementation that uses real observed Chzzk category data to seed, store, prioritize, or review category-to-game candidates.
  - `CHZZK-COVERAGE-FRESHNESS-AUDIT-001` is not required for docs-only planning, synthetic/public-safe test guardrails, or non-runtime review notes that do not use real observed category data.
  - No tracked repo doc or ticket with `CHZZK-COVERAGE-FRESHNESS-AUDIT-001` was found during this checkpoint, so this document treats it as a proposed future prerequisite audit, not an existing approved ticket.
- Next approved direction:
  - Open the proposed audit before any implementation that uses real observed Chzzk category data to seed, store, prioritize, or review category-to-game candidates.
  - Candidate-only storage/review direction may be planned at decision-boundary level, but final storage selection and implementation remain behind future Human Gate.

## Storage / Review Workflow Gate

Future implementation that uses real observed Chzzk category data to seed, store, prioritize, or review category-to-game candidates may only start from a candidate-only review boundary after the scoped audit and Human Gate conditions are satisfied.

- Candidate-only boundary:
  - Candidate evidence may support review discussion only.
  - Candidate evidence must not be treated as a trusted relation, hidden join, canonical identity, or source of serving truth.
- No trusted mapping usage:
  - `candidate`, `unresolved`, and `rejected` evidence cannot power trusted mapping or canonical game semantics.
  - `trusted` / `approved` promotion remains future Human Gate terminology only.
- No automatic matching:
  - `categoryType=GAME`, name similarity, normalized hints, or category evidence must not auto-promote a mapping.
  - Ambiguous alias, renamed category, regional title, franchise collision, and same-name collision must remain review questions rather than guessed mappings.
- No serving semantics:
  - Candidate evidence must not change `/chzzk/categories/overview`, current source views, API response meaning, UI presentation, ranking/sorting/KPI, or other serving behavior.
- No `Combined` semantics:
  - Candidate evidence must not create or enrich `Combined` rows, KPI, ranking, sorting, game identity, or relationship semantics.

## Status Lifecycle Boundary

These terms are decision-level semantics only. They are not concrete persisted values, API fields, UI fields, or operational workflow.

- `candidate`: review 가능한 mapping 가능성이다. Trusted mapping, canonical game semantics, serving semantics, ranking/sorting/KPI, 또는 `Combined` 에 사용할 수 없다.
- `unresolved`: 판단에 필요한 ambiguity가 남아 있다. Guessed mapping, automatic matching, auto-promotion을 허용하지 않는다.
- `rejected`: 검토 결과 수용하지 않은 후보다. Rejected evidence도 trusted mapping으로 되살리지 않는다.
- `trusted` / `approved`: future Human Gate / promotion gate 용어로만 둔다. 이 checkpoint는 trusted state 구현을 승인하지 않는다.

## Evidence Boundary

Public docs and PR text may describe sanitized evidence categories only.

Allowed public categories:

- provider category identity category
- candidate canonical game reference category
- normalized comparison hint category
- ambiguity reason category
- reviewer/operator note category
- timestamp category

Excluded from public docs and PR text:

- real category/channel/display values
- live titles
- thumbnails
- raw provider payloads
- raw API responses
- screenshots
- credentials
- `.env` values
- private paths
- scheduler XML/stdout
- local runtime logs
- raw Grafana/Prometheus responses
- row-level UGC

## Proposed Audit Questions

`CHZZK-COVERAGE-FRESHNESS-AUDIT-001` should answer these questions before implementation that uses real observed Chzzk category data to seed, store, prioritize, or review category-to-game candidates.

- Coverage/freshness:
  - Is there enough tracked, public-safe evidence to judge current Chzzk category coverage and freshness for candidate review?
  - Are coverage gaps, stale windows, missing category evidence, skipped evidence, and bounded pagination caveats visible enough that candidate review will not imply stronger data completeness than exists?
- Category stability:
  - Are observed category identity/type/name signals stable enough for candidate-only review without implying canonical game identity?
  - Does `categoryType=GAME` remain provider category evidence only in all proposed candidate-review uses?
- Caveat preservation:
  - Are bounded sample, bucket coverage, missing evidence, and failure/skip caveats preserved through any proposed candidate-review input?
  - Is there any risk that candidate review would claim full live-list completeness, pagination exhaustion, or uncaveated 1d/7d semantics?
- Public/private safety:
  - Can the candidate review evidence be represented using sanitized evidence categories only?
  - Are raw/private materials kept out of public docs, PR text, fixtures, API/UI semantics, and durable decision records?
- Serving separation:
  - Does `/chzzk/categories/overview` remain category-only observed evidence?
  - Is there any proposed path that would accidentally use candidate evidence for trusted mapping, canonical game semantics, ranking/sorting/KPI, serving semantics, or `Combined`?

This checkpoint does not run the audit and does not claim answers to these questions.

## Later Implementation Ticket Boundary

A later implementation ticket may:

- add candidate-only review/storage behavior only after the scoped audit and Human Gate approval if it uses real observed Chzzk category data to seed, store, prioritize, or review category-to-game candidates
- keep candidate evidence untrusted and separated from current serving and `Combined` surfaces
- add regression tests that prove untrusted category evidence cannot become canonical game identity or trusted mapping
- update durable docs in the same slice if the implementation changes schema/API/data semantics

A later implementation ticket may not implement without separate Human Gate:

- trusted mapping usage
- automatic matching
- promotion/demotion implementation
- serving semantics
- API endpoint or response shape changes
- web UI behavior, route, copy, table, sort/filter/search, or presentation changes
- ranking/sorting/KPI semantics from candidate evidence
- `Combined` semantics, API, UI, KPI, ranking, sorting, or relationship interpretation
- live fetch, scheduler mutation, runtime DB write, backfill, reingest, or bootstrap
- generalized provider abstraction

## Regression / Test Expectations For Later Slices

Any later implementation slice must include focused regression coverage proving:

- `categoryType=GAME` does not become canonical game identity.
- `candidate`, `unresolved`, and `rejected` do not power trusted mapping, canonical game semantics, ranking/sorting/KPI, serving semantics, or `Combined`.
- Trusted mapping usage requires a separate Human Gate and cannot be inferred from candidate evidence.
- Current `/chzzk/categories/overview` remains category-only unless a separate serving contract is approved.
- Public/private evidence boundaries remain enforced.

## Explicit Deferred Human Gate Items

The following remain future Human Gate items and are not approved by this checkpoint:

- final storage selection
- final schema/API/data semantics
- candidate storage/review implementation that uses real observed Chzzk category data
- promotion/demotion rules
- trusted mapping usage
- automatic matching
- serving semantics
- API/web behavior changes
- `Combined` semantics
- runtime, scheduler, DB, backfill, reingest, or live fetch behavior

## Next-Step Recommendation

Recommended next action: open proposed `CHZZK-COVERAGE-FRESHNESS-AUDIT-001` before any implementation that uses real observed Chzzk category data to seed, store, prioritize, or review category-to-game candidates.

Stop condition: do not start mapping storage, trusted mapping, serving, API/web, or `Combined` implementation from this checkpoint alone.
