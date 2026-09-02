"""Job store + background worker (spec sections 4, 23, 24, 25).

The side panel NEVER owns or executes a crawl: it enqueues a job and polls. A
single worker thread owns execution, so writes stay serialized (A10 single-writer)
while API requests only do short reads and control writes.

Everything needed to recover after the panel closes lives in crawl_job — status,
stage, progress, counters, checkpoint, and the owner's pause/cancel intent. The
worker applies that intent only at a SAFE BOUNDARY (between sources), never
mid-write, so a pause can never tear a half-ingested source.

`run_job_once` is the testable seam: fully synchronous, no threads, with the
capture step injected. JobRunner is a thin thread loop on top of it.
"""
from __future__ import annotations

import importlib
import json
import re
import sqlite3
import sys
import threading
import traceback
import uuid
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

from . import db as dbmod
from .archive import backup_database
from .capture import CaptureResult, capture_source
from .connectors.base import CrawlInterrupted
from .ingest import canary_breach, previous_rows_seen
from .payload import utc_now_iso
from .vocab import (
    TERMINAL_JOB_STATUSES,
    WORKER_HELD_STATUSES,
    JobControl,
    JobStage,
    JobStatus,
    LogLevel,
    RunMode,
)

_COUNTER_FIELDS = ("observations", "duplicates", "products", "variants",
                   "attributes", "skipped_ignored", "rejected_out_of_scope")

#: `job_kind` -> `(module, attribute)` for the kinds that are NOT the price crawl.
#:
#: THE PRICE CRAWL IS THE ABSENT ENTRY, deliberately: `run_job_once` takes a manifest,
#: an injected capture, a backup, a connect factory and an admission, so it does not fit
#: `(conn, job_ref)` and pretending it did would mean five parameters travelling through
#: a table that has nowhere to put them. `runner_for` returning `None` MEANS the price
#: path, and `_start_job` reads it that way.
#:
#: RESOLVED ON USE. `enrichment.service` imports this module, so naming these at module
#: scope is a cycle -- which `_start_job` already worked around with a function-local
#: import. Paths also keep `import scrapex.jobs` from pulling the enrichment providers
#: and an HTTP fetcher into every process that only wants to read a job row.
SPECIALISED_RUNNERS: dict[str, tuple[str, str]] = {
    "organization_enrichment": (".enrichment.service", "run_enrichment_job_once"),
    "directory_crawl": (".directoryjob", "run_directory_crawl_job_once"),
}

#: DERIVED, NEVER LISTED TWICE. This used to be a literal set of the same strings a
#: thousand lines above the branch that dispatched them, so a kind added to one and
#: forgotten in the other was either refused at the door or handed to the price
#: collector in silence.
JOB_KINDS = frozenset({"crawl", *SPECIALISED_RUNNERS})


def runner_for(job_kind: str):
    """The function that runs one job of this kind, or `None` for the price crawl."""
    target = SPECIALISED_RUNNERS.get(job_kind)
    if target is None:
        return None
    module, attribute = target
    return getattr(importlib.import_module(module, __package__), attribute)


# ---- store -------------------------------------------------------------------

def create_job(conn: sqlite3.Connection, source_keys: Iterable[str],
               run_mode: RunMode | str = RunMode.UPDATE,
               status: JobStatus | str = JobStatus.QUEUED,
               checkpoint: dict | None = None,
               job_kind: str = "crawl",
               *,
               commit: bool = True) -> str:
    """Persist a new job and return its public job_ref.

    `checkpoint` seeds the job with a resume point it did not earn by being
    paused. That is the ONE way a journal outlives the job that filled it: a
    pause writes `partial_source` here, but cancelling the paused job — or a
    runtime that dies — leaves the kept pages on disk with no non-terminal job
    left to carry them. Without this, resume was reachable only for as long as
    the original job stayed alive, which is exactly how 871 elburoj pages ended
    up stranded.

    `commit=False` lets a caller attach job-specific rows and an immutable work
    snapshot in the same transaction. Ordinary crawl callers retain the
    historical immediate-commit behavior.
    """
    keys = [str(k) for k in source_keys]
    if not keys:
        raise ValueError("a job needs at least one source_key")
    if job_kind not in JOB_KINDS:
        raise ValueError(f"unknown job kind {job_kind!r}")
    job_ref = f"job_{uuid.uuid4().hex[:12]}"
    columns = {row[1] for row in conn.execute("PRAGMA table_info(crawl_job)")}
    if "job_kind" in columns:
        conn.execute(
            "INSERT INTO crawl_job (job_ref, run_mode, status, source_keys, "
            "progress_total, checkpoint_json, job_kind) VALUES (?,?,?,?,?,?,?)",
            (job_ref, str(run_mode), str(status), json.dumps(keys), len(keys),
             json.dumps(checkpoint) if checkpoint else None, job_kind),
        )
    else:
        if job_kind != "crawl":
            raise ValueError(
                "organization enrichment needs the current Engine database schema"
            )
        conn.execute(
            "INSERT INTO crawl_job (job_ref, run_mode, status, source_keys, "
            "progress_total, checkpoint_json) VALUES (?,?,?,?,?,?)",
            (job_ref, str(run_mode), str(status), json.dumps(keys), len(keys),
             json.dumps(checkpoint) if checkpoint else None),
        )
    if commit:
        conn.commit()
    return job_ref


def get_job(conn: sqlite3.Connection, job_ref: str) -> dict | None:
    row = conn.execute("SELECT * FROM crawl_job WHERE job_ref = ?", (job_ref,)).fetchone()
    return _as_job(row) if row is not None else None


def list_jobs(conn: sqlite3.Connection, limit: int = 20, active_only: bool = False) -> list[dict]:
    sql = "SELECT * FROM crawl_job"
    params: tuple = ()
    if active_only:
        marks = ",".join("?" for _ in TERMINAL_JOB_STATUSES)
        sql += f" WHERE status NOT IN ({marks})"
        params = tuple(s.value for s in TERMINAL_JOB_STATUSES)
    sql += " ORDER BY job_id DESC LIMIT ?"
    return [_as_job(r) for r in conn.execute(sql, (*params, limit))]


def set_control(conn: sqlite3.Connection, job_ref: str, control: JobControl | str) -> bool:
    """Record the owner's intent. Returns False for an unknown or finished job.

    A job the worker is ACTUALLY HOLDING gets a transitional status and settles at
    its next safe boundary. A job the worker is NOT holding is settled RIGHT HERE.

    That distinction is load-bearing: the worker only ever picks up `queued`, so
    parking a queued job in `cancelling` would strand it in a non-terminal status
    forever — and because `_source_is_busy` treats any non-terminal job as busy,
    that source's schedules would silently stop firing for good.

    The write is a compare-and-swap on the status we read, so a job that reaches a
    terminal state concurrently can never be resurrected by a late control click.
    """
    job = get_job(conn, job_ref)
    if job is None or job["status"] in {s.value for s in TERMINAL_JOB_STATUSES}:
        return False

    control = JobControl(str(control))
    current = job["status"]
    held = current in WORKER_HELD_STATUSES

    if control is JobControl.RESUME:
        target, next_control, finishing = JobStatus.QUEUED, JobControl.NONE, False
    elif control is JobControl.CANCEL:
        target, next_control, finishing = (
            (JobStatus.CANCELLING, JobControl.CANCEL, False) if held
            else (JobStatus.CANCELLED, JobControl.NONE, True))
    elif control is JobControl.PAUSE:
        target, next_control, finishing = (
            (JobStatus.PAUSING, JobControl.PAUSE, False) if held
            else (JobStatus.PAUSED, JobControl.NONE, False))
    else:  # NONE — just clear a pending intent
        target, next_control, finishing = JobStatus(current), JobControl.NONE, False

    sql = "UPDATE crawl_job SET status = ?, control = ?"
    params: list = [target.value, next_control.value]
    if finishing:
        sql += ", finished_at = ?"
        params.append(utc_now_iso())
    sql += " WHERE job_ref = ? AND status = ?"     # compare-and-swap
    params += [job_ref, current]

    cur = conn.execute(sql, params)
    conn.commit()
    return cur.rowcount == 1


def append_log(conn: sqlite3.Connection, job_id: int, message: str,
               level: LogLevel | str = LogLevel.INFO, source_key: str | None = None) -> None:
    conn.execute(
        "INSERT INTO job_log_entry (job_id, level, source_key, message) VALUES (?,?,?,?)",
        (job_id, str(level), source_key, message),
    )


