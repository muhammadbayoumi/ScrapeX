"""Load the Chrome side panel in a real browser, with chrome.* and fetch stubbed.

The panel is an extension page: `chrome.tabs/runtime/storage` are undefined over
file://, and app.js dies on load without them. This module builds a single
self-contained page from the panel's own HTML, CSS and JS, injects a shim, and
lets a caller drive it.

It exists as its own module because two very different callers need exactly the
same page: `screenshot_panel.py` photographs it, and `tests/test_panel_dom.py`
asserts against it. A second copy of the stub would drift, and the two would stop
describing the same product — which is the whole failure this harness prevents.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "extension"

DEFAULT_BACKEND = "http://127.0.0.1:8000"

# A site whose name and URL are deliberately punishing: long Arabic, a long host,
# and mixed direction — the cases spec 28 asks to be tested.
STRESS_SOURCES = [
    {"source_key": "LONG_AR", "base_url": "https://very-long-subdomain.example-store-name.com.sa",
     "source_name": "متجر مواد البناء والتشطيبات المتكاملة للمقاولات الكبرى بالمملكة",
     "family": "salla-html", "active": True, "implemented": True,
     "observations": 128394, "products": 9321},
    {"source_key": "SHORT", "base_url": "https://a.co", "source_name": "A",
     "family": "shopify-json", "active": True, "implemented": True,
     "observations": 3, "products": 1},
    {"source_key": "NOT_READY", "base_url": "https://unsupported-platform.example.com",
     "source_name": "Unsupported Platform Store", "family": "TBD-probe",
     "active": False, "implemented": False, "observations": 0, "products": 0},
]

ACTIVE_TAB = {"url": "https://shop.example.com/products/lamp",
              "title": "Example Store — Lamps"}

PROBE_RESULT = {
    "url": "https://shop.example.com", "reachable": True,
    "family": "shopify-json", "implemented": True,
    "evidence": ["/products.json returned a Shopify products array (24 products)"],
    "notes": "Known family with a connector — you can capture immediately.",
    "suggested": {"source_key": "SHOP_EXAMPLE", "source_name": "متجر الأمثلة للمواد",
                  "base_url": "https://shop.example.com", "family": "shopify-json",
                  "currency": "SAR", "default_region": "SA", "vat_mode": "incl",
                  "fetcher": "http", "cadence": "daily", "authority": "shop",
                  "kind": "product_prices", "scope": "census", "active": False},
}

OUTPUTS = [
    {"key": "local_db", "label": "Local database", "ready": True, "required": True,
     "detail": "Always on — the source of truth. It cannot be disabled.",
     "blocker": "", "settings_url": ""},
    {"key": "excel", "label": "Excel workbook", "ready": True, "required": False,
     "detail": "", "blocker": "", "settings_url": "/exports"},
    {"key": "apps_script", "label": "Google Sheets via Apps Script", "ready": False,
     "required": False, "settings_url": "/sync",
     "blocker": "Missing: Deployment URL and token. Deploy the script, then save both here."},
    {"key": "google_drive", "label": "Google Drive and Sheets", "ready": False,
     "required": False, "settings_url": "/sync",
     "blocker": "Not signed in yet — use Continue with Google."},
]


def stub(backend: str = DEFAULT_BACKEND, *, engine_up=True, sources=None, jobs=None,
         records=None, changes=None, slow=False, tab=None, resolve=None, probe=None,
         fail_routes=(), storage=None, extension_version=None, engine_version=None,
         version_reporting=True, omit_capabilities=()) -> str:
    """A chrome.* shim plus a fetch() interceptor.

    Any state can be rendered deterministically, including ones a live engine
    cannot easily produce: a route that fails, an engine that is down, a tab that
    is not a website.

    The three version knobs are what make the compatibility work testable:
    `extension_version` is what `chrome.runtime.getManifest()` reports (Chrome's
    only honest answer to "what is loaded"), `engine_version` is what the engine
    says it is, and `version_reporting=False` removes /api/version entirely — an
    engine built before it existed, which is not a broken route and must not be
    read as one.

    /api/version is answered by the REAL scrapex.version.version_report, never
    by a hand-written fixture: a stub ledger would let the panel be tested
    against a compatibility rule the engine does not have.
    """
    from scrapex.version import VERSION, MINIMUM_EXTENSION_VERSION, version_report

    manifest_version = json.loads(
        (EXT / "manifest.json").read_text(encoding="utf-8"))["version"]
    extension_version = manifest_version if extension_version is None else extension_version
    engine_version = VERSION if engine_version is None else engine_version
    routes = {
        "/api/health": {"ok": True, "app": "scrapex", "version": engine_version,
                        "latest_extension_version": VERSION,
                        "minimum_extension_version": MINIMUM_EXTENSION_VERSION,
                        "sources_with_data": 2},
        "/api/sources": {"sources": STRESS_SOURCES if sources is None else sources},
        "/api/jobs": {"jobs": jobs or []},
        "/api/records": records or {"records": [], "total": 0, "next_cursor": None},
        "/api/changes": changes or {"summary": {}, "changes": []},
        "/api/schedules": {"schedules": [],
                           "note": "Schedules run only while the ScrapeX engine is "
                                   "running. Nothing can wake a sleeping or "
                                   "powered-off machine."},
        "/api/outputs": {"outputs": OUTPUTS},
        "/api/storage": storage or {
            "path": "C:\\Users\\Owner\\.scrapex\\harvest.db",
            "sizes": {"db_bytes": 4194304, "backup_count": 2},
            "health": {"status": "healthy", "ok": True}},
        "/api/resolve": resolve if resolve is not None else {"matched": False},
        "/api/probe": probe if probe is not None else PROBE_RESULT,
        # The crawl pace lives in the panel now (owner's rule, 2026-07-29:
        # every setting in the extension, the web page display-only).
        "/api/settings": {"settings": {
            "crawl_honour_delay": {"value": "1"},
            "crawl_min_interval_s": {"value": "1.0"},
            "crawl_parallel_sources": {"value": "1"},
            "crawl_timeout_s": {"value": "30"},
            "crawl_user_agent": {"value": ""},
            "log_retention_days": {"value": "30"}}},
    }
    if version_reporting:
        # Keyed by the path WITHOUT its query string: the interceptor below
        # matches by prefix, and the panel sends ?extension_version=…
        report = version_report(extension_version or None)
        if omit_capabilities:
            # An engine that reports its capabilities and does not have this
            # one. Not a fiction: it is every engine one release behind, which
            # is what the panel meets the day the ledger grows an entry.
            report = dict(report, capabilities=[
                c for c in report["capabilities"] if c["key"] not in omit_capabilities])
        routes["/api/version"] = report
    # A write answers differently from a read on the same path: POST /api/jobs
    # returns the new job's ref, and the panel stores it to start polling. The
    # read table would hand back the job LIST, so anything that checked what a
    # click actually queued was testing against a shape the engine never sends.
    write_routes = {"/api/jobs": {"job_ref": "job_stub", "status": "queued"}}
    return f"""
