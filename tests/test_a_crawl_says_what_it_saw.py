"""A crawl can say what it covered, so nobody is told "does not exist" again.

THE INCIDENT. The owner asked whether membership 10001274 was in the warehouse.
It was not. The site answers 200 for it — شركة عبر المملكة سبك, active, member
since 2018/08/25 — and its neighbours bracket it exactly: membership 10001271 is
contractor 1298, 10001276 is 1303, and the id in his URL is 1301. The warehouse
answered "does not exist" about a real company and could not say it was guessing.
«لا اريد تكرار هذا الامر».

Two gaps produced that, and they are the same gap: a crawl could not say what it
covered. `scrapex/sweep.py` held every id it saw and `tools/sweep_muqawil.py`
never read them; `snapshotcrawl.py` committed every page and no column recorded
which run they belonged to.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.sightings import (
    Coverage,
    coverage,
    departures,
    missing_ids,
    record_sightings,
    sighting_frequencies,
)


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
    """`record_key` AS PRODUCTION BUILDS IT — a hash, not the id.

    THIS HELPER USED TO WRITE THE CONTRACTOR ID STRAIGHT INTO `record_key`, and that
    single shortcut hid a real defect for as long as it existed. `approve_candidate`
    builds the key as `_digest(_canonical(identity))`, so on the live warehouse
    `record_key` is `'ff88670d…'` where the contractor id is `'20044482'` — measured,
    they match on **0 of 1,172 rows**. A function joining sightings to records on
    `record_key` therefore reports every row as unsighted in production and passes
    every test here.

    So the fixture now hashes it exactly as the write path does. It is one line, and
    it is the difference between a test that proves something and a test that agrees
    with itself. `LESSONS.md`: build the fixture from the shipped behaviour, never
    from memory.
    """
    from scrapex.extract.service import _canonical, _digest

    return _digest(_canonical([contractor_id]))


def _stored(conn, *contractor_ids: str) -> None:
    """Records for contractors we actually ingested, minimally shaped.

    Written against the REAL column list rather than a remembered one — the
    first draft of this helper invented `identity_key`, and the column is
    `record_key`. Every NOT NULL column is supplied; none is guessed.
    """
    conn.execute(
        "INSERT INTO source_site (source_key, source_name, base_url) "
        "VALUES ('s','S','https://example.test')")
    conn.execute(
        "INSERT INTO dataset_definition "
        "(source_id, dataset_key, original_name, dataset_kind, "
        " discovery_method, locator_json) "
        "VALUES (1,'contractors','contractors','table','html_table','{}')")
    conn.execute(
        "INSERT INTO dataset_schema_version "
        "(dataset_definition_id, version_number, schema_hash) VALUES (1,1,'h')")
    conn.execute(
        "INSERT INTO generic_page_snapshot (source_url, html_content, content_hash) "
        "VALUES ('https://example.test/1','<html></html>','h')")
    for one in contractor_ids:
        conn.execute(
            "INSERT INTO generic_record "
            "(dataset_definition_id, record_key, schema_version_id, data_json, "
            " source_snapshot_id, source_locator, content_hash, "
            " first_seen_at, last_seen_at, status) "
            "VALUES (1, ?, 1, ?, 1, 'x', ?, "
            "        '2026-08-20T00:00:00Z','2026-08-20T00:00:00Z','active')",
            (_record_key(one), json.dumps({"contractor_id": one}), f"h{one}"))
    conn.commit()


# ---- what the site showed us -------------------------------------------------

def test_a_sighting_survives_the_process_that_saw_it(conn):
    """The whole defect in one sentence: 17,283 ids were in memory and are gone.

    `Sweep` accumulates them in a set and offers `found`; the driver printed a
    summary and exited. The count reached a log file. The list did not.
    """
    assert record_sightings(conn, "contractors", ["1298", "1301", "1303"]) == 3

    assert coverage(conn, "contractors").seen == 3


def test_the_missing_list_is_the_answer_he_could_not_be_given(conn):
    """Sighted minus stored. 1301 is the one he asked about."""
    _stored(conn, "1298", "1303")
    record_sightings(conn, "contractors", ["1298", "1301", "1303"])

    assert missing_ids(conn, "contractors") == ("1301",)

    got = coverage(conn, "contractors")
    assert (got.seen, got.stored, got.missing) == (3, 2, 1)


def test_sighted_is_a_floor_and_the_report_says_so(conn):
    """A contractor no pass has shown us is in NEITHER number.

    The sweep that produced 17,283 stopped at its pass ceiling, not at
    convergence — its sixth pass still brought 62 unseen names. So a coverage
    figure that presented itself as complete would be the same false confidence
    the warehouse showed about 10001274, one level up.
    """
    _stored(conn, "1298")
    record_sightings(conn, "contractors", ["1298", "1301"])

    assert "FLOOR, not the population" in str(coverage(conn, "contractors"))


def test_nothing_sighted_is_not_the_same_as_complete(conn):
    """Zero seen must not read as 100% covered, which is what stored/seen would
    give with an empty denominator guarded the lazy way."""
    assert coverage(conn, "contractors").seen == 0
    assert "cannot be stated" in str(coverage(conn, "contractors"))


# ---- the frequency distribution is a sample, not bookkeeping ------------------

def test_seeing_one_twice_is_counted_rather_than_ignored(conn):
    """The 2026-08-17 pass showed 6,503 contractors once, 3,249 twice, 1,021
    three times, 232 four, 41 five and 13 six. That distribution estimates the
    POPULATION and its confidence interval from data already on disk — an
    insert-or-ignore would have thrown the sample away and kept only the set."""
    assert record_sightings(conn, "contractors", ["1301"]) == 1
    assert record_sightings(conn, "contractors", ["1301", "1303"]) == 1

    assert sighting_frequencies(conn, "contractors") == {1: 1, 2: 1}


def test_a_parser_that_failed_does_not_invent_a_contractor_called_none(conn):
    """`str(None)` is the perfectly non-empty string "None". `Sweep.record`
    learned this the hard way: a failing parser would contribute the same
    phantom to every pass, so a sweep would go dry looking convergent."""
    assert record_sightings(conn, "contractors", [None, "", "   ", "1301"]) == 1

    assert coverage(conn, "contractors").seen == 1


def test_two_datasets_do_not_share_a_sighting(conn):
    """The uniqueness is per dataset, because two sites may publish the same id."""
    record_sightings(conn, "contractors", ["1301"])
    record_sightings(conn, "suppliers", ["1301"])

    assert coverage(conn, "contractors").seen == 1
    assert coverage(conn, "suppliers").seen == 1


def test_the_most_repeatedly_seen_missing_contractor_comes_first(conn):
    """A contractor seen six times and still unstored is a stronger signal than
    one glimpsed once — the second may simply have arrived on the pass that
    ended."""
    record_sightings(conn, "contractors", ["1301", "1400"])
    record_sightings(conn, "contractors", ["1400"])
    record_sightings(conn, "contractors", ["1400"])

    assert missing_ids(conn, "contractors") == ("1400", "1301")


def test_a_sighting_is_not_a_record_with_holes(conn):
    """Nothing here carries a name, a city or a rating — and `generic_record`
    gains no empty rows. A reader of that table must never have to filter out
    contractors that were only ever glimpsed."""
    record_sightings(conn, "contractors", ["1301"])

    assert conn.execute(
        "SELECT COUNT(*) FROM generic_record").fetchone()[0] == 0
    columns = {row[1] for row in conn.execute(
        "PRAGMA table_info(dataset_sighting)")}
    assert "company_name" not in columns and "data_json" not in columns


def test_coverage_of_nothing_is_not_a_division_by_zero(conn):
    assert Coverage("contractors", seen=0, stored=0).fraction == 1.0
    assert Coverage("contractors", seen=4, stored=1).fraction == 0.25


# ---- the other half of coverage: what we hold and the site stopped showing ----

def test_a_stored_contractor_the_site_stopped_showing_is_named(conn):
    """THE QUESTION NOTHING ASKED. `missing_ids` answers "what did the site show us
    that we never stored". This is the reverse — "what did we store that the site has
    stopped showing" — and no code set `generic_record.status='superseded'`, so a
    delisted contractor kept `status='active'` with a frozen `last_seen_at` and was
    indistinguishable from one this run did not crawl."""
    _stored(conn, "1301", "1302", "1303")
    # All three sighted long ago; only two sighted again since.
    record_sightings(conn, "contractors", ["1301", "1302", "1303"])
    conn.execute("UPDATE dataset_sighting SET last_seen_at = '2026-01-01T00:00:00Z'")
    conn.execute("UPDATE dataset_sighting SET last_seen_at = '2026-08-21T10:00:00Z' "
                 " WHERE external_id IN ('1301','1302')")
    conn.commit()

    gap = departures(conn, "contractors", not_seen_since="2026-08-21T00:00:00Z")

    assert gap.gone == ("1303",)
    assert gap.unsighted == ()
    assert "1 stored contractor(s) were not sighted" in str(gap)
    assert "ONLY IF THE CRAWL COVERED THEM" in str(gap)


def test_a_row_that_predates_the_ledger_is_not_called_a_departure(conn):
    """TWO DIFFERENT FACTS, and merging them gives a number nobody can act on. A
    stored row with NO sighting at all is a gap in the LEDGER — those rows predate
    `dataset_sighting`, which arrived with #227 — not a contractor leaving."""
    _stored(conn, "1301", "1302")
    record_sightings(conn, "contractors", ["1301"])
    conn.commit()

    gap = departures(conn, "contractors", not_seen_since="2000-01-01T00:00:00Z")

    assert gap.gone == (), "1301 was sighted after the window and has not left"
    assert gap.unsighted == ("1302",), "and 1302 was never in the ledger at all"
    assert "are not in the sighting ledger at all" in str(gap)
    assert "NOT departures" in str(gap)


