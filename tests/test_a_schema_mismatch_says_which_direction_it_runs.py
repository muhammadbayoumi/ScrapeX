"""A schema mismatch has two directions, and one message fitted neither.

MEASURED ON THE OWNER'S MACHINE, 2026-09-07. A source checkout at 0.4.9 met a
warehouse another build had migrated to schema v19. The engine refused, which is
right — but the Database page then told him:

    engine database is at schema v19, expected v18;
    run database initialization and retry

His warehouse is **1,986 MB**. Initialisation cannot make a v18 build read a v19
schema; it is the remedy for a missing or unmarked file. That sentence, offered
there, is the most expensive wrong instruction this product has.

AND THE RIGHT ANSWER WAS ALREADY IN THE FILE, forty lines up. The health path
asks which direction the mismatch runs and gives each direction its own
instruction; its own comment says why — "telling the owner to restore a backup
sends them to destroy good data over a one-command upgrade". The open path asked
the same question with a bare `!=` and answered for neither direction.

So this file owns the four statements that incident produced:

1. a database AHEAD of the build is never told to initialise;
2. a database BEHIND it names the control that exists, on the screen it is on;
3. migrating stamps WHO migrated it, in the same transaction as the version;
4. a warehouse written before that stamp existed still gets a true sentence.

Integration, against the real `db/engine/schema.sql` and the real migration
stream — a fixture schema cannot go out of step with the build, which is the
whole subject.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.databases.domain import (
    SCHEMA_WRITTEN_AT_KEY,
    SCHEMA_WRITTEN_BY_KEY,
    DatabaseMigrationError,
    schema_ahead_detail,
)


def warehouse(tmp_path: Path) -> DatabaseRegistry:
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    return registry


def set_version(path: Path, version: int) -> None:
    """Move the file's schema version without touching anything else.

    THE ONLY HONEST WAY TO BUILD THIS FIXTURE. A database written by a genuinely
    newer build cannot exist in a test — the newer build is the thing that does
    not exist yet — and the version is exactly what every reader keys on. So the
    number is moved and the tables are left alone, which is the state a real
    later build produces for every column this test looks at.
    """
    conn = sqlite3.connect(path)
    try:
        conn.execute(f"PRAGMA user_version = {version}")
        conn.commit()
    finally:
        conn.close()


def meta(path: Path) -> dict[str, str]:
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        return dict(conn.execute("SELECT key, value FROM scrapex_meta").fetchall())
    finally:
        conn.close()


# ---- 1. the direction that cost him an afternoon -----------------------------

def test_a_database_newer_than_the_build_is_never_told_to_initialise(tmp_path):
    """THE DEFECT, REPRODUCED THROUGH THE PATH HE HIT.

    Not the health card — that one was already right — but `connect()`, which is
    what the Database page reports and what refused to open his warehouse.
    """
    registry = warehouse(tmp_path)
    ahead = registry.engine.latest_schema_version + 1
    set_version(registry.engine.path, ahead)

    with pytest.raises(DatabaseMigrationError) as raised:
        registry.engine.connect()
    detail = str(raised.value)

    assert "initializ" not in detail.lower() and "initialis" not in detail.lower(), (
        "a database whose only fault is being NEWER is still being offered "
        f"initialisation, which cannot help and can destroy: {detail!r}")
    assert "Update ScrapeX" in detail, (
        f"the refusal does not name the remedy: {detail!r}")
    assert "do not downgrade the database" in detail, (
        "the refusal does not warn against the one action that would lose data: "
        f"{detail!r}")
    assert f"v{ahead}" in detail and f"v{registry.engine.latest_schema_version}" in detail, (
        f"the two versions are not both named, so he cannot tell how far: {detail!r}")


def test_the_health_card_and_the_open_path_give_the_same_sentence(tmp_path):
    """ONE PIECE OF KNOWLEDGE, ONE SET OF WORDS.

    The two lived forty lines apart and disagreed; the point of the repair is not
    that both are now right but that there is one place to be right IN. If they
    drift again, this fails — which the previous arrangement could not.
    """
    registry = warehouse(tmp_path)
    ahead = registry.engine.latest_schema_version + 1
    set_version(registry.engine.path, ahead)

    health = registry.engine.health()
    with pytest.raises(DatabaseMigrationError) as raised:
        registry.engine.connect()

    assert health.status == "Needs a newer ScrapeX", health.status
    assert health.action == str(raised.value), (
        "the health card and the open refusal describe the same state in "
        f"different words:\n  card: {health.detail!r}\n  open: {str(raised.value)!r}")


# ---- 2. the other direction names a control that exists ----------------------

def test_a_database_behind_the_build_names_the_screen_the_control_is_on(tmp_path):
    """`#runtime-upgrade` MOVED AND THE SENTENCE DID NOT.

    It was on Settings; #679 gave the Database page its own screen and took the
    control with it. The health detail went on naming Settings — a true-sounding
    instruction that sends him to the wrong screen, which is the same class of
    defect as the one above and was found in the same read.
    """
    registry = warehouse(tmp_path)
    behind = registry.engine.latest_schema_version - 1
    assert behind >= 1, "this stream has too few migrations for the test to mean anything"
    set_version(registry.engine.path, behind)

    detail = registry.engine.health().action
    assert "Database screen" in detail, (
        f"the remedy does not say where the control is: {detail!r}")
    assert "Settings screen" not in detail, (
        "the sentence still sends him to Settings, where the Upgrade control has "
        f"not been since #679: {detail!r}")


# ---- 3. the warehouse records who migrated it --------------------------------

def test_migrating_records_which_build_did_it_and_when(tmp_path):
    """THE FACT THAT TURNS THE NEXT INCIDENT INTO A SENTENCE.

    Diagnosing his took reading the migration list on `origin/main`, finding the
    commit that added `0019`, and comparing it against the checkout the engine
    resolves to. The file itself knew none of that.
    """
    registry = warehouse(tmp_path)
    rows = meta(registry.engine.path)

    assert SCHEMA_WRITTEN_BY_KEY in rows, (
        "the warehouse does not record which build wrote its schema, so a "
        "refusal can only say what it CANNOT read")
    assert SCHEMA_WRITTEN_AT_KEY in rows
    assert rows[SCHEMA_WRITTEN_BY_KEY], "the build is recorded as an empty string"
    assert rows[SCHEMA_WRITTEN_AT_KEY].endswith("Z"), (
        f"the instant is not the UTC form `scrapex_meta` stores: "
        f"{rows[SCHEMA_WRITTEN_AT_KEY]!r}")


def test_the_recorded_build_reaches_the_refusal(tmp_path):
    """Recording it is not the point; the sentence carrying it is."""
    registry = warehouse(tmp_path)
    written_by = meta(registry.engine.path)[SCHEMA_WRITTEN_BY_KEY]
    set_version(registry.engine.path, registry.engine.latest_schema_version + 1)

    with pytest.raises(DatabaseMigrationError) as raised:
        registry.engine.connect()
    assert written_by in str(raised.value), (
        f"the build that wrote the schema is recorded and not reported: "
        f"{str(raised.value)!r}")


# ---- 4. and a warehouse older than the stamp still gets a true sentence ------

def test_a_warehouse_written_before_the_stamp_existed_says_nothing_false(tmp_path):
    """HIS OWN 1,986 MB FILE IS THIS CASE, and it will be for every user's.

    The keys are new; every warehouse that exists today lacks them. The sentence
    must degrade to exactly what it said before rather than inventing a
    provenance or printing an empty one.
    """
    registry = warehouse(tmp_path)
    conn = sqlite3.connect(registry.engine.path)
    try:
        conn.execute("DELETE FROM scrapex_meta WHERE key IN (?, ?)",
                     (SCHEMA_WRITTEN_BY_KEY, SCHEMA_WRITTEN_AT_KEY))
        conn.commit()
    finally:
        conn.close()
    set_version(registry.engine.path, registry.engine.latest_schema_version + 1)

    with pytest.raises(DatabaseMigrationError) as raised:
        registry.engine.connect()
    detail = str(raised.value)
    assert "written by ScrapeX" not in detail, (
        f"a warehouse with no recorded build claims one anyway: {detail!r}")
    assert "Update ScrapeX" in detail and "do not downgrade" in detail, (
        f"the sentence lost its remedy when the provenance was absent: {detail!r}")


def test_the_sentence_is_the_same_words_wherever_it_is_built():
    """A unit check on the one function, so a caller cannot quietly reword it.

    Both callers pass through `schema_ahead_detail`; asserting its output here
    means the two integration tests above are checking WIRING rather than
    prose, and a reworded sentence fails in one obvious place.
    """
    bare = schema_ahead_detail(19, 18)
    assert bare.startswith("This database was written by a later version "
                           "(schema v19; this build reads v18).")
    assert bare.endswith("Update ScrapeX and retry, and do not downgrade the database.")
    assert "written by ScrapeX" not in bare

    named = schema_ahead_detail(19, 18, "0.4.11", "2026-09-07T10:00:00Z")
    assert "Schema v19 was written by ScrapeX 0.4.11 on 2026-09-07T10:00:00Z." in named
    # The remedy survives the extra clause rather than being displaced by it.
    assert named.endswith("Update ScrapeX and retry, and do not downgrade the database.")

    # A build recorded without an instant still names the build.
    assert "written by ScrapeX 0.4.11." in schema_ahead_detail(19, 18, "0.4.11")
