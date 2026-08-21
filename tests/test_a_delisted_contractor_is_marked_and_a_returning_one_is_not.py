"""`generic_record.status` finally gets written, and taking the mark back is half the feature.

WHY THIS EXISTS. `status` has offered `'unavailable'` and `'retired'` since the table
was created and **nothing ever set either**. So a contractor the directory delisted kept
`status='active'` with a frozen `last_seen_at`, indistinguishable from one the last
crawl had simply not reached. He ruled it on 2026-08-21 (`OP-26`): a delisted contractor
becomes **`unavailable`**.

THE HALF THAT IS EASY TO SHIP BROKEN. `row_state` puts a marked row **first** in its
precedence — a decision outranks an observation — so marking without ever unmarking
would make `returned` unreachable for every row it touched. Migration 0006 exists purely
to make `returned` computable; marking without restoring would quietly switch it off
again. That is why `test_the_mark_is_taken_back_or_returned_is_unreachable` is here and
why it asserts on `row_state`'s answer rather than on the column.

AND THE BOUNDARY IS THE INTERESTING PART. `row_state` reads `last_seen_at >=
last_absent_at` as `returned`, with `>=` for a written reason: both timestamps come from
`strftime(...,'now')` at SECOND resolution, so a crawl finishing in the same second as
the absence it answers produces two equal strings. `mark_unavailable` must use the exact
complement — `<` — or a row is marked unavailable while the screen says `returned`.
`test_the_boundary_is_the_one_row_state_uses` is the test that pins the two together.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.sightings import (
    STATE_RETURNED,
    STATE_UNAVAILABLE,
    Marking,
    mark_unavailable,
    record_absences,
    record_sightings,
    row_state,
)

ABSENT_AT = "2026-08-21T12:00:00Z"


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


def _record_key(contractor_id: str) -> str:
    """`record_key` AS PRODUCTION BUILDS IT — a hash of the identity, not the id.

    Copied deliberately from `test_a_crawl_says_what_it_saw.py`, which records why: on
    the live warehouse `record_key` and `contractor_id` match on **0 of 1,172 rows**, so
    a fixture that writes the id into the key hides every join defect it has.
    """
    from scrapex.extract.service import _canonical, _digest

    return _digest(_canonical([contractor_id]))


def _stored(conn, *contractors: tuple[str, str], dataset: str = "contractors") -> None:
    """Records for contractors we hold. Each is `(contractor_id, status)`."""
    if not conn.execute("SELECT COUNT(*) FROM site_profile").fetchone()[0]:
        conn.execute(
            "INSERT INTO site_profile (site_key, display_name, base_url) "
            "VALUES ('s','S','https://example.test')")
        conn.execute(
            "INSERT INTO generic_page_snapshot "
            "(source_url, html_content, content_hash) "
            "VALUES ('https://example.test/1','<html></html>','h')")
    row = conn.execute(
        "INSERT INTO dataset_definition "
        "(site_profile_id, dataset_key, original_name, dataset_kind, "
        " discovery_method, locator_json) "
        "VALUES (1,?,?, 'table','html_table','{}') RETURNING dataset_definition_id",
        (dataset, dataset)).fetchone()
    definition = row[0]
    version = conn.execute(
        "INSERT INTO dataset_schema_version "
        "(dataset_definition_id, version_number, schema_hash) "
        "VALUES (?,1,?) RETURNING schema_version_id",
        (definition, f"h{definition}")).fetchone()[0]
    for contractor_id, status in contractors:
        conn.execute(
            "INSERT INTO generic_record "
            "(dataset_definition_id, record_key, schema_version_id, data_json, "
            " source_snapshot_id, source_locator, content_hash, "
            " first_seen_at, last_seen_at, status) "
            "VALUES (?, ?, ?, ?, 1, 'x', ?, "
            "        '2026-08-20T00:00:00Z','2026-08-20T00:00:00Z', ?)",
            (definition, _record_key(contractor_id), version,
             json.dumps({"contractor_id": contractor_id}),
             f"h{contractor_id}", status))
    conn.commit()


def _absence(conn, contractor_id: str, *, at: str = ABSENT_AT,
             dataset: str = "contractors") -> None:
    """Stamp a proven absence at an EXACT time.

    `record_absences` writes `strftime(...,'now')`, which is the right thing in
    production and useless for testing a boundary: the second it lands in is whatever
    second the test ran in. The realistic path is exercised in
    `test_the_ruled_status_is_written_through_the_real_absence_path`; every other test
    needs the two timestamps placed by hand, one second apart or exactly equal.
    """
    conn.execute(
        "UPDATE dataset_sighting SET last_absent_at = ?, last_absent_run_ref = 'r' "
        " WHERE dataset_key = ? AND external_id = ?", (at, dataset, contractor_id))
    conn.commit()


def _status(conn, contractor_id: str, *, dataset: str = "contractors") -> str:
    return conn.execute(
        "SELECT r.status FROM generic_record AS r "
        "  JOIN dataset_definition AS d "
        "    ON d.dataset_definition_id = r.dataset_definition_id "
        " WHERE d.dataset_key = ? AND r.record_key = ?",
        (dataset, _record_key(contractor_id))).fetchone()[0]


# ---- the ruled behaviour ------------------------------------------------------

def test_the_ruled_status_is_written_through_the_real_absence_path(conn):
    """END TO END, through `record_absences` rather than a hand-written timestamp.

    His ruling was `unavailable` over `retired`, and this is the whole chain that
    delivers it: a crawl sees 1298 and not 1301, `record_absences` writes the proof,
    `mark_unavailable` reads the proof and writes the status.
    """
    _stored(conn, ("1298", "active"), ("1301", "active"))
    record_sightings(conn, "contractors", ["1298", "1301"])
    # AN EARLIER CRAWL, AND IT HAS TO BE EARLIER BY MORE THAN NOTHING. Both
    # `record_sightings` and `record_absences` stamp `strftime(...,'now')` at SECOND
    # resolution, so a test doing both in one tick produces `last_seen_at ==
    # last_absent_at` — and the tie is deliberately resolved toward `returned`, so the
    # row would correctly NOT be marked and the test would look like a bug in the code.
    #
    # Production cannot hit that: a departed row's `last_seen_at` comes from a crawl
    # that ran hours ago, because this crawl by definition did not touch it. Backdating
    # is what makes the fixture resemble production rather than the test runner.
    conn.execute("UPDATE dataset_sighting SET last_seen_at = '2026-08-20T09:00:00Z'")
    conn.commit()
    # A later crawl, provably complete, shows only 1298.
    record_sightings(conn, "contractors", ["1298"])
    assert record_absences(conn, "contractors", seen=["1298"], run_ref="r2") == 1

    marking = mark_unavailable(conn, "contractors")

    assert marking.marked == (_record_key("1301"),)
    assert marking.restored == ()
    assert _status(conn, "1301") == STATE_UNAVAILABLE
    assert _status(conn, "1298") == "active"


def test_a_row_nobody_proved_absent_is_never_marked(conn):
    """THE GUARD THAT MATTERS MOST. A stale `last_seen_at` is not evidence of anything
    — the last crawl may simply not have reached this cell. Only `last_absent_at`, which
    is written from a crawl that closed with `D = 0`, is a proof.

    Without this, a crawler having a bad afternoon delists contractors — `R-27`'s
    failure arriving from the other side.
    """
    _stored(conn, ("1301", "active"))
    record_sightings(conn, "contractors", ["1301"])
    # No `record_absences` call: nothing ever proved 1301 gone.

    assert mark_unavailable(conn, "contractors") == Marking("contractors")
    assert _status(conn, "1301") == "active"


def test_a_row_that_is_not_in_the_ledger_at_all_is_never_marked(conn):
    """`unsighted` is a gap in OUR history — these rows predate `dataset_sighting` —
    and reading it as a departure would invent one out of our own bookkeeping."""
    _stored(conn, ("1301", "active"))
    # Deliberately no sighting row at all.

    assert mark_unavailable(conn, "contractors").marked == ()
    assert _status(conn, "1301") == "active"


def test_a_retired_row_is_a_persons_decision_and_a_crawl_does_not_touch_it(conn):
    """ONE VOCABULARY, TWO AUTHORS. `unavailable` is what the SITE did, so a crawl may
    write it. `retired` is what a PERSON decided, so no crawl may reach it — in either
    direction, which is why this asserts the row is not restored either.

    THE ABSENCE IS RECORDED ON PURPOSE, and the first version of this test omitted it.
    Without a proven absence the row is untouched for a reason that has nothing to do
    with being retired — so the test passed while a mutation deleting the protection
    also passed. A retired row that a complete crawl proved absent is the only setup
    under which "we did not touch it" means anything.
    """
    _stored(conn, ("1301", "retired"))
    record_sightings(conn, "contractors", ["1301"])
    conn.execute("UPDATE dataset_sighting "
                 "   SET last_seen_at = '2026-08-20T00:00:00Z' WHERE external_id='1301'")
    conn.commit()
    _absence(conn, "1301")

    marking = mark_unavailable(conn, "contractors")

    assert (marking.marked, marking.restored) == ((), ())
    assert _status(conn, "1301") == "retired"


# ---- and taking the mark back -------------------------------------------------

def test_a_contractor_the_site_publishes_again_is_restored(conn):
    _stored(conn, ("1301", STATE_UNAVAILABLE))
    record_sightings(conn, "contractors", ["1301"])
    _absence(conn, "1301", at="2026-08-21T11:00:00Z")
    conn.execute("UPDATE dataset_sighting SET last_seen_at = '2026-08-21T13:00:00Z' "
                 " WHERE external_id = '1301'")
    conn.commit()

    marking = mark_unavailable(conn, "contractors")

    assert marking.restored == (_record_key("1301"),)
    assert marking.marked == ()
    assert _status(conn, "1301") == "active"


def test_the_mark_is_taken_back_or_returned_is_unreachable(conn):
    """THE REGRESSION THIS PREVENTS, asserted on `row_state` and not on the column.

    `row_state`'s precedence puts a marked row FIRST, above every observation. So a
    contractor marked `unavailable` who reappears keeps displaying `unavailable` for as
    long as the row exists, and `returned` — the state migration 0006 was written to
    make computable — is never seen by anybody.

    The assertion is deliberately made twice: what the state WOULD be with the mark
    still on, and what it is once `mark_unavailable` has taken it off.
    """
    marked_and_back = {
        "first_seen_at": "2026-08-01T00:00:00Z",
        "last_seen_at": "2026-08-21T13:00:00Z",
        "newest": "2026-08-21T13:00:00Z",
        "sighted_at": "2026-08-01T00:00:00Z",
        "last_absent_at": "2026-08-21T11:00:00Z",
    }

    assert row_state(status=STATE_UNAVAILABLE, **marked_and_back) == STATE_UNAVAILABLE
    assert row_state(status="active", **marked_and_back) == STATE_RETURNED


def test_the_boundary_is_the_one_row_state_uses(conn):
    """THE TWO COMPARISONS ARE ONE COMPARISON, and this is what pins them together.

    `row_state` uses `last_seen_at >= last_absent_at` for `returned`, because both
    timestamps are second-resolution and a crawl finishing in the same second as the
    absence it answers produces two EQUAL strings. So equality means returned — and
    `mark_unavailable` must not mark it. If it used `<=` instead of `<`, this row would
    carry `unavailable` while the screen showed `returned`.
    """
    same = "2026-08-21T12:00:00Z"
    _stored(conn, ("1301", "active"))
    record_sightings(conn, "contractors", ["1301"])
    conn.execute("UPDATE dataset_sighting SET last_seen_at = ? WHERE external_id='1301'",
                 (same,))
    conn.commit()
    _absence(conn, "1301", at=same)

    assert mark_unavailable(conn, "contractors").marked == ()

    assert row_state(status="active", first_seen_at="2026-08-01T00:00:00Z",
                     last_seen_at=same, newest=same, sighted_at="2026-08-01T00:00:00Z",
                     last_absent_at=same) == STATE_RETURNED


def test_one_second_earlier_and_it_is_still_absent(conn):
    """The other side of the same boundary, so `<` is pinned from both directions and
    not merely satisfied by a function that never marks anything."""
    _stored(conn, ("1301", "active"))
    record_sightings(conn, "contractors", ["1301"])
    conn.execute("UPDATE dataset_sighting "
                 "   SET last_seen_at = '2026-08-21T11:59:59Z' WHERE external_id='1301'")
    conn.commit()
    _absence(conn, "1301", at="2026-08-21T12:00:00Z")

    assert mark_unavailable(conn, "contractors").marked == (_record_key("1301"),)


# ---- the properties a caller relies on ---------------------------------------

def test_a_second_pass_over_an_unchanged_warehouse_changes_nothing(conn):
    """Idempotent, because the crawl will call this every run and a caller that has to
    remember whether it already ran is a caller that will get it wrong."""
    _stored(conn, ("1301", "active"))
    record_sightings(conn, "contractors", ["1301"])
    _absence(conn, "1301")
    conn.execute("UPDATE dataset_sighting "
                 "   SET last_seen_at = '2026-08-20T00:00:00Z' WHERE external_id='1301'")
    conn.commit()

    first = mark_unavailable(conn, "contractors")
    second = mark_unavailable(conn, "contractors")

    assert first.marked == (_record_key("1301"),)
    assert second == Marking("contractors")


def test_the_two_directions_are_reported_separately(conn):
    """TWO NUMBERS AND NOT A TOTAL. Seven contractors leaving and seven coming back are
    the same total and completely different news."""
    _stored(conn, ("1301", "active"), ("1302", STATE_UNAVAILABLE))
    record_sightings(conn, "contractors", ["1301", "1302"])
    _absence(conn, "1301")
    _absence(conn, "1302", at="2026-08-21T11:00:00Z")
    conn.execute("UPDATE dataset_sighting SET last_seen_at = "
                 " CASE external_id WHEN '1301' THEN '2026-08-20T00:00:00Z' "
                 "                  ELSE '2026-08-21T13:00:00Z' END")
    conn.commit()

    marking = mark_unavailable(conn, "contractors")

    assert marking.marked == (_record_key("1301"),)
    assert marking.restored == (_record_key("1302"),)
    said = str(marking)
    assert "1 marked unavailable" in said and "1 restored to active" in said


def test_nothing_at_all_says_so_rather_than_printing_two_zeros(conn):
    _stored(conn, ("1301", "active"))
    record_sightings(conn, "contractors", ["1301"])

    assert "no status change" in str(mark_unavailable(conn, "contractors"))


def test_another_dataset_is_not_touched(conn):
    """The `UPDATE` is keyed on `record_key`, which is a hash of the identity values and
    NOT unique across datasets — two sources listing the same contractor id produce the
    same key. So the statement carries its dataset, and this is the test that says so.
    """
    _stored(conn, ("1301", "active"))
    _stored(conn, ("1301", "active"), dataset="engineers")
    record_sightings(conn, "contractors", ["1301"])
    record_sightings(conn, "engineers", ["1301"])
    _absence(conn, "1301")
    conn.execute("UPDATE dataset_sighting "
                 "   SET last_seen_at = '2026-08-20T00:00:00Z' WHERE external_id='1301'")
    conn.commit()

    mark_unavailable(conn, "contractors")

    assert _status(conn, "1301") == STATE_UNAVAILABLE
    assert _status(conn, "1301", dataset="engineers") == "active"


# ---- the gate: the crawl may only write this off the back of a proof ----------
#
# `mark_departures` IS THE CALLER `record_absences` ASKS FOR. That function's docstring
# says its caller must guarantee the crawl was complete, because it cannot see that from
# inside — and until this work, IT HAD NO CALLER AT ALL. Neither did the status write
# that depends on it. So the whole chain existed and none of it ran.
#
# THE OUTCOMES BELOW ARE REAL `PartitionOutcome` OBJECTS, not stubs. The gate turns on
# `provably_complete` and `nested`, and both are computed properties with real
# arithmetic behind them — a stub would let this file agree with its own idea of what
# they return, which is the failure mode `_record_key` above exists to avoid.

def _outcome(*, declared_whole: int, declared_cell: int, ids: tuple[str, ...],
             nested: bool = False):
    """A `PartitionOutcome` whose proof state is decided by arithmetic, as production's is."""
    from scrapex.pagesource import Cell
    from scrapex.partitioncrawl import (
        WHOLE,
        Attempt,
        CellOutcome,
        CellSize,
        PartitionOutcome,
    )

    cell = Cell(params=(("region_id", "1"),))
    return PartitionOutcome(
        whole=CellSize(cell=WHOLE, last_page=1, cards_per_page=declared_whole,
                       tail_cards=declared_whole, requests=1),
        cells=(CellOutcome(
            size=CellSize(cell=cell, last_page=1, cards_per_page=declared_cell,
                          tail_cards=declared_cell, requests=1),
            attempts=(Attempt(ids=ids, pages_read=1, witnessed=False,
                              note="", run_ref="r"),)),),
        whole_at_end=None, parent=cell if nested else WHOLE)


