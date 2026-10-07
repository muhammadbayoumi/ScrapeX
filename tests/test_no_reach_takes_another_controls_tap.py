"""A hit area reaches past its control's box, and it must not reach into another control's box
(#1051). The panel's half is tests/test_panel_dom.py; this is the other places a hit area is
drawn: every web UI page and the extension's Console on a touch screen, where every button
reaches the 44px floor, and the enrichment page's action cells, where each action carries
Supabase's hit-area-2, with the catalogue's markup for one.

WHY IT CAN. A hit area is a ::before that paints over what is under it, so where a reach is
longer than the gap to a neighbour, the later control takes the edge of the earlier one's box.
Supabase keeps adjacent reaches a gap apart for that reason
(apps/design-system/content/docs/components/table.mdx@86c813ec:197). Measured before this
guard existed: the Schedules page's 2x2 filters, 4px apart, gave the bottom 2px of each top
filter to the one below it, and the enrichment page's three actions, wrapped onto three lines
at 360px, gave the bottom of each to the next.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

pytest.importorskip("playwright", reason="needs the browser extra")
pytest.importorskip("fastapi")

from tests.test_console_dom import WORKBOOK  # noqa: E402
from tests.test_panel_dom import (  # noqa: E402,F401  (browser is the fixture)
    _A_ROW,
    _NO_BEFORE,
    WEB_ALSO,
    assert_no_box_grows_and_no_reach_shrinks,
    browser,
    read_the_sweep,
)
from tests.test_the_focus_ring_draws_in_the_web_ui import ORIGIN, PAGES, webui_page  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import tabpage_harness  # noqa: E402

# Reads extension/ sources (the enrichment page and the Console, and the shared sheets copied
# into them); see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension


@pytest.fixture()
def webui_on_a_phone(browser, tmp_path):  # noqa: F811
    """The engine's own pages, served as tests/test_the_focus_ring_draws_in_the_web_ui.py
    serves them, on a 360px touch screen."""
    with webui_page(browser, tmp_path, viewport={"width": 360, "height": 800},
                    has_touch=True, is_mobile=True) as page:
        yield page


#: Why a control keeps the floor on its box and draws no hit area, as the schedule filters and the
#: Console's three lists do: it stands nearer its neighbours than its reach would run.
_KEEPS_THE_FLOOR = ("#1051: it keeps the 44px floor on its box and draws no hit area, because its "
                    "neighbours stand nearer than its reach would run, and Supabase keeps adjacent "
                    "reaches a gap apart (components/table.mdx@86c813ec:197)")

#: Why the grid's own controls are taller: they stand on design/grid-theme.css's literal
#: min-heights, 2.35rem and 1.65rem, off Supabase's scale, which #1430 left to the grid's
#: rebuild, as tests/test_the_web_ui_controls_are_supabases_sizes.py's OFF_SIZE says.
_THE_GRID = ("the grid's own control, at a literal height off Supabase's scale until #1367 "
             "rebuilds the grid")

#: Web UI controls whose box is taller than their Supabase component's on a touch screen, each
#: with its ceiling, read as the panel's are, and why it is still. It may only shrink, and no
#: named box may grow past its ceiling (assert_no_box_grows_and_no_reach_shrinks).
_WEB_TALLER_THAN_SUPABASE = {
    "button.grid-lang-option": (26.5, _THE_GRID),
    "#grid-columns-button": (38, _THE_GRID),
    **dict.fromkeys([
        "#excel_folder", "#excel_schema", "#excel_structure", "#excel_update", "#excel_workbook",
        "#funnel_token", "#funnel_url", "#model-database", "#model-layer", "#model-search",
        "#probe-url", "#schedule-search", "#source-search", ".field > input[type=text]",
        ".field > input[type=url]", ".field > select", ".filters > select",
        ".schedule-field > input[type=text]", ".schedule-field > input[type=time]",
        ".schedule-field > select", "input[type=search].dataset-search"], (44, _NO_BEFORE)),
    **dict.fromkeys([
        "#settings-collection-tab", "#settings-connections-tab", "#settings-governance-tab",
        "#settings-workspace-tab"], (52, _A_ROW)),
    **dict.fromkeys([f"#schedule-source-{i}" for i in range(1, 13)], (73.5, _A_ROW)),
    "#schedule-source-0": (76, _A_ROW),
    "button.schedule-filter": (44, _KEEPS_THE_FLOOR),
}

#: Web UI controls a tap reaches less than 44px of on a touch screen: (the least, why).
_WEB_SHORT_OF_THE_FLOOR: dict[str, tuple[float, str]] = {
    "summary.data-grid-command.dataset-menu-trigger": (26, (
        "the grid's dataset picker on /source stands 9px under the source overview's trigger, "
        "so a centred 44px reach took that trigger's taps: it draws no hit area and reaches its "
        "26px box, where main's 37px box reached 37, until #1367 rebuilds the grid")),
}


def test_on_a_phone_no_web_ui_box_grows_and_no_reach_shrinks(webui_on_a_phone):
    """The panel's sweep, over every page the engine serves (#1051): no reach takes another
    control's tap or widens a scroller, every box is its Supabase component's size, and every
    reach is the 44px the coarse-pointer floor gave it, but for the controls named above. The
    menu button, `.sidebar-toggle`, is the web UI's plain icon button: #1051 named it a 26x44
    slab, and it is Supabase's icon-only Button, 36x26 (#1430, his ruling on #1457), that
    reaches 44."""
    page = webui_on_a_phone
    assert page.evaluate("() => matchMedia('(hover: none), (pointer: coarse)').matches")
    read = {"controls": {}, "stolen": [], "widened": []}
    for path in PAGES:
        response = page.goto(ORIGIN + path)
        assert response is not None and response.status == 200, (path, response and response.status)
        page.wait_for_load_state("networkidle")
        read_the_sweep(page, "body", path, read)
        if path == "/data":
            # The source list, and its icon link, are inside the dataset picker. Only the open
            # picker is read: at 360px it covers its own trigger, which was read closed.
            page.click("summary.dataset-menu-trigger")
            page.wait_for_selector("a.dataset-icon-button", state="visible")
            read_the_sweep(page, ".dataset-menu-popover", f"{path}, its dataset picker", read)
    count = sum(map(len, read["controls"].values()))
    assert count >= 90, f"the sweep read {count} buttons and fields; a page did not draw"
    # The sweep names a control by its classes, and each of WEB_ALSO carries `touch-reach`.
    named = [f"{selector}.touch-reach" for selector in WEB_ALSO]
    also = {name: {(c["height"], c["reach"]) for c in seen}
            for name, seen in read["controls"].items() if name in named}
    assert also == dict.fromkeys(named, {(26, 44)}), (
        f"a Button drawn as another element is not a 26px box that reaches 44px: {also}")
    menu = read["controls"].get("button.sidebar-toggle.workspace-menu-button.icon-button", [])
    assert len(menu) == len(PAGES) and {
        (c["width"], c["height"], c["reach"]) for c in menu} == {(36, 26, 44)}, (
        f"the menu button is not a 36x26 box that reaches exactly 44px on every page: {menu}")
    assert_no_box_grows_and_no_reach_shrinks(read, _WEB_TALLER_THAN_SUPABASE, _WEB_SHORT_OF_THE_FLOOR)


#: The Console's screens, each with the click that opens it from the one before, over
#: tests/test_console_dom.py's WORKBOOK: its two tables, the first one's inspect screen, and its
#: two sources. Each is the section the rail shows.
_CONSOLE_SCREENS = (("#cv-overview", None), ("#cv-tables", "#cv-tab-tables"),
                    ("#cv-inspect", "#tables-list button.pair-row >> nth=0"),
                    ("#cv-sources", "#cv-tab-sources"))

#: Console controls whose box is taller than their Supabase component's on a touch screen, each
#: with its ceiling and why it is still, held as the web UI's are.
_CONSOLE_TALLER_THAN_SUPABASE = {
    **dict.fromkeys([
        "#cv-tab-build", "#cv-tab-overview", "#cv-tab-problems", "#cv-tab-scrapex",
        "#cv-tab-sources", "#cv-tab-tables", "button.pair-row", "button.source-row.source-noted"],
        (44, _KEEPS_THE_FLOOR)),
    "button.map-cells.map-grid": (85, _A_ROW),
}

#: Console controls a tap reaches less than 44px of on a touch screen: (the least, why).
_CONSOLE_SHORT_OF_THE_FLOOR: dict[str, tuple[float, str]] = {}


def test_on_a_phone_no_console_box_grows_and_no_reach_shrinks(browser):  # noqa: F811
    """The panel's sweep, over the Console (extension/console.html), which loads
    design/components.css and so draws every button's hit area on a touch screen (#1051).

    Its rail's tabs stand 2px apart and a list's rows 1px apart, under the 3-4px a 36px row's
    centred reach runs, so on every screen the tab or row below took the bottom of the one
    above, and "Add a source" the bottom of the last source, until extension/console.css kept
    the three lists' floor on their box and sent that button's reach down, measured at 360px."""
    read = {"controls": {}, "stolen": [], "widened": []}
    with tabpage_harness.serve_extension() as base:
        page = browser.new_page(viewport={"width": 360, "height": 800}, has_touch=True, is_mobile=True)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script(tabpage_harness.console_stub(WORKBOOK))
        try:
            page.goto(f"{base}/console.html")
            page.wait_for_selector("#tables-list button.pair-row", state="attached", timeout=10_000)
            assert page.evaluate("() => matchMedia('(hover: none), (pointer: coarse)').matches")
            for screen, click in _CONSOLE_SCREENS:
                if click:
                    page.click(click)
                page.wait_for_selector(screen, state="visible")
                page.wait_for_function("""() => document.getAnimations().every(
                     (a) => a.playState !== 'running' || a.effect.getComputedTiming().iterations === Infinity)""",
                                       timeout=5_000)
                read_the_sweep(page, "body", screen, read)
        finally:
            page.close()
    assert not errors, errors
    count = sum(map(len, read["controls"].values()))
    assert count >= 40 and {f"#cv-tab-{tab}" for tab in ("overview", "tables", "sources")} <= set(
        read["controls"]), f"the sweep read {count} controls; a screen did not open: {sorted(read['controls'])}"
    assert_no_box_grows_and_no_reach_shrinks(read, _CONSOLE_TALLER_THAN_SUPABASE,
                                             _CONSOLE_SHORT_OF_THE_FLOOR)


def test_the_schedule_filters_keep_the_floor_on_their_box(webui_on_a_phone):
    """Their 2x2 grid leaves .25rem between rows, under the 6px a 32px filter's hit area would
    reach, so scrapex/webui/static/pages/schedules.css keeps the 44px on their box and draws
    them no hit area, which is what they had before #1051."""
    page = webui_on_a_phone
    page.goto(ORIGIN + "/schedules")
    page.wait_for_load_state("networkidle")
    filters = page.evaluate("""() => [...document.querySelectorAll('.schedule-filter')].map((el) => ({
      height: el.getBoundingClientRect().height,
      before: getComputedStyle(el, '::before').content,
    }))""")
    assert len(filters) == 4, filters
    assert all(f["height"] >= 44 and f["before"] == "none" for f in filters), filters


