# Category-To-Game Alias / Manual Hint Seeding Assist Gate

Status: implementation gate
Ticket: CATEGORY-MAPPING-ALIAS-HINT-SEEDING-ASSIST-GATE-001
Documented: 2026-05-24 (KST)

## Purpose

이 문서는 `CATEGORY-MAPPING-ALIAS-HINT-REAL-DATA-SMOKE-001`이 approved alias/manual hint source 부재로 실행될 수 없었던 이후, future private/local review seeding assist를 검토할 수 있는지에 대한 decision boundary를 고정한다.

이 gate는 review seeding assist를 구현하지 않는다. 이 gate는 real-data smoke execution, API call, DB query, service start/stop/restart, scheduler action, live fetch, DB write, code implementation, SQL migration, API/web/serving change, 또는 `Combined` semantics를 수행하거나 승인하지 않는다.

목적은 fully manual category-to-game mapping의 review workload를 줄일 수 있는 future private/local aid를 검토하되, 그 output이 `alias`, `manual_hint`, `candidate`, trusted mapping, 또는 serving truth로 자동 승격되지 않도록 먼저 경계를 고정하는 것이다.

## Prior Decision Basis

이 gate는 아래 prior decision chain을 따른다.

- `CATEGORY-MAPPING-CANDIDATE-GENERATION-DRY-RUN-001`은 synthetic exact-match dry-run support를 추가했다.
- Real-data exact-match smoke는 유용한 candidate signal을 생성하지 못했다.
- `CATEGORY-MAPPING-NON-EXACT-MATCHING-GATE-001`은 fuzzy matching 및 automatic alias discovery를 금지(forbidden) 상태로 유지했다.
- `CATEGORY-MAPPING-ALIAS-HINT-CONTRACT-GATE-001`은 `hint_kind = "alias" | "manual_hint"`를 synthetic/test-only contract family로 정의했다.
- `CATEGORY-MAPPING-ALIAS-HINT-DRY-RUN-001`은 synthetic/test-only alias/manual hint dry-run support를 구현했다.
- `CATEGORY-MAPPING-ALIAS-HINT-REAL-DATA-GATE-001`은 real-data alias/manual hint work를 future read-only, no-write, sanitized aggregate smoke로만 제한했다.
- `CATEGORY-MAPPING-ALIAS-HINT-REAL-DATA-SMOKE-001`은 approved alias/manual hint source가 없어서 진행할 수 없었다.

허용된 aggregate evidence를 언급할 때는 아래 수준으로만 제한한다.

- alias/manual hint source: absent
- result status: unknown / insufficient approved source
- DB write performed: false
- candidate insert performed: false
- raw values printed: false

이 문서는 raw category names, raw game names, raw alias/hint rows, raw seed rows, raw API responses, raw SQL output, raw command transcript, private paths, credentials, 또는 `.env` values를 포함하지 않는다.

## Problem

Fully manual category-to-game mapping은 row-by-row로 처음부터 수행하기에는 scalable하지 않다. Real category와 game 후보가 많아질수록 사람이 모든 조합을 직접 검토하는 방식은 review workload가 빠르게 커지고, ambiguity와 conflict를 일관되게 기록하기 어렵다.

현재 project에는 approved real-data alias/manual hint source가 없다. 따라서 `CATEGORY-MAPPING-ALIAS-HINT-REAL-DATA-SMOKE-001`은 approved source absence 때문에 실행될 수 없었고, real-data alias/manual hint smoke는 여전히 blocked 상태다.

Future assist step은 사람이 검토할 private/local review seed를 만들어 workload를 줄이는 데 도움이 될 수 있다. 그러나 assist output은 automatic mapping이 아니며, 자동으로 alias/manual hint evidence, candidate row, trusted mapping, serving truth가 되어서는 안 된다.

## Decision

