"""THE CHAOS TEST. Kill the engine mid-crawl and see what it says afterwards.

`ENGINEERING.md`'s test matrix (T7) names this and `REVIEW-2026-07-28` §9
recorded that it does not exist. `reclaim_orphaned_jobs` has unit tests — a
connection, a row, a call — and they cannot answer the only question that
matters: is that sweep actually reached when a real process is really killed?

WHY IT MATTERS MORE THAN IT LOOKS. `jobs.reclaim_orphaned_jobs` says it itself:

    Without this sweep a crash mid-crawl left a job 'running' forever, and
    `_source_is_busy` then blocked that source's schedules permanently with no
    error anywhere.

A source that silently stops being crawled, with nothing on any screen saying
so, is the worst failure this product has: the warehouse stops growing and every
page still says everything is fine.

This kills the engine with no chance to clean up — `Popen.kill()` is
TerminateProcess on Windows and SIGKILL elsewhere, so no handler, no `finally`,
no flush. The engine is then started again over the same database, and the job
must no longer claim to be running.
"""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Enough products, answered slowly enough, that the crawl is still in flight
# when the kill lands. A shop that answers instantly would finish before this
# test could stage the crash, and the test would pass without ever testing it.
SLOW_DETAIL_S = 0.6
PRODUCTS = [{"product_id": 200 + n, "product_enname": f"Slow Product {n}",
             "product_arname": f"منتج بطيء {n}", "price": 100 + n, "stock": 3}
            for n in range(12)]
BY_ID = {str(p["product_id"]): p for p in PRODUCTS}


class _SlowShop(BaseHTTPRequestHandler):
    def do_GET(self) -> None:                              # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/products":
            body = {"data": PRODUCTS, "pagination": {"totalPages": 1}}
        elif path.startswith("/api/products/"):
            time.sleep(SLOW_DETAIL_S)                      # the crawl's real cost
            body = BY_ID.get(path.rsplit("/", 1)[-1])
        else:
            body = None
        if body is None:
            self.send_error(404)
            return
        raw = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *_args) -> None:
        pass


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(url: str, timeout: float = 2.0):
    with urlopen(Request(url), timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _post(url: str, payload: dict, timeout: float = 10.0):
    request = Request(url, data=json.dumps(payload).encode("utf-8"),
                      headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _wait_for(predicate, seconds: float, what: str):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            result = predicate()
        except (URLError, OSError, TimeoutError):
            result = None
        if result:
            return result
        time.sleep(0.25)
    pytest.fail(f"timed out after {seconds}s waiting for {what}")


@pytest.fixture
def shop():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SlowShop)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def manifest(tmp_path, shop) -> Path:
    path = tmp_path / "sources.yaml"
    path.write_text(f"""
sources:
  - source_key: SLOWSHOP
    source_name: Slow Shop
    base_url: {shop}
    family: custom-json-api
    cadence: daily
    authority: shop
    active: true
    currency: EGP
    default_region: EG
    vat_mode: excl
    extract:
      - kind: product_prices
        scope: census
      - kind: enrichment
        scope: census
""", encoding="utf-8")
    return path


class Engine:
    """The engine as a process, because that is the only thing you can kill."""

    def __init__(self, manifest: Path, db: Path, port: int) -> None:
        self._db = str(db)
        self._args = [sys.executable, "-m", "scrapex.cli", "ui",
                      "--port", str(port), "--no-open", "--db", str(db)]
        self._env = dict(os.environ, SCRAPEX_SOURCES=str(manifest))
        self.url = f"http://127.0.0.1:{port}"
        self.process: subprocess.Popen | None = None

    def create_database(self) -> None:
        """`ui --db` REFUSES a path that does not exist, on purpose — it will not
        guess a database into being at a path someone mistyped. So the test makes
        it the way the owner's first run does, through the CLI."""
        made = subprocess.run(
            [sys.executable, "-m", "scrapex.cli", "init-db", "--db", self._db],
            cwd=str(ROOT), env=self._env, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=300)
        assert made.returncode == 0, f"init-db failed:\n{made.stdout}\n{made.stderr}"

    def start(self, *, swept: bool = False) -> None:
        """Start the engine. `swept` also waits for the orphan sweep to finish.

        OP-19, AND THE REASON THIS ARGUMENT EXISTS. Waiting for /api/health
        proves the HTTP thread is up and nothing else. The sweep that settles
        jobs left by a dead runtime happens on the WORKER thread, after it
        connects — so a test that read crawl_job.status straight after health
        was racing two threads and calling the result a verdict.

        Measured before the fix: three failures in four runs on a loaded Windows
        machine, and green every time on the Linux runner. That combination is
        the worst one available, because it reads as "works in CI, broken
        locally" and sends the reader looking at their own machine.

        NOT A SLEEP. The engine records when the sweep completed
        (jobs.RECLAIM_KEY); this waits for a marker written after the work,
        which cannot pass early on a fast machine or fail late on a slow one.
        """
        started = _reclaim_marker(self._db)
        self.process = subprocess.Popen(
            self._args, cwd=str(ROOT), env=self._env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        _wait_for(lambda: _get(f"{self.url}/api/health"), 90, "the engine to answer")
        if swept:
            _wait_for(lambda: _reclaim_marker(self._db) not in (None, started),
                      60, "the orphan sweep to finish")

    def kill(self) -> None:
        """No handler, no finally, no flush — TerminateProcess / SIGKILL."""
        if self.process and self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=30)


def _reclaim_marker(db: Path) -> str | None:
    """When this database last had its orphaned jobs swept, or None.

    Read straight from the database rather than through a new route: the engine
    already writes it, the test already opens the file read-only, and an HTTP
    endpoint would be a second thing to keep true.
    """
    if not Path(db).exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        row = conn.execute(
            "SELECT value FROM scrapex_meta WHERE key = 'orphans_reclaimed_at'"
        ).fetchone()
        return row[0] if row else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _job_status(db: Path, job_ref: str) -> str:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT status FROM crawl_job WHERE job_ref = ?",
                           (job_ref,)).fetchone()
    finally:
        conn.close()
    assert row, f"the job {job_ref} is not in the database at all"
    return row[0]