def test_a_contractor_never_seen_at_all_is_in_NEITHER_list(conn):
    """HIS CORRECTION, 2026-08-21: «لم يُرَ قطّ» is not «اختفى».

    Membership 10001274 was never shown to us — so it is not stored, not sighted, and
    reachable by neither of these lists. Only the crawl's own deficit `D` counts
    those, and he found that one because he happened to know the company, which does
    not scale. A function that appeared to answer it would be worse than one that
    does not.
    """
    _stored(conn, "1301")
    record_sightings(conn, "contractors", ["1301"])
    conn.commit()

    gap = departures(conn, "contractors", not_seen_since="2026-08-21T00:00:00Z")

    assert "10001274" not in gap.gone
    assert "10001274" not in gap.unsighted
    assert gap.gone == () and gap.unsighted == ()


def test_departures_never_writes(conn):
    """Marking a row superseded is a change to his data and a decision he has not
    been asked. Detection first; the write is OP-26."""
    _stored(conn, "1301")
    record_sightings(conn, "contractors", ["1301"])
    conn.execute("UPDATE dataset_sighting SET last_seen_at = '2026-01-01T00:00:00Z'")
    conn.commit()
    before = conn.execute(
        "SELECT status, last_seen_at FROM generic_record").fetchall()

    departures(conn, "contractors", not_seen_since="2026-08-21T00:00:00Z")

    after = conn.execute("SELECT status, last_seen_at FROM generic_record").fetchall()
    assert [tuple(r) for r in after] == [tuple(r) for r in before]
    assert all(row["status"] == "active" for row in after)


