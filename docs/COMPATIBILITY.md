# ScrapeX Compatibility Contract

This document is the Phase G0 baseline for evolving ScrapeX into a generic
crawling and data-modeling platform without replacing the working product.

The repository behavior and its tests are authoritative. A later roadmap item
does not override a working compatibility guarantee by itself.

## Protected behavior

The following behavior must remain operational while generic capabilities are
introduced:

- Product and price ingestion continues to use the current normalized contract.
- `price_observation` remains append-only and protected by database triggers.
- Existing warehouse files remain readable and migratable.
- Contract-version mismatches continue to refuse writes.
- Existing connectors, manifests, jobs, schedules, reports, and exports keep
  their current public behavior unless a reviewed change explicitly replaces it.
- A crawl job belongs to the Local Runtime, not to the Side Panel lifecycle.
- Pause, resume, cancellation, checkpoint recovery, and bounded log reads remain
  persistent runtime responsibilities.
- Native Messaging remains versioned and cursor-paginated; localhost HTTP remains
  a compatibility fallback.
- Arabic scraped content remains data with automatic direction; interface and
  code language remain English.
- Original Schema and Current View remain separate concepts; presentation changes
  never delete source data.
- Backup, restore, move, retention, and compaction never silently destroy the
  current warehouse or append-only price history.

## Additive evolution rules

Generic-platform work must use additive seams:

1. Database changes use numbered, forward-only migrations.
2. New generic tables do not repurpose existing price columns.
3. The price workflow remains the reference domain until a generic path proves
   end-to-end parity where the two intentionally overlap.
4. New APIs are added beside existing APIs before any compatibility route is
   retired.
5. Old data is migrated by explicit, tested code; it is never rewritten merely
   to make an internal model look cleaner.
6. A replacement path must have rollback instructions before it may become the
   default.

## Warehouse identity and restore safety

A healthy SQLite file is not automatically a ScrapeX warehouse.

Before restore or migration, storage code must verify:

- A supported `PRAGMA user_version`.
- Required core warehouse tables.
- Append-only observation triggers.
- The ScrapeX contract marker for schema version 2 and later.
- SQLite integrity and foreign-key checks.

Restore copies into a staging file and verifies that copy while the current
warehouse remains live. Only the verified staging file may be switched into
place; the previous warehouse is moved aside and never deleted automatically.

## Feature-gate policy

`scrapex.features` is the single public manifest of shipped and planned
capabilities. A generic capability remains disabled until its vertical slice has:

- Persistent storage.
- A real API path.
- A usable UI workflow when the capability is user-facing.
- Failure and recovery behavior.
- Automated tests.
- Compatibility verification against price workflows.

Disabled capabilities must not appear as functional navigation or static mock
controls. `/api/features` allows the extension and Workspace to make the same
decision from one source of truth.

## Human review gates

Programmer approval is required before:

- Destructive or irreversible migration.
- Record-identity behavior changes.
- Automatic approval of inferred schema renames or dataset relationships.
- Retirement of an existing API, CLI command, transport, or output path.
- Changing the database that acts as the source of truth.
- Enabling remotely updated adapter configurations.

Each implementation slice is delivered on its own branch and Draft Pull Request.
The PR must include compatibility impact, migrations, tests, visual evidence when
applicable, known limitations, and rollback behavior. Codex may address review
feedback, but the programmer owns approval and merge.
