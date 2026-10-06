"""The four faces load on both surfaces, measured in a browser (#1048).

The panel is the page tools/panel_harness.py builds from extension/app.html, the Data page
is the one tools/tabpage_harness.py builds from extension/data.html, and the web UI is the
overview the engine's own app serves through base.html, routed exactly as
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

AND IT IS READ TWICE, once on this platform and once as Windows draws it. Chromium aliases a
missing Helvetica to Arial (alternate_font_family.h:96-102), and Windows' Arial carries
Arabic, so on Windows a Helvetica ahead of the shipped face draws every Arabic letter. Here
Helvetica is Liberation Sans, which has none, so a run on this platform alone passes a stack
that fails on his machine. tests/fixtures/fontconfig-windows/fonts.conf gives Helvetica and
Arial a face with Arabic, and the `windows-stand-in` run draws under it.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

pytest.importorskip("playwright")
pytest.importorskip("fastapi")
from playwright.sync_api import sync_playwright  # noqa: E402

from tests.test_panel_dom import open_panel  # noqa: E402,F401  (the fixture)
from tests.test_tab_page_dom import open_data  # noqa: E402,F401  (the Data page's fixture)
from tests.test_the_focus_ring_draws_in_the_web_ui import ORIGIN, webui  # noqa: E402,F401

# Guards the extension's panel; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

FACES = ("Inter", "Manrope", "Source Code Pro", "Noto Sans Arabic")

#: Windows' Helvetica, on Linux: see the module docstring and the file's own comment.
WINDOWS_FONTCONFIG = Path(__file__).resolve().parent / "fixtures" / "fontconfig-windows" / "fonts.conf"

#: The two platforms the Arabic tests draw on. `platform` is the machine running the suite;
#: `windows-stand-in` is the same Chromium launched with FONTCONFIG_FILE at the fixture.
PLATFORMS = pytest.mark.parametrize("browser", ["platform", "windows-stand-in"], indirect=True)


@pytest.fixture(scope="module")
def browser(request):
    """The Chromium every test here opens its pages in. It replaces tests/test_panel_dom.py's
    for this module, so `open_panel`, `open_data` and `webui` all draw in it. Unparametrised,
    it is that fixture's launch exactly; a test marked with PLATFORMS gets the stand-in too."""
    env = None
    if getattr(request, "param", "platform") == "windows-stand-in":
        assert WINDOWS_FONTCONFIG.is_file(), WINDOWS_FONTCONFIG
        env = {**os.environ, "FONTCONFIG_FILE": str(WINDOWS_FONTCONFIG)}
    with sync_playwright() as pw:
        instance = pw.chromium.launch(env=env)
        try:
            yield instance
        finally:
            instance.close()

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


#: Arabic in Helvetica, with the shipped face behind it: the order the sans stack had before
#: the owner's ruling (a') on #1431.
HELVETICA_FIRST = """() => {
  const probe = Object.assign(document.createElement("span"), {textContent: "مثال"});
  probe.style.fontFamily = 'Helvetica, "Noto Sans Arabic"';
  probe.setAttribute("data-face-probe", "helvetica");
  document.body.append(probe);
}"""


def _assert_the_stand_in_took(page, platform: str) -> None:
    """Under the stand-in, Helvetica must take Arabic ahead of the shipped face, as Windows'
    Arial does. If the fixture failed to load -- a malformed file, or no DejaVu Sans on the
    machine -- Helvetica is Liberation Sans again, Noto draws this probe, and the run below
    would pass while proving nothing about Windows. So that fails here, by name."""
    if platform != "windows-stand-in":
        return
    page.evaluate(HELVETICA_FIRST)
    drawn = _faces_drawing(page, "helvetica")
    assert drawn and "Noto Sans Arabic" not in drawn, (
        f"{WINDOWS_FONTCONFIG.relative_to(Path(__file__).resolve().parent.parent).as_posix()} "
        f"did not take: Helvetica drew no Arabic, {drawn}")


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


