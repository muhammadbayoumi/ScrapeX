"""A job its SITE stopped ends `stopped_by_site`, never `failed` (#1772, his ruling (a)).

#1448 ruled that a site's block is a pause, not a failure, and the source keeps its pages
for Resume. A job whose only source was blocked still ended `failed`, because nothing in it
succeeded (`scrapex/jobs.py`, `succeeded == 0`). His ruling on #1772 gave it an ending of
its own. It is FINISHED, not held, because a held (`paused`) job makes that site's next
scheduled run skip (`scheduler.py`, D3 on #1596), and the ruling is that the site continues
from its kept pages on its next run.

These tests drive the real job runner on the real schema, with the same blocked connector
`tests/test_job_journal.py` built for #1448.
"""
from __future__ import annotations

import dataclasses
import sqlite3

import pytest

import scrapex.capture as capmod
from scrapex import localinbox, scheduler
from scrapex.connectors.base import CrawlBlocked, HostRefused, RobotsUnreachable
from scrapex.databases.domain import EngineDatabase
from scrapex.jobs import create_job, get_job, run_job_once
from scrapex.vocab import (
    BLOCKING_JOB_STATUSES,
    TERMINAL_JOB_STATUSES,
    WORKER_HELD_STATUSES,
    JobStatus,
)
from tests.test_job_journal import (  # noqa: F401  (fixtures are used by name)
    _PAGES,
    _BlockedConnector,
    _Fetcher,
    _PagedConnector,
    _with_connector,
    conn,
    journal,
    make_entry,
)

MIGRATION = "0027_a_site_may_stop_a_job.sql"


def _two_sources(monkeypatch, first, second):
    """GPP_ENERGY runs `first`, GPP_OTHER runs `second`; both on one manifest."""
    class _Other:
        """`second`, its pages relabelled as GPP_OTHER's."""
        skip_tokens: set = set()

        def fetch(self, entry):
            for table in second.fetch(entry):
                yield dataclasses.replace(table, source_key="GPP_OTHER")
    other_connector = _Other()
    other = make_entry().model_copy(update={"source_key": "GPP_OTHER"})
    connectors = {"GPP_ENERGY": first, "GPP_OTHER": other_connector}
    monkeypatch.setattr(capmod, "build_connector",
                        lambda entry, rules, crawl_settings=None:
                        (connectors[entry.source_key], _Fetcher()))
    return {"GPP_ENERGY": make_entry(), "GPP_OTHER": other}


class _RaisingConnector(_PagedConnector):
    """Serves nothing and raises `error` at once."""

    def __init__(self, error: Exception):
        super().__init__()
        self.error = error

    def fetch(self, entry):
        raise self.error
        yield  # pragma: no cover -- a generator, as the real ones are


# ---- the vocabulary ---------------------------------------------------------------

def test_stopped_by_site_is_finished_and_holds_nothing():
    assert JobStatus.STOPPED_BY_SITE.value == "stopped_by_site"
    assert JobStatus.STOPPED_BY_SITE in TERMINAL_JOB_STATUSES
    assert JobStatus.STOPPED_BY_SITE.value not in BLOCKING_JOB_STATUSES, (
        "a stopped job would make that site's next scheduled run skip, which is "
        "the run that continues from its kept pages")
    assert JobStatus.STOPPED_BY_SITE.value not in WORKER_HELD_STATUSES


# ---- the warehouse ----------------------------------------------------------------

def test_a_new_warehouse_accepts_stopped_by_site(conn):
    ref = create_job(conn, ["GPP_ENERGY"], status=JobStatus.STOPPED_BY_SITE)
    assert get_job(conn, ref)["status"] == "stopped_by_site"
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE crawl_job SET status = 'stopped' WHERE job_ref = ?", (ref,))


