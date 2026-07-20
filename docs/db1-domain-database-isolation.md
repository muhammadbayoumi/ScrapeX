# DB1 domain database isolation

DB1 separates ScrapeX's operational data into two SQLite files:

- `~/.scrapex/general/general.db` owns generic site and dataset definitions.
- `~/.scrapex/marketlens/marketlens.db` owns the existing product and price path.

The files have different SQLite `application_id` values, required
`database_kind` markers, independent migration ledgers and checksums, and
independent lock, health, backup, and restore operations. ScrapeX refuses a
General file at a MarketLens boundary and vice versa. It never uses `ATTACH`, a
cross-database foreign key, or a distributed transaction.

## Fresh installation

Run:

```text
scrapex init-db
scrapex database-status
```

Initialization creates both files and commits `~/.scrapex/databases.json` only
after both pass health checks.

## Split an existing unified warehouse

First stop the worker and any other process using the warehouse. Then run:

```text
scrapex init-db --db <legacy-harvest.db>
scrapex split-databases --legacy-db <legacy-harvest.db>
scrapex database-status
```

The split takes a pre-split backup, copies each domain to an incoming file,
verifies bounded row counts and checksums, verifies foreign keys, promotes both
files, switches the registry pointer, and seals the legacy file. It does not
delete or update a `price_observation` row. A failure before the pointer switch
leaves the legacy database authoritative; fix the reported cause and retry.

## Backup and restore

Create a bundle containing one independently restorable backup per domain:

```text
scrapex backup-databases --folder <backup-folder>
```

Restore only the affected domain:

```text
scrapex restore-database general <general-backup.db>
scrapex restore-database marketlens <marketlens-backup.db>
scrapex database-status
```

A restore verifies the domain identity and checksum ledger before moving the
live file. The replaced file remains beside it for recovery.

## Rollback

Run:

```text
scrapex rollback-databases
scrapex ui --db <legacy-harvest.db>
```

Rollback unseals the legacy file and switches the registry to explicit legacy
mode. It does not alter or delete either split database. Retry
`split-databases --legacy-db <legacy-harvest.db>` when ready to switch forward.

## Compatibility boundary

The explicit `--db` option remains the temporary unified-database compatibility
path for rollback and migration. Normal commands use the typed registry. The
old `/api/catalog` route remains an alias while G2 rebases; the authoritative
generic route is `/api/general/catalog`.
