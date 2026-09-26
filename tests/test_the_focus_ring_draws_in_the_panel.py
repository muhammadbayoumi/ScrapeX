"""The focus ring the panel draws is Supabase's `focus-ring`, measured in a browser (#721):
a 2px ring at a 2px offset painted in the background. The outline draws the ring, so no
control's own box-shadow can take it away, and a shadow paints the gap."""
from __future__ import annotations

import pytest

pytest.importorskip("playwright")
from tests.test_panel_dom import browser, open_panel  # noqa: E402,F401  (the fixtures)

# Guards the extension's panel; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

READ = """() => {
  const el = document.activeElement, s = getComputedStyle(el);
  const probe = document.createElement('span'); document.body.append(probe);
  const colour = (v) => { probe.style.color = ''; probe.style.color = v; return getComputedStyle(probe).color; };
  const read = {id: el.id, visible: el.matches(':focus-visible'), shadow: s.boxShadow,
                outline: [s.outlineStyle, s.outlineWidth, s.outlineColor, s.outlineOffset],
                bg: colour('var(--bg)'), ring: colour('var(--focus-ring-color)')};
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
  // An element nobody can see draws nothing, however its outline computes: the Source
  // view's radios are opacity 0, and the card around them is what draws the ring.
  const paintable = (el) => {
    if (getComputedStyle(el).visibility === 'hidden') return false;
    let opacity = 1;
    for (let at = el; at; at = at.parentElement) opacity *= parseFloat(getComputedStyle(at).opacity);
    return opacity > 0.05;
  };
  // Whether any side of the outline survives every ancestor that clips, and the viewport:
  // a ring an overflow cuts on all four sides is computed and never seen.
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
    return (down && clip.l < inner.l - 0.5 && clip.r > outer.l + 0.5)
        || (down && clip.r > inner.r + 0.5 && clip.l < outer.r - 0.5)
        || (across && clip.t < inner.t - 0.5 && clip.b > outer.t + 0.5)
        || (across && clip.b > inner.b + 0.5 && clip.t < outer.b - 0.5);
  };
  const settle = (el) => new Promise(done => { const start = performance.now();
    const tick = () => (el.getAnimations().length === 0 || performance.now() - start > 1000)
      ? done() : requestAnimationFrame(tick); tick(); });
  const name = (el) => `${where}: ${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}`
    + [...el.classList].map(c => '.' + c).join('');
  const seen = {controls: 0, opened: 0, ringless: [], clipped: [], doubled: []};
  // A control inside a closed disclosure cannot take focus, so each one is opened first;
  // otherwise the switches in the finance preferences are never measured.
  document.querySelectorAll('details:not([open])').forEach(d => { d.open = true; seen.opened++; });
  await new Promise(done => setTimeout(done, 120));
  const focusable = [...document.querySelectorAll(
      'button, a[href], input, select, textarea, summary, [tabindex]:not([tabindex="-1"])')]
    .filter(el => !el.disabled && el.offsetParent !== null && !(skip && el.matches(skip)));
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
    if (!shown(drawers[0])) seen.clipped.push(name(el));
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
    where it can be seen (not an invisible element, not cut off on all four sides by an
    ancestor that clips), and a field under a wrapper must not draw a second ring or gap."""
    page = open_panel()
    page.keyboard.press("Tab")  # keyboard modality; the views are switched by script, not a click
    views = page.eval_on_selector_all("nav.side-rail button[data-view]", "buttons => buttons.map(b => b.dataset.view)")
    seen = {"controls": 0, "opened": 0, "ringless": [], "clipped": [], "doubled": []}
    for view in views:
        page.evaluate("""(view) => new Promise(done => {
          document.querySelector(`nav.side-rail button[data-view="${view}"]`).click();
          setTimeout(done, 120);
        })""", view)
        for key, value in sweep(page, view).items():
            seen[key] += value
    assert len(views) >= 10 and seen["controls"] >= 250 and seen["opened"] >= 40, seen
    assert not seen["ringless"], f"controls that draw no focus ring: {seen['ringless']}"
    assert not seen["clipped"], f"controls whose ring is cut off on every side: {seen['clipped']}"
    assert not seen["doubled"], f"fields that draw a ring or gap under their wrapper's: {seen['doubled']}"
