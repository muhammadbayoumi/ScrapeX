"""The shared Admonition draws each of Supabase's three types in its own tokens (#2026).

Admonition.tsx@86c813ec:40-112 on alert.tsx:6-27:

- a note is the default box, `border-default`, with a `foreground-muted` badge;
- a warning takes its 200 fill and 400 border, and a destructive alert the same steps of its
  own scale;
- the badge, AdmonitionTypeIcon (AdmonitionIcons.tsx@86c813ec:15-20), takes the 600 step,
  with the glyph in the 200 step.

A note may carry a description alone. Its empty title is not drawn, and its words sit
`my-0.5` lower (Admonition.tsx:72), where a title's line would have centred them beside the
badge.

The catalogue, design/gallery.html, draws all three types, so the guard reads them there. The
sign-in card that uses the component (part 2, #2015) draws only the warning, so without this
guard the destructive colours and the title-less note were held by nothing (#2026's merge
gate). Each value is waited for with a bound, not read once.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.extension]

pytest.importorskip("playwright")

from playwright.sync_api import TimeoutError as PlaywrightTimeout  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
GALLERY = ROOT / "design" / "gallery.html"

#: Each drawn value against its token, both resolved by the page itself.
DRAWN = """() => {
  const token = (name) => { const probe = document.createElement('i');
    probe.style.color = `var(${name})`; document.body.append(probe);
    const value = getComputedStyle(probe).color; probe.remove(); return value; };
  const [note, warning, danger] = document.querySelectorAll('.g-demo .admonition');
  const look = (box, part) => getComputedStyle(part ? box.querySelector(part) : box);
  return {
    'note border': look(note).borderTopColor === token('--line'),
    'note badge': look(note, '.admonition-icon').backgroundColor === token('--text-subtle'),
    'note title not drawn': look(note, '.admonition-title').display === 'none',
    'note words lowered 2px': look(note, '.admonition-text').marginTop === '2px',
    'warning fill': look(warning).backgroundColor === token('--warning-200'),
    'warning border': look(warning).borderTopColor === token('--warning-400'),
    'warning badge': look(warning, '.admonition-icon').backgroundColor === token('--warning-600'),
    'warning glyph': look(warning, '.admonition-icon').color === token('--warning-200'),
    'warning words not lowered': look(warning, '.admonition-text').marginTop === '0px',
    'destructive fill': look(danger).backgroundColor === token('--destructive-200'),
    'destructive border': look(danger).borderTopColor === token('--destructive-400'),
    'destructive badge': look(danger, '.admonition-icon').backgroundColor === token('--destructive-600'),
    'destructive glyph': look(danger, '.admonition-icon').color === token('--destructive-200'),
  };
}"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        instance = pw.chromium.launch()
        try:
            yield instance
        finally:
            instance.close()


@pytest.mark.parametrize("scheme", ("light", "dark"))
def test_each_admonition_type_draws_its_own_tokens(browser, scheme):
    context = browser.new_context(color_scheme=scheme)
    try:
        page = context.new_page()
        page.goto(GALLERY.as_uri())
        try:
            page.wait_for_function(f"() => Object.values(({DRAWN})()).every(Boolean)",
                                   timeout=5_000)
        except PlaywrightTimeout:
            pass  # the assertion below names each value that never arrived
        drawn = page.evaluate(DRAWN)
        assert all(drawn.values()), (
            f"{scheme}: Admonition values not in their tokens: "
            f"{[name for name, ok in drawn.items() if not ok]}")
    finally:
        context.close()
