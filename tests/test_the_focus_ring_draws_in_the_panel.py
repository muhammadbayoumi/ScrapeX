"""The focus ring the panel draws is Supabase's `focus-ring`, measured in a browser (#721):
a 2px ring at a 2px offset painted in the background. The outline draws the ring, so no
control's own box-shadow can take it away, and a shadow paints the gap."""
from __future__ import annotations

import base64

import pytest

pytest.importorskip("playwright")
from tests.test_panel_dom import ACCOUNT, ROOT, _contrast, _over, browser, open_panel  # noqa: E402,F401  (the fixtures)
from tests.test_tab_page_dom import open_data  # noqa: E402,F401  (the fixture)

# Guards the extension's panel; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

READ = """() => {
  const el = document.activeElement, s = getComputedStyle(el);
  const probe = document.createElement('span'); document.body.append(probe);
  const colour = (v) => { probe.style.color = ''; probe.style.color = v; return getComputedStyle(probe).color; };
  const read = {id: el.id, visible: el.matches(':focus-visible'), shadow: s.boxShadow,
                outline: [s.outlineStyle, s.outlineWidth, s.outlineColor, s.outlineOffset],
                bg: colour('var(--bg)'), ring: colour('var(--focus-ring-color)'),
                border: s.borderTopColor, fieldBorder: colour('var(--line-control-hover)')};
  probe.remove();
  return read;
}"""


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a_focused_ghost_button_draws_the_ring_at_a_background_offset(open_panel, scheme):
    page = open_panel()
    page.evaluate("""(scheme) => window.ScrapeXAppearance.set({mode: "manual", scheme, palette: "supabase"})""",
                  scheme)
    # No ghost button is in view on the panel's first screen, so one is placed in it: what
    # is measured is what the panel's own sheets draw for `.ghost`, through their cascade.
    page.evaluate("""() => {
      const button = Object.assign(document.createElement('button'),
                                   {id: 'focus-probe', className: 'ghost', type: 'button', textContent: 'Probe'});
      document.querySelector('main').prepend(button);
    }""")
    page.keyboard.press("Tab")  # keyboard modality, so programmatic focus is :focus-visible
    page.focus("#focus-probe")
    # `.ghost` eases box-shadow in over --dur, so the ring is read once the element's own
    # transitions have finished, never on a frame in between.
    page.wait_for_function("() => document.activeElement.getAnimations().length === 0", timeout=3000)
    read = page.evaluate(READ)
    assert read["id"] == "focus-probe" and read["visible"], read
    assert read["shadow"] == f"{read['bg']} 0px 0px 0px 2px", read
    assert read["outline"] == ["solid", "2px", read["ring"], "2px"], read
    if scheme == "dark":
        # WCAG 1.4.11 asks 3:1 of a focus indicator against what it sits on, scored as it
        # is painted over the gap (#746). Light is Supabase's own --ring, 1.47:1, and
        # tokens.css records it beside --focus.
        assert _contrast(_over(read["ring"], read["bg"]), read["bg"]) >= 3.0, read


@pytest.mark.parametrize("control", ["#source-dataset", "#entity-key", "#detail-dataset", "#detail-key",
                                     "#output-key", "#output-name"])
def test_the_enrichment_page_keeps_the_ring_on_every_field(browser, control):
    """#745: extension/enrichment.css cancelled the shared ring on all six fields of the
    panel's enrichment page, loaded after components.css at the same specificity. Each
    now draws it. (Chromium matches `:focus-visible` on a select or text field focused by
    the mouse too, so a click shows it there as well; that is the browser's rule.) And its
    border takes Supabase's neutral control border, not the brand (#748)."""
    page = browser.new_page(viewport={"width": 900, "height": 900})
    try:
        page.goto((ROOT / "extension" / "enrichment.html").as_uri())
        page.keyboard.press("Tab")  # keyboard modality, so programmatic focus is :focus-visible
        page.focus(control)
        page.wait_for_function("() => document.activeElement.getAnimations().length === 0", timeout=3000)
        read = page.evaluate(READ)
        assert read["id"] == control[1:] and read["visible"], read
        assert read["outline"] == ["solid", "2px", read["ring"], "2px"], read
        assert read["shadow"] == f"{read['bg']} 0px 0px 0px 2px", read
        assert read["border"] == read["fieldBorder"] != read["ring"], read
    finally:
        page.close()


