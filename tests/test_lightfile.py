"""The light file is what the routes answer, written from a copy, readable one part at a time.

#1199. A reader with no engine (#1200) will draw the Data page from this file, so
every part must be the route's own body, byte for byte. Each test below holds that, or
one property the reader relies on: one part inflates alone, two writes agree, the copy
is never written, and one table that fails costs that table and nothing else.

THE FIXTURE IS ONE WAREHOUSE HOLDING EVERY SHAPE THE WRITER MUST CARRY: a price source
with two variants at one price (so it folds) and an Arabic brand (so `ensure_ascii`
would show), ingested twice so its cards carry a change; muqawil's profile dataset
with an activity tree; and a second site holding the same `dataset_key`, which only
`site_key` tells apart (`dataset_definition` is `UNIQUE (source_id, dataset_key)`).
"""
from __future__ import annotations

import gzip
import json
import shutil
import sqlite3
import subprocess
import textwrap
import zlib
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from scrapex import archive, bundle, features, lightfile, reports
from scrapex import db as dbmod
from scrapex.config import MANIFEST_FILE
from scrapex.extract import service
from scrapex.features import FeatureKey, FeatureState
from scrapex.ingest import ingest_payloads
from scrapex.webui.app import create_app
from tests.test_an_activity_filter_reads_what_is_stored import (
    _dataset,
    _hold,
    _record,
    _tree,
)
from tests.test_ingest import make_entry, make_payload, one_row

ROOT = Path(__file__).resolve().parent.parent
SOURCE = "ELSEWEDYSHOP"
DATASET = "contractor_profiles"


def _second_site(conn) -> int:
    """Another site holding `contractor_profiles`, with one record of its own."""
    source = conn.execute(
        "INSERT INTO source_site (source_key, source_name, base_url) "
        "VALUES ('other_org', 'Another directory', 'https://other.example/') "
        "RETURNING source_id").fetchone()[0]
    definition = conn.execute(
        "INSERT INTO dataset_definition "
        "  (source_id, dataset_key, original_name, dataset_kind, discovery_method) "
        "VALUES (?, ?, 'Profiles elsewhere', 'table', 'repeating_dom') "
        "RETURNING dataset_definition_id", (source, DATASET)).fetchone()[0]
    version = conn.execute(
        "INSERT INTO dataset_schema_version "
        "  (dataset_definition_id, version_number, schema_hash) "
        "VALUES (?, 1, 'hash-other') RETURNING schema_version_id",
        (definition,)).fetchone()[0]
    field = conn.execute(
        "INSERT INTO field_definition (dataset_definition_id, field_key, "
        "  original_name, data_type, identity_role) "
        "VALUES (?, 'contractor_id', 'Contractor id', 'text', 'key_part') "
        "RETURNING field_definition_id", (definition,)).fetchone()[0]
    conn.execute(
        "INSERT INTO schema_version_field (schema_version_id, field_definition_id, "
        "  field_order) VALUES (?, ?, 1)", (version, field))
    conn.commit()
    _record(conn, definition, version, "9001")
    return int(source)


def _variants(price: str, scraped_at: str):
    return make_payload([
        one_row(external_variant_id="5001", external_sku="SKU1", brand_ar="السويدي",
                price=price, price_before=price),
        one_row(external_variant_id="5002", external_sku="SKU2", brand_ar="السويدي",
                price=price, price_before=price),
    ], scraped_at=scraped_at)


