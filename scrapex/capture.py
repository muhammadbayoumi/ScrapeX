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
    """
    from . import storage

    row = conn.execute("PRAGMA database_list").fetchone()
    path = row[2] if row is not None else ""
    if not path:
        return                              # in-memory database: nothing to seal
    when = storage.sealed_at(path)
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
    }


def _job_progress(conn: sqlite3.Connection, job_id: int,
                  source_key: str) -> Callable[[int, str], None]:
    """A per-request heartbeat for the job row, throttled to stay negligible.

    Every 10 requests the heartbeat and the live request counter move — the
    panel's Requests figure ticks and a watchdog can tell life from a hang.
    Every 50, one log line states plainly what is happening. The counter is
    provisional (this source's count so far); the authoritative total is merged
    per source by the job loop as before.
    """
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
        conn.execute(
            "UPDATE crawl_job SET last_heartbeat_at = strftime('%Y-%m-%dT%H:%M:%SZ','now'), "
            "counters_json = json_set(COALESCE(NULLIF(counters_json,''),'{}'), "
            "'$.requests', ?) WHERE job_id = ?",
            (count, job_id))
        if count % 50 == 0:
            # Local import: jobs.py imports this module at its top.
            from .jobs import append_log
            append_log(conn, job_id, f"fetching — {count} requests so far",
                       source_key=source_key)
        conn.commit()
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


def capture_source(conn: sqlite3.Connection, entry: SourceEntry,
                   job_id: int | None = None,
                   lock: Callable[[], AbstractContextManager] | None = None,
                   history: bool = False, resume: bool = False) -> CaptureResult:
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
        fetcher.on_request = _job_progress(conn, job_id, entry.source_key)
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
            # published nothing this week.
            notes = ([w for t in tables for w in t.warnings]
                     + list(getattr(fetcher, "robots_warnings", []) or []))
            if notes:
                from .jobs import append_log
                from .vocab import LogLevel
                for w in notes[:12]:
                    append_log(conn, job_id, f"warning: {w}",
                               level=LogLevel.WARNING, source_key=entry.source_key)
                if len(notes) > 12:
                    append_log(conn, job_id,
                               f"...and {len(notes) - 12} more warning(s) from "
                               "the interrupted fetch",
                               level=LogLevel.WARNING, source_key=entry.source_key)
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
        result = ingest_payloads(conn, entry, payloads, job_id=job_id)
    if journal:
        localinbox.clear(localinbox.JOURNAL_DIR, entry.source_key)
    # rows/tables come from the PAYLOADS: on a resume the fetched tables are
    # only the tail of the crawl, and the F6 volume canary must see the whole.
    return CaptureResult(ingest=result, requests_count=requests_count,
                         tables=len(payloads), rows=sum(len(p.rows) for p in payloads),
                         warnings=[w for t in tables for w in t.warnings]
                         + list(getattr(fetcher, "robots_warnings", []) or []))
