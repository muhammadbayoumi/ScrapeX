"""Spec 4/6: the Native Messaging bridge — framing, routing, and the split that
keeps it a CONTROL path: no command here touches the warehouse."""
from __future__ import annotations

import io
import json
import re
import sqlite3
import struct
import sys
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex.native import PROTOCOL_VERSION, handle, read_message, write_message
from scrapex.nativehost import HOST_NAME, build_manifest, install, manifest_path

ROOT = Path(__file__).resolve().parent.parent

# The data commands this host used to answer, each of them a second definition
# of a route webui/app.py already served and none of them ever called by the
# extension. Named here so the router is held to their absence.
RETIRED_COMMANDS = (
    "GET_STATUS", "GET_SOURCES", "START_JOB", "GET_JOB", "GET_JOBS",
    "CONTROL_JOB", "GET_JOB_LOGS", "GET_RECORDS", "GET_CHANGES",
)


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


# ---- framing -----------------------------------------------------------------

def test_message_round_trip():
    buffer = io.BytesIO()
    write_message(buffer, {"command": "PING", "note": "عربي"})
    buffer.seek(0)
    assert read_message(buffer) == {"command": "PING", "note": "عربي"}


def test_length_prefix_is_little_endian_uint32():
    buffer = io.BytesIO()
    write_message(buffer, {"a": 1})
    raw = buffer.getvalue()
    (length,) = struct.unpack("<I", raw[:4])
    assert length == len(raw) - 4 == len(json.dumps({"a": 1}, separators=(",", ":")))


def test_closed_and_truncated_streams_read_as_end():
    assert read_message(io.BytesIO(b"")) is None            # Chrome closed the port
    assert read_message(io.BytesIO(b"\x10\x00\x00\x00ab")) is None   # truncated body


# ---- protocol handshake ------------------------------------------------------

def test_ping_reports_versions(conn):
    r = handle(conn, {"command": "PING", "request_id": "x1"})
    assert r["ok"] and r["protocol_version"] == PROTOCOL_VERSION
    assert r["request_id"] == "x1"      # correlation survives the round trip


def test_version_mismatch_is_reported_not_guessed(conn):
    r = handle(conn, {"command": "PING", "protocol_version": PROTOCOL_VERSION + 99})
    assert r["ok"] is False and r["error"] == "version_mismatch"
    assert r["host_protocol_version"] == PROTOCOL_VERSION
    assert r["client_protocol_version"] == PROTOCOL_VERSION + 99


def test_matching_version_passes_through(conn):
    assert handle(conn, {"command": "PING", "protocol_version": PROTOCOL_VERSION})["ok"]


def test_unknown_command_and_bad_message(conn):
    assert handle(conn, {"command": "LAUNCH_ROCKET"})["error"] == "unknown_command"
    assert handle(conn, ["not", "a", "dict"])["error"] == "bad_message"


# ---- jobs over the bridge ----------------------------------------------------

def test_manifest_allowlists_only_the_given_extensions():
    m = build_manifest(["abcdef"], "/usr/bin/scrapex")
    assert m["name"] == HOST_NAME and m["type"] == "stdio"
    assert m["allowed_origins"] == ["chrome-extension://abcdef/"]
    assert m["path"] == "/usr/bin/scrapex"


def test_install_refuses_without_an_extension_id():
    with pytest.raises(ValueError, match="at least one extension id"):
        install([])


def test_install_writes_the_manifest_without_touching_the_registry(tmp_path, monkeypatch):
    monkeypatch.setattr("scrapex.nativehost._MANIFEST_DIRS",
                        {"linux": tmp_path, "win32": tmp_path, "darwin": tmp_path})
    written = install(["abcdef"], executable="/usr/bin/scrapex",
                      platform="linux", write_registry=False)
    assert written.exists()
    assert json.loads(written.read_text())["allowed_origins"] == ["chrome-extension://abcdef/"]


def test_manifest_never_points_at_a_bare_interpreter(tmp_path, monkeypatch):
    """Regression (HIGH): Chrome runs `path` directly with no arguments, so a bare
    python.exe just opens a REPL on the pipe and the engine never starts."""
    monkeypatch.setattr("scrapex.nativehost._MANIFEST_DIRS",
                        {"linux": tmp_path, "win32": tmp_path, "darwin": tmp_path})
    written = install(["abcdef"], platform=sys.platform, write_registry=False)
    path = json.loads(written.read_text())["path"]
    assert path != sys.executable            # not the raw interpreter
    assert Path(path).exists()               # a real, launchable shim