@pytest.fixture()
def db_path(tmp_path) -> Path:
    path = tmp_path / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    ingest_payloads(conn, make_entry(), [_variants("1,200.00", "2026-07-16T10:00:00Z")])
    ingest_payloads(conn, make_entry(), [_variants("1,100.00", "2026-07-20T10:00:00Z")])
    # As tests/test_api_fields.py stores one: the table a card's details read, so each
    # card is compared with a detail in it rather than an empty list.
    conn.execute(
        "INSERT INTO source_product_attribute (source_product_id, attribute_code, "
        " attribute_label, raw_value, attribute_group, lang, is_site_filter) "
        "SELECT source_product_id, 'cable_gauge', 'Cable gauge', '2.5 mm', "
        "'Specifications', 'en', 0 FROM source_product")
    conn.commit()
    definition, version = _dataset(conn)
    nodes = _tree(conn)
    leaf_only = _record(conn, definition, version, "7001")
    _hold(conn, leaf_only, nodes["leaf"])
    whole_path = _record(conn, definition, version, "7002")
    for node in ("root", "branch", "leaf", "other"):
        _hold(conn, whole_path, nodes[node])
    _record(conn, definition, version, "7003")
    _second_site(conn)
    conn.close()
    return path


@pytest.fixture()
def client(db_path, tmp_path) -> TestClient:
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(db_path, manifest_path=manifest))


def _write(client, db_path, out_dir: Path, name="scrapex-bundle-20260101-000000",
           copy: Path | None = None) -> lightfile.LightReport:
    """The writer over a backup-API copy, as `_build_one_bundle` runs it."""
    out_dir.mkdir(parents=True, exist_ok=True)
    copy = copy or archive.backup_database(db_path, tag="light")
    return lightfile.write(copy, out_dir / name,
                           price_sources=client.app.state.manifest.sources)


def _part(report: lightfile.LightReport, described: dict) -> bytes:
    data = report.parts_path.read_bytes()
    return gzip.decompress(data[described["offset"]:described["offset"] + described["bytes"]])


def _table(report, kind: str, site_key: str, key: str) -> dict:
    found = [one for one in report.index["tables"]
             if (one["kind"], one["site_key"], one["key"]) == (kind, site_key, key)]
    assert len(found) == 1, (kind, site_key, key, report.index["tables"])
    return found[0]


# ---- every part is the route's own body ----------------------------------------

def test_every_part_is_the_body_its_route_answers(client, db_path, tmp_path):
    """If this fails, the page a reader opens offline is not the page the engine shows."""
    report = _write(client, db_path, tmp_path / "out")

    assert report.faults == []
    price = _table(report, "price", SOURCE, SOURCE)
    assert set(price["parts"]) == {"table", "table-folded", "cards"}, (
        "the fixture no longer folds, so the folded part is untested")
    assert _part(report, price["parts"]["table"]) == \
        client.get(f"/api/table/{SOURCE}?fold=0").content
    assert _part(report, price["parts"]["table-folded"]) == \
        client.get(f"/api/table/{SOURCE}?fold=1").content

    rows = json.loads(_part(report, price["parts"]["table"]))["rows"]
    cards = _part(report, price["parts"]["cards"]).splitlines()
    assert len(cards) == len(rows) == price["parts"]["cards"]["lines"] == 2
    for row, line in zip(rows, cards, strict=True):
        assert line == client.get(f"/api/offer/{SOURCE}/{row['offer_id']}").content
    assert json.loads(cards[0])["changes"], "the cards carry no change to compare"
    assert all(json.loads(line)["details"] for line in cards), (
        "a card carries no detail to compare")
    assert "السويدي".encode() in _part(report, price["parts"]["table"])

    for site in ("muqawil_org", "other_org"):
        dataset = _table(report, "dataset", site, DATASET)
        assert _part(report, dataset["parts"]["table"]) == \
            client.get(f"/api/table/{DATASET}?site_key={site}").content, site
    muqawil = _table(report, "dataset", "muqawil_org", DATASET)
    assert _part(report, muqawil["parts"]["taxonomy"]) == \
        client.get(f"/api/taxonomy/{DATASET}").content
    assert json.loads(_part(report, muqawil["parts"]["table"]))["total"] == 3
    assert json.loads(_part(
        report, _table(report, "dataset", "other_org", DATASET)["parts"]["table"])
    )["total"] == 1, "site_key did not tell the two datasets apart"


