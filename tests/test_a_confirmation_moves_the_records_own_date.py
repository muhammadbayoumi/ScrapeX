"""`R-54`, the root half: a confirming pass moves the record's own `last_seen_at`.

WHAT WAS WRONG. `approve_candidate` returns seventy lines above its upsert when every row
on the page is unchanged (`_rows_unchanged`, the `DEC-10`/`R-40` short-circuit). That
return is correct about the ROWS — nothing changed, so nothing should be rewritten — and
wrong about the OBSERVATION: the upsert it skips is the only write that moved
`last_seen_at`, so a pass that confirmed a row left the row's own date behind.

Meanwhile `taxonomy.py` refreshed the same row's MEMBERSHIPS on that very pass. Measured
read-only on the owner's warehouse on 2026-08-27:

    profile records whose last_seen_at reads 2026-08-23    17,264
    records reading 2026-08-24                                121
    their memberships dated 2026-08-24                    397,526 -- every one
    records OLDER THAN THEIR OWN MEMBERSHIPS               17,259

WHY THIS IS THE ROOT AND NOT THE SYMPTOM, which is his ruling `R-54`. The visible defect is
the State column, and the obvious fix is the sighting ledger — but state is compared against
`MAX(last_seen_at)`, so a fix that starts from the ledger builds on a field that does not
move. He was offered the ledger-first route with its cost stated and took the root instead.

**The comparison is deliberately NOT changed here.** He ruled the root first and the
comparison second, in its own pull request, so that a failing mutation names one of the two
rather than either (`OP-18`).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.extract import service
from scrapex.extract.models import ApprovalField, CandidateApproval, SnapshotCreate
from scrapex.extract.muqawil import listing_candidate

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "muqawil"
LISTING = (FIXTURES / "listing-en.html").read_text(encoding="utf-8")
URL = "https://muqawil.org/en/contractors?page=1"

#: Any timestamp older than "now" would do. A real one from before the warehouse existed
#: makes a failure read as "the date did not move" rather than "the date is odd".
LONG_AGO = "2020-01-01T00:00:00Z"


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
    """THROUGH THE PRODUCTION WRITER. `LESSONS` records seventeen tests that passed both
    before and after a real defect because none of them stored a compressed page."""
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


def _approved_once(conn) -> tuple[int, int]:
    """The state this whole file is about: one page approved, and approving it again is a
    confirmation because nothing on it changed. Returns `(snapshot_id, dataset_id)`."""
    snapshot_id = _snapshot(conn)
    candidate = listing_candidate(LISTING)
    result = service.approve_candidate(
        conn, snapshot_id, _approval(candidate), candidate=candidate)
    assert not result.get("recovered"), "the FIRST approval is not a confirmation"
    return snapshot_id, int(result["dataset_definition_id"])


def _confirm_again(conn, snapshot_id: int) -> dict:
    candidate = listing_candidate(LISTING)
    return service.approve_candidate(
        conn, snapshot_id, _approval(candidate), candidate=candidate)


def _age_every_row(conn, dataset_id: int) -> int:
    """Push every row's date into the past so a move is visible.

    NECESSARY RATHER THAN CONVENIENT: `last_seen_at` is `strftime(...,'now')` at SECOND
    resolution, so two approvals inside one second write the same string and a test that
    merely re-approved would pass whether or not the fix exists. That is the shape of
    false green this suite is built to avoid.
    """
    return int(conn.execute(
        "UPDATE generic_record SET last_seen_at = ? WHERE dataset_definition_id = ?",
        (LONG_AGO, dataset_id)).rowcount)


def _dates(conn, dataset_id: int) -> list[str]:
    return [row[0] for row in conn.execute(
        "SELECT last_seen_at FROM generic_record WHERE dataset_definition_id = ? "
        "ORDER BY generic_record_id", (dataset_id,))]


# --------------------------------------------------------------------- the defect itself

def test_a_confirming_reapproval_moves_the_records_own_date(conn):
    """THE DEFECT, in one assertion. Before the fix every date stayed at `LONG_AGO`."""
    snapshot_id, dataset_id = _approved_once(conn)
    aged = _age_every_row(conn, dataset_id)
    assert aged > 0, "the fixture stored no rows, so nothing below proves anything"

    result = _confirm_again(conn, snapshot_id)

    assert result.get("recovered") is True, (
        "the second approval must still take the short-circuit — this file is about what "
        "that branch writes, not about removing it")
    assert all(date != LONG_AGO for date in _dates(conn, dataset_id)), (
        "a confirmed row kept the date it had before the confirmation")


def test_the_confirmation_reaches_every_row_on_the_page(conn):
    """Not just the first. The `IN (...)` list is built from the whole page."""
    snapshot_id, dataset_id = _approved_once(conn)
    aged = _age_every_row(conn, dataset_id)
    _confirm_again(conn, snapshot_id)
    moved = sum(1 for date in _dates(conn, dataset_id) if date != LONG_AGO)
    assert moved == aged, f"{moved} of {aged} row(s) moved"


def test_the_result_says_how_many_rows_it_confirmed(conn):
    """A count the caller can print. `contractors.approve` used to say "wrote nothing"."""
    snapshot_id, dataset_id = _approved_once(conn)
    aged = _age_every_row(conn, dataset_id)
    result = _confirm_again(conn, snapshot_id)
    assert result.get("confirmed") == aged, (
        f"result says {result.get('confirmed')!r}, {aged} row(s) were on the page")


# ----------------------------------------------------- the three columns it must not move

def test_a_confirmation_writes_no_revision(conn):
    """`R-20` / `SR-6`: an unchanged value is confirmed, not appended.

    The revision table is also UNIQUE on `(record, snapshot, content_hash)`, so a
    revision per confirmation would not merely be noise — it would raise on the second
    confirmation of the same page.
    """
    snapshot_id, dataset_id = _approved_once(conn)
    before = conn.execute(
        "SELECT COUNT(*) FROM generic_record_revision").fetchone()[0]
    _age_every_row(conn, dataset_id)
    _confirm_again(conn, snapshot_id)
    after = conn.execute("SELECT COUNT(*) FROM generic_record_revision").fetchone()[0]
    assert after == before, f"{after - before} revision(s) written by a confirmation"


def test_a_confirmation_does_not_resurrect_a_retired_row(conn):
    """`OP-64` retired 14 impostor rows on the owner's warehouse by setting `status`.

    The upsert this branch skips sets `status='active'` UNCONDITIONALLY, so the confirming
    path must not copy that: a withdrawal somebody decided outranks an observation, which
    is `sightings.row_state`'s first precedence rule.
    """
    snapshot_id, dataset_id = _approved_once(conn)
    victim = conn.execute(
        "SELECT generic_record_id FROM generic_record "
        " WHERE dataset_definition_id = ? ORDER BY generic_record_id LIMIT 1",
        (dataset_id,)).fetchone()[0]
    conn.execute("UPDATE generic_record SET status = 'retired' "
                 " WHERE generic_record_id = ?", (victim,))
    _age_every_row(conn, dataset_id)

    _confirm_again(conn, snapshot_id)

    assert conn.execute("SELECT status FROM generic_record WHERE generic_record_id = ?",
                        (victim,)).fetchone()[0] == "retired", (
        "a confirmation un-retired a row that had been withdrawn")


def test_a_confirmation_does_not_move_the_source_snapshot(conn):
    """That column is the RUN link the other half of `R-54` needs, and moving it here
    would change which snapshot is cited as a row's source before the state computation
    that justifies it exists."""
    snapshot_id, dataset_id = _approved_once(conn)
    before = [row[0] for row in conn.execute(
        "SELECT source_snapshot_id FROM generic_record "
        " WHERE dataset_definition_id = ? ORDER BY generic_record_id", (dataset_id,))]
    _age_every_row(conn, dataset_id)
    _confirm_again(conn, snapshot_id)
    after = [row[0] for row in conn.execute(
        "SELECT source_snapshot_id FROM generic_record "
        " WHERE dataset_definition_id = ? ORDER BY generic_record_id", (dataset_id,))]
    assert after == before, "a confirmation repointed a row at a different snapshot"


def test_a_confirmation_does_not_move_first_seen_at(conn):
    """`first_seen_at` answers "when did this contractor appear", and `row_state` reads it
    to decide `new`. A confirmation that moved it would make every row new for ever."""
    snapshot_id, dataset_id = _approved_once(conn)
    conn.execute("UPDATE generic_record SET first_seen_at = ? "
                 " WHERE dataset_definition_id = ?", (LONG_AGO, dataset_id))
    _age_every_row(conn, dataset_id)
    _confirm_again(conn, snapshot_id)
    firsts = {row[0] for row in conn.execute(
        "SELECT first_seen_at FROM generic_record WHERE dataset_definition_id = ?",
        (dataset_id,))}
    assert firsts == {LONG_AGO}, f"first_seen_at moved: {sorted(firsts)}"


# ------------------------------------------------------------------- the helper's own edges

def test_confirm_seen_with_no_keys_writes_nothing(conn):
    """A page that parsed to zero rows is a real case: `_rows_unchanged` answers True for
    it, so this runs with an empty list.

    AND THE REASON FIRST WRITTEN HERE WAS WRONG. It said "an `IN ()` would be a syntax
    error", so the function carried a `if not record_keys: return 0` guard. A mutation
    deleted that guard and this test stayed green, which sent me to measure it: SQLite
    3.50.4 ACCEPTS `WHERE k IN ()`, matches nothing, and reports `rowcount` 0. The guard
    was returning by hand what SQLite already returns, so it is gone — and what this test
    pins is the BEHAVIOUR, which holds either way.
    """
    _, dataset_id = _approved_once(conn)
    _age_every_row(conn, dataset_id)
    assert service._confirm_seen(conn, dataset_id, []) == 0
    assert set(_dates(conn, dataset_id)) == {LONG_AGO}, (
        "an empty confirmation moved a date")


def test_confirm_seen_touches_only_the_dataset_it_was_given(conn):
    """`record_key` is unique per dataset, NOT globally — `UNIQUE (dataset_definition_id,
    record_key)`. A confirmation of one dataset must not move a colliding key in another,
    which is what the missing `dataset_definition_id` predicate would have done."""
    snapshot_id, dataset_id = _approved_once(conn)
    keys = [row[0] for row in conn.execute(
        "SELECT record_key FROM generic_record WHERE dataset_definition_id = ?",
        (dataset_id,))]
    # A second dataset carrying the SAME record_key, built by copying the stored rows.
    other = int(conn.execute(
        "INSERT INTO dataset_definition (source_id, dataset_key, original_name, "
        "dataset_kind, discovery_method) "
        "SELECT source_id, 'other_dataset', original_name, dataset_kind, "
        "       discovery_method "
        "  FROM dataset_definition WHERE dataset_definition_id = ?",
        (dataset_id,)).lastrowid)
    version = int(conn.execute(
        "INSERT INTO dataset_schema_version (dataset_definition_id, version_number, "
        "schema_hash) VALUES (?, 1, 'other-shape')", (other,)).lastrowid)
    conn.execute(
        "INSERT INTO generic_record (dataset_definition_id, record_key, "
        "schema_version_id, data_json, source_snapshot_id, source_locator, "
        "content_hash, last_seen_at) "
        "SELECT ?, record_key, ?, data_json, source_snapshot_id, source_locator, "
        "       content_hash, ? "
        "  FROM generic_record WHERE dataset_definition_id = ?",
        (other, version, LONG_AGO, dataset_id))

    _age_every_row(conn, dataset_id)
    moved = service._confirm_seen(conn, dataset_id, keys)

    assert moved == len(keys)
    intact = {row[0] for row in conn.execute(
        "SELECT last_seen_at FROM generic_record WHERE dataset_definition_id = ?",
        (other,))}
    assert intact == {LONG_AGO}, (
        f"the other dataset's dates moved too: {sorted(intact)}")


def test_the_confirmation_is_not_committed_by_the_service(conn, tmp_path: Path):
    """`extract/service.py` is transaction-neutral BY CONVENTION and the caller commits.

    Asserted rather than assumed, because the convention is what makes the callers correct:
    `contractors.approve` commits after the membership write so a row and its groups land
    together, and `extract/api.py` goes through `EngineDatabase.write`. A service that
    committed here would break the first of those.
    """
    snapshot_id, dataset_id = _approved_once(conn)
    conn.commit()
    _age_every_row(conn, dataset_id)
    conn.commit()

    _confirm_again(conn, snapshot_id)          # deliberately NOT committed

    second = sqlite3.connect(f"file:{tmp_path / 'scrapex-engine.db'}?mode=ro", uri=True)
    try:
        outside = {row[0] for row in second.execute(
            "SELECT last_seen_at FROM generic_record WHERE dataset_definition_id = ?",
            (dataset_id,))}
    finally:
        second.close()
    assert outside == {LONG_AGO}, (
        "the service committed on its own, so a caller can no longer roll a failed "
        "membership write back together with the row it belongs to")

    conn.commit()
    third = sqlite3.connect(f"file:{tmp_path / 'scrapex-engine.db'}?mode=ro", uri=True)
    try:
        after = {row[0] for row in third.execute(
            "SELECT last_seen_at FROM generic_record WHERE dataset_definition_id = ?",
            (dataset_id,))}
    finally:
        third.close()
    assert after != {LONG_AGO}, "the caller's commit did not persist the confirmation"


def test_confirming_twice_is_not_an_error_and_stays_current(conn):
    """Idempotent, and the reason it must be is `--run-ref`: a resumed crawl re-approves
    pages it already approved, and 34,834 of them would each hit this branch."""
    snapshot_id, dataset_id = _approved_once(conn)
    _age_every_row(conn, dataset_id)
    first = _confirm_again(conn, snapshot_id)
    second = _confirm_again(conn, snapshot_id)
    assert first.get("recovered") is True and second.get("recovered") is True
    assert second.get("confirmed") == first.get("confirmed")
    assert all(date != LONG_AGO for date in _dates(conn, dataset_id))


# --------------------------------------------------------------- what the caller now says

def test_the_crawl_no_longer_reports_that_a_confirmation_wrote_nothing(conn):
    """The printed sentence was `"{recovered} unchanged and wrote nothing"`, and after this
    change that is false rather than merely terse.

    READ OFF THE SOURCE, and the reason is that the alternative is worse: driving
    `contractors.approve` needs both locale halves, a directory and a frontier, and a test
    that builds all of it to check one sentence would fail for a dozen reasons that have
    nothing to do with the sentence. What matters is that the claim is gone and that the
    count the service returns is actually read.
    """
    source = (Path(__file__).resolve().parents[1]
              / "scrapex" / "contractors.py").read_text(encoding="utf-8")
    assert "unchanged and wrote nothing" not in source, (
        "the crawl still prints that a confirmation wrote nothing")
    assert 'result.get("confirmed")' in source, (
        "the count the service returns is never read, so the printed number cannot move")
