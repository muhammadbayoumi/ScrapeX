"""A partitioned listing crawl, and the four ways it could lie about being complete.

WHAT THESE TESTS ARE FOR. `scrapex/partitioncrawl.py` produces a sentence — "this
cell is complete" — and the whole value of the module is that the sentence is a
proof rather than a hope. Four ways it could be neither, and each has a test that
was made to fail first:

  * THE WITNESS COMPARING THE WRONG THING. DEC-11 measured a re-fetched page 1
    whose id order was identical and whose bytes were NOT. A byte comparison would
    have failed every witness, certified nothing, ever, and looked like it was
    working the entire time. So: identical order with different bytes must pass,
    and the same ids in a different order must fail.
  * A UNION MISTAKEN FOR A PROOF. Two reads in two generations can between them
    account for every row in a cell without either read having covered it. That is
    the exact shape of the six-pass sweep's answer, and it must not be reported as
    completeness.
  * A ROW IN NO CELL. Fifty-six proven cells that together declare fewer rows than
    the listing prove fifty-six things and not the one that was asked. muqawil's
    was 1,437 contractors who publish no location.
  * A RESUME REPORTING A FALSE DEFICIT. A resumed run does not re-fetch what it
    stored, so nothing harvests those pages' ids unless they are read back off the
    evidence — and a cell would then look emptier than it was read.

No network anywhere here: the site is a dictionary with a cache generation.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.pagesource import WHOLE, Cell
from scrapex.partitioncrawl import (
    DRY_ATTEMPTS,
    NotASubdivision,
    ScopeNotPartitionable,
    crawl_partition,
    size_cell,
    witness,
)

BASE = "https://site.test"
_LAST = re.compile(r'href="[^"]*[?&]page=(\d+)"')
_ID = re.compile(r'href="/[a-z]{2}/row/(\d+)/143"')


class Directory:
    """A paginated listing whose order is a CACHE GENERATION, as muqawil's is.

    The point of the fake is the generation, not the HTML. Inside one generation
    pagination is an exact partition; `roll` is the site's cache turning over
    mid-crawl, which is the event the witness exists to detect.
    """

    def __init__(self, cells: dict[str, list[str]], *, per_page: int = 4) -> None:
        self._order = {label: list(ids) for label, ids in cells.items()}
        self._per = per_page
        #: Bumped on every fetch so no two responses are byte-identical — which is
        #: what the real site does, and what makes a byte-comparison witness a lie.
        self._noise = 0
        self.fetched: list[str] = []

    def roll(self, label: str, order: list[str]) -> None:
        self._order[label] = list(order)

    def last_page(self, label: str) -> int:
        rows = len(self._order[label])
        return max(1, -(-rows // self._per))

    def page(self, label: str, number: int) -> str:
        self._noise += 1
        ids = self._order[label][(number - 1) * self._per:number * self._per]
        links = "".join(f'<a href="/en/row/{one}/143">row</a>' for one in ids)
        return (f"<html><!-- render {self._noise} -->{links}"
                f'<a href="?page={self.last_page(label)}">&raquo;</a></html>')

    def fetch(self, url: str) -> str:
        self.fetched.append(url)
        query = url.split("?", 1)[1]
        parts = dict(pair.split("=", 1) for pair in query.split("&"))
        number = int(parts.pop("page"))
        label = ("-".join(f"{k}_{v}" for k, v in parts.items())) or "whole"
        if label not in self._order:
            raise LookupError(f"no such cell {label!r}")
        return self.page(label, number)


class Partition:
    """The site half of the agreement, over the fake directory."""

    site_key = "site_test"

    def __init__(self, directory: Directory, *, cells: tuple[Cell, ...],
                 locales: tuple[str, ...] = ("en",),
                 primary_locale: str = "en") -> None:
        self._directory = directory
        self._cells = cells
        self.locales = locales
        self.primary_locale = primary_locale

    def cells(self) -> tuple[Cell, ...]:
        return self._cells

    def listing_url(self, base_url: str, *, locale: str, page: int,
                    cell: Cell = WHOLE) -> str:
        query = f"{cell.query}&page={page}" if cell.query else f"page={page}"
        return f"{base_url.rstrip('/')}/{locale}/list?{query}"

    def read_last_page(self, html: str) -> int:
        found = [int(one) for one in _LAST.findall(html)]
        if not found:
            raise ValueError("no pagination on this page")
        return max(found)

    def read_ids(self, html: str) -> tuple[str, ...]:
        return tuple(_ID.findall(html))

    def in_cell(self, cell: Cell, *, last_page: int):
        return _CellSource(self, cell, last_page)


class _CellSource:
    """A `PageSource` naming exactly one cell's pages, in every locale."""

    def __init__(self, partition: Partition, cell: Cell, last_page: int) -> None:
        self.site_key = partition.site_key
        self._partition = partition
        self._cell = cell
        self._last = last_page

    def listing_urls(self, base_url: str):
        for page in range(1, self._last + 1):
            for locale in self._partition.locales:
                yield self._partition.listing_url(
                    base_url, locale=locale, page=page, cell=self._cell)

    def detail_urls(self, page):
        return ()

    def belongs_to_slice(self, page, row_index, slice_of):
        return True


def cell(**params: object) -> Cell:
    return Cell(params=tuple((name, str(value)) for name, value in params.items()))


@pytest.fixture()
def conn(tmp_path: Path):
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    connection = registry.engine.connect()
    try:
        yield connection
    finally:
        connection.close()


def register(conn, scope: str = "listing_only") -> None:
    conn.execute(
        "INSERT INTO source_site (source_key, source_name, base_url, crawl_scope) "
        "VALUES ('site_test','A site',?,?)", (BASE, scope))
    conn.commit()


def run(conn, partition: Partition, directory: Directory, **kwargs):
    return crawl_partition(conn, partition, BASE, fetch=directory.fetch,
                           run_ref=kwargs.pop("run_ref", "run-1"),
                           dataset_key="rows", **kwargs)


# ---- sizing: read the tail, never multiply by the page size ------------------

def test_a_cell_is_sized_from_its_own_paginator_and_its_tail_is_read():
    """`(L−1)·S + c`, and `c` is FETCHED.

    `L·S` would read this nine-row cell as twelve. On the real listing the last
    page carried 15 cards on 2026-08-16, 2 on the morning of 2026-08-20 and 13
    that evening — a constant would have been wrong on all three days.
    """
    directory = Directory({"region_id_1": [str(n) for n in range(1, 10)]})
    partition = Partition(directory, cells=(cell(region_id=1),))
    size = size_cell(directory.fetch, partition, BASE, cell(region_id=1))
    assert (size.last_page, size.cards_per_page, size.tail_cards) == (3, 4, 1)
    assert size.declared == 9
    assert size.requests == 2


def test_a_single_page_cell_costs_one_request_and_not_two():
    """Page 1 IS the last page, so re-fetching it to count its tail is a request
    spent to learn what is already in hand. Fifty-six cells make that real."""
    directory = Directory({"region_id_1": ["1", "2"]})
    partition = Partition(directory, cells=(cell(region_id=1),))
    size = size_cell(directory.fetch, partition, BASE, cell(region_id=1))
    assert (size.last_page, size.declared, size.requests) == (1, 2, 1)
    assert len(directory.fetched) == 1


