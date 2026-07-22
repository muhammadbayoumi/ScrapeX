"""Spec 4/6: the Native Messaging bridge — framing, routing, and the caps that
stop one message becoming a data dump."""
from __future__ import annotations

import io
import json
import sqlite3
import struct
import sys
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex.ingest import ingest_payloads
from scrapex.jobs import create_job, get_job, touch_runtime_heartbeat
from scrapex.native import (
    MAX_PAGE, PROTOCOL_VERSION, handle, read_message, write_message,
)
from scrapex.nativehost import HOST_NAME, build_manifest, install, manifest_path
from tests.test_ingest import make_entry, make_payload, one_row

SOURCE = "ELSEWEDYSHOP"


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


class _Manifest:
    def get(self, key):
        if key != SOURCE:
            raise KeyError(f"unknown source_key {key!r}")
        return object()


def _seed(conn, count=5):
    rows = [one_row(external_product_id=str(1000 + i), external_variant_id=str(5000 + i),
                    product_name=f"Lamp {i}") for i in range(count)]
    ingest_payloads(conn, make_entry(), [make_payload(rows)])


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

def test_start_job_validates_before_queueing(conn):
    assert handle(conn, {"command": "START_JOB", "source_keys": ["GHOST"]},
                  _Manifest())["error"] == "not_found"
    assert handle(conn, {"command": "START_JOB"}, _Manifest())["error"] == "invalid"


def test_start_job_refuses_when_no_worker_is_running(conn):
    """Regression (CRITICAL): the stdio host is torn down after each message, so
    it cannot execute anything. Queueing into a database nobody drains used to
    return ok and then hang on a healthy-looking 'queued' forever."""
    r = handle(conn, {"command": "START_JOB", "source_keys": [SOURCE]}, _Manifest())
    assert r["ok"] is False and r["error"] == "no_worker"
    assert "not queued" in r["detail"].lower()
    assert conn.execute("SELECT COUNT(*) FROM crawl_job").fetchone()[0] == 0


def test_start_job_queues_when_a_worker_is_alive(conn):
    touch_runtime_heartbeat(conn)
    r = handle(conn, {"command": "START_JOB", "source_keys": [SOURCE]}, _Manifest())
    assert r["ok"] and get_job(conn, r["job_ref"])["status"] == "queued"


def test_status_reports_whether_a_worker_is_alive(conn):
    assert handle(conn, {"command": "GET_STATUS"})["worker_alive"] is False
    touch_runtime_heartbeat(conn)
    assert handle(conn, {"command": "GET_STATUS"})["worker_alive"] is True


def test_get_job_returns_aggregated_progress_only(conn):
    ref = create_job(conn, [SOURCE])
    job = handle(conn, {"command": "GET_JOB", "job_ref": ref})["job"]
    assert job["progress"] == {"done": 0, "total": 1, "percent": 0}
    assert "rows" not in job and "records" not in job     # never per-record data


def test_control_job_and_conflicts(conn):
    ref = create_job(conn, [SOURCE])
    # A QUEUED job is settled immediately — nothing is holding it.
    assert handle(conn, {"command": "CONTROL_JOB", "job_ref": ref,
                         "control": "cancel"})["job"]["status"] == "cancelled"
    assert handle(conn, {"command": "CONTROL_JOB", "job_ref": "job_nope"})["error"] == "not_found"


def test_job_logs_are_a_capped_tail(conn):
    ref = create_job(conn, [SOURCE])
    r = handle(conn, {"command": "GET_JOB_LOGS", "job_ref": ref, "limit": 10_000})
    assert r["ok"] and len(r["entries"]) <= 200


# ---- cursor pagination: one message is never a dataset ----------------------

def test_records_are_paginated_with_a_cursor(conn):
    _seed(conn, count=5)
    first = handle(conn, {"command": "GET_RECORDS", "source_key": SOURCE, "limit": 2})
    assert len(first["records"]) == 2 and first["total"] == 5
    assert first["next_cursor"] == 2

    second = handle(conn, {"command": "GET_RECORDS", "source_key": SOURCE,
                           "limit": 2, "cursor": first["next_cursor"]})
    assert len(second["records"]) == 2 and second["next_cursor"] == 4
    # different page, not the same rows again
    assert second["records"][0] != first["records"][0]


def test_last_page_reports_no_next_cursor(conn):
    _seed(conn, count=3)
    page = handle(conn, {"command": "GET_RECORDS", "source_key": SOURCE, "limit": 50})
    assert len(page["records"]) == 3 and page["next_cursor"] is None


def test_oversized_limit_is_capped(conn):
    _seed(conn, count=3)
    page = handle(conn, {"command": "GET_RECORDS", "source_key": SOURCE, "limit": 100_000})
    assert len(page["records"]) <= MAX_PAGE


def test_garbage_cursor_and_limit_do_not_crash(conn):
    _seed(conn, count=3)
    page = handle(conn, {"command": "GET_RECORDS", "source_key": SOURCE,
                         "limit": "lots", "cursor": "elsewhere"})
    assert page["ok"] and page["records"]


def test_visible_fields_projects_the_payload_down(conn):
    _seed(conn, count=1)
    page = handle(conn, {"command": "GET_RECORDS", "source_key": SOURCE,
                         "visible_fields": ["name", "effective_price"]})
    assert set(page["records"][0]) == {"name", "effective_price"}


def test_records_require_a_source_key(conn):
    assert handle(conn, {"command": "GET_RECORDS"})["error"] == "invalid"


# ---- status + changes --------------------------------------------------------

def test_status_lists_active_jobs(conn):
    create_job(conn, [SOURCE])
    r = handle(conn, {"command": "GET_STATUS"})
    assert r["ok"] and len(r["active_jobs"]) == 1


def test_changes_summary_over_the_bridge(conn):
    _seed(conn, count=1)
    r = handle(conn, {"command": "GET_CHANGES", "source_key": SOURCE})
    assert r["ok"] and r["summary"]["new"] >= 1


# ---- host manifest -----------------------------------------------------------

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
    monkeypatch.setattr(native, "_spawn_engine", lambda port: None)
    monkeypatch.setattr(native, "_START_CONFIRM_BUDGET_S", 0.05)

    r = handle(conn, {"command": "START_ENGINE"})

    assert r["ok"] and r["started"]
    assert r["confirmed"] is False


def test_start_engine_honours_a_requested_port(conn, monkeypatch):
    from scrapex import native

    seen = []
    monkeypatch.setattr(native, "_engine_listening", lambda port: (seen.append(port), True)[1])
    monkeypatch.setattr(native, "_spawn_engine", lambda port: None)

    r = handle(conn, {"command": "START_ENGINE", "port": 8077})

    assert seen == [8077] and r["port"] == 8077
