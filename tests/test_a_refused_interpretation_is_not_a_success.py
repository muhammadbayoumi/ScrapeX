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
from scrapex.extract.tvtc_plans import LICENCE_DATASET_KEY
from scrapex.sites.tvtc import PLANS_PATH, PLANS_SITE_KEY, listing_url
from scrapex.snapshotbody import encode
from scrapex.vocab import JobControl, JobStatus, RunMode
from test_tvtc_licences import _doc, _first_establishment_rows

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


def _a_crawl_that_stored(conn, pages: dict[int, tuple[str | None, str]], crawl: str = CRAWL,
                         source: str = SOURCE, path: str | None = None) -> None:
    """A finished TVTC crawl whose run holds these page pairs, after the site registration
    the crawl does first. THROUGH THE REAL TABLES, because `runs_holding_pages` and
    `contractors._pairs` are queries over them. A second `crawl` is a second, newer run; an
    English half of `None` is not stored, as when a crawl kept only the Arabic page."""
    directory = directories.get(source)
    catalog.register_site(conn, SiteCreate(
        site_key=directory.key, display_name=directory.display_name,
        base_url=directory.base_url))
    conn.execute(
        "INSERT INTO crawl_job (job_ref, run_mode, source_keys, job_kind, status) "
        "VALUES (?,?,?,?,?)",
        (crawl, RunMode.UPDATE.value, f'["{source}"]', "directory_crawl",
         JobStatus.COMPLETED.value))
    for page, (english, arabic) in pages.items():
        for locale, body in (("en", english), ("ar", arabic)):
            if body is None:
                continue
            url = listing_url(locale=locale, page=page, **({"path": path} if path else {}))
            blob, codec, dict_id = encode(conn, body, label=None)
            conn.execute(
                "INSERT INTO generic_page_snapshot (source_url, html_content, "
                " content_hash, crawl_run_ref, html_codec, html_dict_id, captured_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (url, blob, url, f"job-{crawl}-whole-a1", codec, dict_id,
                 "2026-10-17T10:00:00Z"))
    conn.commit()


def _interpret(conn) -> dict:
    ref = jobs.create_job(conn, [SOURCE], RunMode.UPDATE, job_kind=datasetjob.JOB_KIND)
    conn.commit()
    datasetjob.run_dataset_interpret_job_once(conn, ref)
    return jobs.get_job(conn, ref)


def _stored(conn, dataset_key: str = DATASET_KEY) -> int:
    return conn.execute(
        "SELECT count(*) FROM generic_record AS r "
        "  JOIN dataset_definition AS d "
        "    ON d.dataset_definition_id = r.dataset_definition_id "
        " WHERE d.dataset_key = ?", (dataset_key,)).fetchone()[0]


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


def test_nothing_stored_beside_a_pair_with_no_english_half_is_not_every_pair_refused(conn):
    """HIS "EVERY" IS LITERAL (#1738), and a pair with no English half is skipped, never
    refused (`approve` reads nothing without the English label). So one refused pair beside
    one skipped pair is not "every page pair refused": the job completes with errors,
    though nothing was stored. Whether it should fail instead is #2018; this pins what the
    ending says until that is decided, and guards the `refused == pairs` half of the test
    for "every" (the gate of #1999 found nothing else does)."""
    _a_crawl_that_stored(conn, {1: _disagreeing(1), 38: (None, json.dumps(_page(38, "ar")))})

    job = _interpret(conn)

    assert _stored(conn) == 0
    assert (job["status"], job["error_summary"]) == (
        JobStatus.COMPLETED_WITH_ERRORS.value,
        "1 of 2 page pair(s) were refused, and the runs holding them are not recorded as "
        "read. The log lists the refusals."), job
    assert RUN not in datasetjob.interpreted_runs(conn, SOURCE)


def test_a_licence_refused_through_the_real_job_completes_with_errors(conn):
    """A DERIVED DATASET'S REFUSAL ENDS THE JOB TOO, through the real reader (ES-5).

    `tvtc_training_plans` is the one directory with a derived reader: each establishment's
    licence, read from the same page as its plans. Here one establishment's plans disagree
    about its licence, so the licence reader refuses the page while its twenty plans are
    written. Until the gate of #1999, only a fake `approve` proved such a refusal reaches
    the ending; reported as a warning instead, the job would complete and retire the run,
    and that page's licences would never be read again."""
    english, arabic = _doc("en"), _doc("ar")
    _first_establishment_rows(arabic)[-1]["establishment"]["license"]["end_date"] = "2099-01-01"
    plans = directories.get(PLANS_SITE_KEY)
    _a_crawl_that_stored(conn, {1: (json.dumps(english), json.dumps(arabic))},
                         crawl="job_plans", source=PLANS_SITE_KEY, path=PLANS_PATH)

    ref = jobs.create_job(conn, [PLANS_SITE_KEY], RunMode.UPDATE,
                          job_kind=datasetjob.JOB_KIND)
    conn.commit()
    datasetjob.run_dataset_interpret_job_once(conn, ref)
    job = jobs.get_job(conn, ref)

    assert _stored(conn, plans.dataset_key) == 20, "precondition: the plans were written"
    assert _stored(conn, LICENCE_DATASET_KEY) == 0
    assert job["status"] == JobStatus.COMPLETED_WITH_ERRORS.value, job
    assert job["error_summary"].startswith("1 of 1 page pair(s) were refused"), job
    assert "job-job_plans" not in datasetjob.interpreted_runs(conn, PLANS_SITE_KEY)


