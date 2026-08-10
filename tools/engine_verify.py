"""Generate representative Engine-page screenshots for PR #151.

Captures the restructured Engine card in realistic Chrome Side Panel sizes and
in both schemes/palettes. Every capture asserts the Engine view is visible, the
workspace backdrop is closed, no unrelated overlay is active, and the status
region has settled before the screenshot is taken.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from panel_harness import build_page, stub as _stub  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots" / "engine-verify"

INSTALLER = {
    "name": "scrapex-engine.exe",
    "url": "https://example.test/scrapex-engine.exe",
    "bytes": 24000000,
    "sha256": "a" * 64,
}


def installer_manifest(version: str = "0.9.0") -> dict:
    return {
        "product": "scrapex-engine",
        "version": version,
        "tag": f"engine-v{version}",
        "published_at": "2026-08-06T09:00:00Z",
        "installer": INSTALLER,
    }


def settle(page, expect_status: str | None = None) -> None:
    page.wait_for_selector("#view-engines:not(.hidden)")
    assert page.locator("#workspace-backdrop").is_hidden()
    page.wait_for_function(
        "() => document.getElementById('engine-status-region').getAttribute('aria-busy') === 'false'",
        timeout=10_000)
    if expect_status:
        page.wait_for_function(
            f"() => document.getElementById('engine-status').textContent.includes({expect_status!r})",
            timeout=10_000)


def capture(page, name: str, width: int, height: int, scheme: str, palette: str) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.evaluate(
        "window.ScrapeXAppearance.set(" + json.dumps(
            {"mode": "manual", "scheme": scheme, "palette": palette, "deviceColors": False}
        ) + ")")
    page.wait_for_timeout(250)
    target = OUT / f"{name}-scheme-{scheme}-palette-{palette}@{width}x{height}.png"
    page.screenshot(path=str(target), full_page=True)
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth > document.documentElement.clientWidth")
    flag = " OVERFLOW!" if overflow else ""
    print(f"  {target.name}{flag}")


def main() -> int:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)

    tmp = OUT / "_tmp"
    tmp.mkdir(exist_ok=True)

    # Remove stale captures that no longer match the dynamic naming scheme.
    for stale in OUT.glob("*.png"):
        stale.unlink()

    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # Running, light, default palette (whatsapp).
        page_file = build_page(tmp, _stub("http://127.0.0.1:8000"))
        page = browser.new_page(viewport={"width": 320, "height": 800})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(700)
        page.click('#tab-engines')
        settle(page, "Running")
        capture(page, "running", 320, 800, "light", "whatsapp")
        capture(page, "running", 360, 800, "light", "whatsapp")
        capture(page, "running", 400, 800, "light", "whatsapp")
        capture(page, "running", 600, 800, "light", "whatsapp")
        page.close()

        # Not detected with installer available, light/default.
        page_file = build_page(tmp, _stub("http://127.0.0.1:8000", engine_up=False,
                                           engine_manifest=installer_manifest()))
        page = browser.new_page(viewport={"width": 320, "height": 800})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(700)
        page.click('#tab-engines')
        settle(page, "Not detected")
        capture(page, "not-detected-with-installer", 320, 800, "light", "whatsapp")
        page.close()

        # Expanded installation instructions, light/default.
        page_file = build_page(tmp, _stub("http://127.0.0.1:8000",
                                           engine_manifest=installer_manifest()))
        page = browser.new_page(viewport={"width": 320, "height": 800})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(700)
        page.click('#tab-engines')
        settle(page)
        page.click('#engine-install-steps summary')
        page.wait_for_function("() => document.getElementById('engine-install-steps').open")
        capture(page, "expanded-instructions", 320, 800, "light", "whatsapp")
        page.close()

        # Overflow menu open, light/default.
        page_file = build_page(tmp, _stub("http://127.0.0.1:8000",
                                           engine_manifest=installer_manifest()))
        page = browser.new_page(viewport={"width": 400, "height": 800})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(700)
        page.click('#tab-engines')
        settle(page)
        page.evaluate("() => document.getElementById('engine-overflow').click()")
        page.wait_for_selector("#engine-overflow-menu:not(.hidden)")
        capture(page, "overflow-menu-open", 400, 800, "light", "whatsapp")
        page.close()

        # Running, dark, default palette.
        page_file = build_page(tmp, _stub("http://127.0.0.1:8000"))
        page = browser.new_page(viewport={"width": 320, "height": 800})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(700)
        page.click('#tab-engines')
        settle(page, "Running")
        capture(page, "running", 320, 800, "dark", "whatsapp")
        page.close()

        # Running, light, alternative-blue palette (github).
        page_file = build_page(tmp, _stub("http://127.0.0.1:8000"))
        page = browser.new_page(viewport={"width": 320, "height": 800})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(700)
        page.click('#tab-engines')
        settle(page, "Running")
        capture(page, "running", 320, 800, "light", "github")
        page.close()

        # Narrow 320x480 layout, light/default.
        page_file = build_page(tmp, _stub("http://127.0.0.1:8000",
                                           engine_manifest=installer_manifest()))
        page = browser.new_page(viewport={"width": 320, "height": 480})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(700)
        page.click('#tab-engines')
        settle(page)
        capture(page, "narrow", 320, 480, "light", "whatsapp")
        page.close()

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