def job_logs(conn: sqlite3.Connection, job_ref: str,
             limit: int | None = None) -> list[dict]:
    """The job's log, oldest first. `limit` keeps only the newest that many.

    None means EVERY entry, and that is now the default. A tail was the wrong
    shape for the one job the log exists for: reading why a run went wrong.
    Capped at 200 (here and again in the route), the line that explained a
    failure was thrown away by the display for any run long enough to need it —
    and the panel's own heading called the 200 it was given "the last 200",
    which reads as a complete list.
    """
    sql = ("SELECT l.* FROM job_log_entry l JOIN crawl_job j ON j.job_id = l.job_id "
           "WHERE j.job_ref = ? ORDER BY l.job_log_id DESC")
    params: tuple = (job_ref,)
    if limit is not None:
        sql += " LIMIT ?"
        params += (limit,)
    return [dict(r) for r in reversed(conn.execute(sql, params).fetchall())]


def job_log_count(conn: sqlite3.Connection, job_ref: str) -> int:
    """How many entries this job's log actually holds.

    So a display can state what it is showing OUT OF what exists. A viewer that
    cannot say that is a viewer that cannot be trusted not to be hiding
    something — which is precisely what it was doing.
    """
    row = conn.execute(
        "SELECT COUNT(*) FROM job_log_entry l JOIN crawl_job j ON j.job_id = l.job_id "
        "WHERE j.job_ref = ?", (job_ref,)).fetchone()
    return int(row[0]) if row is not None else 0


# ---- what each source is fetching, and what it is a fraction OF --------------
#
# THE BAR WAS ANSWERING A QUESTION NOBODY ASKED (2026-07-30).
#
# progress_total is the number of SOURCES, so a one-source job reads 0/1 — 0% —
# for its entire duration. Measured: an ELBUROJ run sat at "0% (0/1)" for
# 18m23s while its Requests counter climbed past 1,030 and everything was fine.
# Nothing was broken; the fraction was of the wrong thing.
#
# So each source gets a slot under counters_json.$.sources, carrying the count
# and — the whole point — WHAT THE COUNT IS A FRACTION OF, plus where that
# denominator came from. Three bases, in descending order of what they claim:
#
#   declared  a connector enumerated its frontier before fetching it, so this
#             is a count and not a guess (salla's sitemap, magento's
#             total_pages). Replaces an estimate the moment it arrives.
#   estimate  this source's last SUCCESSFUL run spent this many requests. Dated,
#             and shown as an estimate, because it is one. It improves by itself
#             every crawl, which is exactly what was asked for.
#   measured  the source has finished. Its expectation is now its actual count,
#             because history is not a prediction.
#
# A source with none of the three has `expected: null`, and every screen must
# say the total is not known rather than draw a bar at 0% — that bar is the
# original complaint, and an honest indeterminate one is better than a precise
# lie. A first-ever crawl of a site with no sitemap is genuinely this case.
#
# It lives in counters_json rather than a new column or table because it is a
# counter on the job, migration 0056 is the last one applied, and none of this
# is worth a schema change. _merge_counters never touches this key.
SOURCES_KEY = "sources"

# What may appear in a json path fragment. Deliberately narrower than anything
# SQLite would accept: see _slot_path.
_SOURCE_KEY_SAFE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def _slot_path(source_key: str) -> str:
    """The json path for one source's slot.

    Interpolated, not bound: SQLite takes the json PATH as a literal and a bound
    parameter cannot be a path fragment. Safe because source_key is validated
    against ^[A-Z][A-Z0-9_]{2,63}$ before anything reaches the warehouse
    (config.py:21) — no quote, dot or bracket can occur in one. Asserted rather
    than assumed, because the day that regex loosens this becomes injection.
    """
    if not _SOURCE_KEY_SAFE.match(source_key or ""):
        raise ValueError(f"unsafe source_key for a json path: {source_key!r}")
    return f"$.{SOURCES_KEY}.{source_key}"


def record_source_fetch(conn: sqlite3.Connection, job_id: int, source_key: str,
                        **fields) -> None:
    """Merge `fields` into one source's slot, and beat the job's heartbeat.

    The WRITE is a json_set that touches ONLY this source's subtree
    ($.sources.<key>), so two per-host lanes updating DIFFERENT sources from
    their own connections cannot clobber each other however they interleave —
    SQLite applies each json_set to the column's current value. The Python read
    just above is only to carry this source's own prior fields forward (keep
    `expected` when updating `requests`), and it is safe because a source is
    written by exactly one lane: it lives in one host-lane, whose sources run
    strictly in order, and the fetch tick and the boundary update for it are
    sequential on that lane.

    Called from the fetch tick (live, every tenth request) and from the job loop
    at each source boundary. Both go through here so the slot has exactly one
    writer's worth of rules.
    """
    if not fields:
        return
    row = conn.execute("SELECT counters_json FROM crawl_job WHERE job_id = ?",
                       (job_id,)).fetchone()
    if row is None:
        return
    current = json.loads(row[0] or "{}") if row[0] else {}
    slot = dict((current.get(SOURCES_KEY) or {}).get(source_key) or {})
    slot.update(dict(fields.items()))
    conn.execute(
        "UPDATE crawl_job SET last_heartbeat_at = strftime('%Y-%m-%dT%H:%M:%SZ','now'), "
        f"counters_json = json_set(COALESCE(NULLIF(counters_json,''),'{{}}'), "
        f"'{_slot_path(source_key)}', json(?)) WHERE job_id = ?",
        (json.dumps(slot, ensure_ascii=False), job_id))


def _merge_counters_column(conn: sqlite3.Connection, job_id: int,
                           counters: dict) -> None:
    """Write the aggregate counters WITHOUT erasing the per-source slots.

    The slots live in the same JSON column, written by a different statement
    (and, with per-host lanes, by a different thread on a different connection).
    A plain `counters_json = ?` here would take the whole column with an
    in-memory dict that has never held them — so every source's denominator
    would vanish at the first source boundary, and the bar would go back to
    being a fraction of nothing exactly when it started to matter.

    json_patch is RFC-7386 merge semantics: the named keys are replaced, keys it
    says nothing about (`sources`) are left alone.
    """
    conn.execute(
        "UPDATE crawl_job SET counters_json = "
        "json_patch(COALESCE(NULLIF(counters_json,''),'{}'), ?) WHERE job_id = ?",
        (json.dumps(counters, ensure_ascii=False), job_id))


def _seed_source_expectations(conn: sqlite3.Connection, job_id: int,
                             source_keys: Iterable[str]) -> None:
    """Give every source a denominator BEFORE it starts, where one exists.

    Seeded up front rather than when each source begins, because a job's bar is
    a fraction of the whole job: with three sources, a denominator that only
    covered the one currently fetching would read 100% while two sites had not
    been touched.
    """
    from .ingest import last_successful_run

    for source_key in source_keys:
        previous = last_successful_run(conn, source_key)
        spent = (previous or {}).get("requests_count") or 0
        record_source_fetch(
            conn, job_id, source_key, state="waiting", requests=0,
            # A previous SUCCESS that spent 0 requests means that run predates
            # requests_count ever being recorded (ingest.py wrote the column for
            # the first time on 2026-07-30) — an absence, so it must not become
            # a denominator of zero.
            expected=spent or None,
            basis="estimate" if spent else None,
            as_of=((previous or {}).get("started_at") or "")[:10] if spent else None)


def _as_job(row: sqlite3.Row) -> dict:
    job = dict(row)
    job.setdefault("job_kind", "crawl")
    job["source_keys"] = json.loads(job["source_keys"] or "[]")
    job["counters"] = json.loads(job["counters_json"] or "{}")
    job["checkpoint"] = json.loads(job["checkpoint_json"] or "{}")
    return job


def _update(conn: sqlite3.Connection, job_id: int, **fields) -> None:
    if not fields:
        return
    sets = ", ".join(f"{name} = ?" for name in fields)
    conn.execute(f"UPDATE crawl_job SET {sets} WHERE job_id = ?",
                 (*fields.values(), job_id))


def _control_of(conn: sqlite3.Connection, job_id: int) -> str:
    row = conn.execute("SELECT control FROM crawl_job WHERE job_id = ?", (job_id,)).fetchone()
    return row[0] if row is not None else JobControl.NONE.value