# ---- the witness, which is the whole method ---------------------------------

def test_the_witness_holds_on_an_identical_ID_SEQUENCE_WITH_DIFFERENT_BYTES():
    """THE CORRECTION THAT WOULD HAVE BROKEN EVERYTHING.

    DEC-11's step 2 originally said "byte-identical". Measured: a re-fetched page
    1 whose id order was identical was NOT byte-identical — the body carries
    per-render noise, and the email address alone is XOR-ed under a key that
    rotates per render. So this test fetches the same page twice, asserts the
    bodies DIFFER, and asserts the witness holds anyway.
    """
    directory = Directory({"region_id_1": ["1", "2", "3", "4"]})
    partition = Partition(directory, cells=(cell(region_id=1),))
    first = directory.page("region_id_1", 1)
    again = directory.page("region_id_1", 1)
    assert first != again, "the fake must carry per-render noise or it proves nothing"
    assert partition.read_ids(first) == partition.read_ids(again)

    held, note = witness(directory.fetch, partition, BASE, cell(region_id=1),
                         partition.read_ids(first))
    assert held, note
    assert "same order" in note


def test_the_witness_fails_on_the_same_ids_in_a_different_order():
    """A SET WOULD PASS THIS AND MUST NOT. The generation rolling is precisely a
    reordering of the same population, so an unordered comparison would certify
    the one event the witness exists to catch."""
    directory = Directory({"region_id_1": ["1", "2", "3", "4"]})
    partition = Partition(directory, cells=(cell(region_id=1),))
    before = partition.read_ids(directory.page("region_id_1", 1))
    directory.roll("region_id_1", ["4", "3", "2", "1"])

    held, note = witness(directory.fetch, partition, BASE, cell(region_id=1), before)
    assert not held
    assert set(partition.read_ids(directory.page("region_id_1", 1))) == set(before)
    assert "reordered" in note and "4 of 4 ids in common" in note


def test_a_witness_told_page_one_was_never_read_refuses_rather_than_passes():
    """`None` IS NOT `()`, AND THAT DISTINCTION IS WORTH A CELL'S PROOF.

    `None` is "page 1 never arrived" — the absence of evidence, which must never
    read as a pass. `()` is "page 1 arrived and published no rows", which is a real
    state on the live site (`region_id=8 & company_size=big` today) and IS
    witnessable. Handing both in as `()` cost the empty cell its proof, and one
    unprovable cell makes the whole partition unprovable.
    """
    directory = Directory({"region_id_1": ["1"]})
    partition = Partition(directory, cells=(cell(region_id=1),))

    held, note = witness(directory.fetch, partition, BASE, cell(region_id=1), None)
    assert not held
    assert "never read in this attempt" in note

    # And a cell whose page 1 DID arrive empty, against a page that is not.
    held, note = witness(directory.fetch, partition, BASE, cell(region_id=1), ())
    assert not held, "one id against none is a difference, not an empty cell"
    assert "reordered" in note


# ---- a cell read whole, inside one generation --------------------------------

def test_a_cell_read_inside_one_generation_is_proven_complete(conn):
    """The sentence this module exists to be able to say."""
    register(conn)
    ids = [str(n) for n in range(1, 10)]
    directory = Directory({"whole": list(ids), "region_id_1": list(ids)})
    partition = Partition(directory, cells=(cell(region_id=1),))

    outcome = run(conn, partition, directory)

    only = outcome.cells[0]
    assert only.provably_complete
    assert only.observed_deficit == 0
    assert only.proof is not None and only.proof.distinct == 9
    assert outcome.exhaustiveness_deficit == 0
    assert outcome.deficit == 0
    assert outcome.provably_complete
    assert "PROVABLY COMPLETE" in str(outcome)


def test_a_rolled_generation_fails_the_witness_and_the_ids_still_count(conn):
    """DEC-11 is explicit: a failed witness still contributes every id it read.
    They are the only evidence that exists for those contractors."""
    register(conn)
    ids = [str(n) for n in range(1, 10)]
    directory = Directory({"whole": list(ids), "region_id_1": list(ids)})
    partition = Partition(directory, cells=(cell(region_id=1),))

    # THE ROLL MUST LAND INSIDE THE READ, NOT INSIDE THE SIZING, and the first
    # draft of this test got that wrong: `size_cell` fetches page 1 and page L
    # too, so "roll on page 3" rolled before the read began — the cell was then
    # read entirely inside the NEW generation, the witness held, and the test
    # failed by proving the cell complete. Counted rather than matched on the URL.
    hits: list[str] = []

    def rolling(url: str) -> str:
        html = directory.fetch(url)
        if url.endswith("region_id=1&page=3"):
            hits.append(url)
            if len(hits) == 2:
                # 1 = sizing's tail read, 2 = the last page of the read itself.
                directory.roll("region_id_1", list(reversed(ids)))
        return html

    outcome = crawl_partition(conn, partition, BASE, fetch=rolling,
                              run_ref="run-1", dataset_key="rows",
                              max_attempts=1)
    only = outcome.cells[0]
    assert not any(a.witnessed for a in only.attempts), "the generation rolled"
    assert len(only.ids) == 9, "the ids it read still count"
    assert only.observed_deficit == 0
    # THE WITNESS FAILED AND THE CELL IS STILL COMPLETE, by the count. This test
    # used to assert `not provably_complete` here, which was the wrong claim — see
    # `test_a_union_across_two_generations_IS_a_proof`.
    assert only.provably_complete
    assert only.proof_kind == "count"
    assert "[by count]" in str(only)
    assert outcome.provably_complete


def test_a_retry_after_a_rolled_generation_earns_the_proof(conn):
    """THE RETRY IS THE METHOD, not a workaround for it.

    DEC-11 measured the generation floor at 157 s and priced a cell above ~31
    pages as one that MAY fail its witness — «that is a cost, not a correctness
    problem». This is that sentence made testable: the same cell, read again while
    nothing rolls under it, comes back proven — and the proof is the SECOND
    attempt's own ids, never the union with the first.
    """
    register(conn)
    ids = [str(n) for n in range(1, 10)]
    directory = Directory({"whole": list(ids), "region_id_1": list(ids)})
    partition = Partition(directory, cells=(cell(region_id=1),))
    # THE ROLL MUST LAND BEFORE THE LAST PAGE, not after it. Rolling after page 3
    # left the first read holding all nine ids, so the COUNTING proof closed the cell
    # on attempt one and there was no retry to observe. Rolling before page 2 makes
    # the first read genuinely partial — 5 distinct of 9 — which is the case a retry
    # exists for.
    hits: list[str] = []

    def rolling(url: str) -> str:
        if url.endswith("region_id=1&page=2"):
            hits.append(url)
            if len(hits) == 1:
                directory.roll("region_id_1", list(reversed(ids)))
        return directory.fetch(url)

    outcome = crawl_partition(conn, partition, BASE, fetch=rolling,
                              run_ref="run-1", dataset_key="rows")
    only = outcome.cells[0]
    assert len(only.attempts) == 2
    assert not only.attempts[0].witnessed, "the first read straddled two generations"
    assert only.attempts[0].distinct < only.size.declared, "and was partial"
    assert only.provably_complete
    assert only.proof is only.attempts[1], "the second read held one generation"
    assert only.proof_kind == "witness"
    assert outcome.provably_complete


