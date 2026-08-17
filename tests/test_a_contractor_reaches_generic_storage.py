"""A contractor, all the way from a saved page into `generic_record`.

THE SENTENCE THIS FILE MAKES TRUE. `scrapex/features.py` gates
`generic_extraction` on *"an approved non-product extraction reaching generic
storage"*, and that gate has been closed since the day it was written because
nothing had ever done it. Every other test in this project's generic half proves
one link; this one walks the whole chain:

    a real muqawil listing page
      -> save_snapshot          (evidence, unparsed)
      -> listing_candidate      (cards, in the shape the approval path speaks)
      -> approve_candidate      (the owner's schema, atomically)
      -> generic_record         (a contractor, with a revision behind it)

THE LINK THIS TESTS IS AN ADAPTER, NOT A SECOND PIPELINE. A muqawil listing has
TWENTY rows and ZERO `<table>` elements, so `detect_html_tables` finds nothing on
it. But nothing under `approve_candidate` cares about tables — only the
detection does — so the cards are converted into a `TableCandidate` and every
guarantee below it (atomicity, idempotent replay, revision history) is the one
that was already tested, not a copy of it.

The fixture is real, committed HTML. No network.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.extract import service
from scrapex.extract.models import (
    ApprovalField,
    CandidateApproval,
    SnapshotCreate,
)
from scrapex.extract.muqawil import listing_candidate, read_listing

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


def approval_for(candidate, **overrides):
    """The owner's answer: every detected field, typed, with the identity named."""
    body = dict(
        table_index=0,
        site_key="muqawil_org",
        site_display_name="Saudi Contractors Authority",
        dataset_key="contractors",
        dataset_name="Contractors",
        fields=[ApprovalField(field_key=f.field_key, display_name=f.source_name,
                              data_type="text",
                              identity=(f.field_key == "contractor_id"))
                for f in candidate.fields],
    )
    body.update(overrides)
    return CandidateApproval(**body)


def store(conn, html: str = LISTING, url: str = URL) -> int:
    saved = service.save_snapshot(conn, SnapshotCreate(source_url=url,
                                                       html_content=html))
    return int(saved["page_snapshot_id"])


def approve(conn, snapshot_id: int, html: str = LISTING):
    candidate = listing_candidate(html)
    return service.approve_candidate(conn, snapshot_id,
                                     approval_for(candidate),
                                     candidate=candidate)


# ---- the chain, end to end ---------------------------------------------------

def test_a_contractor_arrives_in_generic_storage(conn):
    """THE GATE. `generic_extraction` is enabled only after this has happened."""
    snapshot_id = store(conn)

    result = approve(conn, snapshot_id)

    stored = conn.execute(
        "SELECT record_key, data_json FROM generic_record "
        "ORDER BY generic_record_id").fetchall()
    assert len(stored) == len(read_listing(LISTING)) == 4
    assert result["recovered"] is False

    first = dict(stored[0])
    assert "Awared General Contracting Company" in first["data_json"]
    assert "20008518" in first["data_json"]


def test_the_record_key_is_stable_for_the_same_contractor(conn):
    """THE KEY IS A DIGEST OF THE IDENTITY FIELDS, not the id itself — which is
    how `_validated_rows` supports a composite identity without putting a value
    in a key. What matters is not its spelling but that the SAME contractor
    always lands on the SAME key: anything else and every crawl mints a second
    row for a company that was already there.

    Proved across two different pages rather than twice on one, because a key
    that depended on position or on the page would pass the easy version.
    """
    first_page = store(conn)
    approve(conn, first_page)
    key = conn.execute(
        "SELECT record_key FROM generic_record ORDER BY generic_record_id"
    ).fetchone()[0]

    # The same contractor, read from a page with different neighbours around it.
    moved = LISTING.replace("<div class='container'>",
                            "<div class='container'><p>a banner</p>")
    again = store(conn, moved, url=URL + "&again=1")
    service.approve_candidate(conn, again,
                              approval_for(listing_candidate(moved)),
                              candidate=listing_candidate(moved))

    assert conn.execute("SELECT count(*) FROM generic_record").fetchone()[0] == 4, (
        "the same four contractors became eight — the key is not stable")
    assert conn.execute(
        "SELECT count(*) FROM generic_record WHERE record_key = ?", (key,)
    ).fetchone()[0] == 1


