"""A stopped crawl's pages must be usable by the next one, and one line made them not.

HIS INSTRUCTION, 2026-09-05: «عاوزين ايضا الاستفادة من ما تم زحفة فى حالة الالغاء».

MEASURED TWICE IN THREE DAYS, on his own warehouse:

    job_925080aad843   cancelled 2026-09-05T05:06:20Z holding 3,138 stored readings
    job_6eb28381bf56   started   2026-09-06 and re-fetched 3,429 of the same pages

The same work, bought twice: about four hours and ~3,400 requests at muqawil.org for
nothing.

`snapshotcrawl.already_stored` makes resume free and says the design out loud -- the run
ref IS the resume key, because *"the alternative is a `resuming` flag, and a flag is a
second place for the two to disagree"* -- and `crawl_to_snapshots` calls the ref *"the
operator's label"* while `run_id` carries the run's identity (`R-54`). Then
`directoryjob` took the label away from the operator with `run_ref = f"job-{job_ref}"`.
That is right for a pause and a re-pick, and it is exactly why a CANCEL is different:
`cancelled` is terminal, no job is ever given that ref again, and the pages under it
could never be recognised by anything.

TWO PROPERTIES DECIDE WHETHER THIS IS SAFE, and both are asserted below rather than
argued: a FINISHED run must not be inheritable, because skipping everything it stored
would be a crawl that reads nothing and reports success; and a `full_rebuild` must not
inherit at all, because that mode exists to re-read.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex import db as dbmod, directoryjob, jobs  # noqa: E402
from scrapex.config import MANIFEST_FILE  # noqa: E402
from scrapex.vocab import JobStatus, RunMode  # noqa: E402
from scrapex.webui.app import create_app  # noqa: E402

SITE = "muqawil_org"


@pytest.fixture()
def conn(tmp_path):
    connection = dbmod.connect(tmp_path / "harvest.db")
    dbmod.migrate(connection)
    connection.execute(
        "INSERT INTO source_site (source_key, source_name, base_url, platform) "
        "VALUES (?, 'muqawil.org', 'https://muqawil.org', 'directory')", (SITE,))
    connection.commit()
    try:
        yield connection
    finally:
        connection.close()


def _stopped_run(connection: sqlite3.Connection, status: JobStatus,
                 pages: int = 3) -> str:
    """A finished-or-stopped directory job with `pages` stored under its ref."""
    ref = jobs.create_job(connection, [SITE], job_kind=directoryjob.JOB_KIND)
    connection.execute(
        "UPDATE crawl_job SET status = ?, finished_at = '2026-09-05T05:06:20Z' "
        " WHERE job_ref = ?", (status.value, ref))
    for page in range(pages):
        connection.execute(
            "INSERT INTO generic_page_snapshot "
            "  (source_url, content_type, html_content, content_hash, crawl_run_ref) "
            "VALUES (?, 'text/html', X'00', ?, ?)",
            (f"https://muqawil.org/en/contractors?page={page}", f"hash-{ref}-{page}",
             f"job-{ref}-riyadh-a1"))
    connection.commit()
    return f"job-{ref}"


def test_a_stopped_run_holding_pages_is_offered(conn):
    """THE ONE FACT THE CARD NEEDS, and it carries the count and the moment so the owner
    decides rather than the panel."""
    ref = _stopped_run(conn, JobStatus.CANCELLED, pages=4)

    offered = directoryjob.resumable_runs(conn, SITE)

    assert [one["run_ref"] for one in offered] == [ref], offered
    assert offered[0]["readings"] == 4, offered[0]
    assert offered[0]["status"] == JobStatus.CANCELLED.value
    assert offered[0]["stopped_at"] == "2026-09-05T05:06:20Z"


def test_a_finished_run_is_not_offered(conn):
    """THE LOAD-BEARING EXCLUSION. Inheriting a completed run's ref would make the next
    crawl skip every page that run stored -- a crawl that reads nothing and reports
    success, which is the trap issue 642 rejected under "make the ref per-source"."""
    _stopped_run(conn, JobStatus.COMPLETED, pages=9)

    assert directoryjob.resumable_runs(conn, SITE) == [], (
        "a finished run is offered as resumable, so continuing it would read nothing "
        "and report success")


def test_a_run_that_stored_nothing_is_not_offered(conn):
    """An inner join is the filter: there is nothing to continue and no clause says so."""
    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    conn.execute("UPDATE crawl_job SET status = ? WHERE job_ref = ?",
                 (JobStatus.CANCELLED.value, ref))
    conn.commit()

    assert directoryjob.resumable_runs(conn, SITE) == []


def test_the_runner_stores_under_the_inherited_ref(conn):
    """The whole point: the next crawl writes where `already_stored` will look."""
    inherited = _stopped_run(conn, JobStatus.CANCELLED)
    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND,
                          checkpoint={"resume_run_ref": inherited})
    conn.commit()

    job = jobs.get_job(conn, ref)
    run_ref, said = directoryjob._run_ref_for(job, ref)

    assert run_ref == inherited, run_ref
    assert said == inherited, "the runner cannot say it inherited, so the log cannot"


def test_without_a_checkpoint_the_ref_is_the_jobs_own(conn):
    """The default is unchanged BY CONSTRUCTION. A crawl that inherited by accident would
    skip pages nobody asked it to skip."""
    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    conn.commit()

    run_ref, said = directoryjob._run_ref_for(jobs.get_job(conn, ref), ref)

    assert run_ref == f"job-{ref}"
    assert said == "", "it claims to have inherited a ref nobody gave it"


def test_a_full_rebuild_may_not_inherit(conn):
    """`full_rebuild` EXISTS TO RE-READ. A ref that made it skip what is on disk would
    turn it into a no-op that reports success -- worse than the defect being fixed. It
    refuses rather than ignoring, because silently dropping the request would leave the
    owner believing a rebuild had read the site."""
    inherited = _stopped_run(conn, JobStatus.CANCELLED)
    ref = jobs.create_job(conn, [SITE], run_mode=RunMode.FULL_REBUILD,
                          job_kind=directoryjob.JOB_KIND,
                          checkpoint={"resume_run_ref": inherited})
    conn.commit()

    with pytest.raises(ValueError, match="may not inherit"):
        directoryjob._run_ref_for(jobs.get_job(conn, ref), ref)


def test_the_runner_really_crawls_under_the_inherited_ref(conn, monkeypatch):
    """A MUTATION FOUND THIS GUARD MISSING, and the shape of the hole is the lesson.

    The tests above call `_run_ref_for` directly, so replacing its CALL SITE in
    `run_directory_crawl_job_once` with the old `f"job-{job_ref}"` changed nothing any of
    them could see: the helper was proven and the wiring was not. That is the same
    vacuity the interpret-count guard had, one file over.

    SO THIS DRIVES THE RUNNER and reads what it wrote. `contractors.crawl` is stubbed to
    raise the moment it is reached -- the two log lines are committed before it is called,
    which is itself the property being relied on -- and the ref it was handed is captured
    on the way past.
    """
    inherited = _stopped_run(conn, JobStatus.CANCELLED, pages=3)
    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND,
                          checkpoint={"resume_run_ref": inherited})
    conn.commit()
    handed: list[str] = []

    def refuse_to_crawl(*args, **kwargs):
        # POSITIONAL, WHICH IS WHY THIS READS BOTH. `directoryjob` calls
        # `contractors.crawl(conn, directory, beating, fetcher, run_ref, ...)`, so a stub
        # reading only `kwargs` captures `None` and the assertion below fails for the
        # wrong reason -- which is exactly what it did on the first run.
        handed.append(str(kwargs["run_ref"] if "run_ref" in kwargs else args[4]))
        raise RuntimeError("stopped on purpose, after the ref was chosen")

    monkeypatch.setattr(directoryjob.contractors, "crawl", refuse_to_crawl)

    with pytest.raises(RuntimeError, match="on purpose"):
        directoryjob.run_directory_crawl_job_once(conn, ref)

    assert handed == [inherited], (
        f"the crawl was handed {handed}, not the inherited ref {inherited!r} -- so the "
        "pages under it will be fetched again")
    logged = " | ".join(row["message"] for row in jobs.job_logs(conn, ref))
    assert f"continuing the evidence of {inherited}" in logged, (
        f"the run does not say it inherited a ref, so a short run reads as a short "
        f"site: {logged!r}")
    # AND THE COUNT IS REAL. `already_stored` is an exact match on the ref and a
    # partitioned crawl stores under none of them bare -- measured 0 against 802 URLs on
    # his warehouse -- so the wrong helper here prints a confident `0 page URL(s)`.
    assert "3 page URL(s)" in logged, (
        f"the line reports the wrong number of held URLs: {logged!r}")


def test_a_re_picked_job_says_it_is_resuming(conn, monkeypatch):
    """ISSUE 606, AND IT IS THE HALF THE INHERITED-REF LINE DID NOT COVER.

    His crawl was at `running 7/56` with 2,859 pages stored; the engine was relaunched
    and the panel went to `preparing 0/56` with `Requests 0`. Nothing was lost -- the job
    was re-dispatched and RE-PROVED its closed cells from disk at zero network requests.
    But the opening lines were identical either way, so that pair of numbers reads as a
    stalled crawl while being the resume working perfectly. He watched it and had to ask.

    NO INHERITED REF HERE. This is a job re-picked under its OWN ref, which is the case
    he actually met, and the first version of this line fired only on an inheritance.
    """
    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    conn.commit()
    # Pages already under this job's own ref, the way a killed run leaves them.
    for page in range(4):
        conn.execute(
            "INSERT INTO generic_page_snapshot "
            "  (source_url, content_type, html_content, content_hash, crawl_run_ref) "
            "VALUES (?, 'text/html', X'00', ?, ?)",
            (f"https://muqawil.org/en/contractors?page={page}", f"h-{page}",
             f"job-{ref}-riyadh-a1"))
    conn.commit()
    monkeypatch.setattr(directoryjob.contractors, "crawl",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stop")))

    with pytest.raises(RuntimeError, match="stop"):
        directoryjob.run_directory_crawl_job_once(conn, ref)

    logged = " | ".join(row["message"] for row in jobs.job_logs(conn, ref))
    assert "resuming:" in logged, (
        f"a re-picked job does not say it is resuming, so `0/56 · Requests 0` still "
        f"reads as a stalled crawl: {logged!r}")
    assert "4 page URL(s)" in logged, f"it does not say what it found: {logged!r}"
    assert "not fetched" in logged and "zero requests" in logged, (
        f"the line does not explain the pair of numbers he asked about: {logged!r}")
    assert "continuing the evidence" not in logged, (
        "it claims to have inherited a ref nobody gave it")


def test_a_first_run_says_nothing_about_resuming(conn, monkeypatch):
    """A LINE THAT IS ALWAYS THERE IS A LINE NOBODY READS, and a first run has nothing on
    disk to recognise. Silence here is what makes the resume line mean something."""
    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    conn.commit()
    monkeypatch.setattr(directoryjob.contractors, "crawl",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("stop")))

    with pytest.raises(RuntimeError, match="stop"):
        directoryjob.run_directory_crawl_job_once(conn, ref)

    logged = " | ".join(row["message"] for row in jobs.job_logs(conn, ref))
    assert "resuming:" not in logged, (
        f"a first run claims to be resuming: {logged!r}")


# ---- the route the control presses ------------------------------------------


@pytest.fixture()
def served(tmp_path):
    path = tmp_path / "harvest.db"
    connection = dbmod.connect(path)
    dbmod.migrate(connection)
    connection.execute(
        "INSERT INTO source_site (source_key, source_name, base_url, platform) "
        "VALUES (?, 'muqawil.org', 'https://muqawil.org', 'directory')", (SITE,))
    connection.commit()
    stopped = _stopped_run(connection, JobStatus.CANCELLED, pages=5)
    finished = _stopped_run(connection, JobStatus.COMPLETED, pages=7)
    connection.close()
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(path, manifest_path=manifest)), path, stopped, finished


def test_the_route_queues_a_crawl_that_continues_the_stopped_run(served):
    client, path, stopped, _finished = served

    queued = client.post("/api/jobs", json={
        "source_keys": [SITE], "run_mode": "update", "resume_run_ref": stopped})

    assert queued.status_code == 200, queued.text
    conn = sqlite3.connect(str(path))
    try:
        raw = conn.execute("SELECT checkpoint_json FROM crawl_job WHERE job_ref = ?",
                           (queued.json()["job_ref"],)).fetchone()[0]
    finally:
        conn.close()
    assert stopped in (raw or ""), (
        f"the ref never reached the job, so the crawl will store under its own and "
        f"re-fetch everything: {raw!r}")


def test_the_route_refuses_a_ref_nothing_is_stored_under(served):
    """A TYPO WOULD OTHERWISE QUEUE A CRAWL that stores its pages where nothing will look
    for them again -- the same unreachability this change exists to end."""
    client, _path, _stopped, _finished = served

    refused = client.post("/api/jobs", json={
        "source_keys": [SITE], "run_mode": "update",
        "resume_run_ref": "job-nothing-is-stored-under-this"})

    assert refused.status_code == 404, refused.text
    assert "nothing to continue" in refused.json()["detail"]


def test_the_route_refuses_to_continue_a_finished_run(served):
    """Offered by nothing, and refused if asked for anyway: a completed run's ref would
    make this crawl skip every page and report success."""
    client, _path, _stopped, finished = served

    refused = client.post("/api/jobs", json={
        "source_keys": [SITE], "run_mode": "update", "resume_run_ref": finished})

    assert refused.status_code == 409, refused.text
    assert "not resumable" in refused.json()["detail"]


def test_the_route_refuses_a_full_rebuild_that_would_skip_everything(served):
    """THE MESSAGE COMES FROM THE DOOR HE KNOCKED ON. The runner refuses this too, but a
    refusal that arrives as a failed job is a refusal he has to go and find."""
    client, _path, stopped, _finished = served

    refused = client.post("/api/jobs", json={
        "source_keys": [SITE], "run_mode": "full_rebuild",
        "resume_run_ref": stopped})

    assert refused.status_code == 400, refused.text
    assert "no-op that reports success" in refused.json()["detail"]


def test_the_sources_route_offers_the_stopped_run_to_the_card(served):
    """The panel can only draw it if the route sends it, and it must carry the count and
    the moment -- his decision, not the panel's."""
    client, _path, stopped, _finished = served

    rows = client.get("/api/sources").json()["sources"]
    cards = [row for row in rows if row.get("site_key") == SITE]

    assert cards, "muqawil is in no listing at all"
    offered = [row["work_waiting"]["resumable"] for row in cards
               if (row.get("work_waiting") or {}).get("resumable")]
    assert offered, f"no card was told about the stopped run: {cards}"
    assert offered[0]["run_ref"] == stopped
    assert offered[0]["readings"] == 5
    assert offered[0]["status"] == JobStatus.CANCELLED.value
