"""`R-53` step 1: live rows are re-approved onto the field set they actually carry.

THE FAULT, measured on `contractor_profiles` 2026-08-27. The APPROVED version was v3 — 39
fields, taught by the 14 impostor pages `OP-64` disowned — while all 17,371 live rows sat on
v2, 27 fields, RETIRED. The twelve fields v3 adds are `x_*` listing keys, empty on every live
row. **The next field the site publishes makes the whole page refused rather than recorded**,
and muqawil sets that date.

WHAT THESE TESTS ARE REALLY GUARDING, because the repair itself is twenty lines of SQL:

* that `R-31` is NOT relaxed. The ordinary approval path must still refuse a subset — that
  rule is what stopped `region_id=0`'s 74 pages from retiring a column the site publishes and
  refusing 823 others. This repair asks for the forbidden shape and must therefore prove its
  own case, every time, against the database.
* that the two preconditions are load-bearing TOGETHER. Scoping "is this field empty?" to
  active rows is only safe because no active row is bound to the version being retired. Drop
  either and the operation can strand a row or discard a published value.
* that `_ensure_schema` no longer binds a new page to a RETIRED version, which is the fault
  continuing rather than the fault's leftovers. That half applies to every dataset.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.extract import service
from scrapex.extract.models import ExtractionConflict, ExtractionNotFound


@pytest.fixture()
def engine_conn(tmp_path: Path):
    """The same rig every extraction test uses, so this file cannot drift from them."""
    registry = DatabaseRegistry(
        EngineDatabase(tmp_path / "scrapex-engine.db"),
        pointer_file=tmp_path / "databases.json",
    )
    registry.initialize()
    connection = registry.engine.connect()
    try:
        yield connection
    finally:
        connection.close()

FIELDS_27 = tuple(f"kept_{n:02d}" for n in range(27))
PHANTOM_12 = tuple(f"x_phantom_{n:02d}" for n in range(12))


def _rig(conn: sqlite3.Connection, *, live_rows: int = 5,
         phantom_on_retired: bool = True) -> dict[str, int]:
    """A dataset shaped exactly like the fault: live rows on a retired version.

    Built through SQL rather than through the approval path on purpose — the approval path
    REFUSES this shape, which is why the fault needed a repair and not a re-run.
    """
    conn.execute("INSERT INTO site_profile (site_key, display_name, base_url) "
                 "VALUES ('rig_site', 'Rig', 'https://rig.example/')")
    site_id = int(conn.execute("SELECT site_profile_id FROM site_profile "
                               "WHERE site_key='rig_site'").fetchone()[0])
    conn.execute(
        "INSERT INTO dataset_definition (site_profile_id, dataset_key, display_name, "
        "original_name, discovery_method, locator_json) VALUES (?,?,?,?,'html_table','{}')",
        (site_id, "rig", "Rig", "Rig"))
    dataset_id = int(conn.execute("SELECT dataset_definition_id FROM dataset_definition "
                                  "WHERE dataset_key='rig'").fetchone()[0])

    def field(key: str, order: int) -> int:
        conn.execute(
            "INSERT INTO field_definition (dataset_definition_id, field_key, "
            "original_name, data_type, is_nullable, identity_role, display_order) "
            "VALUES (?,?,?,'text',1,'none',?)", (dataset_id, key, key, order))
        return int(conn.execute(
            "SELECT field_definition_id FROM field_definition "
            "WHERE dataset_definition_id=? AND field_key=?", (dataset_id, key)).fetchone()[0])

    ids = {key: field(key, n) for n, key in enumerate(FIELDS_27 + PHANTOM_12)}

    def version(number: int, keys: tuple[str, ...], *, approved: bool) -> int:
        conn.execute(
            "INSERT INTO dataset_schema_version (dataset_definition_id, version_number, "
            "schema_hash, status, valid_to) VALUES (?,?,?,?,?)",
            (dataset_id, number, f"hash-of-{len(keys)}-fields",
             "approved" if approved else "retired",
             None if approved else "2026-08-23T00:00:00Z"))
        version_id = int(conn.execute(
            "SELECT schema_version_id FROM dataset_schema_version "
            "WHERE dataset_definition_id=? AND version_number=?",
            (dataset_id, number)).fetchone()[0])
        for order, key in enumerate(keys):
            conn.execute("INSERT INTO schema_version_field (schema_version_id, "
                         "field_definition_id, field_order) VALUES (?,?,?)",
                         (version_id, ids[key], order))
        return version_id

    retired = version(2, FIELDS_27, approved=False)
    approved_id = version(3, FIELDS_27 + PHANTOM_12, approved=True)

    conn.execute("INSERT INTO generic_page_snapshot (source_url, html_content, content_hash) "
                 "VALUES ('https://rig.example/p', '<html/>', 'snap-hash')")
    snapshot_id = int(conn.execute("SELECT page_snapshot_id FROM generic_page_snapshot "
                                   "WHERE content_hash='snap-hash'").fetchone()[0])

    def record(locator: str, version_id: int, status: str, payload: dict[str, str]) -> None:
        import json
        conn.execute(
            "INSERT INTO generic_record (dataset_definition_id, record_key, "
            "schema_version_id, source_snapshot_id, source_locator, data_json, "
            "content_hash, status) VALUES (?,?,?,?,?,?,?,?)",
            (dataset_id, locator, version_id, snapshot_id, f"row:{locator}",
             json.dumps(payload), f"hash-{locator}", status))

    kept = {key: "value" for key in FIELDS_27}
    for n in range(live_rows):
        record(f"live-{n}", retired, "active", dict(kept))
    # The impostors: retired, bound to the APPROVED version, and carrying the phantom keys.
    # That is the shape that made the first draft of this repair refuse itself.
    poison = dict(kept) | {key: ("poison" if phantom_on_retired else "") for key in PHANTOM_12}
    for n in range(2):
        record(f"impostor-{n}", approved_id, "retired", poison)
    conn.commit()
    return {"dataset_id": dataset_id, "retired": retired, "approved": approved_id,
            "snapshot": snapshot_id, "live_rows": live_rows}


def _approved_version(conn: sqlite3.Connection, dataset_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT schema_version_id, version_number, "
        "(SELECT count(*) FROM schema_version_field f "
        "  WHERE f.schema_version_id=dataset_schema_version.schema_version_id) AS fields "
        "FROM dataset_schema_version WHERE dataset_definition_id=? AND valid_to IS NULL",
        (dataset_id,)).fetchone()


def test_the_dry_run_changes_nothing(engine_conn):
    rig = _rig(engine_conn)
    before = engine_conn.execute(
        "SELECT schema_version_id, status, valid_to FROM dataset_schema_version "
        "ORDER BY schema_version_id").fetchall()
    plan = service.reapprove_onto_clean_version(engine_conn, "rig", dry_run=True)
    assert plan["dry_run"] is True
    assert plan["records_to_move"] == rig["live_rows"]
    assert plan["field_count"] == len(FIELDS_27)
    assert sorted(plan["dropped_fields"]) == sorted(PHANTOM_12)
    after = engine_conn.execute(
        "SELECT schema_version_id, status, valid_to FROM dataset_schema_version "
        "ORDER BY schema_version_id").fetchall()
    assert [tuple(r) for r in before] == [tuple(r) for r in after], (
        "the dry run wrote to dataset_schema_version. A dry run that changes anything is "
        "worse than no dry run, because it is trusted.")


def test_it_moves_the_live_rows_onto_a_new_approved_version(engine_conn):
    rig = _rig(engine_conn)
    done = service.reapprove_onto_clean_version(engine_conn, "rig", dry_run=False)
    engine_conn.commit()

    assert done["records_moved"] == rig["live_rows"]
    assert done["field_count"] == len(FIELDS_27)

    approved = _approved_version(engine_conn, rig["dataset_id"])
    assert approved is not None, "the dataset has no approved version at all afterwards"
    assert approved["version_number"] == 4
    assert approved["fields"] == len(FIELDS_27), (
        "the new version does not declare the field set the live rows carry")

    stranded = engine_conn.execute(
        "SELECT count(*) FROM generic_record g JOIN dataset_schema_version sv "
        "  ON sv.schema_version_id=g.schema_version_id "
        " WHERE g.dataset_definition_id=? AND g.status='active' AND sv.valid_to IS NOT NULL",
        (rig["dataset_id"],)).fetchone()[0]
    assert stranded == 0, f"{stranded} active row(s) are still bound to a retired version"

    approved_count = engine_conn.execute(
        "SELECT count(*) FROM dataset_schema_version "
        " WHERE dataset_definition_id=? AND valid_to IS NULL",
        (rig["dataset_id"],)).fetchone()[0]
    assert approved_count == 1, "a dataset must have exactly one approved version"


def test_the_retired_impostors_keep_the_version_that_declared_their_fields(engine_conn):
    """`R-53`'s own condition: they *"do not silently lose the columns they were approved
    under"*. This is what makes precondition 2's active-only scope safe."""
    rig = _rig(engine_conn)
    service.reapprove_onto_clean_version(engine_conn, "rig", dry_run=False)
    engine_conn.commit()
    still = engine_conn.execute(
        "SELECT count(*) FROM generic_record WHERE schema_version_id=? AND status='retired'",
        (rig["approved"],)).fetchone()[0]
    assert still == 2, "the impostor rows were moved off the version that declares their keys"
    declared = engine_conn.execute(
        "SELECT count(*) FROM schema_version_field WHERE schema_version_id=?",
        (rig["approved"],)).fetchone()[0]
    assert declared == len(FIELDS_27) + len(PHANTOM_12), (
        "the retired version stopped declaring the fields its own rows carry")