def test_the_listing_holds_no_table_at_all_which_is_why_the_adapter_exists(conn):
    """If detection could see these rows the adapter would be dead weight. It
    cannot: the page is cards."""
    from scrapex.extract.html_table import detect_html_tables

    assert detect_html_tables(LISTING) == [], (
        "the listing grew a <table>, so the reason this adapter exists has "
        "changed and the decision should be revisited")


def test_every_record_carries_a_revision_behind_it(conn):
    """The revision is what makes "this contractor's grade changed on that date"
    a claim rather than an opinion."""
    approve(conn, store(conn))

    revisions = conn.execute(
        "SELECT count(*) FROM generic_record_revision").fetchone()[0]
    assert revisions == 4


def test_a_second_reading_of_the_same_page_is_recovered_and_not_duplicated(conn):
    """Idempotent replay, inherited from `approve_candidate` rather than
    rewritten — a lost response must not double every contractor."""
    snapshot_id = store(conn)
    first = approve(conn, snapshot_id)

    second = approve(conn, snapshot_id)

    assert second["recovered"] is True
    assert second["dataset_definition_id"] == first["dataset_definition_id"]
    assert conn.execute("SELECT count(*) FROM generic_record").fetchone()[0] == 4


def test_the_site_and_the_dataset_are_registered_by_the_same_act(conn):
    approve(conn, store(conn))

    site = conn.execute("SELECT site_key, base_url FROM site_profile").fetchone()
    assert site["site_key"] == "muqawil_org"
    assert "muqawil.org" in site["base_url"]

    dataset = conn.execute(
        "SELECT dataset_key, dataset_kind FROM dataset_definition").fetchone()
    assert dataset["dataset_key"] == "contractors"


# ---- what the adapter must get right -----------------------------------------

def test_the_schema_is_the_union_of_every_card_and_not_the_first_one():
    """A contractor with no rating carries no rating keys. Keying the schema off
    row one would drop a column for every contractor after it that had one."""
    candidate = listing_candidate(LISTING)
    keys = {f.field_key for f in candidate.fields}

    assert "customer_rating_score" in keys
    assert "contractor_id" in keys and "company_name" in keys
    for row in candidate.rows:
        assert set(row) == keys, (
            "a row is missing a field the schema declares — `_validated_rows` "
            "walks the field list and would raise rather than record a blank")


def test_a_missing_value_is_None_and_not_an_absent_key():
    candidate = listing_candidate(LISTING)
    thin = [row for row in candidate.rows if row["customer_rating_score"] is None]

    assert thin, "the fixture has no unrated contractor, so this proves nothing"
    assert "customer_rating_score" in thin[0]


def test_the_contractor_id_is_offered_as_the_identity():
    """Not guessed by uniqueness — named. Two contractors can share a name, a
    city and a membership level; only the id is theirs."""
    candidate = listing_candidate(LISTING)
    identity = [f.field_key for f in candidate.fields if f.identity_candidate]

    assert identity == ["contractor_id"]


def test_nothing_is_typed_beyond_text():
    """`html_table.py` infers types from one page's values, and twenty rows
    would type a rating `integer` because none of them happened to be 4.5. The
    owner types the schema at approval; that step is the whole design."""
    candidate = listing_candidate(LISTING)

    assert {f.data_type for f in candidate.fields} == {"text"}


def test_a_page_with_no_cards_is_refused_rather_than_approved_empty():
    """An empty approval would register a dataset, write no rows, and report
    success — a crawl of nothing, recorded as a crawl."""
    candidate = listing_candidate("<html><body>nothing here</body></html>")

    assert candidate.approvable is False
    assert candidate.rows == ()
    assert "No contractor cards" in candidate.warnings[0]
