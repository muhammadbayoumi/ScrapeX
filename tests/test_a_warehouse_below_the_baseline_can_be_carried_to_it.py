"""`R-84` locked v11..v16 out and no release can let them in. This is the way back.

`OP-134` measured that no published engine ever carried the chain past v10, so the
refusal's own advice — *"bring it to v17 with the last release that still carried those
migrations"* — names an artefact that does not exist. `tools/carry_a_warehouse_to_the_baseline.py`
is the artefact, and these are the four properties that make it safe to point at his data:

  1. the chain is recovered from history and PROVED against `squashed-from.json`;
  2. the engine's own runner applies it, not a second implementation;
  3. a rehearsal never opens the original for writing;
  4. and the SHIPPED build has the last word — `health().ok` or the tool fails.

THE FIXTURE STOPS AT v13 ON PURPOSE. It is inside the locked range and it is below
`0014`, the registry merge that REBUILDS `source_site` — so the row planted here has to
survive a table rebuild rather than a column addition, which is the migration most likely
to lose data if the walk were done by hand.
"""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex.databases.domain import EngineDatabase, Migration

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import carry_a_warehouse_to_the_baseline as tool  # noqa: E402

STOP = 13


def _chain_is_reachable() -> bool:
    try:
        subprocess.run(["git", "cat-file", "-e", f"{tool.PRE_SQUASH}^{{commit}}"],
                       cwd=ROOT, capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _chain_is_reachable(),
    reason=f"{tool.PRE_SQUASH} is not in this checkout, so the absorbed chain cannot "
           "be recovered — a shallow clone, not a defect")


@pytest.fixture()
def below_the_baseline(tmp_path, monkeypatch):
    """A warehouse at v13 with a row of his own kind in it."""
    chain_baseline, chain_migrations = tool.recover_chain(tmp_path / "chain")
    path = tmp_path / "scrapex-engine.db"

    monkeypatch.setattr(dbmod, "SCHEMA_FILE", chain_baseline)
    monkeypatch.setattr(dbmod, "MIGRATIONS_DIR", chain_migrations)
    whole = tuple(Migration(n, p) for n, p in dbmod._migration_files())
    database = EngineDatabase(path)
    database._migrations = tuple(m for m in whole if m.number <= STOP)
    database.initialize()
    monkeypatch.undo()

    conn = sqlite3.connect(str(path))
    try:
        have = {row[1] for row in conn.execute("PRAGMA table_info(source_site)")}
        wanted = {"source_key": "muqawil_org", "source_name": "muqawil.org",
                  "source_name_ar": "مقاول", "base_url": "https://muqawil.org/",
                  "platform": "directory", "currency": "SAR",
                  "default_tax_mode": "incl", "authority": "official"}
        use = {k: v for k, v in wanted.items() if k in have}
        conn.execute(f"INSERT INTO source_site ({', '.join(use)}) VALUES "
                     f"({', '.join('?' for _ in use)})", tuple(use.values()))
        conn.commit()
    finally:
        conn.close()
    return path


def _version(path: Path) -> int:
    conn = sqlite3.connect(str(path))
    try:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()


def test_every_absorbed_migration_is_recoverable_and_proves_it_is_itself(tmp_path):
    """THE FOUNDATION. The record names each absorbed file WITH ITS DIGEST, so a file
    pulled out of history is checked rather than trusted because a commit was named.
    Measured on this repository: 17 of 17."""
    baseline, migrations = tool.recover_chain(tmp_path / "chain")

    assert baseline.is_file()
    recovered = sorted(p.name for p in migrations.iterdir())
    assert len(recovered) == 16, recovered
    assert recovered[0].startswith("0002") and recovered[-1].startswith("0017")


def test_a_tampered_chain_is_refused_rather_than_applied(tmp_path, monkeypatch):
    """A digest that does not match means the file is not the one that was absorbed,
    and applying it would put a schema in the warehouse that no baseline describes."""
    written = tool.RECORD.read_text(encoding="utf-8")
    record = written.replace(json.loads(written)["absorbed"][5][2], "0" * 64)
    forged = tmp_path / "squashed-from.json"
    forged.write_text(record, encoding="utf-8")
    monkeypatch.setattr(tool, "RECORD", forged)

    with pytest.raises(SystemExit, match="does not match the record"):
        tool.recover_chain(tmp_path / "chain")


def test_it_carries_a_locked_warehouse_to_the_baseline_and_keeps_the_rows(
        below_the_baseline):
    """The whole point, and `health()` is the shipped build's own verdict rather than
    this tool's."""
    assert _version(below_the_baseline) == STOP
    refused = EngineDatabase(below_the_baseline).health()
    assert not refused.ok and "no upgrade path" in refused.action

    reached = tool.carry(below_the_baseline)

    baseline = dbmod.declared_schema_version(dbmod.SCHEMA_FILE)
    assert reached == baseline
    assert _version(below_the_baseline) == baseline
    settled = EngineDatabase(below_the_baseline).health()
    assert settled.ok, f"{settled.status}: {settled.action}"

    conn = sqlite3.connect(str(below_the_baseline))
    try:
        keys = [row[0] for row in conn.execute("SELECT source_key FROM source_site")]
        assert conn.execute("PRAGMA foreign_key_check").fetchone() is None
    finally:
        conn.close()
    assert "muqawil_org" in keys, (
        "the carry lost his row, and migration 0014 REBUILDS that table — which is "
        "why the fixture plants it below 0014 rather than above it")


def test_it_backs_up_before_it_writes_and_names_the_copy(below_the_baseline, capsys):
    """There is no path through here that advances a schema without a restorable copy
    beside it, which is the rule `dbupgrade` states and this reuses."""
    tool.carry(below_the_baseline)

    copies = list(below_the_baseline.parent.glob("*pre-carry*.backup.db"))
    assert len(copies) == 1, copies
    assert copies[0].stat().st_size > 0
    assert copies[0].name in capsys.readouterr().out, "it copied in silence"


def test_a_rehearsal_never_opens_the_original_for_writing(below_the_baseline, capsys):
    """`--apply` is the only thing that touches his file. And the rehearsal is a REAL
    run on a real copy — a simulation would prove the tool's reasoning rather than the
    migrations' effect on his rows."""
    before = below_the_baseline.stat().st_mtime_ns

    assert tool.main([str(below_the_baseline)]) == 0

    assert below_the_baseline.stat().st_mtime_ns == before
    assert _version(below_the_baseline) == STOP
    said = capsys.readouterr().out
    assert "REHEARSAL ONLY" in said
    assert f"v{STOP} -> v{dbmod.declared_schema_version(dbmod.SCHEMA_FILE)}" in said


def test_a_warehouse_already_at_the_baseline_is_left_alone(tmp_path, capsys):
    """It exists for the locked range and says so instead of doing something."""
    path = tmp_path / "scrapex-engine.db"
    EngineDatabase(path).initialize()
    before = _version(path)

    assert tool.carry(path) == before
    assert "nothing to carry" in capsys.readouterr().out
    assert not list(tmp_path.glob("*pre-carry*")), "it copied a file it did not touch"


def test_a_file_that_is_not_an_engine_warehouse_is_refused(tmp_path):
    """`application_id` is what a warehouse says it is, and a rescue that guessed would
    replay sixteen migrations over somebody else's database."""
    path = tmp_path / "not-ours.db"
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("CREATE TABLE t (x)")
        conn.execute("PRAGMA user_version = 5")
        conn.commit()
    finally:
        conn.close()

    with pytest.raises(SystemExit, match="not the engine's"):
        tool.carry(path)