def test_it_writes_no_revisions_because_no_value_changed(engine_conn):
    """The ruling said 17,371 revisions. It cannot: `generic_record_revision` is
    `UNIQUE (generic_record_id, source_snapshot_id, content_hash)` and nothing here changes a
    value. `SR-6`/`R-20` say the same from the other side."""
    _rig(engine_conn)
    before = engine_conn.execute("SELECT count(*) FROM generic_record_revision").fetchone()[0]
    done = service.reapprove_onto_clean_version(engine_conn, "rig", dry_run=False)
    engine_conn.commit()
    after = engine_conn.execute("SELECT count(*) FROM generic_record_revision").fetchone()[0]
    assert after == before, f"{after - before} revision(s) written for an unchanged value"
    assert done["revisions_written"] == 0, "the report claims revisions it did not write"


def test_it_refuses_when_a_dropped_field_holds_a_value_on_a_LIVE_row(engine_conn):
    """`R-45`. A field with a value on a live row is a field the site published about a live
    company, and no repair may discard it."""
    rig = _rig(engine_conn)
    engine_conn.execute(
        "UPDATE generic_record SET data_json = json_set(data_json, '$.x_phantom_00', 'real') "
        " WHERE generic_record_id = (SELECT min(generic_record_id) FROM generic_record "
        "   WHERE dataset_definition_id=? AND status='active')", (rig["dataset_id"],))
    engine_conn.commit()
    with pytest.raises(ExtractionConflict) as raised:
        service.reapprove_onto_clean_version(engine_conn, "rig", dry_run=True)
    assert "x_phantom_00" in str(raised.value)
    assert "R-45" in str(raised.value), "the refusal must name the rule it is enforcing"