def test_build_manifest_refuses_an_empty_executable():
    with pytest.raises(ValueError, match="launchable executable"):
        build_manifest(["abcdef"], "")


def test_frozen_entry_defaults_to_the_native_host():
    """Chrome's launch arguments vary by build; anything not a known subcommand
    must be treated as "Chrome started us", never as CLI usage on the pipe."""
    # Loaded by path: the repo's `packaging/` dir is shadowed by the PyPI one.
    import importlib.util

    entry = Path(__file__).resolve().parent.parent / "packaging" / "engine_entry.py"
    spec = importlib.util.spec_from_file_location("scrapex_engine_entry", entry)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert "ui" in module.KNOWN_COMMANDS and "native-host" in module.KNOWN_COMMANDS
    assert "chrome-extension://abcdef/" not in module.KNOWN_COMMANDS


def test_manifest_path_is_per_platform(monkeypatch, tmp_path):
    assert manifest_path("linux").name == f"{HOST_NAME}.json"
    assert manifest_path("win32") != manifest_path("darwin")


# ---- START_ENGINE: the button that removes the terminal ----------------------
#
# The panel is a page and the engine is a local server; a page cannot start a
# process, but Chrome starts THIS host on demand — so the host is the hand that
# reaches the machine. These drive the command through handle() and pin its
# honesty: probe-based idempotence, and a reply that never claims more than a
# probe confirmed.

def test_start_engine_does_not_spawn_when_the_port_already_answers(conn, monkeypatch):
    from scrapex import native

    spawned = []
    monkeypatch.setattr(native, "_engine_listening", lambda port: True)
    monkeypatch.setattr(native, "_spawn_engine", lambda port: spawned.append(port))

    r = handle(conn, {"command": "START_ENGINE", "request_id": "s1"})

    assert r["ok"] and r["already_running"] and r["confirmed"]
    assert spawned == [], "a second engine was spawned onto an occupied port"
    assert r["request_id"] == "s1"


def test_start_engine_spawns_and_confirms_when_the_port_comes_up(conn, monkeypatch):
    from scrapex import native

    spawned = []
    answers = iter([False, True])          # down at the probe, up after the spawn
    monkeypatch.setattr(native, "_engine_listening", lambda port: next(answers))
    monkeypatch.setattr(native, "startup_check", lambda: {"ok": True, "databases": {}})
    monkeypatch.setattr(native, "_spawn_engine", lambda port: spawned.append(port))

    r = handle(conn, {"command": "START_ENGINE"})

    assert spawned == [native.DEFAULT_ENGINE_PORT]
    assert r["ok"] and r["started"] and r["confirmed"]


def test_start_engine_that_cannot_be_confirmed_says_so(conn, monkeypatch):
    """The extension's transport allows 5 seconds; a cold interpreter can need
    more. The reply must say confirmed=False rather than claim success — the
    panel's polling is the source of truth, not the button."""
    from scrapex import native

    monkeypatch.setattr(native, "_engine_listening", lambda port: False)
    monkeypatch.setattr(native, "startup_check", lambda: {"ok": True, "databases": {}})
    monkeypatch.setattr(native, "_spawn_engine", lambda port: None)
    monkeypatch.setattr(native, "_START_CONFIRM_BUDGET_S", 0.05)

    r = handle(conn, {"command": "START_ENGINE"})

    assert r["ok"] and r["started"]
    assert r["confirmed"] is False


def test_start_engine_surfaces_a_database_blocker_before_spawning(conn, monkeypatch):
    """A newer build must not start, die, and leave the panel with only a
    timeout. The native host is still available while the HTTP engine is down,
    so it can name the migration and its repair action first."""
    from scrapex import native

    spawned = []
    monkeypatch.setattr(native, "_engine_listening", lambda port: False)
    monkeypatch.setattr(native, "startup_check", lambda: {
        "ok": False,
        "error": "startup_blocked",
        "detail": "marketlens: Needs upgrade. Apply migration 56.",
        "action": "upgrade_database",
        "databases": {"marketlens": {"status": "Needs upgrade"}},
    })
    monkeypatch.setattr(native, "_spawn_engine", lambda port: spawned.append(port))

    answer = handle(conn, {"command": "START_ENGINE"})

    assert answer["ok"] is False
    assert answer["error"] == "startup_blocked"
    assert answer["action"] == "upgrade_database"
    assert "migration 56" in answer["detail"]
    assert spawned == []


