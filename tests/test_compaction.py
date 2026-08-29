"""Spec 18: reclaiming space without ever deleting an observation.

The claims under test are the ones the interface makes to the owner:
the old file always survives, the numbers shown are measured rather than
modelled, and a successor that lost anything is refused before it goes live.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scrapex import compaction, db as dbmod, retention, settings, storage
from scrapex.databases import registry as registry_mod
from scrapex.databases.domain import EngineDatabase
from scrapex.ingest import ingest_payloads
from tests.test_ingest import make_entry, make_payload, one_row
from tests.test_retention import HISTORY, TODAY

SOURCE = "ELSEWEDYSHOP"


@pytest.fixture(autouse=True)
def isolated_pointer(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "POINTER_FILE", tmp_path / "location.json")
    # The registry is the OTHER record commit_live_database writes, and this file
    # promotes real databases. `_point_registry_at` only follows a registry that
    # already names the file being superseded, so the owner's is safe by
    # construction — but a test that compacts a temporary database should not be
    # relying on that guard to keep its hands off ~/.scrapex/databases.json.
    monkeypatch.setattr(registry_mod, "REGISTRY_FILE", tmp_path / "databases.json")


@pytest.fixture()
def db_path(tmp_path) -> Path:
    path = tmp_path / "home" / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    entry = make_entry()
    for date, price in HISTORY:
        ingest_payloads(conn, entry, [make_payload(
            [one_row(price=price)], scraped_at=f"{date}T10:00:00Z")])
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

    The successor is built by running the SAME migrations, so comparing the two
    schemas proves nothing on its own — both sides would always agree. Proving
    it needs a table the source has and the migration chain does not create,
    which is exactly the shape of the defect: something present in the live
    warehouse that a rebuild would leave behind.
    """
    set_aggressive(conn)
    conn.execute("CREATE TABLE a_later_migration_would_add_this (x INTEGER)")
    conn.execute("INSERT INTO a_later_migration_would_add_this VALUES (1)")
    conn.commit()

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

    assert original - successor == {"a_later_migration_would_add_this"}, (
        "every table the migrations create must be carried; only one added behind "
        "their back may be absent")
    # ...and the gate must REFUSE such a successor rather than promote it.
    assert any("a_later_migration_would_add_this" in problem
               for problem in compaction.verify_successor(db_path, out)), \
        "verification accepted a successor that dropped a table"


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
        tampered.execute("DELETE FROM price_observation WHERE price = 40.0")
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
    assert result.stale_pins == 1
    assert "protect nothing" in result.detail, (
        "the RUN must say it too — counting a dead mark and then not reporting it "
        "is the same silence this test exists to prevent")

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


# ---- the successor must be the same KIND as the warehouse (issue #53) --------
#
# Every test above builds BOTH sides with `dbmod.migrate`, so source and
# successor agree by construction and no test in this file could see them
# diverge. The owner's warehouse is not built that way. It is a
# EngineDatabase, and the two streams produce genuinely different databases:
#
#     EngineDatabase.initialize()   40 tables  v59  app id 1398295884  ledger 59
#     dbmod.migrate()                   50 tables  v61  app id 0           no ledger
# Re-measured 2026-08-05. The versions move with every migration; the SHAPE of
# the defect is what this file pins — ten extra tables, no app id, no ledger.
#
# so compaction was handing the product a file the product refuses to open.

def _marketlens_warehouse(tmp_path: Path) -> Path:
    """A real typed warehouse, built the way the owner's actually is.

    Deliberately NOT `dbmod.migrate`: that is the fixture habit that hid #53.
    """
    path = tmp_path / "typed" / "scrapex-engine.db"
    EngineDatabase(path).initialize()
    conn = dbmod.connect(path)
    try:
        entry = make_entry()
        for date, price in HISTORY:
            ingest_payloads(conn, entry, [make_payload(
                [one_row(price=price)], scraped_at=f"{date}T10:00:00Z")])
        conn.commit()
    finally:
        conn.close()
    return path


