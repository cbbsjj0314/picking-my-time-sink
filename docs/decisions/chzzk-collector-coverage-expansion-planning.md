# Chzzk Collector Coverage Expansion Planning Contract

Status: Proposed canonical planning-contract — Human-selected direction; not implementation or live-activation authority until this document is merged through the repository workflow.

Ticket: `CHZZK-COLLECTOR-COVERAGE-EXPANSION-001`

Date: 2026-10-05 (KST)

## Type

Planning-contract ticket

## User Decision

- Problem: current Chzzk `/open/v1/lives` collection follows provider cursor pagination but normally stops at a fixed page bound, so a successful run can end while another cursor remains.
- Why now: Human selected Chzzk collector coverage expansion as the next PMTS planning work after `Useful Combined v1` live application. The next implementation needs a durable contract before changing collector breadth or authority runtime behavior.
- Observable success: a later repository implementation can distinguish provider pagination exhaustion from safety/failure termination, preserve one deterministic collection bucket, and remain inert until a separately gated live activation.
- Must not change: current `bounded_sample` product/API semantics, category observed-evidence boundary, trusted mapping authority, `Combined` semantics, scheduler/runtime authority, DB contents, or current live collector breadth during this planning task.

## Current Repository Evidence

At `main @ 8827014e4efd8e8c64fd7c443c1001405408ad26`:

- `src/chzzk/ingest/run_chzzk_fetch_load_manual_orchestration.py` uses `DEFAULT_FETCH_SIZE = 20` and `DEFAULT_FETCH_PAGES = 3`.
- `src/chzzk/probe/live_list_temporal_probe.py::fetch_pages(...)` follows the provider `next` cursor, stops early when no usable next cursor remains, and otherwise stops at the configured page bound.
- Existing fetch failures distinguish `quota_http_error` for HTTP `429`, other `http_error`, `request_error`, `invalid_json`, and `malformed_page`.
- Sanitized pagination evidence includes `pages_fetched`, `pages_requested`, `last_page_next_present`, and `bounded_page_cutoff`. `bounded_page_cutoff` is true when the configured page bound is reached successfully while another cursor remains.
- Multi-page payloads are concatenated by `merge_pages(...)` before category/channel aggregation. Current code does not perform cross-page live-item dedupe.
- The manual orchestration takes its `NoOverlapLock` before the fetch/load path and releases it after the bounded run completes.
- Current probe output chooses one `collected_at` after the page traversal and uses that same timestamp to derive all category/channel rows and the KST half-hour `bucket_time`.
- Current durable semantics keep `bounded_sample_caveat="bounded_sample"` separate from per-category bucket `coverage_status`; a bounded cutoff or remaining next cursor cannot be described as pagination exhaustion or a complete provider population.
- `categoryType=GAME` remains provider category-type evidence only. Candidate/unresolved/rejected evidence and inferred/fuzzy/guessed mappings are not trusted mapping authority.

These facts authorize planning only. They do not prove provider quota, full-population completeness, stable cross-page live-item identity, or safe unbounded traversal.

## Human-Provided Diagnostic Evidence

The following one-off evidence may be retained only as sanitized point-in-time aggregate context:

- one run traversed 30 pages / 600 live items; every request returned HTTP `200`; a next cursor still remained after page 30;
- a separate run traversed 60 pages / 1,200 live items; every request returned HTTP `200`; a next cursor still remained after page 60;
- normal HTTP `200` response headers did not establish a numeric rate-limit/quota value.

Numeric `/open/v1/lives` quota is therefore **unknown**. This evidence does not prove production-wide or peak-time behavior, full-population completeness, a transactionally frozen snapshot, or safety of truly unbounded traversal. No additional live Chzzk diagnostic is authorized by this contract-writing task.

## Scope

This contract authorizes a later Phase 1 repository implementation to add only the capability required for exhaustion-oriented Chzzk live-list traversal with finite repository-controlled safety budgets and deterministic evidence.

The planned normal success target is:

```text
provider pagination exhaustion
```

A fixed ordinary sample such as 3, 6, or 10 pages is not the target success rule for the new capability. Exhaustion-oriented traversal must still be bounded by explicit circuit breakers and must never become a truly unbounded loop.

## Out of Scope

This planning contract does not authorize:

