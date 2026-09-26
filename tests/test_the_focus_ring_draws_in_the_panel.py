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


SWEEP = r"""async () => {
  const probe = document.createElement('span'); document.body.append(probe);
  probe.style.color = 'var(--focus-ring-color)';
  const ring = getComputedStyle(probe).color; probe.remove();
  const draws = (el) => { const s = getComputedStyle(el);
    return s.boxShadow.includes(ring) || (s.outlineStyle !== 'none' && s.outlineColor === ring); };
  // The controls a phase-4 item rebuilds keep their own ring until it lands (the static
  // guard's LEFT_TO); for them an outline of any colour is what is asked. A shadow does
  // not count: the gap every control paints is a shadow, in the background's colour.
  const leftTo = (el) => el.closest('.m3-switch, .appearance-switch, .split-button-trigger, .finance-converter-select-trigger');
  const visible = (el) => { const s = getComputedStyle(el);
    return s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0 && s.outlineColor !== 'rgba(0, 0, 0, 0)'; };
  const settle = (el) => new Promise(done => { const start = performance.now();
    const tick = () => (el.getAnimations().length === 0 || performance.now() - start > 1000)
      ? done() : requestAnimationFrame(tick); tick(); });
  const views = [...document.querySelectorAll('nav.side-rail button[data-view]')].map(b => b.dataset.view);
  const seen = {views: views.length, controls: 0, opened: 0, ringless: []};
  for (const view of views) {
    document.querySelector(`nav.side-rail button[data-view="${view}"]`).click();
    await new Promise(done => setTimeout(done, 120));
    // A control inside a closed disclosure cannot take focus, so each one is opened first;
    // otherwise the switches in the finance preferences are never measured.
    document.querySelectorAll('details:not([open])').forEach(d => { d.open = true; seen.opened++; });
    await new Promise(done => setTimeout(done, 120));
    const focusable = [...document.querySelectorAll(
        'button, a[href], input, select, textarea, summary, [tabindex]:not([tabindex="-1"])')]
      .filter(el => !el.disabled && el.offsetParent !== null);
    for (const el of focusable) {
      el.focus();
      if (document.activeElement !== el) continue;
      await settle(el);
      seen.controls++;
      let at = el;
      while (at && !(leftTo(el) ? visible(at) : draws(at))) at = at.parentElement;
      // The two switches draw their ring on the track that follows the hidden input.
      if (!at && leftTo(el) && el.nextElementSibling && visible(el.nextElementSibling)) at = el.nextElementSibling;
      if (!at) seen.ringless.push(`${view}: ${el.tagName.toLowerCase()}${el.id ? '#' + el.id : ''}`);
    }
  }
  return seen;
}"""


def test_every_control_in_every_view_draws_the_ring(open_panel):
    """#721's acceptance: the ring is still visible on every control the panel shows. Each
    focusable control in each rail view, with every disclosure open, is focused from the
    keyboard, and it, or the wrapper that draws the ring for it, must paint the ring colour."""
    page = open_panel()
    page.keyboard.press("Tab")
    seen = page.evaluate(SWEEP)
    assert seen["views"] >= 10 and seen["controls"] >= 250 and seen["opened"] >= 40, seen
    assert not seen["ringless"], f"controls that draw no focus ring: {seen['ringless']}"
