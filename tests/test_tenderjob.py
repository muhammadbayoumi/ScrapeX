"""The tender crawl job (milestone 51, part 3b-2a), on the real migration stream.

Nothing reaches the network: the job's fetcher is the collector tests' `Bank`, which
answers from #1647's recorded responses. His rulings of 2026-10-24 decide what is checked
here: the job keeps its record in its own row (#1733), and a pass over changes starts from
the first count, or from the last complete pass, less one day (#1701).
"""
from __future__ import annotations

import dataclasses
import json
import sqlite3
import threading
import time
from contextlib import contextmanager

import httpx
import pytest
from test_worldbank_collector import CHANGES, EGYPT, Bank, changes, count, notices, stamped

from scrapex import (
    capture,
    catalog,
    jobs,
    source_settings,
    storage,
    tenderjob,
    tenders,
    tenderstore,
)
from scrapex import db as dbmod
from scrapex.catalog_models import SiteCreate
from scrapex.connectors.base import HostRefused, RobotsUnreachable
from scrapex.databases.domain import EngineDatabase
from scrapex.sites import worldbank_collect as wc
from scrapex.vocab import JobStatus

KENYA = "Kenya"
#: What a run says about what it refused, and what every later run then does (his choice of
#: 2026-11-01): tested by running them, below.
LATER = ("and a later run reads a refused notice again only if the Ban"
         "k changes it or its area is still unread.")
NOW = "2026-10-13T08:00:00Z"
#: One day before NOW: where the first pass over changes starts (his ruling, #1701).
SINCE = "2026-10-12T08:00:00Z"


@pytest.fixture()
def conn(tmp_path, monkeypatch):
    db = EngineDatabase(tmp_path / "scrapex-engine.db")
    db.initialize()
    connection = db.connect()
    monkeypatch.setattr(tenderjob, "utc_now_iso", lambda: NOW)
    yield connection
    connection.close()


@pytest.fixture()
def bank(monkeypatch):
    """The Bank the job reads. Set `.areas` / `.changed` / failures on it per test."""
    holder = {"bank": Bank({EGYPT: notices(1_200), KENYA: notices(300, start=5_000)})}
    monkeypatch.setattr(tenderjob, "source_fetcher", lambda rules, settings: holder["bank"])
    return holder


@pytest.fixture(autouse=True)
def a_wait_that_cannot_end_fails(monkeypatch):
    """The runner waits as long as another app holds the warehouse, so a wait broken to never end
    would hang CI for its 30 minutes and name no test. An honest wait here costs at least the 10 ms
    these tests set, and no holder outlasts 0.5 s, so this count is out of its reach."""
    waits = []

    def said(*args, **kwargs):
        waits.append(args)
        assert len(waits) < 5_000, f"this wait cannot end: {args[0]}"
        print(*args, **kwargs)

    monkeypatch.setattr(tenderjob, "print", said, raising=False)


def run(conn, mode="initial_crawl"):
    job_ref = jobs.create_job(conn, ["worldbank_org"], mode, job_kind=tenderjob.JOB_KIND)
    return tenderjob.run_tender_crawl_job_once(conn, job_ref), job_ref


def logged(conn, job_ref) -> list[tuple[str, str]]:
    return [(row["level"], row["message"]) for row in jobs.job_logs(conn, job_ref)]


# ---- a first crawl ----------------------------------------------------------------------

def test_a_first_crawl_reads_every_area_largest_first_and_keeps_its_record(conn, bank):
    job, ref = run(conn)
    assert job["status"] == "completed"
    assert [call.get(wc.AREA_FACET) for call in bank["bank"].calls[1:]] == [EGYPT, EGYPT, KENYA]
    assert count(conn, "tender_releases") == 1_500
    lines = [message for _, message in logged(conn, ref)]
    assert lines[0] == "counted 1,500 notices in 2 areas: 4 requests"
    assert f"{EGYPT}: 1,200 notices in 2 requests" in lines
    assert f"{KENYA}: 300 notices in 1 request" in lines
    record = job["checkpoint"]
    assert record["areas_read"] == [EGYPT, KENYA] and record["unread"] == {}
    assert record["count"] == {"counted_at": NOW, "total": 1_500, "requests": 4,
                               "unlisted": 0, "areas": [[EGYPT, 1_200], [KENYA, 300]]}
    assert record["first_counted_at"] == NOW
    assert (job["progress_done"], job["progress_total"]) == (2, 2)
    assert {k: job["counters"][k] for k in tenderjob.COUNTERS} == {
        "requests": 4, "notices": 1_500, "releases_new": 1_500, "releases_unchanged": 0,
        "errors": 0, "pages_refused": 0}
    # An initial crawl reads no changes: the next update does, from the count.
    assert "changes" not in record


def test_notices_in_no_area_are_named_and_the_crawl_starts(conn, bank):
    """His ruling of 2026-10-25 (#1647): the count line stays the confirmed one, and a
    warning beside it names what no area pass can read."""
    bank["bank"].facets["total"] = str(int(bank["bank"].facets["total"]) + 30)
    job, ref = run(conn)
    assert job["status"] == "completed"
    assert ("warning", "30 notices the Bank lists in no area: an area pass cannot read them, "
                       "and the pass over changes reads each one when it changes"
            ) in logged(conn, ref)
    assert job["checkpoint"]["count"]["unlisted"] == 30


def test_the_site_is_registered_when_absent_and_left_alone_when_present(conn, bank):
    catalog.register_site(conn, SiteCreate(site_key="worldbank_org",
                                           display_name="Registered by hand",
                                           base_url="https://search.worldbank.org/x"))
    conn.commit()
    run(conn)
    assert tuple(conn.execute("SELECT count(*), max(source_name) FROM source_site WHERE "
                              "source_key = 'worldbank_org'").fetchone()) == (
        1, "Registered by hand")


def test_an_area_that_fails_is_left_unread_and_named_first(conn, bank):
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(300, start=5_000)},
                        fail={(EGYPT, 1000): 503})
    job, ref = run(conn)
    assert job["status"] == "completed_with_errors"
    summary = (f"1 area not read; an update reads it first. {EGYPT}, page 2: HTTP 503 "
               "after its tries.")
    assert job["error_summary"] == summary and logged(conn, ref)[-1] == ("warning", summary)
    assert job["checkpoint"]["areas_read"] == [KENYA]
    assert job["checkpoint"]["unread"] == {EGYPT: f"{EGYPT}, page 2: HTTP 503 after its tries"}


def test_refused_notices_never_stop_the_crawl_and_end_it_with_errors(conn, bank):
    """His ruling of 2026-10-25 (#1779): a page whose every notice is refused goes on with
    a warning; the run ends completed with errors, counting the notices it did not keep."""
    kenya = notices(300, start=5_000)
    for notice in kenya:
        notice["notice_type"] = "Prequalification Notice"
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: kenya})
    job, ref = run(conn)
    assert job["status"] == "completed_with_errors"
    assert job["error_summary"] == f"300 refusals, {LATER} Each is named in the log by its id."
    assert job["checkpoint"]["areas_read"] == [EGYPT, KENYA]
    assert any(level == "warning" and message.startswith(f"every notice on {KENYA}, page 1")
               for level, message in logged(conn, ref))


def test_unread_areas_lead_the_summary_and_refused_notices_follow(conn, bank):
    egypt = notices(1_200)
    egypt[0]["notice_type"] = "Prequalification Notice"
    bank["bank"] = Bank({EGYPT: egypt, KENYA: notices(300, start=5_000)},
                        fail={(KENYA, 0): 503})
    job, _ = run(conn)
    assert job["status"] == "completed_with_errors"
    assert job["error_summary"] == (f"1 area not read; an update reads it first. {KENYA}, "
                                    f"page 1: HTTP 503 after its tries. 1 refusal, {LATER} It "
                                    "is named in the log by its id.")


# ---- an update ---------------------------------------------------------------------------

def test_an_update_reads_the_unread_areas_first_then_the_changes_from_the_count(conn, bank):
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(300, start=5_000)},
                        fail={(EGYPT, 1000): 503})
    run(conn)
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(300, start=5_000)},
                        changed=stamped(notices(3, start=9_000),
                                        ["2026-10-12T09:00:00Z", "2026-10-12T08:30:00Z",
                                         "2026-10-01T00:00:00Z"]))
    job, ref = run(conn, "update")
    assert job["status"] == "completed"
    lines = [message for _, message in logged(conn, ref)]
    # The count and Egypt's two pages: one figure with the cost question (#1701, 13a).
    assert lines[0] == "1 area not read yet: 3 requests"
    assert f"every area read; reading the notices changed since {SINCE}" in lines
    assert "changes: 2 notices in 1 request" in lines
    record = job["checkpoint"]
    assert record["areas_read"] == [EGYPT]
    assert record["changes"]["since"] == SINCE and record["changes"]["complete"]
    assert record["changes"]["held_whole_at"] == wc.newest_held(
        conn, conn.execute("SELECT source_id FROM source_site").fetchone()[0])
    assert (job["progress_done"], job["progress_total"]) == (1, 0)