- an additional Chzzk live API diagnostic;
- changing the current active fetch page default or authority recurring breadth;
- scheduler/runtime mutation or live recurring activation;
- DB schema/DDL changes, DB writes, backfill, reingest, or bootstrap;
- trusted mapping insert/update, automatic/fuzzy/inferred mapping, candidate promotion, or mapping scheduler work;
- `Combined` SQL/API/Web semantic changes, score, ranking, recommendation, or removal/reinterpretation of `bounded_sample`;
- UI work;
- Airflow, Dagster, dbt, or orchestration architecture redesign;
- unrelated retention/recovery work;
- `dev-notes` or private planning-state/checkpoint changes.

Discovering adjacent work does not authorize it.

## Requirements

### 1. Normal termination and finite safety budgets

The exhaustion-oriented capability must terminate successfully only when a valid provider page has no usable next cursor.

It must also require both of these finite repository-controlled guards:

- a hard page/request ceiling;
- an overall execution deadline/time budget.

The page/request ceiling is a runaway-protection circuit breaker, not the ordinary collection rule and not a provider quota claim. The deadline bounds provider interaction and lock occupancy if traversal becomes slow.

This contract deliberately does not invent numeric production values for either guard because provider quota/headroom is not established. Phase 1 must make the guards explicit and fail-closed for the new capability without changing the current authority runtime breadth. Before Phase 2 activation, the Human Gate approval must identify the exact authority-runtime page/request ceiling and deadline to be used.

### 2. Pagination-loop protection

The new traversal must detect a repeated cursor or equivalent deterministic pagination loop condition. A detected loop is a non-success termination and must stop issuing provider requests.

Loop protection is independent of the hard page/request ceiling; the ceiling remains the final runaway guard even if a novel provider behavior is not recognized as a cursor loop.

### 3. Failure and termination semantics

The following termination classes must remain distinguishable in sanitized evidence:

- `pagination_exhausted`;
- `safety_cutoff`;
- `deadline_exceeded`;
- `pagination_loop_detected`;
- `quota_http_error`;
- `http_error`;
- `request_error`;
- `invalid_json`;
- `malformed_page`.

Only `pagination_exhausted` is a successful pagination-completeness termination for the new capability. Safety cutoff, deadline expiry, loop detection, and provider/request/response failures are incomplete collection attempts.

This contract does not authorize a new retry/backoff loop. Existing fail-fast provider/request/response behavior remains the safe default; adding automatic retry behavior requires separate authority if later desired.

An incomplete collection attempt must not become DB-load-eligible category/channel evidence merely because one or more earlier pages were fetched successfully. Local/private raw pages may be retained under existing governance, but derived category/channel result artifacts used by the write path must remain fail-closed for incomplete traversal.

### 4. Sanitized pagination evidence and compatibility

Phase 1 must add deterministic sanitized termination evidence without deleting or silently redefining the existing pagination fields.

The implementation may choose exact field names, but the emitted evidence must let a reviewer determine at minimum:

- whether pagination exhausted normally;
- whether a hard safety cutoff occurred;
- whether the deadline expired;
- whether a pagination loop was detected;
- whether a provider/request/response failure occurred;
- how many pages/requests completed before termination;
- whether the last accepted page still advertised a usable next cursor.

Compatibility expectations:

- `pages_fetched` remains the number of accepted pages fetched for the attempt.
- `pages_requested` remains supported. In the new exhaustion-oriented mode it must not be presented as an expectation that every configured page should normally be fetched; if reused, its meaning must be documented as the finite configured request/page ceiling for that invocation.
- `last_page_next_present` retains its current evidence role.
- `bounded_page_cutoff` remains true when the hard page ceiling stops traversal while a usable next cursor remains. It must not become true for deadline, loop, or provider/request/response failure termination.
- `coverage.status` remains temporal bucket coverage evidence and must not be overloaded with pagination-completeness meaning.

### 5. Collection timestamp and 30-minute bucket semantics

The current manual fetch path chooses `collected_at` after traversal. That is acceptable for short bounded fetches but can move a longer logical collection into a later 30-minute bucket solely because traversal took longer.

Phase 1 is authorized to change the new exhaustion-oriented capability so that it captures one logical collection anchor immediately before the first provider request. That anchor must be propagated unchanged to every derived category/channel row for the traversal, and `bucket_time` must remain the KST half-hour floor of that single anchor.

A single logical traversal must never split its rows across different 30-minute buckets. Completion time and duration may be recorded separately in sanitized run evidence and must not silently replace the logical collection anchor.

The existing active path must remain unchanged until Phase 2 activation explicitly switches authority runtime behavior to the reviewed capability.

### 6. Coordination and no-overlap behavior

