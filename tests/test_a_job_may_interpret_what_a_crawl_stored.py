"""The panel can turn a finished crawl's evidence into rows.

WHAT WAS ACTUALLY WRONG, and it is the largest `R-81` instance measured so far. His muqawil
listing crawl finished 2026-09-06T05:01:44Z, 56 of 56 cells, zero errors, 6,713 stored
pages. **Zero interpreted.** The newest `generic_ingestion` row was five days older than
the crawl and the card went on showing the 17,304 rows it showed before the crawl started.
`contractors.approve` was reachable from `scrapex contractors --approve` -- fourteen
occurrences -- and from no route, no job kind and no control. Interpreting a copy of that
warehouse afterwards took 21 minutes and moved coverage from 96.8% to 99.4%: 434
contractors already on disk.

WHAT THESE TESTS DO NOT DO. Not one opens a socket, and not one interprets a real page.
`contractors.approve` has its own suite; what is under test here is the three things a JOB
adds to it -- its report reaches the job log, progress is counted in page PAIRS, and a
pause or cancel is applied between two of them -- plus the two seams that would let a
mistake hide: a kind the database refuses, and a route that lets a caller name the wrong
one.
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from scrapex import contractors, datasetjob, directories, jobs
from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.vocab import JobControl, JobStatus, RunMode

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _log_goes_nowhere_real(tmp_path, monkeypatch):
    """`say` writes into `~/.scrapex/`, and a suite that writes to a real home is a suite
    that cannot be trusted twice."""
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


def _a_crawl_that_stored(conn, job_ref: str, pages: int, *,
                         source_key: str = "muqawil_org",
                         job_kind: str = "directory_crawl") -> None:
    """A finished directory crawl with `pages` snapshots under its own run ref.

    WRITTEN THROUGH THE REAL TABLES rather than through a fake, because what
    `latest_crawl_run_ref` reads IS the join between them -- a fixture that stubbed either
    side would leave the query untested while the test passed.
    """
    conn.execute(
        "INSERT INTO crawl_job (job_ref, run_mode, source_keys, job_kind, status) "
        "VALUES (?,?,?,?,?)",
        (job_ref, RunMode.UPDATE.value, f'["{source_key}"]', job_kind,
         JobStatus.COMPLETED.value))
    for n in range(pages):
        conn.execute(
            "INSERT INTO generic_page_snapshot (source_url, html_content, content_hash, "
            "crawl_run_ref) VALUES (?,?,?,?)",
            (f"https://muqawil.org/contractors?page={n}&ref={job_ref}", b"<html/>",
             f"{job_ref}-{n}", f"job-{job_ref}-cell-a1"))
    conn.commit()


def _queue(conn, source_key: str = "muqawil_org") -> str:
    ref = jobs.create_job(conn, [source_key], RunMode.UPDATE,
                          job_kind=datasetjob.JOB_KIND)
    conn.commit()
    return ref


class _Interpreter:
    """`contractors.approve`, faked down to the one thing the job wraps: it walks page
    pairs and asks `between_pages` before each."""

    def __init__(self, pairs: int = 6) -> None:
        self.pairs = pairs
        self.seen = 0
        self.run_ref: str | None = None

    def __call__(self, conn, directory, run_ref, *, ids=(), between_pages=None):
        self.run_ref = run_ref
        # THE PRODUCT'S OWN WORDING, because a stub that says something the real
        # `approve` does not is a stub a vocabulary guard cannot measure.
        contractors.say(f"approve {run_ref}: {self.pairs} page pair(s) to interpret")
        for index in range(self.pairs):
            if between_pages is not None and between_pages(index, self.pairs):
                raise contractors.CrawlStopped
            self.seen += 1
        contractors.say(f"approved {self.seen} page(s)")


# ---- the two registries and the database may not drift ----------------------

def test_the_kind_resolves_to_a_runner_and_the_database_accepts_it(conn):
    """THE THREE PLACES A KIND EXISTS, checked against each other.

    `SPECIALISED_RUNNERS` is the table, `JOB_KINDS` is derived from it, and the CHECK in
    `db/engine/schema.sql` (widened by `0018`) is what the row must satisfy. A kind in the
    Python and not in the constraint is accepted at the door and refused by SQLite; a kind
    in the constraint and not in the Python is a row no worker will ever pick up.
    """
    assert datasetjob.JOB_KIND in jobs.JOB_KINDS
    assert jobs.runner_for(datasetjob.JOB_KIND) is datasetjob.run_dataset_interpret_job_once

    ref = _queue(conn)
    assert conn.execute("SELECT job_kind FROM crawl_job WHERE job_ref = ?",
                        (ref,)).fetchone()[0] == datasetjob.JOB_KIND


def test_the_migration_carries_a_v17_database_and_keeps_its_references(tmp_path):
    """`0018` APPLIED THE WAY THE ENGINE APPLIES ONE, which is not the way a bare script
    runs.

    THE HARNESS THAT NEARLY LIED. Run as a plain `executescript` on a fresh connection,
    this migration leaves all four referencing tables pointing at `crawl_job_old` -- which
    it then drops. Run as `domain.py` runs it (isolation owned, `foreign_keys` off around
    it, `BEGIN IMMEDIATE` in front) the references survive. The first measurement said the
    migration was broken and it was the measurement that was.
    """
    old = subprocess.run([_git(), "show", "origin/main:db/engine/schema.sql"],
                         cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if old.returncode:
        pytest.skip("origin/main is not reachable in this checkout")

    path = tmp_path / "v17.db"
    seed = sqlite3.connect(path)
    seed.executescript(old.stdout)
    assert seed.execute("PRAGMA user_version").fetchone()[0] == 17
    seed.execute("INSERT INTO crawl_job (job_ref, run_mode, source_keys, job_kind) "
                 "VALUES ('old','update','[\"x\"]','directory_crawl')")
    seed.execute("INSERT INTO job_log_entry (job_id, level, message) "
                 "VALUES (1,'info','a line that must survive')")
    seed.commit()
    with pytest.raises(sqlite3.IntegrityError):
        seed.execute("INSERT INTO crawl_job (job_ref, run_mode, source_keys, job_kind) "
                     "VALUES ('n','update','[\"x\"]','dataset_interpret')")
    seed.rollback()
    seed.close()

    sql = (ROOT / "db/engine/migrations"
           / "0018_a_job_may_interpret_what_a_crawl_stored.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(path)
    conn.isolation_level = None
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript(f"BEGIN IMMEDIATE;\n{sql}")
    broken = conn.execute("PRAGMA foreign_key_check").fetchall()
    conn.execute("COMMIT")

    assert not broken, f"the migration left rows pointing at nothing: {broken[:3]}"
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 18
    assert conn.execute("SELECT count(*) FROM crawl_job").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM job_log_entry").fetchone()[0] == 1, (
        "the rebuild dropped the log rows that referenced the table it rebuilt")
    stale = [name for name, sql_text in conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql LIKE ?",
        ("%crawl_job_old%",))]
    assert not stale, (
        f"{stale} still REFERENCE `crawl_job_old`, which this migration drops. "
        "`legacy_alter_table = ON` did not take effect")
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name='ix_crawl_job_status'"
    ).fetchone(), "the rebuild took the index with the table and did not put it back"
    conn.execute("INSERT INTO crawl_job (job_ref, run_mode, source_keys, job_kind) "
                 "VALUES ('n','update','[\"x\"]','dataset_interpret')")
    conn.close()


def _git() -> str:
    return "git" if sys.platform != "win32" else "git"


# ---- choosing which run to read ---------------------------------------------

def test_it_reads_the_newest_crawl_that_actually_stored_pages(conn):
    """NEWEST BY JOB, AND ONLY IF IT STORED SOMETHING.

    A crawl that started and stored nothing is newer than the one that stored six
    thousand pages, and interpreting it would report `0 pages on disk` over a warehouse
    full of unread evidence.
    """
    _a_crawl_that_stored(conn, "job_old", pages=3)
    _a_crawl_that_stored(conn, "job_new", pages=5)
    conn.execute(
        "INSERT INTO crawl_job (job_ref, run_mode, source_keys, job_kind, status) "
        "VALUES ('job_empty','update','[\"muqawil_org\"]','directory_crawl','completed')")
    conn.commit()

    run_ref, pages = datasetjob.latest_crawl_run_ref(conn, "muqawil_org")

    assert run_ref == "job-job_new", (
        "it chose a crawl that stored nothing over one that stored pages")
    assert pages == 5


def test_a_profile_sweeps_pages_are_reachable_too(conn):
    """ISSUE 782, AND IT STRANDED 33 MINUTES OF HIS WORK.

    `latest_crawl_run_ref` filtered `job_kind = 'directory_crawl'`, so it could only ever
    choose a LISTING crawl. He fetched 938 profile pages in 33 minutes with zero
    failures, pressed nothing else, and `contractor_profiles` stayed at 17,393 rows --
    the only door the panel has looked straight past them.

    THE INTERPRETER WAS NEVER THE LIMIT. `contractors.approve` picks the profile
    candidate builder per page through `_contractor_of`, and its own comment records what
    it cost before that branch existed: *"running it over 712 stored profiles would have
    refused every one of them."* The capability was there and the SELECTION was blind.
    """
    _a_crawl_that_stored(conn, "job_listing", pages=4)
    _a_crawl_that_stored(conn, "job_profiles", pages=9, job_kind="profile_crawl")
    conn.commit()

    run_ref, pages = datasetjob.latest_crawl_run_ref(conn, "muqawil_org")

    assert run_ref == "job-job_profiles", (
        "the newest run that stored pages was a profile sweep and it was skipped, so "
        "the pages it fetched cannot become rows from the panel")
    assert pages == 9


def test_a_kind_that_collects_nothing_is_still_not_chosen(conn):
    """NAMED KINDS, NOT AN OPEN FILTER, and dropping the clause entirely would pass the
    test above. Measured on his warehouse: only `directory_crawl` and `profile_crawl`
    hold pages under a `job-` ref, and `organization_enrichment` holds none anywhere --
    but "none today" is not a guarantee. A future kind storing pages of a third shape
    would be fed to a parser built for two, and the failure would be a refusal per page
    rather than anything loud."""
    _a_crawl_that_stored(conn, "job_listing", pages=4)
    _a_crawl_that_stored(conn, "job_enrich", pages=9,
                         job_kind="organization_enrichment")
    conn.commit()

    run_ref, pages = datasetjob.latest_crawl_run_ref(conn, "muqawil_org")

    assert run_ref == "job-job_listing", (
        "a kind that is not one of the two collectors was chosen, so its pages reach a "
        "parser built for something else")
    assert pages == 4


def test_a_source_no_crawl_has_touched_is_refused_rather_than_called_a_success(conn):
    """A job that interpreted nothing and finished green is indistinguishable from one
    that interpreted everything."""
    with pytest.raises(datasetjob.NothingToInterpret) as refusal:
        datasetjob.latest_crawl_run_ref(conn, "muqawil_org")

    assert "no crawl that stored pages" in str(refusal.value)
    assert "Run a crawl first" in str(refusal.value), (
        "the refusal does not say what to do next, which on his only interface is the "
        "whole of the message")


# ---- the job the panel starts ------------------------------------------------

def test_the_interpreters_own_report_reaches_the_job_log(conn, monkeypatch):
    """`contractors.say`'s sink, not a second summary.

    The interpreter already says what it made, recovered, reparsed and refused. A job that
    wrote its own account of one pass would be free to disagree with the console's.
    """
    fake = _Interpreter(pairs=4)
    monkeypatch.setattr(contractors, "approve", fake)
    ref = _queue(conn)
    _a_crawl_that_stored(conn, "job_crawl", pages=9)

    found = datasetjob.run_dataset_interpret_job_once(conn, ref)

    assert found["status"] == JobStatus.COMPLETED.value, found
    assert fake.run_ref == "job-job_crawl", (
        "the job interpreted a ref the crawl never stored under")
    logged = " ".join(row["message"] for row in jobs.job_logs(conn, ref))
    assert "interpreting the stored pages of job-job_crawl" in logged
    assert "9 stored reading(s) on disk" in logged, (
        "the job did not say how much evidence it found, so a run over nothing and a run "
        "over nine thousand pages read the same")
    # AND THE TWO COUNTS MUST NOT SHARE A WORD, which is the whole of issue 684. On the
    # owner's warehouse this job logged `6,713 page(s) on disk` and then, six seconds
    # later, `909 page(s) on disk` -- both true, measuring snapshot ROWS and page PAIRS,
    # and reading in sequence as 5,804 pages lost. The sweep had stored the same URLs
    # once per pass (1,818 / 1,546 / 1,260 / 1,138 / 761 / 190), which is by design.
    assert "page pair(s) to interpret" in logged, (
        "the interpreter no longer says its count is page PAIRS, so it can be read "
        "against the job's snapshot-row count as though pages went missing")
    readings = [row["message"] for row in jobs.job_logs(conn, ref)
                if "on disk" in row["message"]]
    assert len(readings) == 1, (
        "more than one line in this log claims a count 'on disk', which is the "
        f"ambiguity issue 684 is about: {readings}")
    assert "Nothing is fetched" in logged, (
        "the log does not say this makes no request, which is the one fact that decides "
        "whether it is safe to start beside a crawl")
    assert "approved 4 page(s)" in logged, "the interpreter's own report never arrived"


def test_progress_is_counted_in_page_pairs_and_the_total_arrives_first(conn, monkeypatch):
    """A 6,713-page interpretation that showed `0/0` until it finished would read as a job
    that never started -- which is `OP-130` on a different runner."""
    monkeypatch.setattr(datasetjob, "BEAT_EVERY_PAIRS", 1)
    seen: list[tuple[int, int]] = []

    class _Watching(_Interpreter):
        def __call__(self, conn_, directory, run_ref, *, ids=(), between_pages=None):
            for index in range(self.pairs):
                between_pages(index, self.pairs)
                row = conn_.execute(
                    "SELECT progress_done, progress_total FROM crawl_job "
                    " WHERE job_kind = ?", (datasetjob.JOB_KIND,)).fetchone()
                seen.append((row[0], row[1]))

    monkeypatch.setattr(contractors, "approve", _Watching(pairs=3))
    _a_crawl_that_stored(conn, "job_crawl", pages=2)
    ref = _queue(conn)

    datasetjob.run_dataset_interpret_job_once(conn, ref)

    assert seen == [(0, 3), (1, 3), (2, 3)], (
        f"progress did not track the pairs, or the denominator arrived late: {seen}")
    done = conn.execute("SELECT progress_done, progress_total FROM crawl_job "
                        "WHERE job_ref = ?", (ref,)).fetchone()
    assert tuple(done) == (3, 3), (
        "a finished interpretation did not end on its own denominator")


def test_a_pause_stops_between_pages_and_says_a_resume_is_cheap(conn, monkeypatch):
    """BETWEEN PAGES IS SAFE HERE, and the message has to say why he can press it.

    Unlike the crawl, no proof spans the boundary: every earlier pair is written and the
    next one has cost nothing. A pause he is afraid to press is a pause he does not have.
    """
    monkeypatch.setattr(datasetjob, "BEAT_EVERY_PAIRS", 1)
    monkeypatch.setattr(contractors, "approve", _Interpreter(pairs=8))
    _a_crawl_that_stored(conn, "job_crawl", pages=2)
    ref = _queue(conn)
    conn.execute("UPDATE crawl_job SET control = ? WHERE job_ref = ?",
                 (JobControl.PAUSE.value, ref))
    conn.commit()

    found = datasetjob.run_dataset_interpret_job_once(conn, ref)

    assert found["status"] == JobStatus.PAUSED.value, found
    logged = " ".join(row["message"] for row in jobs.job_logs(conn, ref))
    assert "paused between pages" in logged
    assert "recognises what is already in" in logged, (
        "the pause did not tell him a resume re-reads rather than re-fetches")


def test_a_cancel_stops_between_pages(conn, monkeypatch):
    monkeypatch.setattr(datasetjob, "BEAT_EVERY_PAIRS", 1)
    monkeypatch.setattr(contractors, "approve", _Interpreter(pairs=8))
    _a_crawl_that_stored(conn, "job_crawl", pages=2)
    ref = _queue(conn)
    conn.execute("UPDATE crawl_job SET control = ? WHERE job_ref = ?",
                 (JobControl.CANCEL.value, ref))
    conn.commit()

    found = datasetjob.run_dataset_interpret_job_once(conn, ref)

    assert found["status"] == JobStatus.CANCELLED.value, found


def test_a_finished_job_is_not_interpreted_again(conn, monkeypatch):
    """A re-pick after the owner cancelled would rewrite rows he has already stopped."""
    def _never(*a, **k):
        raise AssertionError("a terminal job was interpreted again")

    monkeypatch.setattr(contractors, "approve", _never)
    ref = _queue(conn)
    conn.execute("UPDATE crawl_job SET status = ? WHERE job_ref = ?",
                 (JobStatus.CANCELLED.value, ref))
    conn.commit()

    assert datasetjob.run_dataset_interpret_job_once(conn, ref)["status"] == (
        JobStatus.CANCELLED.value)


def test_two_sources_in_one_job_are_refused(conn):
    """One denominator per job, the same rule the crawl keeps."""
    ref = jobs.create_job(conn, ["muqawil_org", "other"], RunMode.UPDATE,
                          job_kind=datasetjob.JOB_KIND)
    conn.commit()

    with pytest.raises(ValueError, match="exactly one source"):
        datasetjob.run_dataset_interpret_job_once(conn, ref)


def test_a_job_of_another_kind_is_refused_rather_than_run(conn):
    ref = jobs.create_job(conn, ["muqawil_org"], RunMode.UPDATE,
                          job_kind="directory_crawl")
    conn.commit()

    with pytest.raises(ValueError, match="not a 'dataset_interpret'"):
        datasetjob.run_dataset_interpret_job_once(conn, ref)


def test_the_feature_gate_refuses_rather_than_skipping(conn, monkeypatch):
    """THE SAME GATE THE COMMAND LINE STANDS BEHIND.

    `contractors.validate` states the reason in terms: a run that quietly did nothing
    looks like a crawl with nothing to interpret, and those are opposite facts.
    """
    monkeypatch.setattr(datasetjob, "is_enabled", lambda key: False)
    _a_crawl_that_stored(conn, "job_crawl", pages=2)
    ref = _queue(conn)

    with pytest.raises(datasetjob.NothingToInterpret, match="generic extraction is disabled"):
        datasetjob.run_dataset_interpret_job_once(conn, ref)

    assert conn.execute("SELECT count(*) FROM generic_ingestion").fetchone()[0] == 0


def test_it_holds_no_host_reservation(conn, monkeypatch):
    """THE ONE PLACE IT DIFFERS FROM THE CRAWL, ON PURPOSE.

    `_CrawlAdmission` stops two jobs asking one site for pages at once. This job asks
    nobody for anything, and holding a lane would block a real crawl of that site for the
    length of an interpretation that could not have collided with it.
    """
    taken: list[str] = []

    class _Watching:
        def lane(self, host):
            taken.append(host)
            raise AssertionError("the interpreter reserved a host it never contacts")

    monkeypatch.setattr(contractors, "approve", _Interpreter(pairs=2))
    _a_crawl_that_stored(conn, "job_crawl", pages=2)
    ref = _queue(conn)

    found = datasetjob.run_dataset_interpret_job_once(conn, ref,
                                                     admission=_Watching())

    assert found["status"] == JobStatus.COMPLETED.value
    assert not taken


def test_the_directory_registry_is_what_says_a_source_can_be_interpreted(conn):
    """One registry, the same one the crawl reads."""
    ref = jobs.create_job(conn, ["not_a_directory"], RunMode.UPDATE,
                          job_kind=datasetjob.JOB_KIND)
    conn.commit()

    with pytest.raises(datasetjob.NothingToInterpret, match="not a directory"):
        datasetjob.run_dataset_interpret_job_once(conn, ref)

    assert "muqawil_org" in directories.BUILDERS, (
        "the fixture's assumption about the registry no longer holds")


# ---- the door the panel knocks on -------------------------------------------

def _panel(tmp_path):
    """The engine as the panel reaches it, with muqawil registered."""
    import shutil

    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from scrapex import db as dbmod
    from scrapex.catalog import register_site
    from scrapex.catalog_models import SiteCreate
    from scrapex.config import MANIFEST_FILE
    from scrapex.webui.app import create_app

    db_path = tmp_path / "harvest.db"
    conn = dbmod.connect(db_path)
    dbmod.migrate(conn)
    register_site(conn, SiteCreate(site_key="muqawil_org",
                                   display_name="Saudi Contractors Authority",
                                   base_url="https://muqawil.org"))
    conn.commit()
    conn.close()
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(db_path, manifest_path=manifest)), db_path


def _kind_of(db_path, job_ref: str) -> str:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT job_kind FROM crawl_job WHERE job_ref = ?",
                            (job_ref,)).fetchone()[0]
    finally:
        conn.close()


def test_the_route_queues_the_interpret_kind_when_it_is_named(tmp_path):
    """The panel's control, end to end through the door it actually posts to.

    WITHOUT THIS, EVERYTHING ELSE IS UNREACHABLE. The runner exists, the migration lets
    the row be written, and he presses a button that queues a CRAWL -- which would go back
    to the site for pages already on disk.
    """
    client, db_path = _panel(tmp_path)

    posted = client.post("/api/jobs", json={"source_keys": ["muqawil_org"],
                                            "run_mode": "update",
                                            "job_kind": datasetjob.JOB_KIND})

    assert posted.status_code == 200, posted.text
    assert _kind_of(db_path, posted.json()["job_ref"]) == datasetjob.JOB_KIND, (
        "the route accepted the name and queued something else, so the button starts a "
        "crawl that re-fetches what is already stored")


def test_the_same_key_without_the_name_still_queues_a_crawl(tmp_path):
    """The two verbs over ONE key, and the default is unchanged.

    Naming the kind is what distinguishes them; a request that names nothing must keep
    doing exactly what it did before this change.
    """
    client, db_path = _panel(tmp_path)

    posted = client.post("/api/jobs", json={"source_keys": ["muqawil_org"],
                                            "run_mode": "update"})

    assert posted.status_code == 200, posted.text
    assert _kind_of(db_path, posted.json()["job_ref"]) == "directory_crawl"


def test_a_caller_may_not_name_a_crawl_kind(tmp_path):
    """THE REGISTRY CHOOSES THE COLLECTOR, NOT THE CALLER.

    `directories.BUILDERS` exists so one fact -- which collector reads a source -- lives
    in one place. A caller free to name `crawl` for a directory key would be a second
    place deciding it, and the two would disagree the first time a source moved.
    """
    client, _db_path = _panel(tmp_path)

    for named in ("crawl", "directory_crawl", "organization_enrichment"):
        refused = client.post("/api/jobs", json={"source_keys": ["muqawil_org"],
                                                 "run_mode": "update",
                                                 "job_kind": named})
        assert refused.status_code == 400, (named, refused.text)
        assert "chosen by the source registry" in refused.text, refused.text


def test_interpreting_a_source_that_is_not_a_directory_is_refused_at_the_door(tmp_path):
    """A price source has no stored pages of this shape, and the message he reads should
    come from the door he knocked on rather than from a job that started and stopped."""
    client, _db_path = _panel(tmp_path)

    # A KEY THE MANIFEST REALLY CARRIES, because the route validates the key BEFORE it
    # reads the kind -- an invented key answers 404 and would have made this test pass
    # for the wrong reason, which is what the first draft did.
    refused = client.post("/api/jobs", json={"source_keys": ["MADAR"],
                                             "run_mode": "update",
                                             "job_kind": datasetjob.JOB_KIND})

    assert refused.status_code == 400, refused.text
    assert "names no directory" in refused.text, refused.text


def test_a_re_entered_interpretation_says_so_through_the_runner(conn, monkeypatch):
    """ISSUE 796, AND THE CALL SITE IS THE SUBJECT. Five guards drive
    `jobs.note_a_re_entry` directly and a mutation deleting the call from THIS runner
    survived all five -- which is the vacuity shape this repository has been bitten by
    twice: a test that reads a helper while the wiring goes unmeasured.

    The state is the live one: `started_at` set, `progress_done` at what the previous
    pass reached, and `status` back to `queued`, which is exactly what
    `reclaim_orphaned_jobs` leaves behind when a restart requeues a running job. It
    happened eight times across two jobs on 2026-09-07 while he was updating the engine.
    """
    monkeypatch.setattr(contractors, "approve", _Interpreter(pairs=2))
    _a_crawl_that_stored(conn, "job_crawl", pages=2)
    ref = _queue(conn)
    conn.execute(
        "UPDATE crawl_job SET started_at = ?, progress_done = ? WHERE job_ref = ?",
        ("2026-09-07T14:31:42Z", 300, ref))
    conn.commit()

    datasetjob.run_dataset_interpret_job_once(conn, ref)

    said = " | ".join(row["message"] for row in jobs.job_logs(conn, ref))
    assert "re-entered after a restart" in said, (
        f"the runner reset his bar to zero and said nothing: {said}")
    assert "300 page pair(s)" in said, (
        f"the number he watched disappear is not in the line: {said}")
    assert "asked for nothing" in said, (
        f"the line does not say an interpretation costs no requests: {said}")


def test_a_first_interpretation_says_nothing_about_a_restart(conn, monkeypatch):
    """MOST PASSES ARE FIRST ONES, and a line on every start is noise that teaches him
    to stop reading the one that matters."""
    monkeypatch.setattr(contractors, "approve", _Interpreter(pairs=2))
    _a_crawl_that_stored(conn, "job_crawl", pages=2)
    ref = _queue(conn)

    datasetjob.run_dataset_interpret_job_once(conn, ref)

    said = " | ".join(row["message"] for row in jobs.job_logs(conn, ref))
    assert "re-entered" not in said, said
