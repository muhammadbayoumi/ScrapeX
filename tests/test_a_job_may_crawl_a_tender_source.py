"""A sixth job kind: crawling a tender source (migration 0027), on the real migration stream.

Part 3b-2a of milestone 51. His word of 2026-10-24 (#1733): the tender job comes first,
on its own, with no route and no control; part 3b-2b gives it both. SQLite cannot alter
a CHECK, so the kind arrives as a rebuild of `crawl_job`, as `0017`-`0019` and `0023`
brought theirs.
"""
from __future__ import annotations

import sqlite3

import pytest

from scrapex import jobs
from scrapex.databases.domain import EngineDatabase

MIGRATION = "0027_a_job_may_crawl_a_tender_source.sql"

#: Every table that carries `REFERENCES crawl_job` at schema 26, measured on a warehouse
#: this stream built. 3b-1's `fetched_responses` is the fifth.
REFERRERS = {("change_event", "job_id"), ("crawl_run", "job_id"),
             ("job_log_entry", "job_id"), ("organization_enrichment_job", "job_id"),
             ("fetched_responses", "crawl_job_id")}


@pytest.fixture()
def conn(tmp_path):
    db = EngineDatabase(tmp_path / "scrapex-engine.db")
    db.initialize()
    connection = db.connect()
    yield connection
    connection.close()


def _referrers(conn) -> set[tuple[str, str]]:
    found = set()
    for (table,) in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'"):
        for key in conn.execute(f"PRAGMA foreign_key_list('{table}')"):
            if key[2] == "crawl_job":
                found.add((table, key[3]))
    return found


def test_a_tender_crawl_is_a_kind_the_warehouse_accepts(conn):
    job_ref = jobs.create_job(conn, ["worldbank_org"], "initial_crawl",
                              job_kind="tender_crawl")
    assert jobs.get_job(conn, job_ref)["job_kind"] == "tender_crawl"


def test_a_kind_nobody_registered_is_still_refused(conn):
    with pytest.raises(sqlite3.IntegrityError, match="CHECK"):
        conn.execute("INSERT INTO crawl_job (job_ref, run_mode, source_keys, job_kind) "
                     "VALUES ('j', 'update', '[]', 'tender_scrape')")


def test_only_the_kind_list_changes(tmp_path, monkeypatch):
    """Every column, type, NOT NULL and default as 0023 declared them, and the five tables
    that reference `crawl_job` still reference it: without `legacy_alter_table` the RENAME
    would point them at `crawl_job_old`, which is then dropped."""
    db = EngineDatabase(tmp_path / "before.db")
    whole = db._migrations
    at = [one.name for one in whole].index(MIGRATION)
    monkeypatch.setattr(db, "_migrations", whole[:at])
    db.initialize()
    with db.connect() as before:
        columns = [tuple(row) for row in before.execute("PRAGMA table_xinfo('crawl_job')")]
        indexes = sorted(row[1] for row in before.execute("PRAGMA index_list('crawl_job')"))
        assert _referrers(before) == REFERRERS
    monkeypatch.setattr(db, "_migrations", whole[:at + 1])
    assert db.initialize() == [whole[at].number]
    with db.connect() as after:
        assert [tuple(row) for row in after.execute("PRAGMA table_xinfo('crawl_job')")] == columns
        assert sorted(row[1] for row in after.execute("PRAGMA index_list('crawl_job')")) == indexes
        assert _referrers(after) == REFERRERS
        assert after.execute("PRAGMA foreign_key_check").fetchall() == []
        assert after.execute("SELECT count(*) FROM sqlite_master WHERE type = 'trigger' "
                             "AND tbl_name = 'crawl_job'").fetchone()[0] == 0


def test_a_warehouse_at_0026_keeps_every_job_and_what_points_at_it(tmp_path, monkeypatch):
    db = EngineDatabase(tmp_path / "upgraded.db")
    whole = db._migrations
    at = [one.name for one in whole].index(MIGRATION)
    monkeypatch.setattr(db, "_migrations", whole[:at])
    db.initialize()
    with db.connect() as before:
        ref = jobs.create_job(before, ["muqawil_org"], "update", job_kind="directory_crawl",
                              checkpoint={"resume_run_ref": "run-7"})
        job_id = jobs.get_job(before, ref)["job_id"]
        jobs.append_log(before, job_id, "a line written before the upgrade")
        before.execute("INSERT INTO fetched_responses (target_uri, status_code, content_type, "
                       "headers, body, body_sha256, body_codec, crawl_job_id) "
                       "VALUES ('https://x', 200, 'application/json', '{}', x'00', ?, "
                       "'zstd', ?)", ("0" * 64, job_id))
        before.commit()
        row = dict(before.execute("SELECT * FROM crawl_job WHERE job_id = ?",
                                  (job_id,)).fetchone())
    monkeypatch.setattr(db, "_migrations", whole[:at + 1])
    db.initialize()
    with db.connect() as after:
        assert dict(after.execute("SELECT * FROM crawl_job WHERE job_id = ?",
                                  (job_id,)).fetchone()) == row
        assert after.execute("SELECT message FROM job_log_entry WHERE job_id = ?",
                             (job_id,)).fetchone()[0] == "a line written before the upgrade"
        assert after.execute("SELECT crawl_job_id FROM fetched_responses").fetchone()[0] == job_id
        assert after.execute("PRAGMA foreign_key_check").fetchall() == []
