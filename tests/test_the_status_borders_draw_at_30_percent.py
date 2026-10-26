"""Supabase's four status borders draw as their status colour at 30%, in both schemes (#633).

semantic.css@86c813ec:167 and :250 define --border-{destructive,warning,info} as the status
colour at 30% and --border-brand as their --primary, oklch(0.76 0.15 159), at 30%, the same
in both schemes. The expected values below are those, evaluated; they are not read back from
the tokens they check. The warning Button is the one rule that draws a status border today
(Button.tsx@86c813ec:85-100), so it is measured where it is drawn.
"""
from __future__ import annotations

import pytest

pytest.importorskip("playwright")
from tests.test_panel_dom import _alpha, _channels, browser, open_panel  # noqa: E402,F401  (the fixtures)

# Guards the extension's panel; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

EXPECTED = {
    "light": {"destructive": (171, 65, 62), "warning": (202, 138, 16), "info": (108, 94, 186), "brand": (69, 205, 142)},
    "dark": {"destructive": (250, 136, 128), "warning": (242, 175, 72), "info": (155, 143, 240), "brand": (69, 205, 142)},
}
READ = """() => {
  const probe = document.createElement('span'); document.body.append(probe);
  const colour = (v) => { probe.style.color = ''; probe.style.color = v; return getComputedStyle(probe).color; };
  const out = {};
  for (const name of ['destructive', 'warning', 'info', 'brand']) out[name] = colour(`var(--border-${name})`);
  const button = Object.assign(document.createElement('button'), {className: 'warning', textContent: 'Turn off'});
  document.querySelector('main').append(button);
  out.button = getComputedStyle(button).borderTopColor;
  probe.remove(); button.remove();
  return out;
}"""


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_each_status_border_is_its_colour_at_30_percent(open_panel, scheme):
    page = open_panel()
    page.evaluate("(s) => window.ScrapeXAppearance.set({mode: 'manual', scheme: s, palette: 'supabase'})", scheme)
    read = page.evaluate(READ)
    for name, rgb in EXPECTED[scheme].items():
        drawn = [round(channel * 255) for channel in _channels(read[name])]
        assert all(abs(a - b) <= 1 for a, b in zip(drawn, rgb)), (scheme, name, read[name], rgb)
        assert abs(_alpha(read[name]) - 0.30) <= 0.005, (scheme, name, read[name])
    assert read["button"] == read["warning"], f"the warning Button's border is not --border-warning: {read}"
