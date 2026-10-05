"""Each shadow token is the string Supabase's atoms render, and each overlay casts its atom's (#1049).

WHERE THE VALUES COME FROM. Supabase authors no shadow token: none of the 29 CSS files at the
pin under apps/design-system, packages/config, packages/ui and packages/ui-patterns declares
--shadow-*, and tests/fixtures/supabase-design-tokens.json holds no name containing "shadow".
Their atoms write Tailwind's `shadow-*` classes, so what they render is Tailwind's theme at the
version their lockfile resolves for packages/ui -- tailwindcss 4.2.4, pnpm-lock.yaml@86c813ec:
2618-2620. That is the value Supabase renders, not a second source
(docs/DESIGN-SYSTEM-SOURCES.md, "Tailwind's values, stated once").

WHAT WAS TRUE BEFORE. The four were this product's own: one tint, rgb(3 3 3 / 0.06), at offsets
of its own, re-declared darker in both dark blocks. There was no --shadow-md, so every menu,
popover and select cast --shadow-lg or the bare --shadow where Supabase's cast shadow-md.

THE OVERLAY TABLE IS AN EQUALITY, not a list of cases. A new surface that reads --shadow-md or
--shadow-lg fails until it is named here with the atom it maps to, so a popover cannot arrive
casting a Sheet's shadow because the nearest example did.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.test_the_provenance_markers_say_who_owns_each_value import (
    BLOCKS, _blocks, _without_comment_bodies)
from tests.test_ui_kit import _live_markup
from tools.value_literals import SUPABASE, authored, declarations

# Reads extension/app.css and the design/ sources copied into extension/;
# see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
NOTICE = ROOT / "design" / "supabase.NOTICE.txt"
GALLERY = ROOT / "design" / "gallery.html"
APP_CSS = ROOT / "extension" / "app.css"

#: The tailwindcss the pin's lockfile resolves, which is the theme the strings below are from.
TAILWIND = "4.2.4"

#: packages/tailwindcss/theme.css@v4.2.4:407-410, verbatim.
SHADOWS = {
    "--shadow-xs": "0 1px 2px 0 rgb(0 0 0 / 0.05)",
    "--shadow-sm": "0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)",
    "--shadow-md": "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
    "--shadow-lg": "0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)",
}

# Supabase's atoms at the pin, packages/ui/src/components/shadcn/ui/, and the class each casts.
MENU = "dropdown-menu.tsx@86c813ec:87 shadow-md"
POPOVER = "popover.tsx@86c813ec:49 shadow-md"
SELECT = "select.tsx@86c813ec:110 shadow-md"
DIALOG = "dialog.tsx@86c813ec:67 shadow-md dark:shadow-xs"
# modality.mdx@86c813ec:64: "Sheets are dialogs presented as side panels."
SHEET = "sheet.tsx@86c813ec:63 shadow-lg"

#: (authored sheet, selector) -> (the token it reads, the atom that says so).
OVERLAYS = {
    ("design/components.css", ".split-button-options"): ("--shadow-md", MENU),
    ("design/data-workspace.css", ".dataset-menu-popover"): ("--shadow-md", MENU),
    ("design/data-workspace.css", ".dataset-popover"): ("--shadow-md", POPOVER),
    ("design/grid-theme.css", ".tabulator-menu, .tabulator-popup-container"): ("--shadow-md", MENU),
    ("design/grid-theme.css", ".grid-feature-popover"): ("--shadow-md", POPOVER),
    ("design/grid-theme.css", ".column-chooser"): ("--shadow-lg", SHEET),
    ("extension/app.css", ".sx-select-list"): ("--shadow-md", SELECT),
    ("extension/app.css", ".account-menu"): ("--shadow-md", MENU),
    ("extension/app.css", ".finance-converter-options"): ("--shadow-md", SELECT),
    ("extension/app.css", ".modal-card"): ("--shadow-md", DIALOG),
    ("extension/app.css", ".workspace-menu"): ("--shadow-lg", SHEET),
    ("scrapex/webui/static/webui.css", ".source-filter-popover"): ("--shadow-md", POPOVER),
    ("scrapex/webui/static/webui.css", ".sidebar-ready .workspace-sidebar"): ("--shadow-lg", SHEET),
}

#: The Dialog's dark half, in both of the ways a dark scheme is reached.
DIALOG_IN_DARK = (':root[data-theme="dark"] .modal-card', ':root:not([data-theme="light"]) .modal-card')

SHADOW_READ = re.compile(r"var\((--shadow(?:-[a-z0-9]+)?)\)")

#: tokens.css's three declaration blocks, in BLOCKS's order, by the name a reader knows them by.
LIGHT, DARK, DEVICE_DARK = (":root", ':root[data-theme="dark"]',
                            ':root:not([data-theme="light"]) in prefers-color-scheme: dark')


def _declared() -> dict[tuple[str, str], str]:
    """(block, token) -> value, for every declaration in tokens.css's three blocks."""
    assert len(BLOCKS) == 3, f"tokens.css is read as {len(BLOCKS)} blocks; name each one here"
    found = {}
    for name, (_, block) in zip((LIGHT, DARK, DEVICE_DARK), _blocks()):
        for m in re.finditer(r"^\s*(--[a-z0-9-]+)\s*:\s*([^;]+);", _without_comment_bodies(block), re.M):
            found[(name, m.group(1))] = " ".join(m.group(2).split())
    return found


