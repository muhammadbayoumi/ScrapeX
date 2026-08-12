"""A column called `active` that is always 1 answers a question it does not know.

MEASURED ON THE OWNER'S OWN DATABASE, 2026-08-10. `source_site.active` said all
twelve sources were live. `sources.yaml` had five of them switched off —
ELBUROJ, HEIDELBERG_EG, MADAR, SIKAEGSHOP, SPARK_ESHOP.

Nothing was broken by it: the scheduler reads `entry.active` from the manifest,
so the right sources were crawled. The damage is to anyone who reads the
DATABASE — the owner with a query, an export, a future page, the Console when it
arrives. And the flag could never have been right, because it is written on
insert and nothing ever set it to 0: an inactive source is never crawled, so the
only code that touches its row never runs.

`storage.undeclared_sources` already states the rule this enforces, in its own
words: "The manifest is the definition; the warehouse is the consequence."

That same function filtered on `WHERE active = 1`, which matched every row and
so meant nothing — a clause that looked like maintenance and was not. It is
gone, and it was the wrong question anyway: a source deleted from the manifest
is undeclared whatever flag its rows carry.
"""
from __future__ import annotations

import pathlib

import os
import sqlite3
import subprocess
import sys

import pytest

from scrapex.storage import reconcile_active, undeclared_sources

ROOT = pathlib.Path(__file__).resolve().parents[1]

TWO_SOURCES = """
sources:
  - source_key: LIVEONE
    source_name: Live One
    base_url: https://live.invalid
    family: custom-json-api
    cadence: daily
    authority: shop
    active: true
    currency: EGP
    default_region: EG
    vat_mode: excl
    extract:
      - kind: product_prices
        scope: census
  - source_key: SWITCHEDOFF
    source_name: Switched Off
    base_url: https://off.invalid
    family: custom-json-api
    cadence: daily
    authority: shop
    active: false
    currency: EGP
    default_region: EG
    vat_mode: excl
    extract:
      - kind: product_prices
        scope: census
"""


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    """A real database with both sources stored as the ingest would leave them:
    present, and marked active, because that is the only value ever written."""
    manifest = tmp_path / "sources.yaml"
    manifest.write_text(TWO_SOURCES, encoding="utf-8")
    database = tmp_path / "engine.db"
    made = subprocess.run(
        [sys.executable, "-m", "scrapex.cli", "init-db", "--db", str(database)],
        env=dict(os.environ, SCRAPEX_SOURCES=str(manifest)),
        capture_output=True, text=True, timeout=300)
    assert made.returncode == 0, made.stderr

    monkeypatch.setenv("SCRAPEX_SOURCES", str(manifest))
    import scrapex.config as config
    monkeypatch.setattr(config, "MANIFEST_FILE", manifest)
    import scrapex.storage as storage
    monkeypatch.setattr(storage, "MANIFEST_FILE", manifest, raising=False)

    conn = sqlite3.connect(database)
    for key, name in (("LIVEONE", "Live One"), ("SWITCHEDOFF", "Switched Off"),
                      ("DELETEDFROMMANIFEST", "Gone")):
        conn.execute(
            "INSERT INTO source_site (source_key, source_name, source_name_ar, "
            "base_url, active) VALUES (?, ?, ?, ?, 1)",
            (key, name, name, f"https://{key.lower()}.invalid"))
    conn.commit()
    try:
        yield conn, manifest
    finally:
        conn.close()


def _stored(conn) -> dict[str, int]:
    return dict(conn.execute("SELECT source_key, active FROM source_site"))


def test_a_source_switched_off_in_the_manifest_stops_claiming_to_be_active(warehouse):
    conn, _ = warehouse
    assert _stored(conn)["SWITCHEDOFF"] == 1, "fixture is wrong: it starts as the bug"

    changed = reconcile_active(conn)

    assert _stored(conn)["SWITCHEDOFF"] == 0, (
        "the warehouse still says this source is active while sources.yaml has "
        "it switched off — anyone reading the database gets the wrong answer")
    assert changed == {"SWITCHEDOFF": False}, (
        f"only the source that actually changed should be reported: {changed}")


def test_an_active_source_is_left_alone_and_reported_as_unchanged(warehouse):
    conn, _ = warehouse
    reconcile_active(conn)

    assert _stored(conn)["LIVEONE"] == 1
    assert reconcile_active(conn) == {}, (
        "a second run reports changes it did not make, so a caller cannot tell "
        "a real reconciliation from a no-op")


