"""Body text computes Supabase's normal weight, 450, a mono run computes 400 only when it asks
for the normal weight, and the variable faces draw 450 as 450 (#752).

The panel is the page tools/panel_harness.py builds from extension/app.html, the Console the
one tools/tabpage_harness.py serves, and the web UI is every page the engine's own app serves,
routed as tests/test_the_focus_ring_draws_in_the_web_ui.py routes them.
tests/test_the_body_reads_supabases_normal_weight.py holds the rules these compute from.

THEIR CASCADE, which the owner ruled for on 2026-10-06
(https://github.com/muhammadbayoumi/ScrapeX/pull/1443#issuecomment-6010988915). Their mono
context re-declares the normal weight to 400 and sets no weight
(apps/design-system/styles/globals.css@86c813ec:70-75, :89). So a bare `<code>` inherits body's
450, and a mono run that asks for the normal weight -- their `font-normal`, this product's
`font-weight: var(--fw-regular)` -- draws 400.

PROBES AND A SWEEP, because each misses what the other sees. The probes are elements put into
the page -- a paragraph of body text, and code, pre, kbd, samp, .tech and .code inside it, each
bare and each asking for the normal weight -- so each surface answers for the selectors the
reset names whether or not a page happens to show one. The sweep reads every element the
pages actually draw, so a rule that sets the mono family in a sheet the probes never reach is
read where it draws: every mono run there must sit inside the context, its --fw-regular 400.

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

#: A paragraph of body text with each element the reset names inside it, once bare and once
#: asking for the normal weight as their `font-normal` does, and a strong and a strong.tech
#: beside them, read and removed.
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
    const bare = Object.assign(document.createElement(tag), {className: cls, textContent: "x"});
    const asking = Object.assign(document.createElement(tag), {className: cls, textContent: "x"});
    asking.style.fontWeight = "var(--fw-regular)";
    text.append(bare, asking);
    read[name] = getComputedStyle(bare).fontWeight;
    read[`${name} asking`] = getComputedStyle(asking).fontWeight;
  }
  text.remove();
  return read;
}"""

#: Every element with text of its own, by the face its stack resolves to first, its weight,
#: and the normal weight it would read if it asked for it.
SWEEP = """() => {
  const read = [];
  for (const element of document.querySelectorAll("body *")) {
    if (!["SCRIPT", "STYLE", "TEMPLATE"].includes(element.tagName)
        && [...element.childNodes].some((node) => node.nodeType === 3 && node.data.trim())) {
      const style = getComputedStyle(element);
      read.push({family: style.fontFamily.split(",")[0].trim().replace(/"/g, ""),
                 weight: style.fontWeight,
                 normal: style.getPropertyValue("--fw-regular").trim(),
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

#: What the probes must read on every surface: the sans normal on body text and on every
#: bare element the reset names, which asks for no weight and inherits it; the mono normal
#: on each of them that asks for the normal weight. A strong asking reads the sans normal and
#: a strong.tech asking the mono one, as their `<strong class="font-mono font-normal">` does.
RESET_NAMES = ("code", "pre", "kbd", "samp", ".tech", ".code")
EXPECTED = {"body": "450", "synthesis": "none", "text": "450", **dict.fromkeys(RESET_NAMES, "450"),
            **dict.fromkeys((f"{name} asking" for name in RESET_NAMES), "400"),
            "strong asking": "450", "strong.tech asking": "400"}


def _assert_probes(read: dict, where: str) -> None:
    assert {key: read[key] for key in EXPECTED} == EXPECTED, (
        f"{where}: {read}. Supabase's body is font-normal, 450 (globals.css@86c813ec:35, :62), "
        "and their mono context re-declares the normal weight as 400 and sets none (:70-75, "
        ":89): a bare <code> inherits 450, and only a run that asks for the normal weight "
        "draws 400.")
    assert read["strong.tech"] == read["strong"], (
        f"{where}: strong.tech draws {read['strong.tech']} where strong draws {read['strong']}. "
        "The context moves only the normal weight; an emphasised value keeps its emphasis.")


def _assert_mono_in_the_context(read: list[dict], where: str) -> int:
    mono = [element for element in read if element["family"] == "Source Code Pro"]
    outside = sorted({f"{element['name']} (--fw-regular {element['normal']})"
                      for element in mono if element["normal"] != "400"})
    assert not outside, (
        f"{where}: mono runs outside their mono context, so asking for the normal weight would "
        f"draw 450 where theirs draws 400 (globals.css@86c813ec:89): {outside}")
    return len(mono)


def test_the_panel_draws_their_normal_weights(open_panel):
    page = open_panel()
    _assert_probes(page.evaluate(PROBE), "extension/app.html")


def test_the_console_draws_their_normal_weights(inspect):
    page = inspect()
    _assert_probes(page.evaluate(PROBE), "extension/console.html")


def test_the_web_ui_draws_their_normal_weights(webui):  # noqa: F811
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


def test_every_mono_run_in_the_panel_is_in_their_mono_context(open_panel):
    page = open_panel(view="sources")
    counted = _assert_mono_in_the_context(page.evaluate(SWEEP), "panel, sources")
    page.click('nav.side-rail button[data-view="engines"]')
    page.click('#view-engines .engine-row[data-engine-id="scrapex-engine"]')
    page.wait_for_selector("#view-engine-detail:not(.hidden)", timeout=10_000)
    counted += _assert_mono_in_the_context(page.evaluate(SWEEP), "panel, engine detail")
    assert counted >= 100, f"the panel drew {counted} mono runs; the sweep read nothing"


def test_every_mono_run_in_the_console_is_in_their_mono_context(inspect):
    page = inspect()
    counted = _assert_mono_in_the_context(page.evaluate(SWEEP), "the Console, inspect screen")
    # The mapping cards' keys, sources, targets and chains, and the pair list behind them.
    assert counted >= 30, f"the Console drew {counted} mono runs; the sweep read nothing"


def test_every_mono_run_on_every_web_ui_page_is_in_their_mono_context(webui):  # noqa: F811
    counted = 0
    for path in PAGES:
        response = webui.goto(ORIGIN + path)
        assert response is not None and response.status == 200, (path, response and response.status)
        webui.wait_for_load_state("networkidle")
        counted += _assert_mono_in_the_context(webui.evaluate(SWEEP), path)
    assert counted >= 300, f"the web UI drew {counted} mono runs; the sweep read nothing"
