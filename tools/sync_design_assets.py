"""Synchronize generated design assets into both independently shipped UIs.

The Chrome extension and the Python package cannot import files from each
other at runtime. Canonical authored assets therefore live in ``design/`` and
are copied byte-for-byte into each distribution surface.

Usage:
    python tools/sync_design_assets.py
    python tools/sync_design_assets.py --check
"""
from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent

ASSETS = {
    ROOT / "design" / "appearance.js": (
        ROOT / "extension" / "appearance.js",
        ROOT / "scrapex" / "webui" / "static" / "appearance.js",
    ),
    # The one split-button behaviour, shared so the dataset Export control and
    # the Activity panel's log control cannot become two implementations.
    ROOT / "design" / "split-button.js": (
        ROOT / "extension" / "split-button.js",
        ROOT / "scrapex" / "webui" / "static" / "split-button.js",
    ),
    # ADDED 2026-08-11, and it was already duplicated for months before that.
    # `extension/timezone.js` and `scrapex/webui/static/timezone.js` were two
    # hand-maintained copies with no source between them, held equal by
    # `tests/test_display_time_zone.py::test_the_two_copies_of_the_module_are_identical`.
    # That test works — it was not a missing guard. What it could not do is say
    # which copy was right: its failure message read "copy one over the other",
    # and following it in the wrong direction reverts a fix as silently as no
    # test at all would have. Five files cross this boundary; four followed the
    # rule below and one had a rule of its own.
    ROOT / "design" / "timezone.js": (
        ROOT / "extension" / "timezone.js",
        ROOT / "scrapex" / "webui" / "static" / "timezone.js",
    ),
    ROOT / "design" / "tokens.css": (
        ROOT / "extension" / "tokens.css",
        ROOT / "scrapex" / "webui" / "static" / "tokens.css",
    ),
    ROOT / "design" / "components.css": (
        ROOT / "extension" / "components.css",
        ROOT / "scrapex" / "webui" / "static" / "components.css",
    ),
    ROOT / "design" / "material-icons.svg": (
        ROOT / "extension" / "icons" / "material-icons.svg",
        ROOT / "scrapex" / "webui" / "static" / "material-icons" / "material-icons.svg",
    ),
    # THE NOTICE SUPABASE IS OWED, distributed exactly as Google's is. R-74 makes
    # their design system this product's baseline rather than one option among
    # several, so the borrowing is structural: `design/tokens.css` carries values of
    # theirs, byte-exact or re-derived from their own expressions, and says which at
    # each value (#1017). Apache-2.0 section 4 wants attribution, the licence with the
    # derivative, and a prominent statement that files were changed; MIT wants the
    # notice in all copies. The file discharges both, because which of the two
    # governs `packages/ui` is genuinely ambiguous -- their root declares
    # Apache-2.0 and that package declares MIT with no licence text of its own.
    ROOT / "design" / "supabase.NOTICE.txt": (
        ROOT / "extension" / "supabase.NOTICE.txt",
        ROOT / "scrapex" / "webui" / "static" / "supabase.NOTICE.txt",
    ),
    ROOT / "design" / "material-icons.LICENSE.txt": (
        ROOT / "extension" / "icons" / "material-icons.LICENSE.txt",
        ROOT / "scrapex" / "webui" / "static" / "material-icons" / "material-icons.LICENSE.txt",
    ),
    # Google's own "G", byte-for-byte as they publish it. Not redrawn: an
    # invented path is a wrong logo that looks deliberate, and
    # developers.google.com/identity/branding-guidelines forbids altering it.
    ROOT / "design" / "google-g.png": (
        ROOT / "extension" / "icons" / "google-g.png",
        ROOT / "scrapex" / "webui" / "static" / "google-g.png",
    ),
    ROOT / "design" / "x-mark.svg": (
        ROOT / "extension" / "icons" / "x-mark.svg",
        ROOT / "scrapex" / "webui" / "static" / "x-mark.svg",
    ),
    # THE MARK IS TABLER'S x-mark (its class attribute says so), and MIT wants the notice in
    # every copy. So the notice travels to exactly the directories the mark does, taken
    # byte-for-byte from tabler/tabler-icons' LICENSE (#1045).
    ROOT / "design" / "x-mark.LICENSE.txt": (
        ROOT / "extension" / "icons" / "x-mark.LICENSE.txt",
        ROOT / "scrapex" / "webui" / "static" / "x-mark.LICENSE.txt",
    ),
}


# The catalogue is opened by double-clicking it — no server, no build — and a
# `file:` page is its own opaque origin, so it can load neither of the two
# assets it needs:
#
#   * `<use href="material-icons.svg#id">` is refused outright ("'file:' URLs
#     are treated as unique security origins") and every icon draws as an empty
#     box. So the exact sprite is inlined and `<use>` points at local symbols,
#     which is also what the Side Panel now does, for its own reason (below).
#   * `.brand-logo` is a CSS mask, and the mask image is blocked too — a
#     different resource type refused by the same rule. A failed mask hides the
#     element entirely, and no mask at all paints a solid black square, so both
#     failures look like a broken component rather than a blocked file.
#
# Both are therefore embedded, generated here, never hand-edited, and stale-
# checked exactly like every distributed copy above.
GALLERY = ROOT / "design" / "gallery.html"
SPRITE_OPEN = "  <!-- SPRITE:BEGIN generated by tools/sync_design_assets.py -->\n"
SPRITE_CLOSE = "  <!-- SPRITE:END -->"
MARK_OPEN = "    /* MARK:BEGIN generated by tools/sync_design_assets.py */\n"
MARK_CLOSE = "    /* MARK:END */"