def test_a_retired_record_is_not_reported_as_a_departure(conn):
    """A row already marked `retired` has been dealt with. Reporting it again
    every run would make the list grow for ever and stop being actionable."""
    _stored(conn, "1301", "1302")
    record_sightings(conn, "contractors", ["1301", "1302"])
    conn.execute("UPDATE dataset_sighting SET last_seen_at = '2026-01-01T00:00:00Z'")
    conn.execute("UPDATE generic_record SET status = 'retired' "
                 " WHERE record_key = ?", (_record_key("1302"),))
    conn.commit()

    gap = departures(conn, "contractors", not_seen_since="2026-08-21T00:00:00Z")

    assert gap.gone == ("1301",)


# ---- the eight states, and the one that needed a migration --------------------

def test_every_state_is_named_and_explained():
    """A CLOSED VOCABULARY IS WHAT MAKES `R-27` SAFE. The rule is that a row never
    leaves the screen and its state becomes a column — so a state nobody enumerated is
    a row showing something its reader cannot interpret, which is worse than a hidden
    row because it looks like information."""
    from scrapex.sightings import STATE_MEANING

    assert len(STATE_MEANING) == 8
    for state, meaning in STATE_MEANING.items():
        assert state.islower() and " " not in state, state
        assert meaning and meaning[0].isupper(), f"{state} has no sentence"