#: The two things a plain tab cannot have, chrome and an engine, for extension/enrichment.html:
#: one definition with two facts to review, one identity candidate and one merge, so each of the
#: three tables draws its action cell.
ENRICHMENT_STUB = """
window.chrome = {
  storage: {local: {get: async () => ({backend: "http://127.0.0.1:9"}), set: async () => {}}},
  runtime: {lastError: null, getURL: (path) => path, id: "harness"},
  tabs: {create: () => {}},
};
window.fetch = async (input) => {
  const url = String(input && input.url ? input.url : input);
  const answer = (body) => new Response(JSON.stringify(body),
    {status: 200, headers: {"Content-Type": "application/json"}});
  if (url.includes("/api/enrichment/sources/")) return answer({
    site: {site_key: "S", display_name: "Example site"},
    datasets: [{dataset_key: "D", label: "Organizations", fields: [{field_key: "name", label: "Name"}]}],
    proposal: {source_dataset_key: "D", detail_dataset_key: "", entity_key_field: "name",
               field_mapping: {}, providers: [], output_dataset_key: "D_ENRICHED",
               output_dataset_name: "Organization Enrichment"},
    definition: {enrichment_definition_id: 7, status: "active", configuration_version: 1,
                 source_dataset_key: "D", site_key: "S", output_dataset_key: "D_ENRICHED",
                 output_dataset_name: "Organization Enrichment", counts: {}},
    field_roles: [], provider_availability: [], preflight: {}, estimated_requests: 0,
  });
  if (url.includes("/review?")) return answer({items: [
    {organization_id: "org-1", field_key: "email", value: "info@example.com", provider: "website",
     confidence: 0.5, evidence: {page: "/contact"}},
    {organization_id: "org-2", field_key: "phone", value: "+20 2 1234 5678", provider: "website",
     confidence: 0.4, evidence: {page: "/"}},
  ], next_after_id: null});
  if (url.includes("/identity-candidates?")) return answer({items: [
    {organization_id: "org-1", alias_type: "domain", normalized_value: "example.com",
     candidate_id: "org-3", confidence: 0.9, candidate_confidence: 0.8},
  ], next_after_id: null});
  if (url.includes("/merges?")) return answer({items: [
    {source_organization_id: "org-4", target_organization_id: "org-5",
     merged_at: "2026-10-01T09:00:00Z", reversed_at: null},
  ], next_after_id: null});
  return answer({});
};
"""

