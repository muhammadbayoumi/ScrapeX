"""A migration that loses rows and says nothing is worse than one that refuses.

FOUND ON THE OWNER'S MACHINE, 2026-08-11. `~/.scrapex/databases.json` still said
`"mode": "split"`, so every engine command refused to start — which is why
nothing was listening on 127.0.0.1:8000 all day and why the side panel's engine
check returned ERR_CONNECTION_REFUSED in a loop.

The refusal message told the reader to run `init-db`. That command creates a NEW
database and applies migrations to it; it has never read `marketlens.db`.
Following it on that installation would have produced an empty warehouse beside
110 MB of prices — 88,286 price observations, 122,509 change events — that
nothing would ever open again. The files would all still be there, exactly as the
message promised, and the data would be gone from the product's point of view.

So the property under test is not "the carry-over works". It is that the pointer
NEVER moves unless every row arrived, because the pointer moving is what makes
the new database the real one.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scrapex.databases.carry_over import carry_over, read_split_pointer
from scrapex.databases.registry import DatabasePointerError


def _make_source(path: Path, rows: int, *, extra_table: bool = False,
                 prefix: str = "key") -> None:
    """An old-layout database with a table the new schema also has."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE scrapex_meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.executemany("INSERT INTO scrapex_meta VALUES (?, ?)",
                     [(f"{prefix}-{n}", f"value-{n}") for n in range(rows)])
    # A REAL DATA TABLE beside the ledger, because the guard under test must be
    # exercised on something the destination does NOT own.
    #
    # Its columns and constraints are copied from the shipped schema, read out of
    # the owner's own database rather than retyped from memory. The first two
    # attempts were retyped and both were wrong: `source_key`, `source_kind` and
    # `recorded_at` are all NOT NULL, and `(currency, as_of, source_key)` carries
    # a UNIQUE index, and `source_kind` carries a CHECK limiting it to
    # 'provider' or 'shop'. Every row was dropped and the guard reported 45 read,
    # 0 written — the guard working, on a fixture that was not. The CHECK was the
    # last one found, and only by attempting one insert and reading the error
    # instead of reading PRAGMA table_info, which does not show CHECKs at all.
    #
    # That is worth keeping in mind beyond this test: INSERT OR IGNORE swallows a
    # CONSTRAINT failure exactly as quietly as it swallows a duplicate. A row
    # that violates a NOT NULL in the new schema vanishes with no error at all,
    # and the row count is the only thing that notices.
    conn.execute("""CREATE TABLE currency_rate (
        currency_rate_id INTEGER PRIMARY KEY,
        currency    TEXT NOT NULL,
        per_usd     REAL NOT NULL,
        as_of       TEXT NOT NULL,
        source_key  TEXT NOT NULL,
        source_kind TEXT NOT NULL CHECK (source_kind IN ('provider', 'shop')),
        recorded_at TEXT NOT NULL,
        UNIQUE (currency, as_of, source_key))""")
    # THE PRIMARY KEY IS GIVEN EXPLICITLY, and disjoint per file. Left to
    # autoincrement, both old databases number their rows from 1 and the two
    # ranges collide the moment they are carried into one table -- INSERT OR
    # IGNORE then drops the second file's rows without a word. That is a real
    # limitation of carry_over on any table present in BOTH files, and it is
    # exactly what the row-count guard caught here: 45 read, 40 written, pointer
    # not moved. It did not bite on the owner's own data only because no table
    # of theirs lives in both files.
    base = 0 if prefix == "key" else 100_000
    conn.executemany(
        "INSERT INTO currency_rate (currency_rate_id, currency, per_usd, as_of, "
        "source_key, source_kind, recorded_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(base + n, f"{prefix[:3].upper()}{n:03d}", 1.0 + n, "2026-08-11",
          prefix, "provider", "2026-08-11T00:00:00Z") for n in range(rows)])
    if extra_table:
        conn.execute("CREATE TABLE forgotten_domain (id INTEGER PRIMARY KEY, note TEXT)")
        conn.executemany("INSERT INTO forgotten_domain (note) VALUES (?)",
                         [(f"row {n}",) for n in range(7)])
    conn.commit()
    conn.close()


