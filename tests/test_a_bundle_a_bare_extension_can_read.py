"""A backup that restores a machine AND feeds an extension with no engine.

Decision 8: a fresh machine, signed in, with no engine installed, shows the data
and exports it. The expensive reading of that was "run SQLite in the browser",
and spike 2 measured it dead: OPFS loses WAL, an access handle is exclusive, the
service worker cannot write, and `wa-sqlite` is 70-208x slower than Python on
the Data page's own query, with a fast VFS that cannot open an existing database
at all.

So the backup is a BUNDLE — the `.db` for a machine that installs the engine,
a plain per-dataset export for one that has not, and a manifest with a checksum
for every file. Viewing and exporting is read-only, so no database is needed in
a browser at all.

MEASURED ON THE OWNER'S OWN WAREHOUSE, 2026-08-06:

    warehouse.db   116 MB          built in 20.6 s
    exports         93 MB          64 jsonl + 29 csv, 12 datasets, 71 files
    ---------------------
    bundle         209 MB
    zipped          33 MB          6.3x smaller, in one second

Decision 12 makes the upload frequency a setting because "a daily full upload
that changes nothing is not free". 209 MB would have made that a necessity;
33 MB makes it a preference.
"""

from __future__ import annotations

import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

from scrapex import bundle
from scrapex import db as dbmod


@pytest.fixture()
def warehouse(tmp_path):
    """A small real warehouse: two sources, one of them never crawled.

    Built through the real migration stream, because a bundle of a hand-made
    schema would prove nothing about the one the owner has.
    """
    path = tmp_path / "marketlens.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    conn.execute(
        "INSERT INTO source_site (source_id, source_key, source_name_ar, source_name,"
        " base_url, platform, currency, timezone, authority, active) "
        "VALUES (1,'SHOP','متجر','Shop','http://s','magento-graphql','SAR','UTC','shop',1)")
    conn.execute(
        "INSERT INTO source_site (source_id, source_key, source_name_ar, source_name,"
        " base_url, platform, currency, timezone, authority, active) "
        "VALUES (2,'NEVER','لم يُزحف','Never crawled','http://n','shopify-json',"
        "'SAR','UTC','shop',1)")
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
    return path


def test_a_bundle_carries_the_database_the_export_and_a_manifest(warehouse, tmp_path):
    """The three parts, and each is for a different reader."""
    out = tmp_path / "bundle"

    report = bundle.build(warehouse, out)

    assert report.ok, [f"{f.path}: {f.problem}" for f in report.faults]
    assert (out / "warehouse.db").is_file(), "nothing for a machine to restore"
    assert (out / "datasets" / "SHOP" / "current.jsonl").is_file()
    assert (out / "datasets" / "SHOP" / "current.csv").is_file()
    assert (out / "manifest.json").is_file()

    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["bundle_format"] == bundle.BUNDLE_FORMAT
    assert manifest["engine_version"]
    assert manifest["created_at"].endswith("Z")


def test_a_source_that_was_never_crawled_is_recorded_and_not_dropped(warehouse, tmp_path):
    """"Configured, never run" is a state the Library page already names, and a
    bundle that simply omitted it would make "nothing yet" indistinguishable
    from "missing" on the machine restoring it."""
    out = tmp_path / "bundle"

    report = bundle.build(warehouse, out)

    assert "NEVER" in report.datasets, "the never-crawled source vanished"
    assert report.datasets["NEVER"]["current"] == 0
    assert (out / "datasets" / "NEVER" / "current.jsonl").is_file()