@PLATFORMS
def test_the_arabic_face_draws_the_panels_arabic(open_panel, request):
    page = open_panel(view="sources")
    assert page.evaluate(MARK_ARABIC), "the Sources screen showed no Arabic to measure"
    _assert_the_stand_in_took(page, request.node.callspec.params["browser"])
    _assert_the_arabic_face_draws_arabic(page, "extension/app.html")


def test_every_face_loads_in_the_web_ui(webui):  # noqa: F811
    response = webui.goto(ORIGIN + "/")
    assert response is not None and response.status == 200
    # base.html is what loads the design system; the overview is one page built on it.
    assert webui.locator('link[href^="/static/tokens.css"]').count() == 1
    webui.wait_for_load_state("networkidle")
    _assert_every_face_loads(webui.evaluate(LOAD, list(FACES)), "scrapex/webui/templates/base.html")


@PLATFORMS
def test_the_arabic_face_draws_the_web_uis_arabic(webui, request):  # noqa: F811
    response = webui.goto(ORIGIN + "/")
    assert response is not None and response.status == 200
    webui.wait_for_load_state("networkidle")
    assert webui.evaluate(MARK_ARABIC) == "السويدي شوب", "the overview no longer shows the source's Arabic name"
    _assert_the_stand_in_took(webui, request.node.callspec.params["browser"])
    _assert_the_arabic_face_draws_arabic(webui, "scrapex/webui/templates/base.html")


def test_every_face_loads_on_the_data_page(open_data):  # noqa: F811
    """The Data page, built by tools/tabpage_harness.py as every test in
    tests/test_tab_page_dom.py builds it. The harness copies each sheet data.html links
    into a temporary directory, and a url() is read against that copy, so until it
    carried the faces tokens.css names each one failed to load there: those tests
    measured the platform's face, and passed (#1048)."""
    page = open_data()
    _assert_every_face_loads(page.evaluate(LOAD, list(FACES)), "extension/data.html")


#: The family --font-mono computes to, read off a probe element, beside the family the
#: data-model canvas and the dataset snapshot textarea are drawn with.
READ_MONO = """() => {
  const probe = document.createElement("code");
  probe.style.fontFamily = "var(--font-mono)";
  document.body.append(probe);
  const mono = getComputedStyle(probe).fontFamily;
  probe.remove();
  const canvas = document.querySelector("canvas");
  const textarea = document.querySelector(".snapshot-form textarea");
  return {mono,
          canvas: canvas && canvas.getContext("2d").font,
          textarea: textarea && getComputedStyle(textarea).fontFamily};
}"""


def _read_mono(page, path: str) -> dict:
    response = page.goto(ORIGIN + path)
    assert response is not None and response.status == 200, (path, response and response.status)
    page.wait_for_load_state("networkidle")
    page.evaluate("() => document.fonts.ready.then(() => new Promise(requestAnimationFrame))")
    read = page.evaluate(READ_MONO)
    assert read["mono"].startswith('"Source Code Pro"'), read
    return read


def test_the_data_model_labels_draw_in_the_mono_token(webui):  # noqa: F811
    """TSS-20's third site, a canvas font string that no stylesheet reaches. The static
    scan refuses a mono stack written out in a script, and nothing more: delete the line
    that sets the font and the labels draw in the canvas default, `10px sans-serif`, while
    the scan still passes. So the canvas's own font is read, after the page has drawn.
    The font is set per relationship, so a page that drew none reads the default too."""
    read = _read_mono(webui, "/data-model")
    assert read["canvas"] == f"600 12px {read['mono']}", read


def test_the_snapshot_textarea_draws_in_the_mono_token(webui):  # noqa: F811
    """TSS-20's second site. Without its own declaration the textarea takes
    `font: inherit` from design/components.css, the sans stack, and the static scan still
    passes. So the family it computes is read."""
    read = _read_mono(webui, "/datasets")
    assert read["textarea"] == read["mono"], read