@pytest.fixture
def split(tmp_path, monkeypatch):
    """A pointer that names two real old files, and a destination that does not
    exist yet — which is the state every affected installation is in."""
    marketlens = tmp_path / "marketlens" / "marketlens.db"
    general = tmp_path / "general" / "general.db"
    _make_source(marketlens, 40, extra_table=True)
    _make_source(general, 5, prefix="general")

    pointer = tmp_path / "databases.json"
    pointer.write_text(json.dumps({
        "format_version": 1, "mode": "split",
        "marketlens_path": str(marketlens), "general_path": str(general),
        "legacy_path": None,
    }), encoding="utf-8")

    destination = tmp_path / "engine" / "scrapex-engine.db"
    import scrapex.databases.carry_over as module
    monkeypatch.setattr(module, "DEFAULT_ENGINE_PATH", destination)
    return pointer, destination, marketlens, general


def _rows(path: Path, table: str = "scrapex_meta") -> int:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
    finally:
        conn.close()


def test_every_row_arrives_and_only_then_does_the_pointer_move(split):
    pointer, destination, _, _ = split

    report = carry_over(read_split_pointer(pointer))

    assert report["ok"], report
    # The report's own figure, not a raw row count: the destination carries its
    # own schema rows from initialize(), and counting those as carried is
    # exactly the mistake the baseline in carry_over() was added to fix.
    carried = report["tables"]["scrapex_meta"]
    assert carried["written"] == carried["distinct"] == 45, (
        "rows went missing between the old files and the new database, and the "
        f"carry-over reported success anyway: {carried}")
    moved = json.loads(pointer.read_text(encoding="utf-8"))
    assert moved["mode"] == "single"
    assert moved["engine_path"] == str(destination)


def test_the_old_files_are_never_touched(split):
    """They are the only copy until the new database is proved complete."""
    pointer, _, marketlens, general = split
    before = (marketlens.read_bytes(), general.read_bytes())

    carry_over(read_split_pointer(pointer))

    assert (marketlens.read_bytes(), general.read_bytes()) == before, (
        "an old database was modified; it was supposed to be opened read-only")


def test_a_dry_run_writes_nothing_and_leaves_the_pointer_alone(split):
    pointer, _, _, _ = split

    report = carry_over(read_split_pointer(pointer), dry_run=True)

    assert report["ok"] is False, "a dry run must never report itself as done"
    # The file exists — the destination has to be created to be inspected — but
    # not one carried row is in it.
    assert report["tables"]["scrapex_meta"]["written"] == 0
    assert json.loads(pointer.read_text(encoding="utf-8"))["mode"] == "split"


def test_a_table_the_new_schema_lost_is_named_rather_than_dropped_in_silence(split):
    """`forgotten_domain` exists only in the old file. Carrying nothing is the
    right behaviour; carrying nothing QUIETLY is how a year of prices disappears
    behind a success message."""
    pointer, _, _, _ = split

    report = carry_over(read_split_pointer(pointer))

    left = {entry["table"]: entry for entry in report["skipped"]}
    assert "forgotten_domain" in left, (
        "a table full of rows was left behind and never mentioned")
    assert left["forgotten_domain"]["rows"] == 7
    assert left["forgotten_domain"]["why"]


def test_running_it_twice_is_safe_and_does_not_double_the_rows(split):
    """An owner who is unsure whether the first run finished will run it again."""
    pointer, destination, _, _ = split
    carry_over(read_split_pointer(pointer))
    first = _rows(destination)

    # The pointer now says "single", so the plan has to be rebuilt by hand —
    # which is itself the guard in the next test.
    from scrapex.databases.carry_over import CarryOverPlan
    plan = CarryOverPlan(priced=None, general=None,
                         destination=destination, pointer=pointer)
    carry_over(plan)

    assert _rows(destination) == first, "a second run duplicated rows"