def _prepare_the_way_53_shipped(source: Path, target: Path) -> None:
    """`build_successor`'s preparation exactly as the defect shipped it.

    THE ORIGINAL SPELLING NO LONGER REPRODUCES IT, and that is a result rather than a
    problem. #53 built the successor through the UNTYPED legacy stream, which left a file
    with no `application_id` — healthy SQLite that `sqlite3.connect` opens happily and
    `EngineDatabase.connect` refuses. Retiring `db/migrations/` on 2026-08-29 made
    `dbmod.migrate` delegate to the typed runner, so that call now produces a CORRECT
    successor and the gate below had nothing to refuse.

    So the untyping is done explicitly. The gate is what this test is about, and it must
    keep being exercised: a successor can still arrive unopenable by other routes — a
    half-written file, a build interrupted before the marker is stamped — and the refusal
    has to fire before anything is renamed, whichever route it came by.
    """
    conn = dbmod.connect(target)
    try:
        dbmod.migrate(conn)
        # What the legacy stream left behind by omission, now written on purpose.
        conn.execute("PRAGMA application_id = 0")
        conn.commit()
    finally:
        conn.close()


def test_a_compacted_marketlens_warehouse_still_opens_through_the_products_door(tmp_path):
    """The whole sequence: build, verify, promote — then open what was promoted.

    Opened through `EngineDatabase.connect()`, which is the call the engine
    makes at startup. That door is the point of the test: a bare `sqlite3.connect`
    opens the #53 successor happily, and so does the legacy `dbmod.connect` facade
    every other test in this file uses, so either one would pass while the owner's
    warehouse sat in a file the product would not load.
    """
    path = _marketlens_warehouse(tmp_path)
    conn = dbmod.connect(path)
    try:
        digest = set_aggressive(conn)
        before = conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
        result = compaction.compact_warehouse(conn, path, today=TODAY,
                                              expected_digest=digest)
    finally:
        conn.close()

    live = Path(result.built_path)
    assert storage.read_pointer() == live, "the promoted file is the live warehouse"

    opened = EngineDatabase(live).connect()          # ---- the real door ----
    try:
        assert opened.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] \
            == result.observations_after
    finally:
        opened.close()
    assert 0 < result.observations_after < before

    # The archive has to open through the same door too, or the undo path — the
    # owner's only way back to the observations left behind — leads nowhere. It
    # is asserted on its CONTENTS, not merely that it opens: on Windows the
    # predecessor usually keeps its own name (an open handle blocks the rename),
    # so "it opens" alone would be re-asserting that the untouched source is
    # still a MarketLens database, which was never in doubt.
    archive = EngineDatabase(Path(result.sealed_path)).connect()
    try:
        assert archive.execute(
            "SELECT COUNT(*) FROM price_observation").fetchone()[0] == before, (
            "every observation must still be reachable from the sealed archive")
    finally:
        archive.close()


def test_a_typed_warehouse_previews_as_a_measurement_not_as_a_bad_policy(tmp_path):
    """The owner's first step, and the one #53 made unpassable.

    The UI will not authorise a compaction without a preview, and a preview of a
    typed warehouse reported "This policy would not produce an acceptable
    database" — which reads as *your retention policy is wrong*, sends the owner
    to change a setting that was never the problem, and is the only sentence he
    would ever have seen about any of this.
    """
    path = _marketlens_warehouse(tmp_path)
    conn = dbmod.connect(path)
    try:
        set_aggressive(conn)
        result = compaction.preview(conn, path, today=TODAY)
    finally:
        conn.close()
    assert result.ok and not result.problems, result.problems
    assert result.observations_left_behind > 0
    assert "would stay in the sealed archive" in result.detail
    assert not list(path.parent.glob("*.preview*")), "the trial file was left behind"