def test_the_next_update_starts_a_day_before_the_last_complete_pass_ended(conn, bank):
    run(conn)
    bank["bank"].changed = stamped(notices(1, start=9_000), ["2026-10-12T09:00:00Z"])
    first, _ = run(conn, "update")
    held = first["checkpoint"]["changes"]["held_whole_at"]
    second, ref = run(conn, "update")
    assert second["checkpoint"]["changes"]["since"] == tenderjob.SourceState(
        count=None, areas_read=frozenset(), first_counted_at=None,
        held_whole_at=held).since()
    assert next(m for _, m in logged(conn, ref)).startswith(
        "every area read; reading the notices changed since ")


def test_a_pass_cut_short_leaves_the_next_one_starting_where_it_did(conn, bank):
    run(conn)
    bank["bank"].changed = changes(2_500)
    bank["bank"].fail = {(CHANGES, 1000): 503}
    cut, _ = run(conn, "update")
    assert cut["status"] == "completed_with_errors"
    assert cut["checkpoint"]["changes"]["complete"] is False
    assert cut["checkpoint"]["changes"]["held_whole_at"] is None
    assert cut["error_summary"] == (f"the pass over changes stopped: changes, page 2: HTTP 503 "
                                    f"after its tries. The next update reads again from {SINCE}.")
    again, _ = run(conn, "update")
    assert again["checkpoint"]["changes"]["since"] == SINCE


def test_an_initial_crawl_of_a_source_held_whole_reads_no_changes(conn, bank):
    run(conn)
    bank["bank"].changed = changes(3)
    job, _ = run(conn)
    assert job["status"] == "completed" and "changes" not in job["checkpoint"]
    assert [call.get("fct") for call in bank["bank"].calls[-1:]] == [wc.AREA_FACET]


# ---- the state, read from every job's record ------------------------------------------------

def test_the_source_state_is_the_union_of_its_jobs_records(conn, bank):
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(300, start=5_000)},
                        fail={(EGYPT, 1000): 503})
    run(conn)
    state = tenderjob.source_state(conn, "worldbank_org")
    assert state.areas_read == {KENYA} and state.first_counted_at == NOW
    assert state.held_whole_at is None and state.since() == SINCE
    assert tenderjob.source_state(conn, "another_source") == tenderjob.SourceState(
        count=None, areas_read=frozenset(), first_counted_at=None, held_whole_at=None)
    assert tenderjob.SourceState(None, frozenset(), None, None).since() is None


@pytest.mark.parametrize("record, says", [
    ("[]", "not an object"),
    ('{"areas_read": "Egypt"}', "areas_read is not a list"),
    ('{"count": {"areas": []}}', "no counted_at or areas"),
])
def test_a_record_not_in_its_shape_is_refused_by_name(conn, record, says):
    ref = jobs.create_job(conn, ["worldbank_org"], "update", job_kind=tenderjob.JOB_KIND)
    conn.execute("UPDATE crawl_job SET checkpoint_json = ? WHERE job_ref = ?", (record, ref))
    conn.commit()
    with pytest.raises(ValueError, match=f"{ref}: .*{says}"):
        tenderjob.source_state(conn, "worldbank_org")


# ---- Pause, Cancel, and a site that stops -----------------------------------------------------

def _control_after(bank, conn, ref_box, control, at_offset):
    real = bank.get

    def get(url, params=None, **kw):
        response = real(url, params=params, **kw)
        if params.get("os") == str(at_offset) and wc.AREA_FACET in params:
            jobs.set_control(conn, ref_box[0], control)
        return response

    bank.get = get


def test_a_pause_stops_between_pages_and_a_resume_goes_on_from_the_next(conn, bank,
                                                                        monkeypatch):
    ref = jobs.create_job(conn, ["worldbank_org"], "initial_crawl",
                          job_kind=tenderjob.JOB_KIND)
    conn.execute("UPDATE crawl_job SET status = 'running' WHERE job_ref = ?", (ref,))
    conn.commit()
    _control_after(bank["bank"], conn, [ref], "pause", 0)
    paused = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert paused["status"] == "paused"
    assert paused["checkpoint"]["area"] == {"name": EGYPT, "next_page": 1, "count": 1_200}
    assert count(conn, "tender_releases") == 1_000 and not conn.in_transaction
    assert jobs.set_control(conn, ref, "resume")
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(300, start=5_000)})
    monkeypatch.setattr(tenderjob, "utc_now_iso", lambda: "2026-10-14T08:00:00Z")
    done = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert done["status"] == "completed" and count(conn, "tender_releases") == 1_500
    # The resume counted again and read Egypt's page 2 onward, never its page 1 again.
    assert [c.get("os") for c in bank["bank"].calls if wc.AREA_FACET in c and "fct" not in c] \
        == ["1000", "0"]
    # The first count's time is kept, though the resume counted again a day later: the
    # first pass over changes still starts from when the crawl began.
    assert done["checkpoint"]["first_counted_at"] == NOW
    assert done["checkpoint"]["count"]["counted_at"] == "2026-10-14T08:00:00Z"
    assert tenderjob.source_state(conn, "worldbank_org").since() == SINCE


def test_a_cancel_stops_between_pages_and_keeps_what_was_kept(conn, bank):
    ref = jobs.create_job(conn, ["worldbank_org"], "initial_crawl",
                          job_kind=tenderjob.JOB_KIND)
    conn.execute("UPDATE crawl_job SET status = 'running' WHERE job_ref = ?", (ref,))
    conn.commit()
    _control_after(bank["bank"], conn, [ref], "cancel", 0)
    job = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert job["status"] == "cancelled" and count(conn, "tender_releases") == 1_000
    assert not conn.in_transaction
    assert ("info", "cancelled between pages. What was kept stays kept, and an update reads "
                    "the rest") in logged(conn, ref)


def test_a_job_something_else_settled_is_not_settled_again(conn, bank):
    """The row outranks the instruction: a job another path already failed stays failed."""
    ref = jobs.create_job(conn, ["worldbank_org"], "initial_crawl",
                          job_kind=tenderjob.JOB_KIND)
    real = bank["bank"].get

    def get(url, params=None, **kw):
        response = real(url, params=params, **kw)
        if params.get("os") == "0" and wc.AREA_FACET in params:
            job_id = jobs.get_job(conn, ref)["job_id"]
            jobs._finish(conn, job_id, jobs.JobStatus.FAILED, "settled elsewhere")
            conn.commit()
        return response

    bank["bank"].get = get
    job = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert (job["status"], job["error_summary"]) == ("failed", "settled elsewhere")
    assert ("info", "stopped between pages: this job is already settled, so nothing more "
                    "is read") in logged(conn, ref)


def test_each_page_of_changes_is_one_line_and_the_pass_one_more(conn, bank):
    run(conn)
    bank["bank"].changed = stamped(notices(1_500, start=9_000), ["2026-10-12T09:00:00Z"] * 1_500)
    job, ref = run(conn, "update")
    lines = [message for _, message in logged(conn, ref)]
    at = lines.index(f"every area read; reading the notices changed since {SINCE}")
    assert lines[at + 1:at + 4] == ["changes, page 1: 1,000 notices",
                                    "changes, page 2: 500 notices",
                                    "changes: 1,500 notices in 2 requests"]
    assert (job["progress_done"], job["progress_total"]) == (2, 0)


def test_a_site_that_stops_answering_pauses_the_job(conn, bank):
    bank["bank"] = Bank({EGYPT: notices(1_200)},
                        raise_at={(EGYPT, 1000): RobotsUnreachable("robots.txt timed out")})
    job, ref = run(conn)
    assert job["status"] == "paused"
    assert any(level == "warning" and message.startswith("paused: ")
               for level, message in logged(conn, ref))


# ---- what a tender crawl refuses ---------------------------------------------------------------

@pytest.mark.parametrize("mode", ["full_rebuild", "history_backfill"])
def test_a_mode_a_tender_crawl_does_not_run_is_refused_before_any_request(conn, bank, mode):
    ref = jobs.create_job(conn, ["worldbank_org"], mode, job_kind=tenderjob.JOB_KIND)
    with pytest.raises(ValueError, match="the history keeps every notice it read"):
        tenderjob.run_tender_crawl_job_once(conn, ref)
    assert bank["bank"].requests_count == 0


def test_a_job_of_another_kind_or_two_sources_or_an_unknown_source_is_refused(conn, bank):
    other = jobs.create_job(conn, ["muqawil_org"], "update", job_kind="directory_crawl")
    with pytest.raises(ValueError, match="not a 'tender_crawl'"):
        tenderjob.run_tender_crawl_job_once(conn, other)
    two = jobs.create_job(conn, ["worldbank_org", "x"], "update", job_kind=tenderjob.JOB_KIND)
    with pytest.raises(ValueError, match="exactly one source"):
        tenderjob.run_tender_crawl_job_once(conn, two)
    unknown = jobs.create_job(conn, ["worldbank"], "update", job_kind=tenderjob.JOB_KIND)
    with pytest.raises(KeyError, match="not a tender source"):
        tenderjob.run_tender_crawl_job_once(conn, unknown)
    assert bank["bank"].requests_count == 0


def test_a_settled_job_is_returned_untouched(conn, bank):
    ref = jobs.create_job(conn, ["worldbank_org"], "update", job_kind=tenderjob.JOB_KIND)
    jobs.set_control(conn, ref, "cancel")
    assert tenderjob.run_tender_crawl_job_once(conn, ref)["status"] == "cancelled"
    assert bank["bank"].requests_count == 0




def test_the_job_is_registered_for_the_runner(conn):
    assert jobs.runner_for(tenderjob.JOB_KIND) is tenderjob.run_tender_crawl_job_once