#: The controls a phase-4 item rebuilds keep their own ring until it lands (the static
#: guard's LEFT_TO); for them an outline of any colour is what is asked.
LEFT_TO = ".m3-switch, .appearance-switch, .split-button-trigger, .finance-converter-select-trigger"

#: One page, as it stands: every disclosure opened, every focusable control focused, and
#: for each the element that draws its ring found and judged. The web UI's sweep runs the
#: same check (tests/test_the_focus_ring_draws_in_the_web_ui.py).
CHECK = r"""async ({where, leftTo, skip}) => {
  const probe = document.createElement('span'); document.body.append(probe);
  probe.style.color = 'var(--focus-ring-color)';
  const ring = getComputedStyle(probe).color; probe.remove();
  const outlined = (s) => s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0;
  const draws = (el) => { const s = getComputedStyle(el);
    return s.boxShadow.includes(ring) || (outlined(s) && s.outlineColor === ring); };
  // For a control left to a phase-4 item, an outline of any colour. A shadow does not
  // count: the gap every control paints is a shadow, in the background's colour.
  const visible = (el) => { const s = getComputedStyle(el);
    return outlined(s) && s.outlineColor !== 'rgba(0, 0, 0, 0)'; };
  // The opacity an element is painted at: its own times every ancestor's.
  const strength = (el) => {
    let opacity = 1;
    for (let at = el; at; at = at.parentElement) opacity *= parseFloat(getComputedStyle(at).opacity);
    return opacity;
  };
  // An element nobody can see draws nothing, however its outline computes: the Source
  // view's radios are opacity 0, and the card around them is what draws the ring.
  const paintable = (el) => getComputedStyle(el).visibility !== 'hidden' && strength(el) > 0.05;
  // Whether at least two sides of the outline survive every ancestor that clips, and the
  // viewport. A ring cut on all four is computed and never seen, and one left with a
  // single edge is a line that a font's metrics can take too: the finance summary kept
  // its bottom edge on Windows and lost it on Linux.
  const shown = (el) => {
    const s = getComputedStyle(el);
    if (!outlined(s)) return true;
    const width = parseFloat(s.outlineWidth), offset = parseFloat(s.outlineOffset) || 0;
    const box = el.getBoundingClientRect();
    const inner = {l: box.left - offset, t: box.top - offset, r: box.right + offset, b: box.bottom + offset};
    const outer = {l: inner.l - width, t: inner.t - width, r: inner.r + width, b: inner.b + width};
    const clip = {l: 0, t: 0, r: innerWidth, b: innerHeight};
    for (let at = el.parentElement; at; at = at.parentElement) {
      const c = getComputedStyle(at), r = at.getBoundingClientRect();
      // Overflow applies to a box: `display: contents` (Tabulator's column titles) has none.
      if (c.display === 'contents' || c.display === 'inline') continue;
      if (c.overflowX !== 'visible') {
        clip.l = Math.max(clip.l, r.left + parseFloat(c.borderLeftWidth));
        clip.r = Math.min(clip.r, r.right - parseFloat(c.borderRightWidth));
      }
      if (c.overflowY !== 'visible') {
        clip.t = Math.max(clip.t, r.top + parseFloat(c.borderTopWidth));
        clip.b = Math.min(clip.b, r.bottom - parseFloat(c.borderBottomWidth));
      }
    }
    const across = clip.l < outer.r && clip.r > outer.l, down = clip.t < outer.b && clip.b > outer.t;
    return [down && clip.l < inner.l - 0.5 && clip.r > outer.l + 0.5,
            down && clip.r > inner.r + 0.5 && clip.l < outer.r - 0.5,
            across && clip.t < inner.t - 0.5 && clip.b > outer.t + 0.5,
            across && clip.b > inner.b + 0.5 && clip.t < outer.b - 0.5].filter(Boolean).length >= 2;
  };
  const settle = (el) => new Promise(done => { const start = performance.now();
    const tick = () => (el.getAnimations().length === 0 || performance.now() - start > 1000)
      ? done() : requestAnimationFrame(tick); tick(); });
  const name = (el) => `${where}: ${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}`
    + [...el.classList].map(c => '.' + c).join('');
  const seen = {controls: 0, opened: 0, ringless: [], clipped: [], doubled: [], faded: []};
  // A control inside a closed disclosure cannot take focus, so each one is opened first;
  // otherwise the switches in the finance preferences are never measured.
  document.querySelectorAll('details:not([open])').forEach(d => { d.open = true; seen.opened++; });
  await new Promise(done => setTimeout(done, 120));
  const focusable = [...document.querySelectorAll(
      'button, a[href], input, select, textarea, summary, [tabindex]:not([tabindex="-1"])')]
    // getClientRects, not offsetParent: offsetParent is null for a fixed-position control too.
    .filter(el => !el.disabled && el.getClientRects().length > 0 && !(skip && el.matches(skip)));
  for (const el of focusable) {
    el.focus();
    if (document.activeElement !== el) continue;
    await settle(el);
    seen.controls++;
    const exempt = leftTo && el.closest(leftTo);
    const drawers = [];
    for (let at = el; at; at = at.parentElement)
      if (paintable(at) && (exempt ? visible(at) : draws(at))) drawers.push(at);
    // A switch draws its ring on the track that follows its hidden input: the panel's two
    // (left to phase 4) and the web UI's schedule switch.
    const track = el.nextElementSibling;
    if (!drawers.length && track && paintable(track) && (exempt ? visible(track) : draws(track)))
      drawers.push(track);
    if (!drawers.length) { seen.ringless.push(name(el)); continue; }
    // Every element that draws a ring for this control must show it, not only the nearest:
    // a card's ring around a checkbox that draws its own is a ring the reader looks for too.
    if (drawers.some(drawer => !shown(drawer))) seen.clipped.push(name(el));
    // The probe's 3:1 is the ring colour at full strength, and opacity fades a ring with
    // its element: the grid's popup button rests at .55, which takes its ring to 1.8:1
    // in dark mode once its own focus rule is gone (#1453).
    if (strength(drawers[0]) < 1) seen.faded.push(`${name(el)} at ${strength(drawers[0]).toFixed(3)}`);
    // A text field under a wrapper that draws the ring drops its own ring and its gap. A
    // checkbox or radio inside a card keeps its own, as it did before #721.
    if (el.matches('input:not([type=checkbox]):not([type=radio]), select, textarea') && paintable(el)) {
      const s = getComputedStyle(el);
      if (drawers.length > 1 || (drawers[0] !== el && (outlined(s) || s.boxShadow !== 'none')))
        seen.doubled.push(name(el));
    }
  }
  return seen;
}"""


