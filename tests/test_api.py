"""JSON API for the Chrome extension: health/sources/resolve/capture."""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
from pathlib import Path
from types import SimpleNamespace

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
    assert r.json()["worker_alive"] is False


def test_feature_manifest_is_honest_about_the_generic_roadmap(client):
    response = client.get("/api/features")
    assert response.status_code == 200
    features = {item["key"]: item for item in response.json()["features"]}
    assert features["price_tracking"]["enabled"] is True
    assert features["generic_dataset_catalog"]["enabled"] is False
    assert features["generic_extraction"]["stage"] == "not_started"


def test_sources_lists_manifest_with_counts(client):
    data = client.get("/api/sources").json()["sources"]
    keys = {s["source_key"] for s in data}
    assert "ELSEWEDYSHOP" in keys and "MADAR" in keys
    els = next(s for s in data if s["source_key"] == "ELSEWEDYSHOP")
    assert els["implemented"] is True and els["observations"] == 1
    assert "source_name_ar" in els
    madar = next(s for s in data if s["source_key"] == "MADAR")
    assert madar["implemented"] is True  # magento-graphql connector now built
    assert madar["source_name"] == "Madar"


def test_resolve_known_and_unknown(client):
    assert client.get("/api/resolve", params={"url": "https://elsewedyshop.com/products/x"}).json() == {
        "matched": True, "source_key": "ELSEWEDYSHOP", "source_name": "Elsewedy Shop", "implemented": True}
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
    # The served UI is English only (spec 1); Arabic appears solely as DATA.
    assert r.status_code == 200 and "Add a source" in r.text


def test_health_never_reports_the_thread_flag_as_the_workers_liveness(client, monkeypatch):
    """The fallback used to be seeded with `alive = thread_alive`, and the read
    that would have corrected it was swallowed by `except Exception: pass`. So a
    worker spinning on a dead handle — the exact state jobs.py records in
    runtime_worker_error — was published as `worker_alive: true`, and the panel
    printed the engine as running while nothing could crawl."""
    import scrapex.webui.app as webapp

    def unreadable(_conn):
        raise sqlite3.DatabaseError("database disk image is malformed")

    monkeypatch.setattr(webapp, "worker_health", unreadable)
    # The dangerous shape, not a convenient one: a thread object that is still
    # alive while the loop behind it spins on a dead handle. Without this the
    # test would pass on the old code for the wrong reason, because the fixture
    # starts no worker and thread_alive is False anyway.
    client.app.state.runner = SimpleNamespace(is_alive=True)
    body = client.get("/api/health").json()

    assert body["ok"] is True, "health must survive the thing it reports on"
    assert body["worker"]["thread_alive"] is True, "the scenario under test did not arise"
    assert body["worker_alive"] is False, \
        "health published the THREAD flag as the worker's liveness"
    assert body["worker"]["alive"] is None, "unknown must be said as unknown, not as False"
    assert "DatabaseError" in body["worker"]["detail"], \
        "the reason for not knowing was thrown away"
    assert "malformed" in body["worker"]["detail"]


# ---- who may drive this engine ------------------------------------------------
# Binding to 127.0.0.1 was treated as the boundary. It is not: every page the
# owner opens runs inside the browser that can reach the port, and with
# allow_origins=["*"] any site could POST /api/storage/start-fresh, re-point the
# helper with /api/native-host/register, or mint AND READ the funnel token.

HOSTILE = "https://evil.example"


def test_a_web_page_cannot_reach_a_destructive_route(client):
    """The damage is done by the request arriving, not by the reply being read —
    so CORS response headers alone were never a defence for a write route."""
    blocked = client.post("/api/storage/start-fresh", json={"confirm": True},
                          headers={"Origin": HOSTILE})
    assert blocked.status_code == 403, \
        "a page on the internet could wipe the warehouse on this machine"
    assert "another site" in blocked.json()["detail"]


def test_a_web_page_cannot_read_the_funnel_token_or_repoint_the_helper(client):
    for method, path in (("post", "/api/outputs/apps-script/token"),
                         ("post", "/api/native-host/register"),
                         ("post", "/api/settings"),
                         ("get", "/api/health")):
        r = getattr(client, method)(path, headers={"Origin": HOSTILE})
        assert r.status_code == 403, f"{path} answered a hostile origin"


