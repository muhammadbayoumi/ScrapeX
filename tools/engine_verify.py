"""Generate representative Engine-page screenshots for PR #151.

Captures the restructured Engine card in realistic Chrome Side Panel sizes and
in both schemes and conceptual palette labels. Production palette IDs are mapped
to the conceptual names used in filenames.

The IDs became the conceptual names under R-73, which built the registry R-59
asked for: `brand` and `blue` are the real keys and `whatsapp`/`github` are the
legacy aliases. `capture()` reads this dict with `PALETTES[palette_id]`, so a
palette missing a row here is a KeyError mid-run rather than a skipped file --
which is why the row is added in the same change as the palette.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from panel_harness import build_page, stub as _stub  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "screenshots" / "engine-verify"

# Production palette ID -> conceptual filename label.
PALETTES = {
    "supabase": "default-supabase",
    "brand": "alternative-brand",
    "blue": "alternative-blue",
}

INSTALLER = {
    "name": "scrapex-engine.exe",
    "url": "https://example.test/scrapex-engine.exe",
    "bytes": 24000000,
    "sha256": "a" * 64,
}


def open_engine(page, engine_id: str = "scrapex-engine") -> None:
    """Into one engine's own screen, the way the catalogue leads there."""
    page.click(f'#view-engines .engine-row[data-engine-id="{engine_id}"]')
    page.wait_for_selector("#view-engine-detail:not(.hidden)")


def installer_manifest(version: str = "0.9.0", has_installer: bool = True) -> dict:
    return {
        "product": "scrapex-engine",
        "version": version,
        "tag": f"engine-v{version}",
        "published_at": "2026-08-06T09:00:00Z",
        "installer": INSTALLER if has_installer else None,
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


def capture(page, name: str, width: int, height: int, scheme: str, palette_id: str) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.evaluate(
        "window.ScrapeXAppearance.set(" + json.dumps(
            {"mode": "manual", "scheme": scheme, "palette": palette_id, "deviceColors": False}
        ) + ")")
    page.wait_for_timeout(250)
    label = PALETTES[palette_id]
    target = OUT / f"{name}-scheme-{scheme}-palette-{label}@{width}x{height}.png"
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

    # Remove stale captures so obsolete palette names do not persist.
    for stale in OUT.glob("*.png"):
        stale.unlink()

    with sync_playwright() as pw:
        browser = pw.chromium.launch()

        # Running — light, default brand.
        page_file = build_page(tmp, _stub("http://127.0.0.1:8000"))
        page = browser.new_page(viewport={"width": 320, "height": 800})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(700)
        page.click('#tab-engines')
        settle(page, "Running")
        capture(page, "running", 320, 800, "light", "brand")
        capture(page, "running", 360, 800, "light", "brand")
        capture(page, "running", 400, 800, "light", "brand")
        capture(page, "running", 600, 800, "light", "brand")
        page.close()

        # Running — dark, default brand.
        page = browser.new_page(viewport={"width": 320, "height": 800})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(700)
        page.click('#tab-engines')
        settle(page, "Running")
        capture(page, "running", 320, 800, "dark", "brand")
        page.close()

        # Running — light, alternative blue.
        page = browser.new_page(viewport={"width": 320, "height": 800})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(700)
        page.click('#tab-engines')
        settle(page, "Running")
        capture(page, "running", 320, 800, "light", "blue")
        page.close()

        # Running — dark, alternative blue.
        page = browser.new_page(viewport={"width": 320, "height": 800})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(700)
        page.click('#tab-engines')
        settle(page, "Running")
        capture(page, "running", 320, 800, "dark", "blue")
        page.close()

        # Not detected, light/default.
        page_file = build_page(tmp, _stub("http://127.0.0.1:8000", engine_up=False))
        page = browser.new_page(viewport={"width": 320, "height": 800})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(700)
        page.click('#tab-engines')
        settle(page, "Not detected")
        capture(page, "not-detected", 320, 800, "light", "brand")
        page.close()

        # Not detected with installer available, light/default.
        page_file = build_page(tmp, _stub("http://127.0.0.1:8000", engine_up=False,
                                           engine_manifest=installer_manifest()))
        page = browser.new_page(viewport={"width": 320, "height": 800})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(700)
        page.click('#tab-engines')
        settle(page, "Not detected")
        capture(page, "not-detected-with-installer", 320, 800, "light", "brand")
        page.close()

        # Installer unavailable, light/default.
        page_file = build_page(tmp, _stub("http://127.0.0.1:8000",
                                           engine_manifest=installer_manifest(has_installer=False)))
        page = browser.new_page(viewport={"width": 320, "height": 800})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(700)
        page.click('#tab-engines')
        settle(page)
        capture(page, "installer-unavailable", 320, 800, "light", "brand")
        page.close()

        # Expanded installation instructions, light/default.
        page_file = build_page(tmp, _stub("http://127.0.0.1:8000",
                                           engine_manifest=installer_manifest()))
        page = browser.new_page(viewport={"width": 320, "height": 800})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(700)
        page.click('#tab-engines')
        settle(page)
        open_engine(page)
        page.click('#engine-install-steps summary')
        page.wait_for_function("() => document.getElementById('engine-install-steps').open")
        capture(page, "expanded-instructions", 320, 1200, "light", "brand")
        page.close()

        # One engine's own screen, light/default — the state banner, the spec
        # rows and the three actions that used to hide behind the overflow menu.
        page = browser.new_page(viewport={"width": 400, "height": 800})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(700)
        page.click('#tab-engines')
        settle(page)
        open_engine(page)
        capture(page, "one-engine", 400, 800, "light", "brand")
        page.close()

        # A candidate backend: what §8.3 records about it, and nothing to press.
        page = browser.new_page(viewport={"width": 400, "height": 800})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(700)
        page.click('#tab-engines')
        settle(page)
        open_engine(page, "scrapy")
        capture(page, "one-candidate", 400, 800, "light", "brand")
        page.close()

        # Narrow 320x480 layout, light/default.
        page = browser.new_page(viewport={"width": 320, "height": 480})
        page.goto(page_file.as_uri())
        page.wait_for_timeout(700)
        page.click('#tab-engines')
        settle(page)
        capture(page, "narrow", 320, 480, "light", "brand")
        page.close()

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
