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

import re
import shutil
from pathlib import Path

import pytest

from scrapex.databases import DatabaseRegistry, EngineDatabase

#: BOTH MARKS. `docs` because it guards a documented measurement, and
#: `extension` because the number it is written against -- `engineHealth`
#: at 2,500 ms in `extension/startup.js` -- lives on the extension side.
#: Change that deadline and this file's premise changes, so it has to run
#: on an extension-only change too.
pytestmark = [pytest.mark.docs, pytest.mark.extension]

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


# ---- the source count rides the poll at the cost of one statement (#1764) ------------
#
# MEASURED 2026-10-20 on his 2,475,528,192-byte warehouse, 17 sources. `/api/health`
# answered in 1.92-2.21 s against the 2,500 ms deadline, so the panel said "Couldn't
# reach the engine" about an engine that was up. On a copy of that file, at normal
# priority, the endpoint cost 0.506 s and `len(list_sources(conn))` was 0.444 s of it:
# nine statements a source, 154 in all, to produce one number -- how many sources are
# registered. Each summary counts that source's observations, and that count is about
# 19 ms a source even for a source with none. His engine pays roughly four times the
# CPU a fresh process pays for the same statements (#1767), which turned 0.5 s into
# 2.1 s.
#
# SO THE PROPERTY IS THE WORK, NOT THE TIME. A fixture has no observations to count
# and every timing on it would pass; the statements the poll runs are what grew with
# each source, so they are what is pinned.

#: The tables a source's SUMMARY reads (`reports.source_summary`). Every one grows
#: with what was collected, so a poll statement naming one is work that grows too.
SUMMARY_TABLES = ("source_product", "source_variant", "price_observation",
                  "source_variant_match", "v_material_price_tracking", "crawl_run")


@pytest.fixture()
def polled(tmp_path: Path, warehouse: DatabaseRegistry):
    """The real app on the registry path -- the one his engine takes, where
    `read_conn()` is `databases.engine.connect()` -- with no worker thread."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from scrapex.config import MANIFEST_FILE
    from scrapex.webui.app import create_app

    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(databases=warehouse, manifest_path=manifest))


def _register(warehouse: DatabaseRegistry, keys) -> None:
    warehouse.engine.write(lambda conn: conn.executemany(
        "INSERT INTO source_site (source_key, source_name, base_url, platform) "
        "VALUES (?, ?, ?, 'custom')",
        [(key, key, f"https://{key.lower()}.example") for key in keys]))


def _traced(monkeypatch, database: EngineDatabase) -> list[str]:
    """Every statement SQLite runs on a connection `database` hands out from here on.

    `set_trace_callback` rather than a wrapper around `execute`: it is SQLite's own
    record, so a statement reached through a cursor, `executemany` or a script is
    counted too. What `connect()` runs to verify the file is before the callback and
    is left out -- it is one per connection and does not grow with anything.
    """
    seen: list[str] = []
    real = database.connect

    def traced():
        conn = real()
        conn.set_trace_callback(seen.append)
        return conn

    monkeypatch.setattr(database, "connect", traced)
    return seen


def _poll(client) -> dict:
    response = client.get("/api/health")
    assert response.status_code == 200, response.text
    return response.json()


def test_the_poll_does_the_same_work_for_twelve_sources_as_for_two(polled, warehouse,
                                                                   monkeypatch):
    """THE PROPERTY. Ten more sources must cost the poll nothing: before #1764 they
    cost it ninety statements, nine per source."""
    seen = _traced(monkeypatch, warehouse.engine)
    _register(warehouse, [f"FEW{i}" for i in range(2)])
    seen.clear()                     # the INSERTs went through `connect()` too
    _poll(polled)
    few = list(seen)

    _register(warehouse, [f"MORE{i}" for i in range(10)])
    seen.clear()
    _poll(polled)

    assert len(seen) == len(few), (
        f"the poll ran {len(few)} statements with two added sources and {len(seen)} "
        "with twelve, so its cost grows with every source registered -- which is how "
        "it reached 2.1 s against the panel's 2.5 s deadline on his 17")


def test_the_poll_reads_no_table_a_source_summary_reads(polled, warehouse, monkeypatch):
    """The cost of a summary is the size of what was collected, which a fixture does
    not have; naming the tables is how a test without the data sees the work."""
    _register(warehouse, ["SUMMARISED"])
    seen = _traced(monkeypatch, warehouse.engine)

    _poll(polled)

    named = [sql for sql in seen
             if any(re.search(rf"\b{table}\b", sql) for table in SUMMARY_TABLES)]
    assert named == [], (
        "the timed poll read a source's collected data, which grows with every crawl "
        f"and every source: {named}")


def test_the_count_is_still_every_registered_source(polled, warehouse):
    """Cheaper may not mean different: the poll's number is the one `list_sources`
    gives, the sources the overview lists."""
    from scrapex.reports import list_sources

    _register(warehouse, [f"COUNTED{i}" for i in range(3)])

    body = _poll(polled)

    conn = warehouse.engine.connect()
    try:
        listed = len(list_sources(conn))
        registered = conn.execute("SELECT COUNT(*) FROM source_site").fetchone()[0]
    finally:
        conn.close()
    assert registered >= 3
    assert body["sources_with_data"] == listed == registered


def test_a_missing_warehouse_still_answers_with_no_sources(polled, warehouse):
    """Health must survive the thing it reports on (`api_health`'s first comment): the
    cheaper count keeps the same refusal to fail with the database."""
    for leftover in warehouse.engine.path.parent.glob(warehouse.engine.path.name + "*"):
        leftover.unlink()

    body = _poll(polled)

    assert body["sources_with_data"] == 0
    assert body["databases"]["ok"] is False