def test_a_source_the_manifest_no_longer_names_is_not_quietly_switched_off(warehouse):
    """Marking it inactive would HIDE it. Its rows are `undeclared_sources`'
    business — 22% of every offer in this warehouse once belonged to a source
    deleted from the manifest, and it was found by hand two days later."""
    conn, _ = warehouse
    reconcile_active(conn)

    assert _stored(conn)["DELETEDFROMMANIFEST"] == 1, (
        "reconciliation switched off a source the manifest does not name, which "
        "buries the orphan instead of surfacing it")
    assert "DELETEDFROMMANIFEST" in undeclared_sources(conn)


def test_the_orphan_query_no_longer_depends_on_a_flag_nobody_maintains(warehouse):
    """It filtered on `active = 1`, which matched everything. After
    reconciliation a switched-off source has active = 0 — and it must STILL not
    appear as undeclared, because the manifest names it."""
    conn, _ = warehouse
    reconcile_active(conn)

    orphans = undeclared_sources(conn)
    assert "SWITCHEDOFF" not in orphans, (
        "a source the manifest names is being reported as undeclared because "
        "its active flag is 0 — the flag and the declaration are different "
        "questions")
    assert orphans == ["DELETEDFROMMANIFEST"]


def test_reconciling_against_no_manifest_changes_nothing(tmp_path, monkeypatch):
    """An unreadable manifest must not be read as "every source is off". The
    warehouse keeps what it has and something else reports the real problem."""
    import scrapex.config as config
    monkeypatch.setattr(config, "MANIFEST_FILE", tmp_path / "absent.yaml")
    monkeypatch.delenv("SCRAPEX_SOURCES", raising=False)

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE source_site (source_key TEXT, active INTEGER)")
    conn.execute("INSERT INTO source_site VALUES ('ANY', 1)")
    conn.commit()
    try:
        assert reconcile_active(conn) == {}
        assert _stored(conn)["ANY"] == 1
    finally:
        conn.close()


# ---- the warehouse follows the manifest, from every path -------------------

def test_every_manifest_reload_reconciles_the_warehouse():
    """N7 / OP-2, and the fix is the CALLERS rather than the reconciliation.

    `reconcile_active` already existed and was already correct. It had exactly
    one caller — the panel's active toggle — so the warehouse followed the
    manifest only when the owner used that one control. Every other way the
    manifest changes left the database claiming something else: an edit by hand,
    an add, a rename, a remove, or a `git checkout`.

    That last one is recorded rather than imagined. BACKLOG OP-2 measured a
    manifest edit that lived on one machine, was reverted by a checkout, and
    went unnoticed for eleven days.

    Asserted over the SOURCE because the property is "no reload is missed", and
    the way it gets broken is someone adding a sixth route that reloads the
    manifest and forgets the line. A test that exercised the five known routes
    would pass on the day the sixth arrives.
    """
    import re

    source = (ROOT / "scrapex" / "webui" / "app.py").read_text(encoding="utf-8")
    lines = source.splitlines()

    reloads = [n for n, line in enumerate(lines)
               if "app.state.manifest = load_manifest(" in line]
    assert len(reloads) >= 5, (
        f"only {len(reloads)} manifest reloads found; this test has lost track "
        "of the thing it guards")

    missing = []
    for n in reloads:
        # The definition line itself is the one inside create_app's body that
        # precedes the helper; it is followed by the startup call a few lines
        # down rather than immediately.
        window = "\n".join(lines[n:n + 6])
        if "_follow_the_manifest()" not in window:
            missing.append(n + 1)

    assert not missing, (
        f"app.py reloads the manifest at line(s) {missing} without reconciling "
        "the warehouse afterwards. The manifest is the definition and the "
        "warehouse is the consequence — a reload that skips this leaves the "
        "owner's own database saying something the manifest does not.")


def test_the_reconciliation_is_not_reachable_only_through_one_button():
    """The shape of the old defect, named so it cannot return quietly.

    One caller is not a bug in itself; one caller for a rule that describes the
    whole warehouse is. If this ever drops back to a single site, the rule has
    silently become a feature of that one control again.
    """
    source = (ROOT / "scrapex" / "webui" / "app.py").read_text(encoding="utf-8")
    calls = source.count("_follow_the_manifest()")

    # One definition, one startup call, and one per reload path.
    assert calls >= 6, (
        f"the warehouse is reconciled from {calls} place(s). It needs to happen "
        "wherever the manifest is reloaded, including at startup — that is the "
        "only path that notices a manifest changed outside the panel.")
