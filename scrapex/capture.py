"""Capture service: run a source's connector and ingest in one step (DRY).

Shared by the CLI (funnel/local-inbox path stays separate) and the local web
API that the Chrome extension calls. The extension NEVER re-implements parsing:
it triggers this, which reuses the Python connectors + the one ingest pipeline.
"""
from __future__ import annotations

import sqlite3
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field
from typing import Callable

from . import settings
from .config import SourceEntry
from .connectors.factory import build_connector
from .ingest import IngestResult, ingest_payloads


class WarehouseSupersededError(RuntimeError):
    """The database this crawl opened stopped being the live one mid-flight."""


def _refuse_if_superseded(conn: sqlite3.Connection) -> None:
    """Abort rather than ingest into a database that was sealed while we crawled.

    The write lock serialises a commit DURING a compaction, but not one made
    immediately AFTER it by a crawl that began before it: `connector.fetch` runs
    for minutes holding no lock, and the connection it returns to is a handle on
    a file that may since have been sealed and replaced. Those observations
    would land in the archive and be invisible to the live warehouse forever.

    Checked HERE, inside the lock and immediately before the insert, because
    that is the only point where the answer cannot go stale again.

    THE SEAL IS READ THROUGH THIS CRAWL'S OWN HANDLE, not by reopening a path.
    `PRAGMA database_list` reports the file as it was named when the connection
    opened, and a compaction RENAMES it: on macOS and Linux that rename succeeds
    while handles are open, so the recorded path no longer exists. The previous
    version passed that stale path to `storage.sealed_at`, whose first line
    returns "" for a path that is not there — so the guard saw no seal, said
    nothing, and let the crawl write into the sealed archive. Exactly the
    disaster the paragraphs above describe, produced by the guard against it.

    The handle does not care what the file is called. It is attached to the
    database itself, and a seal another connection committed is visible to it.
    """
    from . import storage

    row = conn.execute("PRAGMA database_list").fetchone()
    path = row[2] if row is not None else ""
    if not path:
        return                              # in-memory database: nothing to seal
    try:
        found = conn.execute("SELECT value FROM scrapex_meta WHERE key = ?",
                             (storage.SEALED_KEY,)).fetchone()
    except sqlite3.DatabaseError:
        # Older than migration 0002: no scrapex_meta to read, so nothing can
        # have sealed it. Silence here is the truth, not a swallowed error.
        return
    when = found[0] if found else ""
    if when:
        raise WarehouseSupersededError(
            f"The warehouse was replaced at {when} while this crawl was running, "
            f"so its rows were not written: they would have gone into the sealed "
            f"archive at {path} rather than the live database. Run the crawl again."
        )


def crawl_settings(conn: sqlite3.Connection) -> dict:
    """The owner's politeness choices (spec 33), read once per capture.

    Read here rather than inside the fetcher so the connector layer keeps no
    dependency on the database, and so a bad saved value degrades to the shipped
    default instead of failing a crawl.
    """
    def number(key: str, fallback: float) -> float:
        try:
            return float(settings.get(conn, key))
        except (ValueError, TypeError):
            return fallback

    return {
        "min_interval_s": number("crawl_min_interval_s", 1.0),
        "timeout_s": number("crawl_timeout_s", 30.0),
        "user_agent": settings.get(conn, "crawl_user_agent"),
        # The owner's per-run choice (2026-07-28): may this crawl ignore the
        # Crawl-delay a site asks for? Absent reads as HONOUR — silence must
        # never be permission to go faster than a site asked.
        #
        # It is his call to make: elburoj asks for 10 seconds and publishes
        # 6,720 products, which is a 25-hour crawl. But the consequence is real,
        # so the run SAYS which pace it used either way rather than leaving a
        # fast crawl and a polite one indistinguishable afterwards.
        "honour_crawl_delay": settings.get(conn, "crawl_honour_delay") not in
                              ("0", "false", "False", False),
    }


