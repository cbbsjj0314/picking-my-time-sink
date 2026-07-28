# Ticket Template

하나의 ticket은 일반적으로 하나의 PR에 대응한다.

## Ticket ID

-

## Type

Atomic ticket / Bounded polish batch / Read-only review / Planning-contract ticket

## Batch Items

non-batch ticket에는 `N/A`를 사용한다.

## User Decision

- Problem:
- Why now:
- Observable success:
- Must not change:

## Scope

-

## Out of Scope

-

## Requirements

-

## Acceptance Criteria

- AC-1:
- AC-2:

### User Acceptance Examples

Behavior 또는 semantics가 바뀌지 않는 작은 작업에는 `N/A`를 사용한다.

- Expected case:
- Boundary case:
- Must not happen:

## Required Checks

- `./scripts/check.sh`

## Manual QA

-

## Risk Level

Low / Medium / High

## Review Level

Standard / Fresh-context

## Review Reason

-

## Human Gate Required

Yes / No

Implementation 전에 `Risk Level`, `Human Gate Required`, `Review Level`을 확정한다. Implementation agent는 사전 결정된 세 값을 낮추지 않는다. 더 강한 gate가 필요해지면 구현을 계속하거나 자체 재분류하지 않고 planning 흐름으로 되돌린다.

API response 구조, durable data semantics, DB/schema/migration, scheduler mutation, live fetch/write, secrets/auth/deploy, read-only를 넘어서는 CI permissions, category-to-game trusted semantics, Combined semantics, broad tooling adoption처럼 운영상 의미 있는 변경에는 Human Gate가 필요하다.

## Public Repo Safety

- raw provider payloads, credentials, private runtime detail, host/path detail, scheduler XML/stdout 또는 row-level UGC를 포함하지 않는다.

## Suggested Branch Name

-

## Suggested PR Title

-