def test_start_engine_honours_a_requested_port(conn, monkeypatch):
    from scrapex import native

    seen = []
    monkeypatch.setattr(native, "_engine_listening", lambda port: (seen.append(port), True)[1])
    monkeypatch.setattr(native, "_spawn_engine", lambda port: None)

    r = handle(conn, {"command": "START_ENGINE", "port": 8077})

    assert seen == [8077] and r["port"] == 8077


def test_the_host_never_runs_the_unified_migrations_over_a_marketlens_database(tmp_path):
    """The bug that killed the host at startup, caught by driving the shim the
    way Chrome does: serve() ran dbmod.migrate() unconditionally, the unified
    stream re-applied migration 1 over the split MarketLens database, and the
    process died on "table tax_rule already exists" before reading one frame.
    From the extension's side that is indistinguishable from "not installed".

    Same policy as the web layer's ensure_schema: only a LEGACY --db warehouse
    is migrated here."""
    from scrapex.databases.domain import MarketLensDatabase
    from scrapex.native import serve

    db = tmp_path / "marketlens.db"
    MarketLensDatabase(db).initialize()          # split stream, already at head

    request = io.BytesIO()
    payload = json.dumps({"command": "PING", "request_id": "b1"}).encode()
    request.write(struct.pack("<I", len(payload)) + payload)
    request.seek(0)
    reply = io.BytesIO()

    assert serve(db, stdin=request, stdout=reply) == 0   # no migrate: must not die

    reply.seek(0)
    (n,) = struct.unpack("<I", reply.read(4))
    answer = json.loads(reply.read(n))
    assert answer["ok"] and answer["request_id"] == "b1"


# ---- the host must survive the fault the owner needs it to repair ------------

def _framed(*messages) -> io.BytesIO:
    """Several commands down one pipe, exactly as Chrome frames them."""
    request = io.BytesIO()
    for message in messages:
        payload = json.dumps(message).encode()
        request.write(struct.pack("<I", len(payload)) + payload)
    request.seek(0)
    return request


def _answers(reply: io.BytesIO) -> list[dict]:
    reply.seek(0)
    out: list[dict] = []
    while True:
        head = reply.read(4)
        if len(head) < 4:
            return out
        (size,) = struct.unpack("<I", head)
        out.append(json.loads(reply.read(size)))


def test_an_unreadable_warehouse_does_not_take_start_engine_down(tmp_path, monkeypatch):
    """The fault and its repair used to be the same command.

    serve() opened the database before reading a frame, so a warehouse this
    build cannot read killed the process — and Chrome reported a host that
    exited, which the panel prints as "The helper started and stopped. Open
    Logs". The Logs live in the engine, and START_ENGINE is what starts it.
    """
    from scrapex import native

    broken = tmp_path / "marketlens.db"
    broken.write_bytes(b"this file is not a database at all")
    monkeypatch.setattr(native, "_engine_listening", lambda port: True)

    reply = io.BytesIO()
    code = native.serve(broken, stdin=_framed(
        {"command": "PING", "request_id": "p1"},
        {"command": "START_ENGINE", "request_id": "p2"},
        {"command": "GET_STATUS", "request_id": "p3"},
    ), stdout=reply)

    assert code == 0, "the host died on a warehouse it was never asked to open"
    ping, start, status = _answers(reply)
    assert ping["ok"] and ping["request_id"] == "p1"
    assert start["ok"] and start["already_running"], \
        "the one command that repairs the fault was refused because of it"
    # And the command that genuinely needs the warehouse says so, in words that
    # point at the repair — instead of the process disappearing.
    assert status["ok"] is False and status["error"] == "engine_unavailable"
    assert status["request_id"] == "p3"