def _box_shadows() -> list[tuple[str, str, str]]:
    """(sheet, selector, value) for every box-shadow in a sheet this repository authors."""
    return [(sheet.relative_to(ROOT).as_posix(), selector, value)
            for sheet in authored()
            for selector, prop, value, _line in declarations(sheet.read_text(encoding="utf-8"))
            if prop == "box-shadow"]


def test_the_pin_still_resolves_the_tailwind_these_strings_are_from():
    """A re-pin that moves Tailwind moves what Supabase's atoms render, and these with it."""
    reading = json.loads(SUPABASE.read_text(encoding="utf-8"))
    assert reading["tailwind"] == TAILWIND, (
        f"the pin now resolves tailwindcss {reading['tailwind']}, and SHADOWS are "
        f"theme.css@v{TAILWIND}:407-410. Read the four strings at the new version and "
        f"put them in design/tokens.css and here in the same change.")


@pytest.mark.parametrize("token", sorted(SHADOWS))
def test_each_shadow_token_is_the_string_tailwinds_theme_declares(token):
    light = _declared().get((LIGHT, token))
    assert light == SHADOWS[token], (
        f"design/tokens.css's :root declares {token} as {light!r}. Supabase's atoms render "
        f"{SHADOWS[token]!r}: tailwindcss/theme.css@v{TAILWIND}, the version their lockfile "
        f"resolves at the pin (#1049).")


def test_no_dark_block_re_declares_a_shadow():
    """Supabase renders the same shadow-* classes in both schemes. The one atom that swaps is
    the Dialog, and it swaps at the atom (`dark:shadow-xs`), not by re-toning a token."""
    redeclared = sorted(f"{block} {token}" for (block, token) in _declared()
                        if block != LIGHT and token.startswith("--shadow"))
    assert not redeclared, (
        f"a dark block re-declares {redeclared}. Supabase's shadow-* classes resolve to "
        f"Tailwind's theme in both schemes, so dark re-toning is this product's own (#1049).")


@pytest.mark.parametrize("where", sorted(OVERLAYS), ids=lambda key: f"{key[0]} {key[1]}")
def test_each_overlay_casts_the_shadow_its_supabase_atom_renders(where):
    sheet, selector = where
    token, atom = OVERLAYS[where]
    cast = [value for name, sel, value in _box_shadows() if name == sheet and sel == selector]
    assert cast == [f"var({token})"], (
        f"{sheet} `{selector}` casts {cast or 'nothing'}; its atom is {atom}, which is "
        f"var({token}) here.")