def _job_progress(conn: sqlite3.Connection, job_id: int, source_key: str,
                  fetcher=None) -> Callable[[int, str], None]:
    """A per-request heartbeat for the job row, throttled to stay negligible.

    Every 10 requests the heartbeat and this source's live slot move — the
    panel's progress figure ticks and a watchdog can tell life from a hang.
    Every 50, one log line states plainly what is happening.

    `fetcher` is read, never written: it is already counting everything worth
    showing (304s, retries, the pace actually in force, the frontier a connector
    declared), and reading it here is what puts those facts on the panel without
    a second accounting of any of them. Omitted, the tick still records the
    count — every existing caller and test keeps working.
    """
    def measurements(count: int) -> dict:
        live: dict = {"requests": count, "state": "fetching"}
        if fetcher is None:
            return live
        # A connector that enumerated its frontier outranks the estimate seeded
        # from the last successful run: it counted, the estimate guessed.
        expected = getattr(fetcher, "expected_requests", None)
        if expected:
            live["expected"] = int(expected)
            live["basis"] = "declared"
            live["as_of"] = None
        # 304s are the single best sign a recurring crawl is being cheap and
        # polite, and retries the best early sign a site is pushing back.
        live["not_modified"] = int(getattr(fetcher, "not_modified_count", 0) or 0)
        live["retries"] = int(getattr(fetcher, "retry_count", 0) or 0)
        # The pace IN FORCE, which is not the setting: robots.txt can raise it
        # (see HttpFetcher._robots_for), and whether that was honoured is the
        # owner's own per-run choice. A run that was fast because the site asked
        # for nothing and one that was fast because we overrode a 10s delay must
        # not look identical while it happens.
        live["pace_s"] = float(getattr(fetcher, "_min_interval_s", 0.0) or 0.0)
        live["honouring_delay"] = bool(getattr(fetcher, "_honour_crawl_delay", True))
        return live

    def publish(count: int, *, force: bool = False) -> None:
        from .jobs import record_source_fetch

        record_source_fetch(conn, job_id, source_key, **measurements(count))
        if not force and count and count % 50 == 0:
            # Local import: jobs.py imports this module at its top.
            from .jobs import append_log
            append_log(conn, job_id, f"fetching — {count} requests so far",
                       source_key=source_key)
        conn.commit()

    def tick(count: int, url: str) -> None:
        if count % 10:
            return
        # The owner's Pause/Cancel used to apply only BETWEEN sources, so a
        # single 15-minute crawl had no brakes at all. The same tick that
        # writes the heartbeat now reads the intent, and an interrupt rides
        # the CrawlBlocked propagation path every connector already honours.
        control = conn.execute(
            "SELECT control FROM crawl_job WHERE job_id = ?", (job_id,)).fetchone()
        if control and control[0] in ("cancel", "pause"):
            from .connectors.base import CrawlInterrupted
            raise CrawlInterrupted(control[0])
        publish(count)

    # A declaration arrives once, normally while the count is still in single
    # figures, so it must not wait for the tenth-request tick — otherwise every
    # crawl that DOES know its total would show "unknown" for its first ten
    # pages, which is the complaint this is here to answer.
    tick.on_expectation = lambda _total: publish(
        getattr(fetcher, "requests_count", 0) or 0, force=True)
    return tick


@dataclass
class CaptureResult:
    ingest: IngestResult
    requests_count: int
    tables: int
    rows: int = 0          # raw rows the connector produced — the F6 canary input
    # The connector's own account of what it could NOT collect: skipped
    # countries, pages that published nothing, an energy type that produced no
    # rows. The CLI printed these; the job path dropped them on the floor, so a
    # run that silently lost NATURAL_GAS entirely logged three clean lines and
    # read as a full success.
    warnings: list[str] = field(default_factory=list)
    # Politeness disclosures from the fetcher (robots crawl-delay honoured,
    # Disallow crossed, Retry-After capped). Owner ruling (docs/
    # robots-policy.md): these are INFO — they describe how we behaved toward
    # the site, not a defect in the data — so they must never be dressed as
    # warnings that suggest the run needs review.
    notes: list[str] = field(default_factory=list)