window.chrome = {{
  // getManifest is the extension's only honest answer to "which version of ME
  // is running", so the panel reads it and the harness has to provide it.
  runtime: {{ getURL: p => p, lastError: null,
              getManifest: () => ({{version: {extension_version!r}}}) }},
  tabs: {{ query: async () => [{json.dumps(tab if tab is not None else ACTIVE_TAB)}],
           create: () => {{}} }},
  storage: {{ local: {{ get: async () => ({{backend: {backend!r}}}), set: async () => {{}} }} }},
}};
const ROUTES = {json.dumps(routes)};
const WRITE_ROUTES = {json.dumps(write_routes)};
const ENGINE_UP = {str(engine_up).lower()};
const SLOW = {str(slow).lower()};
const FAIL = {json.dumps(list(fail_routes))};
window.__calls = [];
// The BODY of every write, which __calls (a path list) cannot carry — and the
// body is where "resume" lives, so a test that only saw the path could not
// tell a resume from a run that discards the journal.
window.__writes = [];
window.fetch = async (url, options) => {{
  const path = String(url).replace({backend!r}, "");
  const method = (options && options.method) || "GET";
  window.__calls.push(path);
  if (method !== "GET") {{
    let body = null;
    try {{ body = JSON.parse((options && options.body) || "null"); }} catch (_) {{}}
    window.__writes.push({{path, method, body}});
  }}
  if (!ENGINE_UP) throw new Error("engine down");
  if (SLOW) await new Promise(r => setTimeout(r, 60000));   // freeze on loading state
  if (FAIL.some(f => path.startsWith(f))) {{
    return {{ ok: false, status: 500, statusText: "engine error",
              json: async () => ({{detail: "the engine could not do that"}}) }};
  }}
  const table = method === "GET" ? ROUTES
                                 : {{...ROUTES, ...WRITE_ROUTES}};
  const key = Object.keys(table).find(k => path.startsWith(k));
  if (!key) return {{ ok: false, status: 404, statusText: "not found",
                      json: async () => ({{detail: "not found"}}) }};
  return {{ ok: true, status: 200, json: async () => table[key] }};
}};
"""


_ICON_URL = re.compile(r'url\(["\']?(?:[^"\')]*/)?icons/([\w.-]+)["\']?\)')


def _embed_icons(css: str) -> str:
    """Replace icon references with data: URIs.

    Chromium will not load a CSS mask image over file://, so every masked icon
    rendered as an empty box and the screenshots understated the UI. Embedding
    the bytes removes the origin question entirely.
    """
    def sub(match: re.Match) -> str:
        icon = EXT / "icons" / match.group(1)
        if not icon.exists():
            return match.group(0)
        data = base64.b64encode(icon.read_bytes()).decode("ascii")
        return f'url("data:image/png;base64,{data}")'

    return _ICON_URL.sub(sub, css)


def build_page(tmp: Path, stub_js: str, name: str = "panel.html") -> Path:
    """Inline the panel's own HTML/CSS/JS into one file so file:// can load it."""
    html = (EXT / "app.html").read_text(encoding="utf-8")
    body = html.split("<body>", 1)[1].rsplit("</body>", 1)[0]
    # Drop the module <script src>: file:// blocks module loads by CORS, and the
    # real app.js is inlined below anyway.
    body = re.sub(r'<script type="module".*?</script>', "", body, flags=re.S)
    style = _embed_icons((EXT / "app.css").read_text(encoding="utf-8"))
    tokens_css = (EXT / "tokens.css").read_text(encoding="utf-8")
    components_css = _embed_icons((EXT / "components.css").read_text(encoding="utf-8"))
    # External SVG fragments work on the extension origin but not reliably from
    # the harness's file:// document. Inline the exact same generated sprite and
    # point every <use> at the local symbols for deterministic visual tests.
    sprite = (EXT / "icons" / "material-icons.svg").read_text(encoding="utf-8")
    sprite_body = re.sub(r"^<svg[^>]*>|</svg>\s*$", "", sprite, flags=re.S)
    body = re.sub(r'href=(["\'])icons/material-icons\.svg#', r'href=\1#', body)
    body = (
        "<svg aria-hidden='true' width='0' height='0' "
        "style='position:absolute;overflow:hidden'>"
        f"{sprite_body}</svg>{body}"
    )
    app_js = (EXT / "app.js").read_text(encoding="utf-8")
    appearance_js = (EXT / "appearance.js").read_text(encoding="utf-8")
    engine_js = (EXT / "engine.js").read_text(encoding="utf-8")
    transport_js = (EXT / "transport.js").read_text(encoding="utf-8")
    version_js = (EXT / "version.js").read_text(encoding="utf-8")

    # Flatten the ES-module graph. engine.js imports the protocol version from
    # transport.js, while app.js imports both modules; leaving even that
    # transitive import in this classic inline script stops the whole panel
    # before DOMContentLoaded. Keep the harness on the extension's real module
    # graph instead of re-declaring any of its functions in a test-only stub.
    app_js = re.sub(r"^import .*?;$", "", app_js, flags=re.M)
    engine_js = re.sub(r"^import .*?;$", "", engine_js, flags=re.M)
    transport_js = re.sub(r"^import .*?;$", "", transport_js, flags=re.M)
    version_js = re.sub(r"^import .*?;$", "", version_js, flags=re.M)
    engine_js = re.sub(r"\bexport\s+", "", engine_js)
    transport_js = re.sub(r"\bexport\s+", "", transport_js)
    version_js = re.sub(r"\bexport\s+", "", version_js)

    tmp.mkdir(parents=True, exist_ok=True)
    page = tmp / name
    page.write_text(
        "<!doctype html><meta charset='utf-8'><title>ScrapeX panel</title>"
        "<style>html,body{margin:0}</style>"
        f"<style>{tokens_css}</style><style>{components_css}</style>"
        f"<style>{style}</style>\n{body}\n"
        f"<script>{appearance_js}</script>\n"
        f"<script>{stub_js}</script>\n"
        # No manual DOMContentLoaded dispatch: this inline script is parsed
        # BEFORE the browser fires the real event, so dispatching one as well
        # would run init() twice and double-bind every listener — a click would
        # then toggle twice and appear to do nothing at all.
        f"<script>{transport_js}\n{version_js}\n{engine_js}\n{app_js}</script>",
        encoding="utf-8")
    return page