def test_it_refuses_when_a_live_row_is_bound_to_the_version_being_retired(engine_conn):
    """The other half of the pair. Retiring a version a live row depends on would strand it
    exactly as the fault being repaired stranded the others."""
    rig = _rig(engine_conn, phantom_on_retired=False)
    engine_conn.execute(
        "UPDATE generic_record SET status='active' WHERE schema_version_id=?",
        (rig["approved"],))
    engine_conn.commit()
    with pytest.raises(ExtractionConflict) as raised:
        service.reapprove_onto_clean_version(engine_conn, "rig", dry_run=True)
    assert "active row" in str(raised.value)


def test_it_refuses_when_the_live_rows_carry_a_field_the_contract_never_declared(engine_conn):
    """That is a schema CHANGE, not a poisoned contract, and it belongs where `R-31` judges
    it. A repair that quietly accepted an invented key would be a second approval path."""
    rig = _rig(engine_conn)
    engine_conn.execute(
        "INSERT INTO field_definition (dataset_definition_id, field_key, original_name, "
        "data_type, is_nullable, identity_role, display_order) "
        "VALUES (?,'invented','invented','text',1,'none',99)", (rig["dataset_id"],))
    invented = int(engine_conn.execute(
        "SELECT field_definition_id FROM field_definition WHERE field_key='invented'"
    ).fetchone()[0])
    engine_conn.execute("INSERT INTO schema_version_field (schema_version_id, "
                        "field_definition_id, field_order) VALUES (?,?,99)",
                        (rig["retired"], invented))
    engine_conn.commit()
    with pytest.raises(ExtractionConflict) as raised:
        service.reapprove_onto_clean_version(engine_conn, "rig", dry_run=True)
    assert "invented" in str(raised.value) and "R-31" in str(raised.value)


