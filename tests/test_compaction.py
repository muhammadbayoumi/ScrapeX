"""Spec 18: reclaiming space without ever deleting an observation.

The claims under test are the ones the interface makes to the owner:
the old file always survives, the numbers shown are measured rather than
modelled, and a successor that lost anything is refused before it goes live.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scrapex import compaction, db as dbmod, retention, settings, storage
from scrapex.ingest import ingest_payloads
from tests.test_ingest import make_entry, make_payload, one_row
from tests.test_retention import HISTORY, TODAY

SOURCE = "ELSEWEDYSHOP"


@pytest.fixture(autouse=True)
def isolated_pointer(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "POINTER_FILE", tmp_path / "location.json")


@pytest.fixture()
def db_path(tmp_path) -> Path:
    path = tmp_path / "home" / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    entry = make_entry()
    for date, price in HISTORY:
        ingest_payloads(conn, entry, [make_payload(
            [one_row(effective_price=price)], scraped_at=f"{date}T10:00:00Z")])
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def conn(db_path):
    c = dbmod.connect(db_path)
    try:
        yield c
    finally:
        c.close()


def set_aggressive(conn) -> str:
    retention.save_policy(conn, SOURCE, detail_days=30,
                          older_than_action=retention.ARCHIVE_ONLY)
    conn.commit()
    return retention.policy_digest(retention.get_policies(conn))


# ---- building a successor ----------------------------------------------------

def test_a_successor_holds_the_kept_rows_and_the_whole_catalogue(conn, db_path, tmp_path):
    set_aggressive(conn)
    out = tmp_path / "successor.db"
    result = compaction.build_successor(
        db_path, out, policies=retention.effective_policies(conn),
        cutoffs=retention.cutoff_dates(conn, TODAY))

    assert result.observations_before == len(HISTORY)
    assert 0 < result.observations_after < result.observations_before
    check = dbmod.connect(out)
    try:
        for table in ("source_site", "source_product", "source_variant", "source_offer"):
            assert check.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == \
                conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        check.close()


def test_building_a_successor_never_writes_to_the_original(conn, db_path, tmp_path):
    before = db_path.stat().st_mtime_ns
    rows_before = conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
    set_aggressive(conn)
    compaction.build_successor(db_path, tmp_path / "s.db",
                               policies=retention.effective_policies(conn),
                               cutoffs=retention.cutoff_dates(conn, TODAY))
    assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == rows_before
    assert db_path.stat().st_mtime_ns == before


def test_the_successor_is_still_append_only(conn, db_path, tmp_path):
    """A successor without the triggers would silently end the guarantee."""
    set_aggressive(conn)
    out = tmp_path / "s.db"
    compaction.build_successor(db_path, out, policies=retention.effective_policies(conn),
                               cutoffs=retention.cutoff_dates(conn, TODAY))
    check = dbmod.connect(out)
    try:
        with pytest.raises(Exception, match="append-only"):
            check.execute("DELETE FROM price_observation")
    finally:
        check.close()


def test_every_table_is_carried_not_just_the_ones_someone_remembered(conn, db_path, tmp_path):
    """A hand-written copy list silently drops whatever a later migration adds.
    The successor must contain every table the original has."""
    set_aggressive(conn)
    out = tmp_path / "s.db"
    compaction.build_successor(db_path, out, policies=retention.effective_policies(conn),
                               cutoffs=retention.cutoff_dates(conn, TODAY))
    check = dbmod.connect(out)
    try:
        original = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        successor = {r[0] for r in check.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        check.close()
    assert original - successor == set()


# ---- verification is a gate --------------------------------------------------

def test_a_faithful_successor_passes_verification(conn, db_path, tmp_path):
    set_aggressive(conn)
    out = tmp_path / "s.db"
    compaction.build_successor(db_path, out, policies=retention.effective_policies(conn),
                               cutoffs=retention.cutoff_dates(conn, TODAY))
    assert compaction.verify_successor(db_path, out) == []


def test_a_successor_missing_a_protected_row_is_refused(conn, db_path, tmp_path):
    """Simulates the bug the protected set exists to catch: a build that kept
    only recent rows and lost the cheapest price from three months ago."""
    set_aggressive(conn)
    out = tmp_path / "s.db"
    compaction.build_successor(db_path, out, policies=retention.effective_policies(conn),
                               cutoffs=retention.cutoff_dates(conn, TODAY))

    # Rebuild the successor's observation table without its cheapest row, which
    # requires dropping the append-only triggers IN THE COPY — proof that the
    # only way to lose one is to break the invariant on purpose.
    tampered = dbmod.connect(out)
    try:
        tampered.execute("DROP TRIGGER trg_price_obs_no_delete")
        tampered.execute("DELETE FROM price_observation WHERE effective_price = 40.0")
        tampered.commit()
    finally:
        tampered.close()

    problems = compaction.verify_successor(db_path, out)
    assert any("protected observation" in p for p in problems)
    assert any("trg_price_obs_no_delete" in p for p in problems)


def test_a_successor_that_lost_a_catalogue_row_is_refused(conn, db_path, tmp_path):
    set_aggressive(conn)
    out = tmp_path / "s.db"
    compaction.build_successor(db_path, out, policies=retention.effective_policies(conn),
                               cutoffs=retention.cutoff_dates(conn, TODAY))
    tampered = dbmod.connect(out)
    try:
        tampered.execute("PRAGMA foreign_keys = OFF")
        tampered.execute("DELETE FROM source_product")
        tampered.commit()
    finally:
        tampered.close()
    assert any("carried whole" in p for p in compaction.verify_successor(db_path, out))


# ---- preview -----------------------------------------------------------------

def test_the_preview_measures_a_real_file_and_then_removes_it(conn, db_path):
    set_aggressive(conn)
    result = compaction.preview(conn, db_path, today=TODAY)
    assert result.ok and result.bytes_after > 0
    assert result.built_path == "", "a preview must not offer a path to a deleted file"
    assert not list(db_path.parent.glob("*.preview*")), "the trial file was left behind"


def test_the_preview_states_that_nothing_is_freed_by_itself(conn, db_path):
    set_aggressive(conn)
    assert "until you delete the sealed archive" in \
        compaction.preview(conn, db_path, today=TODAY).detail


def test_a_no_op_policy_previews_as_nothing_to_do(conn, db_path):
    result = compaction.preview(conn, db_path, today=TODAY)   # shipped default
    assert result.observations_left_behind == 0
    assert "no space to reclaim" in result.detail


def test_the_number_shown_is_the_number_a_run_produces(conn, db_path, tmp_path):
    """Preview and run share ONE build implementation, so the figure cannot drift."""
    digest = set_aggressive(conn)
    previewed = compaction.preview(conn, db_path, today=TODAY)
    run = compaction.compact_warehouse(conn, db_path, today=TODAY, expected_digest=digest)
    assert run.observations_after == previewed.observations_after


# ---- committing --------------------------------------------------------------

def test_a_compaction_seals_the_old_file_and_never_deletes_it(conn, db_path):
    digest = set_aggressive(conn)
    before = conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
    result = compaction.compact_warehouse(conn, db_path, today=TODAY, expected_digest=digest)

    sealed = Path(result.sealed_path)
    assert sealed.exists(), "the predecessor must survive a compaction"
    archived = dbmod.connect(sealed)
    try:
        assert archived.execute(
            "SELECT COUNT(*) FROM price_observation").fetchone()[0] == before
    finally:
        archived.close()


def test_the_pointer_is_the_commit_point(conn, db_path):
    digest = set_aggressive(conn)
    result = compaction.compact_warehouse(conn, db_path, today=TODAY, expected_digest=digest)
    assert storage.read_pointer() == Path(result.built_path)
    assert storage.resolve_db_path().exists()


def test_a_stale_preview_cannot_authorise_a_run(conn, db_path):
    """The owner confirms numbers from a preview; if the policy changed since,
    those numbers are not what they would get."""
    digest = set_aggressive(conn)
    retention.save_policy(conn, SOURCE, detail_days=90,
                          older_than_action=retention.DAILY_SUMMARY)
    conn.commit()
    with pytest.raises(compaction.CompactionAborted, match="policy changed"):
        compaction.compact_warehouse(conn, db_path, today=TODAY, expected_digest=digest)


def test_a_failed_verification_leaves_the_warehouse_alone(conn, db_path, monkeypatch):
    digest = set_aggressive(conn)
    monkeypatch.setattr(compaction, "verify_successor", lambda a, b: ["invented problem"])
    with pytest.raises(compaction.CompactionAborted, match="did not pass verification"):
        compaction.compact_warehouse(conn, db_path, today=TODAY, expected_digest=digest)
    assert db_path.exists()
    assert storage.read_pointer() is None, "nothing may be switched after a refusal"
    assert not list(db_path.parent.glob("*.compact-*")), "the rejected build was kept"


def test_a_stale_pin_is_reported_rather_than_blocking_or_being_ignored(conn, db_path):
    """A pin may go stale after manual recovery or imported metadata.

    Two branches reviewed this and each got half of it. Blocking the compaction
    made ONE bad bookmark refuse every future run, reported as "1 protected
    observation did not survive" — a message that reads like data loss. Ignoring
    it let the run claim it carried the owner's exact protected set when it had
    not. A pin is a bookmark, not an observation: it cannot make verification
    demand a row nobody can supply, and it cannot be passed over in silence.
    """
    set_aggressive(conn)
    offer_id = conn.execute("SELECT offer_id FROM price_observation LIMIT 1").fetchone()[0]
    retention.pin(conn, offer_id, "2026-01-01", "hash-that-matches-no-row")
    conn.commit()
    digest = retention.policy_digest(retention.get_policies(conn))

    assert retention.protected_keys(conn) == retention.protected_keys_independently(conn)
    previewed = compaction.preview(conn, db_path, today=TODAY)
    assert previewed.stale_pins == 1
    assert "protect nothing" in previewed.detail, "a dead mark must not be silent"

    result = compaction.compact_warehouse(conn, db_path, today=TODAY,
                                          expected_digest=digest)
    assert result.ok, "one stale bookmark must not block the warehouse forever"

    # The mark itself survives: ScrapeX does not delete the owner's marks.
    live = dbmod.connect(Path(result.built_path))
    try:
        assert live.execute("SELECT COUNT(*) FROM retention_pin").fetchone()[0] == 1
    finally:
        live.close()


def test_the_audit_row_lands_in_the_database_that_is_now_live(conn, db_path):
    """Writing it before the run would leave a row stuck at 'running' inside the
    file being sealed, and the live warehouse would report a run that never ended."""
    digest = set_aggressive(conn)
    result = compaction.compact_warehouse(conn, db_path, today=TODAY, expected_digest=digest)
    live = dbmod.connect(Path(result.built_path))
    try:
        row = live.execute("SELECT mode, status FROM retention_run").fetchone()
        assert row["mode"] == "compact" and row["status"] == "succeeded"
        assert settings.get_state(live, "retention_last")["ok"] is True
    finally:
        live.close()


def test_a_compaction_can_be_undone_because_nothing_was_deleted(conn, db_path):
    digest = set_aggressive(conn)
    before = conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
    result = compaction.compact_warehouse(conn, db_path, today=TODAY, expected_digest=digest)

    undone = compaction.undo_compaction(result.sealed_path)
    assert undone.ok and "not in this one" in undone.detail
    back = dbmod.connect(storage.resolve_db_path())
    try:
        assert back.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == before
    finally:
        back.close()


def test_the_reclaimed_space_figure_is_named_for_what_it_really_is(conn, db_path):
    digest = set_aggressive(conn)
    result = compaction.compact_warehouse(conn, db_path, today=TODAY, expected_digest=digest)
    assert result.bytes_the_archive_would_free == result.bytes_before
    assert "ScrapeX will never delete it" in result.detail


def test_compaction_issues_no_delete_against_observations():
    source = Path(compaction.__file__).read_text(encoding="utf-8")
    assert "DELETE FROM price_observation" not in source
