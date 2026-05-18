# Ticket Template

One ticket should normally map to one PR.

## Ticket ID

-

## Type

Atomic ticket / Bounded polish batch / Read-only review / Planning-contract ticket

## Batch Items

Use `N/A` for non-batch tickets.

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

Human Gate is required for operationally meaningful changes, including API response shape or durable data semantics, DB/schema/migration, scheduler mutation, live fetch/write, secrets/auth/deploy, CI permissions beyond read-only, category-to-game trusted semantics, Combined semantics, and broad tooling adoption.

## Public Repo Safety

- Do not include raw provider payloads, credentials, private runtime detail, host/path detail, scheduler XML/stdout, or row-level UGC.

## Suggested Branch Name

-

## Suggested PR Title

-