def test_a_warehouse_at_v26_upgrades_and_keeps_every_job_and_what_points_at_it(
        tmp_path, monkeypatch):
    """His warehouse holds 213 jobs and five tables point at them. Built the way the
    engine builds one -- the stream stopped short of 0027, a job in every status the
    old CHECK allowed, a log line pointing at one -- then opened by this build."""
    db = EngineDatabase(tmp_path / "upgraded.db")
    whole = db._migrations
    at = [one.name for one in whole].index(MIGRATION)
    monkeypatch.setattr(db, "_migrations", whole[:at])
    db.initialize()
    old_statuses = [s.value for s in JobStatus if s is not JobStatus.STOPPED_BY_SITE]
    with db.connect() as before:
        with pytest.raises(sqlite3.IntegrityError):
            before.execute("INSERT INTO crawl_job (job_ref, run_mode, source_keys, status)"
                           " VALUES ('job_early', 'update', '[\"A\"]', 'stopped_by_site')")
        for index, status in enumerate(old_statuses):
            before.execute(
                "INSERT INTO crawl_job (job_ref, run_mode, source_keys, status, control,"
                " progress_done, progress_total, counters_json, checkpoint_json,"
                " started_at, error_summary, job_kind, retry_count)"
                " VALUES (?, 'update', '[\"A\"]', ?, 'none', ?, 10, '{\"n\": 1}',"
                " '{\"page\": 2}', '2026-10-01T00:00:00Z', ?, 'profile_crawl', ?)",
                (f"job_{index:012d}", status, index, f"why {status}", index % 3))
        first = before.execute("SELECT job_id FROM crawl_job ORDER BY job_id").fetchone()[0]
        before.execute("INSERT INTO job_log_entry (job_id, level, message) VALUES (?, ?, ?)",
                       (first, "info", "kept"))
        before.commit()
        rows_before = before.execute("SELECT * FROM crawl_job ORDER BY job_id").fetchall()
        logs_before = before.execute("SELECT * FROM job_log_entry").fetchall()
    assert len(rows_before) == len(old_statuses)

    monkeypatch.setattr(db, "_migrations", whole[:at + 1])
    assert db.initialize() == [whole[at].number]
    with db.connect() as after:
        assert after.execute("PRAGMA user_version").fetchone()[0] == whole[at].number == 27
        assert [tuple(r) for r in after.execute(
            "SELECT * FROM crawl_job ORDER BY job_id")] == [tuple(r) for r in rows_before]
        assert [tuple(r) for r in after.execute("SELECT * FROM job_log_entry")] \
            == [tuple(r) for r in logs_before]
        # FIVE tables point at crawl_job since 0025; every one still names it.
        for table in ("change_event", "crawl_run", "job_log_entry",
                      "organization_enrichment_job", "fetched_responses"):
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
        after.execute("UPDATE crawl_job SET status = 'stopped_by_site' WHERE job_id = ?",
                      (first,))
        after.commit()


# ---- how a job ends ----------------------------------------------------------------

def test_a_job_whose_only_site_stopped_it_ends_stopped_by_site_not_failed(
        conn, journal, monkeypatch):
    """THE DEFECT. One source, its site blocks after two pages: this ended `failed`."""
    _with_connector(monkeypatch, _BlockedConnector())
    ref = create_job(conn, ["GPP_ENERGY"])

    job = run_job_once(conn, ref, {"GPP_ENERGY": make_entry()})

    assert job["status"] == JobStatus.STOPPED_BY_SITE.value
    assert job["error_summary"] is None, "a stop by the site is not an error"
    assert job["finished_at"], "it is finished, not held"
    assert localinbox.list_tokens(journal, "GPP_ENERGY") == {"DIESEL--EG", "DIESEL--SA"}


def test_the_stopped_sources_slot_says_what_stopped_it_and_what_it_kept(
        conn, journal, monkeypatch):
    """The panel draws the line from the engine's own words, never a cause it guessed:
    the slot carries the state, the kept pages and the sentence `stopped_because` made."""
    _with_connector(monkeypatch, _BlockedConnector())
    ref = create_job(conn, ["GPP_ENERGY"])

    job = run_job_once(conn, ref, {"GPP_ENERGY": make_entry()})

    slot = job["counters"]["sources"]["GPP_ENERGY"]
    assert slot["state"] == "stopped_by_site"
    assert slot["kept_pages"] == 2
    assert slot["stopped_because"] == (
        "blocked by the site (5 consecutive refusals (403) from x)")


def test_a_site_that_stops_one_of_two_leaves_the_job_partially_completed(
        conn, journal, monkeypatch):
    """The other source completed, so part of the job did: today's status, with no error
    summary, because the stopped site is not an error."""
    entries = _two_sources(monkeypatch, _BlockedConnector(), _PagedConnector())
    ref = create_job(conn, ["GPP_ENERGY", "GPP_OTHER"])

    job = run_job_once(conn, ref, entries)

    assert job["status"] == JobStatus.PARTIALLY_COMPLETED.value
    assert job["error_summary"] is None
    slots = job["counters"]["sources"]
    assert (slots["GPP_ENERGY"]["state"], slots["GPP_OTHER"]["state"]) \
        == ("stopped_by_site", "done")


def test_a_real_failure_beside_a_stop_still_reads_failed(conn, journal, monkeypatch):
    """A stop never hides an error: one source failed outright, the other was stopped,
    nothing succeeded, so the job failed and says why."""
    entries = _two_sources(monkeypatch, _BlockedConnector(),
                           _RaisingConnector(RuntimeError("the parser broke")))
    ref = create_job(conn, ["GPP_ENERGY", "GPP_OTHER"])

    job = run_job_once(conn, ref, entries)

    assert job["status"] == JobStatus.FAILED.value
    assert "the parser broke" in (job["error_summary"] or "")
    assert "blocked by the site" not in (job["error_summary"] or ""), (
        "the stop was written into the error summary as if it were an error")