def test_a_union_across_two_generations_IS_a_proof(conn):
    """THIS TEST ASSERTED THE OPPOSITE AND THE ASSERTION WAS WRONG.

    It was written as *"a union across two generations is NOT a proof"*, on the
    reasoning that the union "can reach N by luck". There is no luck in it: every id
    came off this cell's own filtered pages, so the cell contains at least the
    distinct ids seen, and it declares exactly eight. Eight distinct of eight
    declared IS complete, whether one read produced them or five did.

    THE ERROR WAS NOT FREE, which is why it is corrected in place rather than
    quietly. Requiring the witness made the six cells above the 31-page ceiling
    unprovable BY CONSTRUCTION — no single read of them can hold one generation — and
    the first real run reported a 3,690 deficit with no route to close it.
    """
    register(conn)
    everyone = [str(n) for n in range(1, 9)]
    directory = Directory({"whole": list(everyone), "region_id_1": list(everyone)})
    partition = Partition(directory, cells=(cell(region_id=1),))

    # Each attempt sees four of the eight, in a generation of its own, and each
    # attempt's own witness HOLDS — which is what makes this the dangerous case
    # rather than an obvious one. Sized first, so `declared` is 8; the roll is
    # counted from the cell's page 1 and the sizing fetch is hit number one.
    # Page 1 of the cell is fetched five times: 1 sizing, 2 the first read, 3 its
    # witness, 4 the second read, 5 its witness. Rolling on 2 and 4 only means each
    # attempt reads one half AND ITS OWN WITNESS HOLDS — which is what makes this
    # the dangerous case rather than an obvious one.
    hits: list[str] = []
    schedule = {2: everyone[:4] * 2, 4: everyone[4:] * 2}

    def rolling(url: str) -> str:
        if url.endswith("region_id=1&page=1"):
            hits.append(url)
            order = schedule.get(len(hits))
            if order is not None:
                directory.roll("region_id_1", order)
        return directory.fetch(url)

    outcome = crawl_partition(conn, partition, BASE, fetch=rolling,
                              run_ref="run-1", dataset_key="rows")
    only = outcome.cells[0]
    assert len(only.attempts) == 2, "a failed witness must earn the retry"
    assert len(only.ids) == 8, "the union accounts for every row"
    assert only.observed_deficit == 0
    # AND IT IS A PROOF, WHICH IS THE OPPOSITE OF WHAT THIS TEST FIRST ASSERTED.
    # Neither read held a generation, so neither is witnessed — and it does not
    # matter: eight distinct ids came off a cell that declares eight, so the cell
    # contains exactly them. See `counted_complete`.
    assert only.provably_complete
    assert only.proof_kind == "count"
    assert only.proof is None, "no single attempt accounted for the whole cell"
    # AND EACH ATTEMPT'S OWN WITNESS HELD, which is what makes this the subtle case
    # rather than an obvious one: both reads were internally consistent and neither
    # covered the cell. The witness is not the thing that was missing.
    assert all(a.witnessed for a in only.attempts)
    assert all(a.distinct < only.size.declared for a in only.attempts)


def test_a_retry_stores_its_own_evidence_rather_than_being_skipped(conn):
    """A RETRY EXISTS TO READ A FRESH GENERATION, so it must re-fetch. Reusing the
    run ref would let `already_stored` skip every page and the retry would witness
    the same stale ordering for ever."""
    register(conn)
    # NINE IDS, NOT FOUR. A four-id cell is one page, so the first read closes it by
    # counting and there is no second attempt whose evidence to check.
    ids = [str(n) for n in range(1, 10)]
    directory = Directory({"whole": list(ids), "region_id_1": list(ids)})
    partition = Partition(directory, cells=(cell(region_id=1),))

    def rolling(url: str) -> str:
        # Rolled on EVERY fetch, so no read can ever be complete or witnessed —
        # which is what forces both attempts to happen and be observable.
        html = directory.fetch(url)
        directory.roll("region_id_1", list(reversed(directory._order["region_id_1"])))
        return html

    outcome = crawl_partition(conn, partition, BASE, fetch=rolling,
                              run_ref="run-1", dataset_key="rows")
    only = outcome.cells[0]
    refs = [attempt.run_ref for attempt in only.attempts]
    assert refs == ["run-1-region_id_1-a1", "run-1-region_id_1-a2"]
    assert all(attempt.pages_read for attempt in only.attempts), \
        "the second attempt must have fetched, not been skipped"
    assert all(not attempt.skipped for attempt in only.attempts)


# ---- the exhaustiveness audit ------------------------------------------------

def test_a_row_in_no_cell_is_counted_and_not_absorbed(conn):
    """1,437 CONTRACTORS, ON THE REAL SITE. `Σ N` over regions 1–13 was 15,966
    against a listing of 17,403, and the shortfall was every contractor whose card
    publishes no location. A partition method that cannot see that is unsound; one
    that reports it can be fixed, and was — `region_id=0` addresses exactly them."""
    register(conn)
    directory = Directory({
        "whole": [str(n) for n in range(1, 13)],
        "region_id_1": [str(n) for n in range(1, 9)],
    })
    partition = Partition(directory, cells=(cell(region_id=1),))

    outcome = run(conn, partition, directory)
    assert outcome.cells[0].provably_complete, "the cell itself is complete"
    assert outcome.declared_sum == 8
    assert outcome.whole.declared == 12
    assert outcome.exhaustiveness_deficit == 4
    assert outcome.deficit == 4
    assert not outcome.provably_complete, \
        "a proven cell is not a proven listing while rows sit outside every cell"


def test_two_cells_that_cover_the_listing_prove_it_complete(conn):
    register(conn)
    everyone = [str(n) for n in range(1, 13)]
    directory = Directory({
        "whole": everyone,
        "region_id_1": everyone[:8],
        "region_id_2": everyone[8:],
    })
    partition = Partition(directory,
                          cells=(cell(region_id=1), cell(region_id=2)))
    outcome = run(conn, partition, directory)
    assert outcome.exhaustiveness_deficit == 0
    assert outcome.deficit == 0
    assert outcome.provably_complete
    assert all(one.provably_complete for one in outcome.cells)


# ---- what the site showed us, kept ------------------------------------------

def test_every_id_the_site_showed_reaches_the_sightings_ledger(conn):
    """THE 10001274 INCIDENT. Six passes saw at least 17,283 contractors, the count
    reached a log file and the ids died with the process. Written per attempt, so a
    crawl killed in cell forty leaves thirty-nine cells of sightings."""
    register(conn)
    ids = [str(n) for n in range(1, 10)]
    directory = Directory({"whole": list(ids), "region_id_1": list(ids)})
    partition = Partition(directory, cells=(cell(region_id=1),))

    outcome = run(conn, partition, directory)
    stored = {row[0] for row in conn.execute(
        "SELECT external_id FROM dataset_sighting WHERE dataset_key = 'rows'")}
    assert stored == set(ids)
    assert outcome.newly_sighted == 9


