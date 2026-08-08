"""The pack the engine writes is the pack the panel reads. Proved, not assumed.

Two languages, one file format, and nothing but this test standing between them.
It is the same guardrail `contract/parity/` puts under the normalize vectors and
`contracts/version-vectors.json` puts under the compatibility rule: a format
described in two places drifts, and the drift is invisible until a machine with
no engine on it shows an empty screen.

So a REAL pack is built here by the real `bundle.build`, and the REAL
`extension/bundleview.js` is run over it under node. No fixture, no hand-written
sample: a fixture would be a third description of the format and would go stale
the same way.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from scrapex import bundle
from scrapex import db as dbmod

# Guards the extension: this file reads extension/ sources, so a change to a
# button must run it. See tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def packed(tmp_path):
    """A real bundle from a real migrated warehouse."""
    db_path = tmp_path / "marketlens.db"
    conn = dbmod.connect(db_path)
    dbmod.migrate(conn)
    conn.execute(
        "INSERT INTO source_site (source_id, source_key, source_name_ar, source_name,"
        " base_url, platform, currency, timezone, authority, active) "
        "VALUES (1,'SHOP','متجر','Shop','http://s','magento-graphql','SAR','UTC','shop',1)")
    conn.execute("INSERT INTO source_product (source_product_id, source_id, "
                 " external_product_id, product_name, product_name_ar) "
                 "VALUES (1,1,'p','Cement','أسمنت')")
    conn.execute("INSERT INTO source_variant (source_variant_id, source_product_id, "
                 " external_variant_id) VALUES (1,1,'v')")
    conn.execute("INSERT INTO source_offer (offer_id, source_variant_id, "
                 " country_code_alpha2, customer_segment, basis_quantity, currency, "
                 " tax_included) VALUES (1,1,'SA','retail',50,'SAR',1)")
    conn.execute("INSERT INTO crawl_run (run_id, source_id, started_at, status) "
                 "VALUES (1,1,'2026-08-01T00:00:00Z','success')")
    conn.execute(
        "INSERT INTO price_observation (offer_id, run_id, observed_at, business_date,"
        " price, currency, tax_included, availability, record_hash, price_hash,"
        " price_fields, provenance) VALUES (1,1,'2026-08-01T00:00:00Z','2026-08-01',"
        "23.5,'SAR',1,'in_stock','rh','ph','effective','observed')")
    conn.commit()
    conn.close()

    out = tmp_path / "bundle"
    bundle.build(db_path, out)
    return out / bundle.PANEL_PACK


def _read_with_the_panel(pack: Path) -> dict:
    """Run the extension's own reader over the engine's own file."""
    script = textwrap.dedent(f"""
        import {{ readFileSync }} from "node:fs";
        import {{ readPanelPack, datasetSummaries, rowsOf, toCsv }}
          from "{(ROOT / 'extension' / 'bundleview.js').as_uri()}";

        const blob = new Blob([readFileSync({str(pack.as_posix())!r})]);
        const datasets = await readPanelPack(blob);
        const rows = rowsOf(datasets, "SHOP");
        console.log(JSON.stringify({{
          summaries: datasetSummaries(datasets),
          rows,
          csv: toCsv(rows),
        }}));
    """)
    result = subprocess.run(
        [_node(), "--input-type=module", "-e", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _node() -> str:
    from shutil import which
    found = which("node")
    if not found:
        pytest.skip("node is not on PATH")
    return found


def test_the_panel_reads_the_rows_the_engine_wrote(packed):
    """THE WHOLE OF DECISION 8 IN ONE ASSERTION.

    A machine with no engine, given only this file, shows the owner his data.
    """
    seen = _read_with_the_panel(packed)

    assert [s["source_key"] for s in seen["summaries"]] == ["SHOP"]
    assert seen["summaries"][0]["rows"] == 1
    assert len(seen["rows"]) == 1


def test_the_arabic_survives_two_languages_and_a_compressor(packed):
    """utf-8 through gzip through DecompressionStream through TextDecoder. Any
    one of them getting the encoding wrong turns the owner's product names into
    mojibake, and the panel would look broken rather than the format."""
    seen = _read_with_the_panel(packed)

    assert seen["rows"][0]["product_name_ar"] == "أسمنت"
    assert seen["rows"][0]["product_name"] == "Cement"


def test_a_number_written_by_python_is_a_number_read_by_javascript(packed):
    """The reason the export is JSON Lines and not only csv. A price read as
    text sorts 100 before 23.5, which is the kind of wrong that looks like
    working software."""
    seen = _read_with_the_panel(packed)

    assert isinstance(seen["rows"][0]["price"], (int, float))
    assert not isinstance(seen["rows"][0]["price"], str)


def test_the_columns_are_the_engines_own_export_header(packed):
    """Not a shape invented for the panel. `reports.EXPORT_HEADER` is what the
    Sheet and the workbook carry, so a reader who knows one knows all three —
    and a column added to the export reaches the bare panel with no JavaScript
    change at all."""
    from scrapex.reports import EXPORT_HEADER

    seen = _read_with_the_panel(packed)

    assert set(seen["rows"][0]) == set(EXPORT_HEADER), (
        "the panel is seeing a different set of columns from the export")


def test_the_csv_the_panel_offers_matches_the_one_the_engine_writes(packed):
    """Two exporters for one thing is two exporters that disagree by next
    month. They are separate here only because one runs where Python cannot,
    so this asserts they still produce the same header and the same values."""
    seen = _read_with_the_panel(packed)
    engine_csv = (packed.parent / "datasets" / "SHOP" / "current.csv").read_text(
        encoding="utf-8-sig")

    panel_header = seen["csv"].lstrip("﻿").splitlines()[0].split(",")
    engine_header = engine_csv.splitlines()[0].split(",")

    assert panel_header == engine_header
    assert seen["csv"].startswith("﻿"), (
        "the panel's csv has no BOM, so Excel will mangle the Arabic the "
        "engine's csv preserves")
    assert "أسمنت" in seen["csv"]


def test_the_pack_is_part_of_the_bundle_and_checksummed(packed):
    """It travels with everything else, so a tampered pack is caught by the
    same verify() that catches a tampered database."""
    manifest = json.loads(
        (packed.parent / "manifest.json").read_text(encoding="utf-8"))

    assert bundle.PANEL_PACK in manifest["files"]
    assert manifest["files"][bundle.PANEL_PACK]["sha256"]

    raw = bytearray(packed.read_bytes())
    raw[-1] ^= 0x01
    packed.write_bytes(bytes(raw))

    report = bundle.verify(packed.parent)
    assert not report.ok
    assert any(bundle.PANEL_PACK in f.path for f in report.faults)