def sweep(page, where: str, *, left_to: str = LEFT_TO, skip: str = "") -> dict:
    """CHECK over the page as it stands, named `where` in what it reports."""
    return page.evaluate(CHECK, {"where": where, "leftTo": left_to, "skip": skip})


def test_every_control_in_every_view_draws_the_ring(open_panel):
    """#721's acceptance: the ring is still visible on every control the panel shows. Each
    focusable control in each rail view, with every disclosure open, is focused from the
    keyboard. It, or the wrapper that draws the ring for it, must paint the ring colour
    where it can be seen (not an invisible element, and on at least two sides past every
    ancestor that clips), and a field under a wrapper must not draw a second ring or gap."""
    page = open_panel()
    page.keyboard.press("Tab")  # keyboard modality; the views are switched by script, not a click
    views = page.eval_on_selector_all("nav.side-rail button[data-view]", "buttons => buttons.map(b => b.dataset.view)")
    seen = {"controls": 0, "opened": 0, "ringless": [], "clipped": [], "doubled": [], "faded": []}
    for view in views:
        page.evaluate("""(view) => new Promise(done => {
          document.querySelector(`nav.side-rail button[data-view="${view}"]`).click();
          setTimeout(done, 120);
        })""", view)
        for key, value in sweep(page, view).items():
            seen[key] += value
    assert len(views) >= 10 and seen["controls"] >= 250 and seen["opened"] >= 40, seen
    assert not seen["ringless"], f"controls that draw no focus ring: {seen['ringless']}"
    assert not seen["clipped"], f"controls whose ring shows on fewer than two sides: {seen['clipped']}"
    assert not seen["doubled"], f"fields that draw a ring or gap under their wrapper's: {seen['doubled']}"
    assert not seen["faded"], f"controls whose ring is painted below full opacity: {seen['faded']}"