def test_the_record_is_json_the_warehouse_can_read(conn, bank):
    _, ref = run(conn)
    raw = conn.execute("SELECT checkpoint_json FROM crawl_job WHERE job_ref = ?",
                       (ref,)).fetchone()[0]
    assert conn.execute("SELECT json_valid(?)", (raw,)).fetchone()[0] == 1
    assert json.loads(raw)["areas_read"] == [EGYPT, KENYA]


def test_a_count_not_in_its_measured_shape_fails_the_job(conn, bank):
    bank["bank"].facets = {"rows": 0}
    with pytest.raises(wc.PageShapeError):
        run(conn)
    assert conn.execute("SELECT status FROM crawl_job").fetchone()[0] == "failed"


# ---- the gate of #1802: the write lock, his ruling of 2026-10-31 (#1775) ---------------------

def test_a_page_is_written_inside_the_write_lock_and_read_outside_it(conn, bank, monkeypatch):
    """`CLAUDE.md`: one writer at a time. Measured by the gate: without it the job committed 7
    pages inside another process's lock, and pages into a warehouse sealed under it."""
    depth = [0]
    held_at_store, held_at_fetch = [], []
    real_lock = dbmod.write_lock

    @contextmanager
    def lock(path, *args, **kwargs):
        assert str(path) == conn.execute("PRAGMA database_list").fetchone()[2]
        with real_lock(path, *args, **kwargs):
            depth[0] += 1
            try:
                yield
            finally:
                depth[0] -= 1

    monkeypatch.setattr(tenderjob.dbmod, "write_lock", lock)
    real_store = tenderstore.store_response
    monkeypatch.setattr(tenderstore, "store_response",
                        lambda c, **kw: (held_at_store.append(depth[0]), real_store(c, **kw))[1])
    real_get = bank["bank"].get
    bank["bank"].get = lambda url, params=None, **kw: (held_at_fetch.append(depth[0]),
                                                       real_get(url, params=params, **kw))[1]
    job, _ = run(conn)
    assert job["status"] == "completed"
    assert held_at_store == [1, 1, 1] and set(held_at_fetch) == {0}
    held_at_store.clear()
    bank["bank"].changed = changes(3)
    run(conn, "update")
    assert held_at_store == [1] and set(held_at_fetch) == {0}


def test_a_page_waits_for_a_real_holder_of_the_write_lock(conn, bank, monkeypatch):
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    entered, released = threading.Event(), []

    def holder():
        with dbmod.write_lock(path):
            entered.set()
            time.sleep(0.4)
            released.append(time.monotonic())

    thread = threading.Thread(target=holder)
    thread.start()
    entered.wait()
    stored = []
    real_store = tenderstore.store_response
    monkeypatch.setattr(tenderstore, "store_response",
                        lambda c, **kw: (stored.append(time.monotonic()), real_store(c, **kw))[1])
    job, _ = run(conn)
    thread.join()
    assert job["status"] == "completed" and stored[0] >= released[0]


def test_a_warehouse_sealed_under_the_crawl_keeps_nothing_after_the_seal(conn, bank):
    """`capture._refuse_if_superseded`: a crawl that began before a compaction must not write
    into the sealed archive. Read inside the lock, where the answer cannot go stale."""
    conn.execute("INSERT INTO scrapex_meta (key, value) VALUES (?, ?)",
                 (storage.SEALED_KEY, "2026-10-31T00:00:00Z"))
    conn.commit()
    with pytest.raises(capture.WarehouseSupersededError):
        run(conn)
    assert conn.execute("SELECT status FROM crawl_job").fetchone()[0] == "failed"
    assert count(conn, "fetched_responses") == 0


def real_busy(conn) -> sqlite3.OperationalError:
    """The error SQLite itself raises when another connection holds the write lock."""
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    holder = sqlite3.connect(path, isolation_level=None)
    other = sqlite3.connect(path, timeout=0)
    holder.execute("BEGIN IMMEDIATE")
    try:
        other.execute("UPDATE crawl_job SET stage = stage")
    except sqlite3.OperationalError as exc:
        return exc
    finally:
        holder.execute("ROLLBACK")
        other.close()
        holder.close()
    raise AssertionError("the second writer was not refused")


@pytest.mark.parametrize("locked", ["the write lock", "sqlite"])
def test_a_locked_warehouse_pauses_the_job_and_a_resume_reads_the_page_again(conn, bank,
                                                                             monkeypatch, locked):
    """`CLAUDE.md`: another app holding it is waited for, never routed around. The page is
    undone and the record holds its place, so this is a pause, not a failure."""
    real_store = tenderstore.store_response
    calls = []
    refusal = (dbmod.DbLockedError("the write lock is held by pid 7")
               if locked == "the write lock" else real_busy(conn))

    def store(c, **kw):
        calls.append(1)
        if len(calls) == 2:
            raise refusal
        return real_store(c, **kw)

    monkeypatch.setattr(tenderstore, "store_response", store)
    ref = jobs.create_job(conn, ["worldbank_org"], "initial_crawl", job_kind=tenderjob.JOB_KIND)
    job = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert job["status"] == "paused" and job["error_summary"] is None
    assert job["checkpoint"]["area"]["next_page"] == 1
    assert any(level == "warning" and "another app holds the warehouse" in message
               for level, message in logged(conn, ref))
    assert count(conn, "tender_releases") == 1_000
    assert jobs.set_control(conn, ref, "resume")
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(300, start=5_000)})
    done = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert done["status"] == "completed" and count(conn, "tender_releases") == 1_500


def test_a_cancel_pending_when_the_warehouse_is_locked_is_a_cancel(conn, bank, monkeypatch):
    ref = a_job(conn)
    real = bank["bank"].get

    def get(url, params=None, **kw):
        if wc.AREA_FACET in params:
            jobs.set_control(conn, ref, "cancel")
        return real(url, params=params, **kw)

    def store(c, **kw):
        raise dbmod.DbLockedError("held")

    bank["bank"].get = get
    monkeypatch.setattr(tenderstore, "store_response", store)
    assert tenderjob.run_tender_crawl_job_once(conn, ref)["status"] == "cancelled"


def test_a_second_connection_holding_the_warehouse_pauses_the_job(conn, bank, monkeypatch):
    """The real SQLite refusal, not an exception a stand-in raises: at #1802's gate a second
    connection left the row `running`, because the failure's own log line met the same lock.
    It is released when the page has failed, as a holder that outlasts the wait once."""
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    monkeypatch.setattr(tenderjob, "WRITE_WAIT_MS", 10)
    other = sqlite3.connect(path, isolation_level=None)
    real_store = tenderstore.store_response

    def store(c, **kw):
        other.execute("BEGIN IMMEDIATE")
        try:
            return real_store(c, **kw)
        finally:
            other.execute("ROLLBACK")

    monkeypatch.setattr(tenderstore, "store_response", store)
    ref = a_job(conn)
    try:
        job = tenderjob.run_tender_crawl_job_once(conn, ref)
    finally:
        other.close()
    assert job["status"] == "paused" and not conn.in_transaction
    assert count(conn, "fetched_responses") == 0
    assert logged(conn, ref)[-1][0] == "warning"
    assert "another app holds the warehouse (database is locked)" in logged(conn, ref)[-1][1]


def test_a_real_fault_of_the_warehouse_still_fails_the_job(conn, bank, monkeypatch):
    def store(c, **kw):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(tenderstore, "store_response", store)
    with pytest.raises(sqlite3.OperationalError):
        run(conn)
    status, summary = conn.execute("SELECT status, error_summary FROM crawl_job").fetchone()
    assert status == "failed"
    assert summary == ("0 of 2 areas read; an update reads the rest. OperationalError: disk "
                       "I/O error")


def test_no_transaction_is_open_across_any_request(conn, bank):
    """A page's write is committed before the next request, or the write lock would be held
    across the crawl's pace."""
    open_at_request = []
    real_get = bank["bank"].get
    bank["bank"].get = lambda url, params=None, **kw: (open_at_request.append(conn.in_transaction),
                                                       real_get(url, params=params, **kw))[1]
    run(conn)
    assert open_at_request and not any(open_at_request)


# ---- the gate of #1802: where a pass starts, on a clock that moves (his ruling, #1701) --------

def at(monkeypatch, when: str) -> None:
    monkeypatch.setattr(tenderjob, "utc_now_iso", lambda: when)


def test_a_pass_starts_from_the_first_count_whatever_later_jobs_counted(conn, bank, monkeypatch):
    """The loss his ruling closes: a stamp after an early area was read, before the newest
    held. Each later job counts again, and none may move where the first pass starts."""
    run(conn)
    bank["bank"].changed = changes(2_500)
    bank["bank"].fail = {(CHANGES, 1000): 503}
    at(monkeypatch, "2026-10-20T08:00:00Z")
    cut, _ = run(conn, "update")
    assert cut["checkpoint"]["changes"]["since"] == SINCE
    at(monkeypatch, "2026-10-25T08:00:00Z")
    again, _ = run(conn, "update")
    assert again["checkpoint"]["changes"]["since"] == SINCE


def test_an_update_as_a_sources_first_job_starts_from_its_own_count(conn, bank):
    bank["bank"].changed = stamped(notices(1, start=9_000), ["2026-10-12T09:00:00Z"])
    job, _ = run(conn, "update")
    assert job["checkpoint"]["changes"]["since"] == SINCE


