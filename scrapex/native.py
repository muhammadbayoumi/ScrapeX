"""Chrome Native Messaging bridge (spec sections 4, 6, and the MV3 constraints).

WHAT THIS IS: a COMMAND AND STATUS bridge, not a data pipe. Chrome frames every
message with a 4-byte length prefix and caps extension->host at 1 MB, but the
real constraint is the spec's: never push a whole dataset or log through one
message. So every listing command is cursor-paginated and hard-capped here, in
the router, where it cannot be forgotten by a caller.

WHY THE ROUTER IS PURE: `handle()` takes a connection and a dict and returns a
dict. No stdio, no threads. That makes the entire command surface testable
without spawning a host process; `serve()` is the thin stdio loop on top.

MV3 note: the service worker may hibernate after ~30s. Nothing here depends on
it — the local runtime owns job execution and all state lives in harvest.db, so
a reconnecting client just re-reads the current state.
"""
from __future__ import annotations

import json
import struct
import sys
from pathlib import Path
from typing import BinaryIO

from . import __version__, db as dbmod
from .changes import change_summary, recent_changes
from .jobs import create_job, get_job, job_logs, list_jobs, set_control, worker_is_alive
from .reports import browse_observations, list_sources

# Bumped only on a BREAKING change to the command surface. The extension sends
# the version it was built against so a mismatch is reported, never guessed at.
PROTOCOL_VERSION = 1

MAX_PAGE = 200          # hard cap: one message is never a dataset
MAX_LOG_TAIL = 200


# ---- framing -----------------------------------------------------------------

def read_message(stream: BinaryIO) -> dict | None:
    """One framed message, or None at clean end-of-stream (Chrome closed us)."""
    raw_length = stream.read(4)
    if len(raw_length) < 4:
        return None
    (length,) = struct.unpack("<I", raw_length)
    body = stream.read(length)
    if len(body) < length:
        return None                      # truncated: treat as a closed pipe
    return json.loads(body.decode("utf-8"))


def write_message(stream: BinaryIO, message: dict) -> None:
    body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    stream.write(struct.pack("<I", len(body)))
    stream.write(body)
    stream.flush()


# ---- command router ----------------------------------------------------------

def _page_size(message: dict, cap: int = MAX_PAGE) -> int:
    try:
        requested = int(message.get("limit", 50))
    except (TypeError, ValueError):
        requested = 50
    return max(1, min(requested, cap))


def _cursor(message: dict) -> int:
    """Opaque to the client; an offset here. Never trusted blindly."""
    try:
        return max(0, int(message.get("cursor") or 0))
    except (TypeError, ValueError):
        return 0


def _error(code: str, detail: str, **extra) -> dict:
    return {"ok": False, "error": code, "detail": detail, **extra}


def handle(conn, message: dict, manifest=None) -> dict:
    """Route one command. Always returns a dict; never raises for client input."""
    if not isinstance(message, dict):
        return _error("bad_message", "message must be a JSON object")
    command = message.get("command")
    request_id = message.get("request_id")

    client_protocol = message.get("protocol_version")
    if client_protocol is not None and client_protocol != PROTOCOL_VERSION:
        # Version parity check (spec: extension and runtime must agree).
        return {**_error("version_mismatch",
                         "the extension and the ScrapeX engine speak different protocol "
                         "versions — update whichever is older",
                         host_protocol_version=PROTOCOL_VERSION,
                         client_protocol_version=client_protocol),
                "request_id": request_id}

    try:
        result = _dispatch(conn, command, message, manifest)
    except KeyError as exc:
        result = _error("not_found", str(exc))
    except ValueError as exc:
        result = _error("invalid", str(exc))
    return {**result, "request_id": request_id}