def test_the_rows_are_readable_with_no_database_and_no_engine(warehouse, tmp_path):
    """DECISION 8, on the reading side, and deliberately this short.

    No SQL, no schema, no SQLite. The panel does the same thing in JavaScript
    over the same file — which is the whole reason the export exists.
    """
    out = tmp_path / "bundle"
    bundle.build(warehouse, out)

    rows = bundle.read_dataset(out, "SHOP")

    assert len(rows) == 1
    # The column names are reports.EXPORT_HEADER's, not this test's invention:
    # the bundle writes what the Sheet and the workbook already carry, so a
    # reader that knows one knows all three.
    assert rows[0]["product_name_ar"] == "أسمنت", (
        "the Arabic name did not survive the round trip")
    assert rows[0]["product_name"] == "Cement"
    # A number stays a number. This is why the export is JSON Lines and not only
    # CSV: a panel reading "23.5" as a string sorts 100 before 23.5.
    assert isinstance(rows[0]["price"], (int, float))


def test_the_csv_opens_in_excel_with_its_arabic_intact(warehouse, tmp_path):
    """utf-8-sig, because Excel guesses the encoding of a plain UTF-8 file wrong
    and the owner's data is half Arabic."""
    out = tmp_path / "bundle"
    bundle.build(warehouse, out)

    raw = (out / "datasets" / "SHOP" / "current.csv").read_bytes()

    assert raw.startswith(b"\xef\xbb\xbf"), "no BOM, so Excel will mangle the Arabic"
    assert "أسمنت" in raw.decode("utf-8-sig")


# ---- the checks that make `latest.json` mean something -----------------------

def test_a_file_that_changed_after_the_bundle_was_sealed_is_caught(warehouse, tmp_path):
    """The whole reason for checksums. A backup nobody verified is a backup
    discovered to be empty on the day it is needed."""
    out = tmp_path / "bundle"
    bundle.build(warehouse, out)

    (out / "datasets" / "SHOP" / "current.csv").write_text("tampered", encoding="utf-8")

    report = bundle.verify(out)
    assert not report.ok
    assert any("current.csv" in f.path for f in report.faults)


def test_a_byte_changed_without_changing_the_size_is_still_caught(warehouse, tmp_path):
    """THE CASE ONLY THE CHECKSUM CAN SEE, and the reason it is a separate test.

    The tamper above rewrote the file and changed its length, so the byte count
    caught it first and the checksum comparison was never exercised — proved by
    mutation: deleting the sha256 comparison left the whole suite green. Bit rot
    and a half-flushed write do not change the length.
    """
    out = tmp_path / "bundle"
    bundle.build(warehouse, out)
    target = out / "datasets" / "SHOP" / "current.csv"

    raw = bytearray(target.read_bytes())
    raw[-1] ^= 0x01                      # one bit, same length
    target.write_bytes(bytes(raw))

    report = bundle.verify(out)
    assert not report.ok
    assert any("checksum" in f.problem for f in report.faults), (
        [f"{f.path}: {f.problem}" for f in report.faults])


def test_a_missing_file_is_caught_by_name(warehouse, tmp_path):
    out = tmp_path / "bundle"
    bundle.build(warehouse, out)

    (out / "warehouse.db").unlink()

    report = bundle.verify(out)
    assert not report.ok
    assert any(f.path == "warehouse.db" and "missing" in f.problem
               for f in report.faults)


def test_a_file_nobody_named_is_as_wrong_as_one_that_vanished(warehouse, tmp_path):
    """Something wrote into this bundle after it was sealed. A verifier that
    only checked the files it expected would call that bundle good."""
    out = tmp_path / "bundle"
    bundle.build(warehouse, out)

    (out / "datasets" / "SHOP" / "extra.jsonl").write_text("{}\n", encoding="utf-8")

    report = bundle.verify(out)
    assert not report.ok
    assert any("extra.jsonl" in f.path for f in report.faults)