def test_the_newest_complete_pass_decides_not_the_oldest(conn, bank, monkeypatch):
    run(conn)
    bank["bank"].changed = stamped(notices(1, start=9_000), ["2026-10-12T09:00:00Z"])
    run(conn, "update")
    at(monkeypatch, "2026-10-20T08:00:00Z")
    bank["bank"].changed = stamped(notices(1, start=9_100), ["2026-10-19T09:00:00Z"])
    run(conn, "update")
    third, _ = run(conn, "update")
    assert third["checkpoint"]["changes"]["since"] == "2026-10-18T09:00:00Z"


# ---- the gate of #1802: a resume -----------------------------------------------------------

def a_job(conn, mode="initial_crawl") -> str:
    return jobs.create_job(conn, ["worldbank_org"], mode, job_kind=tenderjob.JOB_KIND)


def pause_after(bank, conn, ref, *, area=None, offset=0):
    """Press Pause once this page has been answered, as the panel does."""
    real = bank.get

    def get(url, params=None, **kw):
        response = real(url, params=params, **kw)
        if params.get("os") == str(offset) and "fct" not in params and (
                area is None or params.get(wc.AREA_FACET) == area):
            jobs.set_control(conn, ref, "pause")
        return response

    bank.get = get


def test_refused_notices_before_a_pause_still_end_the_run_with_errors(conn, bank):
    """His ruling on #1779: a run that refused any notice ends completed with errors, and a
    Pause in between must not launder it."""
    egypt = notices(1_200)
    for notice in egypt[:3]:
        notice["notice_type"] = "Prequalification Notice"
    bank["bank"] = Bank({EGYPT: egypt, KENYA: notices(300, start=5_000)})
    ref = a_job(conn)
    pause_after(bank["bank"], conn, ref, area=EGYPT)
    assert tenderjob.run_tender_crawl_job_once(conn, ref)["status"] == "paused"
    assert jobs.set_control(conn, ref, "resume")
    bank["bank"] = Bank({EGYPT: egypt, KENYA: notices(300, start=5_000)})
    done = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert done["status"] == "completed_with_errors"
    assert done["error_summary"] == f"3 refusals, {LATER} Each is named in the log by its id."
    assert done["counters"]["notices"] == 1_500, "a resume must carry the job's counts on"


def test_a_count_that_moved_during_a_pause_reads_the_area_again_from_its_start(conn, bank):
    """The guard inside `read_area` compares with the count just taken, so across a pause only
    the record can see the move. A notice gone from page 1 slides one in from page 2: read on
    from page 2, the notice now at offset 999 would be in neither, and the area called whole."""
    rows = notices(1_200)
    bank["bank"] = Bank({EGYPT: rows, KENYA: notices(300, start=5_000)})
    ref = a_job(conn)
    pause_after(bank["bank"], conn, ref, area=EGYPT)
    paused = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert paused["checkpoint"]["area"] == {"name": EGYPT, "next_page": 1, "count": 1_200}
    assert jobs.set_control(conn, ref, "resume")
    slid = rows[1_000]["id"]
    bank["bank"] = Bank({EGYPT: rows[:500] + rows[501:], KENYA: notices(300, start=5_000)})
    done = tenderjob.run_tender_crawl_job_once(conn, ref)
    offsets = [c["os"] for c in bank["bank"].calls if c.get(wc.AREA_FACET) == EGYPT]
    assert offsets == ["0", "1000"]
    assert slid in {row[0] for row in conn.execute("SELECT release_ref FROM tender_releases")}
    assert done["checkpoint"]["areas_read"] == [EGYPT, KENYA]
    assert ("info", f"{EGYPT}: the Bank now counts 1,199 notices, not the 1,200 it counted "
                    "before this job stopped; reading it again from its first page"
            ) in logged(conn, ref)


def test_the_area_a_pause_stopped_inside_is_read_first_on_a_resume(conn, bank):
    """An earlier area left unread comes back on a resume. Read first, it would erase the
    resume point and the paused area would start over."""
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(1_100, start=5_000)},
                        fail={(EGYPT, 0): 503})
    ref = a_job(conn)
    pause_after(bank["bank"], conn, ref, area=KENYA)
    assert tenderjob.run_tender_crawl_job_once(conn, ref)["status"] == "paused"
    assert jobs.set_control(conn, ref, "resume")
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(1_100, start=5_000)})
    done = tenderjob.run_tender_crawl_job_once(conn, ref)
    pages = [(c[wc.AREA_FACET], c["os"]) for c in bank["bank"].calls if wc.AREA_FACET in c]
    assert pages == [(KENYA, "1000"), (EGYPT, "0"), (EGYPT, "1000")]
    # And the area that failed before the pause, now whole, is no longer reported unread.
    assert done["status"] == "completed" and done["checkpoint"]["unread"] == {}


def test_a_resumes_figures_count_the_job_not_the_leg(conn, bank):
    """Rows 18-19: not `8 of 5` requests and `4/4` areas with 6 read."""
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(1_100, start=5_000)})
    ref = a_job(conn)
    pause_after(bank["bank"], conn, ref, area=KENYA)
    tenderjob.run_tender_crawl_job_once(conn, ref)
    assert jobs.set_control(conn, ref, "resume")
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(1_100, start=5_000)})
    real = bank["bank"].get
    shown = []

    def get(url, params=None, **kw):
        if wc.AREA_FACET in params:
            job = jobs.get_job(conn, ref)
            shown.append((job["progress_done"], job["progress_total"]))
        return real(url, params=params, **kw)

    bank["bank"].get = get
    done = tenderjob.run_tender_crawl_job_once(conn, ref)
    slot = done["counters"]["sources"]["worldbank_org"]
    # 1 count + 2 pages + 1 page, then 1 count + 1 page: and the second leg's total said so.
    assert slot["requests"] == done["counters"]["requests"] == 6
    assert slot["expected"] == 6
    assert shown == [(1, 2)], "Egypt is whole, and Kenya still to finish, as the resume starts"
    assert (done["progress_done"], done["progress_total"]) == (2, 2)


def test_a_resume_says_it_is_one_and_keeps_when_it_started(conn, bank, monkeypatch):
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(300, start=5_000)})
    ref = a_job(conn)
    pause_after(bank["bank"], conn, ref, area=EGYPT)
    paused = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert jobs.set_control(conn, ref, "resume")
    at(monkeypatch, "2026-10-14T08:00:00Z")
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(300, start=5_000)})
    done = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert done["started_at"] == paused["started_at"] == NOW
    assert any(level == "warning" and message.startswith(
        "going on from the next unread page: this is not this job's first pass")
        for level, message in logged(conn, ref))


def test_a_pause_in_the_pass_over_changes_says_it_reads_that_pass_again(conn, bank):
    """Restarting that pass from `since` is right; "the next unread page" would be false, and
    so would an "area(s)" unit for its pages."""
    run(conn)
    bank["bank"].changed = changes(2_500)
    ref = a_job(conn, "update")
    real = bank["bank"].get

    def get(url, params=None, **kw):
        response = real(url, params=params, **kw)
        if params.get("os") == "1000" and wc.AREA_FACET not in params:
            jobs.set_control(conn, ref, "pause")
        return response

    bank["bank"].get = get
    paused = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert paused["status"] == "paused" and paused["progress_done"] == 2
    assert ("info", "paused between pages. Resuming reads the pass over changes again from "
                    "its start, and what it kept is not kept twice") in logged(conn, ref)
    assert jobs.set_control(conn, ref, "resume")
    bank["bank"].get = real
    done = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert done["status"] == "completed"
    assert any(message.startswith("reading the changes again from their start: this is not "
                                  "this job's first pass, and the last one had reached 2 page(s)")
               for _, message in logged(conn, ref))


# ---- the gate of #1802: stopping (his addition of 2026-10-31, #1779) ---------------------------

@pytest.mark.parametrize("control, status", [("cancel", "cancelled"), ("pause", "paused")])
def test_a_stop_is_honoured_while_pages_fail(conn, bank, control, status):
    """Measured by the gate: on a Bank failing every page, 548 more requests after the press,
    about 69 minutes, and the Cancel overwritten. A failed page is a boundary too."""
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(300, start=5_000)},
                        fail={(EGYPT, 0): 502, (KENYA, 0): 502})
    ref = a_job(conn)
    real = bank["bank"].get

    def get(url, params=None, **kw):
        if params.get(wc.AREA_FACET) == EGYPT:
            jobs.set_control(conn, ref, control)
        return real(url, params=params, **kw)

    bank["bank"].get = get
    job = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert job["status"] == status
    assert not any(c.get(wc.AREA_FACET) == KENYA for c in bank["bank"].calls)


def test_a_page_refused_whole_is_counted_for_the_panel_to_suggest_a_stop(conn, bank):
    kenya = notices(300, start=5_000)
    for notice in kenya:
        notice["notice_type"] = "Prequalification Notice"
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: kenya})
    job, ref = run(conn)
    assert job["counters"]["pages_refused"] == 1
    assert any(level == "warning" and message.endswith(
        "The crawl goes on; Pause or Cancel on Jobs stops it.")
        for level, message in logged(conn, ref))


