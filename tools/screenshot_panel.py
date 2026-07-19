"""Render the side panel at real widths and save screenshots (spec 2, 28, 36).

WHY THIS EXISTS: the panel is a Chrome extension page, so it cannot simply be
opened as a file — `chrome.tabs/runtime/storage` are undefined and app.js dies on
load. Every visual claim about it was therefore unverifiable, and "looks fine"
was an assertion nobody could check. This harness stubs those APIs, points the
page at a real running engine, and produces PNGs that ARE the evidence.

    python -m scrapex.cli ui --no-open          # in another terminal
    python tools/screenshot_panel.py

Output: docs/screenshots/<state>@<width>.png

Requires the browser extra:
    python -m pip install -e ".[browser]"
    python -m playwright install chromium
(PowerShell 5.1 has no `&&` — run the two commands separately.)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXT = ROOT / "extension"
OUT = ROOT / "docs" / "screenshots"

# Spec 36: the panel must hold together across this whole range.
WIDTHS = (320, 360, 400)

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


def _stub(backend: str, *, engine_up=True, sources=None, jobs=None, records=None,
          changes=None, slow=False) -> str:
    """A chrome.* shim plus a fetch() interceptor, so any state can be rendered
    deterministically — including states a live engine cannot easily produce."""
    routes = {
        "/api/health": {"ok": True, "app": "scrapex", "version": "0.1.0", "sources_with_data": 2},
        "/api/sources": {"sources": sources if sources is not None else STRESS_SOURCES},
        "/api/jobs": {"jobs": jobs or []},
        "/api/records": records or {"records": [], "total": 0, "next_cursor": None},
        "/api/changes": changes or {"summary": {}, "changes": []},
        "/api/schedules": {"schedules": [], "note": "Schedules run only while the ScrapeX "
                           "engine is running. Nothing can wake a sleeping or powered-off machine."},
        "/api/outputs": {"outputs": [
            {"key": "local_db", "label": "Local database", "ready": True, "required": True,
             "detail": "Always on — the source of truth. It cannot be disabled."},
            {"key": "excel", "label": "Excel files", "ready": True, "required": False,
             "detail": ""},
            {"key": "apps_script", "label": "Google Sheets via Apps Script", "ready": False,
             "required": False,
             "detail": "Set SCRAPEX_FUNNEL_URL and SCRAPEX_FUNNEL_TOKEN to enable."},
            {"key": "google_drive", "label": "Google Drive and Sheets", "ready": False,
             "required": False,
             "detail": "Run: scrapex google-connect (one-time browser sign-in)."}]},
        "/api/probe": {"url": "https://shop.example.com", "reachable": True,
            "family": "shopify-json", "implemented": True,
            "evidence": ["/products.json returned a Shopify products array (24 products)"],
            "notes": "Known family with a connector — you can capture immediately.",
            "suggested": {"source_key": "SHOP_EXAMPLE", "source_name": "متجر الأمثلة للمواد",
                          "base_url": "https://shop.example.com", "family": "shopify-json",
                          "currency": "SAR", "default_region": "SA", "vat_mode": "incl",
                          "fetcher": "http", "cadence": "daily", "authority": "shop",
                          "kind": "product_prices", "scope": "census", "active": False}},
    }
    return f"""
window.chrome = {{
  runtime: {{ getURL: p => p, lastError: null }},
  tabs: {{ query: async () => [{{url: "https://elsewedyshop.com/products/lamp"}}],
           create: () => {{}} }},
  storage: {{ local: {{ get: async () => ({{backend: {backend!r}}}), set: async () => {{}} }} }},
}};
const ROUTES = {json.dumps(routes)};
const ENGINE_UP = {str(engine_up).lower()};
const SLOW = {str(slow).lower()};
window.fetch = async (url) => {{
  const path = String(url).replace({backend!r}, "");
  if (!ENGINE_UP) throw new Error("engine down");
  if (SLOW) await new Promise(r => setTimeout(r, 60000));   // freeze on loading state
  const key = Object.keys(ROUTES).find(k => path.startsWith(k));
  if (!key) return {{ ok: false, status: 404, statusText: "not found",
                      json: async () => ({{detail: "not found"}}) }};
  return {{ ok: true, status: 200, json: async () => ROUTES[key] }};
}};
"""


def build_page(tmp: Path, stub_js: str) -> Path:
    """Inline the panel's own HTML/CSS/JS into one file so file:// can load it."""
    html = (EXT / "app.html").read_text(encoding="utf-8")
    body = html.split("<body>", 1)[1].rsplit("</body>", 1)[0]
    # Drop the module <script src>: file:// blocks module loads by CORS, and the
    # real app.js is inlined below anyway.
    body = re.sub(r'<script type="module".*?</script>', "", body, flags=re.S)
    style = html.split("<style>", 1)[1].split("</style>", 1)[0]
    app_js = (EXT / "app.js").read_text(encoding="utf-8")
    engine_js = (EXT / "engine.js").read_text(encoding="utf-8")

    # Flatten the ES module: drop the import and inline engine.js's exports.
    app_js = re.sub(r"^import .*?;$", "", app_js, flags=re.M)
    engine_js = re.sub(r"\bexport\s+", "", engine_js)

    page = tmp / "panel.html"
    page.write_text(
        "<!doctype html><meta charset='utf-8'><title>ScrapeX panel</title>"
        "<style>html,body{margin:0}</style>"
        f"<link rel='stylesheet' href='{(EXT / 'tokens.css').as_uri()}'>"
        f"<link rel='stylesheet' href='{(EXT / 'components.css').as_uri()}'>"
        f"<style>{style}</style>\n{body}\n"
        f"<script>{stub_js}</script>\n"
        # No manual DOMContentLoaded dispatch: this inline script is parsed
        # BEFORE the browser fires the real event, so dispatching one as well
        # would run init() twice and double-bind every listener — a click would
        # then toggle twice and appear to do nothing at all.
        f"<script>{engine_js}\n{app_js}</script>",
        encoding="utf-8")
    return page