def test_a_resumed_run_reads_the_ids_of_skipped_pages_off_disk(conn):
    """THE FALSE DEFICIT A RESUME WOULD OTHERWISE REPORT.

    `snapshotcrawl`'s resume skips urls this run already stored — correctly, they
    are on disk. But a skipped page is never fetched, so nothing harvests its ids
    and the cell looks emptier than it was read. Re-parsing the stored copy costs
    no request, which is the whole economics of storing it.

    The witness then legitimately fails, because pages recovered from disk were
    read in an earlier generation. That is the right answer, not a shortcoming.
    """
    register(conn)
    ids = [str(n) for n in range(1, 10)]
    directory = Directory({"whole": list(ids), "region_id_1": list(ids)})
    partition = Partition(directory, cells=(cell(region_id=1),))

    run(conn, partition, directory, run_ref="interrupted", max_attempts=1)
    before = len(directory.fetched)

    again = run(conn, partition, directory, run_ref="interrupted", max_attempts=1)
    only = again.cells[0]
    assert only.attempts[0].skipped, "the resume must have skipped stored pages"
    assert only.attempts[0].recovered, "and read their ids back off the evidence"
    assert len(only.ids) == 9, "so the deficit is real and not an artefact of resuming"
    assert only.observed_deficit == 0
    # Sizing and the witness still cost requests; the cell's own pages did not.
    assert len(directory.fetched) - before < 9


# ---- the cells that cannot be witnessed at any price ------------------------

def test_a_cell_above_the_witness_ceiling_is_read_once_and_says_so(conn):
    """FIVE CELLS ON THE REAL SITE STAY ABOVE IT, worst RIYADH×verysmall at ~212
    pages, and no fourth exhaustive axis is fine enough — `user_type` only halves
    it. Retrying those buys ids already in hand and no proof, so the verdict is
    reported honestly instead of bought expensively."""
    register(conn)
    ids = [str(n) for n in range(1, 21)]
    directory = Directory({"whole": list(ids), "region_id_1": list(ids)})
    partition = Partition(directory, cells=(cell(region_id=1),))

    def rolling(url: str) -> str:
        html = directory.fetch(url)
        directory.roll("region_id_1", list(reversed(directory._order["region_id_1"])))
        return html

    outcome = crawl_partition(conn, partition, BASE, fetch=rolling, run_ref="run-1",
                              dataset_key="rows", retry_page_ceiling=2)
    assert len(outcome.cells[0].attempts) == 1, "no retry above the ceiling"
    assert "above the 2-page witness ceiling" in str(outcome)
    assert "region_id_1" in str(outcome)


# ---- the scope, which is the owner's and comes from the database -------------

def test_a_scope_a_listing_partition_cannot_honour_is_refused(conn):
    """REFUSED BEFORE THE FIRST REQUEST, and never narrowed. Under
    `full_then_listing` this crawl would fetch a detail page for every row it
    read: a run priced at ~2,000 requests becomes ~40,000 and takes a day."""
    register(conn, scope="full_then_listing")
    directory = Directory({"whole": ["1"], "region_id_1": ["1"]})
    partition = Partition(directory, cells=(cell(region_id=1),))

    with pytest.raises(ScopeNotPartitionable) as raised:
        run(conn, partition, directory)
    assert "full_then_listing" in str(raised.value)
    assert not directory.fetched, "and it cost nothing to refuse"


# ---- arrivals, and a parse that must not look like a dead page ---------------

def test_arrivals_during_the_crawl_are_reported_and_not_absorbed(conn):
    """«complete as of the start, with N arrivals deferred» — the only honest
    sentence about a live directory. The owner warned the data moves before any of
    this was measured, and the listing's last page grew by ten rows in one day."""
    register(conn)
    ids = [str(n) for n in range(1, 9)]
    directory = Directory({"whole": list(ids), "region_id_1": list(ids)})
    partition = Partition(directory, cells=(cell(region_id=1),))

    def arriving(url: str) -> str:
        html = directory.fetch(url)
        if url.endswith("page=1") and "region_id" in url:
            directory.roll("whole", [*ids, "99", "100"])
        return html

    outcome = crawl_partition(conn, partition, BASE, fetch=arriving,
                              run_ref="run-1", dataset_key="rows")
    assert outcome.arrivals == 2
    assert "GREW by 2 rows" in str(outcome)


def test_a_parse_failure_is_not_reported_as_a_dead_page(conn):
    """The walker turns any exception from `fetch` into a failed page. Letting a
    parse error escape the harvester would therefore discard a page the site served
    perfectly and blame the site for it."""
    register(conn)
    ids = [str(n) for n in range(1, 5)]
    directory = Directory({"whole": list(ids), "region_id_1": list(ids)})

    class Brittle(Partition):
        def read_ids(self, html: str):
            if "page=1" in html or "row 1" in html:
                pass
            if "<!-- render" in html and "boom" not in html:
                return super().read_ids(html)
            raise RuntimeError("boom")

    partition = Brittle(directory, cells=(cell(region_id=1),))
    outcome = run(conn, partition, directory, max_attempts=1)
    stored = conn.execute(
        "SELECT COUNT(*) FROM generic_page_snapshot").fetchone()[0]
    assert stored >= 1, "the pages the site served must still be evidence"
    assert outcome.cells[0].attempts[0].pages_read >= 1


def test_an_empty_cell_is_complete_by_having_nothing_in_it(conn):
    """MEASURED ON THE LIVE SITE, 2026-08-20: `region_id=8 & company_size=big`
    publishes ZERO contractors and still serves a paginator, so `read_last_page`
    answers 1 and `read_ids` answers nothing.

    Its page 1 is read, and it is empty. An earlier draft asked the witness for
    `seen.get(1, ())` — which gives `()` both for a page never read and for a page
    read empty — so this cell could never be witnessed, and ONE unprovable cell
    makes the whole 56-cell partition unprovable for ever. `None` and `()` are
    different facts and the witness is now handed the difference.
    """
    register(conn)
    directory = Directory({"whole": ["1", "2"], "region_id_8": []})
    partition = Partition(directory, cells=(cell(region_id=8),))

    outcome = run(conn, partition, directory)
    only = outcome.cells[0]
    assert only.size.declared == 0
    assert only.provably_complete, "an empty cell is complete, not unprovable"
    assert "complete by having nothing in it" in only.attempts[0].note
    assert "EMPTY — the site publishes no rows" in str(only)
    assert only.observed_deficit == 0


def test_a_cell_whose_page_one_never_arrived_is_not_witnessed(conn):
    """THE OTHER HALF OF THE SAME DISTINCTION. A page 1 that failed to arrive is
    the absence of evidence, and it must not read as an empty cell — otherwise a
    site that 500s on page 1 reports the cell complete."""
    register(conn)
    ids = [str(n) for n in range(1, 10)]
    directory = Directory({"whole": list(ids), "region_id_1": list(ids)})
    partition = Partition(directory, cells=(cell(region_id=1),))
    sized: list[str] = []

    def dying(url: str) -> str:
        if url.endswith("region_id=1&page=1"):
            sized.append(url)
            if len(sized) > 1:          # sizing succeeds, the read's page 1 dies
                raise RuntimeError("500 from the site")
        return directory.fetch(url)

    outcome = crawl_partition(conn, partition, BASE, fetch=dying, run_ref="run-1",
                              dataset_key="rows", max_attempts=1)
    only = outcome.cells[0]
    assert only.size.declared == 9, "the cell is not empty"
    assert not only.provably_complete
    assert "never read in this attempt" in only.attempts[0].note
    assert only.attempts[0].failures, "and the dead page is reported as one"


# ---- the cost report, which must not overstate either -----------------------

