"""A directory whose crawl stored pages, and that has no dataset yet, is owed an interpretation.

MEASURED ON HIS OFFICE MACHINE. The Oman register (`oman_tenderboard`) crawled to COMPLETED
and stored 2,838 pages, and no `dataset_definition` was ever born: only an interpretation
creates one, and nothing had interpreted them. `/api/sources` listed the site as
`kind: "directory"` with `observations: 0` and `work_waiting.interpret` forced to `None`,
because `_work_waiting` was handed no dataset key for a directory row and returned before
it asked. The Data page draws a card only for rows or for a press that is owed, so the site
appeared nowhere and nothing could start the step that would have made it appear.

THE OTHER HALF IS A PRESS THAT CAN ONLY FAIL. A directory whose one crawl stored nothing
has no evidence to read, and `datasetjob.runs_to_interpret` refuses it with
`NothingToInterpret` (issue 1196 records the same trap). So "owed" here means a collecting
job finished since the last interpretation AND the runner would find pages to read.

Every row is written into the real schema (`dbmod.migrate`), and the answer is read from
the route the panel reads.
"""
from __future__ import annotations

import shutil

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex import datasetjob, directories, directoryjob, jobs  # noqa: E402
from scrapex import db as dbmod  # noqa: E402
from scrapex.config import MANIFEST_FILE  # noqa: E402
from scrapex.vocab import JobStatus  # noqa: E402
from scrapex.webui.app import create_app  # noqa: E402

OMAN = "oman_tenderboard"
MUQAWIL = "muqawil_org"


@pytest.fixture()
def warehouse(tmp_path):
    path = tmp_path / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    try:
        yield conn, path, manifest
    finally:
        conn.close()


def _job(conn, site: str, kind: str, status: JobStatus, finished_at: str | None,
         pages: int = 0, checkpoint: dict | None = None) -> str:
    """A job of `kind` for `site`, settled at `status`, with `pages` stored under its ref.

    THE REF IS THE ONE A PARTITIONED CRAWL WRITES: `job-<job_ref>-<cell>-a<n>`, which is
    what job 191 stored the Oman pages under (`job-job_30663cbedfce-whole-aN`).
    """
    ref = jobs.create_job(conn, [site], job_kind=kind, checkpoint=checkpoint)
    conn.execute("UPDATE crawl_job SET status = ?, finished_at = ? WHERE job_ref = ?",
                 (status.value, finished_at, ref))
    for page in range(pages):
        conn.execute(
            "INSERT INTO generic_page_snapshot "
            "  (source_url, content_type, html_content, content_hash, crawl_run_ref) "
            "VALUES (?, 'text/html', X'00', ?, ?)",
            (f"https://{site}.test/list?page={page}", f"hash-{ref}-{page}",
             f"job-{ref}-whole-a1"))
    conn.commit()
    return ref


def _row(path, manifest, site: str) -> dict:
    answer = TestClient(create_app(path, manifest_path=manifest)).get("/api/sources")
    assert answer.status_code == 200, answer.text
    rows = [row for row in answer.json()["sources"]
            if row.get("site_key") == site or row["source_key"] == site]
    assert len(rows) == 1, f"{site} is listed {len(rows)} times: {rows}"
    return rows[0]


def test_a_completed_crawl_that_stored_pages_is_owed_its_interpretation(warehouse):
    """THE OMAN STATE. A listing crawl COMPLETED with its pages on disk, nothing has
    interpreted them, and no dataset exists -- so the row must say a press is owed, in the
    shape the dataset rows already speak, or the panel has nothing to draw."""
    conn, path, manifest = warehouse
    _job(conn, OMAN, directoryjob.JOB_KIND, JobStatus.COMPLETED,
         "2026-10-02T09:15:00Z", pages=4)

    row = _row(path, manifest, OMAN)

    assert row["kind"] == "directory", row
    assert row["work_waiting"]["interpret"] == {
        "crawl_finished_at": "2026-10-02T09:15:00Z", "interpreted_at": None}, (
        "a completed crawl stored pages nobody has interpreted and the route says "
        f"nothing is owed, so the panel draws no card and no control: {row['work_waiting']}")
    # ZERO STAYS THE HONEST NUMBER. Pages are not rows; the card says the first in words.
    assert row["observations"] == 0 and row["products"] == 0, row