IN_FLIGHT = {"preparing", "running", "resuming"}


def test_a_killed_engine_does_not_leave_a_job_claiming_to_run(tmp_path, manifest):
    """The whole point, in one sentence: after a crash, nothing may still say
    'running' — because `_source_is_busy` reads exactly that, and a source stuck
    busy is a source that silently stops being crawled with no error anywhere."""
    db = tmp_path / "engine.db"
    engine = Engine(manifest, db, _free_port())
    engine.create_database()
    engine.start()
    try:
        job_ref = _post(f"{engine.url}/api/jobs", {"source_keys": ["SLOWSHOP"]})["job_ref"]

        _wait_for(lambda: _job_status(db, job_ref) in IN_FLIGHT, 60,
                  "the crawl to actually start")

        # The crash. Not a shutdown — the process is destroyed where it stands,
        # holding an open SQLite connection and a half-finished crawl.
        engine.kill()

        assert _job_status(db, job_ref) in IN_FLIGHT, (
            "the job settled before the kill landed, so this run proved nothing "
            "about a crash — the shop is answering faster than it is meant to")
    finally:
        engine.kill()

    # And now the part that matters: start again over the same database.
    survivor = Engine(manifest, db, _free_port())
    # The sweep is the thing under test here, so wait for IT rather than for
    # the port. See Engine.start's docstring (OP-19).
    survivor.start(swept=True)
    try:
        status = _job_status(db, job_ref)
        assert status not in IN_FLIGHT, (
            f"after a crash and a restart the job still says {status!r}. "
            "_source_is_busy reads this, so SLOWSHOP is now blocked from every "
            "future crawl and nothing anywhere says why")

        # It must also still be READABLE — a hard kill over an open connection
        # is where a corrupt database would show, and asking for the job list is
        # the first thing the panel does after a crash.
        listed = _get(f"{survivor.url}/api/jobs")
        assert isinstance(listed, (list, dict)), "the job list is unreadable"
    finally:
        survivor.kill()


def test_the_database_still_answers_after_the_kill(tmp_path, manifest):
    """A hard kill with the write-ahead log open must not cost the warehouse.

    Separate from the test above because it fails for a different reason and the
    owner would act on it differently: one is a stuck job, this is a lost
    database.
    """
    db = tmp_path / "engine.db"
    engine = Engine(manifest, db, _free_port())
    engine.create_database()
    engine.start()
    try:
        _post(f"{engine.url}/api/jobs", {"source_keys": ["SLOWSHOP"]})
        time.sleep(2.0)                      # let it get properly under way
    finally:
        engine.kill()

    conn = sqlite3.connect(str(db))
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok", (
            "the database did not survive the kill")
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        conn.close()
    assert "crawl_job" in tables, "the schema is gone after a crash"
