"""Every Button and text field the extension's enrichment and onboarding pages draw is
Supabase's size, read from the boxes in a browser (#1430): the panel's
`test_every_button_is_26px_and_every_field_34px_tall`, over the two pages it does not open.

#1430 resized both. extension/enrichment.css dropped its own 40px floor and padding for the
shared 34px Input, and extension/onboarding.html draws the shared tiny Button. Nothing read
their boxes, so a page-sheet rule that stood them taller passed every test: measured at
1280px, the enrichment fields at 44 and 42px and the onboarding Buttons at 32.39px.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("playwright", reason="needs the browser extra")
pytest.importorskip("fastapi")

from tests.test_no_reach_takes_another_controls_tap import ENRICHMENT_STUB  # noqa: E402
from tests.test_panel_dom import _READ_SIZES, _SIZE, browser  # noqa: E402,F401  (the fixture)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import tabpage_harness  # noqa: E402

# Reads extension/ sources; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

#: The enrichment page's six one-line fields, its definition's sources and its output.
ENRICHMENT_FIELDS = {"#source-dataset", "#entity-key", "#detail-dataset", "#detail-key",
                     "#output-key", "#output-name"}

#: Onboarding's Buttons: Start engine and Check again while the engine is down, and Open
#: ScrapeX once it answers (`body.connected`, extension/onboarding.css).
ONBOARDING_BUTTONS = {"setup": {"#start-engine", "#check"}, "connected": {"#open-app"}}


def _off_size(controls: list[dict]) -> list[str]:
    return sorted({f"{c['name']} ({c['kind']}): {c['height']}px" for c in controls
                   if abs(c["height"] - _SIZE[c["kind"]]) > 0.01})


@pytest.mark.parametrize("width", [1280, 360])
def test_every_enrichment_button_is_26px_and_every_field_34px_tall(browser, width):  # noqa: F811
    with tabpage_harness.serve_extension() as base:
        page = browser.new_page(viewport={"width": width, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script(ENRICHMENT_STUB)
        try:
            page.goto(f"{base}/enrichment.html?source=D&site=S")
            page.wait_for_selector("#merge-rows td.action-cell > button", timeout=10_000)
            controls = page.evaluate(_READ_SIZES, ["body", [], []])
        finally:
            page.close()
    assert not errors, errors
    fields = {c["name"] for c in controls if c["kind"] == "field"}
    buttons = [c for c in controls if c["kind"] == "button"]
    # Its six fields, and Reload, the definition's four Buttons, Open data and the eight
    # review actions, when #1430 measured.
    assert fields == ENRICHMENT_FIELDS and len(buttons) >= 13, (
        f"the read found {sorted(fields)} and {len(buttons)} Buttons; the page did not draw")
    wrong = _off_size(controls)
    assert not wrong, (f"Buttons not {_SIZE['button']}px or fields not {_SIZE['field']}px tall:"
                       + "\n  ".join(["", *wrong]))


@pytest.mark.parametrize("width", [1280, 360])
def test_every_onboarding_button_is_26px_tall(browser, width):  # noqa: F811
    read: dict[str, list[dict]] = {}
    with tabpage_harness.serve_extension() as base:
        page = browser.new_page(viewport={"width": width, "height": 900})
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script(ENRICHMENT_STUB)
        try:
            page.goto(f"{base}/onboarding.html")
            page.wait_for_load_state("networkidle")
            for state, connected in (("setup", False), ("connected", True)):
                page.evaluate("(on) => document.body.classList.toggle('connected', on)", connected)
                read[state] = page.evaluate(_READ_SIZES, ["body", [], []])
        finally:
            page.close()
    assert not errors, errors
    assert {state: {c["name"] for c in controls} for state, controls in read.items()} == (
        ONBOARDING_BUTTONS), read
    wrong = _off_size([c for controls in read.values() for c in controls])
    assert not wrong, f"Buttons not {_SIZE['button']}px tall:" + "\n  ".join(["", *wrong])
