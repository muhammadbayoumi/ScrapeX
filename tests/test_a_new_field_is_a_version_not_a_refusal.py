"""A site that adds a field gets a new schema version; one that loses a field does not.

`R-31`, from his question: «ربما تزيد حقول فى المستقبل» — what happens when the site
starts publishing something new. Measured before it was built: **nothing happened**.
Any difference from the approved field set raised `ExtractionConflict`, whose own
message pointed at *"schema-drift review support"* that did not exist and could not:
reaching version 2 requires the active version to be retired, and `valid_to` was read
in five places in the code and **written in none**.

THE RULE THIS FILE GUARDS IS DIRECTIONAL, and the direction is the whole safety of it:

    every approved field still present, plus new ones  ->  retire, open v2
    a field missing, renamed or re-keyed               ->  refuse, as before

#234 IS WHY THE NAIVE VERSION IS WRONG, and the last test here is that case. muqawil's
`region_id=0` publishes contractors with no location box, so its 74 pages taught a
schema of 21 fields where the declared set is 22 — a **subset** — and 823 pages were
refused. Had any drift opened a new version, that parser would have quietly retired a
column the site still publishes, and every row after it would have lost
`card_city_region` with nothing raised anywhere.

No network: the fixture is committed HTML, and the extra fields are added to a copy of
the real candidate.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.extract import service
from scrapex.extract.models import (
    ApprovalField,
    CandidateApproval,
    ExtractionConflict,
    SnapshotCreate,
)
from scrapex.extract.muqawil import listing_candidate

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "muqawil"
LISTING = (FIXTURES / "listing-en.html").read_text(encoding="utf-8")
URL = "https://muqawil.org/en/contractors?page=1"


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


def snapshot(conn, url: str = URL) -> int:
    saved = service.save_snapshot(
        conn, SnapshotCreate(source_url=url, html_content=LISTING))
    return int(saved["page_snapshot_id"])


def approval_for(candidate) -> CandidateApproval:
    return CandidateApproval(
        table_index=0, site_key="muqawil_org",
        site_display_name="Saudi Contractors Authority",
        dataset_key="contractors", dataset_name="Contractors",
        fields=[ApprovalField(field_key=f.field_key, display_name=f.source_name,
                              data_type="text",
                              identity=(f.field_key == "contractor_id"))
                for f in candidate.fields])


def with_extra(candidate, *names):
    """The same candidate plus fields the site has started publishing.

    Built by copying the real candidate's own field objects rather than by
    constructing one from scratch, so the shape stays whatever production makes it.
    """
    template = candidate.fields[-1]
    added = [dataclasses.replace(template, field_key=name, source_name=name)
             for name in names]
    rows = [{**row, **dict.fromkeys(names, "")} for row in candidate.rows]
    return dataclasses.replace(candidate, fields=[*candidate.fields, *added],
                               rows=rows)


def without(candidate, name):
    """The same candidate with a field the site still publishes taken away."""
    return dataclasses.replace(
        candidate,
        fields=[f for f in candidate.fields if f.field_key != name],
        rows=[{k: v for k, v in row.items() if k != name} for row in candidate.rows])


def approve(conn, candidate, url: str = URL):
    return service.approve_candidate(conn, snapshot(conn, url),
                                     approval_for(candidate), candidate=candidate)


def versions(conn):
    return [tuple(row) for row in conn.execute(
        "SELECT version_number, status, valid_to IS NOT NULL "
        "  FROM dataset_schema_version ORDER BY version_number")]


# ---- the schema grows --------------------------------------------------------

def test_a_field_the_site_adds_opens_a_second_version(conn):
    """v1 is retired rather than deleted, and v2 carries the wider set."""
    first = listing_candidate(LISTING)
    approve(conn, first)
    assert versions(conn) == [(1, "approved", False)]

    approve(conn, with_extra(first, "card_new_box"), url=URL + "&page=2")

    assert versions(conn) == [(1, "retired", True), (2, "approved", False)]


def test_the_retired_version_keeps_its_rows_and_its_fields(conn):
    """Retiring is not deleting. The rows approved under v1 are still there, and so
    is the field list that explains them — otherwise the history is unreadable."""
    first = listing_candidate(LISTING)
    approve(conn, first)
    before = conn.execute("SELECT COUNT(*) FROM generic_record").fetchone()[0]
    v1_fields = conn.execute(
        "SELECT COUNT(*) FROM schema_version_field WHERE schema_version_id = 1"
    ).fetchone()[0]

    approve(conn, with_extra(first, "card_new_box"), url=URL + "&page=2")

    assert conn.execute("SELECT COUNT(*) FROM generic_record").fetchone()[0] >= before
    assert conn.execute(
        "SELECT COUNT(*) FROM schema_version_field WHERE schema_version_id = 1"
    ).fetchone()[0] == v1_fields


def test_two_fields_at_once_still_open_exactly_one_version(conn):
    """A version per APPROVAL, not per field — or a site adding a box of six
    columns would leave six versions describing one change."""
    first = listing_candidate(LISTING)
    approve(conn, first)

    approve(conn, with_extra(first, "card_a", "card_b"), url=URL + "&page=2")

    assert [v[0] for v in versions(conn)] == [1, 2]


def test_the_same_schema_twice_opens_nothing(conn):
    """The unchanged case must not churn versions — it is the common one."""
    first = listing_candidate(LISTING)
    approve(conn, first)
    approve(conn, first, url=URL + "&page=2")

    assert versions(conn) == [(1, "approved", False)]


def test_only_the_ACTIVE_version_is_retired_so_v1_keeps_its_own_date(conn):
    """FOUND BY A MUTATION THAT SURVIVED, and it is a history defect not a crash.

    Retiring `WHERE schema_version_id >= 1` instead of `= active` passes every other
    test here, because those never reach a THIRD version. But it rewrites v1's
    `valid_to` every time anything changes afterwards, so "when did v1 stop being the
    schema" silently becomes "when did the schema last change" — and the version
    history stops being a history.

    The sentinel date is what makes this independent of the clock:
    `valid_to` is second-resolution, so two growths inside one second would compare
    equal and the assertion would pass on nothing.
    """
    first = listing_candidate(LISTING)
    approve(conn, first)
    grown = with_extra(first, "card_a")
    approve(conn, grown, url=URL + "&page=2")

    sentinel = "2020-01-01T00:00:00Z"
    conn.execute("UPDATE dataset_schema_version SET valid_to = ? "
                 " WHERE version_number = 1", (sentinel,))
    conn.commit()

    approve(conn, with_extra(grown, "card_b"), url=URL + "&page=3")

    dates = dict(conn.execute(
        "SELECT version_number, valid_to FROM dataset_schema_version"))
    assert dates[1] == sentinel, "v1's retirement date was rewritten"
    assert dates[2] is not None, "v2 should now be retired"
    assert dates[3] is None, "v3 is the active one"


# ---- the schema shrinks, which is #234 --------------------------------------

def test_a_field_the_site_still_publishes_cannot_be_dropped_by_one_page(conn):
    """THE #234 CASE, and the reason the rule is directional rather than permissive.

    `region_id=0`'s pages carry no location box. Under a permissive rule those 74
    pages would have retired `card_city_region` for the whole directory, and every
    later row would have lost it with nothing raised.
    """
    first = listing_candidate(LISTING)
    approve(conn, first)
    dropped = without(first, "card_city_region")

    with pytest.raises(ExtractionConflict) as raised:
        approve(conn, dropped, url=URL + "&page=2")

    assert "card_city_region" in str(raised.value)
    assert versions(conn) == [(1, "approved", False)]


def test_a_rename_is_refused_because_it_cannot_be_told_from_a_loss(conn):
    """One field gone and another arrived is indistinguishable from a rename, and
    guessing would orphan every value already stored under the old key."""
    first = listing_candidate(LISTING)
    approve(conn, first)
    renamed = with_extra(without(first, "card_city_region"), "card_town")

    with pytest.raises(ExtractionConflict):
        approve(conn, renamed, url=URL + "&page=2")

    assert versions(conn) == [(1, "approved", False)]


def test_the_refusal_says_what_was_dropped_and_what_to_do(conn):
    """A refusal nobody can act on sends the next session to guess."""
    first = listing_candidate(LISTING)
    approve(conn, first)

    with pytest.raises(ExtractionConflict) as raised:
        approve(conn, without(first, "card_city_region"), url=URL + "&page=2")

    message = str(raised.value)
    assert "card_city_region" in message
    assert "new dataset key" in message
