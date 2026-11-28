"""The sign-in card is Supabase's connect interstitial, measured in the panel (#1544).

He approved the design on 2026-11-26 from its drawings (#1544, stage 6). These guards hold
the values those drawings were measured against, at the three widths he uses (320, 400 and
480 px) and in both themes:

- the card: InterstitialLayout.tsx@86c813ec:69-88 on card.tsx:9-10;
- the opening check: LogoLoader.tsx@86c813ec:3-23, drawn with design/x-mark.svg's own
  outline, in --accent-ink (his choice of the departure, a mandate row in
  docs/DESIGN-SYSTEM-SOURCES.md);
- the contrast of every colour a sign-in state draws.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.extension]

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

pytest.importorskip("playwright")

from playwright.sync_api import sync_playwright  # noqa: E402

import panel_harness as harness  # noqa: E402

WIDTHS = (320, 400, 480)
SCHEMES = ("light", "dark")


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        instance = pw.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


@pytest.fixture()
def open_card(browser, tmp_path):
    pages = []

    def opener(*, width=400, height=800, scheme="light", ready="settled",
               reduced=False, **stub_kwargs):
        page_file = harness.build_page(tmp_path, harness.stub(**stub_kwargs),
                                       name=f"card{len(pages)}.html")
        context = browser.new_context(viewport={"width": width, "height": height},
                                      color_scheme=scheme,
                                      reduced_motion="reduce" if reduced else "no-preference")
        page = context.new_page()
        page.goto(page_file.as_uri())
        (harness.wait_until_settled if ready == "settled"
         else harness.wait_until_interactive)(page)
        page.evaluate(f"() => window.ScrapeXAppearance.set({{mode: 'manual', scheme: '{scheme}'}})")
        pages.append(context)
        return page

    try:
        yield opener
    finally:
        for context in pages:
            context.close()


CARD = """() => {
  const px = (v) => parseFloat(v);
  const card = document.getElementById('profile-card');
  const cs = getComputedStyle(card);
  const head = getComputedStyle(document.querySelector('.signin-header'));
  const logo = document.querySelector('.signin-logo');
  const ls = getComputedStyle(logo);
  const title = getComputedStyle(document.querySelector('#welcome-signed-out .signin-title'));
  const desc = getComputedStyle(document.getElementById('signin-purpose'));
  const stage = document.getElementById('profile-stage').getBoundingClientRect();
  const box = card.getBoundingClientRect();
  return {
    widthCap: box.width <= 400.5, inStage: box.left >= stage.left - 0.5 && box.right <= stage.right + 0.5,
    radius: px(cs.borderTopLeftRadius), border: px(cs.borderTopWidth),
    shadowed: cs.boxShadow !== 'none', padding: px(cs.paddingTop),
    headPadding: px(head.paddingTop), logo: [logo.offsetWidth, logo.offsetHeight],
    logoRadius: px(ls.borderTopLeftRadius), logoGap: px(ls.marginBottom),
    title: [px(title.fontSize), title.fontWeight, title.fontFamily.split(',')[0].replace(/["']/g, '')],
    titleLeading: px(title.lineHeight),
    desc: px(desc.fontSize), descEnds: document.getElementById('signin-purpose').textContent.trim().slice(-1),
    overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    fits: document.documentElement.scrollHeight <= innerHeight + 1,
  };
}"""


@pytest.mark.parametrize("scheme", SCHEMES)
@pytest.mark.parametrize("width", WIDTHS)
def test_the_signed_out_card_is_the_interstitials(open_card, width, scheme):
    """card.tsx:9-10 rounded-lg (8 px), a 1 px border, shadow-xs, max-w-[400px];
    InterstitialLayout.tsx:76-80 px-6 py-6 and a 48 px LogoBox, rounded-xl (12 px), mb-4;
    the title text-lg (16 px here, tokens.css's naming trap) at 500 in the sans face, on
    the leading Tailwind pairs with text-lg, calc(1.75 / 1.125) (theme.css@v4.2.4:354),
    24.9 px; the description text-sm (13 px), with no full stop
    (connect-interstitials.mdx:267-268)."""
    page = open_card(width=width, scheme=scheme)
    page.wait_for_selector("#welcome-signed-out:visible")
    card = page.evaluate(CARD)

    assert card["widthCap"] and card["inStage"], card
    assert card["radius"] == 8 and card["border"] == 1 and card["shadowed"], card
    assert card["padding"] == 0 and card["headPadding"] == 24, card
    assert card["logo"] == [48, 48] and card["logoRadius"] == 12 and card["logoGap"] == 16, card
    assert card["title"] == [16, "500", "Inter"], card
    assert abs(card["titleLeading"] - 16 * 1.75 / 1.125) < 0.05, card
    assert card["desc"] == 13 and card["descEnds"] != ".", card
    assert card["overflowX"] <= 0 and card["fits"], card


LOADER = """() => {
  const svg = document.querySelector('#welcome-checking .welcome-loader');
  const s = getComputedStyle(svg);
  const root = getComputedStyle(document.documentElement);
  return {use: svg.querySelector('use') && svg.querySelector('use').getAttribute('href'),
          size: [svg.getBoundingClientRect().width, svg.getBoundingClientRect().height],
          stroke: s.stroke, ink: root.getPropertyValue('--accent-ink').trim(),
          dash: s.strokeDasharray, name: s.animationName, duration: s.animationDuration,
          curve: s.animationTimingFunction};
}"""


@pytest.mark.parametrize("scheme", SCHEMES)
def test_the_opening_check_is_logoloader_in_the_brand_ink(open_card, scheme):
    """LogoLoader: one 60 px outline with one dash running round it on its own timing,
    the two tokens; the colour is --accent-ink, his choice (1.96:1 against 5.15:1)."""
    page = open_card(scheme=scheme, signin_never_returns=True, ready="interactive")
    loader = page.evaluate(LOADER)

    assert loader["use"] == "#x-mark-outline", loader
    assert loader["size"] == [60, 60], loader
    probe = page.evaluate("""(ink) => { const e = document.createElement('i');
      e.style.color = ink; document.body.append(e); const c = getComputedStyle(e).color;
      e.remove(); return c; }""", loader["ink"])
    assert loader["stroke"] == probe, f"the loader is not drawn in --accent-ink: {loader}"
    assert loader["dash"] == "15.1px, 110.8px", loader
    assert loader["name"] == "sx-logo-loader", loader
    assert loader["duration"] == "1.15s", loader
    assert loader["curve"] == "cubic-bezier(0.39, 0.29, 0.5, 0.59)", loader


def test_reduced_motion_stops_the_loader_and_shows_the_whole_mark(open_card):
    page = open_card(signin_never_returns=True, ready="interactive", reduced=True)
    loader = page.evaluate(LOADER)
    assert loader["name"] == "none" and loader["dash"] == "none", loader


CONTRAST = """() => {
  const c = document.createElement('canvas').getContext('2d');
  const rgba = (v) => { c.fillStyle = '#000'; c.fillStyle = v; const s = c.fillStyle;
    if (s.startsWith('#')) { const n = parseInt(s.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255, 1]; }
    const p = s.match(/[\\d.]+/g).map(Number); return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1]; };
  const over = (t, b) => [0, 1, 2].map(i => t[i] * t[3] + b[i] * (1 - t[3])).concat(1);
  const backdrop = (el) => { const stack = [];
    for (let e = el; e; e = e.parentElement) { const v = rgba(getComputedStyle(e).backgroundColor);
      if (v[3] > 0) stack.push(v); if (v[3] >= 1) break; }
    let base = [255, 255, 255, 1]; for (let i = stack.length - 1; i >= 0; i--) base = over(stack[i], base);
    return base; };
  const lum = (p) => 0.2126 * f(p[0]) + 0.7152 * f(p[1]) + 0.0722 * f(p[2]);
  function f(v) { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; }
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const pair = (sel, prop) => { const el = document.querySelector(sel);
    const bg = backdrop(el); let fg = rgba(getComputedStyle(el)[prop]);
    if (fg[3] < 1) fg = over(fg, bg); return Math.round(ratio(fg, bg) * 100) / 100; };
  renderAccount({tokenProblem: {state: 'no-chrome-account', title: 'T', detail: 'D', interactive: true}});
  const box = document.getElementById('signin-problem-box');
  document.getElementById('signin-problem').textContent = 'x'; box.classList.remove('hidden');
  const status = document.getElementById('signin-status');
  status.textContent = 'x'; status.classList.remove('hidden');
  return {title: pair('#welcome-signed-out .signin-title', 'color'),
          description: pair('#signin-purpose', 'color'),
          status: pair('#signin-status', 'color'),
          error: pair('#signin-problem', 'color'),
          admonitionTitle: pair('#signin-blocked-title', 'color'),
          admonitionText: pair('#signin-blocked-description', 'color')};
}"""


@pytest.mark.parametrize("scheme", SCHEMES)
def test_every_sign_in_words_colour_is_readable(open_card, scheme):
    """WCAG 2.2 SC 1.4.3: 4.5:1 for each colour the card writes words in, read from the
    drawn page; the 12 px action error included."""
    page = open_card(scheme=scheme)
    page.wait_for_selector("#welcome-signed-out:visible")
    ratios = page.evaluate(CONTRAST)
    assert all(value >= 4.5 for value in ratios.values()), ratios


@pytest.mark.parametrize("scheme", SCHEMES)
def test_the_loader_meets_three_to_one_on_the_page(open_card, scheme):
    """WCAG 2.2 SC 1.4.11: while it shows, the loader is the only thing on the page. This is
    the mandate's reason, so it is guarded: --brand-default measured 1.96:1 on light."""
    page = open_card(scheme=scheme, signin_never_returns=True, ready="interactive")
    ratio = page.evaluate("""() => {
      const c = document.createElement('canvas').getContext('2d');
      const rgb = (v) => { c.fillStyle = '#000'; c.fillStyle = v; const s = c.fillStyle;
        if (s.startsWith('#')) { const n = parseInt(s.slice(1), 16); return [n >> 16 & 255, n >> 8 & 255, n & 255]; }
        return s.match(/[\\d.]+/g).slice(0, 3).map(Number); };
      const f = (v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
      const lum = (p) => 0.2126 * f(p[0]) + 0.7152 * f(p[1]) + 0.0722 * f(p[2]);
      const a = rgb(getComputedStyle(document.querySelector('.welcome-loader')).stroke);
      const b = rgb(getComputedStyle(document.getElementById('view-profile')).backgroundColor);
      const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
      return (x + 0.05) / (y + 0.05); }""")
    assert ratio >= 3, ratio