def test_a_pointer_that_already_says_single_is_refused_by_name(split):
    pointer, _, _, _ = split
    carry_over(read_split_pointer(pointer))

    with pytest.raises(DatabasePointerError, match="already points at a single"):
        read_split_pointer(pointer)


def test_a_missing_old_file_stops_everything_before_a_single_row_moves(split):
    """Half a carry-over that reports success is the failure this whole module
    exists to prevent."""
    pointer, destination, marketlens, _ = split
    marketlens.unlink()

    with pytest.raises(DatabasePointerError, match="not there"):
        read_split_pointer(pointer)
    assert not destination.exists(), "a database was created despite the refusal"
    assert json.loads(pointer.read_text(encoding="utf-8"))["mode"] == "split"


def test_a_short_count_refuses_and_leaves_the_pointer_where_it_was(split, monkeypatch):
    """THE ONE THAT MATTERS. If rows do not arrive, the installation must keep
    refusing to start rather than start on top of an incomplete warehouse."""
    pointer, _, _, _ = split
    plan = read_split_pointer(pointer)

    import scrapex.databases.carry_over as module
    real_count = module._row_count

    def short(conn, table):
        # `currency_rate`, NOT `scrapex_meta`. The latter is a LEDGER the
        # destination owns, so a shortfall there is expected and excused by
        # design; using it here would have made this test pass for a reason
        # that has nothing to do with what it guards.
        value = real_count(conn, table)
        return value - 1 if table == "currency_rate" and value > 3 else value

    monkeypatch.setattr(module, "_row_count", short)
    report = carry_over(plan)

    assert report["short"], "a short table was not detected"
    assert report["ok"] is False
    assert json.loads(pointer.read_text(encoding="utf-8"))["mode"] == "split", (
        "the pointer moved even though rows were missing — the installation "
        "would now start and serve an incomplete warehouse with nothing saying so")



def test_a_ledger_the_destination_owns_does_not_block_the_pointer(split):
    """The fix that came out of the owner's real run, guarded.

    `database_migration` and `scrapex_meta` are LEDGERS: the destination writes
    its own schema version and migration record when it is created, so some of
    the old rows are duplicates and INSERT OR IGNORE drops them. On the owner's
    machine that shortfall — 62 -> 56 and 26 -> 21 — stopped a carry-over in
    which every table of DATA had arrived exactly. The refusal was right in its
    logic and wrong in its verdict.

    Removing the exemption must fail this test. Without it the exemption is a
    line nobody is holding to account, which is how it would quietly widen later
    into "and these other tables too".
    """
    pointer, destination, _, _ = split

    # Put a row in the destination's ledger that the sources also carry, so the
    # ledger is genuinely short after the carry while the data table is not.
    from scrapex.databases.domain import EngineDatabase
    destination.parent.mkdir(parents=True, exist_ok=True)
    EngineDatabase(destination).initialize()
    conn = sqlite3.connect(destination)
    conn.execute("INSERT OR REPLACE INTO scrapex_meta (key, value) VALUES (?, ?)",
                 ("key-0", "written by the destination, not carried"))
    conn.commit()
    conn.close()

    report = carry_over(read_split_pointer(pointer))

    assert report["ledgers"], (
        "the ledger shortfall was not reported at all; it has to be visible "
        "even though it is excused")
    assert report["ledgers"][0]["table"] == "scrapex_meta"
    assert report["ledgers"][0]["why"], "excused with no reason recorded"
    assert not report["short"], f"a ledger blocked the pointer: {report['short']}"
    assert report["ok"], report
    assert json.loads(pointer.read_text(encoding="utf-8"))["mode"] == "single"