#: Each action in an action cell under `root`: its box, its neighbour in the cell, and which
#: control takes a tap at each distance past each side. `self` is the action itself.
_ACTIONS = """(root) => [...document.querySelector(root).querySelectorAll('td.action-cell > button')].map((button) => {
  button.scrollIntoView({block: 'center', inline: 'center'});
  const r = button.getBoundingClientRect();
  const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
  const at = (x, y) => {
    const hit = document.elementFromPoint(x, y);
    const control = hit && hit.closest('button');
    return control === button ? 'self' : (control ? control.textContent.trim() : null);
  };
  const past = (d) => ({left: at(r.left - d, cy), right: at(r.right + d, cy),
                        top: at(cx, r.top - d), bottom: at(cx, r.bottom + d)});
  const edges = [];
  for (let x = r.left + 6; x <= r.right - 6; x += 3) edges.push(at(x, r.top + 0.75), at(x, r.bottom - 0.75));
  for (let y = r.top + 6; y <= r.bottom - 6; y += 3) edges.push(at(r.left + 0.75, y), at(r.right - 0.75, y));
  const next = button.nextElementSibling;
  return {text: button.textContent.trim(), classes: button.className, height: r.height,
          gap: next ? next.getBoundingClientRect().left - r.right : null,
          sameLine: next ? Math.abs(next.getBoundingClientRect().top - r.top) < 1 : null,
          hasNext: Boolean(next), hasPrevious: Boolean(button.previousElementSibling),
          past6: past(6), past8: past(8), past9: past(9), past11: past(11), edges: [...new Set(edges)]};
})"""