Private/local review seeding assist may be considered only as a future read-only, no-write, human-review aid. Review seed output is not `alias`, `manual_hint`, `candidate`, `trusted`, `approved`, or serving truth unless a later Human Gate and human curation step explicitly promotes it.

즉, private/local review seeding assist는 향후 별도 ticket에서 read-only, no-write, human-review aid로만 검토할 수 있다. Review seed output은 사람이 명시적으로 curate/adopt하고 별도 Human Gate가 승인하기 전까지 `alias`, `manual_hint`, `candidate`, `trusted`, `approved`, 또는 serving truth가 아니다.

이 결정은 아래를 의미한다.

- Private/local review seeding assist may be considered only as future work.
- Review seed output은 `alias` evidence가 아니다.
- Review seed output은 `manual_hint` evidence가 아니다.
- Review seed output은 `candidate`가 아니다.
- Review seed output은 trusted mapping이 아니다.
- Review seed output은 API/web/serving output이 아니다.
- Review seed output은 `Combined`가 아니다.
- Review seed output은 later Human Gate 및 human curation step이 명시적으로 채택하기 전까지 alias/manual hint evidence가 될 수 없다.
- Public artifacts는 sanitized aggregate-only로 유지한다.
- Real category/game names 및 seed rows는 private/local only로 유지한다.
- DB writes, candidate inserts, trusted mapping, API/web/serving, 그리고 `Combined`는 계속 forbidden이다.
- Fuzzy matching 및 automatic alias discovery는 계속 forbidden이다.

## Review Seed Boundary

`review seed`는 사람이 검토할 수 있도록 private/local에서만 생성되는 candidate pair 또는 suggestion이다. 이 용어는 review workload를 줄이기 위한 operator aid를 가리키며, durable mapping evidence나 storage row를 뜻하지 않는다.

Core boundary:

```text
review seed ≠ alias/manual_hint
review seed ≠ candidate
review seed ≠ trusted mapping
review seed ≠ serving truth
```

Review seed는 아래로 해석해야 한다.

- Review seed is not an alias.
- Review seed is not a manual hint.
- Review seed is not a candidate proposal.
- Review seed is not trusted mapping.
- Review seed is not API/web/serving output.
- Review seed is not `Combined`.
- Review seed is private/local operator evidence only.
- Human adoption is required before a seed can become future `alias` or `manual_hint` evidence.

Human adoption은 별도의 approved future step에서만 가능하다. 그 future step도 public-safe strategy가 승인되기 전까지 private/local로 유지되어야 하며, real category/game names 또는 seed rows를 public docs/tests/PR bodies에 복사해서는 안 된다.

## Allowed Future Assist Direction

향후 별도 gate 또는 별도 read-only private report ticket은 deterministic private/local assist methods를 검토할 수 있다. 이 ticket은 아래 방법들을 구현하거나 승인하지 않는다.

These methods are not implemented by this ticket. 또한 이 methods는 automatic mapping, trusted mapping, candidate storage, 또는 alias/manual hint evidence creation으로 승인되지 않는다.

Future candidates로 검토할 수 있는 method family:

- normalized token overlap
- substring containment
- punctuation/spacing normalization
- casefold/whitespace normalization
- known suffix/prefix trimming
- top-N private/local review seed report
- aggregate-only public completion report

이 methods는 matching policy가 아니다. Token overlap 또는 substring containment를 언급하더라도, 이는 private/local review seed assist candidate일 뿐이며 automatic matching, fuzzy matching, automatic alias discovery, candidate generation for storage, 또는 trusted mapping approval이 아니다.

Future assist work는 아래를 모두 만족해야 한다.

- separately approved ticket이어야 한다.
- read-only여야 한다.
- no-write여야 한다.
- DB에 write해서는 안 된다.
- `chzzk_category_game_candidate`에 insert해서는 안 된다.
- public row-level output을 만들면 안 된다.
- alias/manual hint evidence를 자동 생성하면 안 된다.
- generated seed rows를 trusted mapping처럼 취급하면 안 된다.
- exact source, scoring/candidate generation method, stop conditions, public/private output boundary를 future ticket에서 먼저 정의해야 한다.