def _directory():
    from scrapex.directories import get as get_directory

    return get_directory(None)


def test_a_proven_crawl_writes_both_the_absence_and_the_status(conn, capsys):
    from scrapex.contractors import mark_departures

    _stored(conn, ("1", "active"), ("2", "active"), ("9", "active"))
    record_sightings(conn, "contractors", ["1", "2", "9"])
    conn.execute("UPDATE dataset_sighting SET last_seen_at = '2026-08-20T09:00:00Z'")
    conn.commit()

    # The crawl saw 1 and 2. It declared 2 rows and found 2 distinct ids, so it closed
    # by counting — and 9 is therefore proved gone rather than merely unseen.
    mark_departures(conn, _directory(),
                    _outcome(declared_whole=2, declared_cell=2, ids=("1", "2")), "r9")

    assert _status(conn, "9") == STATE_UNAVAILABLE
    assert _status(conn, "1") == "active"
    said = capsys.readouterr().out
    assert "provably complete, so absence is evidence" in said
    assert "1 marked unavailable" in said


def test_a_nested_proof_must_not_delist_the_rest_of_the_listing(conn, capsys):
    """THE DANGEROUS CASE, and it is dangerous precisely because it looks proven.

    A nested outcome reports `provably_complete = True` — measured, not assumed — and
    its own docstring says why that is correct: *"IT IS A CLAIM ABOUT `scope` AND NEVER
    MORE."* True on a nested run means the PARENT CELL is accounted for. Marking
    absences from it would delist every contractor the cell does not contain, which on
    muqawil is most of the country.
    """
    from scrapex.contractors import mark_departures

    _stored(conn, ("1", "active"), ("9", "active"))
    record_sightings(conn, "contractors", ["1", "9"])
    conn.execute("UPDATE dataset_sighting SET last_seen_at = '2026-08-20T09:00:00Z'")
    conn.commit()
    nested = _outcome(declared_whole=2, declared_cell=2, ids=("1", "2"), nested=True)
    assert nested.provably_complete, "the premise: it really does look proven"

    mark_departures(conn, _directory(), nested, "r9")

    assert _status(conn, "9") == "active"
    assert "says nothing about the rest of the listing" in capsys.readouterr().out


