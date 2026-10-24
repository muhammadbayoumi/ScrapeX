"""`/api/sources` asks each question once, and no question reads what it does not need.

MEASURED 2026-10-24 on a read-only copy of his 2,475,528,192-byte warehouse, through the
real app: the route took 1.797 s of work and 200 statements. His engine pays several
times that (#1767), so live it answered in 2.9-6.4 s, 10.7 s cold, against the
5,000 ms the panel gives it (`destinationData`, `extension/startup.js`). Every page but
Jobs said "Couldn't reach the engine" about an engine that was up (#1769).

Three repetitions cost most of it, and each is a test here:

    resumable_runs     6 calls, 3 of them the same site's: muqawil's three datasets,
                       159 ms each. Every call scanned all 126,848 snapshots, 22 ms
                       even for a site with no candidate job.
    observation count  17 statements, one a source, each reading all 102,528
                       observations: 342 ms, a source with none paying 19 ms.
    variant count      the same shape over 14,320 variants: 122 ms.

After: 0.560 s and 164 statements on the same copy, and the route's JSON byte-identical.

SO THE PROPERTY IS THE WORK, NOT THE TIME. A fixture holds a few hundred rows and every
timing on it would pass. What grew on his warehouse was how many times a question was
asked and how many rows each asking read, so those are what is pinned: calls counted
through a spy, statements through `set_trace_callback`, and rows read as SQLite's own
count of virtual-machine steps through `set_progress_handler`.
"""
from __future__ import annotations

import collections
import re
import sqlite3

import pytest

pytest.importorskip("fastapi")

from scrapex import db as dbmod
from scrapex import directoryjob, jobs
from scrapex.ingest import ingest_payloads
from scrapex.reports import list_sources, source_summary
from scrapex.vocab import JobStatus
from tests.test_a_cancelled_crawls_pages_are_not_lost import _stopped_run
from tests.test_ingest import make_entry, make_payload, one_row
from tests.test_one_card_per_site_not_one_per_dataset import (
    SITE,
    _warehouse,
)

#: `extension` because the number this file is written against -- `destinationData`
#: at 5,000 ms in `extension/startup.js` -- lives on the extension side, the reason
#: `test_the_health_poll_does_not_scan_the_warehouse.py` gives for its own mark.
pytestmark = pytest.mark.extension


def _steps(conn: sqlite3.Connection, ask) -> int:
    """How many virtual-machine steps SQLite takes to answer `ask()` on `conn`.

    The handler runs once every step, so the count is the work itself: a statement
    that reads a table row by row takes steps for every row it reads, and one that
    seeks an index takes the same steps whatever the table holds.
    """
    taken = 0

    def tick() -> int:
        nonlocal taken
        taken += 1
        return 0

    conn.set_progress_handler(tick, 1)
    try:
        ask()
    finally:
        conn.set_progress_handler(None, 1)
    return taken


# ---- one question per site, not per card --------------------------------------------


@pytest.fixture()
def three_datasets(tmp_path):
    """Three datasets on muqawil, as his warehouse holds them, and a stopped crawl of
    the site holding pages. Not related as parent and child (`relate=False`), so two
    cards stand on one site and the answer each card carries is visible."""
    client = _warehouse(tmp_path, relate=False, chain=True)
    conn = client.app.state.general_database.connect()
    try:
        stopped = _stopped_run(conn, JobStatus.CANCELLED, pages=4)
        listed = [row[0] for row in conn.execute(
            "SELECT d.dataset_key FROM dataset_definition AS d "
            "JOIN source_site AS s ON s.source_id = d.source_id "
            "WHERE s.source_key = ? AND d.valid_to IS NULL", (SITE,))]
    finally:
        conn.close()
    assert len(listed) == 3, (
        f"the premise is three datasets on one site, and the warehouse holds {listed}")
    return client, stopped


def test_a_site_is_asked_for_its_stopped_run_once_however_many_datasets_it_holds(
        three_datasets, monkeypatch):
    """THE PROPERTY. A stopped run belongs to the site, so a site with three datasets
    asks once: before #1769 it asked three times, 159 ms each on his warehouse."""
    client, _stopped = three_datasets
    asked = collections.Counter()
    real = directoryjob.resumable_runs

    def counted(conn, source_key, *args, **kwargs):
        asked[source_key] += 1
        return real(conn, source_key, *args, **kwargs)

    monkeypatch.setattr(directoryjob, "resumable_runs", counted)

    response = client.get("/api/sources")

    assert response.status_code == 200, response.text
    assert asked[SITE] == 1, (
        f"/api/sources asked for {SITE}'s stopped run {asked[SITE]} times in one "
        "request, once per dataset card, which is how it reached 6 s on his engine")
    assert set(asked.values()) == {1}, f"a site was asked more than once: {asked}"