def test_one_unsizeable_cell_does_not_end_the_crawl_and_is_named(conn):
    """A CELL THAT WILL NOT SIZE MUST NOT DISCARD FIFTY-FIVE THAT DID.

    `size_cell` raises when a cell's page 1 does not arrive or publishes no
    paginator. Letting that propagate would end a ~2,000-request crawl over one
    cell — the same reasoning `pagewalk` applies to a dead page. The cell is named,
    contributes nothing to `declared_sum`, and therefore appears as an
    exhaustiveness deficit rather than as a smaller directory.
    """
    register(conn)
    directory = Directory({
        "whole": [str(n) for n in range(1, 13)],
        "region_id_1": [str(n) for n in range(1, 9)],
        # `region_id_2` is deliberately absent, so fetching it raises LookupError.
    })
    partition = Partition(directory,
                          cells=(cell(region_id=1), cell(region_id=2)))

    outcome = run(conn, partition, directory)
    assert len(outcome.cells) == 1, "the sized cell was still read"
    assert outcome.cells[0].provably_complete
    assert [label for label, _ in outcome.unsized] == ["region_id_2"]
    assert outcome.declared_sum == 8
    assert outcome.exhaustiveness_deficit == 4, "the unread cell shows as a gap"
    assert not outcome.provably_complete
    assert "could not be sized and were NOT READ" in str(outcome)
    assert "region_id_2" in str(outcome)


def test_a_witness_that_never_fetched_is_not_charged_a_request(conn):
    """A cost report that overstates is as useless as one that understates. The
    witness returns early — without fetching — when page 1 never arrived, so a flat
    `+1` per attempt billed the crawl for a request it did not make."""
    register(conn)
    ids = [str(n) for n in range(1, 10)]
    directory = Directory({"whole": list(ids), "region_id_1": list(ids)})
    partition = Partition(directory, cells=(cell(region_id=1),))
    sized: list[str] = []

    def dying(url: str) -> str:
        if url.endswith("region_id=1&page=1"):
            sized.append(url)
            if len(sized) > 1:
                raise RuntimeError("500 from the site")
        return directory.fetch(url)

    outcome = crawl_partition(conn, partition, BASE, fetch=dying, run_ref="run-1",
                              dataset_key="rows", max_attempts=1,
                              resize_at_end=False)
    attempt = outcome.cells[0].attempts[0]
    assert attempt.witness_requests == 0
    # Sizing 2, pages 2 and 3 read, page 1 attempted and dead, no witness asked.
    # The dead page IS a request — it was spent — and the witness was not.
    assert outcome.cells[0].requests == 5
    assert attempt.pages_read == 2
    assert len(attempt.failures) == 1


def test_a_parse_failure_is_not_counted_as_a_request(conn):
    """A page that arrived and could not be read is already counted in
    `pages_read` and is already stored as evidence. Adding it to `failures` too
    made the cost report charge twice for one page, and blamed the site for it."""
    register(conn)
    ids = [str(n) for n in range(1, 10)]
    directory = Directory({"whole": list(ids), "region_id_1": list(ids)})

    class Brittle(Partition):
        def read_ids(self, html: str):
            # PAGE 2 OF THE CELL AND NOTHING ELSE: it is the only page any fetch
            # returns that carries id 5. Keyed on the content rather than on a
            # call counter, because a counter moves the moment the crawl's request
            # order changes and the test then quietly targets the witness instead.
            if "/row/5/143" in html:
                raise RuntimeError("boom")
            return super().read_ids(html)

    partition = Brittle(directory, cells=(cell(region_id=1),))
    outcome = run(conn, partition, directory, max_attempts=1, resize_at_end=False)
    attempt = outcome.cells[0].attempts[0]
    assert [url for url, _ in attempt.parse_failures] == \
        ["https://site.test/en/list?region_id=1&page=2"]
    assert not attempt.failures, "and it is NOT reported as a page that never came"
    assert attempt.pages_read == 3, "the site served all three pages"
    # Sizing 2 + three pages read + one witness. The unreadable page cost one
    # request, not two.
    assert outcome.cells[0].requests == 6
    assert conn.execute(
        "SELECT COUNT(*) FROM generic_page_snapshot").fetchone()[0] == 3, \
        "and every page the site served is still evidence"


def test_a_witness_that_cannot_be_read_is_a_verdict_and_not_an_end(conn):
    """FOUND BY MAKING THE PARSER THROW. The witness's own fetch and parse were
    unguarded, so one unreadable page 1 out of fifty-six would have raised out of
    `crawl_partition` and discarded every cell already read — after hours of
    fetching. Not being able to witness is precisely what `witnessed=False` means.
    """
    register(conn)
    ids = [str(n) for n in range(1, 5)]
    directory = Directory({"whole": list(ids), "region_id_1": list(ids)})
    reads: list[str] = []

    class Brittle(Partition):
        def read_ids(self, html: str):
            reads.append(html)
            if len(reads) == 4:          # sizing whole, sizing cell, read, WITNESS
                raise RuntimeError("boom")
            return super().read_ids(html)

    partition = Brittle(directory, cells=(cell(region_id=1),))
    outcome = run(conn, partition, directory, max_attempts=1, resize_at_end=False)
    only = outcome.cells[0]
    # THE POINT IS THAT NOTHING RAISED. An unguarded witness would have thrown out of
    # `crawl_partition` and discarded every cell already read.
    assert "the witness could not be read" in only.attempts[0].note
    assert not only.attempts[0].witnessed
    assert len(only.ids) == 4, "the pages it did read still count"
    # And the cell is still complete — by COUNTING, which needs no witness at all.
    # That is the correct outcome: the witness being unreadable costs the cheaper
    # single-pass proof, not the coverage.
    assert only.provably_complete
    assert only.proof_kind == "count"


# ---- the counting proof, and what it costs a heavy cell ----------------------

def test_a_cell_too_big_to_witness_is_closed_by_counting(conn):
    """THE 3,690 DEFICIT'S ROUTE OUT, and the reason the old rule was wrong.

    Six cells were measured above the 31-page ceiling on 2026-08-21 — the worst 236
    pages — so no single read of them can hold one cache generation and the witness
    can never carry them. Under the old rule they were unprovable BY CONSTRUCTION.
    Read repeatedly, their distinct ids accumulate to the declared count, and that is
    a proof.
    """
    register(conn)
    ids = [str(n) for n in range(1, 13)]
    directory = Directory({"whole": list(ids), "region_id_1": list(ids)})
    partition = Partition(directory, cells=(cell(region_id=1),))
    # Rolled on every fetch, so no read is ever internally consistent — the exact
    # condition of a cell larger than one generation.
    def rolling(url: str) -> str:
        html = directory.fetch(url)
        order = directory._order["region_id_1"]
        directory.roll("region_id_1", order[1:] + order[:1])
        return html

    outcome = crawl_partition(conn, partition, BASE, fetch=rolling, run_ref="run-1",
                              dataset_key="rows", retry_page_ceiling=1,
                              heavy_attempts=8, resize_at_end=False)
    only = outcome.cells[0]
    assert not any(a.witnessed for a in only.attempts), "no read held a generation"
    assert only.provably_complete, "and the cell is complete anyway"
    assert only.proof_kind == "count"
    assert len(only.ids) == only.size.declared == 12
    assert len(only.attempts) > 1, "it took more than one read"
    assert "[by count]" in str(only)


