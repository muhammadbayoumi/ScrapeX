"""Render design/gallery.html in both themes and save the pictures.

WHY THIS EXISTS: on 2026-08-05 the Console rail button shipped wearing the same
icon as the Workspace toggle. Every test passed. It was found by looking at a
screenshot, because no assertion compared one button against another.

A catalogue has the same exposure and more of it: a component that is only ever
asserted about is a component nobody has looked at. Both themes are captured
because the panel and the web UI each ship light and dark, and a component that
works in one and not the other is broken for half the users of it.

    python tools/screenshot_gallery.py

Output: docs/screenshots/ui-kit-<theme>.png

Requires the browser extra:
    python -m pip install -e ".[browser]"
    python -m playwright install chromium
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GALLERY = ROOT / "design" / "gallery.html"
OUT = ROOT / "docs" / "screenshots"

#: Wide enough that the card grid actually wraps into columns, which is the
#: shape a reader is judging. Height is a starting viewport; the capture is
#: full-page.
WIDTH, HEIGHT = 1100, 900


def capture() -> int:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    written = 0
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for theme in ("light", "dark"):
            page = browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(GALLERY.as_uri())
            page.wait_for_timeout(400)
            # The catalogue's own toggle, so the picture proves the toggle works
            # rather than the emulation flag.
            if theme == "dark":
                page.click("#g-theme")
                page.wait_for_timeout(300)

            target = OUT / f"ui-kit-{theme}.png"
            page.screenshot(path=str(target), full_page=True)

            overflow = page.evaluate(
                "() => document.documentElement.scrollWidth"
                " > document.documentElement.clientWidth")
            flag = " OVERFLOW!" if overflow else ""
            if errors:
                flag += f" JS-ERROR: {errors[0][:80]}"
            print(f"  {target.name}{flag}")
            written += 1
            page.close()
        browser.close()
    return written


def main() -> int:
    if not GALLERY.exists():
        print(f"missing {GALLERY}", file=sys.stderr)
        return 1
    return 0 if capture() else 1


if __name__ == "__main__":
    raise SystemExit(main())