def _merge_counters(counters: dict, result: CaptureResult) -> dict:
    for name in _COUNTER_FIELDS:
        counters[name] = counters.get(name, 0) + getattr(result.ingest, name)
    counters["errors"] = (counters.get("errors", 0)
                          + len(result.ingest.errors) + len(result.ingest.contained))
    counters["requests"] = counters.get("requests", 0) + result.requests_count
    return counters



# A ceiling the setting cannot exceed. Concurrency here costs one HTTP session
# and one database connection per lane, and every lane still waits out its own
# site's pace — so past a handful the wall-clock stops improving while the
# failure modes (open handles, contended write lock) keep growing. Eight is
# generous for a manifest of ten sources on ten hosts.
MAX_PARALLEL_SOURCES = 8

# The same ceiling for whole JOBS. The owner's scheduled crawls are one job per
# source (scheduler.fire_due), so ten sites firing daily is ten single-source
# jobs — and within-job lane concurrency does nothing for a job that has one
# lane. Running the JOBS concurrently is what actually crawls those ten sites at
# once; this bounds how many at a time, and the per-host reservation below keeps
# it polite.
MAX_PARALLEL_JOBS = 8


def job_capacity(conn: sqlite3.Connection) -> int:
    """How many jobs the engine will run at once — the owner's site budget, capped.

    ONE definition, read by the worker that enforces it AND by the API that
    explains the queue, so the panel can never promise a concurrency the worker
    will not deliver. At 1 (the shipped default) the engine runs exactly one job
    at a time and the panel says so.
    """
    try:
        from . import settings
        width = int(settings.get(conn, "crawl_parallel_sources") or 1)
    except (ValueError, TypeError, sqlite3.DatabaseError):
        return 1
    return max(1, min(width, MAX_PARALLEL_JOBS))


# ---- admission: the two rules that make concurrent JOBS safe ----------------

def _host_of(manifest, key: str, fallback: str) -> str:
    """The politeness identity of a source: its host, www-stripped, lowercased.

    ONE definition, used to bucket lanes AND to reserve a host across jobs — so
    a source cannot be filed under one host name for grouping and a different
    one for reservation, which is the crack two jobs would slip through to crawl
    a site together. A key the manifest cannot resolve gets `fallback`, and the
    caller passes a value unique to that source so two unknowns never collide.
    """
    try:
        host = urlsplit(manifest.get(key).base_url).netloc.lower()
    except Exception:
        return fallback
    return host.removeprefix("www.") or fallback


class _CrawlAdmission:
    """The rules that let several JOBS crawl at once without a site feeling it.

    Held by the worker and shared — the SAME object — by every concurrent job.
    That sharing is the whole point: a rule that lived inside one job could only
    ever govern that job's own lanes, and the risk here is precisely the one
    that spans jobs. A lane handed no admission (the sequential default, every
    test, the CLI) admits itself and the code path is exactly as it was.

    per-host reservation
        Two lanes on one host serialise, whichever JOB each belongs to. This is
        the rule `_host_lanes` already enforces inside a job — that two sources
        of one site never run together — lifted to span jobs, so a scheduled
        crawl and a hand-started one of the same site cannot double the load it
        asked to be spared. This is the safety property the task calls the whole
        risk, and the test `two jobs never crawl one host together` pins it.

    budget
        At most N sites crawl at once across the ENTIRE engine, N being the
        owner's existing "Sites crawled at the same time" setting. Without it, J
        concurrent jobs of W lanes each would open J×W sessions at once and the
        setting would bound nothing.
    """

    def __init__(self, budget: int | None) -> None:
        self._budget = threading.Semaphore(budget) if budget and budget > 0 else None
        self._hosts: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    def _host_lock(self, host: str) -> threading.Lock:
        with self._guard:
            lock = self._hosts.get(host)
            if lock is None:
                lock = self._hosts[host] = threading.Lock()
            return lock

    @contextmanager
    def lane(self, host: str):
        """Admit one lane to crawl `host`: reserve the host, then take a slot.

        HOST FIRST, THEN SLOT — one global acquisition order, so the wait graph
        has no cycle and cannot deadlock. Holding an (almost always uncontended,
        since the owner's hosts are distinct) host reservation while waiting for
        a slot is harmless; the reverse would let a lane that cannot run yet sit
        on a scarce slot and starve one that can.

        The reservation and the slot both span the lane's whole run — a host
        with several sources is one site being crawled, and holds one of each
        for the duration of its sequential sources.
        """
        host_lock = self._host_lock(host) if host else nullcontext()
        with host_lock:
            if self._budget is None:
                yield
                return
            self._budget.acquire()
            try:
                yield
            finally:
                self._budget.release()


# ---- lanes: concurrency that a site can never feel --------------------------

@dataclass
class _SourceRun:
    """Everything one source needs, and everywhere its result accumulates.

    A plain object rather than a pile of nonlocals because the accumulators are
    now written from several threads: one place to see what is shared, and one
    lock guarding all of it.
    """

    # The ORCHESTRATOR's connection, and usable ONLY from its thread. sqlite3
    # refuses a connection across threads, so a lane must use the one its own
    # _run_lane opened — never this. Reaching for it inside a lane is what
    # killed a 3,490-request crawl the moment a pause was asked for: the brake
    # path wrote the job row through this handle and the worker died with
    # "SQLite objects created in a thread can only be used in that same thread".
    # Kept because the sequential path (width 1) legitimately passes it down.
    conn: sqlite3.Connection
    job: dict
    job_id: int
    manifest: object
    capture: Callable
    rebuilding: bool
    checkpoint: dict
    done: list
    errors: list
    counters: dict
    succeeded: int
    # Set by whichever lane first honours a pause or a cancel. Its presence is
    # what stops the others starting anything new, and what tells the caller
    # the job already reached a terminal state and must not be finished twice.
    stopped: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)


def _host_lanes(manifest, source_keys: list[str]) -> list[list[str]]:
    """Sources bucketed by HOST, first-seen order preserved.

    The bucket is the unit of concurrency, so two sources on one site can never
    run at the same time however wide the fan-out is set. A key the manifest
    does not know gets a lane of its own — the failure belongs in that source's
    own error, not in a crash here that would take the whole job with it.
    """
    lanes: dict[str, list[str]] = {}
    for index, key in enumerate(source_keys):
        lanes.setdefault(_host_of(manifest, key, f"?{index}"), []).append(key)
    return list(lanes.values())


def _parallel_width(conn: sqlite3.Connection, connect, lanes: int) -> int:
    """How many sites to crawl at once — 1 unless BOTH halves say otherwise.

    `connect` is the half that cannot be configured away: a worker thread needs
    a database connection of its OWN (sqlite3 refuses one across threads), and
    without a factory to make one there is no safe concurrency to have. Absent
    it — every existing caller, and every test holding an in-memory database
    that a second thread could not reopen — this returns 1 and the job runs
    exactly as it did before.
    """
    if connect is None or lanes < 2:
        return 1
    try:
        from . import settings
        width = int(settings.get(conn, "crawl_parallel_sources") or 1)
    except (ValueError, TypeError, sqlite3.DatabaseError):
        return 1
    return max(1, min(width, lanes, MAX_PARALLEL_SOURCES))


def _drive_lanes(run: _SourceRun, lanes: list[list[str]], width: int, connect,
                 admission: _CrawlAdmission | None = None) -> None:
    """Run each lane to completion; lanes concurrently when asked.

    `admission` (when present) is the cross-job gate every lane passes through —
    it is threaded down here rather than consulted per source, because a lane is
    already one host's worth of work and the reservation is a fact about the
    host, not the source. width<=1 is NOT a shortcut past it: a single-lane job
    still competes with OTHER jobs for the same host and the same budget, so it
    is admitted the same way, just without an executor of its own.
    """
    if width <= 1:
        for lane in lanes:
            _run_lane(run, lane, None, admission)
        return
    with ThreadPoolExecutor(max_workers=width,
                            thread_name_prefix="scrapex-lane") as pool:
        futures = [pool.submit(_run_lane, run, lane, connect, admission)
                   for lane in lanes]
        for future in futures:
            future.result()      # a lane that raised must not vanish silently