def test_a_heavy_cell_gets_more_than_one_read(conn):
    """`RETRY_PAGE_CEILING` used to cut a heavy cell to a SINGLE attempt, on the
    reasoning that a second read "buys ids it already has and no proof" — true of the
    witness, false of the count. That one line is why the first real run left six
    cells with a deficit and no way to close them."""
    register(conn)
    ids = [str(n) for n in range(1, 41)]
    directory = Directory({"whole": list(ids), "region_id_1": list(ids)})
    partition = Partition(directory, cells=(cell(region_id=1),))

    def never_settles(url: str) -> str:
        html = directory.fetch(url)
        order = directory._order["region_id_1"]
        directory.roll("region_id_1", order[3:] + order[:3])
        return html

    outcome = crawl_partition(conn, partition, BASE, fetch=never_settles,
                              run_ref="run-1", dataset_key="rows",
                              retry_page_ceiling=2, heavy_attempts=3,
                              resize_at_end=False)
    only = outcome.cells[0]
    assert len(only.attempts) == 3, "a heavy cell must get its retries"
    assert "closed by COUNTING" in str(outcome)
    assert f"{2}-page witness ceiling" in str(outcome)


# ---- a deficit that is churn, not a gap -------------------------------------

def test_a_cell_that_lost_a_row_says_so_instead_of_reporting_a_gap(conn):
    """THREE CELLS FINISHED ONE OR TWO SHORT on the first real run — `235 of 236`,
    `148 of 149`, `405 of 413` — and nothing could say whether a contractor had been
    missed or had LEFT. The listing shrank by 25 rows that same night, so departure
    was the likelier reading and there was no way to prefer it. One request per short
    cell settles it."""
    register(conn)
    ids = [str(n) for n in range(1, 10)]
    directory = Directory({"whole": list(ids), "region_id_1": list(ids)})
    partition = Partition(directory, cells=(cell(region_id=1),))
    reads: list[str] = []

    def losing_one(url: str) -> str:
        html = directory.fetch(url)
        reads.append(url)
        # One contractor leaves the cell after it has been sized and read once, so
        # the re-size finds 8 where the read was counted against 9.
        if len(reads) == 4:
            directory.roll("region_id_1", ids[:-1])
        return html

    outcome = crawl_partition(conn, partition, BASE, fetch=losing_one,
                              run_ref="run-1", dataset_key="rows",
                              max_attempts=1, resize_at_end=False)
    only = outcome.cells[0]
    assert only.size_at_end is not None, "a short cell must be re-sized"
    assert only.departures >= 1
    assert only.deficit_is_churn, (
        f"D={only.observed_deficit} against {only.departures} departure(s) is churn")
    assert "which accounts for it: nothing was missed" in str(only)


def test_a_cell_that_closed_is_not_re_sized_at_all(conn):
    """One request a cell over 56 cells is 56 requests spent explaining a deficit
    that most cells do not have. It is asked for exactly the cells that fell short."""
    register(conn)
    ids = [str(n) for n in range(1, 10)]
    directory = Directory({"whole": list(ids), "region_id_1": list(ids)})
    partition = Partition(directory, cells=(cell(region_id=1),))

    outcome = run(conn, partition, directory, resize_at_end=False)
    only = outcome.cells[0]
    assert only.provably_complete
    assert only.size_at_end is None, "a complete cell must not cost a re-size"
    assert only.departures == 0
    assert not only.deficit_is_churn


def test_a_listing_that_shrank_says_shrank_and_not_grew_by_minus(conn):
    """THE REPORT SAID "the listing grew by -25 rows" ON THE FIRST REAL RUN, because
    `arrivals` was named for one direction. A directory can shrink — that one did,
    17,417 -> 17,392 overnight — and a departure is the more interesting event,
    because it is why a cell can end short without anything being missed."""
    register(conn)
    ids = [str(n) for n in range(1, 9)]
    directory = Directory({"whole": list(ids), "region_id_1": list(ids)})
    partition = Partition(directory, cells=(cell(region_id=1),))

    def leaving(url: str) -> str:
        html = directory.fetch(url)
        if url.endswith("region_id=1&page=1"):
            directory.roll("whole", ids[:-3])
        return html

    outcome = crawl_partition(conn, partition, BASE, fetch=leaving, run_ref="run-1",
                              dataset_key="rows")
    assert outcome.arrivals == -3
    report = str(outcome)
    assert "SHRANK by 3 rows" in report
    assert "grew by -" not in report, "a negative growth is a shrinkage, in words"


# ---- REQ-21 · a subdivision is audited against its parent ---------------------
#
# THE FIFTH WAY IT COULD LIE, and it is the one the owner named. A heavy cell can
# only be subdivided by a value read off evidence we already have — muqawil's
# `city_id`, chosen from the two thirds of contractors seen so far — and the site
# is live, so «ماذا لو تم اضافة مقاول جديد بمدينة جديدة». A new city must cost
# EFFICIENCY AND NEVER COVERAGE, which holds only if the shortfall is measured
# against the PARENT. Audited against the whole listing instead, 151 city cells of
# one region would be compared to 17,414 and report a deficit of thirteen thousand
# rows that were never in scope — a number nobody can act on, which is a check that
# has stopped being one.

PARENT = cell(region_id=1, company_size="verysmall")


def _nested(*, child_rows: dict[int, list[str]], parent_rows: list[str],
            listing_rows: int = 100):
    """A listing far bigger than the parent, so auditing the wrong one shows."""
    cells = {"whole": [str(9000 + n) for n in range(listing_rows)],
             PARENT.label: list(parent_rows)}
    children = []
    for city, rows in child_rows.items():
        child = cell(region_id=1, company_size="verysmall", city_id=city)
        cells[child.label] = list(rows)
        children.append(child)
    directory = Directory(cells)
    return directory, Partition(directory, cells=tuple(children)), tuple(children)


def test_a_subdivision_is_audited_against_its_parent_and_not_the_listing(conn):
    """`Σ N_child == N_parent` is the claim, and the listing is not the yardstick."""
    register(conn)
    rows = [str(100 + n) for n in range(8)]
    directory, partition, children = _nested(
        child_rows={21: rows[:4], 22: rows[4:]}, parent_rows=rows)

    outcome = run(conn, partition, directory, cells=children, parent=PARENT)

    # The parent declares 8 and the children declare 8 between them.
    assert outcome.whole.declared == 8
    assert outcome.declared_sum == 8
    assert outcome.exhaustiveness_deficit == 0
    # Audited against the listing this would have been 100 - 8 = 92.
    assert outcome.nested and outcome.scope == f"cell {PARENT.label}"
    assert outcome.provably_complete


def test_a_subdivision_short_of_its_parent_names_the_deficit_against_the_parent(conn):
    """The 32-of-4,697 shape: a city the evidence never showed, counted."""
    register(conn)
    rows = [str(100 + n) for n in range(8)]
    directory, partition, children = _nested(
        child_rows={21: rows[:4], 22: rows[4:6]}, parent_rows=rows)

    outcome = run(conn, partition, directory, cells=children, parent=PARENT)

    assert outcome.declared_sum == 6
    assert outcome.exhaustiveness_deficit == 2      # and NOT 94
    assert outcome.deficit == 2
    assert not outcome.provably_complete
    assert f"NOT proven complete for cell {PARENT.label}" in str(outcome)