@pytest.mark.parametrize("touch, width", [(False, 1280), (False, 360), (True, 360), (True, 1024),
                                          (True, 1280)],
                         ids=["mouse-1280", "mouse-360", "touch-360", "touch-1024", "touch-1280"])
def test_each_action_reaches_past_its_box_and_no_further_than_its_neighbour(
        browser, touch, width):  # noqa: F811
    """Supabase's action cell (components/table.mdx@86c813ec:197): each action carries
    hit-area-2, and two side by side keep at least gap-x-2, 8px, between them.

    hit-area-2's insets are measured from the padding edge (hit-area.css@86c813ec:43-48), so a
    bordered Button reaches 7px past its border: a tap 6px out lands, one 9px out does not. Where
    two actions meet, the gap is the later one's and neither box is the other's.

    ON ONE LINE, as their cell's `flex items-center gap-x-2` is: at 360px the three review
    actions wrapped onto three lines with no gap between them until `td.action-cell` stopped
    them wrapping, and each took the bottom of the one above. On a touch screen the reach is
    the larger of hit-area-2's 8px and the 44px floor's: up and down on a 26px action, the
    floor's (#1430). From 1024px the cells stop wrapping and one row's actions stand over the
    next row's, 17px apart, so the lower reach cut the upper one to 42.5px until the cell
    held half of --touch-stack-gap above and below (extension/enrichment.css)."""
    with tabpage_harness.serve_extension() as base:
        page = browser.new_page(viewport={"width": width, "height": 900},
                                has_touch=touch, is_mobile=touch)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script(ENRICHMENT_STUB)
        try:
            page.goto(f"{base}/enrichment.html?source=D&site=S")
            page.wait_for_selector("#merge-rows td.action-cell > button", timeout=10_000)
            actions = page.evaluate(_ACTIONS, "body")
        finally:
            page.close()
    assert not errors, errors
    assert [a["text"] for a in actions] == [
        "Approve", "Reject", "Override", "Approve", "Reject", "Override", "Merge", "Reverse"], actions
    _assert_each_action_reaches_past_its_box_and_no_further_than_its_neighbour(actions, touch)