def _run_lane(run: _SourceRun, lane: list[str], connect,
              admission: _CrawlAdmission | None = None) -> None:
    """One host's sources, strictly in order, on a connection of this lane's own.

    The admission is acquired around the WHOLE lane, held across its sequential
    sources: they are all the same site, and reserving it once is what stops
    another job's lane touching that site until this one is done with it.
    """
    host = _host_of(run.manifest, lane[0], lane[0]) if lane else ""
    admit = admission.lane(host) if admission is not None else nullcontext()
    with admit:
        conn = connect() if connect is not None else run.conn
        try:
            for source_key in lane:
                with run.lock:
                    if run.stopped is not None:
                        return          # another lane already hit the brakes
                if not _run_source(run, conn, source_key):
                    return
        finally:
            if connect is not None:
                conn.close()


def _run_source(run: _SourceRun, conn: sqlite3.Connection, source_key: str) -> bool:
    """Capture one source. False means the JOB stopped, not that this failed.

    The body is the one the sequential loop always had, moved rather than
    rewritten: one implementation serves both widths, so a fix can never land
    on the fast path and miss the slow one.
    """
    control = _control_of(conn, run.job_id)   # safe boundary: between sources
    if control in (JobControl.CANCEL.value, JobControl.PAUSE.value):
        with run.lock:
            if run.stopped is not None:
                return False
            run.stopped = control
        if control == JobControl.CANCEL.value:
            append_log(conn, run.job_id, "cancelled by owner")
            _finish(conn, run.job_id, JobStatus.CANCELLED, None)
        else:
            append_log(conn, run.job_id, "paused by owner")
            _update(conn, run.job_id, status=JobStatus.PAUSED.value,
                    control=JobControl.NONE.value, stage=None,
                    last_heartbeat_at=utc_now_iso())
        conn.commit()
        return False

    _update(conn, run.job_id, status=JobStatus.RUNNING.value, stage=JobStage.FETCHING.value,
            current_source_key=source_key, last_heartbeat_at=utc_now_iso())
    record_source_fetch(conn, run.job_id, source_key, state="fetching")
    conn.commit()
    spent: int | None = None      # requests this source cost, once it is known
    try:
        entry = run.manifest.get(source_key)
        previous = previous_rows_seen(conn, source_key)
        # Keywords travel only when the situation asks for them, so every
        # existing capture fake with the plain (conn, entry, job_id)
        # signature keeps working untouched. `resume` fires for exactly
        # the source a pause interrupted MID-fetch: its journaled pages
        # are still on disk and the connector may skip them.
        extras: dict = {}
        if run.rebuilding:
            # The archive travels WITH the write, into the same lock —
            # doing it here meant a failed capture (a held lock, a dead
            # site) left the catalogue archived and nothing re-crawled.
            extras["archive_first"] = True
        if run.job["run_mode"] == RunMode.HISTORY_BACKFILL.value:
            extras["history"] = True
        if run.checkpoint.get("partial_source") == source_key:
            extras["resume"] = True
        result = (run.capture(conn, entry, run.job_id, **extras) if extras
                  else run.capture(conn, entry, run.job_id))
        spent = int(result.requests_count)
        _merge_counters(run.counters, result)
        append_log(conn, run.job_id,
                   f"{result.ingest.observations} observations, "
                   f"{result.ingest.products} new products, {result.requests_count} requests",
                   source_key=source_key)
        # Ingest errors used to be folded into a bare counter here, so the
        # job finished 'completed' with error_summary NULL and the MESSAGE —
        # the only thing that could explain a degraded run — was discarded.
        # Each one is now a job-level error (it degrades the job's outcome)
        # and a log line the owner can actually read.
        for issue in result.ingest.errors:
            run.errors.append(f"{source_key}: {issue}")
            append_log(conn, run.job_id, issue, level=LogLevel.WARNING,
                       source_key=source_key)
        # Contained side-effect failures did not degrade the run and must
        # not degrade the job — but silent is not an option either.
        for note in result.ingest.contained:
            append_log(conn, run.job_id, note, level=LogLevel.WARNING,
                       source_key=source_key)
        # Notices are neither: a normal outcome the owner can see, logged at
        # INFO so it never reads as trouble and never touches the counters.
        for note in result.ingest.notices:
            append_log(conn, run.job_id, note, level=LogLevel.INFO,
                       source_key=source_key)
        # What the connector could NOT collect belongs in this log too. The
        # CLI printed these warnings; here they were dropped, so the run
        # that lost NATURAL_GAS entirely — 47 country pages publishing no
        # local price, every one skipped — logged three clean lines and
        # read as a full success. Capped so a systemic failure cannot bury
        # the log; the cap itself is stated.
        shown = getattr(result, "warnings", None) or []
        for warning in shown[:30]:
            append_log(conn, run.job_id, warning, level=LogLevel.WARNING,
                       source_key=source_key)
        # AND ON THE RUN ITSELF. The log has always had them — SPARK_ESHOP's
        # "en locale unavailable ... 404" is sitting in job_log_entry right now
        # and it is the one sentence that explains 1,789 mislabelled products.
        # But a run row could not answer "what went wrong in THIS run" without
        # someone knowing to go and join a log by job id, and nobody did for
        # two days. The count is what makes a clean run visibly clean; the
        # first line is what makes a dirty one worth opening.
        if shown:
            conn.execute(
                "UPDATE crawl_run SET warning_count = ?, first_warning = ? "
                "WHERE run_id = ?",
                (len(shown), str(shown[0])[:500], result.ingest.run_id))
        if len(shown) > 30:
            append_log(conn, run.job_id,
                       f"...and {len(shown) - 30} more warnings like these "
                       "(the CLI crawl prints them all)",
                       level=LogLevel.WARNING, source_key=source_key)
        # Politeness disclosures ride at INFO — the owner's robots ruling
        # (docs/robots-policy.md): how we behaved toward the site is worth
        # a line, never a warning that suggests the run needs review.
        for note in (getattr(result, "notes", None) or []):
            append_log(conn, run.job_id, note, source_key=source_key)
        # F6: a rotted connector fails QUIETLY — treat a volume breach as a
        # real failure, never a clean success.
        breach = canary_breach(entry, result.rows, previous)
        if breach is None:
            run.succeeded += 1
        else:
            run.errors.append(breach)
            append_log(conn, run.job_id, breach, level=LogLevel.WARNING, source_key=source_key)
    except CrawlInterrupted as stop:
        with run.lock:
            if run.stopped is not None:
                return False
            run.stopped = stop.control
        # The owner pressed the brakes MID-FETCH. Nothing was ingested for
        # this source (fetch aborts before ingest), but every fetched page
        # is already in the job journal — a pause keeps it and marks this
        # source in the checkpoint so the resume skips those pages; a
        # cancel abandons the source and discards the journal, which would
        # otherwise sit as stale state for a future job to trip over.
        from . import localinbox
        kept = len(localinbox.list_tokens(localinbox.JOURNAL_DIR, source_key))
        if stop.control == JobControl.CANCEL.value:
            localinbox.clear(localinbox.JOURNAL_DIR, source_key)
            append_log(conn, run.job_id,
                       "cancel honoured mid-fetch — nothing from this source "
                       "was ingested and the partial fetch was discarded",
                       source_key=source_key)
            _finish(conn, run.job_id, JobStatus.CANCELLED, None)
        else:
            if kept:
                append_log(conn, run.job_id,
                           f"pause honoured mid-fetch — {kept} fetched "
                           "page(s) kept; resume continues with the "
                           "remaining pages",
                           source_key=source_key)
            else:
                append_log(conn, run.job_id,
                           "pause honoured mid-fetch — nothing from this "
                           "source was ingested; it restarts from the top "
                           "if resumed",
                           source_key=source_key)
            _update(conn, run.job_id, status=JobStatus.PAUSED.value,
                    control=JobControl.NONE.value, stage=None,
                    checkpoint_json=json.dumps(
                        {"completed_source_keys": run.done,
                         "errors": run.errors,
                         "succeeded": run.succeeded,
                         # WHICH source the brakes caught, so the resume hands
                         # its journaled pages back to the connector instead of
                         # re-fetching them. With lanes in flight this is the
                         # one that stopped FIRST; the others had not started.
                         "partial_source": source_key}),
                    last_heartbeat_at=utc_now_iso())
        conn.commit()
        return False
    except Exception as exc:
        run.errors.append(f"{source_key}: {exc}")
        append_log(conn, run.job_id, f"failed: {exc}", level=LogLevel.ERROR, source_key=source_key)

    run.done.append(source_key)
    # This source is history now, so its expectation becomes its actual count:
    # a finished source contributes a MEASUREMENT to the job's denominator, and
    # leaving a guess in there would keep the job's total wrong for the rest of
    # the run. `requests` is left as the final figure for display; the job-wide
    # numerator stops counting this slot and reads the merged total instead
    # (see _job_view), so nothing is double-counted.
    record_source_fetch(conn, run.job_id, source_key, state="done",
                        **({"requests": int(spent), "expected": int(spent),
                            "basis": "measured", "as_of": None}
                           if spent is not None else {}))
    _update(conn, run.job_id, progress_done=len(run.done),
            checkpoint_json=json.dumps({"completed_source_keys": run.done,
                                        "errors": run.errors, "succeeded": run.succeeded}),
            last_heartbeat_at=utc_now_iso())
    _merge_counters_column(conn, run.job_id, run.counters)
    conn.commit()
    return True