def test_a_child_that_dropped_a_parents_filter_is_refused_before_any_request(conn):
    """Refused on a set comparison, not discovered after hours of fetching."""
    register(conn)
    rows = [str(100 + n) for n in range(8)]
    directory, partition, children = _nested(
        child_rows={21: rows[:4], 22: rows[4:]}, parent_rows=rows)
    # Carries `city_id` but has LOST `company_size`, so it selects more than the
    # parent — and a sum over it could clear the parent's count while covering
    # none of it.
    wider = cell(region_id=1, city_id=21)

    with pytest.raises(NotASubdivision) as raised:
        run(conn, partition, directory, cells=(*children, wider), parent=PARENT)

    assert wider.label in str(raised.value)
    assert directory.fetched == []


def test_a_nested_run_never_claims_the_listing_is_complete(conn):
    """A proof about one cell must not read as a proof about the site."""
    register(conn)
    rows = [str(100 + n) for n in range(8)]
    directory, partition, children = _nested(
        child_rows={21: rows[:4], 22: rows[4:]}, parent_rows=rows)

    said = str(run(conn, partition, directory, cells=children, parent=PARENT))

    assert "AND FOR THAT CELL ONLY" in said
    assert "PROVABLY COMPLETE for the listing as published" not in said


def test_a_nested_run_never_sizes_the_unfiltered_listing(conn):
    """So `arrivals` is the parent's movement and not the site's churn.

    A nested run that re-sized the whole listing would excuse a child ending one
    id short by a departure that happened in another region entirely.
    """
    register(conn)
    rows = [str(100 + n) for n in range(8)]
    directory, partition, children = _nested(
        child_rows={21: rows[:4], 22: rows[4:]}, parent_rows=rows)

    outcome = run(conn, partition, directory, cells=children, parent=PARENT)

    assert all("region_id=1" in url for url in directory.fetched)
    assert outcome.arrivals == 0


def test_the_order_of_a_parents_filters_does_not_decide_what_is_under_it(conn):
    """The params are ordered for the URL's sake; membership is a set question."""
    register(conn)
    rows = [str(100 + n) for n in range(4)]
    child = cell(region_id=1, company_size="verysmall", city_id=21)
    directory = Directory({"whole": [str(9000 + n) for n in range(100)],
                           PARENT.label: list(rows),
                           child.label: list(rows)})
    partition = Partition(directory, cells=(child,))
    reversed_parent = cell(company_size="verysmall", region_id=1)
    assert reversed_parent.label != PARENT.label     # the URL really does differ

    directory.roll(reversed_parent.label, list(rows))
    outcome = run(conn, partition, directory, cells=(child,),
                  parent=reversed_parent)

    assert outcome.exhaustiveness_deficit == 0


def test_a_top_level_run_still_audits_against_the_whole_listing(conn):
    """The default has to be exactly what it was, or #229-#234 are undone."""
    register(conn)
    rows = [str(100 + n) for n in range(8)]
    left, right = cell(region_id=1), cell(region_id=2)
    directory = Directory({"whole": list(rows),
                           left.label: rows[:4], right.label: rows[4:]})
    partition = Partition(directory, cells=(left, right))

    outcome = run(conn, partition, directory)

    assert not outcome.nested and outcome.scope == "listing"
    assert outcome.whole.declared == 8
    assert outcome.exhaustiveness_deficit == 0
    assert "PROVABLY COMPLETE for the listing as published" in str(outcome)


# ---- a cell is left alone when the reads stop returning anything -------------
#
# MEASURED ON THE OWNER'S OWN CRAWL, which is the whole reason this exists. The
# residual run fetched 7,898 pages against the first crawl's 1,982, and its last 43
# minutes of continuous fetching produced ZERO new ids: 1,125 -> 459 -> 50 -> 7 -> 1
# -> 902 -> 87 -> 2 -> nothing. `HEAVY_ATTEMPTS` is an ALLOWANCE, not a stopping rule,
# so a cell that had converged kept being read until the allowance ran out.


def never_converges(directory, label, hidden):
    """A fetch that rolls after every read AND never serves ONE PARTICULAR row.

    Rolling is the existing idiom in this file: no read is internally consistent, so
    the witness can never carry the cell. Withholding a row is what stops the COUNT
    proof too, so the union can only ever reach `declared - 1` — the exact shape a
    fixed allowance burns ten reads on for nothing.

    A FIXED ROW, AND THE FIRST ATTEMPT AT THIS GOT IT WRONG. Dropping "one card from
    page 2" drops a DIFFERENT id each read once the order is rolling, so every id
    appears eventually and the union reaches the declared count after all. It has to
    be the same row every time.

    SIZING IS UNAFFECTED because `hidden` starts on a middle page: `size_cell` reads
    page 1 and the last page before anything has rolled, so the cell still declares
    its true size.
    """
    anchor = f'<a href="/en/row/{hidden}/143">row</a>'

    def fetch(url: str) -> str:
        html = directory.fetch(url)
        order = directory._order[label]
        directory.roll(label, order[1:] + order[:1])
        return html.replace(anchor, "", 1)
    return fetch


def test_a_cell_whose_reads_go_dry_is_not_read_to_its_allowance(conn):
    """Two consecutive reads that add nothing end it, however much allowance is left."""
    register(conn)
    ids = [str(400 + n) for n in range(12)]
    one = cell(region_id=1)
    directory = Directory({"whole": list(ids), one.label: list(ids)})
    partition = Partition(directory, cells=(one,))

    outcome = crawl_partition(
        conn, partition, BASE, fetch=never_converges(directory, one.label, ids[5]),
        run_ref="run-1", dataset_key="rows", retry_page_ceiling=1,
        heavy_attempts=10, resize_at_end=False)

    only = outcome.cells[0]
    assert not only.provably_complete, "the fixture must not let it close"
    assert len(only.attempts) < 10, "it used its whole allowance"
    assert len(only.attempts) >= DRY_ATTEMPTS + 1, "it stopped before it had evidence"
    assert only.went_dry()


def test_a_cell_that_closes_on_a_proof_is_never_reported_as_dry(conn):
    """The proof is why it stopped. Reporting dryness would misstate the reason."""
    register(conn)
    ids = [str(500 + n) for n in range(8)]
    one = cell(region_id=2)
    directory = Directory({"whole": list(ids), one.label: list(ids)})
    partition = Partition(directory, cells=(one,))

    outcome = run(conn, partition, directory, cells=(one,))

    only = outcome.cells[0]
    assert only.provably_complete
    assert not only.went_dry()