# THE SIDE PANEL CARRIES THE SPRITE TOO, for a reason the catalogue does not
# have. Since Chrome 150 (Chromium f4800f1b, "Delay 'load' until after a <use>
# shadow tree has been attached") a <use> that points into another file holds
# the document's `load` until its shadow tree is built, and that build runs
# only in a layout pass. Chrome shows the Side Panel only after `load`, and a
# panel it has not shown yet is hidden and 0x0, so it gets no layout pass. The
# panel waited for `load` and `load` waited for the panel: blank until a click
# somewhere else (issue 1110; the measurement is beside the guard, in
# extension/tests/side-panel-startup.test.mjs).
#
# THE PANEL'S COPY PREFIXES EVERY ID, because the panel's own ids share its
# document. The sprite has a `check` symbol and the Test site button's id is
# `check`: `getElementById` and `<use href="#…">` both answer with the first
# element carrying an id. Unprefixed, one of the two loses: ahead of the button
# the symbol takes its click handler (the DOM harness did exactly that while it
# injected the unprefixed sprite), behind it every `#check` icon points at the
# button and draws nothing. `iconHref` in extension/app.js builds the same
# prefix, and extension/tests/side-panel-startup.test.mjs holds the two equal.
PANEL = ROOT / "extension" / "app.html"
PANEL_ICON_PREFIX = "icon-"


def _replace_between(page: Path, text: str, opener: str, closer: str, block: str) -> str:
    start = text.find(opener)
    end = text.find(closer, start) if start >= 0 else -1
    if end < 0:
        lost = (opener if start < 0 else closer).strip()
        raise ValueError(
            f"{page.name} has lost the marker {lost!r}, so its generated block "
            "cannot be checked; restore the marker")
    return text[:start] + block + text[end + len(closer):]


def _sprite_block(id_prefix: str = "") -> str:
    """The canonical sprite's symbols as one hidden inline <svg>, markers included."""
    sprite = (ROOT / "design" / "material-icons.svg").read_text(encoding="utf-8")
    body = sprite[sprite.index(">") + 1:sprite.rindex("</svg>")].strip("\n")
    if id_prefix:
        # Whitespace before `id`, so an attribute that merely ENDS in "id" (a
        # `data-id`, say) is never taken for the symbol's own.
        body = re.sub(r'(<symbol\b[^>]*?\sid=")', rf"\g<1>{id_prefix}", body)
    return (f'{SPRITE_OPEN}  <svg hidden aria-hidden="true">\n{body}\n  </svg>\n'
            f'{SPRITE_CLOSE}')


def _gallery_generated() -> str:
    """The catalogue's text with its embedded assets matching the canon."""
    import base64

    text = GALLERY.read_text(encoding="utf-8")
    text = _replace_between(GALLERY, text, SPRITE_OPEN, SPRITE_CLOSE, _sprite_block())

    # read_text, not read_bytes: git hands this file CRLF on Windows and LF on
    # Linux, and raw bytes therefore base64-encode to two different strings. CI
    # failed on exactly that — the generated block was "stale" on Linux and
    # current on the machine that wrote it. Universal newlines make the output
    # the same on both.
    mark = base64.b64encode(
        (ROOT / "design" / "x-mark.svg").read_text(encoding="utf-8").encode("utf-8")
    ).decode()
    return _replace_between(
        GALLERY, text, MARK_OPEN, MARK_CLOSE,
        f'{MARK_OPEN}    :root {{ --brand-mark: '
        f'url("data:image/svg+xml;base64,{mark}"); }}\n{MARK_CLOSE}')


def _panel_generated() -> str:
    """The panel's text with its embedded sprite matching the canon."""
    text = PANEL.read_text(encoding="utf-8")
    return _replace_between(
        PANEL, text, SPRITE_OPEN, SPRITE_CLOSE, _sprite_block(PANEL_ICON_PREFIX))


def sync(*, check: bool) -> list[Path]:
    stale: list[Path] = []
    for source, destinations in ASSETS.items():
        expected = source.read_bytes()
        for destination in destinations:
            if not destination.exists() or destination.read_bytes() != expected:
                stale.append(destination)
                if not check:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, destination)

    # Unconditional. This ran only while the sprite marker was present, so renaming
    # that one comment switched the check off and --check called the catalogue
    # current forever (#408). A lost marker or a missing catalogue now raises.
    embedded = _gallery_generated()
    if embedded != GALLERY.read_text(encoding="utf-8"):
        stale.append(GALLERY)
        if not check:
            GALLERY.write_text(embedded, encoding="utf-8")

    # The panel's block, under the same rule: a lost marker or a missing panel
    # raises, because a panel skipped here would be called current while every
    # icon it draws had nothing to point at.
    embedded = _panel_generated()
    if embedded != PANEL.read_text(encoding="utf-8"):
        stale.append(PANEL)
        if not check:
            PANEL.write_text(embedded, encoding="utf-8")
    return stale


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="report stale generated assets without changing them",
    )
    args = parser.parse_args()
    stale = sync(check=args.check)
    if args.check and stale:
        for path in stale:
            print(path.relative_to(ROOT))
        return 1
    for path in stale:
        print(f"updated {path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
