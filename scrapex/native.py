"""Chrome Native Messaging bridge (spec sections 4, 6, and the MV3 constraints).

WHAT THIS IS: the CONTROL path, and nothing else. Chrome frames every message
with a 4-byte length prefix and caps a message at 1 MB, but the real constraint
is the spec's: never push a whole dataset or log through one message. So the
panel has two paths and they do not overlap — CONTROL travels here over native
messaging (start the engine, read and set autostart, ping), and every byte of
DATA travels HTTP to the routes in webui/app.py.

Nine data commands used to live here as well: GET_STATUS, GET_SOURCES,
START_JOB, GET_JOB, GET_JOBS, CONTROL_JOB, GET_JOB_LOGS, GET_RECORDS and
GET_CHANGES. Each was a second definition of a contract webui/app.py already
served, carrying its own pagination and its own validation — and not one of
them had a caller anywhere in the extension; the only thing exercising them was
their own tests. Two definitions of one contract drift, and the one nobody
calls is the one that drifts without anybody noticing. They are gone, and the
split above is the rule that replaced them.

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

from . import __version__, enginelaunch
from . import db as dbmod

# Bumped only on a BREAKING change to the contract between the extension and
# this machine — BOTH paths, not just this one. /api/health publishes this same
# number so the HTTP path, which carries all the data traffic, can refuse a
# mismatch outright instead of 404ing route by route on an engine that no
# longer speaks its contract. The extension sends the version it was built
# against so a mismatch is reported, never guessed at.
#
# THE NUMBER IS WRITTEN TWICE, because the extension cannot import Python: the
# other copy is `PROTOCOL_VERSION` in extension/transport.js. A handshake whose
# two ends can silently disagree is worse than no handshake, so test_native.py
# reads the number back out of that file and fails if they ever diverge.
PROTOCOL_VERSION = 1

# The commands that need nothing but this process: no warehouse, no manifest.
# They are EXACTLY the ones the owner reaches for when the warehouse or the
# manifest is the thing that is broken, so serve() answers them without opening
# either. Since the data commands moved to HTTP that is now every command this
# host serves — but the guard stays, because it is what serve() consults for a
# command it does NOT know: an extension built against a newer contract, or one
# built before this pruning and still sending GET_RECORDS, must meet the
# fail-safe path rather than be answered from a process that opened nothing.
# Keep this in step with _dispatch: a command listed here that later starts
# reading `conn` would meet None.
STANDALONE_COMMANDS = frozenset({
    "PING", "START_ENGINE", "AUTOSTART_STATUS", "SET_AUTOSTART",
    "CHECK_STARTUP", "UPGRADE_DATABASE",
})


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
    """Route a CONTROL command. `conn` and `manifest` are unused by every
    command that is left and that is the point — see the module docstring: a
    command that needs the warehouse is an HTTP route, not a frame on this
    pipe. They stay in the signature because serve() still opens them for a
    command this host does not know, and answers `engine_unavailable` instead
    of dying when it cannot.
    """
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

    if command == "CHECK_STARTUP":
        # This is deliberately native-only. The HTTP engine may be the very
        # thing that cannot start, so a page cannot be the only place that
        # checks whether the next build can open the warehouse.
        return startup_check()

    if command == "UPGRADE_DATABASE":
        # The same escape hatch must also work while the engine is down. The
        # old UI could show "Upgrade database" but its HTTP request had no
        # server left to receive it after a failed restart.
        return upgrade_database()

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


def _database_report() -> tuple[dict[str, dict] | None, str | None]:
    """Read the current build's database readiness without opening the engine.

    Missing databases are not a blocker: the engine creates them on first
    start. Existing databases with a failed health report are different and
    must be named before the launcher starts a process that will immediately
    disappear.
    """
    try:
        from .databases import DatabaseRegistry

        registry = DatabaseRegistry.defaults()
        states = registry.health()
    except Exception as exc:
        return None, str(exc)
    return states, None


def startup_check() -> dict:
    """Return a structured, actionable preflight result for engine startup."""
    states, failure = _database_report()
    if failure:
        return _error(
            "startup_check_failed",
            f"ScrapeX could not inspect its databases: {failure}",
            action="check_storage",
        )
    blocked = [
        (name, state) for name, state in (states or {}).items()
        if not state["ok"] and state["status"] != "Missing"
    ]
    if not blocked:
        return {"ok": True, "databases": states or {}}
    details = "; ".join(
        f"{name}: {state['status']}. {state['action']}"
        for name, state in blocked
    )
    # THE CONSTANT, NOT A FOURTH COPY OF THE WORDS. `dbupgrade.BEHIND` documents
    # itself as "spelled once here and imported by both callers" and this was the
    # second spelling the whole time: the button offered here is the one
    # `upgrade_what_is_only_behind` decides to act on, and the two decided it by
    # comparing against strings that nothing held together.
    from .dbupgrade import BEHIND

    action = "upgrade_database" if any(
        state["status"] == BEHIND for _, state in blocked
    ) else "check_storage"
    return _error(
        "startup_blocked",
        details,
        action=action,
        databases=states or {},
    )


def upgrade_database() -> dict:
    """Apply forward migrations from the native host when HTTP is unavailable.

    THROUGH THE GUARDED PATH SINCE `OP-127`. This called
    `DatabaseRegistry.defaults().initialize()` directly, which migrates an existing file
    with **none** of the four protections `registry.ensure_ready`'s docstring says are
    kept in the caller: no backup, no BEHIND check, no refusal over damage, and nothing
    said out loud. `EngineDatabase.initialize()` also migrates BEFORE it verifies, so a
    damaged file was migrated first -- the third protection's exact stated hazard.

    AND THIS IS THE DOOR THE OWNER USES. `R-81`: the panel is the only interface, so the
    surface with no safety was the only one he could reach. The engine's own launch has
    always gone through the guarded path -- `_spawn_engine` runs `engine_argv("ui", ...)`
    -- which is why the two doors differed for so long without anything failing.

    THE REPLY NOW NAMES THE BACKUP, which is the fourth protection arriving here for the
    first time: *said out loud*. The old message could only say how many migrations were
    applied, because there was no backup to name.
    """
    try:
        from .databases import DatabaseRegistry
        from .dbupgrade import upgrade_what_is_only_behind

        registry = DatabaseRegistry.defaults()
        # THE REPORT FIRST, BECAUSE THE RULE IS DECIDED ON IT. `ensure_ready` creates a
        # database that does not exist -- which holds nothing to lose -- and REPORTS one
        # that does, without touching it. That report is what says whether the only fault
        # is the version.
        report = registry.ensure_ready()
        report, outcome = upgrade_what_is_only_behind(registry, report)
        states, failure = _database_report()
        if failure:
            return _error("database_upgrade_failed", failure, action="check_storage")
        if outcome.refused:
            # REFUSED IS NOT A CRASH AND IT IS NOT A SUCCESS. The panel gets the reason in
            # words and the action it can take, because a button that reports nothing is
            # the failure `R-81` names.
            return _error("database_upgrade_failed", outcome.refused,
                          action="check_storage")
        return {"ok": True, "applied": outcome.applied, "databases": states or {},
                "backups": [{"kind": kind, "path": where}
                            for kind, where in outcome.backups],
                "message": outcome.message()}
    except Exception as exc:
        return _error("database_upgrade_failed", str(exc), action="check_storage")


def _spawn_engine(port: int) -> None:
    """The engine, detached: it must OUTLIVE this host by design.

    Chrome tears the stdio host down right after the reply, so the engine is
    started as its own process group with no console. pythonw where it exists,
    because python.exe would flash a console window at the owner on every
    start. Output goes to ~/.scrapex/engine.log — a detached process with no
    log is undiagnosable the day it fails to come up.
    """
    import subprocess

    from .relaunch import open_engine_log

    # `enginelaunch` owns the `-m scrapex.cli` question, which this got wrong
    # for the shipped binary: a frozen build ignores `-m` and the child became
    # a silent native messaging host instead of an engine (`OP-36`).
    command = enginelaunch.engine_argv("ui", "--port", str(port))
    # Rotated at the one place it is opened: four writers append to this file and
    # none of them used to bound it, while every failure message in the panel
    # sends the owner to read it.
    log = open_engine_log()
    flags = 0
    if sys.platform == "win32":
        flags = (subprocess.DETACHED_PROCESS |
                 subprocess.CREATE_NEW_PROCESS_GROUP)
    try:
        subprocess.Popen(
            command,
            cwd=str(Path(__file__).resolve().parent.parent),
            stdin=subprocess.DEVNULL, stdout=log, stderr=log,
            creationflags=flags)
    finally:
        # The engine keeps its own inherited handle. Ours was never closed, and
        # a handle nobody closes is a file nothing can rotate.
        log.close()


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
    preflight = startup_check()
    if not preflight["ok"]:
        return {**preflight, "port": port}
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


# ---- the stdio loop ----------------------------------------------------------

def serve(db_path=None, stdin: BinaryIO | None = None, stdout: BinaryIO | None = None,
          migrate: bool = False) -> int:
    """Read framed commands from Chrome until the pipe closes.

    NOTHING IS OPENED UNTIL A COMMAND NEEDS IT. The warehouse and the manifest
    used to be opened before the first frame was read, so a database written by
    a newer build — or a `sources.yaml` the engine's own Manage page had just
    made invalid — killed this process at startup. Chrome then reported a host
    that exited, the panel said "The helper started and stopped. Open Logs",
    and the Logs are inside the engine that START_ENGINE was the only way to
    start. The one command that repairs the fault was the one the fault removed.
    START_ENGINE, PING and the autostart pair touch neither, so they are answered
    from a process that has opened nothing (STANDALONE_COMMANDS).

    `migrate` is for LEGACY single-file warehouses only (tests, --db sessions).
    A registry database has its own numbered migration stream and was
    migrated when it was created; running the unified stream over it re-applies
    migration 1 and dies — "table tax_rule already exists" — before the first
    frame is read. That killed the host at startup, and from the extension's
    side it looked like the host was never installed at all. The same policy as
    the web layer's ensure_schema, at the same kind of seam.
    """
    from .config import load_manifest

    path = db_path or dbmod.DEFAULT_DB_PATH
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    conn: object = None
    manifest = None
    try:
        while True:
            message = read_message(stdin)
            if message is None:
                return 0                      # Chrome closed the port: a normal exit
            command = message.get("command") if isinstance(message, dict) else None
            try:
                if isinstance(message, dict) and command not in STANDALONE_COMMANDS:
                    if conn is None:
                        conn = dbmod.connect(path)
                        if migrate:
                            dbmod.migrate(conn)
                    if manifest is None:
                        manifest = load_manifest()
            except Exception as exc:
                # Deliberately leaves conn/manifest None, so the NEXT command
                # tries again: the owner repairs the database from the engine
                # this host can still start, and the repair takes effect without
                # anyone knowing a host has to be restarted.
                write_message(stdout, {**_error(
                    "engine_unavailable",
                    f"the ScrapeX warehouse or manifest could not be opened: {exc}. "
                    "Start the engine and open its page — it says which database, "
                    "what state, and what to do."),
                    "request_id": message.get("request_id")})
                continue
            try:
                response = handle(conn, message, manifest)
                if conn is not None:
                    conn.commit()
            except Exception as exc:
                if conn is not None:
                    conn.rollback()
                response = _error("internal", str(exc))
            write_message(stdout, response)
    finally:
        if conn is not None:
            conn.close()