def _dispatch(conn, command, message: dict, manifest) -> dict:
    if command == "PING":
        return {"ok": True, "app": "scrapex", "app_version": __version__,
                "protocol_version": PROTOCOL_VERSION}

    if command == "START_ENGINE":
        # The one thing only THIS process can do for the extension. The panel
        # is a page and the engine is a local server: a page cannot start a
        # process, but Chrome starts this host on demand — so the host is the
        # hand that reaches the machine. Without this the owner opens a
        # terminal every session, which is the exact friction being removed.
        return start_engine(message)

    if command == "GET_STATUS":
        active = list_jobs(conn, limit=5, active_only=True)
        return {"ok": True, "app_version": __version__,
                "sources_with_data": len(list_sources(conn)),
                # Surfaced so the panel can say "engine idle" instead of showing a
                # job that will never move.
                "worker_alive": worker_is_alive(conn),
                "active_jobs": [_job_brief(j) for j in active]}

    if command == "GET_SOURCES":
        return {"ok": True, "sources": [
            {"source_key": s.source_key, "source_name": s.source_name,
             "observations": s.observations, "products": s.products}
            for s in list_sources(conn)]}

    if command == "START_JOB":
        keys = message.get("source_keys") or []
        if isinstance(keys, str):
            keys = [keys]
        if not keys:
            raise ValueError("source_keys is required")
        if manifest is not None:
            for key in keys:
                manifest.get(key)          # KeyError -> not_found, before queueing
        # Chrome tears this stdio host down after each message, so it can never
        # host the worker itself. Queueing into a database nobody is draining
        # would look like success and then hang on a healthy-looking 'queued'
        # forever — refuse instead, and say what to start.
        if not worker_is_alive(conn):
            return _error("no_worker",
                          "the ScrapeX engine is not running, so the job was NOT queued — "
                          "start it with `scrapex ui` and try again")
        return {"ok": True, "job_ref": create_job(conn, keys,
                                                  message.get("run_mode", "update"))}

    if command == "GET_JOB":
        job = get_job(conn, message.get("job_ref", ""))
        if job is None:
            raise KeyError(f"unknown job {message.get('job_ref')!r}")
        return {"ok": True, "job": _job_brief(job)}

    if command == "GET_JOBS":
        jobs = list_jobs(conn, limit=_page_size(message, 50),
                         active_only=bool(message.get("active_only")))
        return {"ok": True, "jobs": [_job_brief(j) for j in jobs]}

    if command == "CONTROL_JOB":
        job_ref = message.get("job_ref", "")
        if get_job(conn, job_ref) is None:
            raise KeyError(f"unknown job {job_ref!r}")
        applied = set_control(conn, job_ref, message.get("control", "pause"))
        if not applied:
            return _error("conflict", f"job {job_ref!r} has already finished")
        return {"ok": True, "job": _job_brief(get_job(conn, job_ref))}

    if command == "GET_JOB_LOGS":
        job_ref = message.get("job_ref", "")
        if get_job(conn, job_ref) is None:
            raise KeyError(f"unknown job {job_ref!r}")
        # A TAIL, never the whole log — the full technical log stays in the DB.
        return {"ok": True, "entries": job_logs(conn, job_ref,
                                                limit=_page_size(message, MAX_LOG_TAIL))}

    if command == "GET_RECORDS":
        source_key = message.get("source_key", "")
        if not source_key:
            raise ValueError("source_key is required")
        limit, offset = _page_size(message), _cursor(message)
        page = browse_observations(conn, source_key, search=message.get("search") or None,
                                   availability=message.get("availability") or None,
                                   offset=offset, limit=limit)
        rows, total = page.rows, page.total
        visible = message.get("visible_fields")
        if visible:
            rows = [{k: r[k] for k in visible if k in r} for r in rows]
        next_cursor = offset + len(rows)
        return {"ok": True, "records": rows, "total": total,
                # None means "you have everything" — the client stops, not guesses.
                "next_cursor": next_cursor if next_cursor < total else None}

    if command == "GET_CHANGES":
        source_key = message.get("source_key") or None
        return {"ok": True,
                "summary": change_summary(conn, source_key) if source_key else {},
                "changes": recent_changes(conn, source_key, limit=_page_size(message))}

    if command == "AUTOSTART_STATUS":
        from . import autostart
        return {"ok": True, **autostart.status()}

    if command == "SET_AUTOSTART":
        # The panel's "Start with Windows" toggle. Native-only like
        # START_ENGINE: the launcher lives on the machine, and this host is
        # the extension's only hand that reaches it.
        from . import autostart
        if message.get("enabled"):
            path = autostart.install(int(message.get("port") or DEFAULT_ENGINE_PORT))
            return {"ok": True, "installed": True, "path": str(path)}
        autostart.remove()
        return {"ok": True, "installed": False,
                "path": str(autostart.launcher_path())}

    return _error("unknown_command", f"unknown command {command!r}")