def test_a_row_absent_then_seen_again_reads_returned(conn):
    """THE STATE THAT COULD NOT BE DERIVED, and the reason migration 0006 exists.

    Absence leaves NO trace in `dataset_sighting`: a row simply stops being touched,
    and a `last_seen_at` two crawls old is identical whether the id was missed once
    and seen again or has been gone throughout. "Was this absent at some point" is a
    question about a moment that has passed, so it must have been WRITTEN when a crawl
    proved it — which is what `last_absent_at` is.
    """
    from scrapex.sightings import STATE_RETURNED, record_absences, row_state

    _stored(conn, "1301", "1302")
    record_sightings(conn, "contractors", ["1301", "1302"])
    conn.commit()

    # A crawl that PROVED it saw only 1301. 1302's absence is written down.
    assert record_absences(conn, "contractors", seen=["1301"],
                           run_ref="proved-run-1") == 1

    # The next crawl shows 1302 again.
    record_sightings(conn, "contractors", ["1301", "1302"])
    conn.commit()
    row = conn.execute(
        "SELECT last_seen_at, last_absent_at FROM dataset_sighting "
        " WHERE external_id = '1302'").fetchone()

    assert row["last_absent_at"] is not None, "the absence was recorded"
    assert row_state(status="active", first_seen_at="2026-08-20T00:00:00Z",
                     last_seen_at=row["last_seen_at"],
                     row_run=7, latest_run=7,
                     # AFTER `first_seen_at`, deliberately: `new` is checked before
                     # `returned` and a run that began the moment the row first
                     # appeared would make it new rather than returned. The precedence
                     # is right; the fixture had to say which crawl this is.
                     run_started_at="2026-08-21T00:00:00Z",
                     sighted_at=row["last_seen_at"],
                     last_absent_at=row["last_absent_at"]) == STATE_RETURNED


def test_an_absence_is_only_written_for_the_rows_a_crawl_did_not_see(conn):
    """`record_absences` marks the complement of what was seen, and nothing else."""
    from scrapex.sightings import record_absences

    _stored(conn, "1301", "1302", "1303")
    record_sightings(conn, "contractors", ["1301", "1302", "1303"])
    conn.commit()

    assert record_absences(conn, "contractors", seen=["1301", "1302", "1303"],
                           run_ref="r") == 0, "a full crawl marks nobody absent"
    assert record_absences(conn, "contractors", seen=["1301"], run_ref="r2") == 2

    marked = {row[0] for row in conn.execute(
        "SELECT external_id FROM dataset_sighting WHERE last_absent_at IS NOT NULL")}
    assert marked == {"1302", "1303"}
    run = conn.execute(
        "SELECT last_absent_run_ref FROM dataset_sighting "
        " WHERE external_id = '1302'").fetchone()[0]
    assert run == "r2", "the run that proved it is recorded, so it can be checked"


def test_a_marked_row_outranks_an_observation(conn):
    """PRECEDENCE, and it is a decision rather than an accident. A row can be both
    absent and retired; the retirement is what somebody DECIDED, and a decision
    outranks an observation."""
    from scrapex.sightings import STATE_RETIRED, row_state

    assert row_state(status="retired", first_seen_at="2026-01-01T00:00:00Z",
                     last_seen_at="2026-01-01T00:00:00Z",
                     row_run=1, latest_run=9,
                     run_started_at="2026-08-21T00:00:00Z",
                     sighted_at="2026-01-01T00:00:00Z") == STATE_RETIRED


def test_a_new_row_is_not_called_updated_or_returned(conn):
    """A row cannot have changed or come back on the crawl that introduced it, so
    `new` is checked before both."""
    from scrapex.sightings import STATE_NEW, row_state

    assert row_state(status="active", first_seen_at="2026-08-21T12:00:00Z",
                     last_seen_at="2026-08-21T12:00:00Z",
                     row_run=4, latest_run=4,
                     run_started_at="2026-08-21T12:00:00Z",
                     changed_at="2026-08-21T12:00:00Z",
                     sighted_at="2026-08-21T12:00:00Z",
                     last_absent_at="2026-01-01T00:00:00Z") == STATE_NEW


