"""A held write lock answers 409 on every write route, not an unhandled failure.

Eighteen of the twenty-one `write_lock` sites in `scrapex/webui/app.py` had no
catch of their own -- `POST /api/storage/restore` and `POST /api/storage/start-fresh`
among them -- so ordinary contention, another app holding the single write
permission, reached the panel as a server fault about a database that was
working perfectly.

THESE TESTS HOLD THE REAL LOCK: real lock file, real in-process gate, real
refusal. A fake `DbLockedError` would pass against a handler registered for the
wrong exception, which is the one mistake this guard exists to catch.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex import db as dbmod  # noqa: E402
from scrapex.webui.app import create_app  # noqa: E402

# THE MARK, because the docstring below cites `extension/backend.js`. This file
# reads no extension source, and the gate is deliberately broad about that:
# "a false positive costs one marker, a false negative costs a guard nobody
# notices is gone" (tests/test_the_extension_gate_is_complete.py:42).
pytestmark = pytest.mark.extension

#: A source_key the repository's own manifest carries, for the one route whose
#: refusal must keep its own sentence.
A_REAL_SOURCE = "ELSEWEDYSHOP"


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    path = tmp_path / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def client(db_path: Path) -> TestClient:
    return TestClient(create_app(db_path))


@contextmanager
def lock_held(db_path: Path, monkeypatch: pytest.MonkeyPatch, timeout_s: float = 0.3):
    """Hold the write lock in another thread, and let a route give up quickly.

    ONLY THE TIMEOUT IS PATCHED. The default is 10 s (`scrapex/db.py`), which is
    correct for a product waiting on a crawl and is ten seconds per test here.
    Everything else -- the lock file, the gate, the exception -- is the
    product's own.
    """
    real = dbmod.write_lock

    def impatient(path, timeout_s=timeout_s):
        return real(path, timeout_s=timeout_s)

    monkeypatch.setattr(dbmod, "write_lock", impatient)

    holding = threading.Event()
    release = threading.Event()
    refused: list[BaseException] = []

    def hold():
        try:
            with real(db_path):
                holding.set()
                release.wait(30)
        except Exception as exc:          # the assertion below reports it
            refused.append(exc)
            holding.set()

    holder = threading.Thread(target=hold, name="lock-holder", daemon=True)
    holder.start()
    assert holding.wait(10), "the holder never took the lock"
    assert not refused, f"the holder could not take the lock: {refused}"
    try:
        yield
    finally:
        release.set()
        holder.join(30)
        assert not holder.is_alive(), "the holder never released the lock"


def test_the_lock_is_really_held_while_the_routes_are_asked(db_path, monkeypatch):
    """The precondition, stated as a test: without it every case below passes vacuously."""
    lock_path = Path(str(db_path) + ".lock")
    assert not lock_path.exists(), "an idle engine holds nothing"
    with lock_held(db_path, monkeypatch):
        assert lock_path.exists()
    assert not lock_path.exists()


def test_a_settings_save_against_a_held_lock_is_409_not_a_server_fault(
        client, db_path, monkeypatch):
    """`POST /api/settings` is one of the eighteen with no catch of its own."""
    with lock_held(db_path, monkeypatch):
        response = client.post("/api/settings", json={})
    assert response.status_code == 409, response.text


def test_the_refusal_carries_the_engines_own_words_where_the_panel_reads_them(
        client, db_path, monkeypatch):
    """`detail`, because that is the field the panel renders.

    `extension/backend.js:156-158` reads `(await res.json()).detail` and throws
    it as the message. A refusal with the right status and no `detail` reaches
    him as the bare status text.
    """
    with lock_held(db_path, monkeypatch):
        response = client.post("/api/settings", json={})
    body = response.json()
    assert body["ok"] is False
    assert body["error"] == "database_busy"
    assert "writing to the database" in body["detail"]


def test_it_is_the_handler_and_not_one_route(client, db_path, monkeypatch):
    """A second route with no catch of its own answers the same way."""
    with lock_held(db_path, monkeypatch):
        response = client.post("/api/retention/prune", json={"before_date": "2020-01-01"})
    assert response.status_code == 409, response.text
    assert response.json()["error"] == "database_busy"


def test_a_route_that_already_caught_it_keeps_its_own_sentence(
        client, db_path, monkeypatch):
    """`/api/capture` is one of the three that answered correctly already.

    Its sentence is not the handler's, and this pins that: registering a global
    handler must not quietly restate a refusal a route words for itself.
    """
    with lock_held(db_path, monkeypatch):
        response = client.post("/api/capture", json={"source_key": A_REAL_SOURCE})
    assert response.status_code == 409, response.text
    assert response.json()["detail"] == (
        "a crawl is already running — try again shortly")


def test_the_refusal_is_retryable_and_the_route_works_once_the_lock_is_free(
        client, db_path, monkeypatch):
    """The whole point of 409 rather than 500: pressing again is the remedy."""
    with lock_held(db_path, monkeypatch):
        assert client.post("/api/settings", json={}).status_code == 409
    after = client.post("/api/settings", json={})
    assert after.status_code == 200, after.text
    assert "settings" in after.json()
