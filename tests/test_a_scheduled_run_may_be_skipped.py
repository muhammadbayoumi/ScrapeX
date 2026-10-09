"""A job may end `skipped`, and nothing treats it as running (#1596, step 1 of 5).

HIS RULING D4: a scheduled firing that finds its source already running, or the write
lock held by another app, is skipped and leaves a visible job row saying why. It fires
again at its next slot and never waits in a queue. That needs a status of its own, and
this file holds what the status must mean before anything writes it:

  * the warehouse accepts it -- fresh, and upgraded from v22 with every row kept;
  * it is TERMINAL: nothing resumes, cancels, pauses or reclaims it;
  * it is NOT BLOCKING: a skip occupies nothing, so it never makes the NEXT firing skip;
  * every copy of the terminal list -- the enrichment queries and the panel's two JS
    sets -- says the same thing as `vocab.TERMINAL_JOB_STATUSES`.

Integration tests run the real `db/engine/schema.sql` plus the shipped migrations.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex import scheduler
from scrapex.databases.domain import EngineDatabase
from scrapex.jobs import (
    _finish,
    create_job,
    get_job,
    list_jobs,
    reclaim_orphaned_jobs,
    set_control,
)
from scrapex.vocab import (
    BLOCKING_JOB_STATUSES,
    TERMINAL_JOB_STATUSES,
    WORKER_HELD_STATUSES,
    JobControl,
    JobStatus,
    LogLevel,
)

# It reads the panel's two terminal sets and its sprite, so an extension-only change runs it.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = "0023_a_scheduled_run_may_be_skipped.sql"
REASON = "skipped: a run is in progress (job_0a1b2c3d4e5f)"


@pytest.fixture()
def conn() -> sqlite3.Connection:
    connection = dbmod.connect(":memory:")
    dbmod.migrate(connection)
    yield connection
    connection.close()


def _skipped_job(conn: sqlite3.Connection, source_key: str = "MADAR") -> dict:
    ref = create_job(conn, [source_key])
    job = get_job(conn, ref)
    _finish(conn, job["job_id"], JobStatus.SKIPPED, REASON)
    return get_job(conn, ref)


# ---- the vocabulary ---------------------------------------------------------------

def test_skipped_is_terminal_and_holds_nothing():
    assert JobStatus.SKIPPED.value == "skipped"
    assert JobStatus.SKIPPED in TERMINAL_JOB_STATUSES
    assert JobStatus.SKIPPED.value not in BLOCKING_JOB_STATUSES, (
        "a skip would make the next firing of the same schedule skip too, for ever")
    assert JobStatus.SKIPPED.value not in WORKER_HELD_STATUSES


def test_no_status_is_both_terminal_and_blocking():
    """The two sets answer opposite questions; a status in both would be a finished job
    that blocks its source's schedule for good."""
    terminal = {status.value for status in TERMINAL_JOB_STATUSES}
    assert not terminal & BLOCKING_JOB_STATUSES, terminal & BLOCKING_JOB_STATUSES


# ---- the warehouse ----------------------------------------------------------------

def test_a_new_warehouse_accepts_skipped_and_still_refuses_a_made_up_status(conn):
    ref = create_job(conn, ["MADAR"], status=JobStatus.SKIPPED)
    assert get_job(conn, ref)["status"] == "skipped"
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE crawl_job SET status = 'skipping' WHERE job_ref = ?", (ref,))


def test_the_new_crawl_job_keeps_every_other_rule_it_had(conn):
    """The rebuild widened ONE CHECK. A job kind, run mode or control outside its list
    is still refused, and the index `/api/jobs` orders by is still there."""
    ref = create_job(conn, ["MADAR"])
    for column, value in (("job_kind", "not_a_kind"), ("run_mode", "sometimes"),
                          ("control", "stop")):
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(f"UPDATE crawl_job SET {column} = ? WHERE job_ref = ?",
                         (value, ref))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO crawl_job (job_ref, run_mode, source_keys)"
                     " VALUES (?, 'update', '[\"MADAR\"]')", (ref,))
    assert [r[2] for r in conn.execute("PRAGMA index_info('ix_crawl_job_status')")] \
        == ["status", "created_at"]


