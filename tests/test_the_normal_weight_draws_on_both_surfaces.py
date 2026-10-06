"""Body text computes Supabase's normal weight, 450, and mono text 400, on both surfaces, and
the variable faces draw 450 as 450 (#752).

The panel is the page tools/panel_harness.py builds from extension/app.html, the Console the
one tools/tabpage_harness.py serves, and the web UI is every page the engine's own app serves,
routed as tests/test_the_focus_ring_draws_in_the_web_ui.py routes them.
tests/test_the_body_reads_supabases_normal_weight.py holds the rules these compute from.

PROBES AND A SWEEP, because each misses what the other sees. The probes are elements put into
the page -- a paragraph of body text, and code, pre, kbd, samp, .tech and .code inside it --
so each surface answers for the selectors the reset names whether or not a page happens to
show one. The sweep reads every element the pages actually draw, so a rule that sets the mono
family in a sheet the probes never reach is read where it draws.

WHY 450 AND NOT "MORE THAN 400". A face without a `wght` axis has no 450: the browser draws
the nearest weight it has, so body text would compute 450 and draw 400, and every computed
style here would pass. So the weight is also DRAWN. Inter's advances widen with its axis, so
its width at 450 lies strictly between 400 and 500. Source Code Pro is monospaced at every
weight, so its advances cannot move, and its ink is counted instead.
"""
from __future__ import annotations

import pytest

pytest.importorskip("playwright")
pytest.importorskip("fastapi")

from tests.test_console_dom import inspect, served  # noqa: E402,F401  (the Console's fixtures)
from tests.test_panel_dom import browser, open_panel  # noqa: E402,F401  (the fixtures)
from tests.test_the_focus_ring_draws_in_the_web_ui import ORIGIN, PAGES, webui  # noqa: E402,F401

# Guards the extension's panel; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

#: A paragraph of body text with each element the reset names inside it, and a strong and
#: a strong.tech beside them, read and removed.
PROBE = """() => {
  const text = Object.assign(document.createElement("p"), {textContent: "Body text "});
  document.body.append(text);
  const read = {body: getComputedStyle(document.body).fontWeight,
                synthesis: getComputedStyle(document.body).fontSynthesisWeight,
                text: getComputedStyle(text).fontWeight};
  for (const [name, tag, cls] of [["code", "code", ""], ["pre", "pre", ""], ["kbd", "kbd", ""],
                                  ["samp", "samp", ""], [".tech", "span", "tech"],
                                  [".code", "span", "code"], ["strong", "strong", ""],
                                  ["strong.tech", "strong", "tech"]]) {
    const probe = Object.assign(document.createElement(tag), {className: cls, textContent: "x"});
    text.append(probe);
    read[name] = getComputedStyle(probe).fontWeight;
  }
  text.remove();
  return read;
}"""

#: Every element with text of its own, by the face its stack resolves to first, and weight.
SWEEP = """() => {
  const read = [];
  for (const element of document.querySelectorAll("body *")) {
    if (!["SCRIPT", "STYLE", "TEMPLATE"].includes(element.tagName)
        && [...element.childNodes].some((node) => node.nodeType === 3 && node.data.trim())) {
      const style = getComputedStyle(element);
      read.push({family: style.fontFamily.split(",")[0].trim().replace(/"/g, ""),
                 weight: style.fontWeight,
                 name: element.tagName.toLowerCase() + (element.className && typeof element.className === "string"
                   ? "." + element.className.trim().split(/\\s+/).join(".") : "")});
    }
  }
  return read;
}"""

#: Inter's advance width and Source Code Pro's ink, at 400, 450 and 500, after each face has
#: loaded at each weight.
DRAWN = """async () => {
  for (const weight of [400, 450, 500]) {
    await document.fonts.load(`${weight} 32px Inter`);
    await document.fonts.load(`${weight} 32px "Source Code Pro"`);
  }
  const canvas = Object.assign(document.createElement("canvas"), {width: 900, height: 80});
  const context = canvas.getContext("2d", {willReadFrequently: true});
  const read = {width: {}, ink: {}, mono: {}};
  for (const weight of [400, 450, 500]) {
    // 64px, so a step of 50 on the axis is several pixels of advance, not a rounding.
    context.font = `${weight} 64px Inter`;
    read.width[weight] = context.measureText("Supabase normal weight 0123456789").width;
    context.font = `${weight} 32px "Source Code Pro"`;
    read.mono[weight] = context.measureText("mono 0123456789").width;
    context.clearRect(0, 0, canvas.width, canvas.height);
    context.fillText("mono 0123456789 {}[]", 4, 48);
    const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let ink = 0;
    for (let index = 3; index < pixels.length; index += 4) ink += pixels[index];
    read.ink[weight] = ink;
  }
  return read;
}"""