def test_a_successor_the_product_cannot_open_is_refused_before_anything_moves(
        tmp_path, monkeypatch):
    """The gate, tested on its own against the artefact #53 actually produced.

    Verification runs while the successor is still a temporary file under a name
    no pointer resolves to, so refusing costs one build and nothing else: the
    warehouse is not renamed, not sealed, and never stops being the live one.
    """
    path = _marketlens_warehouse(tmp_path)
    monkeypatch.setattr(compaction, "_prepare_successor", _prepare_the_way_53_shipped)
    conn = dbmod.connect(path)
    try:
        digest = set_aggressive(conn)
        before = conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
        with pytest.raises(compaction.CompactionAborted) as refusal:
            compaction.compact_warehouse(conn, path, today=TODAY,
                                         expected_digest=digest)
        assert "this product can open" in str(refusal.value), (
            "the refusal must say the successor could not be OPENED. The old gate "
            "happened to stop this same build — on its schema version and a table "
            "it was missing — and named neither the cause nor the consequence")
        assert conn.execute(
            "SELECT COUNT(*) FROM price_observation").fetchone()[0] == before
    finally:
        conn.close()

    assert storage.read_pointer() is None, "nothing may be promoted after a refusal"
    assert not list(path.parent.glob("*.compact-*")), "a rejected build was kept"
    assert not list(path.parent.glob("*.building-*")), "a rejected build was kept"
    assert not storage.sealed_at(path), "the warehouse was sealed despite the refusal"
    EngineDatabase(path).connect().close()   # exactly where the owner was


def test_a_source_whose_kind_cannot_be_read_is_refused_rather_than_guessed(
        conn, db_path, monkeypatch):
    """Silence is not an answer, and must not be heard as "legacy".

    `_typed_class_for` decides BOTH how the successor is built and whether the
    identity gate runs at all, so if an unreadable header were treated as a
    legacy warehouse it would build the old way AND switch off the check that
    catches the old way — #53's exact shape, one layer down. This uses the
    legacy fixture deliberately: there, guessing "legacy" would be RIGHT, the
    compaction would succeed, and nothing else in the suite would notice.
    """
    digest = set_aggressive(conn)
    before = conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
    monkeypatch.setattr(compaction, "_application_id", lambda path: None)

    with pytest.raises(compaction.CompactionAborted, match="could not read what kind"):
        compaction.compact_warehouse(conn, db_path, today=TODAY, expected_digest=digest)

    assert storage.read_pointer() is None, "nothing may be promoted after a refusal"
    assert not list(db_path.parent.glob("*.compact-*"))
    assert not list(db_path.parent.glob("*.building-*"))
    assert not storage.sealed_at(db_path)
    assert conn.execute(
        "SELECT COUNT(*) FROM price_observation").fetchone()[0] == before

def test_a_source_that_is_behind_is_named_as_the_one_that_is_behind(tmp_path):
    """TWO DIFFERENT FAULTS WORE ONE SENTENCE.

    The successor is always built at the ENGINE's schema version. A mismatch
    therefore means one of two completely different things: the successor was
    built the wrong way — defect #53, which this change fixes — or the SOURCE is
    simply behind. Both used to report "the successor is on a different schema
    version", which sends the owner to inspect a successor that is perfectly
    correct.

    Since the engine upgrades a behind warehouse on the way up (#98), the second
    case now reaches compaction only through a restored old backup — which is
    exactly when a precise sentence is worth the most."""
    import sqlite3
    from scrapex.compaction import _prepare_successor, verify_successor
    from scrapex.databases.domain import EngineDatabase

    head = EngineDatabase(tmp_path / "probe.db").latest_schema_version
    if head < 2:
        # NOT A SKIP THAT ROTS: it turns itself back on. "Behind" means a
        # version BELOW the engine's head, and M5 restarted the engine stream at
        # 1, so there is no such version to sit at — v0 is an uninitialised
        # file, which is a different fault with a different message. The moment
        # engine migration 0002 exists this runs again, unchanged.
        pytest.skip(f"the engine stream is {head} migration(s); a source cannot "
                    "be behind head until there is a version below it")

    source = tmp_path / "behind.db"
    EngineDatabase(source).initialize()
    conn = sqlite3.connect(source)
    conn.execute(f"PRAGMA user_version = {head - 1}")
    conn.commit()
    conn.close()

    successor = tmp_path / "successor.db"
    _prepare_successor(source, successor)

    problems = verify_successor(source, successor)

    behind = [p for p in problems
              if f"the source warehouse is at schema v{head - 1}" in p]
    assert behind, f"the source being behind was not named; got {problems}"
    assert "upgrade it first" in behind[0], "it named the fault and not the way out"