def test_every_card_of_the_site_still_carries_the_stopped_run(three_datasets):
    """Asked once, told to every card: a card after the first must not lose the offer
    the first one carries."""
    client, stopped = three_datasets

    rows = client.get("/api/sources").json()["sources"]
    cards = [row for row in rows if row.get("site_key") == SITE]

    assert len(cards) == 2, f"expected two muqawil cards, got {cards}"
    for card in cards:
        offered = card["work_waiting"]["resumable"]
        assert offered is not None, f"{card['source_key']} lost the stopped run"
        assert offered["run_ref"] == stopped
        assert offered["readings"] == 4


# ---- a stopped run is found by its ref, not by reading every page --------------------


@pytest.fixture()
def conn(tmp_path):
    """The real schema, and the site `_stopped_run` writes for."""
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


def _other_sites_pages(conn: sqlite3.Connection, other: str, first: int,
                       pages: int) -> None:
    """`pages` more snapshots that another site's crawl `other` stored, under refs that
    sort beside every `job-...` ref, so a range that leaked would reach them."""
    conn.executemany(
        "INSERT INTO generic_page_snapshot "
        "  (source_url, content_type, html_content, content_hash, crawl_run_ref) "
        "VALUES (?, 'text/html', X'00', ?, ?)",
        [(f"https://example.test/{other}/{page}", f"hash-{other}-{page}",
          f"job-{other}-cell{page}-a1") for page in range(first, first + pages)])
    conn.commit()


@pytest.mark.parametrize("stopped_here", [False, True],
                         ids=["no stopped run", "a stopped run of four pages"])
def test_asking_costs_the_same_however_many_other_pages_are_stored(conn, stopped_here):
    """Before #1769 every call read every snapshot, so its cost grew with each page any
    crawl of any site stored: 126,848 of them on his warehouse, 22 ms a call for a site
    with nothing to offer. The answer is the candidate jobs' pages, so only they may
    cost anything."""
    if stopped_here:
        _stopped_run(conn, JobStatus.CANCELLED, pages=4)
    # ONE JOB FOR THE OTHER SITE, made before the first count: the jobs are read, and
    # a second one would be a row the second count reads that the first did not.
    other = jobs.create_job(conn, ["oman_tenderboard"], job_kind=directoryjob.JOB_KIND)
    _other_sites_pages(conn, other, 0, 20)

    def ask():
        return directoryjob.resumable_runs(conn, SITE, limit=1)

    # ASKED ONCE BEFORE COUNTING: the first asking also prepares the statements, and
    # those steps are paid once per connection, not once per page.
    answer = ask()
    few = _steps(conn, ask)
    _other_sites_pages(conn, other, 20, 2000)
    many = _steps(conn, ask)

    assert ask() == answer
    assert many == few, (
        f"asking for {SITE}'s stopped run took {few} steps beside 20 other pages and "
        f"{many} beside 2,020, so it reads pages that cannot be in its answer")


def test_the_ref_match_is_the_prefix_and_nothing_beside_it(conn):
    """THE RANGE MUST MEAN EXACTLY WHAT THE PREFIX MEANT. A run's pages are stored
    under `job-<ref>` or `job-<ref>-<cell>`; each decoy below sorts next to one of
    those and differs from it by one byte, so a bound that is off by one counts it."""
    ref = jobs.create_job(conn, [SITE], job_kind=directoryjob.JOB_KIND)
    conn.execute("UPDATE crawl_job SET status = ?, finished_at = '2026-10-24T05:00:00Z' "
                 "WHERE job_ref = ?", (JobStatus.CANCELLED.value, ref))
    own = [f"job-{ref}", f"job-{ref}-", f"job-{ref}-riyadh-a1", f"job-{ref}-￿"]
    decoys = [
        f"job-{ref}.", f"job-{ref}.-a1",        # `.` is the bound itself
        f"job-{ref},", f"job-{ref},-a1",        # `,` is the byte before `-`
        f"job-{ref}0-a1",                       # a longer ref this one prefixes
        f"job-{ref}x", f"JOB-{ref}-a1",
        f"job-{ref[:-1]}-a1",                   # a shorter ref
        "job-" + ref.replace("_", "x", 1) + "-a1",   # `_` read as a LIKE wildcard
        f"{ref}-a1", None,
    ]
    conn.executemany(
        "INSERT INTO generic_page_snapshot "
        "  (source_url, content_type, html_content, content_hash, crawl_run_ref) "
        "VALUES (?, 'text/html', X'00', ?, ?)",
        [(f"https://muqawil.org/{n}", f"hash-{n}", run_ref)
         for n, run_ref in enumerate(own + decoys)])
    conn.commit()

    offered = directoryjob.resumable_runs(conn, SITE)

    assert [run["job_ref"] for run in offered] == [ref], offered
    assert offered[0]["readings"] == len(own), (
        f"counted {offered[0]['readings']} pages for {ref}, which stored {len(own)}: "
        "the ref match took a neighbour or dropped one of its own")