def test_a_pages_refusal_lines_are_one_commit(conn, bank):
    """Measured by the gate: 1,000 lines with a commit each took 400-589 ms and 9.36 MB of WAL,
    against 13-15 ms and 0.2 MB. Every refusal stays named, his ruling of 2026-10-31."""
    egypt = notices(1_200)
    for notice in egypt[:1_000]:
        notice["notice_type"] = "Prequalification Notice"
    bank["bank"] = Bank({EGYPT: egypt})
    commits = []
    conn.set_trace_callback(lambda sql: commits.append(sql) if sql.startswith("COMMIT") else None)
    ref = a_job(conn)
    tenderjob.run_tender_crawl_job_once(conn, ref)
    conn.set_trace_callback(None)
    assert sum(1 for _, message in logged(conn, ref) if "not kept" in message) >= 1_000
    assert len(commits) < 40, len(commits)


def test_a_stop_during_the_count_is_honoured_before_running_is_claimed(conn, bank):
    ref = a_job(conn)
    real = bank["bank"].get

    def get(url, params=None, **kw):
        response = real(url, params=params, **kw)
        if "fct" in params:
            jobs.set_control(conn, ref, "pause")
        return response

    bank["bank"].get = get
    statuses = []
    conn.set_trace_callback(lambda sql: statuses.append(sql) if "status = " in sql
                            and sql.startswith("UPDATE crawl_job") else None)
    job = tenderjob.run_tender_crawl_job_once(conn, ref)
    conn.set_trace_callback(None)
    assert job["status"] == "paused" and bank["bank"].requests_count == 1
    assert not any("'running'" in sql for sql in statuses), statuses


def test_a_stop_inside_the_pass_over_changes_is_honoured(conn, bank):
    run(conn)
    bank["bank"].changed = changes(2_500)
    ref = a_job(conn, "update")
    real = bank["bank"].get

    def get(url, params=None, **kw):
        response = real(url, params=params, **kw)
        if params.get("os") == "0" and wc.AREA_FACET not in params and "fct" not in params:
            jobs.set_control(conn, ref, "cancel")
        return response

    bank["bank"].get = get
    assert tenderjob.run_tender_crawl_job_once(conn, ref)["status"] == "cancelled"
    assert not any(c.get("os") == "1000" for c in bank["bank"].calls if wc.AREA_FACET not in c)


def test_no_changes_are_read_while_an_area_is_unread(conn, bank):
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(300, start=5_000)},
                        fail={(EGYPT, 0): 503}, changed=changes(3))
    job, _ = run(conn, "update")
    assert "changes" not in job["checkpoint"]
    assert not any(str(c.get("srt", "")).startswith("api_modified_date") for c in bank["bank"].calls)


# ---- the gate of #1802: what a run says ------------------------------------------------------

def test_an_update_of_a_bank_with_unlisted_notices_still_says_its_plan(conn, bank):
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(300, start=5_000)},
                        fail={(EGYPT, 0): 503})
    run(conn)
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(300, start=5_000)})
    bank["bank"].facets["total"] = str(int(bank["bank"].facets["total"]) + 30)
    _, ref = run(conn, "update")
    lines = logged(conn, ref)
    assert lines[0] == ("info", "1 area not read yet: 3 requests")
    assert lines[1][0] == "warning" and lines[1][1].startswith("30 notices the Bank lists in no area")


def test_a_first_crawl_says_one_plan_line_and_one_unlisted_notice_reads_at_one(conn, bank):
    bank["bank"].facets["total"] = str(int(bank["bank"].facets["total"]) + 1)
    _, ref = run(conn)
    lines = [message for _, message in logged(conn, ref)]
    assert lines[0] == "counted 1,501 notices in 2 areas: 4 requests"
    assert not any("not read yet" in line for line in lines)
    assert ("1 notice the Bank lists in no area: an area pass cannot read it, and the pass over "
            "changes reads it when it changes") in lines


def test_an_initial_crawl_of_a_source_held_whole_says_why_it_read_nothing(conn, bank):
    run(conn)
    _, ref = run(conn)
    assert logged(conn, ref)[0] == ("info", "every area is already read, so an initial crawl "
                                            "has nothing to read")