#: A view's own ring: the band each side of its outline covers, and whether the view fills
#: `main` (its box is main's, edge to edge) or sits inside main's padding.
RING_BANDS = """(id) => {
  const el = document.getElementById(id), s = getComputedStyle(el), r = el.getBoundingClientRect();
  const main = document.querySelector('main').getBoundingClientRect();
  const width = parseFloat(s.outlineWidth), offset = parseFloat(s.outlineOffset);
  const inner = {l: r.left - offset, t: r.top - offset, r: r.right + offset, b: r.bottom + offset};
  const outer = {l: inner.l - width, t: inner.t - width, r: inner.r + width, b: inner.b + width};
  return {offset, fills: Math.abs(r.left - main.left) < 1 && Math.abs(r.right - main.right) < 1,
          sides: {left: [outer.l, inner.t, inner.l, inner.b], right: [inner.r, inner.t, outer.r, inner.b],
                  top: [inner.l, outer.t, inner.r, inner.t], bottom: [inner.l, inner.b, inner.r, outer.b]}};
}"""

#: For each side, how many pixels of its band (inside the viewport) differ between two
#: screenshots, and how many there are: what focus visibly changed there.
PIXELS_CHANGED = """async ({focused, blurred, sides}) => {
  const load = (src) => new Promise(done => { const image = new Image(); image.onload = () => done(image); image.src = src; });
  const read = (image) => { const canvas = document.createElement('canvas');
    canvas.width = image.width; canvas.height = image.height;
    const context = canvas.getContext('2d'); context.drawImage(image, 0, 0);
    return context.getImageData(0, 0, image.width, image.height); };
  const [a, b] = (await Promise.all([load(focused), load(blurred)])).map(read);
  const out = {};
  for (const [side, [l, t, r, bottom]] of Object.entries(sides)) {
    let changed = 0, total = 0;
    for (let y = Math.max(0, Math.ceil(t)); y < Math.min(a.height, Math.floor(bottom)); y++)
      for (let x = Math.max(0, Math.ceil(l)); x < Math.min(a.width, Math.floor(r)); x++) {
        const i = (y * a.width + x) * 4; total++;
        if (a.data[i] !== b.data[i] || a.data[i + 1] !== b.data[i + 1] || a.data[i + 2] !== b.data[i + 2]) changed++;
      }
    out[side] = [changed, total];
  }
  return out;
}"""

SETTLED = "() => document.getAnimations().every(a => a.playState !== 'running' || a.effect.getTiming().iterations === Infinity)"


def _ring_seen(browser, page, view_id: str) -> tuple[dict, dict]:
    """The view's ring and, per side, the share of its band that focus visibly changes."""
    page.keyboard.press("Shift")  # keyboard modality, without moving focus
    page.focus(f"#{view_id}")
    page.wait_for_function(SETTLED, timeout=3000)
    ring = page.evaluate(RING_BANDS, view_id)
    focused = page.screenshot()
    page.evaluate("() => document.activeElement.blur()")
    page.wait_for_function(SETTLED, timeout=3000)
    blurred = page.screenshot()
    canvas = browser.new_page()
    try:
        changed = canvas.evaluate(PIXELS_CHANGED, {
            "focused": "data:image/png;base64," + base64.b64encode(focused).decode(),
            "blurred": "data:image/png;base64," + base64.b64encode(blurred).decode(),
            "sides": ring["sides"]})
    finally:
        canvas.close()
    return ring, {side: hit / total for side, (hit, total) in changed.items() if total}


