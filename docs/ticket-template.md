# Ticket Template

하나의 ticket은 일반적으로 하나의 PR에 대응한다.

## Ticket ID

-

## Type

Atomic ticket / Bounded polish batch / Read-only review / Planning-contract ticket

## Batch Items

non-batch ticket에는 `N/A`를 사용한다.

## Goal

-

## Scope

-

## Out of Scope

-

## Requirements

-

## Acceptance Criteria

-

## Required Checks

- `./scripts/check.sh`

## Manual QA

-

## Risk Level

Low / Medium / High

## Human Gate Required

Yes / No

API response 구조, durable data semantics, DB/schema/migration, scheduler mutation, live fetch/write, secrets/auth/deploy, read-only를 넘어서는 CI permissions, category-to-game trusted semantics, Combined semantics, broad tooling adoption처럼 운영상 의미 있는 변경에는 Human Gate가 필요하다.

## Public Repo Safety

- raw provider payloads, credentials, private runtime detail, host/path detail, scheduler XML/stdout 또는 row-level UGC를 포함하지 않는다.

## Suggested Branch Name

-

## Suggested PR Title

-