def test_a_failed_run_leads_with_what_it_means_and_names_what_failed(conn, bank, monkeypatch):
    """Row 24: the consequence leads, so the two-line clamp on Jobs keeps it."""
    real = wc.read_area
    calls = []

    def read_area(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise ValueError("boom\nsecond line of it")
        return real(*args, **kwargs)

    monkeypatch.setattr(tenderjob.wc, "read_area", read_area)
    with pytest.raises(ValueError):
        run(conn)
    ref = conn.execute("SELECT job_ref FROM crawl_job").fetchone()[0]
    job = jobs.get_job(conn, ref)
    summary = "1 of 2 areas read; an update reads the rest. ValueError: boom"
    assert (job["status"], job["error_summary"]) == ("failed", summary)
    assert logged(conn, ref)[-1] == ("error", summary)


@pytest.mark.parametrize("raised, named", [
    (httpx.ReadError(""), "The count failed, so this run read nothing. ReadError"),
    (httpx.ConnectError("no route"),
     "The count failed, so this run read nothing. ConnectError: no route"),
])
def test_a_count_that_fails_says_so_and_is_never_blank(conn, bank, raised, named):
    def get(url, params=None, **kw):
        raise raised

    bank["bank"].get = get
    with pytest.raises(type(raised)):
        run(conn)
    assert conn.execute("SELECT error_summary FROM crawl_job").fetchone()[0] == named


def test_a_pass_over_changes_that_fails_says_that_and_not_its_areas(conn, bank, monkeypatch):
    run(conn)
    bank["bank"].changed = changes(3)

    def store(c, **kw):
        raise ValueError("boom")

    monkeypatch.setattr(tenderstore, "store_response", store)
    with pytest.raises(ValueError):
        run(conn, "update")
    assert conn.execute("SELECT error_summary FROM crawl_job ORDER BY job_id DESC").fetchone(
        )[0] == "The pass over changes failed, and the next update reads it again. ValueError: boom"


def test_a_site_stopping_the_pass_over_changes_says_what_a_resume_does(conn, bank):
    run(conn)
    bank["bank"].changed = changes(3)
    bank["bank"].raise_at = {(CHANGES, 0): RobotsUnreachable("robots.txt timed out")}
    job, ref = run(conn, "update")
    assert job["status"] == "paused"
    assert logged(conn, ref)[-1][1].endswith("Resuming reads the pass over changes again from its "
                                             "start, and what it kept is not kept twice")


def test_a_cut_short_pass_and_refused_notices_read_as_two_sentences(conn, bank):
    run(conn)
    changed = changes(2_500)
    changed[0]["notice_type"] = "Prequalification Notice"
    bank["bank"].changed = changed
    bank["bank"].fail = {(CHANGES, 1000): 503}
    job, _ = run(conn, "update")
    assert job["error_summary"] == (f"the pass over changes stopped: changes, page 2: HTTP 503 "
                                    f"after its tries. The next update reads again from {SINCE}. "
                                    f"1 refusal, {LATER} It is named in the log by its id.")


def test_a_page_of_changes_reads_at_one(conn, bank):
    run(conn)
    bank["bank"].changed = stamped(notices(1, start=9_000), ["2026-10-12T09:00:00Z"])
    _, ref = run(conn, "update")
    lines = [message for _, message in logged(conn, ref)]
    assert "changes, page 1: 1 notice" in lines
    assert lines.count("changes: 1 notice in 1 request") == 1


def test_what_a_run_counts_is_what_the_collector_tallies():
    assert tuple(field.name for field in dataclasses.fields(wc.Tally)) == tenderjob.COUNTERS


# ---- the gate of #1802: the wiring politeness rests on ------------------------------------------

def test_the_job_fetches_with_the_sources_rules_and_his_settings(conn, monkeypatch):
    seen = {}

    def fetcher(rules, settings):
        seen.update(rules=rules, settings=settings)
        return Bank({EGYPT: notices(3)})

    monkeypatch.setattr(tenderjob, "source_fetcher", fetcher)
    run(conn)
    assert seen["rules"].robots.value == "obey" and seen["rules"].crawl_pace_s == 2.5
    assert seen["settings"] == capture.crawl_settings(conn)
    # His choice outranks what it ships with, or the rules he sets would change nothing.
    source_settings.save(conn, "worldbank_org", tenders.get("worldbank_org"), {"robots": "default"})
    run(conn)
    assert seen["rules"].robots.value == "default"


class Lane:
    """The cross-job gate, recording the host and what happens while it is waited for."""

    def __init__(self, on_enter=None):
        self.hosts, self.on_enter, self.inside = [], on_enter, False

    @contextmanager
    def lane(self, host):
        self.hosts.append(host)
        if self.on_enter:
            self.on_enter()
        self.inside = True
        try:
            yield
        finally:
            self.inside = False


def test_the_fetching_holds_the_sites_lane(conn, bank):
    lane = Lane()
    inside = []
    real = bank["bank"].get
    bank["bank"].get = lambda url, params=None, **kw: (inside.append(lane.inside),
                                                       real(url, params=params, **kw))[1]
    ref = jobs.create_job(conn, ["worldbank_org"], "initial_crawl", job_kind=tenderjob.JOB_KIND)
    tenderjob.run_tender_crawl_job_once(conn, ref, admission=lane)
    assert lane.hosts == ["search.worldbank.org"] and inside and all(inside)


def test_a_job_settled_while_waiting_for_the_lane_reads_nothing(conn, bank):
    ref = jobs.create_job(conn, ["worldbank_org"], "initial_crawl", job_kind=tenderjob.JOB_KIND)
    job_id = jobs.get_job(conn, ref)["job_id"]
    lane = Lane(on_enter=lambda: jobs._finish(conn, job_id, JobStatus.CANCELLED, None))
    job = tenderjob.run_tender_crawl_job_once(conn, ref, admission=lane)
    assert job["status"] == "cancelled" and bank["bank"].requests_count == 0


@pytest.mark.parametrize("ending", ["completed", "with_errors", "failed", "paused", "cancelled",
                                    "blocked"])
def test_how_the_run_treated_the_site_is_logged_on_every_ending_before_the_summary(
        conn, bank, monkeypatch, ending):
    bank["bank"].robots_warnings = ["robots.txt asked for a delay"]
    ref = a_job(conn)
    if ending == "failed":
        monkeypatch.setattr(tenderstore, "store_response",
                            lambda c, **kw: (_ for _ in ()).throw(ValueError("boom")))
    elif ending == "with_errors":
        bank["bank"].fail = {(KENYA, 0): 503}
    elif ending == "blocked":
        bank["bank"].raise_at = {(EGYPT, 0): RobotsUnreachable("robots.txt timed out")}
    elif ending in {"paused", "cancelled"}:
        real = bank["bank"].get
        control = "pause" if ending == "paused" else "cancel"

        def get(url, params=None, **kw):
            response = real(url, params=params, **kw)
            if wc.AREA_FACET in params:
                jobs.set_control(conn, ref, control)
            return response

        bank["bank"].get = get
    try:
        tenderjob.run_tender_crawl_job_once(conn, ref)
    except ValueError:
        assert ending == "failed"
    lines = logged(conn, ref)
    assert ("info", "robots.txt asked for a delay") in lines
    if ending == "failed":
        assert lines[-1][0] == "error", "the summary is the last line (row 21)"
    if ending == "with_errors":
        assert lines[-1][0] == "warning" and lines[-1][1].startswith("1 area not read")


# ---- the gate of #1802: the source it writes is a declared one -----------------------------------

def test_a_crawled_tender_source_is_declared(conn, bank):
    """`storage.undeclared_sources` reads a source no registry names as one that can never be
    refreshed, and /api/health says so about the World Bank."""
    run(conn)
    assert "worldbank_org" not in storage.undeclared_sources(conn)


# ---- the re-review of #1802: a write meets another app (his ruling of 2026-10-31, #1775) ---------

class Holder:
    """A real second connection holding SQLite's write lock: `take` it, and it commits a write of
    its own after `seconds`, on its own thread, as another app's transaction ends."""

    def __init__(self, conn, seconds):
        path = conn.execute("PRAGMA database_list").fetchone()[2]
        self.other = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.seconds, self.taken, self.timer = seconds, False, None

    def take(self):
        if self.taken:
            return
        self.taken = True
        self.other.execute("BEGIN IMMEDIATE")
        self.other.execute("INSERT INTO scrapex_meta (key, value) VALUES ('held', 'by another app') "
                           "ON CONFLICT(key) DO UPDATE SET value = excluded.value")
        self.timer = threading.Timer(self.seconds, lambda: self.other.execute("COMMIT"))
        self.timer.start()

    def close(self):
        if self.timer:
            self.timer.join()
        self.other.close()


@pytest.fixture()
def holder(conn):
    holders = []

    def make(seconds=0.3):
        holders.append(Holder(conn, seconds))
        return holders[-1]

    yield make
    for each in holders:
        each.close()


def hold_at_the_sites_lines(monkeypatch, held):
    """Taken as the run's lines about the site are written, the first write of every ending."""
    real = tenderjob.directoryjob.log_politeness

    def politeness(*args, **kwargs):
        held.take()
        return real(*args, **kwargs)

    monkeypatch.setattr(tenderjob.directoryjob, "log_politeness", politeness)


def stop_after_the_first_page(bank, conn, ref, control):
    real = bank["bank"].get

    def get(url, params=None, **kw):
        response = real(url, params=params, **kw)
        if wc.AREA_FACET in params:
            jobs.set_control(conn, ref, control)
        return response

    bank["bank"].get = get


@pytest.mark.parametrize("control, status", [("pause", "paused"), ("cancel", "cancelled")])
def test_another_app_writing_as_a_stop_settles_does_not_replace_the_stop(
        conn, bank, monkeypatch, holder, control, status):
    """At the re-review a 7 s holder turned his Pause and his Cancel into `failed`: the site's
    line met the lock, replaced the stop on its way out, and the pause got no wait of its own."""
    bank["bank"].robots_warnings = ["robots.txt asked for a delay"]
    conn.execute("PRAGMA busy_timeout = 10")
    hold_at_the_sites_lines(monkeypatch, holder())
    ref = a_job(conn)
    stop_after_the_first_page(bank, conn, ref, control)
    job = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert job["status"] == status and job["error_summary"] is None
    assert ("info", "robots.txt asked for a delay") in logged(conn, ref)
    assert not conn.in_transaction


def test_another_app_writing_as_a_failure_settles_keeps_the_consequence_and_the_error(
        conn, bank, monkeypatch, holder):
    bank["bank"].robots_warnings = ["robots.txt asked for a delay"]
    hold_at_the_sites_lines(monkeypatch, holder())
    monkeypatch.setattr(tenderstore, "store_response",
                        lambda c, **kw: (_ for _ in ()).throw(ValueError("boom")))
    conn.execute("PRAGMA busy_timeout = 10")
    with pytest.raises(ValueError):
        run(conn)
    ref = conn.execute("SELECT job_ref FROM crawl_job").fetchone()[0]
    summary = "0 of 2 areas read; an update reads the rest. ValueError: boom"
    assert jobs.get_job(conn, ref)["error_summary"] == summary
    assert logged(conn, ref)[-1] == ("error", summary)


@pytest.mark.parametrize("raised, status, named", [
    (RobotsUnreachable("robots.txt timed out"), "paused", "robots.txt timed out"),
    (HostRefused("the host is refused"), "failed", "the host is refused"),
])
def test_another_app_writing_as_the_site_stops_a_job_keeps_the_sites_reason(
        conn, bank, monkeypatch, holder, raised, status, named):
    bank["bank"].robots_warnings = ["robots.txt asked for a delay"]
    bank["bank"].raise_at = {(EGYPT, 0): raised}
    hold_at_the_sites_lines(monkeypatch, holder())
    conn.execute("PRAGMA busy_timeout = 10")
    ref = a_job(conn)
    job = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert job["status"] == status
    assert any(named in message for _, message in logged(conn, ref))


def test_a_resume_into_another_apps_write_pauses_and_can_be_resumed_again(
        conn, bank, monkeypatch, holder):
    """He was just told another app is writing, so this is the likely moment for a Resume. At the
    re-review it failed the job, and a failed job refuses the next Resume."""
    ref = a_job(conn)
    stop_after_the_first_page(bank, conn, ref, "pause")
    tenderjob.run_tender_crawl_job_once(conn, ref)
    assert jobs.set_control(conn, ref, "resume")
    monkeypatch.setattr(tenderjob, "WRITE_WAIT_MS", 10)
    held = holder()
    held.take()
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(300, start=5_000)})
    job = tenderjob.run_tender_crawl_job_once(conn, ref)
    held.timer.join()
    assert job["status"] == "paused"
    assert bank["bank"].requests_count == 0
    assert "another app holds the warehouse (database is locked)" in logged(conn, ref)[-1][1]
    assert jobs.set_control(conn, ref, "resume")
    assert tenderjob.run_tender_crawl_job_once(conn, ref)["status"] == "completed"
    assert count(conn, "tender_releases") == 1_500


def test_a_first_start_into_another_apps_write_pauses_with_nothing_read(conn, bank, monkeypatch,
                                                                        holder):
    monkeypatch.setattr(tenderjob, "WRITE_WAIT_MS", 10)
    ref = a_job(conn)
    held = holder()
    held.take()
    job = tenderjob.run_tender_crawl_job_once(conn, ref)
    held.timer.join()
    assert job["status"] == "paused" and bank["bank"].requests_count == 0
    assert jobs.set_control(conn, ref, "resume")
    assert tenderjob.run_tender_crawl_job_once(conn, ref)["status"] == "completed"


@pytest.mark.parametrize("wait_ms, status", [(60_000, "completed"), (10, "paused")])
def test_the_end_of_a_run_waits_for_another_app_and_loses_nothing(conn, bank, monkeypatch, holder,
                                                                  wait_ms, status):
    """Every page kept, and the last write meets a holder. A wait it can outlast completes; one it
    cannot pauses, for a Resume costs one count and settles it. Never `failed`, with all kept."""
    monkeypatch.setattr(tenderjob, "WRITE_WAIT_MS", wait_ms)
    hold_at_the_sites_lines(monkeypatch, holder())
    ref = a_job(conn)
    job = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert job["status"] == status and count(conn, "tender_releases") == 1_500
    if status == "paused":
        assert jobs.set_control(conn, ref, "resume")
        bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(300, start=5_000)})
        assert tenderjob.run_tender_crawl_job_once(conn, ref)["status"] == "completed"
        assert bank["bank"].requests_count == 1, "the count, and nothing else"