def test_a_nodes_records_are_what_the_filter_keeps(client, db_path, tmp_path):
    report = _write(client, db_path, tmp_path / "out")
    muqawil = _table(report, "dataset", "muqawil_org", DATASET)
    selected = json.loads(_part(report, muqawil["parts"]["selected"]))

    conn = dbmod.connect(db_path)
    try:
        for node, records in selected.items():
            kept = service.dataset_table_payload(
                conn, DATASET, site_key="muqawil_org", nodes=[int(node)])
            assert records == sorted(
                row[service.OBSERVED_RECORD_ID] for row in kept["rows"]), node
    finally:
        conn.close()
    assert any(len(records) == 2 for records in selected.values()), (
        "no node reaches both records, so descent is untested")
    # EVERY NODE THE TREE OFFERS, the undeclared one included: a node the copy does
    # not answer is a filter the offline page offers and cannot apply.
    tree = json.loads(_part(report, muqawil["parts"]["taxonomy"]))
    offered = {node["node_id"] for group in tree["groups"] for node in group["nodes"]}
    offered |= {group["undeclared"]["node_id"] for group in tree["groups"]
                if group["undeclared"]}
    assert {int(node) for node in selected} == offered
    assert any(group["undeclared"] for group in tree["groups"]), (
        "the fixture has no undeclared node, so its answer is untested")


def test_the_index_describes_the_parts_file_and_each_part(client, db_path, tmp_path):
    copy = archive.backup_database(db_path, tag="light")
    report = _write(client, db_path, tmp_path / "out", copy=copy)
    index = json.loads(report.index_path.read_text(encoding="utf-8"))

    assert index == report.index
    assert index["light_format"] == lightfile.LIGHT_FORMAT
    assert index["parts_file"] == {
        "name": report.parts_path.name, "bytes": report.parts_path.stat().st_size,
        "sha256": bundle.sha256_of(report.parts_path)}
    for table in index["tables"]:
        for described in table["parts"].values():
            inflated = _part(report, described)
            assert len(inflated) == described["raw_bytes"]
    # ASKED OF THE PARSED INDEX, by name. JSON doubles every backslash in a Windows
    # path, so searching the raw text for `str(path)` can never match one.
    said = json.dumps(index, ensure_ascii=False)
    for name in (copy.name, copy.parent.name):
        assert name not in said, (
            f"{name!r} is in the index; it travels to Drive and must carry names, "
            "never paths")


def test_the_members_tile_the_file_with_nothing_between_them(client, db_path, tmp_path):
    report = _write(client, db_path, tmp_path / "out")
    members = sorted((d["offset"], d["bytes"]) for t in report.index["tables"]
                     for d in t["parts"].values())

    end = 0
    for offset, size in members:
        assert offset == end, "bytes in the file that no part names"
        end = offset + size
    assert end == report.parts_path.stat().st_size


# ---- a browser reads one part alone ---------------------------------------------

def _node() -> str:
    found = shutil.which("node")
    if not found:
        pytest.skip("node is not on PATH")
    return found


def test_a_browser_inflates_one_part_without_the_others(client, db_path, tmp_path):
    """The reader #1200 needs: `Blob.slice` and `DecompressionStream`, nothing else."""
    report = _write(client, db_path, tmp_path / "out")
    cards = _table(report, "price", SOURCE, SOURCE)["parts"]["cards"]
    script = textwrap.dedent(f"""
        import {{ readFileSync }} from "node:fs";
        const blob = new Blob([readFileSync({report.parts_path.as_posix()!r})]);
        const part = blob.slice({cards["offset"]}, {cards["offset"] + cards["bytes"]});
        const text = await new Response(
          part.stream().pipeThrough(new DecompressionStream("gzip"))).text();
        process.stdout.write(text);
    """)
    run = subprocess.run([_node(), "--input-type=module", "-e", script],
                         capture_output=True, encoding="utf-8", errors="replace")

    assert run.returncode == 0, run.stderr
    assert run.stdout.encode("utf-8") == _part(report, cards)