def test_dry_attempts_decides_how_long_it_keeps_reading(conn):
    """One dry read is not evidence: a cell is a randomised ordering, so a pass can
    repeat the last one and the next can still surface new ids. The parameter has to
    actually change the behaviour, or it is a comment pretending to be a setting."""
    register(conn)
    lengths = {}
    for wanted in (1, 3):
        ids = [str(600 + n) for n in range(12)]
        one = cell(region_id=3 + wanted)
        directory = Directory({"whole": list(ids), one.label: list(ids)})
        outcome = crawl_partition(
            conn, Partition(directory, cells=(one,)), BASE,
            fetch=never_converges(directory, one.label, ids[5]),
            run_ref=f"run-{wanted}", dataset_key="rows", retry_page_ceiling=1,
            heavy_attempts=10, dry_attempts=wanted, resize_at_end=False)
        lengths[wanted] = len(outcome.cells[0].attempts)

    # NOT AN EXACT COUNT, and the first version of this asserted one and was wrong.
    # The fixture rolls after EVERY fetch, so a single attempt reads its three pages
    # across three different orderings and does not see the whole cell — which is
    # what a rolling cache really does. The number of attempts therefore depends on
    # the fixture's rotation arithmetic, and pinning it would test the fake. What
    # matters is that the parameter DECIDES, and that neither value burns the
    # allowance.
    assert lengths[1] < lengths[3], lengths
    assert max(lengths.values()) < 10, lengths


def test_the_ids_it_did_find_are_still_recorded(conn):
    """Stopping early must not cost coverage of what WAS seen — filling the ledger is
    the thing the whole method exists for."""
    register(conn)
    ids = [str(700 + n) for n in range(12)]
    one = cell(region_id=6)
    directory = Directory({"whole": list(ids), one.label: list(ids)})

    crawl_partition(conn, Partition(directory, cells=(one,)), BASE,
                    fetch=never_converges(directory, one.label, ids[5]), run_ref="run-1",
                    dataset_key="rows", retry_page_ceiling=1, heavy_attempts=10,
                    resize_at_end=False)

    stored = {row[0] for row in conn.execute(
        "SELECT external_id FROM dataset_sighting")}
    assert len(stored) == 11, f"saw {len(stored)} of 12 — one row is never served"
    assert stored < set(ids)


# ---- cells crawled concurrently, and the rate NOT raised --------------------
#
# The wall clock of a real crawl is muqawil's ~6 s latency, not our 1 s pace, and the
# cells are independent — which is the same property that makes each one provable. So
# overlapping them is the whole win. `HttpFetcher._throttle` had to become
# thread-safe first: measured 2026-08-21, four workers made 20 requests in 1.02 s
# where 3.80 s was owed. Concurrency without that would have quadrupled the real
# request rate against a live site and reported itself as a speedup.


def _pool_run(conn, registry, partition, directory, cells, **kwargs):
    return crawl_partition(
        conn, partition, BASE, fetch=directory.fetch, run_ref="run-1",
        dataset_key="rows", cells=cells, connect=registry.engine.connect, **kwargs)


@pytest.fixture()
def registry(tmp_path: Path):
    one = DatabaseRegistry(EngineDatabase(tmp_path / "pool-engine.db"),
                           pointer_file=tmp_path / "pool.json")
    one.initialize()
    return one


def _four_cells(directory_cells):
    return tuple(cell(region_id=n) for n in range(1, 5)), directory_cells


def test_every_cell_is_crawled_when_the_work_is_shared(registry):
    """Four workers, four cells, and nothing may be dropped or done twice."""
    conn = registry.engine.connect()
    try:
        conn.execute(
            "INSERT INTO source_site (source_key, source_name, base_url, crawl_scope) "
            "VALUES ('site_test','A site',?, 'listing_only')", (BASE,))
        conn.commit()
        ids = {n: [str(n * 100 + k) for k in range(8)] for n in range(1, 5)}
        cells = tuple(cell(region_id=n) for n in range(1, 5))
        directory = Directory({"whole": [x for v in ids.values() for x in v],
                               **{c.label: list(ids[n]) for n, c in
                                  zip(range(1, 5), cells, strict=True)}})
        partition = Partition(directory, cells=cells)

        outcome = _pool_run(conn, registry, partition, directory, cells, workers=4)

        assert [one.size.cell.label for one in outcome.cells] == [
            c.label for c in cells], "cells must be reported in the PLAN's order"
        assert all(one.provably_complete for one in outcome.cells)
        assert len(outcome.ids) == 32
    finally:
        conn.close()


def test_the_sightings_of_every_worker_reach_the_ledger(registry):
    """Each worker writes on its own connection; none may be lost to the others."""
    conn = registry.engine.connect()
    try:
        conn.execute(
            "INSERT INTO source_site (source_key, source_name, base_url, crawl_scope) "
            "VALUES ('site_test','A site',?, 'listing_only')", (BASE,))
        conn.commit()
        ids = {n: [str(n * 100 + k) for k in range(8)] for n in range(1, 5)}
        cells = tuple(cell(region_id=n) for n in range(1, 5))
        directory = Directory({"whole": [x for v in ids.values() for x in v],
                               **{c.label: list(ids[n]) for n, c in
                                  zip(range(1, 5), cells, strict=True)}})

        _pool_run(conn, registry, Partition(directory, cells=cells), directory,
                  cells, workers=4)

        stored = {row[0] for row in conn.execute(
            "SELECT external_id FROM dataset_sighting")}
        assert stored == {x for v in ids.values() for x in v}
    finally:
        conn.close()


def test_without_a_connect_factory_it_stays_sequential(conn):
    """`workers` alone must not silently share one connection across threads —
    `sqlite3` refuses that, and refusing to try is better than discovering it."""
    register(conn)
    ids = [str(800 + n) for n in range(8)]
    one = cell(region_id=1)
    directory = Directory({"whole": list(ids), one.label: list(ids)})

    outcome = crawl_partition(conn, Partition(directory, cells=(one,)), BASE,
                              fetch=directory.fetch, run_ref="run-1",
                              dataset_key="rows", cells=(one,), workers=8)

    assert outcome.cells[0].provably_complete


def test_a_replayed_attempt_does_not_count_as_a_dry_read(conn):
    """FOUND BY RUNNING IT ON HIS OWN RESUMED CRAWL, not by reading the code.

    A resumed attempt has its already-stored pages removed by `_Unstored` and its
    ids recovered off disk, so it returns EXACTLY what the previous attempt did. It
    gains zero **by construction**, not because the site has run out — and counting
    that as a dry read made the stop fire on the first two replays and abandon the
    cell:

        region_id_1-company_size_verysmall: 3,125 of 4,699, D=1,574
                                            [3 attempt(s), 5 REQUESTS]

    Five requests for a cell of 1,291 pages. `pages_read` is the FETCHED count, so
    zero means the attempt asked the site nothing and can say nothing about it.
    """
    register(conn)
    ids = [str(900 + n) for n in range(12)]
    one = cell(region_id=9)
    directory = Directory({"whole": list(ids), one.label: list(ids)})

    # A first run stores every page of the cell.
    crawl_partition(conn, Partition(directory, cells=(one,)), BASE,
                    fetch=directory.fetch, run_ref="first", dataset_key="rows",
                    cells=(one,), resize_at_end=False)

    # A SECOND run with the SAME ref: every page is already stored under it, so each
    # attempt is a pure replay — `pages_read` is 0 and no attempt may be called dry.
    outcome = crawl_partition(
        conn, Partition(directory, cells=(one,)), BASE, fetch=directory.fetch,
        run_ref="first", dataset_key="rows", cells=(one,), resize_at_end=False,
        retry_page_ceiling=1, heavy_attempts=4)

    only = outcome.cells[0]
    replays = [a for a in only.attempts if a.pages_read == 0]
    assert replays, "the fixture must actually produce a replayed attempt"
    assert not only.went_dry(), (
        "a replayed attempt fetched nothing and cannot be evidence that the site "
        "has nothing left")