def test_a_holder_past_the_wait_is_waited_for_and_the_job_is_never_left_running(conn, bank,
                                                                                monkeypatch,
                                                                                holder, capfd):
    """`CLAUDE.md`: wait for it, never route around it. At the re-review a 25 s holder left the row
    `running` with no worker, and nothing said so."""
    monkeypatch.setattr(tenderjob, "WRITE_WAIT_MS", 10)
    held = holder(0.5)
    real_store = tenderstore.store_response

    def store(c, **kw):
        held.take()
        return real_store(c, **kw)

    monkeypatch.setattr(tenderstore, "store_response", store)
    ref = a_job(conn)
    job = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert job["status"] == "paused" and not conn.in_transaction
    assert count(conn, "fetched_responses") == 0
    assert "another app holds the warehouse (database is locked)" in logged(conn, ref)[-1][1]
    assert f"{ref}: waiting to settle this job" in capfd.readouterr().err, "the row cannot say so"


def test_a_fault_of_the_warehouse_while_settling_the_pause_is_not_waited_on(conn, bank, monkeypatch):
    """Only another app ends. A disk that has failed never would, and the worker must hear of it."""
    monkeypatch.setattr(tenderstore, "store_response",
                        lambda c, **kw: (_ for _ in ()).throw(dbmod.DbLockedError("held")))

    def pause(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(tenderjob.directoryjob, "pause_because", pause)
    with pytest.raises(sqlite3.OperationalError, match="disk"):
        run(conn)


def test_a_cancel_pending_when_a_holder_outlasts_the_wait_is_a_cancel(conn, bank, monkeypatch,
                                                                      holder):
    monkeypatch.setattr(tenderjob, "WRITE_WAIT_MS", 10)
    held = holder(0.5)
    real_store = tenderstore.store_response

    def store(c, **kw):
        held.take()
        return real_store(c, **kw)

    monkeypatch.setattr(tenderstore, "store_response", store)
    ref = a_job(conn)
    real = bank["bank"].get

    def get(url, params=None, **kw):
        if wc.AREA_FACET in params:
            jobs.set_control(conn, ref, "cancel")
        return real(url, params=params, **kw)

    bank["bank"].get = get
    assert tenderjob.run_tender_crawl_job_once(conn, ref)["status"] == "cancelled"


def test_the_words_of_a_pause_for_the_warehouse_come_from_the_record_a_resume_reads(
        conn, bank, monkeypatch):
    """The page was undone: what is said about a Resume is what the committed record will do."""
    run(conn)
    bank["bank"].changed = changes(3)
    ref = a_job(conn, "update")

    def store(c, **kw):
        raise dbmod.DbLockedError("held")

    monkeypatch.setattr(tenderstore, "store_response", store)
    job = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert job["status"] == "paused"
    assert logged(conn, ref)[-1][1].endswith("Resuming reads the pass over changes again from its "
                                             "start, and what it kept is not kept twice")


def test_the_pause_for_the_warehouse_says_how_the_run_treated_the_site_first(conn, bank,
                                                                             monkeypatch):
    bank["bank"].robots_warnings = ["robots.txt asked for a delay"]

    def store(c, **kw):
        raise dbmod.DbLockedError("held")

    monkeypatch.setattr(tenderstore, "store_response", store)
    ref = a_job(conn)
    tenderjob.run_tender_crawl_job_once(conn, ref)
    lines = logged(conn, ref)
    assert lines.count(("info", "robots.txt asked for a delay")) == 1
    assert "another app holds the warehouse" in lines[-1][1]


def test_an_error_that_only_reads_like_a_lock_fails_the_job(conn, bank, monkeypatch):
    """At the re-review `no such table: source_blocked` paused the job for another app."""
    def store(c, **kw):
        c.execute("SELECT 1 FROM source_blocked")

    monkeypatch.setattr(tenderstore, "store_response", store)
    with pytest.raises(sqlite3.OperationalError, match="source_blocked"):
        run(conn)
    status, summary = conn.execute("SELECT status, error_summary FROM crawl_job").fetchone()
    assert status == "failed" and "no such table: source_blocked" in summary


def test_the_workers_last_resort_settles_on_a_fresh_transaction(conn):
    """`_fail_orphan`'s docstring promises it, and the recorder before it leaves a failed `BEGIN`
    open: its write was then an upgrade SQLite does not wait on, and the row stayed `running` with
    no worker at the re-review."""
    ref = a_job(conn)
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    other = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    other.execute("BEGIN IMMEDIATE")
    conn.execute("PRAGMA busy_timeout = 10")
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("UPDATE crawl_job SET stage = 'x'")
    assert conn.in_transaction
    conn.execute("PRAGMA busy_timeout = 5000")
    timer = threading.Timer(0.3, lambda: other.execute("ROLLBACK"))
    timer.start()
    try:
        jobs.JobRunner._fail_orphan(conn, ref, ValueError("boom"))
    finally:
        timer.join()
        other.close()
    assert jobs.get_job(conn, ref)["status"] == "failed"


# ---- the re-review of #1802: the row outranks every ending ----------------------------------------

def settled_at_the_ending(monkeypatch, conn, ref):
    """Settled by something else as the run's first ending write is made: the window is a whole
    fetch with its tries at the two endings that wait on one."""
    real = tenderjob.directoryjob.log_politeness

    def politeness(*args, **kwargs):
        job = jobs.get_job(conn, ref)
        jobs._finish(conn, job["job_id"], JobStatus.CANCELLED, None)
        return real(*args, **kwargs)

    monkeypatch.setattr(tenderjob.directoryjob, "log_politeness", politeness)


def test_a_cancel_on_a_pausing_job_is_not_turned_back_into_a_pause(conn, bank, monkeypatch):
    """The panel draws Cancel on `pausing`, and `set_control` settles that at once. His Cancel was
    then lost, the row `paused` with `finished_at` set."""
    ref = a_job(conn)
    stop_after_the_first_page(bank, conn, ref, "pause")
    real = tenderjob.directoryjob.log_politeness

    def politeness(*args, **kwargs):
        assert jobs.set_control(conn, ref, "cancel")
        return real(*args, **kwargs)

    monkeypatch.setattr(tenderjob.directoryjob, "log_politeness", politeness)
    job = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert job["status"] == "cancelled"
    assert logged(conn, ref)[-1][1] == ("stopped between pages: this job is already settled, so "
                                        "nothing more is read")


def test_a_failure_does_not_overwrite_a_settled_job_and_is_still_named(conn, bank, monkeypatch):
    ref = a_job(conn)
    settled_at_the_ending(monkeypatch, conn, ref)
    monkeypatch.setattr(tenderstore, "store_response",
                        lambda c, **kw: (_ for _ in ()).throw(ValueError("boom")))
    with pytest.raises(ValueError):
        tenderjob.run_tender_crawl_job_once(conn, ref)
    job = jobs.get_job(conn, ref)
    assert (job["status"], job["error_summary"]) == ("cancelled", None)
    assert logged(conn, ref)[-1] == (
        "error", "0 of 2 areas read; an update reads the rest. ValueError: boom — this job is "
                 "already settled, so it is left as it is")


def test_refused_notices_at_the_end_do_not_overwrite_a_settled_job(conn, bank, monkeypatch):
    kenya = notices(300, start=5_000)
    for notice in kenya:
        notice["notice_type"] = "Prequalification Notice"
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: kenya})
    ref = a_job(conn)
    settled_at_the_ending(monkeypatch, conn, ref)
    job = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert (job["status"], job["error_summary"]) == ("cancelled", None)
    assert logged(conn, ref)[-1][0] == "warning"
    assert logged(conn, ref)[-1][1].endswith(" — this job is already settled, so it is left as it is")
    assert "300 refusals" in logged(conn, ref)[-1][1]


def test_a_clean_end_does_not_overwrite_a_settled_job(conn, bank, monkeypatch):
    ref = a_job(conn)
    settled_at_the_ending(monkeypatch, conn, ref)
    job = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert (job["status"], job["error_summary"]) == ("cancelled", None)
    assert logged(conn, ref)[-1] == (
        "info", "every page it read is kept — this job is already settled, so it is left as it is")


# ---- the re-review of #1802: what a run says is what the next run does -----------------------------

def test_a_count_that_fails_on_a_resume_does_not_say_nothing_was_read(conn, bank):
    """A site stop, then a Resume whose count answers 503: the natural path, and 1,000 releases
    were held under the words "this run read nothing"."""
    ref = a_job(conn)
    pause_after(bank["bank"], conn, ref, area=EGYPT)
    tenderjob.run_tender_crawl_job_once(conn, ref)
    assert jobs.set_control(conn, ref, "resume")
    bank["bank"].get = lambda url, params=None, **kw: (_ for _ in ()).throw(
        httpx.ConnectError("no route"))
    with pytest.raises(httpx.ConnectError):
        tenderjob.run_tender_crawl_job_once(conn, ref)
    assert jobs.get_job(conn, ref)["error_summary"] == (
        "The count failed; an update reads the rest. ConnectError: no route")


def test_a_job_settled_in_the_lane_on_a_resume_says_nothing_more_was_read(conn, bank):
    ref = a_job(conn)
    pause_after(bank["bank"], conn, ref, area=EGYPT)
    tenderjob.run_tender_crawl_job_once(conn, ref)
    assert jobs.set_control(conn, ref, "resume")
    job_id = jobs.get_job(conn, ref)["job_id"]
    lane = Lane(on_enter=lambda: jobs._finish(conn, job_id, JobStatus.CANCELLED, None))
    tenderjob.run_tender_crawl_job_once(conn, ref, admission=lane)
    assert logged(conn, ref)[-1][1] == ("stopped while waiting for the site's turn, so nothing more "
                                        "was read")
    assert not conn.in_transaction