# ---- deterministic, read-only, and safe on any path ---------------------------------

def test_two_writes_of_one_copy_are_the_same_bytes(client, db_path, tmp_path):
    copy = archive.backup_database(db_path, tag="light")
    first = _write(client, db_path, tmp_path / "one", copy=copy)
    second = _write(client, db_path, tmp_path / "two", copy=copy)

    assert first.parts_path.read_bytes() == second.parts_path.read_bytes()


def test_no_member_carries_a_time_or_a_name(client, db_path, tmp_path):
    """Two writes inside one second agree whatever a header says, so the test above
    cannot see a clock in one. RFC 1952: byte 3 is FLG, which names no file when 0,
    and bytes 4-7 are MTIME."""
    report = _write(client, db_path, tmp_path / "out")
    data = report.parts_path.read_bytes()

    for table in report.index["tables"]:
        for name, described in table["parts"].items():
            header = data[described["offset"]:described["offset"] + 8]
            assert header == b"\x1f\x8b\x08\x00\x00\x00\x00\x00", (
                table["key"], name, header.hex())


def test_each_card_is_compressed_before_the_next_is_built(
        client, db_path, tmp_path, monkeypatch):
    """STREAMED: 19,218 cards on his warehouse, so the writer never holds a source's
    cards. Collecting them before compressing passes every other test here."""
    fed: list[bytes] = []
    real_compressobj = zlib.compressobj

    class Watched:
        def __init__(self, *args):
            self._real = real_compressobj(*args)

        def compress(self, data):
            fed.append(data)
            return self._real.compress(data)

        def flush(self, *args):
            return self._real.flush(*args)

    real_card = reports.offer_card
    compressed_before: list[int] = []

    def card(conn, source_key, offer_id):
        compressed_before.append(sum(1 for chunk in fed if chunk.endswith(b"\n")))
        return real_card(conn, source_key, offer_id)

    monkeypatch.setattr(zlib, "compressobj", Watched)
    monkeypatch.setattr(reports, "offer_card", card)
    report = _write(client, db_path, tmp_path / "out")

    assert report.faults == []
    assert compressed_before == [0, 1], (
        "a card was built before the previous one was compressed")


def test_the_copy_is_never_written(client, db_path, tmp_path, monkeypatch):
    copy = archive.backup_database(db_path, tag="light")
    before = bundle.sha256_of(copy)
    _write(client, db_path, tmp_path / "out", copy=copy)
    assert bundle.sha256_of(copy) == before

    # And a reader that tries to write is refused by the connection itself.
    real = reports.offer_card

    def writing(conn, source_key, offer_id):
        conn.execute("CREATE TABLE intruder (x)")
        return real(conn, source_key, offer_id)

    monkeypatch.setattr(reports, "offer_card", writing)
    report = _write(client, db_path, tmp_path / "again", copy=copy)
    assert [f["key"] for f in report.faults] == [SOURCE]
    assert "readonly" in report.faults[0]["problem"]


def test_a_folder_named_with_hash_and_percent_is_read_and_left_alone(
        client, db_path, tmp_path):
    """`#` and `%` in a URI path are a fragment and an escape: `storage.row_counts`."""
    folder = tmp_path / "Drive #2 50%"
    folder.mkdir()
    copy = folder / "warehouse.db"
    shutil.copy2(archive.backup_database(db_path, tag="light"), copy)

    report = _write(client, db_path, tmp_path / "out", copy=copy)

    assert _table(report, "price", SOURCE, SOURCE)["rows"] == 2
    assert sorted(p.name for p in tmp_path.iterdir() if p.name.startswith("Drive")) == [
        "Drive #2 50%"], "a database was created at a truncated name"


# ---- what fails, fails alone ----------------------------------------------------------