def test_it_is_idempotent(engine_conn):
    """Running it twice must not open a fifth version. A repair that is not idempotent is a
    repair nobody dares run after an interruption."""
    _rig(engine_conn)
    service.reapprove_onto_clean_version(engine_conn, "rig", dry_run=False)
    engine_conn.commit()
    again = service.reapprove_onto_clean_version(engine_conn, "rig", dry_run=False)
    engine_conn.commit()
    assert again["already_correct"] is True
    assert again["records_moved"] == 0
    count = engine_conn.execute(
        "SELECT count(*) FROM dataset_schema_version").fetchone()[0]
    assert count == 3, (
        f"{count} versions exist. The rig builds two and the repair opens the third; a "
        "fourth means the second run opened one instead of recognising it was done.")


def test_an_unknown_dataset_key_is_not_found(engine_conn):
    with pytest.raises(ExtractionNotFound):
        service.reapprove_onto_clean_version(engine_conn, "no_such_dataset", dry_run=True)


# ---- the half that applies to every dataset -------------------------------------------

def test_a_page_is_never_bound_to_a_retired_version(engine_conn):
    """THE FAULT CONTINUING, rather than its leftovers.

    `_ensure_schema` looked a version up by `(dataset, schema_hash)` with no filter on
    status, so a page whose shape matched a RETIRED version joined it. Measured on
    `contractor_profiles`: a fresh 27-field page joined v2, dead since 2026-08-23.

    The lookup is exercised through its own function rather than through `approve_candidate`,
    because the point is the query, and driving it end to end would test the parser instead.
    """
    rig = _rig(engine_conn)
    hash_of_retired = engine_conn.execute(
        "SELECT schema_hash FROM dataset_schema_version WHERE schema_version_id=?",
        (rig["retired"],)).fetchone()[0]
    found = engine_conn.execute(
        "SELECT schema_version_id FROM dataset_schema_version "
        "WHERE dataset_definition_id = ? AND schema_hash = ? AND valid_to IS NULL LIMIT 1",
        (rig["dataset_id"], hash_of_retired)).fetchone()
    assert found is None, (
        "the status-aware lookup still returns a retired version for a matching shape")
    # and the source really carries that filter, so the assertion above is not testing a
    # query I wrote in the test
    # THE FIRST DRAFT OF THIS ASSERTION SURVIVED ITS OWN MUTATION, and the reason is worth
    # keeping: it looked for "AND valid_to IS NULL" anywhere in the function, and the
    # APPROVED-version lookup a few lines below also contains that clause. Removing it from
    # the hash lookup left the string present and the test green. So the statement is
    # isolated first, and both halves are asserted inside it. (The same shape survived in
    # tests/test_no_tag_is_cut_while_the_warehouse_is_ahead.py earlier the same day.)
    import inspect
    source = inspect.getsource(service._ensure_schema)
    start = source.index("SELECT schema_version_id FROM dataset_schema_version")
    statement = source[start:source.index(").fetchone()", start)]
    assert "schema_hash = ?" in statement, (
        "the isolated statement is not the hash lookup any more; re-point this assertion")
    assert "valid_to IS NULL" in statement, (
        "_ensure_schema's HASH lookup has lost its status filter, so a new page can be "
        "bound to a retired version again -- which is OP-68 and the poisoned schema both")


def test_after_the_repair_a_page_of_that_shape_resolves_to_the_new_version(engine_conn):
    """The repair and the lookup fix only work together: the new version carries the target's
    hash precisely so a page of this shape resolves to an APPROVED version."""
    rig = _rig(engine_conn)
    hash_of_retired = engine_conn.execute(
        "SELECT schema_hash FROM dataset_schema_version WHERE schema_version_id=?",
        (rig["retired"],)).fetchone()[0]
    service.reapprove_onto_clean_version(engine_conn, "rig", dry_run=False)
    engine_conn.commit()
    found = engine_conn.execute(
        "SELECT schema_version_id FROM dataset_schema_version "
        "WHERE dataset_definition_id = ? AND schema_hash = ? AND valid_to IS NULL LIMIT 1",
        (rig["dataset_id"], hash_of_retired)).fetchone()
    assert found is not None, (
        "a page carrying the live shape resolves to nothing, so it would open yet another "
        "version on every crawl")
    assert int(found["schema_version_id"]) != rig["retired"]


def test_migration_0013_lifted_the_constraint_that_forbade_this(engine_conn):
    """Two versions of one dataset may now share a shape across time, which is what lets the
    new version carry the target's hash. `UNIQUE (dataset, version_number)` stays."""
    sql = engine_conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='dataset_schema_version'").fetchone()[0]
    flat = sql.replace(" ", "").replace("\n", "")
    assert "schema_hash)" not in flat, (
        "UNIQUE (dataset_definition_id, schema_hash) is back, so the repair cannot give the "
        "new version the hash a page of that shape computes")
    assert "version_number)" in flat, (
        "UNIQUE (dataset_definition_id, version_number) is gone; a version's number is its "
        "identity and two alike make 'which v2?' unanswerable")
    index = engine_conn.execute(
        "SELECT count(*) FROM sqlite_master WHERE type='index' "
        "AND name='ux_dataset_schema_version_active'").fetchone()[0]
    assert index == 1, (
        "ux_dataset_schema_version_active is missing, so nothing stops a dataset having two "
        "approved versions — the invariant that actually matters")


