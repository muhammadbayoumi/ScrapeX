"""The four faces load on both surfaces, measured in a browser (#1048).

The panel is the page tools/panel_harness.py builds from extension/app.html, and the web
UI is the overview the engine's own app serves through base.html, routed exactly as
tests/test_the_focus_ring_draws_in_the_web_ui.py routes it.

`document.fonts.check('16px Inter')` ALONE PROVES NOTHING. It answers true when no face in
the document matches the family at all, which is the state before #1048: the stacks named
Inter and nothing declared it. So each family is loaded by name first, and then its
FontFace is read -- exactly one, with status 'loaded'. Before #1048 that list is empty.

The Arabic face is asked one thing more: that it is the face that DRAWS Arabic. Shipping it
is not enough. A family's glyphs are taken in stack order, and a platform face ahead of it
that carries Arabic -- `system-ui` is DejaVu Sans here and Segoe UI on Windows -- draws
every Arabic letter while the shipped face loads and is never used. Chromium reports the
face behind each glyph through CSS.getPlatformFontsForNode, so that is what is read.
"""
from __future__ import annotations

import pytest

pytest.importorskip("playwright")
pytest.importorskip("fastapi")
from tests.test_panel_dom import browser, open_panel  # noqa: E402,F401  (the fixtures)
from tests.test_the_focus_ring_draws_in_the_web_ui import ORIGIN, webui  # noqa: E402,F401

# Guards the extension's panel; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

FACES = ("Inter", "Manrope", "Source Code Pro", "Noto Sans Arabic")

LOAD = """async (families) => {
  const read = {};
  for (const family of families) {
    await document.fonts.load(`16px "${family}"`);
    const faces = [...document.fonts].filter(
      (face) => face.family.replace(/^["']|["']$/g, "") === family);
    read[family] = {check: document.fonts.check(`16px "${family}"`),
                    status: faces.map((face) => face.status)};
  }
  return read;
}"""

#: Marks the first visible element whose own text is Arabic, and a code element holding
#: Arabic placed beside it, so the sans and the mono stack are both read where they draw.
MARK_ARABIC = """() => {
  const arabic = /[\\u0600-\\u06FF]/;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let found = null;
  while (walker.nextNode()) {
    const element = walker.currentNode.parentElement;
    if (arabic.test(walker.currentNode.data) && element.checkVisibility()
        && !element.closest("input, textarea, select, option, script, style")) {
      found = element;
      break;
    }
  }
  if (!found) return null;
  found.setAttribute("data-face-probe", "text");
  const code = Object.assign(document.createElement("code"), {textContent: "مثال 42"});
  code.setAttribute("data-face-probe", "code");
  found.after(code);
  return found.textContent.trim();
}"""


def _faces_drawing(page, probe: str) -> dict[str, int]:
    """Platform face -> glyphs it drew, for the probe element's own text."""
    page.evaluate("() => document.fonts.ready.then(() => new Promise(requestAnimationFrame))")
    cdp = page.context.new_cdp_session(page)
    try:
        cdp.send("DOM.enable")
        cdp.send("CSS.enable")
        root = cdp.send("DOM.getDocument", {"depth": 0})["root"]["nodeId"]
        node = cdp.send("DOM.querySelector", {"nodeId": root,
                                              "selector": f'[data-face-probe="{probe}"]'})["nodeId"]
        fonts = cdp.send("CSS.getPlatformFontsForNode", {"nodeId": node})["fonts"]
    finally:
        cdp.detach()
    return {font["familyName"]: font["glyphCount"] for font in fonts}


def _assert_every_face_loads(read: dict, where: str) -> None:
    for family in FACES:
        assert read[family] == {"check": True, "status": ["loaded"]}, (
            f"{where}: {family} -- {read[family]}. An empty status list is no @font-face "
            "for the family; 'error' is a url() that does not resolve from this surface's "
            "tokens.css.")


def _assert_the_arabic_face_draws_arabic(page, where: str) -> None:
    for probe in ("text", "code"):
        drawn = _faces_drawing(page, probe)
        assert drawn.get("Noto Sans Arabic", 0) > 0, f"{where} {probe}: {drawn}"
        # A shipped face may draw the spaces and digits; no platform face may draw anything.
        strangers = {name: count for name, count in drawn.items()
                     if not any(name.startswith(family) for family in FACES)}
        assert not strangers, f"{where} {probe}: drawn by a face this product does not ship: {drawn}"


def test_every_face_loads_in_the_panel(open_panel):
    page = open_panel()
    _assert_every_face_loads(page.evaluate(LOAD, list(FACES)), "extension/app.html")


def test_the_arabic_face_draws_the_panels_arabic(open_panel):
    page = open_panel(view="sources")
    assert page.evaluate(MARK_ARABIC), "the Sources screen showed no Arabic to measure"
    _assert_the_arabic_face_draws_arabic(page, "extension/app.html")


def test_every_face_loads_in_the_web_ui(webui):  # noqa: F811
    response = webui.goto(ORIGIN + "/")
    assert response is not None and response.status == 200
    # base.html is what loads the design system; the overview is one page built on it.
    assert webui.locator('link[href^="/static/tokens.css"]').count() == 1
    webui.wait_for_load_state("networkidle")
    _assert_every_face_loads(webui.evaluate(LOAD, list(FACES)), "scrapex/webui/templates/base.html")


def test_the_arabic_face_draws_the_web_uis_arabic(webui):  # noqa: F811
    response = webui.goto(ORIGIN + "/")
    assert response is not None and response.status == 200
    webui.wait_for_load_state("networkidle")
    assert webui.evaluate(MARK_ARABIC) == "السويدي شوب", "the overview no longer shows the source's Arabic name"
    _assert_the_arabic_face_draws_arabic(webui, "scrapex/webui/templates/base.html")