def test_an_unreachable_robots_txt_stops_the_source_too(conn, journal, monkeypatch):
    """`RobotsUnreachable` is the site's state, not ours (ES-2): a stop, with its own
    sentence, not "blocked by the site"."""
    _with_connector(monkeypatch, _RaisingConnector(
        RobotsUnreachable("robots.txt at x answered 503")))
    ref = create_job(conn, ["GPP_ENERGY"])

    job = run_job_once(conn, ref, {"GPP_ENERGY": make_entry()})

    assert job["status"] == JobStatus.STOPPED_BY_SITE.value
    slot = job["counters"]["sources"]["GPP_ENERGY"]
    assert slot["stopped_because"] == "robots.txt at x answered 503"
    assert slot["kept_pages"] == 0


def test_a_host_scrapex_refuses_is_still_a_failure_not_a_stop(conn, journal, monkeypatch):
    """`HostRefused` is OURS, and a Continue would meet it again: it stays a failure."""
    _with_connector(monkeypatch, _RaisingConnector(HostRefused("x is on the refused list")))
    ref = create_job(conn, ["GPP_ENERGY"])

    job = run_job_once(conn, ref, {"GPP_ENERGY": make_entry()})

    assert job["status"] == JobStatus.FAILED.value
    assert job["counters"]["sources"]["GPP_ENERGY"]["state"] == "done"


def test_a_resumed_job_remembers_a_stop_from_before_its_pause(conn, journal, monkeypatch):
    """A stop survives a pause the way an error does: a job resumed after its first
    source was stopped must not end `completed`."""
    _with_connector(monkeypatch, _PagedConnector())
    ref = create_job(conn, ["GPP_ENERGY"], checkpoint={
        "completed_source_keys": ["GPP_GONE"], "errors": [], "succeeded": 0,
        "stopped_by_site": ["GPP_GONE"]})
    conn.execute("UPDATE crawl_job SET source_keys = '[\"GPP_GONE\", \"GPP_ENERGY\"]'"
                 " WHERE job_ref = ?", (ref,))
    conn.commit()

    job = run_job_once(conn, ref, {"GPP_ENERGY": make_entry()})

    assert job["status"] == JobStatus.PARTIALLY_COMPLETED.value


def test_a_clean_run_still_completes(conn, journal, monkeypatch):
    _with_connector(monkeypatch, _PagedConnector())
    ref = create_job(conn, ["GPP_ENERGY"])
    job = run_job_once(conn, ref, {"GPP_ENERGY": make_entry()})
    assert job["status"] == JobStatus.COMPLETED.value
    assert job["counters"]["sources"]["GPP_ENERGY"]["state"] == "done"


# ---- the schedule ------------------------------------------------------------------

def test_a_stopped_job_does_not_make_its_site_busy(conn, journal, monkeypatch):
    """THE REASON IT IS FINISHED AND NOT PAUSED: the next scheduled run of this site must
    fire, because that run is the one that continues from the kept pages."""
    _with_connector(monkeypatch, _BlockedConnector())
    run_job_once(conn, create_job(conn, ["GPP_ENERGY"]), {"GPP_ENERGY": make_entry()})
    assert scheduler._blocking_job(conn, "GPP_ENERGY") is None


def test_the_blocked_connector_still_serves_two_pages_before_its_block():
    """A guard on the fixture these tests share: if it stopped blocking, every test above
    would pass for the wrong reason."""
    connector = _BlockedConnector()
    with pytest.raises(CrawlBlocked):
        list(connector.fetch(make_entry()))
    assert connector.served == [token for token, _, _ in _PAGES[:2]]


# ---- continuing from the kept pages (#1449, his ruling 2026-10-25) ------------------

def _due(conn, key: str) -> None:
    from datetime import timedelta

    scheduler.upsert_schedule(conn, key, frequency="daily", run_at="00:00",
                              run_mode="update")
    conn.execute("UPDATE schedule SET next_run_at = ? WHERE source_key = ?",
                 ((scheduler.utcnow() - timedelta(seconds=30)).strftime(
                     "%Y-%m-%dT%H:%M:%SZ"), key))
    conn.commit()