# ---- execution (the testable seam) -------------------------------------------

def run_job_once(conn: sqlite3.Connection, job_ref: str, manifest,
                 capture: Callable[[sqlite3.Connection, object], CaptureResult] = capture_source,
                 backup: Callable[[], object] | None = None,
                 connect: Callable[[], sqlite3.Connection] | None = None,
                 admission: _CrawlAdmission | None = None) -> dict:
    """Execute one job to completion, or until a pause/cancel boundary.

    `connect` opens a database connection of the caller's choosing. It is the
    ONLY thing that unlocks crawling several sites at once, because a worker
    thread cannot borrow this function's connection — sqlite3 refuses one
    across threads, and an in-memory database could not be reopened anyway.
    Omit it (every test does) and the job runs one source at a time exactly as
    it always has, whatever crawl_parallel_sources says.

    `admission` is the CROSS-JOB gate: when the worker runs several jobs at
    once, it hands every one the SAME admission, and that shared object is what
    keeps two jobs off one host and bounds the total sites in flight. Omit it
    and the job answers to no one but itself — which is every caller that runs a
    job alone.

    Still the testable seam, and still synchronous from the caller's side: it
    returns when the job has reached a boundary, threads or no threads.
    Per-source failures are isolated and recorded (Q3): one dead site downgrades
    the job to partially_completed, it never kills the other sources.
    """
    job = get_job(conn, job_ref)
    if job is None:
        raise KeyError(f"unknown job_ref {job_ref!r}")
    if job.get("job_kind", "crawl") != "crawl":
        raise ValueError(f"job {job_ref!r} is not a crawl job")
    if job["status"] in {s.value for s in TERMINAL_JOB_STATUSES}:
        return job

    job_id = job["job_id"]
    checkpoint = job["checkpoint"]
    done: list[str] = list(checkpoint.get("completed_source_keys", []))
    counters: dict = job["counters"]
    # The per-source slots are NOT aggregate counters and must not ride in this
    # dict: they are written per source, from per-lane connections, straight into
    # the column. Carried here they would be re-written stale at every boundary
    # by whichever lane finished last.
    counters.pop(SOURCES_KEY, None)
    # Failures must survive a pause the same way counters do — rehydrating them
    # from the checkpoint is what stops a resumed job that already lost a source
    # from reporting a clean COMPLETED.
    errors: list[str] = list(checkpoint.get("errors", []))
    succeeded = int(checkpoint.get("succeeded", 0))

    # NB: `control` is deliberately NOT cleared here — a cancel/pause requested
    # while the job was still queued must survive into the first boundary check.
    _update(conn, job_id, status=JobStatus.PREPARING.value, stage=JobStage.PREPARING.value,
            last_heartbeat_at=utc_now_iso(),
            **({} if job["started_at"] else {"started_at": utc_now_iso()}))
    append_log(conn, job_id, f"job started ({job['run_mode']}, {len(job['source_keys'])} sources)")

    # FULL REBUILD: the backup is the rollback path, so a failure to take one
    # must stop the rebuild — proceeding would archive the catalogue with no way
    # back. Archiving itself happens PER SOURCE, after that source's boundary
    # check, so a cancel leaves the catalogue untouched.
    rebuilding = job["run_mode"] == RunMode.FULL_REBUILD.value
    if rebuilding and not done and backup is not None:
        try:
            append_log(conn, job_id, f"backup created: {backup()}")
        except Exception as exc:
            append_log(conn, job_id, f"backup failed: {exc}", level=LogLevel.ERROR)
            _finish(conn, job_id, JobStatus.FAILED, f"backup failed, rebuild aborted: {exc}")
            return get_job(conn, job_ref)
    conn.commit()

    # ONE SOURCE AT A TIME WAS COSTING THE OTHER NINE (2026-07-29).
    #
    # elburoj publishes 3,874 products behind a 10-second Crawl-delay: an
    # eleven-hour crawl, scheduled DAILY, and listed first. Nine of its jobs
    # were measured and every one was cancelled — job_694e92dc1e8b sat on it
    # with done=0/10, so ten sources starved behind one. The schedule could
    # not converge, which is why the owner's data stopped moving.
    #
    # Sources reach DIFFERENT SITES, so waiting on one teaches us nothing
    # about the others. Fetching holds no database lock (capture takes the
    # write lock around the ingest alone), so the expensive part — hours of
    # network — is exactly the part that parallelises, while the writes still
    # serialise on the lock that already exists.
    #
    # TWO SOURCES ON ONE SITE NEVER RUN TOGETHER. Today all ten hosts are
    # distinct, but the rule is in the code and not in that fact: masdaronline
    # already serves advancedcastle content on its homepage, and the day two
    # entries share a host, concurrency would double the load we put on it and
    # halve the delay it asked for. Sources are bucketed into per-host LANES;
    # lanes run concurrently, and within a lane strictly in order.
    pending = [k for k in job["source_keys"] if k not in done]
    # Every pending source gets whatever denominator exists BEFORE it starts, so
    # the bar has something true to be a fraction of from the first second
    # rather than after the first source finishes. Sources that have never
    # succeeded get `expected: null`, which the panel reads as "the total is not
    # known yet" — not as zero.
    _seed_source_expectations(conn, job_id, pending)
    conn.commit()
    lanes = _host_lanes(manifest, pending)
    width = _parallel_width(conn, connect, len(lanes))
    run = _SourceRun(conn=conn, job=job, job_id=job_id, manifest=manifest,
                     capture=capture, rebuilding=rebuilding, checkpoint=checkpoint,
                     done=done, errors=errors, counters=counters,
                     succeeded=succeeded)
    if width > 1:
        append_log(conn, job_id,
                   f"crawling {len(lanes)} site(s), up to {width} at a time")
        conn.commit()
    _drive_lanes(run, lanes, width, connect, admission)
    done, errors, counters = run.done, run.errors, run.counters
    succeeded = run.succeeded
    if run.stopped is not None:
        return get_job(conn, job_ref)

    if not errors:
        status = JobStatus.COMPLETED
    elif succeeded == len(job["source_keys"]):
        # Every source ran and passed its canary, yet a run degraded (partial
        # ingest). That is not 'completed' — the owner has something to read —
        # and not 'partially_completed' either, which means a whole source died.
        status = JobStatus.COMPLETED_WITH_ERRORS
    elif succeeded:
        status = JobStatus.PARTIALLY_COMPLETED
    else:
        status = JobStatus.FAILED
    _finish(conn, job_id, status, "; ".join(errors) or None)
    return get_job(conn, job_ref)


HEARTBEAT_KEY = "runtime_heartbeat"
#: When this runtime last finished sweeping jobs left behind by a dead one. It
#: is the answer to "has the engine tidied up yet?", which /api/health cannot
#: give: health is the HTTP thread's answer and the sweep is the worker's.
RECLAIM_KEY = "orphans_reclaimed_at"
HEARTBEAT_MAX_AGE_S = 30.0

# A JOB may go quiet for far longer than a loop pass and still be healthy:
# a polite crawler waits out a Crawl-delay between requests, and job 40
# logged progress every ~8 minutes against a rate-limited shop. Judging a
# job by the loop's 30s window is what made a working crawl look dead.
JOB_HEARTBEAT_MAX_AGE_S = 15 * 60.0

# Where the worker writes WHY it stopped. It used to write that to stderr
# only, and the engine runs under pythonw so there is no console and no
# redirect: the diagnosis was produced and discarded in the same breath.
# The owner then saw pages answering on the port — which proves the web
# server, never the worker — and waited for crawls that could not start.
# A fault that hides itself costs more than the fault.
WORKER_ERROR_KEY = "runtime_worker_error"