def test_the_engines_own_pages_and_local_tools_still_work(client):
    """No Origin header at all is the engine's own page, curl, or the CLI —
    refusing those would break the product to fix the boundary."""
    assert client.get("/api/health").status_code == 200
    assert client.get("/").status_code == 200


def test_the_extension_is_still_allowed(tmp_path, monkeypatch, db_path, manifest_copy):
    """The panel's HTTP fallback must not be locked out.

    Pinned to a manifest this test WRITES. It used to read the real one on the
    developer's machine and assert that an invented id was accepted, so it
    passed only where ScrapeX was not installed — and failed the moment the
    engine registered its native host, which is the product correctly refusing
    an untrusted extension. A test whose answer depends on whether the app is
    installed on the machine running it is not a test.
    """
    trusted = "a" * 32
    client = _client_trusting_only(tmp_path, monkeypatch, db_path,
                                   manifest_copy, trusted)
    origin = "chrome-extension://" + trusted
    r = client.get("/api/health", headers={"Origin": origin})
    assert r.status_code == 200, "the panel's HTTP fallback was locked out"
    assert r.headers.get("access-control-allow-origin") == origin, \
        "the panel may reach the engine but cannot read the answer"


def test_a_rebinding_host_header_is_refused(client):
    """A DNS-rebinding page points its OWN name at 127.0.0.1, so the request
    arrives with the attacker's host — a same-origin request as far as the
    browser is concerned, carrying no Origin for the check above to catch."""
    assert client.get("/api/health",
                      headers={"Host": "attacker.example"}).status_code == 400


def test_the_allowlist_is_the_native_host_manifest_not_a_second_copy(tmp_path, monkeypatch):
    """One file decides which extension may drive this machine. A second
    allowlist here would be a copy to keep in step — the DRY defect this
    codebase names in Q1."""
    from scrapex.webui import app as webapp

    manifest = tmp_path / "com.scrapex.engine.json"
    manifest.write_text(json.dumps({"allowed_origins": [
        "chrome-extension://" + "b" * 32 + "/"]}), encoding="utf-8")
    monkeypatch.setattr(webapp.nativehost, "manifest_path", lambda platform=None: manifest)

    assert webapp.allowed_extension_ids() == ["b" * 32]
    pattern = webapp.extension_origin_regex()
    assert re.match(pattern, "chrome-extension://" + "b" * 32)
    assert not re.match(pattern, "chrome-extension://" + "c" * 32), \
        "an extension the helper does not trust was accepted over HTTP"


def _client_trusting_only(tmp_path, monkeypatch, db_path, manifest_copy, extension_id):
    from scrapex.webui import app as webapp

    host_manifest = tmp_path / "com.scrapex.engine.json"
    host_manifest.write_text(
        json.dumps({"allowed_origins": [f"chrome-extension://{extension_id}/"]}),
        encoding="utf-8")
    monkeypatch.setattr(webapp.nativehost, "manifest_path",
                        lambda platform=None: host_manifest)
    return TestClient(create_app(db_path, manifest_path=manifest_copy))


def test_an_extension_the_helper_does_not_trust_is_refused(tmp_path, monkeypatch,
                                                          db_path, manifest_copy):
    client = _client_trusting_only(tmp_path, monkeypatch, db_path, manifest_copy, "b" * 32)
    stale = {"Origin": "chrome-extension://" + "c" * 32}
    assert client.get("/api/health", headers=stale).status_code == 403
    assert client.get("/api/health",
                      headers={"Origin": "chrome-extension://" + "b" * 32}).status_code == 200


def test_the_relink_route_stays_reachable_to_the_extension_it_would_repair(
        tmp_path, monkeypatch, db_path, manifest_copy):
    """Held to the stale allowlist, the repair would be locked out by the very
    fault it repairs — a dead panel with no route back."""
    client = _client_trusting_only(tmp_path, monkeypatch, db_path, manifest_copy, "b" * 32)
    new_id = "d" * 32
    monkeypatch.setattr("scrapex.nativehost.install",
                        lambda ids, **kw: tmp_path / "written.json")

    r = client.post("/api/native-host/register", json={"extension_id": new_id},
                    headers={"Origin": f"chrome-extension://{new_id}"})
    assert r.status_code == 200, "the panel could not re-link itself and is stranded"
    # ...and it is still only extensions, never a web page.
    assert client.post("/api/native-host/register", json={"extension_id": new_id},
                       headers={"Origin": HOSTILE}).status_code == 403
