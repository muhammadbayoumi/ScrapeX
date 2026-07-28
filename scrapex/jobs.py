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

import json
import sqlite3
import sys
import threading
import traceback
import uuid
from datetime import datetime, timezone
from typing import Callable, Iterable

from . import db as dbmod
from .archive import archive_source, backup_database
from .capture import CaptureResult, capture_source
from .connectors.base import CrawlInterrupted
from .ingest import canary_breach, previous_rows_seen
from .payload import utc_now_iso
from .vocab import (
    BLOCKING_JOB_STATUSES, TERMINAL_JOB_STATUSES, WORKER_HELD_STATUSES,
    JobControl, JobStage, JobStatus, LogLevel, RunMode,
)

_COUNTER_FIELDS = ("observations", "duplicates", "products", "variants",
                   "attributes", "skipped_ignored", "rejected_out_of_scope")


# ---- store -------------------------------------------------------------------

def create_job(conn: sqlite3.Connection, source_keys: Iterable[str],
               run_mode: RunMode | str = RunMode.UPDATE,
               status: JobStatus | str = JobStatus.QUEUED) -> str:
    """Persist a new job and return its public job_ref."""
    keys = [str(k) for k in source_keys]
    if not keys:
        raise ValueError("a job needs at least one source_key")
    job_ref = f"job_{uuid.uuid4().hex[:12]}"
    conn.execute(
        "INSERT INTO crawl_job (job_ref, run_mode, status, source_keys, progress_total) "
        "VALUES (?,?,?,?,?)",
        (job_ref, str(run_mode), str(status), json.dumps(keys), len(keys)),
    )
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
    return [_as_job(r) for r in conn.execute(sql, params + (limit,))]


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


def job_logs(conn: sqlite3.Connection, job_ref: str, limit: int = 200) -> list[dict]:
    """Newest-last tail of the job log (spec 25: the panel only ever tails)."""
    rows = conn.execute(
        "SELECT l.* FROM job_log_entry l JOIN crawl_job j ON j.job_id = l.job_id "
        "WHERE j.job_ref = ? ORDER BY l.job_log_id DESC LIMIT ?",
        (job_ref, limit),
    ).fetchall()
    return [dict(r) for r in reversed(rows)]


def _as_job(row: sqlite3.Row) -> dict:
    job = dict(row)
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
    for field in _COUNTER_FIELDS:
        counters[field] = counters.get(field, 0) + getattr(result.ingest, field)
    counters["errors"] = (counters.get("errors", 0)
                          + len(result.ingest.errors) + len(result.ingest.contained))
    counters["requests"] = counters.get("requests", 0) + result.requests_count
    return counters


# ---- execution (the testable seam) -------------------------------------------