def test_every_view_shows_its_own_ring(browser, open_panel):
    """#1471: what a focused view's ring shows, read in pixels, because the sweep's clip
    check cannot see a child painted over a ring. A view that fills `main` is clipped
    by it, so it draws the inset ring, and at least three of its sides show (a sticky
    heading may cover the top). Every other view keeps the outside ring, and every side
    inside the viewport shows: an inset ring there is lost under the view's own sticky
    heading. The views no rail button opens (Manage account, Engine detail, the source
    editor) are measured too, and their controls swept."""
    page = open_panel(signed_in=ACCOUNT)
    page.keyboard.press("Tab")  # keyboard modality; views are switched by script, not a click
    views = page.eval_on_selector_all("nav.side-rail button[data-view]", "buttons => buttons.map(b => b.dataset.view)")
    measured, seen = {}, {"controls": 0, "opened": 0, "ringless": [], "clipped": [], "doubled": [], "faded": []}

    def open_view(script: str, view_id: str) -> None:
        page.evaluate(script)
        page.wait_for_selector(f"#{view_id}:not(.hidden)")
        page.wait_for_function(SETTLED, timeout=3000)

    for view in views:
        open_view(f"() => document.querySelector('nav.side-rail button[data-view=\"{view}\"]').click()", f"view-{view}")
        measured[view] = _ring_seen(browser, page, f"view-{view}")
    beyond_the_rail = [
        ("manage-account", "profile", "() => document.querySelector('#manage-account').click()"),
        ("engine-detail", "engines", "() => document.querySelector('#view-engines .engine-row').click()"),
        ("source-edit", "sources", "() => document.querySelector('[data-edit-source]').click()"),
    ]
    for view, home, opener in beyond_the_rail:
        open_view(f"() => document.querySelector('nav.side-rail button[data-view=\"{home}\"]').click()", f"view-{home}")
        open_view(opener, f"view-{view}")
        measured[view] = _ring_seen(browser, page, f"view-{view}")
        for key, value in sweep(page, view).items():
            seen[key] += value

    assert len(measured) >= 13, sorted(measured)
    wrong = {}
    for view, (ring, shares) in measured.items():
        shown = sorted(side for side, share in shares.items() if share >= 0.8)
        if ring["fills"]:
            ok = ring["offset"] < 0 and len(shown) >= 3
        else:
            ok = ring["offset"] > 0 and shown == sorted(shares)
        if not ok:
            wrong[view] = {"fills": ring["fills"], "offset": ring["offset"],
                           "shown": {side: round(share, 2) for side, share in shares.items()}}
    assert not wrong, f"views whose own ring is not seen as it should be: {wrong}"
    assert seen["controls"] >= 20, seen
    assert not seen["ringless"], f"controls that draw no focus ring: {seen['ringless']}"
    assert not seen["clipped"], f"controls whose ring shows on fewer than two sides: {seen['clipped']}"
    assert not seen["doubled"], f"fields that draw a ring or gap under their wrapper's: {seen['doubled']}"
    assert not seen["faded"], f"controls whose ring is painted below full opacity: {seen['faded']}"


def test_every_control_on_the_data_page_draws_the_ring(open_data):
    """The grid has two homes, and the web UI's was the only one swept: the same check,
    over the extension's Data page (extension/data.html) with its grid drawn."""
    page = open_data()
    page.keyboard.press("Tab")  # keyboard modality, so programmatic focus is :focus-visible
    seen = sweep(page, "data")
    # 28 when written, six of them the popup buttons in the grid's header.
    assert seen["controls"] >= 25, seen
    assert not seen["ringless"], f"controls that draw no focus ring: {seen['ringless']}"
    assert not seen["clipped"], f"controls whose ring shows on fewer than two sides: {seen['clipped']}"
    assert not seen["doubled"], f"fields that draw a ring or gap under their wrapper's: {seen['doubled']}"
    assert not seen["faded"], f"controls whose ring is painted below full opacity: {seen['faded']}"