def test_a_truncated_export_is_caught_by_its_row_count(warehouse, tmp_path):
    """A truncated file has a perfectly valid checksum FOR ITS TRUNCATED SELF
    once someone rewrites the manifest. Counting the rows back is the check
    that does not depend on the manifest being honest about the bytes."""
    out = tmp_path / "bundle"
    bundle.build(warehouse, out)

    jsonl = out / "datasets" / "SHOP" / "current.jsonl"
    jsonl.write_text("", encoding="utf-8")
    # Rewrite the manifest so the byte and hash checks pass and only the row
    # count can catch it.
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"]["datasets/SHOP/current.jsonl"] = {
        "bytes": 0, "sha256": bundle.sha256_of(jsonl)}
    (out / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    report = bundle.verify(out)
    assert not report.ok
    assert any("rows" in f.problem for f in report.faults)


def test_a_bundle_from_a_later_format_is_refused_whole(tmp_path):
    """Not half-read. A newer bundle may have moved anything, and guessing
    which parts are still compatible is how a restore silently loses a
    dataset."""
    out = tmp_path / "bundle"
    out.mkdir()
    (out / "manifest.json").write_text(json.dumps(
        {"bundle_format": bundle.BUNDLE_FORMAT + 1, "files": {}}), encoding="utf-8")

    report = bundle.verify(out)
    assert not report.ok
    assert "bundle_format" in report.faults[0].problem


def test_every_fault_is_reported_and_not_only_the_first(warehouse, tmp_path):
    """A caller deciding whether to publish this as `latest` needs the whole
    picture; stopping at the first bad file hides how bad it is."""
    out = tmp_path / "bundle"
    bundle.build(warehouse, out)

    (out / "warehouse.db").unlink()
    (out / "datasets" / "SHOP" / "current.csv").write_text("x", encoding="utf-8")

    report = bundle.verify(out)
    assert len(report.faults) >= 2, [f.path for f in report.faults]


# ---- what actually travels ---------------------------------------------------

def test_packing_refuses_a_bundle_that_does_not_verify(warehouse, tmp_path):
    """`latest.json` naming only a validated bundle is worth nothing if the
    validation can be skipped by packing first and checking afterwards."""
    out = tmp_path / "bundle"
    bundle.build(warehouse, out)
    (out / "warehouse.db").unlink()

    with pytest.raises(ValueError, match="does not verify"):
        bundle.pack(out, tmp_path / "b.zip")


def test_a_packed_bundle_unpacks_and_still_verifies(warehouse, tmp_path):
    """The round trip, which is the only thing that proves a restore works."""
    out = tmp_path / "bundle"
    built = bundle.build(warehouse, out)
    archive = tmp_path / "b.zip"

    described = bundle.pack(out, archive)
    restored = bundle.unpack(archive, tmp_path / "restored")

    assert described["bytes"] < built.bytes, "compression made it bigger"
    assert described["sha256"]
    assert restored.ok, [f"{f.path}: {f.problem}" for f in restored.faults]
    assert restored.datasets == built.datasets
    assert bundle.read_dataset(
        tmp_path / "restored", "SHOP")[0]["product_name_ar"] == "أسمنت"


def test_an_archive_entry_that_escapes_the_folder_is_refused(tmp_path):
    """A bundle arrives from Drive, which is outside this machine.

    `../../autorun` is the oldest trick there is, and Python's `extractall` has
    historically obliged. Every name is resolved against the destination.
    """
    archive = tmp_path / "evil.zip"
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr("manifest.json", "{}")
        out.writestr("../escaped.txt", "outside")

    with pytest.raises(ValueError, match="escapes the bundle"):
        bundle.unpack(archive, tmp_path / "dest")

    assert not (tmp_path / "escaped.txt").exists(), "the file was written anyway"


def test_the_database_in_the_bundle_is_a_real_openable_warehouse(warehouse, tmp_path):
    """The .db is the artefact a machine restores FROM, so it has to be a
    database and not a copy of a half-written page. sqlite3's own backup API is
    what makes that true even while something is writing."""
    out = tmp_path / "bundle"
    bundle.build(warehouse, out)

    conn = sqlite3.connect(f"file:{out / 'warehouse.db'}?mode=ro", uri=True)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == 1
    finally:
        conn.close()
