"""The panel's timed poll asks identity, not corruption, and the difference is 3.8 s.

WHAT HAPPENED, 2026-08-22. A `merge-warehouse` took the owner's engine database from
796 MB to 1,067 MB. `/api/health` then answered in **3.8 s**, the extension's deadline
for that call is **2,500 ms** (`extension/startup.js`, `engineHealth`), and the panel
reported:

    Installed version   Not detected
    Protocol            Not available
    Engine power        Control is not connected yet

while the engine was healthy, on 0.3.0, serving 200 on `/` and listening on
127.0.0.1:8000. Nothing was broken except the question being asked.

WHERE THE TIME WENT, measured on that file:

    PRAGMA quick_check(1)                            0.879 s
    SELECT 1 FROM pragma_foreign_key_check LIMIT 1   0.398 s

Both are O(file size), `/api/health` ran them on every poll, and the endpoint's other
work — `list_sources` at 0.203 s, `pending_migrations` at 0.004 s, `connect` at
0.005 s — was noise beside them.

AND THE SPLIT IS A RULE THIS CODEBASE ALREADY WROTE DOWN, which is why the fix is a
parameter rather than a cache: `storage.py:_warehouse_identity` says *"Integrity and
identity are deliberately separate checks."* A poll every few seconds asks whether the
file is readable and at the version this build expects. Corruption does not develop
between two polls, and scanning a gigabyte on a timer buys an answer nobody changed.

WHY A SPY AND NOT A CORRUPTED FILE. The first version of this file corrupted the
database and asserted that the cheap path still called it healthy. That is a fine
property, and building the fixture took three attempts without ever working: a
freshly-migrated database has very few pages actually IN USE, `quick_check` walks the
b-trees it can reach, and garbage written at an arbitrary offset was simply never
looked at — so it answered "ok" and the test compared two identical answers.

Recording the SQL that runs is the property itself rather than a proxy for it: the
claim is "the scan did not run", and a spy says exactly that, with no dependence on
what a given SQLite build happens to notice.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scrapex.databases import DatabaseRegistry, EngineDatabase

pytestmark = pytest.mark.docs

#: The two statements whose cost scales with the file, named so the assertions read
#: as the rule rather than as string matching.
SCANS = ("quick_check", "pragma_foreign_key_check")


@pytest.fixture()
def warehouse(tmp_path: Path) -> DatabaseRegistry:
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    return registry


def _recorded(monkeypatch, database: EngineDatabase) -> list[str]:
    """Every SQL string `database` executes from here on.

    Wraps the connection rather than the module, so it records what THIS database
    object does and nothing else — the registry, the migrations and any other
    connection in the process stay invisible.
    """
    seen: list[str] = []
    real = database.connect

    class Watched:
        def __init__(self, conn):
            self._conn = conn

        def execute(self, sql, *args, **kwargs):
            seen.append(sql)
            return self._conn.execute(sql, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._conn, name)

    monkeypatch.setattr(database, "connect", lambda: Watched(real()))
    return seen


def test_the_poll_does_not_run_either_scan(warehouse, monkeypatch):
    """THE PROPERTY. Not "it was fast" and not "it still said healthy" — that the two
    O(file size) statements are never executed on the path the panel polls."""
    seen = _recorded(monkeypatch, warehouse.engine)

    result = warehouse.engine.health(integrity=False)

    ran = [sql for sql in seen if any(scan in sql for scan in SCANS)]
    assert ran == [], (
        "the timed poll ran the corruption scan after all, which is the 3.8 s the "
        f"extension's 2,500 ms deadline could not wait for: {ran}")
    assert result.ok is True
    assert result.integrity_checked is False, (
        "the narrower claim must be visible: 'Healthy' without a scan is not the "
        "same sentence as 'Healthy' with one")


def test_the_full_check_still_runs_both(warehouse, monkeypatch):
    """The companion, and it has to be asserted separately: a fix that skipped the
    scan EVERYWHERE would pass the test above and quietly stop the Storage page
    reporting corruption — the opposite defect, and a much quieter one."""
    seen = _recorded(monkeypatch, warehouse.engine)

    result = warehouse.engine.health()

    for scan in SCANS:
        assert any(scan in sql for sql in seen), (
            f"the full check no longer runs {scan}, so nothing reports corruption")
    assert result.integrity_checked is True


def test_identity_is_still_answered_by_the_cheap_path(warehouse):
    """Skipping the scan may not skip the QUESTION. The poll exists to say whether the
    engine can serve this database, so the version and the application id — the two
    facts that decide it — must still come back."""
    poll = warehouse.engine.health(integrity=False)

    assert poll.ok is True
    assert poll.schema_version == warehouse.engine.latest_schema_version
    assert poll.application_id is not None, (
        "the poll dropped the application id, so a file of the wrong KIND would now "
        "read as healthy")


def test_a_missing_file_is_still_missing_on_the_cheap_path(warehouse):
    """The one failure a poll must never soften, because it is the common one: the
    drive holding the warehouse is not mounted."""
    warehouse.engine.path.unlink()

    poll = warehouse.engine.health(integrity=False)

    assert poll.ok is False
    assert poll.status == "Missing"


def test_the_registry_passes_the_switch_through(warehouse):
    """The endpoint calls the REGISTRY, not the database, so a switch the registry
    swallowed would leave the bug exactly where it was."""
    assert warehouse.health()["engine"]["integrity_checked"] is True
    assert warehouse.health(integrity=False)["engine"]["integrity_checked"] is False


def test_the_wide_answer_stays_the_default(warehouse):
    """Anything that asks without saying gets the full check. If this default ever
    flips, every caller silently stops checking integrity."""
    import inspect

    signature = inspect.signature(warehouse.engine.health)
    assert signature.parameters["integrity"].default is True


def test_the_endpoint_asks_for_the_cheap_one():
    """THE WIRING, pinned. Both halves can be correct while the endpoint still calls
    the expensive one — which is precisely the state this file was written in.

    Read from the source rather than timed: the cost lives in the file size, and a
    test fixture has none, so a timing assertion here would measure nothing.
    """
    source = (Path(__file__).resolve().parent.parent
              / "scrapex" / "webui" / "app.py").read_text(encoding="utf-8")
    assert "app.state.databases.health(integrity=False)" in source, (
        "/api/health no longer asks for the cheap check, so the panel's timed poll "
        "scans the whole warehouse again")
    assert source.count("databases.health(") == 1, (
        "a second call to databases.health() appeared — check whether it is also on "
        "a timed path")
