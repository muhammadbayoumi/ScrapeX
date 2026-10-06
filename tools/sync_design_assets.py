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
import json
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
    # THE ONE GLYPH MAP (#1056), beside the engine's sprite, where scrapex/ui_manifest.py
    # reads it for the sidebar. The panel's copy is the block _panel_generated writes
    # into app.html below, beside its inline sprite and for the same reason.
    ROOT / "design" / "glyph-map.json": (
        ROOT / "scrapex" / "webui" / "static" / "material-icons" / "glyph-map.json",
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
    # THE DATA PAGE'S GRID, authored here so the extension's Data page runs the
    # engine's own grid rather than a second one (#1198). The engine's copies keep
    # the paths its templates already load. The extension's sit flat beside
    # data.html, which loads them, as every other extension page's files do.
    ROOT / "design" / "grid.js": (
        ROOT / "scrapex" / "webui" / "static" / "grid.js",
        ROOT / "extension" / "grid.js",
    ),
    ROOT / "design" / "ui.js": (
        ROOT / "scrapex" / "webui" / "static" / "ui.js",
        ROOT / "extension" / "ui.js",
    ),
    ROOT / "design" / "grid-theme.css": (
        ROOT / "scrapex" / "webui" / "static" / "grid-theme.css",
        ROOT / "extension" / "grid-theme.css",
    ),
    ROOT / "design" / "table-theme.css": (
        ROOT / "scrapex" / "webui" / "static" / "table-theme.css",
        ROOT / "extension" / "table-theme.css",
    ),
    ROOT / "design" / "data-workspace.css": (
        ROOT / "scrapex" / "webui" / "static" / "pages" / "data-workspace.css",
        ROOT / "extension" / "data-workspace.css",
    ),
    # THE FOUR FACES (#1048), each beside its own OFL.txt, which the licence asks to
    # travel with every copy. They land in a fonts/ directory beside each surface's
    # tokens.css, so the one relative url() its @font-face blocks write resolves on both.
    # Binary, and copied as bytes like google-g.png: `*.ttf binary` in .gitattributes is
    # what keeps git from normalising them, and tests/test_the_faces_ship_with_their_licences.py
    # holds each to google/fonts' own digest.
    **{
        ROOT / "design" / "fonts" / face: (
            ROOT / "extension" / "fonts" / face,
            ROOT / "scrapex" / "webui" / "static" / "fonts" / face,
        )
        for face in (
            "inter/Inter-opsz-wght.ttf", "inter/OFL.txt",
            "manrope/Manrope-wght.ttf", "manrope/OFL.txt",
            "sourcecodepro/SourceCodePro-wght.ttf", "sourcecodepro/OFL.txt",
            "notosansarabic/NotoSansArabic-wdth-wght.ttf", "notosansarabic/OFL.txt",
        )
    },
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
# THE PANEL'S COPY KEEPS THE SPRITE'S IDS, because every id already carries its
# source's key (design/glyph-map.json's rule, #1056), and the panel's own ids share
# its document. `getElementById` and `<use href="#…">` both answer with the first
# element carrying an id: when the sprite's `check` met the Test site button's id
# `check`, one of the two lost, so the panel's copy prefixed every id with `icon-`.
# `material-check` is no word a panel element is named by, and
# tests/test_panel_wiring.py fails on any id two elements carry.
PANEL = ROOT / "extension" / "app.html"

# THE PANEL CARRIES THE GLYPH MAP TOO (#1056), as a JSON data block beside its
# sprite, and app.js reads it from there synchronously at startup. A JSON module
# import needs import attributes, Chrome 123, and the manifest's floor is 116; a
# fetch would put a request and a failure mode back on the startup path the sprite
# was inlined to clear. A data block is not a script, so MV3's CSP does not apply.
# The file's text is carried verbatim, so the block IS the map: `</` would end the
# element early, and is refused rather than escaped.
GLYPHS_OPEN = "  <!-- GLYPH-MAP:BEGIN generated by tools/sync_design_assets.py -->\n"
GLYPHS_CLOSE = "  <!-- GLYPH-MAP:END -->"

# THE RAIL'S TABS FOR THE PANEL'S OWN DESTINATIONS DRAW THE MAP'S GLYPH TOO (#1056).
# Data and Settings are the panel's own pages, so its Workspace menu leaves them
# out (extension/app.js PANEL_DESTINATIONS) and their rail tab is the panel's entry
# for that destination. Each such <use> names its destination in this attribute,
# and its href is written here from the map, so a renamed glyph moves the rail
# with the menu and the sidebar, and the panel does no work for it at startup.
RAIL_GLYPH = re.compile(r'<use href="#[^"]*" data-glyph-destination="([^"]*)">')


def _replace_between(page: Path, text: str, opener: str, closer: str, block: str) -> str:
    start = text.find(opener)
    end = text.find(closer, start) if start >= 0 else -1
    if end < 0:
        lost = (opener if start < 0 else closer).strip()
        raise ValueError(
            f"{page.name} has lost the marker {lost!r}, so its generated block "
            "cannot be checked; restore the marker")
    return text[:start] + block + text[end + len(closer):]


def _sprite_block() -> str:
    """The canonical sprite's symbols as one hidden inline <svg>, markers included."""
    sprite = (ROOT / "design" / "material-icons.svg").read_text(encoding="utf-8")
    body = sprite[sprite.index(">") + 1:sprite.rindex("</svg>")].strip("\n")
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


def _glyph_map_block() -> str:
    """The canonical glyph map as app.html's data block, markers included."""
    text = (ROOT / "design" / "glyph-map.json").read_text(encoding="utf-8")
    json.loads(text)  # a map that does not parse would stop the panel at startup
    if "</" in text:
        raise ValueError("design/glyph-map.json contains '</', which would end "
                         "app.html's glyph-map block early")
    return (f'{GLYPHS_OPEN}  <script type="application/json" id="glyph-map">\n'
            f'{text}</script>\n{GLYPHS_CLOSE}')


def _rail_glyphs(text: str) -> str:
    """The panel's text with each data-glyph-destination <use> drawing the map's glyph."""
    destinations = json.loads(
        (ROOT / "design" / "glyph-map.json").read_text(encoding="utf-8"))["destinations"]

    def written(found: re.Match) -> str:
        key = found.group(1)
        if key not in destinations:
            raise ValueError(f"{PANEL.name} draws the glyph of destination {key!r}, "
                             "which design/glyph-map.json does not name")
        return (f'<use href="#{destinations[key]}" '
                f'data-glyph-destination="{key}">')

    text, drawn = RAIL_GLYPH.subn(written, text)
    # Refused, like a lost marker (#408): with no attribute left, the rail would
    # drop out of the sync and be called current whatever the map said.
    if not drawn:
        raise ValueError(f"{PANEL.name} has lost every data-glyph-destination <use>, "
                         "so its rail's glyphs cannot be checked; restore them")
    return text


def _panel_generated() -> str:
    """The panel's text with its embedded sprite, its glyph map and its rail's
    destination glyphs matching the canon."""
    text = PANEL.read_text(encoding="utf-8")
    text = _replace_between(
        PANEL, text, SPRITE_OPEN, SPRITE_CLOSE, _sprite_block())
    text = _replace_between(PANEL, text, GLYPHS_OPEN, GLYPHS_CLOSE, _glyph_map_block())
    return _rail_glyphs(text)


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
