"""DEC-10: "fix the parser and re-run over the snapshots" did not actually work.

WHAT WAS WRONG. `approve_candidate`'s idempotency key was `(source_snapshot_id,
source_locator)` plus the schema hash. **Nothing in it describes the VALUES**, so a parser
that had been corrected — same page, same columns, different data — matched the existing
ingestion, answered `recovered=True` and wrote not one row.

WHY IT IS FIXED NOW RATHER THAN LATER, and it is his ruling
[R-38](../docs/RULINGS.md): on the listing it was survivable, because 871 pages are cheap
to fetch again. `R-37` registers the profile crawl, and that is **34,834 pages at about
11.1 hours measured** — so a parser defect found afterwards would cost a re-crawl to
repair what should be a re-parse. `docs/GENERIC-FETCH-SEAM.md` exists exactly so a wrong
parse costs minutes; a key that refuses to rewrite a corrected row hands the cost back.

THE FIX ADDS NO COLUMN, AND THE FIRST ATTEMPT DID. It put a `rows_hash` on
`generic_ingestion` — and that table is **append-only in both directions** and **UNIQUE on
`(source_snapshot_id, source_locator)`**, so the digest would have been unwritable after
the first insert and there can never be a second ingestion for one page. The schema was
saying, correctly, that "this page was ingested" happened once and is not revisable.

`generic_record.content_hash` already holds the fact per row, and the write path already
reads it to decide whether to write a revision. So the recovery short-circuit simply asks
the same question one step earlier, and a changed parse **falls through to the write path
that was always there** — a path that is already right, because the upsert is idempotent
and `R-20` writes a revision only for a real change.
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


def _snapshot(conn) -> int:
    saved = service.save_snapshot(
        conn, SnapshotCreate(source_url=URL, html_content=LISTING))
    return int(saved["page_snapshot_id"])


def _approval(candidate) -> CandidateApproval:
    return CandidateApproval(
        table_index=0, site_key="muqawil_org",
        site_display_name="Saudi Contractors Authority",
        dataset_key="contractors", dataset_name="Contractors",
        fields=[ApprovalField(field_key=f.field_key, display_name=f.source_name,
                              data_type="text",
                              identity=(f.field_key == "contractor_id"))
                for f in candidate.fields])


def _corrected(candidate, field: str, value: str):
    """THE SAME PAGE PARSED BETTER. Identical fields, identical identity, one column's
    values different — which is what fixing a parser looks like and is exactly the case
    the old key could not see.

    Not a new field: that is `R-31`'s case and opens a version. Not a missing one: that
    is refused. This is the case in between, which had no behaviour at all.
    """
    return dataclasses.replace(
        candidate,
        rows=[{**row, field: f"{value}{n}"} for n, row in enumerate(candidate.rows)])


def _values(conn, field: str) -> list[str]:
    import json

    return [json.loads(row[0]).get(field) for row in conn.execute(
        "SELECT data_json FROM generic_record ORDER BY record_key")]


def _revisions(conn) -> int:
    return conn.execute("SELECT COUNT(*) FROM generic_record_revision").fetchone()[0]


def _ingestions(conn) -> list[tuple]:
    return [tuple(row) for row in conn.execute(
        "SELECT generic_ingestion_id, record_count "
        "  FROM generic_ingestion ORDER BY generic_ingestion_id")]


# ---- the case the feature exists for ------------------------------------------

def test_a_corrected_parser_writes_its_new_values(conn):
    """THE WHOLE DEFECT IN ONE TEST. Same snapshot, same locator, same schema, better
    values — and it used to change nothing at all."""
    snapshot = _snapshot(conn)
    original = listing_candidate(LISTING)
    service.approve_candidate(conn, snapshot, _approval(original),
                              candidate=original)
    before = _values(conn, "card_city_region")

    fixed = _corrected(original, "card_city_region", "RIYADH - Riyadh #")
    result = service.approve_candidate(conn, snapshot, _approval(fixed),
                                       candidate=fixed)

    assert result["recovered"] is False, "it must not report a no-op"
    assert result["reparsed"] is True, "and it must say the page had been seen before"
    after = _values(conn, "card_city_region")
    assert after != before
    assert all(value.startswith("RIYADH - Riyadh #") for value in after)


def test_the_change_is_recorded_as_history(conn):
    """`R-20` MEETS `R-38`. A re-parse that changed values writes a revision per changed
    row, so "when did this column change" stays answerable — which is the whole reason
    R-20 stopped writing a revision for every unchanged row."""
    snapshot = _snapshot(conn)
    original = listing_candidate(LISTING)
    service.approve_candidate(conn, snapshot, _approval(original),
                              candidate=original)
    first = _revisions(conn)

    fixed = _corrected(original, "card_city_region", "CORRECTED ")
    service.approve_candidate(conn, snapshot, _approval(fixed), candidate=fixed)

    assert _revisions(conn) > first


def test_an_identical_re_approval_still_writes_nothing(conn):
    """THE OTHER DIRECTION, so the fix cannot pass by simply rewriting always. A genuine
    re-run of the same parser over the same page is a no-op, and `R-20` means no
    revision is written for it either."""
    snapshot = _snapshot(conn)
    candidate = listing_candidate(LISTING)
    service.approve_candidate(conn, snapshot, _approval(candidate),
                              candidate=candidate)
    revisions = _revisions(conn)
    ingestions = _ingestions(conn)

    result = service.approve_candidate(conn, snapshot, _approval(candidate),
                                       candidate=candidate)

    assert result["recovered"] is True
    assert _revisions(conn) == revisions
    assert _ingestions(conn) == ingestions, "no second ingestion for a no-op"


def test_a_reparse_does_not_claim_a_second_ingestion(conn):
    """THE SCHEMA IS WHAT DECIDES THIS, and it is why the first design was wrong.
    `generic_ingestion` is UNIQUE on `(source_snapshot_id, source_locator)` and
    append-only in both directions — so "this page was ingested" happened once and cannot
    be revised or repeated. A re-parse changes the ROWS, and their history belongs in
    `generic_record_revision`.
    """
    snapshot = _snapshot(conn)
    original = listing_candidate(LISTING)
    service.approve_candidate(conn, snapshot, _approval(original),
                              candidate=original)
    before = _ingestions(conn)

    fixed = _corrected(original, "card_city_region", "CORRECTED ")
    result = service.approve_candidate(conn, snapshot, _approval(fixed),
                                       candidate=fixed)

    assert _ingestions(conn) == before, "one ingestion per page, ever"
    assert result["generic_ingestion_id"] == before[0][0], (
        "and the result names the ingestion that exists, not a row that was refused")


def test_a_row_the_first_pass_missed_counts_as_a_change(conn):
    """A CORRECTED PARSER OFTEN FINDS MORE, not different. Every row it shares with the
    first pass is identical, so comparing values alone would call that unchanged — which
    is why the count is compared too."""
    snapshot = _snapshot(conn)
    original = listing_candidate(LISTING)
    fewer = dataclasses.replace(original, rows=original.rows[:-1])
    service.approve_candidate(conn, snapshot, _approval(fewer), candidate=fewer)
    assert len(_values(conn, "contractor_id")) == len(original.rows) - 1

    result = service.approve_candidate(conn, snapshot, _approval(original),
                                       candidate=original)

    assert result["recovered"] is False
    assert len(_values(conn, "contractor_id")) == len(original.rows)


# ---- what must not change -----------------------------------------------------

def test_a_different_identity_is_still_a_conflict(conn):
    """The row digest is a NEW condition, not a replacement for the old ones. Approving
    the same page into a different dataset is still refused, because that is a mistake
    rather than a corrected parse."""
    snapshot = _snapshot(conn)
    candidate = listing_candidate(LISTING)
    service.approve_candidate(conn, snapshot, _approval(candidate),
                              candidate=candidate)

    elsewhere = CandidateApproval(
        table_index=0, site_key="muqawil_org",
        site_display_name="Saudi Contractors Authority",
        dataset_key="engineers", dataset_name="Engineers",
        fields=_approval(candidate).fields)

    with pytest.raises(ExtractionConflict):
        service.approve_candidate(conn, snapshot, elsewhere, candidate=candidate)


def test_a_first_approval_is_not_reported_as_a_reparse(conn):
    """`reparsed` means "this page had been ingested before". A first approval must not
    claim it, or a caller counting re-parses counts every page."""
    snapshot = _snapshot(conn)
    candidate = listing_candidate(LISTING)

    result = service.approve_candidate(conn, snapshot, _approval(candidate),
                                       candidate=candidate)

    assert (result["recovered"], result["reparsed"]) == (False, False)