def test_every_raised_overlay_is_named_with_its_atom():
    """The equality: every read of --shadow-md or --shadow-lg is in OVERLAYS, and nothing
    in OVERLAYS has stopped reading it."""
    raised = {(sheet, selector): read
              for sheet, selector, value in _box_shadows()
              for read in SHADOW_READ.findall(value) if read in {"--shadow-md", "--shadow-lg"}}
    expected = {where: token for where, (token, _atom) in OVERLAYS.items()}
    assert raised == expected, (
        f"reads of --shadow-md/-lg and OVERLAYS disagree.\n"
        f"  read, not named: {sorted(set(raised.items()) - set(expected.items()))}\n"
        f"  named, not read: {sorted(set(expected.items()) - set(raised.items()))}\n"
        f"Name the surface with the Supabase atom it maps to, and cast what that atom casts.")


@pytest.mark.parametrize("selector", DIALOG_IN_DARK)
def test_the_dialog_drops_to_xs_in_dark(selector):
    """Their Dialog is `border shadow-md dark:shadow-xs`: the border is unconditional and the
    shadow is the part that goes, because dark plates sit too close for a blur to separate."""
    cast = [value for name, sel, value in _box_shadows()
            if name == "extension/app.css" and sel == selector]
    assert cast == ["var(--shadow-xs)"], (
        f"extension/app.css `{selector}` casts {cast or 'nothing'}; {DIALOG}.")


def test_the_dialogs_device_dark_drop_is_inside_the_dark_media_query():
    """`:root:not([data-theme="light"])` matches a light device too: only the media query
    around it makes it dark. The test above reads the selector and not its @media, so moving
    the rule under `prefers-color-scheme: light` passed it and dropped the light Dialog to xs."""
    css = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)),
                 APP_CSS.read_text(encoding="utf-8"), flags=re.S)
    bodies = []
    for match in re.finditer(r"@media\s*\(\s*prefers-color-scheme\s*:\s*dark\s*\)\s*\{", css):
        depth, end = 1, match.end()
        while depth:
            depth += {"{": 1, "}": -1}.get(css[end], 0)
            end += 1
        bodies.append(css[match.end():end - 1])
    device_dark = DIALOG_IN_DARK[1]
    cast = [value for body in bodies for selector, prop, value, _line in declarations(body)
            if selector == device_dark and prop == "box-shadow"]
    assert cast == ["var(--shadow-xs)"], (
        f"inside extension/app.css's @media (prefers-color-scheme: dark), `{device_dark}` "
        f"casts {cast or 'nothing'}; {DIALOG}.")


def test_the_gallery_shows_the_four_shadows_and_quotes_no_retired_one():
    """The catalogue is where the four are seen side by side. Before #1049 it showed three,
    and its code sample quoted `--shadow-sm: 0 1px 3px var(--shadow-color)`."""
    gallery = GALLERY.read_text(encoding="utf-8")
    shown = {f"--{name}" for name in re.findall(r'class="[^"]*\bg-(shadow-[a-z0-9]+)\b',
                                                 _live_markup(gallery))}
    assert shown == set(SHADOWS), (
        f"design/gallery.html shows specimens for {sorted(shown)}; "
        f"the tokens are {sorted(SHADOWS)}")
    chrome = re.search(r"<style>(.*?)</style>", gallery, re.S)
    assert chrome, "design/gallery.html has no <style> block for its specimen classes"
    reads = {selector: value for selector, prop, value, _line in declarations(chrome.group(1))
             if prop == "box-shadow" and selector.startswith(".g-shadow-")}
    assert reads == {f".g-{token[2:]}": f"var({token})" for token in SHADOWS}, (
        f"design/gallery.html's specimen classes cast {reads}: each must read its own token")
    assert "--shadow-color" not in gallery, (
        "design/gallery.html still quotes --shadow-color, which no longer ships (#1049)")


def test_the_notice_says_where_the_shadows_come_from():
    """The statement of changes said the shadow tokens were this product's own. They are what
    Supabase's atoms render now, and a notice that kept the old sentence would under-credit them."""
    notice = " ".join(NOTICE.read_text(encoding="utf-8").split())
    assert "--shadow-color" not in notice, (
        "design/supabase.NOTICE.txt still names --shadow-color, which no longer ships")
    assert "Shadow tokens, line-height tokens" not in notice, (
        "item 5 still lists the shadow tokens among the tokens Supabase does not have")
    assert f"packages/tailwindcss/theme.css at v{TAILWIND}" in notice, (
        "the notice does not say the shadows are Tailwind's theme at the version the pin resolves")
