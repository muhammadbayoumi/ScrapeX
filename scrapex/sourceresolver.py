"""One question — *which source is this key?* — answered against BOTH registries.

`R-78`: the scheduler resolves a source through `source_site`, and `sources.yaml` stops
being a registry. This is that ruling's one moving part.

WHAT THE WORKER ACTUALLY ASKS OF A SOURCE, measured against `scrapex/jobs.py` on
2026-08-30 rather than assumed. Three things, and nothing else:

    manifest.get(key)                       -> an entry            (jobs.py:606)
    entry.base_url                          -> the politeness host (jobs.py:391)
    capture(conn, entry, job_id, **extras)  -> a CaptureResult     (jobs.py:622)

**Nothing in `jobs.py` knows what a price source is.** It never reads `unit_charter`,
never touches a connector, never mentions a table. So a second worker for contractors
would have been a second copy of host lanes, cross-job admission, pause and resume,
archive-before-rebuild, per-source failure isolation and the counters — **seven mechanisms
that already exist and none of which `contractors.py` has.** That is what `R-78` means by
the fourth row being history rather than design, and it is why this module is small: the
seam was always there, and only the resolver was missing.

WHY A RESOLVER AND NOT A WIDER MANIFEST. `sources.yaml` is a file a developer edits, and
`R-48` says the extension is the only interface. A source registered through the panel
lands in `source_site` and must be crawlable without anybody opening an editor -- which is
what `CLAUDE.md` already promises for shops (*"a new shop needs no new module"*) and what
muqawil never had. Widening the file would have kept the door shut.

THE MANIFEST WINS A COLLISION, and it is not a preference. Twelve audited price sources
are declared there with a `unit_charter`, a locale and a connector; a `source_site` row
carries none of that. If a key somehow existed in both, resolving to the registry row
would silently drop the contract `SR-13` exists to enforce. So the file is asked first and
the registry answers for what it does not know.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


class UnknownSource(LookupError):
    """No registry knows this key, so no job can be queued for it."""


@dataclass(frozen=True)
class RegistrySource:
    """A source declared in `source_site` rather than in the manifest.

    It answers `base_url` because that is the only attribute the worker reads off an
    entry, and it carries `crawl_scope` because the collector needs it and reading it
    twice would be two places to disagree about one fact.
    """

    source_key: str
    base_url: str
    display_name: str = ""
    crawl_scope: str = ""


def registry_source(conn: sqlite3.Connection, source_key: str) -> RegistrySource | None:
    """The live `source_site` row for a key, or None.

    `valid_to IS NULL` is the whole of "live": `0014` closed the old `muqawil` row rather
    than deleting it, so a query without this predicate resolves a retired source and
    queues a job against a registration somebody deliberately ended.
    """
    row = conn.execute(
        "SELECT source_key, base_url, source_name, crawl_scope FROM source_site "
        " WHERE source_key = ? AND valid_to IS NULL", (source_key,)).fetchone()
    if row is None:
        return None
    return RegistrySource(source_key=row[0], base_url=row[1] or "",
                          display_name=row[2] or "", crawl_scope=row[3] or "")


class SourceResolver:
    """`manifest.get(key)` widened to the registry, with the manifest's own shape.

    IT IS DUCK-COMPATIBLE WITH `Manifest` ON PURPOSE. `jobs.py` takes the manifest as a
    bare `object` and calls `.get`; `_host_of` calls `.get(key).base_url` inside a
    `try/except`. Matching that shape means **`jobs.py` needs no change at all** -- the
    resolver is passed where the manifest was, and every lane, reservation and isolation
    mechanism keeps working on a contractor source without knowing one exists.
    """

    def __init__(self, manifest, connect):
        #: `connect` is a callable rather than a connection because the worker resolves
        #: keys from lane threads, and sqlite3 refuses a connection across threads --
        #: the same reason `run_job_once` takes `connect` rather than a connection.
        self._manifest = manifest
        self._connect = connect

    def get(self, source_key: str):
        """The manifest's entry, else the registry's row, else `UnknownSource`.

        RAISES A LOOKUP ERROR, like `Manifest.get` raises `KeyError` -- `UnknownSource`
        subclasses it, so every existing `except KeyError` around this call keeps catching
        what it caught before. A resolver that returned None instead would turn
        `POST /api/jobs`'s clear 404 into an `AttributeError` deeper in the worker, which
        is the delayed failure `R-71` measured and `OP-92` records.
        """
        try:
            return self._manifest.get(source_key)
        except KeyError:
            pass
        conn = self._connect()
        try:
            found = registry_source(conn, source_key)
        finally:
            conn.close()
        if found is None:
            raise UnknownSource(f"unknown source_key {source_key!r}")
        return found

    def resolve_by_url(self, url: str):
        """Delegated unchanged. The extension asks *which source is this tab?* and only
        the manifest can answer it today -- a registry row has a `base_url` but no
        connector, so matching one would name a source the panel cannot then act on."""
        return self._manifest.resolve_by_url(url)

    @property
    def sources(self):
        """The manifest's own list, unwidened, and the reason is a real caller.
        `app.py` builds `{entry.source_key: entry for entry in manifest.sources}` to
        render price-source cards; adding registry rows there would put a contractor
        source into a list every consumer treats as price entries."""
        return self._manifest.sources