# The last exchange-rate refresh: when, how many landed, and any
# per-currency warning. A rate that silently stopped refreshing would
# leave the USD column quietly converting at last month's number.
RATES_NOTE_KEY = "runtime_rates_note"


def record_worker_failure(conn: sqlite3.Connection, exc: BaseException,
                          *, fatal: bool) -> None:
    """Write the failure where a PERSON can find it: the warehouse.

    On its own connection, because the caller's is usually the thing that
    just broke — recording the failure inside the failed transaction is how
    a failure record gets rolled away with what it was reporting.
    """
    payload = json.dumps({
        "at": utc_now_iso(),
        "fatal": fatal,       # fatal = the loop is gone, not just this pass
        "error": f"{type(exc).__name__}: {exc}",
        "traceback": "".join(traceback.format_exception(exc))[-4000:],
    }, ensure_ascii=False)
    try:
        conn.rollback()
        conn.execute(
            "INSERT INTO scrapex_meta (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (WORKER_ERROR_KEY, payload))
        conn.commit()
    except Exception:
        traceback.print_exc(file=sys.stderr)


def clear_worker_failure(conn: sqlite3.Connection) -> None:
    """A pass that completes clears the last error, so a recovered worker
    does not go on showing a fault it already survived."""
    conn.execute("DELETE FROM scrapex_meta WHERE key = ?", (WORKER_ERROR_KEY,))


def _age_s(stamp: str | None) -> float | None:
    """Seconds since an ISO stamp, or None when it is missing or unreadable.

    An unparseable stamp is NOT treated as fresh: a clock we cannot read is a
    clock we cannot trust.
    """
    if not stamp:
        return None
    try:
        then = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None
    return (datetime.now(UTC) - then).total_seconds()


def worker_health(conn: sqlite3.Connection) -> dict:
    """Is the WORKER alive — a different question from whether the port answers,
    and the difference once cost the owner an afternoon.

    TWO heartbeats, because there are two ways to be alive and only one of them
    was being read. `runtime_heartbeat` is written at the top of each worker
    pass; `crawl_job.last_heartbeat_at` is written by a job while it works. The
    loop then hands its whole pass to run_job_once, so ANY crawl longer than
    HEARTBEAT_MAX_AGE_S left the runtime stamp stale and this function called a
    perfectly healthy worker dead — the harder the engine worked, the deader it
    looked.

    Measured on 2026-07-28: job 40 had been crawling ELBUROJ for three hours,
    850 requests in, its own heartbeat 4 seconds old, and /api/health said
    worker_alive false with failure null. The message it printed then —
    "Pages may still open, that is the web server, not the worker" — was an
    actively WRONG explanation, and `thread_alive: true` sat beside
    `alive: false` with nothing to reconcile them.

    A busy worker is therefore alive, and says what it is busy WITH.
    """
    rows = dict(conn.execute(
        "SELECT key, value FROM scrapex_meta WHERE key IN (?,?)",
        (HEARTBEAT_KEY, WORKER_ERROR_KEY)).fetchall())
    note = conn.execute("SELECT value FROM scrapex_meta WHERE key = ?",
                        (RATES_NOTE_KEY,)).fetchone()
    beat = rows.get(HEARTBEAT_KEY)
    failure = json.loads(rows[WORKER_ERROR_KEY]) if rows.get(WORKER_ERROR_KEY) else None
    age = _age_s(beat)
    idle_alive = age is not None and age <= HEARTBEAT_MAX_AGE_S

    # The job's own proof of life. Its window is wider on purpose: a polite
    # crawler waits out a Crawl-delay between requests, so a job legitimately
    # goes quiet for longer than a loop pass ever should.
    running = conn.execute(
        "SELECT job_ref, current_source_key, stage, last_heartbeat_at, started_at "
        "FROM crawl_job WHERE status = 'running' "
        "ORDER BY job_id DESC LIMIT 1").fetchone()
    busy = None
    if running is not None:
        # Read by INDEX: this function is called with plain connections as well
        # as Row ones, and name access would raise on the plain kind — inside
        # the very call that is meant to report whether anything is wrong.
        job_ref, source_key, stage, job_beat, started_at = running[:5]
        job_age = _age_s(job_beat)
        if job_age is not None and job_age <= JOB_HEARTBEAT_MAX_AGE_S:
            busy = {"job_ref": job_ref, "source_key": source_key, "stage": stage,
                    "age_s": job_age, "started_at": started_at}

    alive = idle_alive or busy is not None
    if busy:
        where = busy["source_key"] or "a source"
        detail = (f"The worker is busy: {busy['stage'] or 'working'} {where} "
                  f"(reported {int(busy['age_s'])}s ago). The idle heartbeat is "
                  "stale because the job holds the loop — that is the job "
                  "running, not the worker stopping.")
    elif idle_alive:
        detail = "The worker is running."
    elif failure:
        detail = f"The worker stopped: {failure['error']}"
    elif beat:
        detail = (f"The worker last reported {int(age)}s ago, should report every "
                  f"{int(HEARTBEAT_MAX_AGE_S)}s, and no job is reporting either. "
                  "Pages may still open — that is the web server, not the worker.")
    else:
        detail = "The worker has never reported. Nothing can crawl until it does."
    return {"rates": json.loads(note[0]) if note and note[0] else None,
            "alive": alive, "busy": busy, "last_beat": beat, "age_s": age,
            "detail": detail, "failure": failure}


def touch_runtime_heartbeat(conn: sqlite3.Connection) -> None:
    """Proof of life from the ONLY process that can execute jobs."""
    conn.execute(
        "INSERT INTO scrapex_meta (key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (HEARTBEAT_KEY, utc_now_iso()))


def worker_is_alive(conn: sqlite3.Connection, max_age_s: float = HEARTBEAT_MAX_AGE_S) -> bool:
    """Is a job worker actually running right now?

    Queueing a job into a database no worker is draining looks like success and
    then hangs forever with a healthy-looking 'queued' status — the worst failure
    mode available. Callers that can only ENQUEUE (the native bridge) must check
    this first and refuse loudly instead.

    IT HAS NO CALLERS. Measured 2026-08-12: `scrapex/native.py` — the caller this
    docstring names — does not call it, and the last caller in the tree (`_about`
    in webui/app.py) was moved to `worker_health` because THIS function reads
    only the runtime heartbeat and therefore calls a busy worker dead. It is left
    here rather than deleted because the refusal it describes is still missing
    and still wanted; if the bridge is ever given that guard, it wants
    `worker_health`'s two-heartbeat verdict, not this one.
    """
    row = conn.execute("SELECT value FROM scrapex_meta WHERE key = ?", (HEARTBEAT_KEY,)).fetchone()
    if row is None or not row[0]:
        return False
    try:
        beat = datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except (ValueError, TypeError):
        return False
    return (datetime.now(UTC) - beat).total_seconds() <= max_age_s


def reclaim_orphaned_jobs(conn: sqlite3.Connection) -> int:
    """Settle jobs left mid-flight by a runtime that died. Returns how many.

    Only ONE worker ever executes, so at startup any in-flight job is ours and
    nobody else's — nothing can be legitimately running. Without this sweep a
    crash mid-crawl left a job 'running' forever, and `_source_is_busy` then
    blocked that source's schedules permanently with no error anywhere.

    Re-queueing is safe because the checkpoint records which sources already
    completed, so the resumed run skips them.
    """
    reclaimed = 0
    for stuck, target in (
        (JobStatus.PREPARING, JobStatus.QUEUED), (JobStatus.RUNNING, JobStatus.QUEUED),
        (JobStatus.RESUMING, JobStatus.QUEUED),
        (JobStatus.PAUSING, JobStatus.PAUSED),          # the owner asked to stop
        (JobStatus.CANCELLING, JobStatus.CANCELLED),    # ...and to give up entirely
    ):
        cur = conn.execute(
            "UPDATE crawl_job SET status = ?, control = ?, "
            " finished_at = CASE WHEN ? = 'cancelled' THEN ? ELSE finished_at END "
            "WHERE status = ?",
            (target.value, JobControl.NONE.value, target.value, utc_now_iso(), stuck.value))
        reclaimed += cur.rowcount
    # THE SWEEP SAYS WHEN IT RAN, and it says so even when it reclaimed nothing.
    #
    # OP-19. `Engine.start()` in the chaos test waited for /api/health and then
    # read crawl_job.status immediately — but health is answered by the HTTP
    # thread the moment the server binds, while this sweep runs on the WORKER
    # thread after it connects. Which of the two won was a coin toss: the test
    # failed three runs in four on a loaded Windows machine and passed reliably
    # on the Linux runner, so it read as "works in CI, broken locally" and
    # invited exactly the wrong diagnosis.
    #
    # Nothing here needed fixing — the reclaim was always correct. What was
    # missing is that the engine knew it had finished and nobody could ask.
    #
    # Written UNCONDITIONALLY, before the `if reclaimed` above would have
    # returned early: "no orphans found" is a completed sweep, and a marker that
    # only appears when there was damage cannot be waited on by anyone.
    conn.execute(
        "INSERT INTO scrapex_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (RECLAIM_KEY, utc_now_iso()))
    conn.commit()
    return reclaimed


def _finish(conn: sqlite3.Connection, job_id: int, status: JobStatus, error_summary: str | None) -> None:
    _update(conn, job_id, status=status.value, stage=None, current_source_key=None,
            finished_at=utc_now_iso(), last_heartbeat_at=utc_now_iso(),
            control=JobControl.NONE.value, error_summary=error_summary)
    append_log(conn, job_id, f"job {status.value}",
               level=LogLevel.ERROR if status == JobStatus.FAILED else LogLevel.INFO)
    conn.commit()


# ---- the background worker ---------------------------------------------------

class JobRunner:
    """One poll loop that dispatches queued jobs, running several at once.

    The LOOP is single-threaded and owns scheduling, the heartbeat and the rate
    refresh. Each JOB runs on its own thread with its own connection, up to the
    owner's "Sites crawled at the same time" setting — so ten single-source
    schedules firing together crawl ten sites at once instead of nine waiting on
    one. The single-WRITER invariant (A10) is unchanged: it was never the single
    thread that guaranteed it — the process-wide write lock did, and it now
    serialises those job threads' ingests the same way it always serialised the
    crawl against the HTTP process. Two jobs never touch one site together
    because every lane passes the shared _CrawlAdmission's per-host reservation.

    At budget 1 (the shipped default) this is exactly one job at a time, byte
    for byte the old behaviour; raising the setting is what turns it on.
    """

    def __init__(self, db_path, manifest_provider: Callable[[], object],
                 poll_interval_s: float = 0.5, capture: Callable | None = None,
                 path_provider: Callable[[], str] | None = None) -> None:
        self._db_path = db_path
        # Where the warehouse is NOW. The worker used to open one connection at
        # start and hold it forever, so after a move or a compaction it kept
        # crawling into the superseded file and everything it gathered landed
        # where nothing else in the product would ever read it.
        self._path_provider = path_provider or (lambda: db_path)
        self._manifest_provider = manifest_provider
        self._poll_interval_s = poll_interval_s
        self._capture = capture          # injectable so the thread itself is testable
        self._stop = threading.Event()
        self._reopen = threading.Event()   # a restore needs our file handle gone
        self._thread: threading.Thread | None = None
        # job_ref -> its running thread. The loop launches into this and reaps
        # from it; the SAME admission below is shared by every job in it, which
        # is the only way its per-host rule can span jobs rather than one.
        self._running: dict[str, threading.Thread] = {}
        self._admission: _CrawlAdmission | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="scrapex-jobs", daemon=True)
        self._thread.start()

    @property
    def is_alive(self) -> bool:
        """Whether the crawl worker, not merely the HTTP process, is running."""
        return bool(
            self._thread is not None
            and self._thread.is_alive()
            and not self._stop.is_set()
        )

    def stop(self, timeout_s: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout_s)
            self._thread = None

    def _locked_capture(self, conn: sqlite3.Connection, entry,
                        job_id: int | None = None, **extras) -> CaptureResult:
        # Whatever run_job_once decided the capture needs — history, resume,
        # archive_first — travels straight through: this seam only ADDS the
        # write lock, so it must not enumerate (and stale-out on) the keyword
        # set capture_source accepts. Forwarding **extras is why a full_rebuild's
        # archive_first reaches capture instead of dying here (owner-reported:
        # every rebuild failed on an unexpected 'archive_first').
        #
        # The lock is passed DOWN so it wraps only the ingest write, not the
        # network crawl. Holding it across the whole fetch made every unrelated
        # UI write fail with a conflict for the duration of a crawl.
        return capture_source(conn, entry, job_id,
                              lock=lambda: dbmod.write_lock(self._db_path),
                              **extras)

    def release_database(self) -> None:
        """Ask the worker to drop its connection before the next poll.

        A restore has to RENAME the live database, and on Windows an open handle
        makes that impossible. The route gave up its own connection; this one is
        held for the worker's whole life, so it has to be asked. The worker
        reopens on its next iteration, which is also the only safe moment.
        """
        self._reopen.set()

    def _follow_the_warehouse(self, conn: sqlite3.Connection) -> sqlite3.Connection:
        """Reopen if the database moved under us; otherwise return `conn` as is.

        Checked between jobs, never during one: a crawl that started against one
        file must finish against it, and the switch is only safe at the same
        boundary the pause and cancel controls already use.

        NOTHING IS COMMITTED UNTIL THE NEW HANDLE EXISTS. The handle really does
        have to be released before the reopen — a restore renames the file and
        Windows will not rename what anyone holds — so the failure window cannot
        be closed by opening first. What CAN be fixed is what a failed reopen
        leaves behind. Clearing `_reopen` and moving `_db_path` up front meant
        that a connect which raised (the instant during `os.replace` when the
        path does not exist, a migration mismatch, a locked file) left the loop
        holding a CLOSED connection that the guard above then returned on every
        later pass: no crawls, no scheduler, no heartbeat, and the failure
        recorder's own rollback raising on the same dead handle, so nothing was
        written anywhere. Both are now committed only on success, and the caller
        drops the dead handle — so a transient fault stays transient.
        """
        current = str(self._path_provider())
        if current == str(self._db_path) and not self._reopen.is_set():
            return conn
        conn.commit()
        conn.close()
        # Give the file up for a moment: a restore renames it while we wait, and
        # reopening immediately would take the handle straight back.
        if self._stop.wait(self._poll_interval_s):
            pass
        fresh = dbmod.connect(current)
        reclaim_orphaned_jobs(fresh)     # anything left running belongs to the old file
        fresh.commit()
        self._db_path = current
        self._reopen.clear()
        return fresh

    def _refresh_rates(self, conn) -> None:
        """Keep the USD column's exchange rates current, quietly.

        Rate-limited to six hours, so a poll costs the two SELECTs in
        rates.refresh_is_due and stops there. Isolated from the job loop: a
        Google Finance outage must never stop a crawl from running — the USD
        column is an aid to ranking, and the prices are the product.

        THE DECLINE HAS TO BE CHEAP, and for a long time it was not. The
        six-hour throttle lives inside refresh_if_due, so this read as free —
        but `HttpFetcher()` was built to be passed IN, before that function
        could decline, and its httpx.Client reloads the OS certificate store:
        1.3s of CPU, twice a second, for a client no request was ever made
        with. An idle `scrapex ui` sat at ~44% of a core and quietly stretched
        everything else on the machine, including this suite's own timings
        (a migrate() measured 5.9s under two idle engines against 1.9s beside
        none). Asking first is the whole fix.
        """
        from . import rates

        # Before the lock and before the fetcher: a decline must touch nothing
        # but two SELECTs. Taking the write lock 172,800 times a day to be told
        # no was the cheaper half of the same mistake.
        try:
            if not rates.refresh_is_due(conn):
                return
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            self._record_failure(conn, exc)
            return

        from .connectors.base import HttpFetcher

        try:
            # The write lock, like every other write. Without it this blocked a
            # job the owner queued: the refresh runs on the worker's FIRST pass,
            # and this warehouse prices in 93 currencies (GPP's global fuel
            # data), so it held the database through 93 fetch-and-store cycles
            # while /api/jobs was trying to insert a row.
            with dbmod.write_lock(self._db_path):
                batch = rates.refresh_if_due(conn, HttpFetcher())
        except Exception as exc:
            traceback.print_exc(file=sys.stderr)
            self._record_failure(conn, exc)
            return
        if batch is None:
            return
        # NOT the job log: job_log_entry.job_id is NOT NULL with a foreign key,
        # and a rate refresh is not a job. It goes to scrapex_meta beside the
        # heartbeat, where /api/health can read it — the same reasoning that put
        # the worker's failure there rather than on a stderr nobody sees under
        # pythonw. Warnings are per-currency by design (the Turkey rule), so one
        # bad quote page is reported and the rest still land.
        conn.execute(
            "INSERT INTO scrapex_meta (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (RATES_NOTE_KEY, json.dumps({
                "at": utc_now_iso(),
                "stored": len(batch.rates),
                "warnings": batch.warnings[:20],
            }, ensure_ascii=False)))
        conn.commit()

    def _loop(self) -> None:
        # Imported lazily: scheduler imports this module, so a top-level import
        # here would be circular.
        from .scheduler import fire_due

        conn = dbmod.connect(self._db_path)
        try:
            reclaim_orphaned_jobs(conn)     # a previous runtime may have died mid-run
            while not self._stop.wait(self._poll_interval_s):
                try:
                    if conn is None:
                        # A previous pass released the handle and could not get
                        # a new one. Retrying here is the whole recovery: the
                        # fault that broke the reopen (a restore mid-rename, an
                        # unplugged drive) is usually over by the next poll.
                        conn = dbmod.connect(self._db_path)
                        reclaim_orphaned_jobs(conn)
                    self._reap_finished()
                    # A database move or a restore renames the live file, which
                    # cannot happen under a live crawl handle — so the reopen
                    # waits until every job thread has let its connection go.
                    # This is the same boundary the single-job worker used
                    # ("between jobs"); with several jobs it is "between waves".
                    if not self._running:
                        try:
                            conn = self._follow_the_warehouse(conn)
                        except BaseException:
                            # The old handle is closed and the new one never
                            # opened. Holding the dead object is what turned a
                            # passing fault into a permanently silent worker.
                            conn = None
                            raise
                    touch_runtime_heartbeat(conn)   # proof of life for enqueue-only clients
                    # Reaching here IS the recovery: the loop is running and
                    # the warehouse is writable. Clearing later would leave an
                    # idle worker showing a fault it already survived, because
                    # an idle pass `continue`s before it gets there.
                    clear_worker_failure(conn)
                    conn.commit()
                    # The local runtime IS the scheduler (spec 26) — browser
                    # alarms cannot be relied on to wake anything.
                    fire_due(conn, manifest=self._manifest_provider())
                    self._refresh_rates(conn)
                    self._dispatch(conn)
                except Exception as exc:
                    # ...but NEVER silently. Swallowing this used to leave a job
                    # 'running' forever (blocking its source's schedules) or spin
                    # the loop on it at poll speed with nothing written anywhere.
                    # A job that blew up records and parks ITSELF (see _start_job);
                    # this handler is for the loop's own scheduling work.
                    traceback.print_exc(file=sys.stderr)
                    self._record_failure(conn, exc)
        except BaseException as exc:
            # The loop itself is gone — the connect, the orphan reclaim, or
            # anything the inner handler could not hold. This is the case
            # that produced a live port and a dead worker with nothing said
            # anywhere, so it is recorded before the thread unwinds.
            traceback.print_exc(file=sys.stderr)
            try:
                record_worker_failure(dbmod.connect(self._db_path), exc, fatal=True)
            except Exception:
                traceback.print_exc(file=sys.stderr)
            raise
        finally:
            if conn is not None:
                conn.close()

    # ---- concurrent job dispatch --------------------------------------------

    def _reap_finished(self) -> None:
        """Drop the threads of jobs that have returned. Cheap; every poll.

        A finished job thread has already recorded its own outcome and closed
        its own connection (see _start_job); reaping is only bookkeeping, so the
        wave can shrink and let the next queued job in.
        """
        for job_ref, thread in list(self._running.items()):
            if not thread.is_alive():
                thread.join()
                del self._running[job_ref]

    def _next_startable(self, conn: sqlite3.Connection) -> str | None:
        """The lowest-id queued job that is not already in flight.

        Membership in `_running` — not a status flip — is what stops the same
        job being picked twice in the window before its thread sets 'preparing'.
        That keeps run_job_once the single place a job's status changes, so its
        careful "control is not cleared here" invariant is never second-guessed
        from the loop.
        """
        running = set(self._running)
        for row in conn.execute(
                "SELECT job_ref FROM crawl_job WHERE status = ? ORDER BY job_id",
                (JobStatus.QUEUED.value,)):
            if row[0] not in running:
                return row[0]
        return None

    def _dispatch(self, conn: sqlite3.Connection) -> None:
        """Fill the wave up to the budget with queued jobs.

        A reopen pending means a rename is waiting on our handles, so nothing new
        starts until the wave drains — see the loop. The admission is created
        once per wave and reused while any job runs, because a NEW admission per
        job would give each its own host locks and the cross-job rule would
        govern nothing. Its budget is re-read only when the wave is empty, so a
        setting change takes effect between waves rather than mid-crawl.
        """
        if str(self._path_provider()) != str(self._db_path) or self._reopen.is_set():
            return
        capacity = job_capacity(conn)
        if not self._running or self._admission is None:
            self._admission = _CrawlAdmission(capacity)
        while len(self._running) < capacity:
            job_ref = self._next_startable(conn)
            if job_ref is None:
                return
            self._start_job(job_ref, self._admission)

    def _start_job(self, job_ref: str, admission: _CrawlAdmission) -> None:
        """Run one job on its own thread, with its own connection.

        A job thread cannot borrow the loop's connection (sqlite3 forbids one
        across threads), so it opens and closes its own. It records and parks
        ITSELF on failure — the loop's handler cannot, because the loop no longer
        waits on the job. Registered in `_running` BEFORE it starts so the very
        next poll cannot re-pick it.
        """
        def run() -> None:
            conn = None
            try:
                conn = dbmod.connect(str(self._db_path))
                job = get_job(conn, job_ref)
                if job is None:
                    raise KeyError(f"unknown job_ref {job_ref!r}")
                # ONE LOOKUP, NOT A CHAIN. `runner_for` returning `None` means the
                # price crawl, which is the only kind whose runner needs more than
                # `(conn, job_ref)` -- see `SPECIALISED_RUNNERS`.
                runner = runner_for(job.get("job_kind", "crawl"))
                if runner is not None:
                    runner(conn, job_ref)
                else:
                    run_job_once(conn, job_ref, self._manifest_provider(),
                                 capture=self._capture or self._locked_capture,
                                 backup=lambda: backup_database(self._db_path),
                                 # Only the worker knows a real path to reopen, so
                                 # only the worker can offer concurrency.
                                 connect=lambda: dbmod.connect(str(self._db_path)),
                                 admission=admission)
            except Exception as exc:
                traceback.print_exc(file=sys.stderr)
                self._record_failure(conn, exc)
                if conn is not None:
                    self._fail_orphan(conn, job_ref, exc)
            finally:
                if conn is not None:
                    conn.close()

        thread = threading.Thread(target=run, name=f"scrapex-job-{job_ref}",
                                  daemon=True)
        self._running[job_ref] = thread
        thread.start()

    def _record_failure(self, conn: sqlite3.Connection | None, exc: BaseException) -> None:
        """Write the failure even when the worker no longer holds a connection.

        The pass that has no handle is exactly the pass whose reason the owner
        most needs — a reopen that failed — and it was the one pass that
        recorded nothing, because the recorder was handed the closed handle and
        its rollback raised on the way in.
        """
        if conn is not None:
            record_worker_failure(conn, exc, fatal=False)
            return
        try:
            spare = dbmod.connect(self._db_path)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            return
        try:
            record_worker_failure(spare, exc, fatal=False)
        finally:
            spare.close()

    @staticmethod
    def _fail_orphan(conn: sqlite3.Connection, job_ref: str, exc: BaseException) -> None:
        """Park a job whose execution blew up, on a fresh transaction so the
        failure record cannot be rolled away with the thing that failed."""
        try:
            job = get_job(conn, job_ref)
            if job is None or job["status"] in {s.value for s in TERMINAL_JOB_STATUSES}:
                return
            append_log(conn, job["job_id"], f"worker error: {exc}", level=LogLevel.ERROR)
            _finish(conn, job["job_id"], JobStatus.FAILED, f"worker error: {exc}")
        except Exception:
            conn.rollback()
            traceback.print_exc(file=sys.stderr)

    @staticmethod
    def _next_queued(conn: sqlite3.Connection) -> str | None:
        row = conn.execute(
            "SELECT job_ref FROM crawl_job WHERE status = ? ORDER BY job_id LIMIT 1",
            (JobStatus.QUEUED.value,),
        ).fetchone()
        return row[0] if row is not None else None