def test_the_cli_pass_persists_what_it_did(tmp_path):
    """THE DEFECT THE UNIT TESTS ABOVE COULD NOT SEE, because every one of them calls
    `engine_conn.commit()` itself.

    `extract/service.py` is transaction-neutral by convention — `approve_candidate` does not
    commit either, and the caller owns the transaction so `GET /api/dry/{key}` can read the
    same function without one. `_say_reapprove_one` therefore has to commit, and it did not:
    `--repair` printed "APPLIED: v4 approved, 17,371 record(s) moved" on THREE consecutive
    runs and left the database untouched. Only running the command end to end showed it.

    So this reads back on a SECOND connection, which is the only way to tell a commit from a
    convincing return value.
    """
    from scrapex.contractors import _say_reapprove_one
    from scrapex.databases import DatabaseRegistry, EngineDatabase

    registry = DatabaseRegistry(
        EngineDatabase(tmp_path / "scrapex-engine.db"),
        pointer_file=tmp_path / "databases.json")
    registry.initialize()
    writer = registry.engine.connect()
    try:
        rig = _rig(writer)
        result = _say_reapprove_one(writer, "rig", dry_run=False)
        assert result["records_moved"] == rig["live_rows"]
    finally:
        writer.close()

    reader = registry.engine.connect()
    try:
        approved = reader.execute(
            "SELECT version_number FROM dataset_schema_version "
            " WHERE dataset_definition_id = ? AND valid_to IS NULL",
            (rig["dataset_id"],)).fetchone()
        assert approved is not None and approved["version_number"] == 4, (
            "a second connection cannot see the new approved version, so the pass reported "
            "work it never committed")
        stranded = reader.execute(
            "SELECT count(*) FROM generic_record g JOIN dataset_schema_version sv "
            "  ON sv.schema_version_id = g.schema_version_id "
            " WHERE g.dataset_definition_id = ? AND g.status = 'active' "
            "   AND sv.valid_to IS NOT NULL", (rig["dataset_id"],)).fetchone()[0]
        assert stranded == 0
    finally:
        reader.close()


def test_the_dry_cli_pass_persists_nothing(tmp_path):
    """The other direction, and it is the one that would make the pass untrustworthy."""
    from scrapex.contractors import _say_reapprove_one
    from scrapex.databases import DatabaseRegistry, EngineDatabase

    registry = DatabaseRegistry(
        EngineDatabase(tmp_path / "scrapex-engine.db"),
        pointer_file=tmp_path / "databases.json")
    registry.initialize()
    writer = registry.engine.connect()
    try:
        rig = _rig(writer)
        _say_reapprove_one(writer, "rig", dry_run=True)
    finally:
        writer.close()

    reader = registry.engine.connect()
    try:
        approved = reader.execute(
            "SELECT version_number FROM dataset_schema_version "
            " WHERE dataset_definition_id = ? AND valid_to IS NULL",
            (rig["dataset_id"],)).fetchone()
        assert approved["version_number"] == 3, (
            "the dry run committed something. A dry run that writes is worse than none, "
            "because it is the one people trust.")
    finally:
        reader.close()


def test_the_pass_is_declared_where_the_panel_reads_it():
    """`scrapex/passes.py` is the one declaration `contractors.validate`, the CLI and
    `GET /api/dry/{key}` all read — #274 built it so the command line and the panel cannot
    come to offer different sets. A pass added to the parser alone is invisible in the panel
    and refused by `validate`, which is how the first attempt exited 2."""
    from scrapex import passes

    assert "reapprove_schema" in passes.DIRECTORY_PASSES
    # `_DIRECTORY` is private on purpose: the public door is `directory_passes()`, which
    # fills the cost in. This reads the declaration itself, because the assertion is about
    # what was DECLARED and not about how it renders.
    declared = passes._DIRECTORY["reapprove_schema"]
    assert declared.network == 0, "this pass makes no request and must not claim otherwise"
    assert "generic_record" in declared.writes, (
        "the declaration must name what it writes, or the hover promises a read-only pass")
    assert "dataset_schema_version" in declared.writes