def test_a_row_whose_run_is_unknown_is_not_reported_as_absent(conn):
    """There is no "last run" to be missing from when nothing names one, and calling
    every row absent would be an artefact of our own history rather than a fact about
    the site.

    IT READS `unsighted` AND NOT `confirmed`, WHICH IS HIS RULING OF 2026-08-29 and a
    change from what this test asserted before. `confirmed` claims the last crawl saw
    the row; nobody can show that it did. `unsighted` says "stored before the ledger
    existed" and claims nothing about the site — which is the honest answer for the
    57,041 snapshots taken before `0016` gave a run an id.
    """
    from scrapex.sightings import STATE_UNSIGHTED, row_state

    # nothing anywhere names a run
    assert row_state(status="active", first_seen_at="2026-08-20T00:00:00Z",
                     last_seen_at="2026-08-20T00:00:00Z",
                     row_run=None, latest_run=None,
                     sighted_at="2026-08-20T00:00:00Z") == STATE_UNSIGHTED
    # the dataset has a latest run, but THIS row predates run identity
    assert row_state(status="active", first_seen_at="2026-08-20T00:00:00Z",
                     last_seen_at="2026-08-20T00:00:00Z",
                     row_run=None, latest_run=5,
                     run_started_at="2026-08-29T00:00:00Z",
                     sighted_at="2026-08-20T00:00:00Z") == STATE_UNSIGHTED


def test_a_changed_row_reads_updated_and_not_confirmed():
    """THE STATE HE ASKED FOR BY NAME — «حتى حالة اذا تم ابديت لصف» — AND IT HAD NO
    GUARD. A mutation collapsing `updated` into `confirmed` survived every test in
    this file and every test of the payload: five of six mutations died and this one
    walked through, so the one state he singled out was the one nothing checked.

    IT IS ONLY KNOWABLE BECAUSE OF `R-20`. A revision is now written only when the
    content actually changed, so a revision dated in the last crawl IS the change.
    Before that fix every row had one every crawl and this state would have been
    every row, permanently — which is why R-20 was a precondition and not tidying.
    """
    from scrapex.sightings import STATE_CONFIRMED, STATE_UPDATED, row_state

    crawl = "2026-08-21T12:00:00Z"
    common = {"status": "active", "first_seen_at": "2026-01-01T00:00:00Z",
              "last_seen_at": crawl, "row_run": 3, "latest_run": 3,
              "run_started_at": crawl, "sighted_at": crawl}

    # A revision written by THAT crawl: the row changed.
    assert row_state(**common, changed_at=crawl) == STATE_UPDATED
    # A revision from an earlier crawl: seen again, unchanged since.
    assert row_state(**common, changed_at="2026-01-01T00:00:00Z") == STATE_CONFIRMED
    # Never revised at all — only ever its first write.
    assert row_state(**common, changed_at=None) == STATE_CONFIRMED


def test_updated_outranks_confirmed_but_not_new_or_absent():
    """Precedence, asserted rather than left to the order of the `if`s. A row that
    changed on the crawl that introduced it is `new`; one that changed and is now
    missing is `absent`. Both matter more to a reader than the change."""
    from scrapex.sightings import (
        STATE_ABSENT,
        STATE_NEW,
        STATE_UPDATED,
        row_state,
    )

    crawl = "2026-08-21T12:00:00Z"
    # new: written by the latest run, and first seen once it had started
    assert row_state(status="active", first_seen_at=crawl, last_seen_at=crawl,
                     row_run=2, latest_run=2, run_started_at=crawl,
                     changed_at=crawl, sighted_at=crawl) == STATE_NEW
    # absent: a DIFFERENT run wrote this row, so the latest one did not see it. It is
    # the run that decides now, not a timestamp comparison the crawl's own duration
    # could break.
    assert row_state(status="active", first_seen_at="2026-01-01T00:00:00Z",
                     last_seen_at="2026-08-01T00:00:00Z",
                     row_run=1, latest_run=2, run_started_at=crawl,
                     changed_at="2026-08-01T00:00:00Z",
                     sighted_at="2026-08-01T00:00:00Z") == STATE_ABSENT
    # updated: the latest run wrote it and a revision landed while it ran
    assert row_state(status="active", first_seen_at="2026-01-01T00:00:00Z",
                     last_seen_at=crawl, row_run=2, latest_run=2,
                     run_started_at=crawl, changed_at=crawl,
                     sighted_at=crawl) == STATE_UPDATED