def test_two_good_pages_complete_and_the_run_is_read(conn):
    """The ending a clean run always had, through the same real path."""
    _a_crawl_that_stored(conn, {1: _good(1), 38: _good(38)})

    job = _interpret(conn)

    assert _stored(conn) == 20
    assert (job["status"], job["error_summary"]) == (JobStatus.COMPLETED.value, None)
    assert datasetjob.interpreted_runs(conn, SOURCE) == {RUN: 4}


def _paused_after_the_first_run_then_resumed(conn, monkeypatch) -> dict:
    """Interpret with the real `approve`, pressing Pause as the first run ends, then resume.

    A PAUSE IS A RE-ENTRY: the next entry starts `run_dataset_interpret_job_once` afresh,
    with the runs the first entry recorded as read left out of its plan. The control is
    written where `set_control` writes it, and the row re-queued the way a Resume does
    (`tests/test_a_job_may_interpret_what_a_crawl_stored.py` does the same)."""
    real = contractors.approve
    ref = jobs.create_job(conn, [SOURCE], RunMode.UPDATE, job_kind=datasetjob.JOB_KIND)
    conn.commit()
    pressed: list[str] = []

    def pauses_as_the_first_run_ends(conn_, directory, run_ref, **kwargs):
        done = real(conn_, directory, run_ref, **kwargs)
        # ONCE: a refused first run is read again by the resumed entry, which must go on.
        if run_ref == "job-job_first" and not pressed:
            pressed.append(run_ref)
            conn_.execute("UPDATE crawl_job SET control = ? WHERE job_ref = ?",
                          (JobControl.PAUSE.value, ref))
            conn_.commit()
        return done

    monkeypatch.setattr(contractors, "approve", pauses_as_the_first_run_ends)
    paused = datasetjob.run_dataset_interpret_job_once(conn, ref)
    assert paused["status"] == JobStatus.PAUSED.value, (
        f"precondition: the walk did not stop between its two runs: {paused}")
    jobs._update(conn, paused["job_id"], status=JobStatus.QUEUED.value, finished_at=None)
    conn.commit()
    datasetjob.run_dataset_interpret_job_once(conn, ref)
    return jobs.get_job(conn, ref)


def test_a_resumed_walk_ends_on_what_the_whole_job_stored(conn, monkeypatch):
    """THE ENDING IS THE JOB'S, NOT ITS LAST ENTRY'S (the merge gate of #1999).

    The first entry stores run 1's ten establishments and is paused; the resumed entry
    reads only run 2, whose one pair is refused. Counted per entry, the job ended FAILED,
    "Nothing was stored", beside the ten rows its first entry wrote."""
    _a_crawl_that_stored(conn, {1: _good(1)}, crawl="job_first")
    _a_crawl_that_stored(conn, {38: _disagreeing(38)}, crawl="job_second")

    job = _paused_after_the_first_run_then_resumed(conn, monkeypatch)

    assert _stored(conn) == 10, "precondition: run 1's ten establishments are stored"
    assert (job["status"], job["error_summary"]) == (
        JobStatus.COMPLETED_WITH_ERRORS.value,
        "1 of 2 page pair(s) were refused, and the runs holding them are not recorded as "
        "read. The log lists the refusals."), job
    assert set(datasetjob.interpreted_runs(conn, SOURCE)) == {"job-job_first"}


def test_a_refused_run_read_again_by_the_resumed_entry_counts_once(conn, monkeypatch):
    """A REFUSED RUN STAYS UNREAD, SO THE RESUMED ENTRY READS IT AGAIN, and the job's
    figure counts it once: its second reading replaces its first. Both runs refused, so
    the job stored nothing and fails, naming two pairs, not three."""
    _a_crawl_that_stored(conn, {38: _disagreeing(38)}, crawl="job_first")
    _a_crawl_that_stored(conn, {1: _disagreeing(1)}, crawl="job_second")

    job = _paused_after_the_first_run_then_resumed(conn, monkeypatch)

    assert _stored(conn) == 0
    assert job["status"] == JobStatus.FAILED.value, job
    assert job["error_summary"].startswith(
        "Nothing was stored: every one of the 2 page pair(s) read was refused, and no "
        "run is recorded as read. The first: "), job["error_summary"]
    assert "page=38" in job["error_summary"], (
        "the first refusal of the job is its first entry's, page 38: "
        f"{job['error_summary']}")
    assert datasetjob.interpreted_runs(conn, SOURCE) == {}


def test_approve_returns_what_it_read_wrote_and_refused(conn):
    """THE JOB DECIDES FROM THIS, so each number is checked against the pages: two pairs
    read, page 1's written, page 38's refused once and named."""
    _a_crawl_that_stored(conn, {1: _good(1), 38: _disagreeing(38)})

    done = contractors.approve(conn, directories.get(SOURCE), RUN)

    assert (done.pairs, done.made, len(done.refused)) == (2, 1, 1), done
    key, why = done.refused[0]
    assert "page=38" in key and "LanguagesDisagree" in why, done.refused