def capture_source(conn: sqlite3.Connection, entry: SourceEntry,
                   job_id: int | None = None,
                   lock: Callable[[], AbstractContextManager] | None = None,
                   history: bool = False, resume: bool = False,
                   archive_first: bool = False) -> CaptureResult:
    """Fetch a source via its connector and ingest straight into harvest.db.

    `lock` (when given) wraps ONLY the ingest write. Holding the process-wide DB
    lock across `connector.fetch` would keep it for the whole network crawl —
    minutes of politeness delays — during which every unrelated UI write (renaming
    a column, saving a view) is refused. The fetch touches no database at all, so
    it has no business holding a database lock.

    A JOB capture journals every yielded table to disk as it arrives, so a
    pause or crash at page 399 of 400 loses nothing: `resume=True` (passed by
    the job loop only for the exact source that was paused mid-fetch) reuses
    the journal and hands the connector the tokens it may skip. The journal is
    a separate dir from the CLI inbox — a job clearing its own state must
    never touch payloads the owner crawled and has not ingested yet.

    Connector/network errors propagate; per-row data errors are isolated (Q3)."""
    from . import localinbox

    connector, fetcher = build_connector(entry, crawl_settings(conn))
    if history:
        # The panel gates this per source, but a job is data and data can be
        # forged; the capability check here is the one that counts. Running
        # "history" on a connector that has none would silently be a normal
        # crawl wearing the wrong name.
        if not hasattr(connector, "_history"):
            fetcher.close()
            raise ValueError(
                f"history backfill is not supported for family "
                f"{entry.family.value!r}")
        connector._history = True
    journal = job_id is not None
    if journal:
        if resume:
            # Untokenized entries (summary tables, list rows) are re-emitted
            # by the re-run; keeping the paused attempt's copies would ingest
            # them twice. Tokenized pages are the whole point: kept, skipped.
            localinbox.clear_untokenized(localinbox.JOURNAL_DIR, entry.source_key)
            tokens = localinbox.list_tokens(localinbox.JOURNAL_DIR, entry.source_key)
            if tokens and hasattr(connector, "skip_tokens"):
                connector.skip_tokens = tokens
            elif tokens:
                # A connector that cannot skip cannot resume: refetching whole
                # while keeping the journal would double-ingest every page.
                localinbox.clear(localinbox.JOURNAL_DIR, entry.source_key)
        else:
            # Stale journal from a cancelled or crashed earlier job: pages
            # fetched on a DIFFERENT day must never mix into this crawl.
            localinbox.clear(localinbox.JOURNAL_DIR, entry.source_key)
    if job_id is not None and hasattr(fetcher, "on_request"):
        # A long single-source fetch was INVISIBLE: the job's progress unit is
        # sources, so a 450-page country crawl sat at "0/1, 0 requests" with a
        # start-time heartbeat for a quarter hour — indistinguishable from a
        # hang. The fetch holds no lock (see above), so these tiny job-row
        # writes are exactly the kind the lock design set out to keep flowing.
        tick = _job_progress(conn, job_id, entry.source_key, fetcher)
        fetcher.on_request = tick
        # The other half of the same display: the moment a connector knows how
        # many pages it will fetch, the panel's bar gains a real denominator.
        if hasattr(fetcher, "on_expectation"):
            fetcher.on_expectation = tick.on_expectation
    tables: list = []
    try:
        for t in connector.fetch(entry):            # network only — no DB involved
            tables.append(t)
            if journal:
                # Journal AS FETCHED, not after: the whole point is surviving
                # an interruption between here and the ingest.
                localinbox.write_payload(localinbox.JOURNAL_DIR, t.to_payload(),
                                         token=t.page_token)
        requests_count = fetcher.requests_count
    except Exception as exc:
        from .connectors.base import CrawlInterrupted
        if journal and isinstance(exc, CrawlInterrupted):
            # The journaled pages survive, but their warnings live only in
            # memory (the payload contract carries none) — flush them to the
            # job log now or the resume silently forgets e.g. which countries
            # published nothing this week. Politeness notes flush at INFO
            # (owner robots ruling), data warnings at WARNING.
            from .jobs import append_log
            from .vocab import LogLevel
            flush = [w for t in tables for w in t.warnings]
            for w in flush[:12]:
                append_log(conn, job_id, f"warning: {w}",
                           level=LogLevel.WARNING, source_key=entry.source_key)
            if len(flush) > 12:
                append_log(conn, job_id,
                           f"...and {len(flush) - 12} more warning(s) from "
                           "the interrupted fetch",
                           level=LogLevel.WARNING, source_key=entry.source_key)
            for note in list(getattr(fetcher, "robots_warnings", []) or []):
                append_log(conn, job_id, note, source_key=entry.source_key)
        raise
    finally:
        fetcher.close()
    if journal:
        # The journal holds this run's pages PLUS any kept from before the
        # pause — reading it back is what makes the resumed ingest whole.
        payloads = localinbox.read_payloads(localinbox.JOURNAL_DIR, entry.source_key)
    else:
        payloads = [t.to_payload() for t in tables]
    with (lock() if lock is not None else nullcontext()):
        _refuse_if_superseded(conn)
        if archive_first:
            # A FULL REBUILD archives inside the same lock that writes the new
            # rows — atomically, and only once writing is actually possible.
            # Archiving earlier (as the job loop did) meant a lock conflict
            # left the catalogue archived and NOTHING re-crawled: the owner's
            # sika run lost 87 products to a five-word error message.
            from .archive import archive_source
            archived = archive_source(conn, entry.source_key)
            if job_id is not None:
                from .jobs import append_log
                append_log(conn, job_id,
                           f"archived {archived} products before rebuild",
                           source_key=entry.source_key)
        # Defects travel from the FETCH, deduplicated: a connector that pins the
        # same defect to every page is stating one fact about the run, not one
        # per page. Read from `tables` and not from the journal, because a defect
        # describes what THIS attempt produced.
        defects = list(dict.fromkeys(d for t in tables for d in t.defects))
        # What the fetch actually cost, recorded ON THE RUN. crawl_run has had a
        # requests_count column since the schema was written and nothing ever
        # wrote it, so every run in the warehouse reads 0 — which is why the
        # panel had no measured expectation to show a bar against. From here a
        # successful run leaves the next crawl of this source a real number, and
        # it sharpens by itself every time.
        result = ingest_payloads(conn, entry, payloads, job_id=job_id,
                                 fetch_defects=defects,
                                 requests_count=requests_count)
        _store_published_rates(conn, entry, tables, result)
    if journal:
        localinbox.clear(localinbox.JOURNAL_DIR, entry.source_key)
    # rows/tables come from the PAYLOADS: on a resume the fetched tables are
    # only the tail of the crawl, and the F6 volume canary must see the whole.
    return CaptureResult(ingest=result, requests_count=requests_count,
                         tables=len(payloads), rows=sum(len(p.rows) for p in payloads),
                         warnings=[w for t in tables for w in t.warnings],
                         notes=list(getattr(fetcher, "robots_warnings", []) or []))


def _store_published_rates(conn, entry, tables: list, result) -> None:
    """The rate the STORE printed about itself, into currency_rate as 'shop'.

    Read from `tables` and not from the journal for the same reason defects
    are: the payload contract is frozen across engines and carries no rate, so
    this is what THIS attempt saw. A resume reads it again off its first page.

    ISOLATED, NOT SILENT. A rate that will not store must not cost the
    catalogue that was already ingested — but a failure that leaves no trace is
    how the USD column goes on quoting a stale number with nothing anywhere
    saying why (the lesson _record_implied_rate spells out). So the failure
    becomes a NOTICE: the run is not partial, and the reason is on the record.
    """
    published: dict[str, float] = {}
    for table in tables:
        published.update(getattr(table, "published_rates", None) or {})
    if not published:
        return
    from . import rates as rates_mod
    try:
        rates_mod.store_shop_rates(conn, entry.source_key, published)
    except (ValueError, TypeError, sqlite3.DatabaseError) as exc:
        result.notices.append(
            f"the exchange rate {entry.source_key} publishes about itself was "
            f"not stored ({', '.join(sorted(published))}) — {exc}")