def test_an_invalid_manifest_does_not_take_the_host_down(tmp_path, monkeypatch):
    """sources.yaml is written by the engine's own Manage page, so an invalid
    one is a state the product can put itself into. It used to be fatal at
    startup, for every command."""
    from scrapex import config, native

    db = tmp_path / "marketlens.db"
    from scrapex.databases.domain import MarketLensDatabase
    MarketLensDatabase(db).initialize()

    def _refuse(*a, **kw):
        raise ValueError("sources.yaml: unknown family 'magento-graphq'")

    monkeypatch.setattr(config, "load_manifest", _refuse)
    monkeypatch.setattr(native, "_engine_listening", lambda port: True)

    reply = io.BytesIO()
    code = native.serve(db, stdin=_framed(
        {"command": "START_ENGINE", "request_id": "m1"},
        {"command": "GET_SOURCES", "request_id": "m2"},
    ), stdout=reply)

    assert code == 0
    start, sources = _answers(reply)
    assert start["ok"], "a broken manifest blocked the button that opens the fixer"
    assert sources["error"] == "engine_unavailable"
    assert "sources.yaml" in sources["detail"]


def test_the_warehouse_is_opened_once_and_only_when_a_command_needs_it(tmp_path, monkeypatch):
    """Lazy, not per-command: reopening on every frame would trade one fault
    for a slower one."""
    from scrapex import native
    from scrapex.databases.domain import MarketLensDatabase

    db = tmp_path / "marketlens.db"
    MarketLensDatabase(db).initialize()
    opened: list[str] = []
    real_connect = dbmod.connect
    monkeypatch.setattr(native.dbmod, "connect",
                        lambda p: (opened.append(str(p)), real_connect(p))[1])
    monkeypatch.setattr(native, "_engine_listening", lambda port: True)

    reply = io.BytesIO()
    native.serve(db, stdin=_framed(
        {"command": "PING"}, {"command": "START_ENGINE"},
        {"command": "GET_SOURCES"}, {"command": "GET_SOURCES"},
    ), stdout=reply)

    assert opened == [str(db)], f"the warehouse was opened {len(opened)} time(s)"


# ---- who may drive the machine: the allowlist may not be taken, only joined --

def _allowlist(written: Path) -> list[str]:
    return [o.removeprefix("chrome-extension://").rstrip("/")
            for o in json.loads(written.read_text())["allowed_origins"]]


def test_a_second_extension_joins_the_allowlist_it_does_not_seize_it(tmp_path, monkeypatch):
    """/api/native-host/register is reachable from ANY extension on purpose: it
    repairs an id the allowlist no longer names, so holding it to that allowlist
    would lock out the repair. Replacing meant that exception could be used to
    EVICT — two installed extensions taking the helper from each other, and a
    Start-engine button that works every other time for no visible reason."""
    monkeypatch.setattr("scrapex.nativehost._MANIFEST_DIRS",
                        {"linux": tmp_path, "win32": tmp_path, "darwin": tmp_path})
    first = "a" * 32
    second = "b" * 32

    install([first], executable="/usr/bin/scrapex", platform="linux", write_registry=False)
    written = install([second], executable="/usr/bin/scrapex", platform="linux",
                      write_registry=False)

    assert _allowlist(written) == [second, first], \
        "the extension that asked last evicted the one that was working"


def test_re_registering_the_same_id_does_not_duplicate_it(tmp_path, monkeypatch):
    monkeypatch.setattr("scrapex.nativehost._MANIFEST_DIRS",
                        {"linux": tmp_path, "win32": tmp_path, "darwin": tmp_path})
    same = "c" * 32
    install([same], executable="/usr/bin/scrapex", platform="linux", write_registry=False)
    written = install([same], executable="/usr/bin/scrapex", platform="linux",
                      write_registry=False)
    assert _allowlist(written) == [same]


def test_the_allowlist_is_capped_and_drops_the_oldest_never_the_newest(tmp_path, monkeypatch):
    """An allowlist that only grows is one nobody prunes. The cap drops the
    folder a developer stopped loading from — never the id that just asked."""
    from scrapex.nativehost import MAX_ALLOWED_IDS

    monkeypatch.setattr("scrapex.nativehost._MANIFEST_DIRS",
                        {"linux": tmp_path, "win32": tmp_path, "darwin": tmp_path})
    ids = [chr(ord("a") + i) * 32 for i in range(MAX_ALLOWED_IDS + 2)]
    for eid in ids:
        written = install([eid], executable="/usr/bin/scrapex", platform="linux",
                          write_registry=False)

    listed = _allowlist(written)
    assert len(listed) == MAX_ALLOWED_IDS
    assert listed[0] == ids[-1], "the id that just asked was dropped"
    assert ids[0] not in listed, "the oldest id was kept over a newer one"