Phase 1 must preserve the current no-overlap boundary. The lock protecting fetch/load orchestration must continue to cover the full logical attempt; a longer traversal must not create concurrent provider fetches or weaken `lock_busy` behavior.

The deadline is part of this safety model because it bounds how long one traversal can occupy the coordination boundary.

### 7. Provider-list mutation during traversal

`pagination_exhausted` means the cursor chain presented during that traversal ended. It does **not** mean the provider supplied a transactionally frozen point-in-time universe.

Live rows can appear, disappear, reorder, or move while pages are traversed. Therefore pagination exhaustion can be stronger evidence than a known fixed cutoff while still being weaker than full snapshot completeness.

No product/API wording may convert exhaustion evidence into a claim that every live item that existed at one instant was observed exactly once.

### 8. Duplicate handling

Current `merge_pages(...)` concatenates parser-eligible live items across pages before aggregation. Repository/provider evidence does not establish a safe stable cross-page live-session identity for dedupe. In particular, the presence of `channelId` does not by itself authorize treating it as that identity.

The smallest safe Phase 1 contract is therefore:

- do not invent or apply a new cross-page dedupe key;
- preserve current row multiplicity when merging accepted pages;
- make the absence of a proven dedupe identity an explicit implementation/review caveat;
- do not claim exact de-duplicated population totals from pagination exhaustion.

Any future change that deduplicates live items, chooses a stable identity, or changes aggregation semantics requires a separate evidence-backed contract update before use.

### 9. Completeness semantics

These meanings must remain distinct:

```text
pagination exhausted
!=
transactionally frozen, complete point-in-time provider universe
```

They must also remain separate from temporal bucket coverage and product-level completeness:

- new pagination termination evidence describes one collector traversal;
- `coverage_status` describes observed category bucket coverage over time;
- `bounded_sample_caveat="bounded_sample"` remains the public/product caveat and is not removed merely because a traversal exhausted its cursor chain;
- `chzzk_collection_bucket_count_7d` remains persisted global category-fact bucket evidence, not a count of pagination-complete runs and not proof of full provider-population completeness;
- observation ratio `1` remains compatible with incomplete provider-population evidence.

Phase 1 must not add a stronger product-level completeness claim that the implementation cannot prove.

### 10. Collection and mapping remain separate

Collector expansion applies to valid upstream Chzzk observed category evidence, not only categories with a trusted Steam mapping.

The existing parser/schema category evidence boundary remains authoritative. `categoryType=GAME` is provider category-type evidence, not canonical Steam game identity. Candidate, unresolved, rejected, inferred, guessed, fuzzy, or hidden fallback mapping evidence must not become trusted mapping input through this work.

This contract does not authorize mapping discovery/promotion or broader `Combined` semantics.

## Future Phase Authority

### Phase 1 — repository implementation

Phase 1 may implement only the inert repository capability required by this contract, including:

- exhaustion-oriented traversal;
- mandatory finite hard page/request ceiling;
- mandatory overall deadline/time budget;
- repeated-cursor/equivalent loop guard;
- deterministic sanitized termination evidence and compatibility handling;
- the single logical collection-anchor behavior defined above;
- focused synthetic/mocked tests;
- only the durable docs updates required to keep the implementation contract accurate.

Phase 1 must not:

- change `DEFAULT_FETCH_PAGES = 3` or otherwise expand the current authority runtime collection breadth;
- mutate scheduler configuration;
- activate the new traversal on the authority runtime;
- perform a live provider fetch for validation;
- perform DB writes, DDL, backfill, reingest, or bootstrap;
- grant itself Phase 2 authority.

The checked-in capability must remain inert with respect to the separately gated live activation.

### Phase 2 — live activation and bounded runtime verification

Phase 2 may begin only after the required Human Gate is Approved with human-authored GitHub evidence that names the exact approved scope.

Phase 2 may then perform only the approved activation steps, including as applicable:

- selecting the exact authority-runtime hard page/request ceiling and deadline;
- switching actual recurring collector breadth to the reviewed exhaustion-oriented capability;
- exact scheduler/runtime configuration mutation needed for that switch;
- a bounded live provider execution using the approved budgets;
- bounded runtime verification of termination evidence, coordination behavior, and write-path compatibility.

Phase 1 PR merge, Fresh-context review, or this planning-contract merge is not Phase 2 Human Gate approval.

## Acceptance Criteria

### Phase 1 repository implementation