def capture(scenarios: dict[str, tuple[str, str | None]], backend: str) -> int:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / "_tmp"
    tmp.mkdir(exist_ok=True)
    written = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for name, (stub, click) in scenarios.items():
            page_file = build_page(tmp, stub)
            for width in WIDTHS:
                page = browser.new_page(viewport={"width": width, "height": 800})
                errors: list[str] = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(page_file.as_uri())
                page.wait_for_timeout(700)
                # Steps to reach a screen that lives behind an interaction.
                # "sel" clicks; ("sel", "text") fills first.
                for step in ([click] if isinstance(click, str) else (click or [])):
                    if isinstance(step, tuple):
                        page.fill(step[0], step[1])
                    else:
                        page.click(step)
                    page.wait_for_timeout(400)
                target = OUT / f"{name}@{width}.png"
                page.screenshot(path=str(target), full_page=True)

                # Horizontal overflow is a hard failure at these widths (spec 36).
                overflow = page.evaluate(
                    "() => document.documentElement.scrollWidth > document.documentElement.clientWidth")
                flag = " OVERFLOW!" if overflow else ""
                if errors:
                    flag += f" JS-ERROR: {errors[0][:70]}"
                print(f"  {target.name}{flag}")
                written += 1
                page.close()
        browser.close()
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", default="http://127.0.0.1:8000")
    args = parser.parse_args()

    TAB_DATA = 'nav.tabs button[data-view="data"]'
    TAB_SETTINGS = 'nav.tabs button[data-view="settings"]'
    running_job = [{
        "job_ref": "job_demo", "status": "running", "run_mode": "update",
        "source_keys": ["LONG_AR", "SHORT"], "current_source_key": "LONG_AR",
        "stage": "fetching", "progress": {"done": 1, "total": 2, "percent": 50},
        "counters": {"observations": 8420, "duplicates": 12, "products": 310,
                     "requests": 96, "errors": 2},
        "started_at": "2026-07-19T05:00:00Z", "error_summary": None}]
    arabic_records = {
        "records": [
            {"name": "طلمبة مياه جراندفوس عالية الضغط للاستخدام الصناعي الثقيل",
             "region": "SA", "region_name": "Saudi Arabia", "effective_price": 1450.5,
             "currency": "SAR", "availability": "in_stock", "sku": "GRF-9912-XL-2026"},
            {"name": "DIESEL", "region": "EG", "region_name": "Egypt",
             "effective_price": 0.404, "currency": "USD",
             "availability": "unknown", "sku": ""},
        ], "total": 2, "next_cursor": None}

    # (stub, optional selector to click before capturing)
    scenarios = {
        "01-run-sites-populated": (_stub(args.backend), None),
        "02-run-empty-no-sites": (_stub(args.backend, sources=[]), None),
        "03-runtime-down": (_stub(args.backend, engine_up=False), None),
        "04-loading": (_stub(args.backend, slow=True), None),
        "05-job-running": (_stub(args.backend, jobs=running_job), None),
        "06-data-datasets": (_stub(args.backend, records=arabic_records), TAB_DATA),
        "07-data-records-arabic": (
            _stub(args.backend, records=arabic_records), TAB_DATA + " >> nth=0"),
        "08-settings": (_stub(args.backend), TAB_SETTINGS),
        "09-job-running-on-data-tab": (
            _stub(args.backend, jobs=running_job, records=arabic_records), TAB_DATA),
        "10-addsite-empty": (_stub(args.backend), "#open-add"),
        "11-addsite-tested": (_stub(args.backend),
                              ["#open-add", ("#url", "https://shop.example.com"), "#check"]),
        "12-addsite-advanced": (_stub(args.backend),
                                ["#open-add", ("#url", "https://shop.example.com"),
                                 "#check", "#adv-toggle"]),
        "13-selected-cards": (_stub(args.backend),
                              ['input[data-key="LONG_AR"]', 'input[data-key="SHORT"]']),
    }

    try:
        n = capture(scenarios, args.backend)
    except ImportError:
        print("playwright is missing. Run these TWO commands (PowerShell has no &&):\n"
              '  python -m pip install -e ".[browser]"\n'
              "  python -m playwright install chromium", file=sys.stderr)
        return 1
    print(f"\n{n} screenshots -> {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