def test_installing_by_hand_still_means_exactly_what_it_was_given(tmp_path, monkeypatch):
    """`scrapex install-native-host` is the deliberate prune: a person typing
    the ids means that list, not that list plus everything before it."""
    monkeypatch.setattr("scrapex.nativehost._MANIFEST_DIRS",
                        {"linux": tmp_path, "win32": tmp_path, "darwin": tmp_path})
    install(["d" * 32], executable="/usr/bin/scrapex", platform="linux",
            write_registry=False)
    written = install(["e" * 32], executable="/usr/bin/scrapex", platform="linux",
                      write_registry=False, replace=True)
    assert _allowlist(written) == ["e" * 32]


def test_the_web_layer_reads_the_allowlist_through_the_module_that_owns_it(tmp_path, monkeypatch):
    """One file decides who may drive this machine, and one reader parses it."""
    from scrapex import nativehost
    from scrapex.webui import app as webapp

    monkeypatch.setattr("scrapex.nativehost._MANIFEST_DIRS",
                        {"linux": tmp_path, "win32": tmp_path, "darwin": tmp_path})
    monkeypatch.setattr(nativehost, "manifest_path",
                        lambda platform=None: tmp_path / f"{HOST_NAME}.json")
    install(["f" * 32], executable="/usr/bin/scrapex", platform=sys.platform,
            write_registry=False)
    assert webapp.allowed_extension_ids() == ["f" * 32]


# ---- the surface that was retired, and the one contract left on it -----------

def test_the_retired_data_commands_are_gone_from_the_router(conn):
    """Ten commands answered here that nothing ever called.

    Each was a second definition of a route webui/app.py already served, with
    its own pagination and its own validation, kept alive only by its own
    tests — so the two could drift and no test in the suite would notice. The
    panel reaches the engine over HTTP for data and over native messaging for
    the six things only the local launcher can do.
    """
    for command in RETIRED_COMMANDS:
        answer = handle(conn, {"command": command, "request_id": "r"})
        assert answer["error"] == "unknown_command", (
            f"{command} still answers here — the data surface was meant to have "
            "one definition, in the web layer")
        assert answer["request_id"] == "r"


def test_the_control_commands_the_panel_actually_calls_still_answer(conn, monkeypatch):
    """The other half: retiring the data surface must not touch the six
    commands the panel genuinely uses. Grep the extension before changing this
    list — it is the whole reason this host exists."""
    from scrapex import native

    monkeypatch.setattr(native, "_engine_listening", lambda port: True)
    for command in ("PING", "START_ENGINE"):
        assert handle(conn, {"command": command})["ok"] is True, command
    assert set(native.STANDALONE_COMMANDS) == {
        "PING", "START_ENGINE", "AUTOSTART_STATUS", "SET_AUTOSTART",
        "CHECK_STARTUP", "UPGRADE_DATABASE"}


def test_startup_check_names_the_database_action(monkeypatch):
    from scrapex import native

    monkeypatch.setattr(native, "_database_report", lambda: ({
        "marketlens": {
            "ok": False,
            "status": "Needs upgrade",
            "action": "Run init-db",
        },
    }, None))

    answer = native.startup_check()

    assert answer["ok"] is False
    assert answer["error"] == "startup_blocked"
    assert answer["action"] == "upgrade_database"
    assert "marketlens: Needs upgrade. Run init-db" == answer["detail"]


def test_the_two_protocol_constants_cannot_drift(conn):
    """PROTOCOL_VERSION is written twice — once in Python, once in JavaScript —
    because the extension cannot import Python. Two constants that must agree
    and have nothing holding them together is a defect waiting for a release;
    this is the thing holding them together."""
    import re

    js = (ROOT / "extension" / "transport.js").read_text(encoding="utf-8")
    found = re.search(r"export const PROTOCOL_VERSION\s*=\s*(\d+)", js)
    assert found, "transport.js no longer exports PROTOCOL_VERSION"
    assert int(found.group(1)) == PROTOCOL_VERSION, (
        f"the extension speaks protocol {found.group(1)} and the engine speaks "
        f"{PROTOCOL_VERSION}; bump both or neither")