def test_a_crawl_that_stored_nothing_is_not_offered_a_press_that_would_fail(warehouse):
    """A FINISH TIME IS NOT EVIDENCE. A crawl that failed before its first page has a
    finish time later than any interpretation, and the press it would earn is refused by
    the runner -- asserted here too, so this test is tied to the refusal it guards."""
    conn, path, manifest = warehouse
    _job(conn, OMAN, directoryjob.JOB_KIND, JobStatus.FAILED,
         "2026-10-02T09:15:00Z", pages=0)

    row = _row(path, manifest, OMAN)

    with pytest.raises(datasetjob.NothingToInterpret):
        datasetjob.runs_to_interpret(conn, OMAN)
    assert row["work_waiting"]["interpret"] is None, (
        "the route offers an interpretation of a source that stored nothing, and the "
        f"runner refuses exactly that press: {row['work_waiting']}")
    assert row["observations"] == 0


def test_a_completed_interpretation_settles_it(warehouse):
    """AFTER THE PRESS, NOTHING IS OWED. An interpretation that completed after the crawl
    has read its pages; the badge going on saying otherwise is the stale card the badge
    was built to replace."""
    conn, path, manifest = warehouse
    crawl = _job(conn, OMAN, directoryjob.JOB_KIND, JobStatus.COMPLETED,
                 "2026-10-02T09:15:00Z", pages=4)
    _job(conn, OMAN, datasetjob.JOB_KIND, JobStatus.COMPLETED, "2026-10-02T10:00:00Z",
         checkpoint={"runs_read": {f"job-{crawl}": 4}})

    row = _row(path, manifest, OMAN)

    assert row["work_waiting"]["interpret"] is None, row["work_waiting"]


@pytest.mark.parametrize("status", [JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.PAUSED])
def test_an_interpretation_on_its_way_is_said_on_the_directory_row(warehouse, status):
    """THE CARD HANGS ON THIS FLAG WHILE ONE IS LIVE. `interpret` is withheld for as long as
    an interpretation of the source is on its way (#1042), and a directory row has no rows
    to keep its card drawn, so `interpretation_live` is what the panel reads instead
    (`app.js` `storedNotRows`). A row that dropped it would lose its card the moment he
    pressed it, and for as long as a paused one waits on him."""
    conn, path, manifest = warehouse
    _job(conn, OMAN, directoryjob.JOB_KIND, JobStatus.COMPLETED,
         "2026-10-02T09:15:00Z", pages=4)
    _job(conn, OMAN, datasetjob.JOB_KIND, status, None)

    row = _row(path, manifest, OMAN)

    assert row["kind"] == "directory", row
    assert row["work_waiting"]["interpretation_live"] is True, (
        f"a {status.value} interpretation is not said on the directory row, so its card "
        f"has nothing left to stand on: {row['work_waiting']}")
    assert row["work_waiting"]["interpret"] is None, row["work_waiting"]
    assert row["observations"] == 0, row


def test_a_crawl_still_running_is_not_offered_yet(warehouse):
    """THE PAGES OF A RUNNING CRAWL ARE NOT A PRESS YET. Interpreting while the crawl still
    writes would read half a run and contend for the write lock, and the dataset rows have
    never been offered one mid-crawl either: the badge waits for a finish time."""
    conn, path, manifest = warehouse
    _job(conn, OMAN, directoryjob.JOB_KIND, JobStatus.RUNNING, None, pages=4)

    row = _row(path, manifest, OMAN)

    assert row["work_waiting"]["interpret"] is None, row["work_waiting"]


def test_a_failed_crawl_that_stored_pages_is_owed_one(warehouse):
    """THE PAGES OF A FAILED CRAWL ARE STILL ON DISK. A crawl that died part-way bought what
    it stored, and an interpretation reads them without a request."""
    conn, path, manifest = warehouse
    _job(conn, OMAN, directoryjob.JOB_KIND, JobStatus.FAILED,
         "2026-10-02T09:15:00Z", pages=2)

    row = _row(path, manifest, OMAN)

    assert row["work_waiting"]["interpret"] is not None, row["work_waiting"]