## Forbidden Interpretation

Review seeding assist는 아래가 아니다.

- fuzzy matching
- automatic alias discovery
- automatic matching
- trusted mapping
- automatic candidate generation for storage
- automatic `alias` generation
- automatic `manual_hint` generation
- promotion/demotion workflow
- API/web/serving change
- `Combined`

이 문서는 fuzzy matching이 구현되었거나 승인되었다고 주장하지 않는다. Automatic alias discovery가 구현되었거나 승인되었다고 주장하지 않는다. Deterministic assist method를 future review aid 후보로 언급하더라도, 그 output은 matching decision이나 identity assertion이 아니라 private/local review seed일 뿐이다.

## Public Artifact Boundary

Public artifacts include:

- PR body
- public docs
- tests
- fixtures/examples
- repo-committed logs/reports
- Codex completion reports that may be copied into public PRs

Public artifacts may include only sanitized aggregate output, such as:

- input category count
- input game count
- review seed row count
- method family count
- conflict/ambiguous seed count
- skipped/unknown count
- DB write performed: false
- candidate insert performed: false
- raw values printed: false

Public artifacts must not include:

- real category names
- real game names
- real alias names
- real manual hint rows
- real review seed rows
- real channel/display values
- live titles
- thumbnails
- raw provider payloads
- raw API responses
- raw SQL output
- private paths
- credentials
- `.env` values
- scheduler XML/stdout
- raw runtime logs
- screenshots
- row-level UGC
- raw command transcript
- raw Grafana/Prometheus responses

## Private / Local Evidence Boundary

Review seed rows may exist only as private/local operator evidence before a future explicit public-safe strategy exists.

- Private/local seed rows must not be copied into public docs or tests.
- Public docs may refer to review seeds only as a source class, not by value.
- If future work generates a private/local seed report, public completion output must summarize aggregate counts only.
- If aggregate-only reporting cannot be guaranteed, future work must stop.
- Raw/private review seed evidence must not be promoted into public fixtures, examples, docs, PR bodies, or committed reports.

## Relationship To Alias / Manual Hint

`alias` is a curated alternate label that may help propose a review candidate. 즉, `alias`는 검토 후보(review candidate)를 제안하는 데 도움이 될 수 있는 curated alternate label이다.

`manual_hint`는 사람이 제공한 review hint이며, 검토 후보를 제안하는 데 도움이 될 수 있다.

Review seed output is neither of these. 즉, review seed output은 `alias`도 아니고 `manual_hint`도 아니다.

Boundary:

- Review seed output may become `alias` or `manual_hint` only after human curation in a separately approved future step.
- Human curation step must remain private/local until a public-safe strategy is approved.
- `hint_kind = "alias" | "manual_hint"` must not be assigned automatically by seeding assist without human adoption.
- Review seed output must not create trusted mapping.
- Review seed output must not create serving truth.
- Review seed output must not bypass review.
- Review seed output must not directly produce `trusted` / `approved`.

## Relationship To Candidate Storage

Review seed assist는 candidate storage가 아니다.

Preserved boundary:

- no DB write
- no insert into `chzzk_category_game_candidate`
- no candidate write smoke
- no durable candidate state
- no trusted mapping
- no `approved`
- no `trusted`
- no serving truth
- no API/web/serving/`Combined`

Writing seed rows would make private/local suggestions look like durable review evidence. 즉, seed row를 storage에 쓰면 private/local suggestion이 승인된 durable review evidence처럼 보일 수 있다.

Candidate storage requires separate write policy, audit trail, and Human Gate. `chzzk_category_game_candidate` insert 또는 candidate write smoke는 storage/write policy, audit trail, review workflow, public/private evidence boundary가 별도로 승인된 이후에만 검토할 수 있다.

