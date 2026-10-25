"""What the confirmed tender control reads from the engine (milestone 51, part 3b-2b).

#1701's "What the engine must send": the tender row on `/api/sources`, the tender path of
`POST /api/jobs` with its refusals in order and its cost question, and the tender job's
unit and `counted_from`. Every expected value here is the one the confirmed mock drew
(`tenders/2-panel-draft`, `tools/mock_tender_control/render.py`). Nothing reaches the Bank.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from test_worldbank_collector import NOTICES

from scrapex import catalog, jobs, source_settings, tenderjob, tenders, tenderstore
from scrapex.catalog_models import SiteCreate
from scrapex.databases.domain import EngineDatabase
from scrapex.sites import worldbank as wb
from scrapex.webui.app import create_app

EGYPT, KENYA = "Egypt, Arab Republic of", "Kenya"
BLOCKED = ("Full rebuild is not offered for search.worldbank.org: it keeps every notice as "
           "it was read, so there is nothing to archive.")
DUPLICATE = ("search.worldbank.org already has a crawl that has not finished. Follow or "
             "cancel it on Jobs.")
FIRST = {"source": "search.worldbank.org", "requests": 537, "pace_s": 2.5,
         "counted_at": "2026-10-10",
         "reads": "Reads every notice the Bank lists, 422,285 of them, one area at a time. "
                  "An area is one of the Bank's 184 countries and regions.",
         "basis": "Counted from the Bank's own notice totals."}


@pytest.fixture()
def warehouse(tmp_path):
    path = tmp_path / "scrapex-engine.db"
    EngineDatabase(path).initialize()
    return path


@pytest.fixture()
def client(warehouse):
    with TestClient(create_app(warehouse)) as client:
        yield client


def connect(warehouse):
    return EngineDatabase(warehouse).connect()


def tender_row(client) -> dict:
    rows = [row for row in client.get("/api/sources").json()["sources"]
            if row["source_key"] == "worldbank_org"]
    assert len(rows) == 1, rows
    return rows[0]


def past_job(warehouse, record: dict, status: str = "completed_with_errors",
             mode: str = "initial_crawl", finished: str = "2026-10-13T16:30:00Z") -> str:
    """A tender crawl that already ran, with the record it kept (#1733)."""
    conn = connect(warehouse)
    try:
        ref = jobs.create_job(conn, ["worldbank_org"], mode, job_kind=tenderjob.JOB_KIND,
                              checkpoint=record)
        conn.execute("UPDATE crawl_job SET status = ?, finished_at = ? WHERE job_ref = ?",
                     (status, finished if status in {s.value for s in jobs.TERMINAL_JOB_STATUSES}
                      else None, ref))
        conn.commit()
    finally:
        conn.close()
    return ref


COUNT = {"counted_at": "2026-10-13T08:00:00Z", "total": 1_500, "requests": 4,
         "areas": [[EGYPT, 1_200], [KENYA, 300]]}


def start(client, **body):
    return client.post("/api/jobs", json={"source_keys": ["worldbank_org"], **body})


def tender_jobs(warehouse) -> int:
    conn = connect(warehouse)
    try:
        return conn.execute("SELECT count(*) FROM crawl_job WHERE job_kind = ?",
                            (tenderjob.JOB_KIND,)).fetchone()[0]
    finally:
        conn.close()


# ---- the tender row on /api/sources --------------------------------------------------------

def test_the_world_bank_is_a_tender_row_before_any_crawl(client):
    row = tender_row(client)
    assert row == {"kind": "tender", "site_key": "worldbank_org", "source_key": "worldbank_org",
                   "source_name": "World Bank procurement notices", "source_name_ar": "",
                   "base_url": "https://search.worldbank.org", "family": "generic",
                   "implemented": True, "supports_history": False,
                   "runs_blocked": {"full_rebuild": BLOCKED}, "observations": 0,
                   "products": 0, "last_success": None, "kept_pages": 0, "kept_at": None}


def test_a_first_crawl_that_ended_partway_is_on_its_row(client, warehouse):
    past_job(warehouse, {"count": COUNT, "areas_read": [KENYA]})
    assert tender_row(client)["first_crawl"] == {
        "read": 1, "of": 2, "unit": "areas", "stopped_at": "2026-10-13T16:30:00Z"}


@pytest.mark.parametrize("record, status", [
    ({"count": COUNT, "areas_read": [KENYA]}, "queued"),        # not settled
    ({"count": COUNT, "areas_read": [KENYA]}, "paused"),        # not settled either
    ({"count": COUNT, "areas_read": []}, "cancelled"),          # nothing read: Initial again
    ({"count": COUNT, "areas_read": [EGYPT, KENYA]}, "completed"),   # whole
])
def test_no_first_crawl_is_sent_while_unsettled_unread_or_whole(client, warehouse, record,
                                                                status):
    past_job(warehouse, record, status=status)
    assert "first_crawl" not in tender_row(client)


def test_no_first_crawl_is_sent_while_the_update_that_finishes_it_runs(client, warehouse):
    """The stopped first crawl is on record, and an update of it is running: the row says
    nothing about a stop while the crawl that finishes it is under way (#1701, 13)."""
    past_job(warehouse, {"count": COUNT, "areas_read": [KENYA]})
    past_job(warehouse, {"phase": "areas"}, status="running", mode="update")
    assert "first_crawl" not in tender_row(client)


def test_the_last_crawl_that_left_areas_unread_dates_the_row(client, warehouse):
    past_job(warehouse, {"count": COUNT, "areas_read": []}, finished="2026-10-12T09:00:00Z")
    past_job(warehouse, {"count": COUNT, "areas_read": [KENYA]}, mode="update",
             finished="2026-10-14T10:00:00Z")
    assert tender_row(client)["first_crawl"]["stopped_at"] == "2026-10-14T10:00:00Z"


def test_its_count_is_the_tenders_compiled_from_its_notices(client, warehouse):
    conn = connect(warehouse)
    try:
        catalog.register_site(conn, SiteCreate(site_key="worldbank_org",
                                               display_name="World Bank procurement notices",
                                               base_url="https://search.worldbank.org"))
        site = conn.execute("SELECT source_id FROM source_site WHERE source_key = "
                            "'worldbank_org'").fetchone()[0]
        for notice in NOTICES[:2]:
            tenderstore.store_release(conn, source_site_id=site,
                                      release=wb.release_from_notice(notice),
                                      fetched_response_id=None)
        conn.commit()
        compiled = conn.execute("SELECT count(*) FROM tenders").fetchone()[0]
    finally:
        conn.close()
    row = tender_row(client)
    assert compiled > 0 and row["observations"] == compiled == row["products"]


# ---- POST /api/jobs: the refusals in #1701's order, then the question ------------------------

def test_a_tender_source_with_anything_else_is_refused_by_domain(client):
    answer = client.post("/api/jobs", json={"source_keys": ["worldbank_org", "MADAR"]})
    assert answer.status_code == 400
    # Named by `jobs.host_of_url`, the one definition of a host, which drops the `www.`.
    assert answer.json()["detail"] == ("search.worldbank.org collects tenders and runs on its "
                                       "own. Start madar.com separately.")


def test_a_second_crawl_of_a_source_with_one_unfinished_is_refused(client, warehouse):
    past_job(warehouse, {}, status="paused")
    answer = start(client, run_mode="update")
    assert (answer.status_code, answer.json()["detail"]) == (409, DUPLICATE)
    # Before the mode: a full rebuild beside an unfinished crawl hears about the crawl.
    assert start(client, run_mode="full_rebuild").json()["detail"] == DUPLICATE


@pytest.mark.parametrize("mode, says", [("full_rebuild", BLOCKED),
                                        ("history_backfill", "runs initial_crawl or update")])
def test_a_mode_it_does_not_run_is_refused_with_its_sentence(client, mode, says):
    answer = start(client, run_mode=mode)
    assert answer.status_code == 400 and says in answer.json()["detail"]


def test_a_first_crawl_asks_its_cost_with_the_measured_figures_and_queues_nothing(client,
                                                                                    warehouse):
    answer = start(client, run_mode="initial_crawl")
    assert answer.status_code == 409
    assert answer.json() == {"question": "cost", "detail": "confirm the cost to start",
                             "cost": FIRST}
    assert tender_jobs(warehouse) == 0


def test_the_figure_accepted_starts_the_crawl_and_another_figure_is_asked_again(client,
                                                                                 warehouse):
    assert start(client, run_mode="initial_crawl", accept_cost={"requests": 536}
                 ).status_code == 409
    answer = start(client, run_mode="initial_crawl", accept_cost={"requests": 537})
    assert answer.status_code == 200, answer.text
    assert answer.json()["status"] == "queued" and tender_jobs(warehouse) == 1
    conn = connect(warehouse)
    try:
        job = jobs.get_job(conn, answer.json()["job_ref"])
    finally:
        conn.close()
    assert (job["job_kind"], job["run_mode"]) == (tenderjob.JOB_KIND, "initial_crawl")


def test_after_a_count_the_question_is_the_stored_count_dated_by_it(client, warehouse):
    past_job(warehouse, {"count": COUNT, "areas_read": []}, status="cancelled")
    assert start(client, run_mode="initial_crawl").json()["cost"] == {
        **FIRST, "requests": 4, "counted_at": "2026-10-13",
        "reads": "Reads every notice the Bank lists, 1,500 of them, one area at a time. An "
                 "area is one of the Bank's 2 countries and regions."}


def test_a_count_that_left_notices_in_no_area_says_what_it_reads(client, warehouse):
    """His ruling of 2026-10-25 (#1647): the gap is named. The question promises only what
    an area pass reads, and says what it does not."""
    past_job(warehouse, {"count": {**COUNT, "total": 1_530, "unlisted": 30}, "areas_read": []},
             status="cancelled")
    assert start(client, run_mode="initial_crawl").json()["cost"]["reads"] == (
        "Reads every notice the Bank lists in an area, 1,500 of them, one area at a time. An "
        "area is one of the Bank's 2 countries and regions; the 30 notices it lists in no "
        "area are not read.")


@pytest.mark.parametrize("mode, then", [("update", ", then the notices changed since"),
                                        ("initial_crawl", "")])
def test_an_update_that_finishes_a_first_crawl_asks_for_what_is_left(client, warehouse,
                                                                     mode, then):
    past_job(warehouse, {"count": COUNT, "areas_read": [KENYA]})
    assert start(client, run_mode=mode).json()["cost"] == {
        "source": "search.worldbank.org", "requests": 3, "pace_s": 2.5,
        "counted_at": "2026-10-13",
        "reads": f"Reads the 1 area the initial crawl did not reach{then}.",
        "basis": "Counted from the Bank's own notice totals when the initial crawl "
                 "started. The notices changed since are not in these figures."}


def test_a_count_an_update_took_is_named_as_the_last_crawl(client, warehouse):
    past_job(warehouse, {"count": COUNT, "areas_read": [KENYA]}, mode="update")
    asked = start(client, run_mode="update").json()["cost"]
    assert asked["reads"].startswith("Reads the 1 area the last crawl did not reach")
    assert "when the last crawl started" in asked["basis"]


def test_an_update_of_a_source_held_whole_asks_nothing(client, warehouse):
    past_job(warehouse, {"count": COUNT, "areas_read": [EGYPT, KENYA]}, status="completed")
    answer = start(client, run_mode="update")
    assert answer.status_code == 200 and answer.json()["status"] == "queued"


def test_his_pace_is_the_pace_the_question_states(client, warehouse):
    conn = connect(warehouse)
    try:
        catalog.register_site(conn, SiteCreate(site_key="worldbank_org",
                                               display_name="World Bank procurement notices",
                                               base_url="https://search.worldbank.org"))
        source_settings.save(conn, "worldbank_org", tenders.get("worldbank_org"),
                             {"crawl_pace_s": 4.0})
        conn.commit()
    finally:
        conn.close()
    assert start(client, run_mode="initial_crawl").json()["cost"]["pace_s"] == 4.0


# ---- the job, as the control reads it ----------------------------------------------------------

def test_a_tender_job_counts_areas_then_pages_and_says_what_it_counted_from(client, warehouse):
    ref = past_job(warehouse, {"phase": "areas"}, status="running")
    conn = connect(warehouse)
    try:
        job_id = jobs.get_job(conn, ref)["job_id"]
        jobs.record_source_fetch(conn, job_id, "worldbank_org", expected=537,
                                 basis="declared", requests=12)
        conn.commit()
    finally:
        conn.close()
    view = client.get(f"/api/jobs/{ref}").json()
    assert view["progress"]["unit"] == "areas"
    assert view["fetch"]["counted_from"] == "the Bank's notice totals"
    conn = connect(warehouse)
    try:
        conn.execute("UPDATE crawl_job SET checkpoint_json = ? WHERE job_ref = ?",
                     (json.dumps({"phase": "changes"}), ref))
        jobs.record_source_fetch(conn, job_id, "worldbank_org", expected=None, basis=None)
        conn.commit()
    finally:
        conn.close()
    view = client.get(f"/api/jobs/{ref}").json()
    assert view["progress"]["unit"] == "pages"
    assert "counted_from" not in view["fetch"]


def test_its_rules_are_answered_as_a_tender_sources(client):
    answer = client.get("/api/sources/worldbank_org/rules")
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["kind"] == "tender"
    assert body["fields"]["robots"]["value"] == "obey"
    assert body["fields"]["robots"]["origin"] == "source"
    assert body["fields"]["crawl_pace_s"]["value"] == 2.5
