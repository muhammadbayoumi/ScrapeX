"""The tender crawl job (milestone 51, part 3b-2a), on the real migration stream.

Nothing reaches the network: the job's fetcher is the collector tests' `Bank`, which
answers from #1647's recorded responses. His rulings of 2026-10-24 decide what is checked
here: the job keeps its record in its own row (#1733), and a pass over changes starts from
the first count, or from the last complete pass, less one day (#1701).
"""
from __future__ import annotations

import json
import sqlite3

import pytest
from test_worldbank_collector import CHANGES, EGYPT, Bank, changes, count, notices, stamped

from scrapex import catalog, jobs, tenderjob
from scrapex.catalog_models import SiteCreate
from scrapex.connectors.base import RobotsUnreachable
from scrapex.databases.domain import EngineDatabase
from scrapex.sites import worldbank_collect as wc

KENYA = "Kenya"
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
                               "areas": [[EGYPT, 1_200], [KENYA, 300]]}
    assert record["first_counted_at"] == NOW
    assert (job["progress_done"], job["progress_total"]) == (2, 2)
    assert {k: job["counters"][k] for k in tenderjob.COUNTERS} == {
        "requests": 4, "notices": 1_500, "releases_new": 1_500, "releases_unchanged": 0,
        "errors": 0}
    # An initial crawl reads no changes: the next update does, from the count.
    assert "changes" not in record


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
    assert job["error_summary"] == summary and logged(conn, ref)[-2] == ("warning", summary)
    assert job["checkpoint"]["areas_read"] == [KENYA]
    assert job["checkpoint"]["unread"] == {EGYPT: f"{EGYPT}, page 2: HTTP 503 after its tries"}


def test_a_page_that_changed_shape_fails_the_crawl_and_says_how_far_it_got(conn, bank):
    kenya = notices(300, start=5_000)
    for notice in kenya:
        notice["notice_type"] = "Prequalification Notice"
    bank["bank"] = Bank({EGYPT: notices(1_200), KENYA: kenya})
    job, _ = run(conn)
    assert job["status"] == "failed"
    assert job["error_summary"].startswith(
        f"1 of 2 areas read; an update reads the rest. Stopped because the Bank's notices "
        f"changed shape at {KENYA}, page 1: none of 300 notices could be read")


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
    assert lines[0] == "1 area not read yet: 2 requests"
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
                                    f"after its tries. The next update reads again from {SINCE}")
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
    assert paused["checkpoint"]["area"] == {"name": EGYPT, "next_page": 1}
    assert count(conn, "tender_releases") == 1_000
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
    assert lines[at + 1:at + 4] == ["changes: 1,000 notices in 1 request",
                                    "changes: 500 notices in 1 request",
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


def test_a_locked_warehouse_fails_the_job_and_names_the_lock(conn, bank, monkeypatch):
    real = wc.read_area

    def locked(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(tenderjob.wc, "read_area", locked)
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        run(conn)
    job = conn.execute("SELECT status, error_summary FROM crawl_job").fetchone()
    assert tuple(job) == ("failed", "database is locked")
    monkeypatch.setattr(tenderjob.wc, "read_area", real)


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