RESUMING_CHANGES = ("Resuming reads the pass over changes again from its start, and what it kept "
                    "is not kept twice")
RESUMING_AREAS = ("Resuming goes on from the next unread page, and the areas read whole are not "
                  "read again")


def test_a_job_stopped_in_the_changes_says_so_when_stopped_again_during_the_count(conn, bank):
    run(conn)
    bank["bank"].changed = changes(2_500)
    ref = a_job(conn, "update")
    real = bank["bank"].get

    def stop_in_the_changes(url, params=None, **kw):
        response = real(url, params=params, **kw)
        if "fct" not in params:
            jobs.set_control(conn, ref, "pause")
        return response

    bank["bank"].get = stop_in_the_changes
    tenderjob.run_tender_crawl_job_once(conn, ref)
    assert logged(conn, ref)[-1][1] == f"paused between pages. {RESUMING_CHANGES}"
    assert jobs.set_control(conn, ref, "resume")

    def stop_during_the_count(url, params=None, **kw):
        response = real(url, params=params, **kw)
        jobs.set_control(conn, ref, "pause")
        return response

    bank["bank"].get = stop_during_the_count
    job = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert job["checkpoint"]["phase"] == "changes"
    assert logged(conn, ref)[-1][1] == f"paused between pages. {RESUMING_CHANGES}"
    assert jobs.set_control(conn, ref, "resume")
    bank["bank"].get = real
    tenderjob.run_tender_crawl_job_once(conn, ref)
    assert any("reading the changes again from their start" in message
               for _, message in logged(conn, ref))


def pause_as_the_area_ends(monkeypatch, conn, ref, name):
    """Pressed after the area's last page was answered and checked: the boundary after the area."""
    real = tenderjob.wc.read_area

    def read_area(*args, **kwargs):
        read = real(*args, **kwargs)
        if kwargs["area"].name == name:
            jobs.set_control(conn, ref, "pause")
        return read

    monkeypatch.setattr(tenderjob.wc, "read_area", read_area)


def test_a_pause_after_an_updates_last_area_says_the_changes_come_next(conn, bank, monkeypatch):
    """Its last area read whole, an update has only the pass over changes left, and the words
    "the next unread page" named nothing it would read."""
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(300, start=5_000)},
                        fail={(KENYA, 0): 503})
    run(conn)
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(300, start=5_000)})
    bank["bank"].changed = changes(3)
    ref = a_job(conn, "update")
    pause_as_the_area_ends(monkeypatch, conn, ref, KENYA)
    job = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert job["checkpoint"]["phase"] == "changes"
    assert logged(conn, ref)[-1][1] == f"paused between pages. {RESUMING_CHANGES}"
    assert jobs.set_control(conn, ref, "resume")
    assert tenderjob.run_tender_crawl_job_once(conn, ref)["status"] == "completed"
    assert "changes: 3 notices in 1 request" in [message for _, message in logged(conn, ref)]


def test_an_initial_crawl_never_reaches_the_changes_phase(conn, bank, monkeypatch):
    ref = a_job(conn)
    pause_as_the_area_ends(monkeypatch, conn, ref, KENYA)
    job = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert job["checkpoint"]["phase"] == "areas"
    assert logged(conn, ref)[-1][1] == f"paused between pages. {RESUMING_AREAS}"


def test_a_pause_with_an_area_still_unread_keeps_the_areas_phase_on_an_update(conn, bank,
                                                                              monkeypatch):
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(300, start=5_000)},
                        fail={(EGYPT, 0): 503, (KENYA, 0): 503})
    run(conn)
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: notices(300, start=5_000)})
    ref = a_job(conn, "update")
    pause_as_the_area_ends(monkeypatch, conn, ref, EGYPT)
    job = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert job["checkpoint"]["phase"] == "areas"
    assert logged(conn, ref)[-1][1] == f"paused between pages. {RESUMING_AREAS}"


def test_what_is_left_reads_at_one_on_a_small_area(conn, bank):
    """Areas of 1 to 8 notices are measured live (#1779), and a plain Pause reaches these words."""
    bank["bank"] = Bank({EGYPT: notices(3), KENYA: notices(2, start=5_000)})
    ref = a_job(conn)
    pause_after(bank["bank"], conn, ref, area=KENYA)
    tenderjob.run_tender_crawl_job_once(conn, ref)
    assert jobs.set_control(conn, ref, "resume")
    bank["bank"] = Bank({EGYPT: notices(3), KENYA: notices(2, start=5_000)})
    tenderjob.run_tender_crawl_job_once(conn, ref)
    assert "1 area not read yet: 1 request" in [message for _, message in logged(conn, ref)]


def test_a_count_that_moved_reads_at_one(conn, bank):
    bank["bank"] = Bank({EGYPT: notices(3), KENYA: notices(2, start=5_000)})
    ref = a_job(conn)
    pause_after(bank["bank"], conn, ref, area=KENYA)
    tenderjob.run_tender_crawl_job_once(conn, ref)
    assert jobs.set_control(conn, ref, "resume")
    bank["bank"] = Bank({EGYPT: notices(3), KENYA: notices(1, start=5_000)})
    tenderjob.run_tender_crawl_job_once(conn, ref)
    assert ("Kenya: the Bank now counts 1 notice, not the 2 it counted before this job stopped; "
            "reading it again from its first page") in [m for _, m in logged(conn, ref)]


def test_refusals_are_counted_as_refusals_for_a_resume_reads_a_page_again(conn, bank):
    """A pass over changes restarted by a Resume refuses the same notice twice. The figure is what
    was refused, each named in the log, not a count of distinct notices lost."""
    run(conn)
    changed = changes(2_500)
    changed[0]["notice_type"] = "Prequalification Notice"
    bank["bank"].changed = changed
    ref = a_job(conn, "update")
    real = bank["bank"].get

    def stop_on_the_first_page(url, params=None, **kw):
        response = real(url, params=params, **kw)
        if "fct" not in params:
            jobs.set_control(conn, ref, "pause")
        return response

    bank["bank"].get = stop_on_the_first_page
    tenderjob.run_tender_crawl_job_once(conn, ref)
    assert jobs.set_control(conn, ref, "resume")
    bank["bank"].get = real
    done = tenderjob.run_tender_crawl_job_once(conn, ref)
    assert done["status"] == "completed_with_errors"
    assert done["error_summary"] == f"2 refusals, {LATER} Each is named in the log by its id."
    assert sum(1 for level, _ in logged(conn, ref) if level == "error") == 2


def test_a_notice_nested_past_what_the_warehouse_parses_is_refused_by_its_id(conn, bank):
    """`jsonb()` answers it with an `OperationalError`, which `_keep` rightly reads as the warehouse's
    fault: the job failed, and every later update failed on the same notice."""
    nested = "x"
    for _ in range(1_100):
        nested = [nested]
    egypt = notices(8)
    egypt[3]["noticetitle"] = nested
    bank["bank"] = Bank({EGYPT: egypt, KENYA: notices(2, start=5_000)})
    job, ref = run(conn)
    assert job["status"] == "completed_with_errors"
    assert count(conn, "tender_releases") == 9
    assert any(level == "error" and repr(egypt[3]["id"]) in message and "nests deeper" in message
               for level, message in logged(conn, ref))


# ---- the re-review of #1802: what the summary says later runs do, by running them -----------------

def refused_page(start, size):
    page = notices(size, start=start)
    for notice in page:
        notice["notice_type"] = "Prequalification Notice"
    return page


def test_an_area_with_a_refusal_is_held_whole_and_only_a_change_reads_the_notice_again(conn, bank):
    """His choice of 2026-11-01: said plainly, and read again by a control decided later. When that
    control is built this test changes, on purpose."""
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: refused_page(5_000, 300)})
    job, _ = run(conn)
    assert LATER in job["error_summary"] and KENYA in job["checkpoint"]["areas_read"]

    readable = notices(300, start=5_000)
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: readable})
    done, ref = run(conn, "update")
    assert done["status"] == "completed"
    assert all(call.get(wc.AREA_FACET) != KENYA for call in bank["bank"].calls), "held whole"
    assert count(conn, "tender_releases") == 1_200

    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: readable})
    bank["bank"].changed = stamped(readable[:2], ["2026-10-12T09:00:00Z"] * 2)
    run(conn, "update")
    assert count(conn, "tender_releases") == 1_202, "the Bank changed two, so two are read"


def test_a_refusal_in_an_area_still_unread_is_read_again_by_the_update(conn, bank):
    page = refused_page(5_000, 1_000) + notices(200, start=7_000)
    bank["bank"] = Bank({EGYPT: notices(10), KENYA: page}, fail={(KENYA, 1000): 503})
    job, _ = run(conn)
    assert LATER in job["error_summary"] and KENYA in job["checkpoint"]["unread"]

    readable = notices(1_000, start=5_000) + notices(200, start=7_000)
    bank["bank"] = Bank({EGYPT: notices(10), KENYA: readable})
    done, _ = run(conn, "update")
    assert done["status"] == "completed"
    assert count(conn, "tender_releases") == 1_210