def test_an_only_run_is_refused_and_the_arithmetic_is_what_refuses_it(conn, capsys):
    """`--only` NEEDS NO SEPARATE CHECK, AND THIS IS THE TEST THAT SAYS SO.

    A subset run sizes the WHOLE listing and sums only the cells it was handed, so its
    `exhaustiveness_deficit` is the thousands of rows in the cells it skipped and
    `provably_complete` is already False. That is the right answer reached indirectly,
    which is exactly the kind of safety property that disappears in a refactor with
    nobody noticing — so it is asserted here rather than trusted.
    """
    from scrapex.contractors import mark_departures

    _stored(conn, ("1", "active"), ("9", "active"))
    record_sightings(conn, "contractors", ["1", "9"])
    conn.execute("UPDATE dataset_sighting SET last_seen_at = '2026-08-20T09:00:00Z'")
    conn.commit()
    subset = _outcome(declared_whole=100, declared_cell=2, ids=("1", "2"))
    assert subset.exhaustiveness_deficit == 98
    assert not subset.provably_complete

    mark_departures(conn, _directory(), subset, "r9")

    assert _status(conn, "9") == "active"
    assert "not provably complete" in capsys.readouterr().out


def test_declining_says_why_rather_than_saying_nothing(conn, capsys):
    """A crawl that silently marked nothing is indistinguishable from one that found no
    departures, and those are opposite facts about the directory."""
    from scrapex.contractors import mark_departures

    _stored(conn, ("1", "active"))
    record_sightings(conn, "contractors", ["1"])

    mark_departures(conn, _directory(),
                    _outcome(declared_whole=100, declared_cell=2, ids=("1",)), "r9")

    said = capsys.readouterr().out
    assert "departures not marked" in said
    assert "bad afternoon" in said       # the reason, not just the refusal
