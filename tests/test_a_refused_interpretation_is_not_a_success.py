"""An interpretation that stores nothing does not finish as a success (#1738).

THE REAL JOB OVER REAL PAGES, as the issue asked: `run_dataset_interpret_job_once`, the
real `contractors.approve`, TVTC's real directory, the real schema, and real page pairs
from `tests/fixtures/` -- the person-free copies `tests/test_tvtc.py` keeps. A pair is
made to disagree with itself, which the register's reader refuses as `LanguagesDisagree`:
its two languages name different establishments.

BEFORE THE FIX, measured by the merge gate of #1729: every page refused, 0 rows stored,
the job `completed` with no error, and the run recorded as read, so no later press would
read it again. His ruling: every page pair refused fails; some refused completes with
errors and the count; and a run holding a refusal is not recorded as read either way.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scrapex import catalog, contractors, datasetjob, directories, jobs
from scrapex.catalog_models import SiteCreate
from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.extract.tvtc import DATASET_KEY
from scrapex.sites.tvtc import listing_url
from scrapex.snapshotbody import encode
from scrapex.vocab import JobStatus, RunMode

SOURCE = "tvtc_establishments"
CRAWL = "job_crawl"
RUN = f"job-{CRAWL}"
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _log_goes_nowhere_real(tmp_path, monkeypatch):
    monkeypatch.setattr(contractors, "LOG", tmp_path / "trial" / "listing.log")


@pytest.fixture()
def conn(tmp_path):
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    connection = registry.engine.connect()
    try:
        yield connection
    finally:
        connection.close()


def _page(page: int, locale: str) -> dict:
    return json.loads((FIXTURES / f"tvtc_establishments_p{page}_{locale}.json").read_text(
        encoding="utf-8"))


def _good(page: int) -> tuple[str, str]:
    return json.dumps(_page(page, "en")), json.dumps(_page(page, "ar"))


def _disagreeing(page: int) -> tuple[str, str]:
    """The English names an establishment the Arabic does not, which is refused whole."""
    english = _page(page, "en")
    english["data"][3]["id"] = 999
    return json.dumps(english), json.dumps(_page(page, "ar"))


def _a_crawl_that_stored(conn, pages: dict[int, tuple[str, str]]) -> None:
    """A finished TVTC crawl whose run holds these page pairs, after the site registration
    the crawl does first. THROUGH THE REAL TABLES, because `runs_holding_pages` and
    `contractors._pairs` are queries over them."""
    directory = directories.get(SOURCE)
    catalog.register_site(conn, SiteCreate(
        site_key=directory.key, display_name=directory.display_name,
        base_url=directory.base_url))
    conn.execute(
        "INSERT INTO crawl_job (job_ref, run_mode, source_keys, job_kind, status) "
        "VALUES (?,?,?,?,?)",
        (CRAWL, RunMode.UPDATE.value, f'["{SOURCE}"]', "directory_crawl",
         JobStatus.COMPLETED.value))
    for page, (english, arabic) in pages.items():
        for locale, body in (("en", english), ("ar", arabic)):
            url = listing_url(locale=locale, page=page)
            blob, codec, dict_id = encode(conn, body, label=None)
            conn.execute(
                "INSERT INTO generic_page_snapshot (source_url, html_content, "
                " content_hash, crawl_run_ref, html_codec, html_dict_id, captured_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (url, blob, url, f"{RUN}-whole-a1", codec, dict_id,
                 "2026-10-17T10:00:00Z"))
    conn.commit()


def _interpret(conn) -> dict:
    ref = jobs.create_job(conn, [SOURCE], RunMode.UPDATE, job_kind=datasetjob.JOB_KIND)
    conn.commit()
    datasetjob.run_dataset_interpret_job_once(conn, ref)
    return jobs.get_job(conn, ref)


def _stored(conn) -> int:
    return conn.execute(
        "SELECT count(*) FROM generic_record AS r "
        "  JOIN dataset_definition AS d "
        "    ON d.dataset_definition_id = r.dataset_definition_id "
        " WHERE d.dataset_key = ?", (DATASET_KEY,)).fetchone()[0]


def test_every_page_pair_refused_fails_and_stores_nothing(conn):
    _a_crawl_that_stored(conn, {1: _disagreeing(1), 38: _disagreeing(38)})

    job = _interpret(conn)

    assert _stored(conn) == 0, "precondition: the reader refused both pairs"
    assert job["status"] == JobStatus.FAILED.value, job
    assert job["error_summary"].startswith(
        "Nothing was stored: every one of the 2 page pair(s) read was refused, and no "
        "run is recorded as read. The first: "), job["error_summary"]
    assert "LanguagesDisagree" in job["error_summary"], (
        "the summary does not say why, so he cannot tell a site change from a parser "
        "defect without opening the log")
    assert RUN not in datasetjob.interpreted_runs(conn, SOURCE)
    assert RUN in dict(datasetjob.runs_to_interpret(conn, SOURCE)), (
        "the refused run is not offered to the next interpretation")


def test_a_refused_page_beside_a_good_one_completes_with_errors(conn):
    _a_crawl_that_stored(conn, {1: _good(1), 38: _disagreeing(38)})

    job = _interpret(conn)

    assert _stored(conn) == 10, "page 1's ten establishments were not stored"
    assert job["status"] == JobStatus.COMPLETED_WITH_ERRORS.value, job
    assert job["error_summary"] == (
        "1 of 2 page pair(s) were refused, and the runs holding them are not recorded as "
        "read. The log lists the refusals."), job["error_summary"]
    assert RUN not in datasetjob.interpreted_runs(conn, SOURCE)
    logged = " ".join(row["message"] for row in jobs.job_logs(conn, job["job_ref"]))
    assert "LanguagesDisagree" in logged, "the refusal is not named in the job log"


def test_two_good_pages_complete_and_the_run_is_read(conn):
    """The ending a clean run always had, through the same real path."""
    _a_crawl_that_stored(conn, {1: _good(1), 38: _good(38)})

    job = _interpret(conn)

    assert _stored(conn) == 20
    assert (job["status"], job["error_summary"]) == (JobStatus.COMPLETED.value, None)
    assert datasetjob.interpreted_runs(conn, SOURCE) == {RUN: 4}


def test_approve_returns_what_it_read_wrote_and_refused(conn):
    """THE JOB DECIDES FROM THIS, so each number is checked against the pages: two pairs
    read, page 1's written, page 38's refused once and named."""
    _a_crawl_that_stored(conn, {1: _good(1), 38: _disagreeing(38)})

    done = contractors.approve(conn, directories.get(SOURCE), RUN)

    assert (done.pairs, done.made, len(done.refused)) == (2, 1, 1), done
    key, why = done.refused[0]
    assert "page=38" in key and "LanguagesDisagree" in why, done.refused