def _assert_each_action_reaches_past_its_box_and_no_further_than_its_neighbour(actions, touch):
    """The rules of Supabase's action cell, held for each action _ACTIONS read.

    UP AND DOWN ON A TOUCH SCREEN THE FLOOR'S REACH IS THE LARGER. An action is the tiny
    Button, 26px (#1430), 24 inside its border, so the 44px floor insets its hit area by
    (24 - 44) / 2, -10px, past hit-area-2's -8px: it reaches 9px past the border, not 7. There
    a tap 8px out lands and one 11px out does not, not 10, because the top edge measured up to
    0.75px past the 9. Left and right keep hit-area-2's reach: the floor never widened a box."""
    for action in actions:
        assert "hit-area-2" in action["classes"].split(), action
        assert action["edges"] == ["self"], (
            f"{action['text']}: another control takes taps inside its box: {action['edges']}")
        free = {"top", "bottom", *(["left"] if not action["hasPrevious"] else []),
                *(["right"] if not action["hasNext"] else [])}
        assert {side: action["past6"][side] for side in free} == dict.fromkeys(free, "self"), (
            f"{action['text']}: a tap 6px past a free side missed it: {action['past6']}")
        beyond = dict(action["past9"])
        if touch:
            up_and_down = ("top", "bottom")
            assert {side: action["past8"][side] for side in up_and_down} == dict.fromkeys(
                up_and_down, "self"), (
                f"{action['text']}: on a touch screen a tap 8px above or below missed it, so it "
                f"does not reach the 44px floor: {action['past8']}")
            beyond.update({side: action["past11"][side] for side in up_and_down})
        assert "self" not in beyond.values(), (
            f"{action['text']}: a tap past its reach still lands on it (9px out, and 11px up "
            f"and down on a touch screen): {beyond}")
        if action["hasNext"]:
            assert action["sameLine"], f"{action['text']}: the actions wrapped: {actions}"
            assert action["gap"] >= 8 - 0.01, (
                f"{action['text']}: {action['gap']}px to the next action, under Supabase's gap-x-2")


def _the_catalogues_action_cell() -> str:
    """The markup design/gallery.html's "Hit area" entry gives to copy: its <pre>, unescaped."""
    gallery = BeautifulSoup((ROOT / "design" / "gallery.html").read_text(encoding="utf-8"),
                            "html.parser")
    items = [h3.find_parent(class_="g-item") for h3 in gallery.find_all("h3")
             if h3.get_text(strip=True) == "Hit area"]
    assert len(items) == 1 and items[0].find("pre"), "the catalogue has no one Hit area entry"
    snippet = items[0].find("pre").get_text()
    assert snippet.startswith('<td class="action-cell">'), snippet
    return snippet


@pytest.mark.parametrize("touch, width", [(False, 1280), (True, 360)], ids=["mouse-1280", "touch-360"])
def test_the_catalogues_action_cell_keeps_its_actions_apart(browser, touch, width):  # noqa: F811
    """The catalogue shows the action cell as markup to copy, and the cell is the enrichment
    page's, so the markup is drawn there, in a row of its own, and held to every rule above.
    Its actions are bare <button>s, with no `button` class, and the gap rule read only `.button`
    until it read `button, .button`: they stood 4px apart, the whitespace between them, and
    Edit took the taps inside Inspect's right edge, with a mouse and on a touch screen."""
    snippet = _the_catalogues_action_cell()
    with tabpage_harness.serve_extension() as base:
        page = browser.new_page(viewport={"width": width, "height": 900},
                                has_touch=touch, is_mobile=touch)
        page.add_init_script(ENRICHMENT_STUB)
        try:
            page.goto(f"{base}/enrichment.html?source=D&site=S")
            page.wait_for_selector("#merge-rows td.action-cell > button", timeout=10_000)
            page.evaluate("""(snippet) => {
              const row = document.createElement('tr');
              row.id = 'catalogue-row';
              row.innerHTML = snippet;
              document.getElementById('merge-rows').append(row);
            }""", snippet)
            actions = page.evaluate(_ACTIONS, "#catalogue-row")
        finally:
            page.close()
    assert [a["text"] for a in actions] == ["Inspect", "Edit"], actions
    _assert_each_action_reaches_past_its_box_and_no_further_than_its_neighbour(actions, touch)