# How long START_ENGINE waits to CONFIRM the port answers before replying.
# The extension's transport gives the whole exchange 5 seconds, so the host
# must answer inside that; an engine that needs longer still comes up — the
# reply just says confirmed=False and the panel's normal polling finds it.
_START_CONFIRM_BUDGET_S = 3.5

DEFAULT_ENGINE_PORT = 8000


def _engine_listening(port: int) -> bool:
    import socket

    with socket.socket() as probe:
        probe.settimeout(0.4)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _spawn_engine(port: int) -> None:
    """The engine, detached: it must OUTLIVE this host by design.

    Chrome tears the stdio host down right after the reply, so the engine is
    started as its own process group with no console. pythonw where it exists,
    because python.exe would flash a console window at the owner on every
    start. Output goes to ~/.scrapex/engine.log — a detached process with no
    log is undiagnosable the day it fails to come up.
    """
    import subprocess

    interpreter = Path(sys.executable)
    windowless = interpreter.with_name("pythonw.exe")
    runner = str(windowless if windowless.exists() else interpreter)
    log_home = Path.home() / ".scrapex"
    log_home.mkdir(parents=True, exist_ok=True)
    log = open(log_home / "engine.log", "ab")
    flags = 0
    if sys.platform == "win32":
        flags = (subprocess.DETACHED_PROCESS |
                 subprocess.CREATE_NEW_PROCESS_GROUP)
    subprocess.Popen(
        [runner, "-m", "scrapex.cli", "ui", "--port", str(port)],
        cwd=str(Path(__file__).resolve().parent.parent),
        stdin=subprocess.DEVNULL, stdout=log, stderr=log,
        creationflags=flags)


def start_engine(message: dict) -> dict:
    """Start the local engine if it is not already answering.

    Idempotent by probe, not by bookkeeping: the truth about "is the engine
    up" is whether the port answers, so that is the only thing consulted —
    a stale pidfile can lie, a listening socket cannot.
    """
    import time

    port = int(message.get("port") or DEFAULT_ENGINE_PORT)
    if _engine_listening(port):
        return {"ok": True, "already_running": True, "confirmed": True, "port": port}
    _spawn_engine(port)
    deadline = time.monotonic() + _START_CONFIRM_BUDGET_S
    while time.monotonic() < deadline:
        if _engine_listening(port):
            return {"ok": True, "started": True, "confirmed": True, "port": port}
        time.sleep(0.25)
    # Started but not yet answering — normal on a cold interpreter. Saying
    # "confirmed": False is honest; claiming success would teach the owner to
    # distrust the button the first slow morning.
    return {"ok": True, "started": True, "confirmed": False, "port": port}


def _job_brief(job: dict) -> dict:
    """Aggregated progress only (spec 25) — never per-record events."""
    total = job.get("progress_total") or 0
    done = job.get("progress_done") or 0
    return {"job_ref": job["job_ref"], "status": job["status"], "run_mode": job["run_mode"],
            "source_keys": job["source_keys"], "current_source_key": job["current_source_key"],
            "stage": job["stage"], "counters": job.get("counters", {}),
            "progress": {"done": done, "total": total,
                         "percent": round(done / total * 100) if total else 0},
            "error_summary": job.get("error_summary")}


# ---- the stdio loop ----------------------------------------------------------

def serve(db_path=None, stdin: BinaryIO | None = None, stdout: BinaryIO | None = None,
          migrate: bool = False) -> int:
    """Read framed commands from Chrome until the pipe closes.

    `migrate` is for LEGACY single-file warehouses only (tests, --db sessions).
    A MarketLens database has its own numbered migration stream and was
    migrated when it was created; running the unified stream over it re-applies
    migration 1 and dies — "table tax_rule already exists" — before the first
    frame is read. That killed the host at startup, and from the extension's
    side it looked like the host was never installed at all. The same policy as
    the web layer's ensure_schema, at the same kind of seam.
    """
    from .config import load_manifest

    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    conn = dbmod.connect(db_path or dbmod.DEFAULT_DB_PATH)
    try:
        if migrate:
            dbmod.migrate(conn)
        manifest = load_manifest()
        while True:
            message = read_message(stdin)
            if message is None:
                return 0                      # Chrome closed the port: a normal exit
            try:
                response = handle(conn, message, manifest)
                conn.commit()
            except Exception as exc:  # noqa: BLE001 — one bad command never kills the host
                conn.rollback()
                response = _error("internal", str(exc))
            write_message(stdout, response)
    finally:
        conn.close()
