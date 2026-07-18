"""JSON API for the Chrome extension: health/sources/resolve/capture."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex import db as dbmod  # noqa: E402
from scrapex.capture import CaptureResult  # noqa: E402
from scrapex.config import MANIFEST_FILE, load_manifest  # noqa: E402
from scrapex.ingest import IngestResult, ingest_payloads  # noqa: E402
from scrapex.probe import ProbeResult  # noqa: E402
from scrapex.vocab import ConnectorFamily  # noqa: E402
from scrapex.webui.app import create_app  # noqa: E402
from tests.test_ingest import make_entry, make_payload, one_row  # noqa: E402


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "harvest.db"
    conn = dbmod.connect(p)
    dbmod.migrate(conn)
    ingest_payloads(conn, make_entry(), [make_payload([one_row(product_name="LED 400W")])])
    conn.commit()
    conn.close()
    return p


@pytest.fixture()
def manifest_copy(tmp_path: Path) -> Path:
    dst = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, dst)
    return dst


@pytest.fixture()
def client(db_path, manifest_copy) -> TestClient:
    # Point the app at a COPY of the manifest so add-source tests never touch the real file.
    return TestClient(create_app(db_path, manifest_path=manifest_copy))


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_sources_lists_manifest_with_counts(client):
    data = client.get("/api/sources").json()["sources"]
    keys = {s["source_key"] for s in data}
    assert "ELSEWEDYSHOP" in keys and "MADAR" in keys
    els = next(s for s in data if s["source_key"] == "ELSEWEDYSHOP")
    assert els["implemented"] is True and els["observations"] == 1
    madar = next(s for s in data if s["source_key"] == "MADAR")
    assert madar["implemented"] is False  # magento-graphql connector not built yet


def test_resolve_known_and_unknown(client):
    assert client.get("/api/resolve", params={"url": "https://elsewedyshop.com/products/x"}).json() == {
        "matched": True, "source_key": "ELSEWEDYSHOP", "source_name": "السويدي شوب", "implemented": True}
    assert client.get("/api/resolve", params={"url": "https://example.com/x"}).json()["matched"] is False


def test_resolve_strips_www(client):
    r = client.get("/api/resolve", params={"url": "https://www.masdaronline.com/p/1"}).json()
    assert r["matched"] is True and r["source_key"] == "MASDAR"


def test_capture_requires_source_key(client):
    assert client.post("/api/capture", json={}).status_code == 400


def test_capture_unknown_source_404(client):
    assert client.post("/api/capture", json={"source_key": "NOPE"}).status_code == 404


def test_capture_runs_and_ingests(client, db_path, monkeypatch):
    """Capture endpoint wiring (write-lock + commit) without hitting the network:
    stub the capture service, then assert the response shape."""
    def fake_capture(conn, entry):
        # write a row so we prove the endpoint commits on the real connection
        r = ingest_payloads(conn, entry, [make_payload(
            [one_row(external_product_id="9", external_variant_id="v9", product_name="Stub")])])
        return CaptureResult(ingest=r, requests_count=2, tables=1)

    monkeypatch.setattr("scrapex.webui.app.capture_source", fake_capture)
    r = client.post("/api/capture", json={"source_key": "ELSEWEDYSHOP"})
    assert r.status_code == 200
    body = r.json()
    assert body["observations"] == 1 and body["requests"] == 2 and body["status"] == "success"

    # Persisted? A fresh connection sees the stub product.
    conn = dbmod.connect(db_path)
    try:
        n = conn.execute("SELECT COUNT(*) FROM source_product WHERE external_product_id='9'").fetchone()[0]
    finally:
        conn.close()
    assert n == 1


def test_capture_unimplemented_family_501(client, monkeypatch):
    def boom(conn, entry):
        raise NotImplementedError("no connector implemented for family 'magento-graphql'")
    monkeypatch.setattr("scrapex.webui.app.capture_source", boom)
    r = client.post("/api/capture", json={"source_key": "MADAR"})
    assert r.status_code == 501


# ---- add-source flow (probe + write to the manifest copy) -------------------

def test_probe_endpoint(client, monkeypatch):
    def fake_probe(url):
        return ProbeResult(url=url, reachable=True, family=ConnectorFamily.SHOPIFY_JSON,
                           implemented=True, evidence=["/products.json"], suggested={"source_key": "X"})
    monkeypatch.setattr("scrapex.webui.app.probe_url", fake_probe)
    r = client.post("/api/probe", json={"url": "https://x.com"})
    assert r.status_code == 200 and r.json()["family"] == "shopify-json"


def test_probe_requires_url(client):
    assert client.post("/api/probe", json={}).status_code == 400


def test_add_source_writes_manifest_and_reflects_in_api(client, manifest_copy):
    payload = {
        "source_key": "uifieldtest", "source_name": "من الواجهة",
        "base_url": "https://uishop.com", "family": "shopify-json",
        "currency": "EGP", "default_region": "EG", "vat_mode": "incl",
        "cadence": "daily", "authority": "shop", "fetcher": "http",
        "kind": "product_prices", "scope": "census", "active": False,
    }
    r = client.post("/api/sources", json=payload)
    assert r.status_code == 200 and r.json()["source_key"] == "UIFIELDTEST"  # upper-cased
    # Written to the manifest copy:
    assert load_manifest(manifest_copy).get("UIFIELDTEST").currency == "EGP"
    # Reflected live in the API (manifest reloaded on app.state):
    keys = {s["source_key"] for s in client.get("/api/sources").json()["sources"]}
    assert "UIFIELDTEST" in keys


def test_add_source_duplicate_409(client):
    payload = {"source_key": "MADAR", "source_name": "dup", "base_url": "https://x.com",
               "family": "magento-graphql", "kind": "product_prices", "scope": "census"}
    assert client.post("/api/sources", json=payload).status_code == 409


def test_add_source_invalid_400(client):
    # lowercase-only key that can't be upper-snake, missing base_url
    bad = {"source_key": "", "source_name": "x", "base_url": "", "family": "shopify-json",
           "kind": "product_prices", "scope": "census"}
    assert client.post("/api/sources", json=bad).status_code == 400


def test_manage_page_renders(client):
    r = client.get("/manage")
    assert r.status_code == 200 and "إضافة مصدر" in r.text