# ---- each source's counts come from one pass over each table -------------------------


#: The two tables each source's summary counted by reading all of them. A statement
#: naming one is a pass over it.
COUNTED = re.compile(r"\b(price_observation|source_variant)\b")


def _passes(statements: list[str]) -> list[str]:
    """The statements that pass over a counted table. The approved-match count joins
    `source_variant` from `source_variant_match`, a table that holds only what he
    approved -- 0.1 ms for all 17 sources on his warehouse -- so it is not one."""
    return [sql for sql in statements
            if COUNTED.search(sql) and "source_variant_match" not in sql]


def _register(conn: sqlite3.Connection, keys) -> None:
    conn.executemany(
        "INSERT INTO source_site (source_key, source_name, base_url, platform) "
        "VALUES (?, ?, ?, 'custom')",
        [(key, key, f"https://{key.lower()}.example") for key in keys])
    conn.commit()


def test_a_listing_reads_the_collected_tables_once_however_many_sources_it_lists(conn):
    """THE PROPERTY. Ten more sources cost the listing no further pass over the
    observations or the variants: before #1769 they cost twenty, two a source."""
    seen: list[str] = []
    _register(conn, [f"FEW{i}" for i in range(2)])
    conn.set_trace_callback(seen.append)
    list_sources(conn)
    few = _passes(seen)

    _register(conn, [f"MORE{i}" for i in range(10)])
    seen.clear()
    list_sources(conn)
    many = _passes(seen)
    conn.set_trace_callback(None)

    assert len(few) == 2, f"expected one pass over each counted table: {few}"
    assert len(many) == len(few), (
        f"the listing read the collected tables {len(few)} times for 3 sources and "
        f"{len(many)} times for 13, once per source, which cost 464 ms on his warehouse")


def test_each_source_is_given_its_own_counts(conn):
    """Counted together, told apart: every source's numbers in the listing are the ones
    its summary alone gives, and a source with none says none."""
    ingest_payloads(conn, make_entry(source_key="BIG", source_name="Big"), [
        make_payload([one_row(external_product_id="1", external_variant_id="11"),
                      one_row(external_product_id="1", external_variant_id="12"),
                      one_row(external_product_id="2", external_variant_id="21")],
                     source_key="BIG"),
        make_payload([one_row(external_product_id="1", external_variant_id="11",
                              price="1,300.00")],
                     source_key="BIG", scraped_at="2026-07-17T10:00:00Z"),
    ])
    ingest_payloads(conn, make_entry(source_key="SMALL", source_name="Small"), [
        make_payload([one_row(external_product_id="9", external_variant_id="91")],
                     source_key="SMALL")])
    _register(conn, ["EMPTY"])

    listed = {s.source_key: (s.products, s.variants, s.observations)
              for s in list_sources(conn)}
    alone = {key: (s.products, s.variants, s.observations)
             for key in listed for s in [source_summary(conn, key)]}

    assert listed["BIG"] == (2, 3, 4), listed
    assert listed["SMALL"] == (1, 1, 1), listed
    assert listed["EMPTY"] == (0, 0, 0), listed
    assert listed == alone, (
        "the listing's counts differ from each source's own summary, so one of the "
        f"two counts something else: listed {listed}, alone {alone}")


def test_a_missing_source_still_has_no_summary(conn):
    """The single-source path keeps its answer for a key nothing registered."""
    assert source_summary(conn, "NO_SUCH_SOURCE") is None


def test_the_index_the_range_searches_leads_with_the_ref(conn):
    """The range is cheap only because `idx_snapshot_run_url` leads with the ref, so
    the step counts above rest on it."""
    columns = [row[2] for row in conn.execute(
        "PRAGMA index_info('idx_snapshot_run_url')")]
    assert columns[:1] == ["crawl_run_ref"], columns