#: What the probes must read on every surface: the sans normal on body text, the mono
#: normal on each element the reset names. strong.tech keeps strong's own weight.
EXPECTED = {"body": "450", "synthesis": "none", "text": "450", "code": "400", "pre": "400",
            "kbd": "400", "samp": "400", ".tech": "400", ".code": "400"}


def _assert_probes(read: dict, where: str) -> None:
    assert {key: read[key] for key in EXPECTED} == EXPECTED, (
        f"{where}: {read}. Supabase's body is font-normal, 450 (globals.css@86c813ec:35, :62), "
        "and their mono context resets the normal weight to 400 (:70-75, :89).")
    assert read["strong.tech"] == read["strong"], (
        f"{where}: strong.tech draws {read['strong.tech']} where strong draws {read['strong']}. "
        "The reset moves only the normal weight; an emphasised value keeps its emphasis.")


def _assert_no_mono_run_at_the_sans_normal(read: list[dict], where: str) -> int:
    mono = [element for element in read if element["family"] == "Source Code Pro"]
    sans_normal = sorted({element["name"] for element in mono if element["weight"] == "450"})
    assert not sans_normal, (
        f"{where}: mono runs at 450, the SANS normal: {sans_normal}. Their mono context draws "
        "its normal weight at 400 (globals.css@86c813ec:89).")
    return len(mono)


def test_the_panel_draws_body_text_at_450_and_mono_at_400(open_panel):
    page = open_panel()
    _assert_probes(page.evaluate(PROBE), "extension/app.html")


def test_the_console_draws_body_text_at_450_and_mono_at_400(inspect):
    page = inspect()
    _assert_probes(page.evaluate(PROBE), "extension/console.html")


def test_the_web_ui_draws_body_text_at_450_and_mono_at_400(webui):  # noqa: F811
    response = webui.goto(ORIGIN + "/")
    assert response is not None and response.status == 200
    webui.wait_for_load_state("networkidle")
    _assert_probes(webui.evaluate(PROBE), "scrapex/webui/templates/base.html")


def test_the_variable_faces_draw_450_between_400_and_500(open_panel):
    read = open_panel().evaluate(DRAWN)
    width, ink, mono = ({int(k): v for k, v in part.items()} for part in
                        (read["width"], read["ink"], read["mono"]))
    assert width[400] < width[450] < width[500], (
        f"Inter's advances at 400/450/500: {width}. Equal at 400 and 450 is a face drawing the "
        "nearest weight it has, not its wght axis.")
    assert mono[400] == mono[450] == mono[500], f"Source Code Pro is monospaced at every weight: {mono}"
    assert ink[400] < ink[450] < ink[500], (
        f"Source Code Pro's ink at 400/450/500: {ink}. The face draws one weight for two.")


def test_no_mono_run_in_the_panel_draws_at_the_sans_normal(open_panel):
    page = open_panel(view="sources")
    counted = _assert_no_mono_run_at_the_sans_normal(page.evaluate(SWEEP), "panel, sources")
    page.click('nav.side-rail button[data-view="engines"]')
    page.click('#view-engines .engine-row[data-engine-id="scrapex-engine"]')
    page.wait_for_selector("#view-engine-detail:not(.hidden)", timeout=10_000)
    counted += _assert_no_mono_run_at_the_sans_normal(page.evaluate(SWEEP), "panel, engine detail")
    assert counted >= 100, f"the panel drew {counted} mono runs; the sweep read nothing"


def test_no_mono_run_in_the_console_draws_at_the_sans_normal(inspect):
    page = inspect()
    counted = _assert_no_mono_run_at_the_sans_normal(page.evaluate(SWEEP), "the Console's inspect screen")
    # The mapping cards' keys, sources, targets and chains, and the pair list behind them.
    assert counted >= 30, f"the Console drew {counted} mono runs; the sweep read nothing"


def test_no_mono_run_on_any_web_ui_page_draws_at_the_sans_normal(webui):  # noqa: F811
    counted = 0
    for path in PAGES:
        response = webui.goto(ORIGIN + path)
        assert response is not None and response.status == 200, (path, response and response.status)
        webui.wait_for_load_state("networkidle")
        counted += _assert_no_mono_run_at_the_sans_normal(webui.evaluate(SWEEP), path)
    assert counted >= 300, f"the web UI drew {counted} mono runs; the sweep read nothing"
