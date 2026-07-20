"""Render the side panel at real widths and save screenshots (spec 2, 28, 36).

WHY THIS EXISTS: the panel is a Chrome extension page, so it cannot simply be
opened as a file — `chrome.tabs/runtime/storage` are undefined and app.js dies on
load. Every visual claim about it was therefore unverifiable, and "looks fine"
was an assertion nobody could check.

The page itself is built by tools/panel_harness.py, which tests/test_panel_dom.py
also drives. Screenshots and assertions therefore describe the SAME page: a stub
that drifted between them would let a picture prove something the tests never saw.

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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from panel_harness import STRESS_SOURCES, build_page, stub as _stub  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots"

# Spec 36: the panel must hold together across this whole range.
WIDTHS = (320, 360, 400)


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

    TAB_RUN = 'nav.tabs button[data-view="run"]'
    TAB_DATA = 'nav.tabs button[data-view="data"]'
    TAB_SETTINGS = 'nav.tabs button[data-view="settings"]'
    TAB_SOURCE = 'nav.tabs button[data-view="source"]'
    SOURCE_URLS = 'label[for="source-urls"]'
    SOURCE_FILE = 'label[for="source-file"]'
    SOURCE_ADDSITE = 'label[for="source-addsite"]'
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
        "01-run-sites-populated": (_stub(args.backend), TAB_RUN),
        "02-run-empty-no-sites": (_stub(args.backend, sources=[]), TAB_RUN),
        "03-runtime-down": (_stub(args.backend, engine_up=False), TAB_RUN),
        "04-loading": (_stub(args.backend, slow=True), TAB_RUN),
        "05-job-running": (_stub(args.backend, jobs=running_job), TAB_RUN),
        "06-data-datasets": (_stub(args.backend, records=arabic_records), TAB_DATA),
        "07-data-records-arabic": (
            _stub(args.backend, records=arabic_records), TAB_DATA + " >> nth=0"),
        "08-settings": (_stub(args.backend), TAB_SETTINGS),
        "09-job-running-on-data-tab": (
            _stub(args.backend, jobs=running_job, records=arabic_records), TAB_DATA),
        # No click: this is what the owner sees the instant the panel opens.
        # Every other scenario navigates first, which is exactly how a broken
        # opening screen stayed invisible.
        "00-first-open": (_stub(args.backend), None),
        "10-source-current-page": (_stub(args.backend), TAB_SOURCE),
        # The whole point of the tab: a real page becomes a reviewable site.
        "10b-source-reviewed": (_stub(args.backend), [TAB_SOURCE, "#cur-use"]),
        "11-source-urls": (_stub(args.backend), [TAB_SOURCE, SOURCE_URLS]),
        "11b-source-urls-checked": (
            _stub(args.backend),
            [TAB_SOURCE, SOURCE_URLS,
             ("#urls-box", "https://shop.example.com"), "#urls-check"]),
        "12-source-file-image": (_stub(args.backend), [TAB_SOURCE, SOURCE_FILE]),
        # The fourth choice: price tracking, with its settings inside it.
        "12b-source-addsite": (_stub(args.backend), [TAB_SOURCE, SOURCE_ADDSITE]),
        "13-selected-cards": (_stub(args.backend),
                              [TAB_RUN, 'input[data-key="LONG_AR"]', 'input[data-key="SHORT"]']),
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
