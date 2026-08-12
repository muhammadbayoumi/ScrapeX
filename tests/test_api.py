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
    """The page is same-origin, while curl and the CLI send no Origin at all.

    Browsers attach Origin to same-origin writes, so testing only the absent
    header leaves the settings page looking authorised until its first save.
    """
    assert client.get("/api/health").status_code == 200
    assert client.get("/").status_code == 200
    same_engine = {"Origin": "http://testserver"}
    assert client.get("/api/health", headers=same_engine).status_code == 200
    assert client.post("/api/settings", json={}, headers=same_engine).status_code == 200


def test_the_refusal_does_not_rely_on_whoever_wrote_the_pattern_anchoring_it():
    """`match` was changed to `fullmatch` alongside the same-origin exception,
    and nothing caught it: both patterns in this file already end in `$`, so
    the two behave identically today and the improvement is invisible.

    It is not decoration. `match` anchors only the start, so the day someone
    writes a pattern without a trailing `$` — or builds one by joining ids and
    forgets it — `chrome-extension://<valid-id>.attacker.example` becomes a
    permitted origin. The middleware must be safe on its own rather than on
    the assumption that every future pattern is written correctly."""
    import re

    from starlette.applications import Starlette
    from starlette.responses import PlainTextResponse
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from scrapex.webui.app import RefuseForeignOrigins

    valid = "a" * 32
    unanchored = r"^chrome-extension://" + valid          # deliberately no $

    app = Starlette(routes=[Route("/x", lambda r: PlainTextResponse("ok"))])
    app.add_middleware(RefuseForeignOrigins, pattern=unanchored)
    client = TestClient(app)

    assert client.get("/x", headers={"Origin": f"chrome-extension://{valid}"}).status_code == 200
    suffixed = f"chrome-extension://{valid}.attacker.example"
    assert client.get("/x", headers={"Origin": suffixed}).status_code == 403, (
        "an origin that merely STARTS with a permitted one was accepted; the "
        "refusal is anchoring only at the front")

    # And the pattern really is the unanchored one, or this proves nothing.
    assert re.compile(unanchored).match(suffixed) is not None


def test_an_origin_that_only_looks_local_must_match_the_engine_port(client):
    """A loopback-looking origin is not enough: origin includes the port."""
    wrong_port = {"Origin": "http://testserver:8001"}
    assert client.get("/api/health", headers=wrong_port).status_code == 403


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
    assert client.get("/api/health", headers={
        "Host": "attacker.example",
        "Origin": "http://attacker.example",
    }).status_code == 400, "the same-origin exception bypassed the Host boundary"


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


def test_health_states_the_protocol_version_the_panel_can_check(client):
    """The handshake belonged on the transport that carries the traffic.

    The native path checked protocol_version on every message and reported a
    mismatch precisely — and it carries four control commands. THIS path
    carries every record the panel shows and checked nothing, so an extension
    newer than its engine met a 404 and the owner read it as a broken feature
    rather than as an engine that needs updating.
    """
    from scrapex.native import PROTOCOL_VERSION

    body = client.get("/api/health").json()
    assert body["protocol_version"] == PROTOCOL_VERSION


def test_health_carries_the_two_numbers_a_stale_extension_needs(client):
    """The panel polls health and nothing else on a timer, so the pair that
    lets it notice itself has to ride along. The full ledger deliberately does
    NOT: it is fetched once from /api/version, because re-sending it every few
    seconds would answer a question that changes only when the engine restarts.
    """
    from scrapex.version import MINIMUM_EXTENSION_VERSION, VERSION

    body = client.get("/api/health").json()
    assert body["version"] == VERSION, "the engine's own version"
    assert body["latest_extension_version"] == VERSION
    assert body["minimum_extension_version"] == MINIMUM_EXTENSION_VERSION


def test_the_version_report_answers_the_five_facts_a_notification_needs(client):
    """One implementation of "is this extension outdated", and it is here: the
    panel states its version, the engine applies the rule, and the web page can
    read the same verdict instead of inventing a second one."""
    from scrapex.version import VERSION

    body = client.get("/api/version", params={"extension_version": "0.1.0"}).json()
    assert body["installed_extension_version"] == "0.1.0"      # 1
    assert body["latest_extension_version"] == VERSION         # 2
    assert body["minimum_extension_version"]                   # 3
    assert body["missing"] and all(                            # 4
        item["summary"] and item["since"] for item in body["missing"])
    assert "chrome://extensions" in body["update_instructions"]  # 5
    assert body["outdated"] is True
    assert "no remote update server" in body["latest_source"], (
        "the wire implies an update server that does not exist")