def test_a_warehouse_at_v22_upgrades_and_keeps_every_job_and_what_points_at_it(
        tmp_path, monkeypatch):
    """HIS warehouse holds jobs, and four tables point at them. Built the way the engine
    builds one: the stream stopped short of 0023, a job in EVERY status the old CHECK
    allowed, a log line and a run pointing at one -- then opened by this build."""
    db = EngineDatabase(tmp_path / "upgraded.db")
    whole = db._migrations
    at = [one.name for one in whole].index(MIGRATION)
    monkeypatch.setattr(db, "_migrations", whole[:at])
    db.initialize()
    old_statuses = [status.value for status in JobStatus if status is not JobStatus.SKIPPED]
    with db.connect() as before:
        with pytest.raises(sqlite3.IntegrityError):
            before.execute("INSERT INTO crawl_job (job_ref, run_mode, source_keys, status)"
                           " VALUES ('job_early', 'update', '[\"A\"]', 'skipped')")
        for index, status in enumerate(old_statuses):
            before.execute(
                "INSERT INTO crawl_job (job_ref, run_mode, source_keys, status, control,"
                " progress_done, progress_total, counters_json, checkpoint_json,"
                " started_at, finished_at, error_summary, job_kind, retry_count)"
                " VALUES (?, 'update', '[\"A\"]', ?, 'none', ?, 10, '{\"n\": 1}',"
                " '{\"page\": 2}', '2026-10-01T00:00:00Z', NULL, ?, 'profile_crawl', ?)",
                (f"job_{index:012d}", status, index, f"why {status}", index % 3))
        first = before.execute("SELECT job_id FROM crawl_job ORDER BY job_id").fetchone()[0]
        before.execute("INSERT INTO job_log_entry (job_id, level, message) VALUES (?, ?, ?)",
                       (first, LogLevel.INFO.value, "kept"))
        before.commit()
        rows_before = before.execute("SELECT * FROM crawl_job ORDER BY job_id").fetchall()
        logs_before = before.execute("SELECT * FROM job_log_entry").fetchall()
    assert len(rows_before) == len(old_statuses)

    monkeypatch.setattr(db, "_migrations", whole[:at + 1])
    assert db.initialize() == [whole[at].number]
    with db.connect() as after:
        assert after.execute("PRAGMA user_version").fetchone()[0] == whole[at].number
        assert [tuple(r) for r in after.execute(
            "SELECT * FROM crawl_job ORDER BY job_id")] == [tuple(r) for r in rows_before]
        assert [tuple(r) for r in after.execute("SELECT * FROM job_log_entry")] \
            == [tuple(r) for r in logs_before]
        # THE REFERENCES STILL NAME `crawl_job`, which is what `legacy_alter_table` is for.
        for table in ("change_event", "crawl_run", "job_log_entry",
                      "organization_enrichment_job"):
            targets = {r[2] for r in after.execute(f"PRAGMA foreign_key_list('{table}')")}
            assert "crawl_job" in targets, (table, targets)
            assert "crawl_job_old" not in targets, (table, targets)
        assert not after.execute(
            "SELECT 1 FROM sqlite_master WHERE name IN ('crawl_job_old', 'crawl_job_rebuilt')"
        ).fetchone()
        assert after.execute("SELECT 1 FROM sqlite_master WHERE type = 'index'"
                             " AND name = 'ix_crawl_job_status'").fetchone()
        assert not after.execute("PRAGMA foreign_key_check").fetchall()
        assert after.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        after.execute("UPDATE crawl_job SET status = 'skipped' WHERE job_id = ?", (first,))
        after.commit()


# ---- the engine -------------------------------------------------------------------

