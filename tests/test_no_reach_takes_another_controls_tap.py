"""A hit area reaches past its control's box, and it must not reach into another control's box
(#1051). The panel's half is tests/test_panel_dom.py; this is the other two places a hit area
is drawn: every web UI page on a touch screen, where every button reaches the 44px floor, and
the enrichment page's action cells, where each action carries Supabase's hit-area-2.

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

pytest.importorskip("playwright", reason="needs the browser extra")
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex import db as dbmod  # noqa: E402
from scrapex.ingest import ingest_payloads  # noqa: E402
from scrapex.webui.app import create_app  # noqa: E402
from tests.test_ingest import make_entry, make_payload, one_row  # noqa: E402
from tests.test_panel_dom import _SWEEP, browser  # noqa: E402,F401  (the fixture)

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import tabpage_harness  # noqa: E402

# Reads extension/ sources (the enrichment page, and the shared sheets copied into it); see
# tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ORIGIN = "http://webui.test"
PAGES = ["/", "/data", "/data-model", "/schema", "/changes", "/history", "/review", "/jobs",
         "/schedules", "/logs", "/exports", "/settings", "/sync", "/manage", "/source/ELSEWEDYSHOP"]


@pytest.fixture()
def webui_on_a_phone(browser, tmp_path):  # noqa: F811
    """The engine's own pages through its TestClient, as
    tests/test_the_focus_ring_draws_in_the_web_ui.py serves them, on a 360px touch screen."""
    db_path = tmp_path / "harvest.db"
    conn = dbmod.connect(db_path)
    dbmod.migrate(conn)
    ingest_payloads(conn, make_entry(), [make_payload([
        one_row(external_product_id="1", external_variant_id="v1", product_name="LED Floodlight 400W"),
        one_row(external_product_id="2", external_variant_id="v2", product_name="Copper Wire",
                price="50.00", availability="out_of_stock"),
    ])])
    conn.commit()
    conn.close()
    client = TestClient(create_app(db_path))
    page = browser.new_page(viewport={"width": 360, "height": 800}, has_touch=True, is_mobile=True)

    def serve(route):
        request = route.request
        answer = client.request(request.method, request.url[len(ORIGIN):],
                                content=request.post_data_buffer,
                                headers={"content-type": request.headers.get("content-type", "")})
        route.fulfill(status=answer.status_code, body=answer.content,
                      headers={"content-type": answer.headers.get("content-type", "text/plain")})

    page.route("**/*", lambda route: route.abort())  # nothing leaves the machine
    page.route(f"{ORIGIN}/**", serve)
    try:
        yield page
    finally:
        page.close()


def test_on_a_phone_no_web_ui_reach_takes_another_controls_tap(webui_on_a_phone):
    page = webui_on_a_phone
    assert page.evaluate("() => matchMedia('(hover: none), (pointer: coarse)').matches")
    read, stolen = 0, []
    for path in PAGES:
        response = page.goto(ORIGIN + path)
        assert response is not None and response.status == 200, (path, response and response.status)
        page.wait_for_load_state("networkidle")
        found = page.evaluate(_SWEEP, "body")
        read += len(found["controls"])
        stolen += [f"{path}: {theft}" for theft in found["stolen"]]
    assert read >= 90, f"the sweep read {read} buttons and fields; a page did not draw"
    assert not stolen, (
        "a hit area takes taps inside another control's box:\n  " + "\n  ".join(sorted(set(stolen))))


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

#: Each action in an action cell: its box, its neighbour in the cell, and which control takes a
#: tap at each distance past each side. `self` is the action itself.
_ACTIONS = """() => [...document.querySelectorAll('td.action-cell > button')].map((button) => {
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
          past6: past(6), past9: past(9), edges: [...new Set(edges)]};
})"""


@pytest.mark.parametrize("touch, width", [(False, 1280), (False, 360), (True, 360)],
                         ids=["mouse-1280", "mouse-360", "touch-360"])
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
    the larger of hit-area-2's 8px and the 44px floor's."""
    with tabpage_harness.serve_extension() as base:
        page = browser.new_page(viewport={"width": width, "height": 900},
                                has_touch=touch, is_mobile=touch)
        errors: list[str] = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.add_init_script(ENRICHMENT_STUB)
        try:
            page.goto(f"{base}/enrichment.html?source=D&site=S")
            page.wait_for_selector("#merge-rows td.action-cell > button", timeout=10_000)
            actions = page.evaluate(_ACTIONS)
        finally:
            page.close()
    assert not errors, errors
    assert [a["text"] for a in actions] == [
        "Approve", "Reject", "Override", "Approve", "Reject", "Override", "Merge", "Reverse"], actions
    for action in actions:
        assert "hit-area-2" in action["classes"].split(), action
        assert action["edges"] == ["self"], (
            f"{action['text']}: another control takes taps inside its box: {action['edges']}")
        free = {"top", "bottom", *(["left"] if not action["hasPrevious"] else []),
                *(["right"] if not action["hasNext"] else [])}
        assert {side: action["past6"][side] for side in free} == dict.fromkeys(free, "self"), (
            f"{action['text']}: a tap 6px past a free side missed it: {action['past6']}")
        assert "self" not in action["past9"].values(), (
            f"{action['text']}: a tap 9px past its box still lands on it: {action['past9']}")
        if action["hasNext"]:
            assert action["sameLine"], f"{action['text']}: the actions wrapped: {actions}"
            assert action["gap"] >= 8 - 0.01, (
                f"{action['text']}: {action['gap']}px to the next action, under Supabase's gap-x-2")