def test_the_version_report_refuses_a_number_that_is_not_a_version(client):
    """Answering an unreadable version with "everything is missing" would send
    the owner to reload an extension that is perfectly current."""
    response = client.get("/api/version", params={"extension_version": "banana"})
    assert response.status_code == 400
    assert "not a ScrapeX version" in response.json()["detail"]


def test_the_version_report_without_a_caller_version_judges_nobody(client):
    body = client.get("/api/version").json()
    assert body["installed_extension_version"] is None
    assert body["outdated"] is False and body["missing"] == []
    assert body["capabilities"], "the ledger is empty"


def _a_crawl_is_running_but_the_loop_looks_quiet(db_path: Path) -> None:
    """The exact shape that broke it: a job crawling, its OWN heartbeat fresh,
    and the runtime heartbeat stale because the loop is busy.

    This is not a contrived state — it is what a long crawl looks like from the
    outside, and BACKLOG OP-6·ت2 records it costing the owner an afternoon.
    """
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    stale = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    fresh = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO scrapex_meta (key, value) VALUES ('runtime_heartbeat', ?)",
            (stale,))
        # BUILT FROM THE SHIPPED SCHEMA, not from memory, and not from PRAGMA
        # either: `PRAGMA table_info` reports NOT NULL and defaults but shows no
        # CHECK constraint at all. BACKLOG OP-17 records that exact trap costing
        # three wrong fixtures, and the first version of this one repeated it —
        # `run_mode='full'` is not in the allowed set, and only reading
        # sqlite_master's CREATE TABLE says so.
        conn.execute(
            "INSERT INTO crawl_job (job_ref, run_mode, source_keys, status, "
            "current_source_key, stage, last_heartbeat_at, started_at) "
            "VALUES (?, 'update', ?, 'running', ?, ?, ?, ?)",
            ("job_busy", "ELBUROJ", "ELBUROJ", "fetching", fresh, fresh))
        conn.commit()
    finally:
        conn.close()


def test_the_engine_does_not_call_itself_dead_on_its_own_settings_page(client, db_path):
    """THE PANEL WAS RIGHT AND THE ENGINE'S OWN PAGE WAS WRONG, which is the
    worse way round: the owner opens Settings precisely when something looks
    broken.

    There were TWO worker_alive computations. `/api/health` published the
    two-heartbeat verdict from `worker_health`; `_about` — which renders the
    Settings page — still called `worker_is_alive`, the single-heartbeat answer
    that `worker_health` was written to supersede. So while a crawl ran, the
    engine printed "Not running" beside advice to check whether it had started.
    """
    _a_crawl_is_running_but_the_loop_looks_quiet(db_path)

    health = client.get("/api/health").json()
    assert health["worker_alive"] is True, "the scenario under test did not arise"

    # THE RENDERED PAGE, not the dict behind it. `_about` is a closure with no
    # JSON route, and the badge is what the owner actually reads — a test on the
    # dict would pass while the template said the opposite.
    page = client.get("/settings").text
    assert "Not running" not in page, (
        "the engine's own Settings page says the worker is dead while a crawl "
        "is running — the single-heartbeat verdict is back")
    assert "Queued jobs wait until a worker is running" not in page, (
        "the page advises the owner to check whether the engine started, while "
        "it is crawling")
    assert "Running" in page, "the badge says nothing at all"


def test_the_two_liveness_answers_cannot_drift_apart_again(client, db_path):
    """The point is not this one state, it is that there is ONE answer. Driven
    across both directions rather than asserted about the source."""
    def page_says_running() -> bool:
        return "Not running" not in client.get("/settings").text

    idle_health = client.get("/api/health").json()["worker_alive"]
    assert page_says_running() is idle_health, (
        "with nothing running, the page and /api/health already disagree")

    _a_crawl_is_running_but_the_loop_looks_quiet(db_path)

    busy_health = client.get("/api/health").json()["worker_alive"]
    assert busy_health != idle_health, (
        "the state did not actually change, so this test proves nothing")
    assert page_says_running() is busy_health, (
        "the page and /api/health drifted apart the moment a crawl started — "
        "which is the only moment it matters")
