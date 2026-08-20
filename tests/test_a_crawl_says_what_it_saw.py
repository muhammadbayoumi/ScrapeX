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


def _stored(conn, *contractor_ids: str) -> None:
    """Records for contractors we actually ingested, minimally shaped.

    Written against the REAL column list rather than a remembered one — the
    first draft of this helper invented `identity_key`, and the column is
    `record_key`. Every NOT NULL column is supplied; none is guessed.
    """
    conn.execute(
        "INSERT INTO site_profile (site_key, display_name, base_url) "
        "VALUES ('s','S','https://example.test')")
    conn.execute(
        "INSERT INTO dataset_definition "
        "(site_profile_id, dataset_key, original_name, dataset_kind, "
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
            (one, json.dumps({"contractor_id": one}), f"h{one}"))
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