def test_the_scheduled_run_after_a_stop_continues_from_the_kept_pages(
        conn, journal, monkeypatch):
    """THE RULING. It used to clear them (`capture.py`'s fresh-capture branch) and start
    from page 1; now the firing is seeded as the panel's Resume seeds it, and the site
    is asked only for what it refused."""
    _with_connector(monkeypatch, _BlockedConnector())
    run_job_once(conn, create_job(conn, ["GPP_ENERGY"]), {"GPP_ENERGY": make_entry()})
    _due(conn, "GPP_ENERGY")

    [ref] = scheduler.fire_due(conn)

    assert get_job(conn, ref)["checkpoint"].get("partial_source") == "GPP_ENERGY"
    second = _PagedConnector()
    _with_connector(monkeypatch, second)
    job = run_job_once(conn, ref, {"GPP_ENERGY": make_entry()})
    assert job["status"] == JobStatus.COMPLETED.value
    assert second.served == ["DIESEL--US"], "a page kept before the stop was refetched"


def test_a_scheduled_run_after_a_clean_run_starts_fresh(conn, journal, monkeypatch):
    """Only a SITE's stop is continued: the newest finished run decides."""
    _with_connector(monkeypatch, _PagedConnector())
    run_job_once(conn, create_job(conn, ["GPP_ENERGY"]), {"GPP_ENERGY": make_entry()})
    _due(conn, "GPP_ENERGY")

    [ref] = scheduler.fire_due(conn)

    assert "partial_source" not in (get_job(conn, ref)["checkpoint"] or {})


def test_a_stop_whose_pages_are_gone_starts_fresh(conn, journal, monkeypatch):
    """Nothing kept, nothing to continue: the journal answers, not the job row alone."""
    _with_connector(monkeypatch, _BlockedConnector())
    run_job_once(conn, create_job(conn, ["GPP_ENERGY"]), {"GPP_ENERGY": make_entry()})
    localinbox.clear(journal, "GPP_ENERGY")
    _due(conn, "GPP_ENERGY")

    [ref] = scheduler.fire_due(conn)

    assert "partial_source" not in (get_job(conn, ref)["checkpoint"] or {})


def _age_the_journal(journal, source_key: str, days: float) -> None:
    import os
    import time

    then = time.time() - days * 86400
    for page in (journal / source_key).glob("*.json"):
        os.utime(page, (then, then))


@pytest.mark.parametrize("days, warned", [(8, True), (6, False)])
def test_continuing_from_pages_kept_over_a_week_ago_advises_an_update(
        conn, journal, monkeypatch, days, warned):
    """Kept pages are never deleted for being old (his ruling): past 7 days the run says
    how old they are and advises an update. The pages are still continued from."""
    from scrapex.jobs import KEPT_PAGES_STALE_DAYS, job_logs

    assert KEPT_PAGES_STALE_DAYS == 7
    _with_connector(monkeypatch, _BlockedConnector())
    run_job_once(conn, create_job(conn, ["GPP_ENERGY"]), {"GPP_ENERGY": make_entry()})
    _age_the_journal(journal, "GPP_ENERGY", days)
    second = _PagedConnector()
    _with_connector(monkeypatch, second)
    ref = create_job(conn, ["GPP_ENERGY"], checkpoint={
        "completed_source_keys": [], "errors": [], "succeeded": 0,
        "partial_source": "GPP_ENERGY"})

    run_job_once(conn, ref, {"GPP_ENERGY": make_entry()})

    said = [e for e in job_logs(conn, ref) if "run an update" in e["message"]]
    assert bool(said) is warned, [e["message"] for e in job_logs(conn, ref)]
    if warned:
        assert said[0]["level"] == "warning"
        assert f"kept {days} days ago" in said[0]["message"]
    assert second.served == ["DIESEL--US"], "old pages were thrown away instead of kept"


class _FailsAfterTwo(_PagedConnector):
    """Two pages journaled, then OUR side breaks: a failure, not a stop by the site."""

    def fetch(self, entry):
        for index, table in enumerate(super().fetch(entry)):
            if index == 2:
                raise RuntimeError("the parser broke on page three")
            yield table


def test_a_scheduled_run_after_a_failure_that_left_pages_starts_fresh(
        conn, journal, monkeypatch):
    """Pages left by a FAILURE are the stale journal `capture.py` clears, not kept pages
    to continue from: only a stop by the site is continued, so the slot decides."""
    _with_connector(monkeypatch, _FailsAfterTwo())
    job = run_job_once(conn, create_job(conn, ["GPP_ENERGY"]), {"GPP_ENERGY": make_entry()})
    assert job["status"] == JobStatus.FAILED.value
    assert localinbox.list_tokens(journal, "GPP_ENERGY"), (
        "the guard needs pages left behind by the failure")
    _due(conn, "GPP_ENERGY")

    [ref] = scheduler.fire_due(conn)

    assert "partial_source" not in (get_job(conn, ref)["checkpoint"] or {})