def test_finish_writes_a_skip_as_a_finished_job_with_its_reason(conn):
    job = _skipped_job(conn)
    assert job["status"] == "skipped"
    assert job["error_summary"] == REASON
    assert job["finished_at"], "a skip is finished the moment it is written"
    assert job["control"] == JobControl.NONE.value
    logged = conn.execute("SELECT level, message FROM job_log_entry WHERE job_id = ?",
                          (job["job_id"],)).fetchall()
    # INFO, NOT ERROR: nothing failed. `_finish` raises the level for FAILED alone.
    assert [tuple(r) for r in logged][-1] == (LogLevel.INFO.value, "job skipped")


@pytest.mark.parametrize("control", list(JobControl))
def test_nothing_resumes_pauses_or_cancels_a_skipped_job(conn, control):
    job = _skipped_job(conn)
    assert set_control(conn, job["job_ref"], control) is False
    again = get_job(conn, job["job_ref"])
    assert (again["status"], again["control"], again["finished_at"]) \
        == ("skipped", "none", job["finished_at"])


def test_a_skipped_job_is_not_listed_as_active(conn):
    skipped = _skipped_job(conn)
    queued = create_job(conn, ["MADAR"])
    active = [job["job_ref"] for job in list_jobs(conn, active_only=True)]
    assert active == [queued], active
    assert skipped["job_ref"] in [job["job_ref"] for job in list_jobs(conn)]


def test_the_orphan_sweep_leaves_a_skipped_job_alone(conn):
    job = _skipped_job(conn)
    reclaim_orphaned_jobs(conn)
    assert get_job(conn, job["job_ref"])["status"] == "skipped"


def test_a_skipped_job_does_not_make_its_source_busy(conn):
    """THE ONE THAT MATTERS FOR STEP 2. A skip that counted as busy would make the next
    firing of the same schedule skip as well, and every one after it."""
    _skipped_job(conn, "MADAR")
    assert scheduler._source_is_busy(conn, "MADAR") is False
    create_job(conn, ["MADAR"])
    assert scheduler._source_is_busy(conn, "MADAR") is True


# ---- every other copy of the terminal list -----------------------------------------

def _js_set(path: Path, name: str) -> set[str]:
    text = path.read_text(encoding="utf-8")
    found = re.search(rf"const {name} = new Set\(\[(.*?)\]\);", text, re.DOTALL)
    assert found, f"{path.name} no longer declares `{name}` where this test reads it"
    return set(re.findall(r'"([a-z_]+)"', found.group(1)))


@pytest.mark.parametrize(("path", "name"), [
    pytest.param(ROOT / "extension" / "jobsview.js", "SETTLED", id="jobs-page"),
    pytest.param(ROOT / "extension" / "enrichment.js", "TERMINAL", id="enrichment-page"),
])
def test_the_panels_terminal_sets_are_the_engines(path, name):
    """The panel cannot import `vocab.py`, so it carries copies. A copy missing a
    terminal status draws a finished job as live: the mini-player adopts it, the row
    offers Pause, and the page polls it for ever."""
    assert _js_set(path, name) == {status.value for status in TERMINAL_JOB_STATUSES}


def test_every_status_glyph_is_a_symbol_the_panel_carries():
    """`material-next-plan` was added to the sprite for `skipped`. A status glyph the
    sprite lacks draws an empty box, and no other guard reads `STATUS_LOOK`'s ids."""
    text = (ROOT / "extension" / "jobsview.js").read_text(encoding="utf-8")
    table = re.search(r"const STATUS_LOOK = \{(.*?)\n\};", text, re.DOTALL)
    assert table, "jobsview.js no longer declares STATUS_LOOK where this test reads it"
    glyphs = set(re.findall(r'\["(material-[a-z0-9-]+)"', table.group(1)))
    assert "material-next-plan" in glyphs
    for sprite in (ROOT / "extension" / "app.html", ROOT / "design" / "material-icons.svg"):
        carried = set(re.findall(r'<symbol id="([a-z0-9-]+)"', sprite.read_text(encoding="utf-8")))
        assert glyphs <= carried, (sprite.name, sorted(glyphs - carried))