def test_one_table_that_fails_is_a_fault_and_the_rest_are_whole(
        client, db_path, tmp_path, monkeypatch):
    real = reports.offer_card
    calls = []

    def second_fails(conn, source_key, offer_id):
        calls.append(offer_id)
        if len(calls) == 2:
            raise RuntimeError("the second card")
        return real(conn, source_key, offer_id)

    monkeypatch.setattr(reports, "offer_card", second_fails)
    report = _write(client, db_path, tmp_path / "out")

    assert report.faults == [{"kind": "price", "site_key": SOURCE, "key": SOURCE,
                              "problem": "RuntimeError: the second card"}]
    assert all(t["key"] != SOURCE for t in report.index["tables"])
    members = sorted((d["offset"], d["bytes"]) for t in report.index["tables"]
                     for d in t["parts"].values())
    end = 0
    for offset, size in members:
        assert offset == end, "the failed table's bytes were left in the file"
        end = offset + size
    assert end == report.parts_path.stat().st_size
    for site in ("muqawil_org", "other_org"):
        dataset = _table(report, "dataset", site, DATASET)
        assert _part(report, dataset["parts"]["table"]) == \
            client.get(f"/api/table/{DATASET}?site_key={site}").content


def test_a_listed_dataset_the_resolver_refuses_is_a_fault(client, db_path, tmp_path):
    """#1361: the listing shows a dataset on a retired site and the resolver refuses
    it. The route falls through to an empty price table; the copy names the fault."""
    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE source_site SET valid_to = '2026-01-01T00:00:00Z' "
                 "WHERE source_key = 'other_org'")
    conn.commit()
    conn.close()

    report = _write(client, db_path, tmp_path / "out")

    assert [(f["site_key"], f["key"]) for f in report.faults] == [("other_org", DATASET)]
    assert "resolves to nothing" in report.faults[0]["problem"]


def test_an_interrupted_write_leaves_no_file_under_any_name(
        client, db_path, tmp_path, monkeypatch):
    def interrupted(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(reports, "offer_card", interrupted)
    with pytest.raises(KeyboardInterrupt):
        _write(client, db_path, tmp_path / "out")

    assert list((tmp_path / "out").iterdir()) == []


# ---- the edges ---------------------------------------------------------------------------

def test_a_truncated_table_carries_a_card_for_each_row_it_holds(
        client, db_path, tmp_path, monkeypatch):
    _limit, fold = reports.table_payload.__defaults__
    monkeypatch.setattr(reports.table_payload, "__defaults__", (1, fold))

    report = _write(client, db_path, tmp_path / "out")
    price = _table(report, "price", SOURCE, SOURCE)

    assert price["truncated"] is True and price["rows"] == 1
    assert price["parts"]["cards"]["lines"] == 1
    assert _part(report, price["parts"]["table"]) == \
        client.get(f"/api/table/{SOURCE}?fold=0").content


def test_an_empty_warehouse_writes_empty_tables_and_no_faults(client, tmp_path):
    empty = tmp_path / "empty.db"
    conn = dbmod.connect(empty)
    dbmod.migrate(conn)
    conn.close()

    report = lightfile.write(empty, tmp_path / "out-empty",
                             price_sources=client.app.state.manifest.sources)

    assert report.faults == []
    assert [t["kind"] for t in report.index["tables"]] == \
        ["price"] * len(client.app.state.manifest.sources)
    assert all(t["rows"] == 0 and t["parts"]["cards"]["lines"] == 0
               for t in report.index["tables"])


def test_with_the_catalogue_off_no_dataset_is_carried(
        client, db_path, tmp_path, monkeypatch):
    monkeypatch.setattr(features, "_FEATURES", tuple(
        FeatureState(one.key, False, one.stage, one.detail)
        if one.key == FeatureKey.GENERIC_DATASET_CATALOG else one
        for one in features._FEATURES))

    report = _write(client, db_path, tmp_path / "out")

    assert [t for t in report.index["tables"] if t["kind"] == "dataset"] == []
    assert _table(report, "price", SOURCE, SOURCE)["rows"] == 2