- AC-1: synthetic/mocked tests prove normal success stops on provider pagination exhaustion before the hard ceiling.
- AC-2: tests prove a remaining usable cursor at the hard ceiling terminates as `safety_cutoff`, preserves compatible cutoff evidence, and produces no load-eligible category/channel result.
- AC-3: tests prove deadline expiry and repeated-cursor/loop detection terminate deterministically without further requests and without load-eligible category/channel result.
- AC-4: tests preserve distinguishable `429`, other HTTP, request, invalid JSON, and malformed-page failure evidence with no partial derived result accepted as successful collection.
- AC-5: tests cover compatibility of `pages_fetched`, `pages_requested`, `last_page_next_present`, and `bounded_page_cutoff` alongside the new termination evidence.
- AC-6: a simulated traversal crossing a KST half-hour boundary keeps every derived category/channel row on the single pre-request logical collection anchor and bucket.
- AC-7: focused tests show current no-overlap behavior is not weakened by the new traversal.
- AC-8: multi-page merge behavior remains explicit no-dedupe unless a separately authorized stable identity contract exists; `channelId` alone is not promoted to a dedupe key.
- AC-9: `bounded_sample`, bucket `coverage_status`, collection-bucket denominator meaning, mapping authority, and `Combined` semantics remain unchanged.
- AC-10: current active/default runtime breadth is unchanged and no live provider/runtime/DB activation occurs in Phase 1.

### Phase 2 activation

- AC-11: Human Gate evidence names the exact authority-runtime page/request ceiling, deadline, runtime/scheduler mutation, and bounded verification scope before execution.
- AC-12: bounded verification demonstrates the approved runtime can distinguish exhaustion from every safety/failure termination needed by this contract without weakening no-overlap behavior or public/private evidence boundaries.
- AC-13: activation evidence does not claim a frozen complete provider universe, de-duplicated exact population, or provider quota that has not been proven.

## Required Checks

For Phase 1 implementation, follow the then-current repository runbook and run focused synthetic/mocked pagination, orchestration, timestamp/bucket, and no-overlap tests plus the canonical final code-state validation. No live Chzzk provider call is required or authorized as implementation validation.

For this docs-only planning-contract PR, use the current docs-only static validation contract. Runtime/provider checks are not applicable.

## Manual QA

- Phase 1: no live provider QA. Review deterministic synthetic evidence and confirm the checked-in capability is not wired into authority runtime breadth.
- Phase 2: only the Human-Gate-approved bounded runtime verification may use the live provider/runtime.

## Risk Level

High

Reason: the eventual activation changes recurring external-provider request breadth and can affect collection/write behavior under unknown provider quota/headroom. The docs-only planning task and inert Phase 1 implementation do not themselves exercise that live risk.

## Review Level

Fresh-context

## Review Reason

The future implementation touches pagination/failure semantics, recurring/no-overlap execution, timestamp/bucket semantics, and public/private completeness evidence. Fresh-context review must verify the accepted contract, focused tests, exact validation evidence, and that the implementation remains inert before the Phase 1 merge decision.

## Human Gate Required

Yes

```text
Human Gate Scope:
Phase 2 authority-runtime activation: exact recurring collector breadth/budget selection, any scheduler/runtime mutation that switches the authority runtime to exhaustion-oriented traversal, live provider execution using that broader traversal, and bounded runtime verification.

Pre-Gate Allowed Work:
Phase 1 inert repository implementation, focused tests, required durable docs, canonical validation/CI, required Fresh-context review, and—only after those requirements pass and a Human separately decides to merge—the Phase 1 implementation PR merge. This work must not itself change the authority runtime breadth, scheduler configuration, perform a live provider fetch, or activate the new traversal.

Pre-Gate Merge Allowed:
Yes
```

Human Gate remains Pending until a human-authored GitHub PR comment or review explicitly approves the exact Phase 2 scope. A planning-contract PR, implementation PR, PR merge, agent report, or ChatGPT conversation is not approval evidence.

## Public Repo Safety

Public evidence may include only durable contract text and sanitized aggregate/termination evidence. Do not publish credentials, application identifiers, raw provider payloads, category/channel/title values, private paths, host-specific runtime detail, scheduler XML/stdout, raw terminal output, raw API bodies, or row-level UGC.

The Human-provided 30-page and 60-page diagnostics above are the maximum live diagnostic detail authorized for this public planning record.

## Suggested Branch Name

`docs/chzzk-collector-coverage-contract`

## Suggested PR Title

`docs(chzzk): define collector coverage expansion contract`
