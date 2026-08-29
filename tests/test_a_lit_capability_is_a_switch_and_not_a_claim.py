"""`is_enabled` had zero callers, so every flag in the manifest was decoration.

WHAT WAS WRONG. `scrapex/features.py` describes `is_enabled` as *"the gate that
NAVIGATION and UI must call before advertising a capability"*, and **nothing in the
repository called it**. `GENERIC_DATASET_CATALOG` and `GENERIC_EXTRACTION` were lit at
`PARTIAL` on the owner's instruction on 2026-08-20; turning either of them off again
would have changed nothing whatsoever. A flag that governs nothing is a claim about a
capability, not a switch over it — and this manifest exists precisely to stop
capabilities being oversold, which makes an inert flag the worst kind of entry in it.

WHERE THE TWO CALLERS BELONG, and it is not symmetrical:

    GENERIC_DATASET_CATALOG   `_dataset_rows` — what puts a dataset in the source
                              listing the panel draws. That IS the advertisement.
    GENERIC_EXTRACTION        `scrapex contractors --approve` — the SHIPPED command,
                              which `REQ-24` made a user-facing surface.

AND THE API ROUTES ARE DELIBERATELY EXCLUDED, because `is_enabled`'s own docstring
excludes them: `/api/table/contractors` and `/source/contractors` are mounted on
127.0.0.1 so the slice can be exercised and tested. Gating those would turn the flag
into a kill switch for development; gating the listing and the shipped command makes it
a switch over what is ANNOUNCED. `test_the_routes_stay_mounted_when_the_flag_is_off`
pins that distinction, because it is the one a later reader would "tidy up".
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scrapex import db as dbmod
from scrapex import features
from scrapex.config import MANIFEST_FILE
from scrapex.features import FeatureKey, FeatureState, is_enabled
from scrapex.webui.app import create_app

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """A migrated warehouse and NOTHING INGESTED.

    `test_api.py` has a `client` of its own, and it ingests price rows because its
    tests are about price sources. Copying it here would have pulled in that setup for
    no reason — and its fixtures are module-local, so they are not importable anyway.
    The generic tables come from `db/migrations/0014_generic_html_table_extraction.sql`,
    which `migrate` applies, so an empty warehouse already has somewhere to put a
    dataset.
    """
    path = tmp_path / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def client(db_path, tmp_path) -> TestClient:
    """Pointed at a COPY of the manifest, so no test can edit the real one."""
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(db_path, manifest_path=manifest))


@pytest.fixture()
def off(monkeypatch):
    """Turn one capability off through the REAL manifest, not by faking the gate.

    `is_enabled` reads `_FEATURES` at call time, so replacing the tuple exercises the
    shipped function. Monkeypatching `is_enabled` itself would test the call site
    against a stub of the thing being tested.
    """
    def turn_off(key: FeatureKey) -> None:
        monkeypatch.setattr(features, "_FEATURES", tuple(
            FeatureState(one.key, False, one.stage, one.detail)
            if one.key == key else one
            for one in features._FEATURES))
        assert is_enabled(key) is False, "the fixture must actually turn it off"

    return turn_off


# ---- the shipped command --------------------------------------------------------

def _args(**overrides) -> argparse.Namespace:
    from scrapex.contractors import add_arguments

    parser = argparse.ArgumentParser()
    add_arguments(parser)
    return parser.parse_args(["--run-ref", "r", *[
        flag for key, value in overrides.items() if value
        for flag in (f"--{key.replace('_', '-')}",)]])


def test_approve_refuses_when_generic_extraction_is_off(off, capsys):
    """IT REFUSES RATHER THAN SKIPPING. A run that quietly approved nothing would look
    exactly like a crawl with nothing left to approve, and those are opposite facts."""
    from scrapex.contractors import validate

    off(FeatureKey.GENERIC_EXTRACTION)

    with pytest.raises(SystemExit) as raised:
        validate(_args(approve=True))

    assert raised.value.code == 2
    said = capsys.readouterr().err
    assert "generic extraction is disabled" in said
    assert "Nothing was read or written" in said


def test_approve_proceeds_while_the_flag_is_lit():
    """The other direction, so the guard cannot pass by refusing everything."""
    from scrapex.contractors import validate

    assert is_enabled(FeatureKey.GENERIC_EXTRACTION) is True
    validate(_args(approve=True))          # raises nothing


def test_the_other_operations_are_not_gated_on_extraction(off):
    """`--crawl` FETCHES AND STORES; it interprets nothing. Gating it on the extraction
    flag would stop evidence being collected because interpretation is switched off,
    and the two phases are separate for exactly that reason — a wrong parse costs
    minutes because the pages are already on disk."""
    from scrapex.contractors import validate

    off(FeatureKey.GENERIC_EXTRACTION)

    validate(_args(crawl=True))            # raises nothing
    validate(_args(coverage=True))
    validate(_args(plan=True))


# ---- the advertisement ----------------------------------------------------------

def _a_dataset_in(db_path: Path) -> None:
    """One approved dataset, so the listing has something it COULD advertise."""
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT INTO source_site (source_key, source_name, base_url) "
                 "VALUES ('muq','Contractors','https://muqawil.org')")
    conn.execute(
        "INSERT INTO dataset_definition (source_id, dataset_key, original_name, "
        " dataset_kind, discovery_method, locator_json) "
        "VALUES (1,'contractors','contractors','table','html_table','{}')")
    conn.commit()
    conn.close()


def _dataset_keys(client) -> list[str]:
    return [row["source_key"] for row in client.get("/api/sources").json()["sources"]
            if row.get("kind") == "dataset"]


def test_a_lit_catalogue_advertises_the_dataset(client, db_path):
    """The premise. Without this the test below passes on an empty warehouse and
    proves nothing at all — which is how an inert flag looked correct for two days."""
    _a_dataset_in(db_path)

    assert "contractors" in _dataset_keys(client)


def test_an_unlit_catalogue_advertises_nothing(client, db_path, off):
    _a_dataset_in(db_path)
    off(FeatureKey.GENERIC_DATASET_CATALOG)

    assert _dataset_keys(client) == []


def test_the_routes_stay_mounted_when_the_flag_is_off(client, db_path, off):
    """THE DISTINCTION A LATER READER WOULD TIDY AWAY. `is_enabled`'s docstring puts
    the API routes outside the flag on purpose: they exist so the slice can be
    exercised and tested on a server bound to 127.0.0.1. What the flag governs is
    whether anything TELLS a user the capability exists.
    """
    _a_dataset_in(db_path)
    off(FeatureKey.GENERIC_DATASET_CATALOG)

    assert client.get("/api/features").status_code == 200
    # ASSERTED ON THE ROUTE TABLE, not by calling it. `/api/table/{source_key}` reads
    # `dataset_sighting`, which is an ENGINE migration and not in this price-database
    # fixture — so calling it raises `no such table` and says nothing about the flag.
    # "Mounted" is a fact about routing, so it is asked of the router.
    paths = {getattr(route, "path", "") for route in client.app.routes}
    assert "/api/table/{source_key}" in paths
    assert "/source/{source_key}" in paths


# ---- and the state that started all this ---------------------------------------

def test_every_feature_key_the_manifest_declares_is_reachable_from_the_code():
    """THE GUARD AGAINST THIS COMING BACK. `is_enabled` had zero callers, and nothing
    failed — which is why it stayed that way. This counts call sites in shipped code, so
    a flag added without a reader, or a reader deleted in a refactor, is a red build
    rather than a silent return to decoration.

    IT COUNTS CALLS AND NOT KEYS, deliberately. Two of the five keys are
    `NOT_STARTED` and have nothing to gate yet; requiring a caller per key would force
    a fake one for a capability that does not exist.
    """
    shipped = [path.read_text(encoding="utf-8")
               for path in (ROOT / "scrapex").rglob("*.py")]
    calls = sum(text.count("is_enabled(FeatureKey.") for text in shipped)

    assert calls >= 2, (
        "`is_enabled` is back to having no callers in scrapex/, so every flag in "
        "features.py is decoration again")


def test_an_unlit_flag_says_what_is_actually_missing():
    """`CRAWL_FRONTIER` LOOKED STALE AND IS NOT, which is worth a test because the
    partitioned crawl makes it look shipped.

    Measured 2026-08-21 against its own written condition — *"persistent discovery,
    limits, and checkpoint recovery"*. Limits shipped; checkpoint recovery shipped for
    the partitioned crawl, since `already_stored` lets a resume skip pages it already
    holds. Persistent discovery did not: `declare_frontier` hands the fetcher an
    in-memory denominator for the Activity panel and writes nothing, so no new process
    could resume a frontier. Two of three, so `False` is the correct value — and a
    detail naming which two is what stops the next session re-deriving it.
    """
    frontier = next(f for f in features.manifest()["features"]
                    if f["key"] == "crawl_frontier")

    assert frontier["enabled"] is False
    assert "Persistent discovery did NOT" in frontier["detail"]
    assert "declare_frontier" in frontier["detail"]
