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

import json
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
        # EVERY REF, IN ORDER. `run_ref` stays the last one so the tests written before
        # the walk keep asserting what they always asserted; issue 823 needs the whole
        # sequence, because reading the right run LAST is not the same as reading it.
        self.refs: list[str] = []
        self.beats: list[tuple[int, int]] = []

    def __call__(self, conn, directory, run_ref, *, ids=(), between_pages=None):
        self.run_ref = run_ref
        self.refs.append(run_ref)
        # THE PRODUCT'S OWN WORDING, because a stub that says something the real
        # `approve` does not is a stub a vocabulary guard cannot measure.
        contractors.say(f"approve {run_ref}: {self.pairs} page pair(s) to interpret")
        for index in range(self.pairs):
            if between_pages is not None and between_pages(index, self.pairs):
                raise contractors.CrawlStopped
            self.beats.append((index, self.pairs))
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
    assert "not this job's first pass" in said, (
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
    assert "not this job's first pass" not in said, said


# ---- issue 823: the run that holds the evidence is not always the newest -----

def _an_interpretation_that_read(conn, *refs: str) -> str:
    """A finished interpretation whose checkpoint records the runs it read.

    THE REAL SHAPE, WRITTEN THE REAL WAY. `interpreted_runs` reads `checkpoint_json` off
    `crawl_job`, so a fixture that stubbed the ledger would leave the only thing this
    change depends on unmeasured.
    """
    ref = jobs.create_job(conn, ["muqawil_org"], RunMode.UPDATE,
                          job_kind=datasetjob.JOB_KIND)
    row = jobs.get_job(conn, ref)
    # THE SIZE IS TAKEN FROM THE WAREHOUSE, not invented: the ledger records what a run
    # HELD when it was read, and a fixture that recorded a number no page count supports
    # would let a run look read at a size it never had.
    held = {one: conn.execute(
        "SELECT COUNT(*) FROM generic_page_snapshot "
        " WHERE crawl_run_ref = ? OR crawl_run_ref LIKE ?",
        (one, one + "-%")).fetchone()[0] for one in refs}
    conn.execute("UPDATE crawl_job SET status = ?, checkpoint_json = ? WHERE job_id = ?",
                 (JobStatus.COMPLETED.value, json.dumps({"runs_read": held}),
                  row["job_id"]))
    conn.commit()
    return ref


def test_an_older_run_nobody_read_is_interpreted_even_though_a_newer_one_is_done(
        conn, monkeypatch):
    """ISSUE 823, AND IT IS THE GUARD THE ISSUE ASKED FOR IN ITS OWN WORDS: *"a source
    whose newest collecting run is already fully interpreted, and an older one that is
    not, must interpret the older one."*

    MEASURED ON HIS WAREHOUSE, 2026-09-24. 37 sighted contractors have no profile row,
    all 37 sit in run `job-job_7b891d5b67ac` (469 page pairs, 2026-09-07) and all 37
    carry BOTH locales, so every one of them reaches the parser and is refused with
    `ProfileIdDidNotResolve` -- which is the one refusal that writes the mark #799 ships.
    That run was interpreted five times, every one of them BEFORE the mark existed. Since
    the mark shipped, the six interpretations that ran read 2, 2, 2, 3, 75 and 75 pairs,
    because the selection took the NEWEST run and the newest run is a two-page sweep.

    So `dataset_sighting.profile_unresolved_at` was set on 0 of 17,928 rows, his card
    said 37 contractors had work waiting on them, and no press of any button could ever
    change that.
    """
    fake = _Interpreter(pairs=3)
    monkeypatch.setattr(contractors, "approve", fake)
    _a_crawl_that_stored(conn, "job_holds_the_37", pages=938, job_kind="profile_crawl")
    _a_crawl_that_stored(conn, "job_two_pages", pages=4, job_kind="profile_crawl")
    _an_interpretation_that_read(conn, "job-job_two_pages")

    found = datasetjob.run_dataset_interpret_job_once(conn, _queue(conn))

    assert found["status"] == JobStatus.COMPLETED.value, found
    assert "job-job_holds_the_37" in fake.refs, (
        f"the run holding the evidence was never read: {fake.refs}. This is the defect "
        f"exactly -- the newest run is read, the older one is not, and the 37 stay in "
        f"the number for ever")
    # AND THE NEWEST IS READ TOO, AFTER IT, by the owner's ruling of 2026-09-26: the
    # newest run is read on every press so a corrected parser reaches it. Oldest first
    # still holds.
    assert fake.refs == ["job-job_holds_the_37", "job-job_two_pages"], (
        f"the older unread run was not read before the newest: {fake.refs}")


def test_the_walk_goes_oldest_first_so_history_is_written_in_order(
        conn, monkeypatch):
    """ORDER NO LONGER DECIDES THE LIVE VALUE, AND THIS TEST USED TO SAY IT DID.

    A Resume stores new pages under an old job's ref, so runs interleave in capture time
    and no ordering of runs guarantees the newest page is written last -- measured on a
    copy of his warehouse, the job-order walk left 99 contractors on an older value.
    #1178 fixed that where it belongs: a page captured before the one the record cites is
    refused, in whatever order it arrives.

    WHAT ORDER STILL DECIDES IS THE HISTORY. Oldest first, each change is written as a
    revision in the order it happened. Newest first, the newest is written and every older
    reading is refused, so the values in between never become revisions at all.
    """
    fake = _Interpreter(pairs=2)
    monkeypatch.setattr(contractors, "approve", fake)
    _a_crawl_that_stored(conn, "job_first", pages=4)
    _a_crawl_that_stored(conn, "job_second", pages=4)
    _a_crawl_that_stored(conn, "job_third", pages=4)

    datasetjob.run_dataset_interpret_job_once(conn, _queue(conn))

    assert fake.refs == ["job-job_first", "job-job_second", "job-job_third"], (
        f"the walk did not read the runs oldest first: {fake.refs}")


def test_a_second_press_reads_what_is_new_and_not_the_whole_warehouse_again(
        conn, monkeypatch):
    """THE COST HE ACCEPTED, AND THE COST HE DID NOT. Measured on his warehouse: walking
    every run reads 3,309 page pairs, about 20 minutes and no requests. Paying that on
    EVERY press -- and `directoryjob` now queues an interpretation after every crawl by
    itself -- is the version of this he was not offered.
    """
    fake = _Interpreter(pairs=2)
    monkeypatch.setattr(contractors, "approve", fake)
    _a_crawl_that_stored(conn, "job_one", pages=4)
    _a_crawl_that_stored(conn, "job_two", pages=4)

    datasetjob.run_dataset_interpret_job_once(conn, _queue(conn))
    first_pass = list(fake.refs)
    _a_crawl_that_stored(conn, "job_three", pages=4)
    fake.refs.clear()
    datasetjob.run_dataset_interpret_job_once(conn, _queue(conn))

    assert first_pass == ["job-job_one", "job-job_two"], first_pass
    assert fake.refs == ["job-job_three"], (
        f"the second press re-read runs the first one had already finished: {fake.refs}")


def test_a_run_the_walk_stopped_inside_is_not_recorded_as_read(conn, monkeypatch):
    """HALF A RUN'S PAGES ARE NOT THE RUN. Recording it on the way in would lose the rest
    of its evidence for ever -- and the pause here is the owner's own, so the next press
    is exactly the moment he expects it to continue.
    """
    class _StopsInTheSecondRun(_Interpreter):
        def __call__(self, conn, directory, run_ref, *, ids=(), between_pages=None):
            self.refs.append(run_ref)
            self.run_ref = run_ref
            if len(self.refs) == 2:
                raise contractors.CrawlStopped
            contractors.say(f"approve {run_ref}: 1 page pair(s) to interpret")
            if between_pages is not None:
                between_pages(0, 1)
            contractors.say("approved 1 page(s)")

    fake = _StopsInTheSecondRun()
    monkeypatch.setattr(contractors, "approve", fake)
    _a_crawl_that_stored(conn, "job_one", pages=4)
    _a_crawl_that_stored(conn, "job_two", pages=4)

    datasetjob.run_dataset_interpret_job_once(conn, _queue(conn))

    read = set(datasetjob.interpreted_runs(conn, "muqawil_org"))
    assert "job-job_one" in read, (
        f"a run read to the end before the stop was forgotten, so the next walk pays "
        f"for it again: {read}")
    assert "job-job_two" not in read, (
        f"the run the walk stopped INSIDE was recorded as read, so the rest of its "
        f"pages will never be interpreted: {read}")


def test_a_ref_asked_for_by_name_is_read_even_when_the_ledger_holds_it(
        conn, monkeypatch):
    """THE EXPLICIT REF STILL WINS, which is what asking for a run BY NAME means. The
    runner's own contract says so -- *"a caller that knows exactly which run it means can
    say so"* -- and the ledger must not quietly turn that into a no-op.
    """
    fake = _Interpreter(pairs=2)
    monkeypatch.setattr(contractors, "approve", fake)
    _a_crawl_that_stored(conn, "job_one", pages=4)
    _an_interpretation_that_read(conn, "job-job_one")
    ref = jobs.create_job(conn, ["muqawil_org"], RunMode.UPDATE,
                          job_kind=datasetjob.JOB_KIND,
                          checkpoint={"run_ref": "job-job_one"})
    conn.commit()

    datasetjob.run_dataset_interpret_job_once(conn, ref)

    assert fake.refs == ["job-job_one"], (
        f"a run asked for by name was skipped because the ledger held it: {fake.refs}")


def test_the_bar_does_not_fall_back_when_the_walk_opens_the_next_run(
        conn, monkeypatch):
    """ISSUE 796 WEARING A DIFFERENT HAT. `approve` counts from zero for each run it is
    given, so a job reporting that figure straight through would show 0 of 469, then 0 of
    75 -- his bar falling back to nothing with the work already done. The denominator may
    GROW as each run opens, because more work really was found; the numerator may not
    fall.
    """
    fake = _Interpreter(pairs=3)
    monkeypatch.setattr(contractors, "approve", fake)
    # EVERY PAGE BEATS, AND WITHOUT THIS THE TEST MEASURES NOTHING. `page_closed` writes
    # a progress pair only on `index % BEAT_EVERY_PAIRS`, which is 50 -- so a three-pair
    # run beats once, at index 0, and a numerator that falls back to zero between runs
    # produces [0, 0]: sorted, monotonic, and indistinguishable from the fix. The first
    # version of this guard asserted exactly that and survived the mutation.
    monkeypatch.setattr(datasetjob, "BEAT_EVERY_PAIRS", 1)
    _a_crawl_that_stored(conn, "job_one", pages=4)
    _a_crawl_that_stored(conn, "job_two", pages=4)
    seen: list[tuple[int, int]] = []
    real = jobs._update

    def watch(conn_, job_id, **fields):
        if "progress_done" in fields and "progress_total" in fields:
            seen.append((fields["progress_done"], fields["progress_total"]))
        return real(conn_, job_id, **fields)

    monkeypatch.setattr(jobs, "_update", watch)

    datasetjob.run_dataset_interpret_job_once(conn, _queue(conn))

    # THE WHOLE SEQUENCE, NOT A PROPERTY OF IT. Three pairs in each of two runs: the
    # second run continues from three and states six, rather than restarting at zero.
    assert seen == [(0, 3), (1, 3), (2, 3), (3, 6), (4, 6), (5, 6), (6, 6)], (
        f"the number he watches restarted when the walk opened the next run: {seen}")


def test_a_resume_keeps_the_runs_the_first_pass_already_read(conn, monkeypatch):
    """THE LEDGER MUST SURVIVE A RE-ENTRY INTO THE SAME JOB ROW.

    `set_control(RESUME)` re-queues the SAME row, and `reclaim_orphaned_jobs` does the
    same to a job whose engine was killed. Both re-enter `run_dataset_interpret_job_once`
    with a fresh `read_to_the_end`, so a ledger written by replacing the key loses every
    run the first pass finished.

    WHAT IT COSTS CHANGED WITH #1178, AND IS STILL NOT NOTHING. The runs that fall out of
    the ledger are read again on a LATER press, after the newer runs have been applied.
    Before #1178 that wrote the older page over the newer row; since, the record refuses
    it -- so what remains is every row of those runs read again for nothing, and a history
    written out of the order it happened in.
    """
    class _StopsInTheThirdRun(_Interpreter):
        def __call__(self, conn, directory, run_ref, *, ids=(), between_pages=None):
            self.refs.append(run_ref)
            self.run_ref = run_ref
            if len(self.refs) == 3:
                raise contractors.CrawlStopped
            contractors.say(f"approve {run_ref}: 1 page pair(s) to interpret")
            if between_pages is not None:
                between_pages(0, 1)
            contractors.say("approved 1 page(s)")

    fake = _StopsInTheThirdRun()
    monkeypatch.setattr(contractors, "approve", fake)
    for name in ("job_one", "job_two", "job_three", "job_four"):
        _a_crawl_that_stored(conn, name, pages=4)
    ref = _queue(conn)

    datasetjob.run_dataset_interpret_job_once(conn, ref)
    after_the_stop = set(datasetjob.interpreted_runs(conn, "muqawil_org"))
    assert after_the_stop == {"job-job_one", "job-job_two"}, after_the_stop

    # THE SAME ROW IS RE-ENTERED, which is what a resume does.
    jobs._update(conn, jobs.get_job(conn, ref)["job_id"],
                 status=JobStatus.QUEUED.value, finished_at=None)
    conn.commit()
    fake.refs.clear()
    datasetjob.run_dataset_interpret_job_once(conn, ref)

    after_the_resume = set(datasetjob.interpreted_runs(conn, "muqawil_org"))
    # AND THE RESUME SAYS SO. The re-entry line used to promise "every pair is read from
    # disk again", which the ledger made false: the resumed pass above read only the two
    # runs the first pass had not finished.
    said = " | ".join(row["message"] for row in jobs.job_logs(conn, ref))
    assert "already finished are not read again" in said, (
        f"the resumed pass does not say which runs it skipped: {said}")
    assert fake.refs == ["job-job_three", "job-job_four"], (
        f"the resume read runs the first pass had finished: {fake.refs}")
    assert after_the_resume == {"job-job_one", "job-job_two",
                                "job-job_three", "job-job_four"}, (
        f"the resume dropped runs the first pass read to the end: {after_the_resume}. "
        f"They are now unread, so a later press applies them AFTER the newer runs and "
        f"reads them again after the newer ones, out of order")


def test_a_press_with_nothing_new_reads_only_the_newest_run_and_says_why(
        conn, monkeypatch):
    """EVERY PRESS AFTER THE FIRST, and the owner ruled what it does, 2026-09-26: it reads
    the newest run again -- so a corrected parser reaches it -- and nothing older.

    The branch that used to answer this finished COMPLETED at 0 of 0 with `interpreting
    the stored pages of . Nothing is fetched`. The ruling makes an empty plan impossible
    while any run exists, so that branch is gone rather than left unreachable.

    WHAT THE JOB OWES HIM IS THE REASON. A run the ledger already holds, read again on
    every press, reads as the ledger failing unless the job says why.
    """
    fake = _Interpreter(pairs=2)
    monkeypatch.setattr(contractors, "approve", fake)
    _a_crawl_that_stored(conn, "job_one", pages=4)
    _a_crawl_that_stored(conn, "job_two", pages=4)
    datasetjob.run_dataset_interpret_job_once(conn, _queue(conn))

    fake.refs.clear()
    ref = _queue(conn)
    found = datasetjob.run_dataset_interpret_job_once(conn, ref)

    assert found["status"] == JobStatus.COMPLETED.value, found
    assert fake.refs == ["job-job_two"], (
        f"a press with nothing new read something other than the newest run alone: "
        f"{fake.refs}")
    said = " | ".join(row["message"] for row in jobs.job_logs(conn, ref))
    assert "job-job_two was already interpreted and is read again" in said, (
        f"the job re-read a run the ledger holds and did not say why: {said}")
    assert "a corrected parser reaches its pages" in said, (
        f"the reason is missing, so the re-read reads as a defect: {said}")
    # AND THE BROKEN SENTENCE MAY NOT COME BACK. An empty ref reads as a missing word.
    assert "stored pages of ." not in said, (
        f"the opening line names an empty run ref: {said}")


# ---- what the merge gate's mutation sweep found unwatched ---------------------
#
# SEVENTEEN MUTATIONS SURVIVED the first set of guards, and they shared one shape: every
# assertion read `fake.refs` or `interpreted_runs`, and NOT ONE read the job's final
# status, its log, or the ledger's exact contents. Three unwatched outputs, seventeen
# ways through. These watch the three.

def test_a_source_no_crawl_has_touched_is_refused_by_the_RUNNER_too(conn, monkeypatch):
    """THE REFUSAL HAS TO SURVIVE THE CALL SITE, and the guard above it does not prove
    that: it calls `latest_crawl_run_ref` directly and never enters the runner.

    The runner used to reach the refusal through a bare `latest_crawl_run_ref(...)` whose
    return value was discarded -- a line that exists for its exception, which is exactly
    the line a later reader deletes as dead. Deleting it left the suite GREEN and made a
    press on a never-crawled source finish COMPLETED, the outcome `NothingToInterpret`'s
    own docstring names: *"A job that interpreted nothing and finished green is
    indistinguishable from one that interpreted everything."*
    """
    fake = _Interpreter(pairs=2)
    monkeypatch.setattr(contractors, "approve", fake)
    ref = _queue(conn)

    with pytest.raises(datasetjob.NothingToInterpret) as refusal:
        datasetjob.run_dataset_interpret_job_once(conn, ref)

    assert "Run a crawl first" in str(refusal.value)
    assert fake.refs == [], f"it interpreted something on a source with no crawl: {fake.refs}"
    assert jobs.get_job(conn, ref)["status"] != JobStatus.COMPLETED.value, (
        "a source no crawl has touched finished GREEN, which reads as an interpretation "
        "of everything")


def test_the_ledger_holds_exactly_the_runs_the_walk_opened(conn, monkeypatch):
    """MEMBERSHIP IS NOT ENOUGH, and the gate proved it: appending a ref the walk never
    opened to `read_to_the_end` left every guard green.

    A run marked read but never interpreted is evidence no press can ever reach again --
    which is issue 823 itself, arriving from the other side.
    """
    fake = _Interpreter(pairs=2)
    monkeypatch.setattr(contractors, "approve", fake)
    _a_crawl_that_stored(conn, "job_one", pages=4)
    _a_crawl_that_stored(conn, "job_two", pages=4)

    datasetjob.run_dataset_interpret_job_once(conn, _queue(conn))

    ledger = datasetjob.interpreted_runs(conn, "muqawil_org")
    assert set(ledger) == {"job-job_one", "job-job_two"}, ledger
    # AND THE SIZE IT RECORDS IS THE SIZE THE RUN HELD, which is what makes a ref that
    # GROWS after it was read become unread again.
    assert ledger == {"job-job_one": 4, "job-job_two": 4}, ledger
    assert set(fake.refs) == set(ledger), (
        f"the ledger and the runs actually opened disagree: {fake.refs} against "
        f"{datasetjob.interpreted_runs(conn, 'muqawil_org')}")


def test_a_walk_that_FAILS_keeps_the_runs_it_finished_before_the_failure(
        conn, monkeypatch):
    """THE SHAPE THE PR BODY DESCRIBES, and only the pause shape was measured. *"A walk
    that fails on run 7 keeps runs 1 to 6 out of the next walk, and run 7 in it."*
    """
    class _BlowsUpInTheThirdRun(_Interpreter):
        def __call__(self, conn, directory, run_ref, *, ids=(), between_pages=None):
            self.refs.append(run_ref)
            if len(self.refs) == 3:
                raise RuntimeError("the parser fell over")
            contractors.say(f"approve {run_ref}: 1 page pair(s) to interpret")
            if between_pages is not None:
                between_pages(0, 1)
            contractors.say("approved 1 page(s)")

    monkeypatch.setattr(contractors, "approve", _BlowsUpInTheThirdRun())
    for name in ("job_one", "job_two", "job_three"):
        _a_crawl_that_stored(conn, name, pages=4)
    ref = _queue(conn)

    with pytest.raises(RuntimeError):
        datasetjob.run_dataset_interpret_job_once(conn, ref)

    assert jobs.get_job(conn, ref)["status"] == JobStatus.FAILED.value
    assert set(datasetjob.interpreted_runs(conn, "muqawil_org")) == {
        "job-job_one", "job-job_two"}, (
        f"a failure lost the runs already read, or recorded the one it died inside: "
        f"{datasetjob.interpreted_runs(conn, 'muqawil_org')}")


def test_the_multi_run_log_says_which_run_it_starts_at_and_what_the_walk_totals(
        conn, monkeypatch):
    """THE WHOLE MULTI-RUN VOCABULARY WAS UNMEASURED -- five mutations lived here. The
    existing log guard asserts carefully over a ONE-run plan, so every sentence this
    change introduced was free to say anything.

    The last of the five is issue 796's defect class in the LOG rather than the bar: the
    closing line reporting the last run's count instead of the walk's, beside a bar that
    reports the walk's.
    """
    fake = _Interpreter(pairs=2)
    monkeypatch.setattr(contractors, "approve", fake)
    _a_crawl_that_stored(conn, "job_one", pages=4)
    _a_crawl_that_stored(conn, "job_two", pages=6)
    ref = _queue(conn)

    datasetjob.run_dataset_interpret_job_once(conn, ref)
    said = " | ".join(row["message"] for row in jobs.job_logs(conn, ref))

    assert "2 run(s), oldest first, starting at job-job_one" in said, (
        f"the opening line does not name the run the walk actually starts at: {said}")
    assert "10 stored reading(s) on disk" in said, (
        f"the opening line does not total the evidence across the plan (4 + 6): {said}")
    assert "run 1 of 2: job-job_one" in said and "run 2 of 2: job-job_two" in said, (
        f"the walk does not say where it is, so a 20-minute pass reports nothing between "
        f"its ends: {said}")
    assert "4 page pair(s) read from disk across 2 run(s)" in said, (
        f"the closing line reports one run's count rather than the walk's: {said}")


def test_a_checkpoint_that_is_not_a_dictionary_is_treated_as_unknown(conn):
    """VALID JSON IS NOT ENOUGH. `create_job` dumps whatever it is handed, so a
    checkpoint holding a JSON LIST parses and then raises on `.get` -- an `AttributeError`
    the two exception types beside that comment did not catch, while the comment promised
    they did.

    UNKNOWN MEANS READ AGAIN, never "read nothing": a ledger that cannot be parsed must
    not silently retire evidence.
    """
    _a_crawl_that_stored(conn, "job_one", pages=4)
    for payload in ('["not", "a", "dict"]', "not json at all", "null"):
        ref = jobs.create_job(conn, ["muqawil_org"], RunMode.UPDATE,
                              job_kind=datasetjob.JOB_KIND)
        conn.execute("UPDATE crawl_job SET checkpoint_json = ? WHERE job_ref = ?",
                     (payload, ref))
        conn.commit()

    assert datasetjob.interpreted_runs(conn, "muqawil_org") == {}
    assert [one[0] for one in datasetjob.runs_to_interpret(conn, "muqawil_org")] == [
        "job-job_one"], "an unreadable checkpoint retired a run nobody has interpreted"


def test_a_run_that_GREW_after_it_was_read_is_read_again(conn, monkeypatch):
    """A REF IS NOT A UNIT OF "READ", AND THIS IS THE REGRESSION IT WOULD HAVE BEEN.

    `directoryjob` stores a resume under the job's OWN ref -- *"THE REF IS THE JOB'S BY
    DEFAULT, so a resume under the same job skips the pages it already stored"* -- and the
    panel's continue-a-stopped-crawl control passes `resume_run_ref`, so a NEW job's pages
    land under an OLD ref.

    MEASURED ON HIS WAREHOUSE, 2026-09-24. `job-job_925080aad843` holds 7,934 pages stored
    in three bursts nine days apart (3,138 on 09-03, 4,720 on 09-08, 76 on 09-12) and the
    first interpretation finished 2026-09-06. Keyed on the ref alone, that interpretation
    retires the run and 4,796 of its 7,934 pages -- 60% -- are unreachable from the only
    surface he has. `main` never had that failure: it re-reads the newest run on every
    press. A ledger of NAMES would have been a regression against it.
    """
    fake = _Interpreter(pairs=2)
    monkeypatch.setattr(contractors, "approve", fake)
    _a_crawl_that_stored(conn, "job_one", pages=4)

    datasetjob.run_dataset_interpret_job_once(conn, _queue(conn))
    assert fake.refs == ["job-job_one"]
    assert datasetjob.interpreted_runs(conn, "muqawil_org") == {"job-job_one": 4}

    # THE SAME REF GROWS, which is what a resumed crawl does to it.
    for n in range(6):
        conn.execute(
            "INSERT INTO generic_page_snapshot (source_url, html_content, content_hash, "
            "crawl_run_ref) VALUES (?,?,?,?)",
            (f"https://muqawil.org/contractors?page=later{n}", b"<html/>",
             f"later-{n}", "job-job_one-cell-a1"))
    conn.commit()

    fake.refs.clear()
    datasetjob.run_dataset_interpret_job_once(conn, _queue(conn))

    assert fake.refs == ["job-job_one"], (
        f"six pages arrived under a run the ledger had already retired, and no press can "
        f"ever reach them again: {fake.refs}")
    assert datasetjob.interpreted_runs(conn, "muqawil_org") == {"job-job_one": 10}, (
        f"the ledger did not move to the size it has now read: "
        f"{datasetjob.interpreted_runs(conn, 'muqawil_org')}")

    # AND THE LEDGER SETTLES. Nothing is unread once the grown run is read at its new
    # size. (A press would still read it -- it is the newest, and the owner ruled that
    # the newest is read on every press -- which is why this asks the ledger, not a press.)
    assert datasetjob.runs_to_interpret(conn, "muqawil_org") == [], (
        f"a run read at its full size is still offered as unread: "
        f"{datasetjob.runs_to_interpret(conn, 'muqawil_org')}")


def test_the_ledger_moves_UP_to_the_largest_size_read_never_down(conn, monkeypatch):
    """A RECORD THAT CAN SHRINK IS A RECORD THAT NEVER SETTLES.

    The same job records the same ref twice when the ref grew between its two entries: it
    reads it at 4, is paused, the crawl resumes and stores six more, and the resumed pass
    reads it at 10. Keeping the smaller of the two leaves the run permanently unread --
    every later press pays for it again and the ledger never converges.
    """
    fake = _Interpreter(pairs=1)
    monkeypatch.setattr(contractors, "approve", fake)
    _a_crawl_that_stored(conn, "job_one", pages=4)
    ref = _queue(conn)
    datasetjob.run_dataset_interpret_job_once(conn, ref)
    assert datasetjob.interpreted_runs(conn, "muqawil_org") == {"job-job_one": 4}

    for n in range(6):
        conn.execute(
            "INSERT INTO generic_page_snapshot (source_url, html_content, content_hash, "
            "crawl_run_ref) VALUES (?,?,?,?)",
            (f"https://muqawil.org/contractors?page=more{n}", b"<html/>",
             f"more-{n}", "job-job_one-cell-a1"))
    conn.commit()

    # THE SAME ROW IS RE-ENTERED, which is what a resume does.
    jobs._update(conn, jobs.get_job(conn, ref)["job_id"],
                 status=JobStatus.QUEUED.value, finished_at=None)
    conn.commit()
    datasetjob.run_dataset_interpret_job_once(conn, ref)

    assert datasetjob.interpreted_runs(conn, "muqawil_org") == {"job-job_one": 10}, (
        f"the ledger did not move up to what the second pass read: "
        f"{datasetjob.interpreted_runs(conn, 'muqawil_org')}")
    assert datasetjob.runs_to_interpret(conn, "muqawil_org") == [], (
        "the run is still offered after being read at its full size, so it never settles")


def test_a_ledger_written_in_the_older_LIST_shape_retires_nothing(conn, monkeypatch):
    """SELF-HEALING BEATS A MIGRATION, but only if the older shape reads as ZERO.

    The first version of this ledger stored a list of names with no size. Reading such an
    entry as "read at any size" would retire a run nobody has measured -- the exact
    failure the size exists to prevent, arriving through the back-compatibility path.
    """
    fake = _Interpreter(pairs=1)
    monkeypatch.setattr(contractors, "approve", fake)
    _a_crawl_that_stored(conn, "job_one", pages=4)
    old = jobs.create_job(conn, ["muqawil_org"], RunMode.UPDATE,
                          job_kind=datasetjob.JOB_KIND)
    conn.execute("UPDATE crawl_job SET status = ?, checkpoint_json = ? WHERE job_ref = ?",
                 (JobStatus.COMPLETED.value,
                  json.dumps({"runs_read": ["job-job_one"]}), old))
    conn.commit()

    assert datasetjob.interpreted_runs(conn, "muqawil_org") == {"job-job_one": 0}, (
        "a sizeless record was read as though its size were known")
    assert [one[0] for one in datasetjob.runs_to_interpret(conn, "muqawil_org")] == [
        "job-job_one"], "the older shape retired a run whose size nobody recorded"

    datasetjob.run_dataset_interpret_job_once(conn, _queue(conn))
    assert fake.refs == ["job-job_one"]
    assert datasetjob.interpreted_runs(conn, "muqawil_org") == {"job-job_one": 4}, (
        "the re-read did not upgrade the sizeless record, so it never heals")


def test_a_ledger_value_no_writer_can_produce_still_leaves_the_source_readable(conn):
    """THE GUARD PROMISED THIS AND DID NOT DELIVER IT.

    The shaping of `runs_read` used to sit OUTSIDE the `try`, so a value holding a number
    raised `TypeError` past the `except` and killed the whole source's ledger -- while the
    two sentences beside it promised *"Unreadable means unknown, and unknown runs are read
    again."*

    No writer in this repo can produce these: `_remember_runs_read` always writes `int`,
    and no panel route sets `runs_read`. They are guarded anyway because the blast radius
    is every run of that source, permanently, with no control that can clear it.
    """
    _a_crawl_that_stored(conn, "job_one", pages=4)
    for payload in ('{"runs_read": 5}', '{"runs_read": true}',
                    '{"runs_read": {"job-job_one": "many"}}',
                    '{"runs_read": {"job-job_one": [4]}}',
                    '{"runs_read": {"job-job_one": null}}',
                    '{"runs_read": {"job-job_one": -3}}'):
        ref = jobs.create_job(conn, ["muqawil_org"], RunMode.UPDATE,
                              job_kind=datasetjob.JOB_KIND)
        conn.execute("UPDATE crawl_job SET checkpoint_json = ? WHERE job_ref = ?",
                     (payload, ref))
        conn.commit()

        # IT MUST NOT RAISE, and the run must still be offered.
        datasetjob.interpreted_runs(conn, "muqawil_org")
        assert [one[0] for one in datasetjob.runs_to_interpret(conn, "muqawil_org")] == [
            "job-job_one"], f"{payload} retired a run nobody read"

        conn.execute("UPDATE crawl_job SET checkpoint_json = NULL WHERE job_ref = ?",
                     (ref,))
        conn.commit()


def test_a_ref_asked_for_by_name_records_the_size_it_actually_held(conn, monkeypatch):
    """A BY-NAME PRESS IS STILL A READ, and recording it at size 0 left the run
    permanently unread -- never retired wrongly, but buying the ledger nothing.
    """
    fake = _Interpreter(pairs=2)
    monkeypatch.setattr(contractors, "approve", fake)
    _a_crawl_that_stored(conn, "job_one", pages=4)
    ref = jobs.create_job(conn, ["muqawil_org"], RunMode.UPDATE,
                          job_kind=datasetjob.JOB_KIND,
                          checkpoint={"run_ref": "job-job_one"})
    conn.commit()

    datasetjob.run_dataset_interpret_job_once(conn, ref)

    assert fake.refs == ["job-job_one"]
    assert datasetjob.interpreted_runs(conn, "muqawil_org") == {"job-job_one": 4}, (
        f"a by-name read recorded a size the run never held: "
        f"{datasetjob.interpreted_runs(conn, 'muqawil_org')}")
    # AND A REF NO COLLECTING JOB STORED UNDER RECORDS NOTHING, because a size nobody can
    # count is not a size.
    other = jobs.create_job(conn, ["muqawil_org"], RunMode.UPDATE,
                            job_kind=datasetjob.JOB_KIND,
                            checkpoint={"run_ref": "job-invented-by-hand"})
    conn.commit()
    datasetjob.run_dataset_interpret_job_once(conn, other)
    assert datasetjob.interpreted_runs(conn, "muqawil_org")["job-invented-by-hand"] == 0


def test_a_corrected_parser_reaches_the_newest_run_on_the_next_press(conn, monkeypatch):
    """THE OWNER'S RULING, 2026-09-26, AND THE REASON FOR IT.

    The fourth gate pass demonstrated the door the ledger closed: a parser that reads
    nothing retires the run at its full size, the parser is fixed, and the next press
    hands the fixed parser NOTHING -- so the fix reaches no stored page. `main` re-read the
    newest run on every press, which was the one guarantee a parser fix ever had.
    """
    class _Blind(_Interpreter):
        def __call__(self, conn, directory, run_ref, *, ids=(), between_pages=None):
            self.refs.append(run_ref)
            self.run_ref = run_ref
            contractors.say(f"approve {run_ref}: 0 page pair(s) to interpret")
            contractors.say("approved 0 page(s)")

    blind = _Blind()
    monkeypatch.setattr(contractors, "approve", blind)
    _a_crawl_that_stored(conn, "job_one", pages=4)
    datasetjob.run_dataset_interpret_job_once(conn, _queue(conn))
    assert blind.refs == ["job-job_one"] and blind.seen == 0
    assert datasetjob.interpreted_runs(conn, "muqawil_org") == {"job-job_one": 4}, (
        "precondition: the blind pass retired the run at its full size")

    fixed = _Interpreter(pairs=4)
    monkeypatch.setattr(contractors, "approve", fixed)
    datasetjob.run_dataset_interpret_job_once(conn, _queue(conn))

    assert fixed.refs == ["job-job_one"], (
        f"the parser was corrected and the next press did not reach the pages it failed "
        f"on: {fixed.refs}")
    assert fixed.seen == 4, f"the corrected parser was handed nothing: {fixed.seen}"


def test_only_the_NEWEST_is_read_again_an_older_read_run_stays_retired(
        conn, monkeypatch):
    """THE RULING HAS A LIMIT, AND THE LIMIT IS THE LEDGER'S WHOLE POINT.

    "The newest run always" must not drift into "every run always": that is the version
    he was not offered, and on his warehouse it is ~3,309 page pairs and ~20 minutes on
    every press -- repeated for every crawl, now that a crawl queues its own
    interpretation. Older runs stay retired; reaching them after a parser fix is filed
    as its own question.
    """
    fake = _Interpreter(pairs=1)
    monkeypatch.setattr(contractors, "approve", fake)
    for name in ("job_one", "job_two", "job_three"):
        _a_crawl_that_stored(conn, name, pages=4)
    datasetjob.run_dataset_interpret_job_once(conn, _queue(conn))
    assert fake.refs == ["job-job_one", "job-job_two", "job-job_three"]

    fake.refs.clear()
    datasetjob.run_dataset_interpret_job_once(conn, _queue(conn))

    assert fake.refs == ["job-job_three"], (
        f"runs older than the newest were read again, so every press pays for the whole "
        f"warehouse: {fake.refs}")


# ---- one interpretation waiting is enough -- issue 779 ----------------------

def _interpretation_in(db_path, status: str, source: str = "muqawil_org") -> str:
    """An interpretation of `source` sitting in `status`, written through the engine's
    own job table, so the route and the chain are both asked about a row that exists."""
    from scrapex import db as dbmod
    conn = dbmod.connect(db_path)
    try:
        ref = jobs.create_job(conn, [source], RunMode.UPDATE,
                              job_kind=datasetjob.JOB_KIND)
        jobs._update(conn, jobs.get_job(conn, ref)["job_id"], status=status)
        conn.commit()
        return ref
    finally:
        conn.close()


def _interpretations_of(db_path, source: str = "muqawil_org") -> list[str]:
    conn = sqlite3.connect(db_path)
    try:
        return [row[0] for row in conn.execute(
            "SELECT job_ref FROM crawl_job WHERE job_kind = ? AND source_keys LIKE ? "
            "ORDER BY job_id", (datasetjob.JOB_KIND, f'%"{source}"%'))]
    finally:
        conn.close()


def _press_interpret(client, source: str = "muqawil_org"):
    return client.post("/api/jobs", json={"source_keys": [source],
                                          "run_mode": "update",
                                          "job_kind": datasetjob.JOB_KIND})


@pytest.mark.parametrize("status", ["queued", "scheduled"])
def test_a_second_interpretation_is_refused_while_one_has_not_started(tmp_path, status):
    """ISSUE 779, REFUSED WHERE THE WRITE HAPPENS.

    Before this, `POST /api/jobs` accepted a second interpretation of a source that
    already had one waiting, so one press made a job that read nothing the first would
    not -- a worker slot out of `job_capacity` spent on nothing. The panel was left to
    explain the gap in copy, and every sentence it wrote claimed a state the code was
    not in. Refused at the door, the card has nothing to explain.

    A job still `queued` or `scheduled` plans its reading when it STARTS, so it will read
    every stored run nobody has read -- which is exactly what the second press asked for.
    """
    client, db_path = _panel(tmp_path)
    waiting = _interpretation_in(db_path, status)

    refused = _press_interpret(client)

    assert refused.status_code == 409, (
        f"a {status} interpretation was waiting and the route queued another: "
        f"{refused.status_code} {refused.text}")
    assert waiting in refused.json()["detail"], (
        f"the refusal does not name the job that will do the work, so he cannot go and "
        f"find it: {refused.text}")
    assert _interpretations_of(db_path) == [waiting], (
        f"the route answered 409 and wrote a job anyway: {_interpretations_of(db_path)}")


@pytest.mark.parametrize("status", ["preparing", "running", "resuming",
                                    "pausing", "cancelling", "paused",
                                    "requires_review"])
def test_one_that_already_planned_does_not_refuse_the_press(tmp_path, status):
    """NOT "ANY LIVE INTERPRETATION", and the difference decides whether a refusal loses
    pages.

    One that is `preparing` or later computed `runs_to_interpret` when it started,
    possibly before the pages he now wants read existed -- so a second one is not a
    duplicate: it reads the runs the first did not plan for. Refusing it would leave those
    pages unread with nothing on the screen saying so. A `paused` or `requires_review` one
    waits on him and does not advance by itself.
    """
    client, db_path = _panel(tmp_path)
    first = _interpretation_in(db_path, status)

    accepted = _press_interpret(client)

    assert accepted.status_code == 200, (
        f"a {status} interpretation had already planned its reading and the route "
        f"refused a second one, which would read what the first did not plan for: "
        f"{accepted.status_code} {accepted.text}")
    assert _interpretations_of(db_path) == [first, accepted.json()["job_ref"]], (
        "the route answered 200 without writing the second job")


@pytest.mark.parametrize("status", ["completed", "completed_with_errors",
                                    "partially_completed", "failed", "cancelled"])
def test_a_finished_interpretation_refuses_nothing(tmp_path, status):
    """The other end of the list: a job that ended reads nothing more, so the press it
    would block is the only way the runs stored since get read."""
    client, db_path = _panel(tmp_path)
    _interpretation_in(db_path, status)

    accepted = _press_interpret(client)

    assert accepted.status_code == 200, (
        f"a {status} interpretation refused a new one: {accepted.text}")


def test_the_refusal_is_about_interpretations_and_nothing_else(tmp_path):
    """A waiting interpretation does not stop him CRAWLING. The two are different work --
    a crawl buys pages, an interpretation reads them -- and a refusal that reached past
    its own kind would block the Update button on every source with an interpretation
    queued, which after this PR is every source a crawl has just finished."""
    client, db_path = _panel(tmp_path)
    _interpretation_in(db_path, "queued")

    crawl = client.post("/api/jobs", json={"source_keys": ["muqawil_org"],
                                           "run_mode": "update"})

    assert crawl.status_code == 200, (
        f"a queued interpretation refused a CRAWL of the same source: {crawl.text}")
    assert _kind_of(db_path, crawl.json()["job_ref"]) == "directory_crawl"


def test_another_sources_interpretation_does_not_refuse_this_one(tmp_path):
    """The refusal is per SOURCE. One source waiting to be interpreted is no reason to
    refuse interpreting another -- and `source_keys LIKE` matching, had the rule used it,
    would match a key that merely CONTAINS this one."""
    client, db_path = _panel(tmp_path)
    _interpretation_in(db_path, "queued", source="muqawil_org_archive")

    accepted = _press_interpret(client)

    assert accepted.status_code == 200, (
        f"another source's queued interpretation refused this one: {accepted.text}")


@pytest.mark.parametrize("status", [
    "scheduled", "queued", "preparing", "running", "resuming",
    "pausing", "cancelling", "paused", "requires_review"])
def test_the_chain_and_the_route_give_one_answer(tmp_path, status):
    """ONE RULE, TWO READERS, AND THEY MAY NOT DISAGREE -- on any of the nine live
    statuses.

    The crawl's chain decides whether to queue another interpretation; the route decides
    whether to refuse one he pressed. Both read `datasetjob.waiting_interpretation`. Were
    either to grow its own copy, a press could make the duplicate the chain would have
    skipped, or a crawl queue the one the route would have refused -- and this PR's own
    first version had a chain and a card that asked two different questions.
    """
    client, db_path = _panel(tmp_path)
    _interpretation_in(db_path, status)

    from scrapex import db as dbmod
    conn = dbmod.connect(db_path)
    try:
        chain_skips = datasetjob.waiting_interpretation(conn, "muqawil_org") is not None
    finally:
        conn.close()
    route_refuses = _press_interpret(client).status_code == 409

    assert chain_skips == route_refuses, (
        f"for a {status} interpretation the chain {'skips' if chain_skips else 'queues'} "
        f"and the route {'refuses' if route_refuses else 'accepts'} -- one rule, read two "
        f"ways, so whichever path disagrees makes a duplicate or loses a reading")
    assert chain_skips == (status in {"scheduled", "queued"}), (
        f"the shared rule itself moved: for {status} it says "
        f"{'waiting' if chain_skips else 'not waiting'}")


def test_the_rule_reads_only_interpretations(tmp_path):
    """A queued CRAWL of the source is not an interpretation waiting to read it. Without
    the kind in the rule, a crawl queued behind another would make the chain skip the
    interpretation its own finish owes."""
    _client, db_path = _panel(tmp_path)
    from scrapex import db as dbmod
    conn = dbmod.connect(db_path)
    try:
        jobs.create_job(conn, ["muqawil_org"], RunMode.UPDATE, job_kind="directory_crawl")
        conn.commit()
        assert datasetjob.waiting_interpretation(conn, "muqawil_org") is None
    finally:
        conn.close()


def test_the_rule_names_the_job_it_found(tmp_path):
    """The refusal's message and the chain's skip line both print the waiting job's ref,
    so the rule must hand back THAT job, not merely say one exists."""
    _client, db_path = _panel(tmp_path)
    _interpretation_in(db_path, "completed")
    waiting = _interpretation_in(db_path, "queued")

    from scrapex import db as dbmod
    conn = dbmod.connect(db_path)
    try:
        found = datasetjob.waiting_interpretation(conn, "muqawil_org")
    finally:
        conn.close()

    assert found is not None and found["job_ref"] == waiting, found


def test_the_rule_is_not_read_through_a_window(tmp_path):
    """A WAITING ONE OLDER THAN TWO HUNDRED OTHERS IS STILL WAITING. The first version read
    `jobs.list_jobs(limit=200)`, newest first, so an interpretation queued before two
    hundred other live jobs fell outside the window and the rule said nothing was
    waiting -- and the chain and the route would both make the duplicate it exists to
    stop."""
    _client, db_path = _panel(tmp_path)
    waiting = _interpretation_in(db_path, "queued")
    from scrapex import db as dbmod
    conn = dbmod.connect(db_path)
    try:
        for _ in range(201):
            jobs.create_job(conn, ["muqawil_org"], RunMode.UPDATE,
                            job_kind="directory_crawl", commit=False)
        conn.commit()
        found = datasetjob.waiting_interpretation(conn, "muqawil_org")
    finally:
        conn.close()

    assert found is not None and found["job_ref"] == waiting, (
        f"201 newer live jobs hid the waiting interpretation: {found}")


def test_of_two_waiting_the_rule_names_the_one_that_starts_first(tmp_path):
    """Two can be waiting -- one queued before this PR, or by a caller that is not the
    route. The worker starts the OLDEST first, so that is the one that will read the
    pages, and the ref he is sent to must be that one."""
    _client, db_path = _panel(tmp_path)
    first = _interpretation_in(db_path, "queued")
    _interpretation_in(db_path, "queued")
    from scrapex import db as dbmod
    conn = dbmod.connect(db_path)
    try:
        found = datasetjob.waiting_interpretation(conn, "muqawil_org")
    finally:
        conn.close()

    assert found is not None and found["job_ref"] == first, found


def _write_lock_is_held(db_path) -> bool:
    """Whether some connection holds the write lock: a second one asking for it with no
    patience at all is refused."""
    other = sqlite3.connect(db_path, timeout=0)
    try:
        other.execute("BEGIN IMMEDIATE")
    except sqlite3.OperationalError:
        return True
    else:
        other.rollback()
        return False
    finally:
        other.close()


def test_the_route_asks_with_the_write_lock_held(tmp_path, monkeypatch):
    """TWO PRESSES A MOMENT APART ARE TWO THREADS OF ONE ENGINE, and the rule is asked
    once by each. Asked without the lock, both can hear "nothing is waiting" before
    either has written, and both write, which is #779's double press arriving by the one
    path this refusal was built to close. Asked under the lock, the second waits for the
    first to commit and then hears the truth."""
    client, db_path = _panel(tmp_path)
    held = []
    real = datasetjob.waiting_interpretation

    def probing(conn, source_key):
        held.append(_write_lock_is_held(db_path))
        return real(conn, source_key)

    monkeypatch.setattr(datasetjob, "waiting_interpretation", probing)

    first = _press_interpret(client)
    second = _press_interpret(client)

    assert held == [True, True], (
        f"the route asked whether one was waiting without the write lock: {held}")
    assert (first.status_code, second.status_code) == (200, 409), (first.text, second.text)
    assert not _write_lock_is_held(db_path), (
        "a refused press kept the write lock, so the engine's next writer waits on a "
        "request that has already answered")