Review seed assist is only workload reduction, not persistence. 즉, review seed assist의 목적은 검토 부담을 줄이는 것이지 persisted state를 만드는 것이 아니다.

## Explicit Non-Goals

이 gate는 아래 항목을 승인하거나 구현하지 않는다.

- code implementation
- review seeding assist implementation
- real-data smoke execution
- API call
- DB query
- service start/stop/restart
- scheduler action
- live fetch
- DB write
- insert into `chzzk_category_game_candidate`
- schema/DDL changes
- SQL migration
- public fixture with real names
- fuzzy matching
- automatic alias discovery
- automatic matching
- trusted mapping
- promotion/demotion workflow
- `game_external_id`
- tracked_universe
- App Catalog
- API endpoint changes
- web UI changes
- serving semantics
- `Combined`
- backfill/reingest
- raw/private evidence promotion

## Required Validation For Future Work

Future review seeding assist work must:

- be separately approved
- be read-only
- be no-write
- use explicitly approved source commands/paths only
- not start/stop/restart services
- not mutate scheduler/runtime
- not inspect or print credentials/`.env` values
- not commit any public file containing real values
- report sanitized aggregate output only
- confirm DB write performed: false
- confirm candidate insert performed: false
- confirm raw values printed: false
- stop if source shape is ambiguous
- stop if aggregate-only reporting cannot be maintained
- stop if method output cannot be distinguished from automatic mapping

Future validation must also confirm that public artifacts contain no real category/game/channel/display values, real alias names, real manual hint rows, real review seed rows, live titles, thumbnails, raw provider payloads, raw API responses, raw SQL output, private paths, credentials, `.env` values, scheduler XML/stdout, raw runtime logs, screenshots, row-level UGC, raw command transcript, or raw Grafana/Prometheus responses.

## Stop Conditions For Future Work

Future work must stop if:

- source requires raw provider payload printing
- source requires real category/game names in public output
- source requires credentials or `.env` value inspection
- source requires DB write or candidate insert
- source requires API/web/serving changes
- source requires `Combined`
- source requires fuzzy matching or automatic alias discovery
- source produces row-level output that cannot be sanitized
- generated seeds would be treated as alias/manual hint without human curation
- generated seeds would be treated as trusted mapping
- generated seeds would be persisted without a separate write gate
- source shape is ambiguous
- aggregate-only reporting cannot be maintained
- method output cannot be distinguished from automatic mapping

## Next Ticket

Recommended next ticket:

`CATEGORY-MAPPING-REVIEW-SEEDING-ASSIST-GATE-001`

Reason:

- It avoids implying that seeding assist automatically creates `alias` or `manual_hint`.
- It names the work as review-seed generation, not alias/hint generation.

Next ticket goal:

`Define the exact private/local read-only review seed report method, source boundary, and aggregate-only public output before any implementation.`

The next ticket must remain:

- docs/decision first
- no implementation
- no real names in public artifacts
- no DB write
- no candidate insert
- no trusted mapping
- no API/web/serving/`Combined`
- fuzzy matching forbidden
- automatic alias discovery forbidden
- generated seed rows are not alias/manual_hint until human curated

## Deferred Items

- review seeding assist implementation
- private/local review seed source creation
- concrete deterministic assist method selection
- scoring/candidate generation method definition
- top-N private/local report implementation
- aggregate-only public completion report implementation
- real-data smoke execution
- DB query
- DB write
- insert into `chzzk_category_game_candidate`
- candidate write smoke
- candidate storage/write policy
- audit trail and review workflow
- human curation workflow
- trusted mapping
- promotion/demotion workflow
- API/web/serving changes
- `Combined`
- fuzzy matching
- automatic alias discovery
- automatic matching
- automatic `alias` generation
- automatic `manual_hint` generation
- `game_external_id`
- tracked_universe
- App Catalog
- backfill/reingest
- live fetch
- scheduler mutation
- raw/private evidence promotion