def test_an_older_crawls_pages_are_owed_when_the_newest_stored_nothing(warehouse):
    """THE QUESTION IS WHETHER ANY RUN HOLDS UNREAD PAGES, not whether the newest did.
    A second crawl that failed at once must not hide the first one's harvest."""
    conn, path, manifest = warehouse
    _job(conn, OMAN, directoryjob.JOB_KIND, JobStatus.COMPLETED,
         "2026-10-01T09:15:00Z", pages=3)
    _job(conn, OMAN, directoryjob.JOB_KIND, JobStatus.FAILED,
         "2026-10-02T09:15:00Z", pages=0)

    row = _row(path, manifest, OMAN)

    assert row["work_waiting"]["interpret"] == {
        "crawl_finished_at": "2026-10-02T09:15:00Z", "interpreted_at": None}, (
        row["work_waiting"])


def test_pages_an_interpretation_read_are_not_owed_again_by_an_empty_crawl(warehouse):
    """READ IS READ, and a later finish time does not unread it. An interpretation read the
    first crawl to the end; a second crawl then failed before its first page. The finish
    times say a crawl ended after the last interpretation, and there is still nothing
    unread -- the ledger the runner keeps (`datasetjob.interpreted_runs`) says so, and the
    badge asks the runner rather than the clock alone."""
    conn, path, manifest = warehouse
    crawl = _job(conn, OMAN, directoryjob.JOB_KIND, JobStatus.COMPLETED,
                 "2026-10-01T09:15:00Z", pages=3)
    _job(conn, OMAN, datasetjob.JOB_KIND, JobStatus.COMPLETED, "2026-10-01T10:00:00Z",
         checkpoint={"runs_read": {f"job-{crawl}": 3}})
    _job(conn, OMAN, directoryjob.JOB_KIND, JobStatus.FAILED,
         "2026-10-02T09:15:00Z", pages=0)

    row = _row(path, manifest, OMAN)

    assert datasetjob.runs_to_interpret(conn, OMAN) == []
    assert row["work_waiting"]["interpret"] is None, row["work_waiting"]


def test_a_directory_with_no_dataset_is_never_offered_a_profile_sweep(warehouse):
    """WITH NO ROWS, "THE MISSING PROFILES" ARE ALL OF THEM. muqawil's listing names its
    contractors in the sighting ledger; on a warehouse with no dataset every one of them is
    rowless, so a `profiles` figure here would offer the whole frontier -- about 35,700
    pages and 87 hours, the press his ruling keeps off the button -- on a card that has no
    profiles control. The interpretation is owed first."""
    conn, path, manifest = warehouse
    directory = directories.get(MUQAWIL)
    for contractor in ("9001", "9002", "9003"):
        conn.execute(
            "INSERT INTO dataset_sighting (dataset_key, external_id, seen_count) "
            "VALUES (?, ?, 1)", (directory.dataset_key, contractor))
    _job(conn, MUQAWIL, directoryjob.JOB_KIND, JobStatus.COMPLETED,
         "2026-10-02T09:15:00Z", pages=3)

    row = _row(path, manifest, MUQAWIL)

    assert row["kind"] == "directory", row
    assert row["work_waiting"]["interpret"] is not None, row["work_waiting"]
    assert row["work_waiting"]["profiles"] is None, (
        "a site with no dataset is told every sighted contractor needs a profile page: "
        f"{row['work_waiting']}")


def test_the_press_the_card_offers_is_one_the_route_queues(warehouse):
    """THE KEY ON THE ROW IS THE KEY THE ROUTE TAKES, with the kind named. Without the kind
    the route infers a crawl and goes back to the site for pages already on disk."""
    conn, path, manifest = warehouse
    _job(conn, OMAN, directoryjob.JOB_KIND, JobStatus.COMPLETED,
         "2026-10-02T09:15:00Z", pages=4)
    key = _row(path, manifest, OMAN)["source_key"]

    answer = TestClient(create_app(path, manifest_path=manifest)).post(
        "/api/jobs", json={"source_keys": [key], "run_mode": "update",
                           "job_kind": datasetjob.JOB_KIND})

    assert answer.status_code == 200, answer.text
    kind = conn.execute("SELECT job_kind FROM crawl_job WHERE job_ref = ?",
                        (answer.json()["job_ref"],)).fetchone()[0]
    assert kind == datasetjob.JOB_KIND