def run_job_once(conn: sqlite3.Connection, job_ref: str, manifest,
                 capture: Callable[[sqlite3.Connection, object], CaptureResult] = capture_source,
                 backup: Callable[[], object] | None = None) -> dict:
    """Execute one job to completion, or until a pause/cancel boundary.

    Synchronous and thread-free by design so the whole lifecycle is testable.
    Per-source failures are isolated and recorded (Q3): one dead site downgrades
    the job to partially_completed, it never kills the other sources.
    """
    job = get_job(conn, job_ref)
    if job is None:
        raise KeyError(f"unknown job_ref {job_ref!r}")
    if job["status"] in {s.value for s in TERMINAL_JOB_STATUSES}:
        return job

    job_id = job["job_id"]
    checkpoint = job["checkpoint"]
    done: list[str] = list(checkpoint.get("completed_source_keys", []))
    counters: dict = job["counters"]
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
        except Exception as exc:  # noqa: BLE001
            append_log(conn, job_id, f"backup failed: {exc}", level=LogLevel.ERROR)
            _finish(conn, job_id, JobStatus.FAILED, f"backup failed, rebuild aborted: {exc}")
            return get_job(conn, job_ref)
    conn.commit()

    for source_key in job["source_keys"]:
        if source_key in done:
            continue  # resumed job: this source already ran

        control = _control_of(conn, job_id)  # safe boundary: between sources only
        if control == JobControl.CANCEL.value:
            append_log(conn, job_id, "cancelled by owner")
            _finish(conn, job_id, JobStatus.CANCELLED, None)
            return get_job(conn, job_ref)
        if control == JobControl.PAUSE.value:
            append_log(conn, job_id, "paused by owner")
            _update(conn, job_id, status=JobStatus.PAUSED.value,
                    control=JobControl.NONE.value, stage=None,
                    last_heartbeat_at=utc_now_iso())
            conn.commit()
            return get_job(conn, job_ref)

        _update(conn, job_id, status=JobStatus.RUNNING.value, stage=JobStage.FETCHING.value,
                current_source_key=source_key, last_heartbeat_at=utc_now_iso())
        conn.commit()
        try:
            entry = manifest.get(source_key)
            previous = previous_rows_seen(conn, source_key)
            # Keywords travel only when the situation asks for them, so every
            # existing capture fake with the plain (conn, entry, job_id)
            # signature keeps working untouched. `resume` fires for exactly
            # the source a pause interrupted MID-fetch: its journaled pages
            # are still on disk and the connector may skip them.
            extras: dict = {}
            if rebuilding:
                # The archive travels WITH the write, into the same lock —
                # doing it here meant a failed capture (a held lock, a dead
                # site) left the catalogue archived and nothing re-crawled.
                extras["archive_first"] = True
            if job["run_mode"] == RunMode.HISTORY_BACKFILL.value:
                extras["history"] = True
            if checkpoint.get("partial_source") == source_key:
                extras["resume"] = True
            result = (capture(conn, entry, job_id, **extras) if extras
                      else capture(conn, entry, job_id))
            _merge_counters(counters, result)
            append_log(conn, job_id,
                       f"{result.ingest.observations} observations, "
                       f"{result.ingest.products} new products, {result.requests_count} requests",
                       source_key=source_key)
            # Ingest errors used to be folded into a bare counter here, so the
            # job finished 'completed' with error_summary NULL and the MESSAGE —
            # the only thing that could explain a degraded run — was discarded.
            # Each one is now a job-level error (it degrades the job's outcome)
            # and a log line the owner can actually read.
            for issue in result.ingest.errors:
                errors.append(f"{source_key}: {issue}")
                append_log(conn, job_id, issue, level=LogLevel.WARNING,
                           source_key=source_key)
            # Contained side-effect failures did not degrade the run and must
            # not degrade the job — but silent is not an option either.
            for note in result.ingest.contained:
                append_log(conn, job_id, note, level=LogLevel.WARNING,
                           source_key=source_key)
            # Notices are neither: a normal outcome the owner can see, logged at
            # INFO so it never reads as trouble and never touches the counters.
            for note in result.ingest.notices:
                append_log(conn, job_id, note, level=LogLevel.INFO,
                           source_key=source_key)
            # What the connector could NOT collect belongs in this log too. The
            # CLI printed these warnings; here they were dropped, so the run
            # that lost NATURAL_GAS entirely — 47 country pages publishing no
            # local price, every one skipped — logged three clean lines and
            # read as a full success. Capped so a systemic failure cannot bury
            # the log; the cap itself is stated.
            shown = getattr(result, "warnings", None) or []
            for warning in shown[:30]:
                append_log(conn, job_id, warning, level=LogLevel.WARNING,
                           source_key=source_key)
            if len(shown) > 30:
                append_log(conn, job_id,
                           f"...and {len(shown) - 30} more warnings like these "
                           "(the CLI crawl prints them all)",
                           level=LogLevel.WARNING, source_key=source_key)
            # Politeness disclosures ride at INFO — the owner's robots ruling
            # (docs/robots-policy.md): how we behaved toward the site is worth
            # a line, never a warning that suggests the run needs review.
            for note in (getattr(result, "notes", None) or []):
                append_log(conn, job_id, note, source_key=source_key)
            # F6: a rotted connector fails QUIETLY — treat a volume breach as a
            # real failure, never a clean success.
            breach = canary_breach(entry, result.rows, previous)
            if breach is None:
                succeeded += 1
            else:
                errors.append(breach)
                append_log(conn, job_id, breach, level=LogLevel.WARNING, source_key=source_key)
        except CrawlInterrupted as stop:
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
                append_log(conn, job_id,
                           "cancel honoured mid-fetch — nothing from this source "
                           "was ingested and the partial fetch was discarded",
                           source_key=source_key)
                _finish(conn, job_id, JobStatus.CANCELLED, None)
            else:
                if kept:
                    append_log(conn, job_id,
                               f"pause honoured mid-fetch — {kept} fetched "
                               "page(s) kept; resume continues with the "
                               "remaining pages",
                               source_key=source_key)
                else:
                    append_log(conn, job_id,
                               "pause honoured mid-fetch — nothing from this "
                               "source was ingested; it restarts from the top "
                               "if resumed",
                               source_key=source_key)
                _update(conn, job_id, status=JobStatus.PAUSED.value,
                        control=JobControl.NONE.value, stage=None,
                        checkpoint_json=json.dumps(
                            {"completed_source_keys": done, "errors": errors,
                             "succeeded": succeeded,
                             "partial_source": source_key}),
                        last_heartbeat_at=utc_now_iso())
            conn.commit()
            return get_job(conn, job_ref)
        except Exception as exc:  # noqa: BLE001 — one bad source never kills the job (Q3)
            errors.append(f"{source_key}: {exc}")
            append_log(conn, job_id, f"failed: {exc}", level=LogLevel.ERROR, source_key=source_key)

        done.append(source_key)
        _update(conn, job_id, progress_done=len(done),
                checkpoint_json=json.dumps({"completed_source_keys": done,
                                            "errors": errors, "succeeded": succeeded}),
                counters_json=json.dumps(counters), last_heartbeat_at=utc_now_iso())
        conn.commit()

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
    except Exception:  # noqa: BLE001 — never let the reporter kill the worker
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
        then = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - then).total_seconds()


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
    """
    row = conn.execute("SELECT value FROM scrapex_meta WHERE key = ?", (HEARTBEAT_KEY,)).fetchone()
    if row is None or not row[0]:
        return False
    try:
        beat = datetime.strptime(row[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return False
    return (datetime.now(timezone.utc) - beat).total_seconds() <= max_age_s


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
    if reclaimed:
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
    """One worker thread draining queued jobs. Owns the only long-running writes.

    Deliberately single-threaded: it keeps the single-writer topology (A10) and
    makes 'one crawl at a time' the default the OS never has to fight over.
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

    def wake(self) -> None:
        """Called after enqueueing so a new job starts without waiting a full poll."""

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

        Rate-limited inside rates.refresh_if_due (six hours), so calling it every
        poll costs one SELECT almost always. Isolated from the job loop: a
        Google Finance outage must never stop a crawl from running — the USD
        column is an aid to ranking, and the prices are the product.
        """
        from . import rates
        from .connectors.base import HttpFetcher

        try:
            # The write lock, like every other write. Without it this blocked a
            # job the owner queued: the refresh runs on the worker's FIRST pass,
            # and this warehouse prices in 93 currencies (GPP's global fuel
            # data), so it held the database through 93 fetch-and-store cycles
            # while /api/jobs was trying to insert a row.
            with dbmod.write_lock(self._db_path):
                batch = rates.refresh_if_due(conn, HttpFetcher())
        except Exception as exc:  # noqa: BLE001 — never fatal to the loop
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
                job_ref = None
                try:
                    if conn is None:
                        # A previous pass released the handle and could not get
                        # a new one. Retrying here is the whole recovery: the
                        # fault that broke the reopen (a restore mid-rename, an
                        # unplugged drive) is usually over by the next poll.
                        conn = dbmod.connect(self._db_path)
                        reclaim_orphaned_jobs(conn)
                    try:
                        conn = self._follow_the_warehouse(conn)
                    except BaseException:
                        # The old handle is closed and the new one never opened.
                        # Holding the dead object is what turned a passing fault
                        # into a permanently silent worker, so let it go.
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
                    job_ref = self._next_queued(conn)
                    if job_ref is None:
                        continue
                    run_job_once(conn, job_ref, self._manifest_provider(),
                                 capture=self._capture or self._locked_capture,
                                 backup=lambda: backup_database(self._db_path))
                except Exception as exc:  # noqa: BLE001 — survive any one job...
                    # ...but NEVER silently. Swallowing this used to leave the job
                    # 'running' forever (blocking its source's schedules) or spin
                    # the loop on it at poll speed with nothing written anywhere.
                    traceback.print_exc(file=sys.stderr)
                    self._record_failure(conn, exc)
                    if job_ref is not None and conn is not None:
                        self._fail_orphan(conn, job_ref, exc)
        except BaseException as exc:  # noqa: BLE001
            # The loop itself is gone — the connect, the orphan reclaim, or
            # anything the inner handler could not hold. This is the case
            # that produced a live port and a dead worker with nothing said
            # anywhere, so it is recorded before the thread unwinds.
            traceback.print_exc(file=sys.stderr)
            try:
                record_worker_failure(dbmod.connect(self._db_path), exc, fatal=True)
            except Exception:  # noqa: BLE001
                traceback.print_exc(file=sys.stderr)
            raise
        finally:
            if conn is not None:
                conn.close()

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
        except Exception:  # noqa: BLE001 — the database itself is what is unreachable
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
        except Exception:  # noqa: BLE001 — a failing failure-handler must not kill the worker
            conn.rollback()
            traceback.print_exc(file=sys.stderr)

    @staticmethod
    def _next_queued(conn: sqlite3.Connection) -> str | None:
        row = conn.execute(
            "SELECT job_ref FROM crawl_job WHERE status = ? ORDER BY job_id LIMIT 1",
            (JobStatus.QUEUED.value,),
        ).fetchone()
        return row[0] if row is not None else None
