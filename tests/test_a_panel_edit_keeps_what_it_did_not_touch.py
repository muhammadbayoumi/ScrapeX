"""Renaming a source must not delete the rest of it.

This is the defect `scrapex/manifest_io.py` describes in its own words:

    THIS IS AN ORDERING HINT, NEVER THE SET OF FIELDS THAT SURVIVE. It was both
    for a year, and everything the model grew afterwards was deleted in silence
    by the first panel edit.

That warning was acted on in the WRITER. It was not true of the form-to-entry
builder in webui/app.py, which rebuilt the entry from a hand-maintained list of
seventeen names while SourceEntry had twenty-nine — so twelve fields were gone
before `update_source` was ever called, and the writer's care never saw them.

Measured on 2026-08-10, an edit that only renamed a shop destroyed: api, brand,
default_language, max_drop_pct, min_expected_rows, notes,
tax, taxonomy, unit_charter, user_agent.

`user_agent` is not cosmetic. Zid 403s a non-browser client, which is the only
reason that field exists; losing it stops the source collecting anything.
"""
from __future__ import annotations

import os
import subprocess
import sys

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from scrapex.config import SourceEntry, load_manifest  # noqa: E402

# One source carrying a value in every field a panel edit has ever dropped.
FULL_SOURCE = """
sources:
  - source_key: EVERYTHING
    source_name: Everything Shop
    source_name_ar: متجر كل شيء
    default_language: ar
    brand: EverythingBrand
    base_url: https://everything.invalid
    family: custom-json-api
    cadence: daily
    authority: shop
    active: true
    currency: EGP
    default_region: EG
    vat_mode: excl
    user_agent: Mozilla/5.0 (Zid 403s anything else)
    notes: two days of measurement live in this line
    min_expected_rows: 40
    max_drop_pct: 25.0
    robots: custom
    robots_custom:
      enforce_disallow: true
      crawl_delay_s: 9.0
    extract:
      - kind: product_prices
        scope: census
"""


@pytest.fixture
def panel(tmp_path):
    manifest = tmp_path / "sources.yaml"
    manifest.write_text(FULL_SOURCE, encoding="utf-8")
    database = tmp_path / "engine.db"
    made = subprocess.run(
        [sys.executable, "-m", "scrapex.cli", "init-db", "--db", str(database)],
        env=dict(os.environ, SCRAPEX_SOURCES=str(manifest)),
        capture_output=True, text=True, timeout=300)
    assert made.returncode == 0, made.stderr

    from scrapex.webui.app import create_app

    client = TestClient(create_app(db_path=str(database), manifest_path=str(manifest)))
    return client, manifest


def test_renaming_a_source_keeps_every_other_field(panel):
    client, manifest = panel
    before = load_manifest(manifest).get("EVERYTHING")

    answer = client.post("/api/sources/EVERYTHING/edit", json={"source_name": "Renamed"})
    assert answer.status_code == 200, answer.text

    after = load_manifest(manifest).get("EVERYTHING")
    assert after.source_name == "Renamed", "the edit did not take"

    lost = [field for field in SourceEntry.model_fields
            if field != "source_name"
            and getattr(before, field) != getattr(after, field)]
    assert not lost, (
        "renaming a shop destroyed these fields: " + ", ".join(lost) +
        ". The panel rebuilds the entry from a list of field names, so anything "
        "the list does not mention is deleted by an edit that never touched it.")


def test_the_check_covers_every_field_the_model_has(panel):
    """The guard above only bites for fields the fixture actually fills.

    Without this, adding a field to SourceEntry and forgetting to put it in
    FULL_SOURCE leaves it unprotected while the suite stays green — the same
    shape of silence as the defect itself.
    """
    _, manifest = panel
    entry = load_manifest(manifest).get("EVERYTHING")

    empty = [field for field in SourceEntry.model_fields
             if getattr(entry, field) in (None, "", [], {}, 0)]
    # These are legitimately empty: they are lists/objects this source has no
    # use for, and filling them would test the fixture rather than the panel.
    allowed = {"unit_charter", "api", "taxonomy", "tax", "fallback_families",
               "identity", "auth_required", "fold_variants", "fetcher"}
    unguarded = [field for field in empty if field not in allowed]
    assert not unguarded, (
        "FULL_SOURCE leaves these fields empty, so the test above cannot notice "
        "them being dropped: " + ", ".join(unguarded))
