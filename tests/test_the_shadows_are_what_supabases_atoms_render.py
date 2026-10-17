"""Each shadow token is the string Supabase's atoms render, and each overlay casts its atom's (#1049).

WHERE THE VALUES COME FROM. Supabase authors no shadow token: none of the 29 CSS files at the
pin under apps/design-system, packages/config, packages/ui and packages/ui-patterns declares
--shadow-*, and tests/fixtures/supabase-design-tokens.json holds no name containing "shadow".
Their atoms write Tailwind's `shadow-*` classes, so what they render is Tailwind's theme at the
version their lockfile resolves for packages/ui -- tailwindcss 4.2.4, pnpm-lock.yaml@86c813ec:
2618-2620. That is the value Supabase renders, not a second source
(docs/DESIGN-SYSTEM-SOURCES.md, "Tailwind's values, stated once"). tools/read_supabase_values.py
reads the four strings from that theme into tests/fixtures/supabase-value-axes.json, beside the
spacing, leading, radius and easings it reads from the same file, so a re-pin reads them again.

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
from collections import Counter
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
TOKENS = ROOT / "design" / "tokens.css"
NOTICE = ROOT / "design" / "supabase.NOTICE.txt"
GALLERY = ROOT / "design" / "gallery.html"
APP_CSS = ROOT / "extension" / "app.css"

READING = json.loads(SUPABASE.read_text(encoding="utf-8"))

#: packages/tailwindcss/theme.css at the version the pin resolves, as the reader read it.
SHADOWS = READING["axes"]["shadow"]["declared"]

#: The one other shadow declaration: the bare alias eight surfaces read. It is xs, which is
#: what Supabase's Card casts (card.tsx@86c813ec:10 shadow-xs).
ALIAS = ("--shadow", "var(--shadow-xs)")

# Supabase's atoms at the pin, packages/ui/src/components/shadcn/ui/, and the class each casts.
MENU = "dropdown-menu.tsx@86c813ec:87 shadow-md"
SUBMENU = "dropdown-menu.tsx@86c813ec:70 shadow-lg"  # DropdownMenuSubContent
POPOVER = "popover.tsx@86c813ec:49 shadow-md"
SELECT = "select.tsx@86c813ec:110 shadow-md"
DIALOG = "dialog.tsx@86c813ec:67 shadow-md dark:shadow-xs"
# modality.mdx@86c813ec:64: "Sheets are dialogs presented as side panels."
SHEET = "sheet.tsx@86c813ec:63 shadow-lg"
TOAST = "sonner.tsx@86c813ec:42 shadow-lg"

#: (authored sheet, selector) -> (the token it reads, the atom that says so).
OVERLAYS = {
    ("design/components.css", ".split-button-options"): ("--shadow-md", MENU),
    ("design/data-workspace.css", ".dataset-menu-popover"): ("--shadow-md", MENU),
    ("design/data-workspace.css", ".dataset-popover"): ("--shadow-md", POPOVER),
    ("design/grid-theme.css", ".dg-menu, .dg-popup"): ("--shadow-md", MENU),
    ("design/grid-theme.css", ".dg-submenu"): ("--shadow-lg", SUBMENU),
    ("design/grid-theme.css", ".grid-feature-popover"): ("--shadow-md", POPOVER),
    ("design/grid-theme.css", ".column-chooser"): ("--shadow-lg", SHEET),
    ("extension/app.css", ".sx-select-list"): ("--shadow-md", SELECT),
    ("extension/app.css", ".account-menu"): ("--shadow-md", MENU),
    ("extension/app.css", ".finance-converter-options"): ("--shadow-md", SELECT),
    ("extension/app.css", ".modal-card"): ("--shadow-md", DIALOG),
    ("extension/app.css", ".workspace-menu"): ("--shadow-lg", SHEET),
    ("extension/app.css", ".toast"): ("--shadow-lg", TOAST),
    ("scrapex/webui/static/webui.css", ".source-filter-popover"): ("--shadow-md", POPOVER),
    ("scrapex/webui/static/webui.css", ".sidebar-ready .workspace-sidebar"): ("--shadow-lg", SHEET),
}

#: The Dialog's dark half, in both of the ways a dark scheme is reached.
DIALOG_IN_DARK = (':root[data-theme="dark"] .modal-card', ':root:not([data-theme="light"]) .modal-card')

#: EVERY box-shadow the Dialog takes, each with the rules around it, outermost first. The
#: base, md, stands alone: under any condition it would leave some theme and device with no
#: shadow. The explicit choice is dark on any device, so its rule stands alone too;
#: `:root:not([data-theme="light"])` matches a light device as well, so only the dark media
#: query around it makes it dark. A fourth rule is a fourth key, so it fails.
DIALOG_RULES = {".modal-card": [(".modal-card",)],
                DIALOG_IN_DARK[0]: [(DIALOG_IN_DARK[0],)],
                DIALOG_IN_DARK[1]: [("@media (prefers-color-scheme: dark)", DIALOG_IN_DARK[1])]}


def _names_the_dialog(selector: str) -> bool:
    """Some comma part's subject compound carries the class `.modal-card` -- the Dialog
    itself, not a descendant (`.modal-card button`) or a longer class (`.modal-card-wide`)."""
    return any(re.search(r"\.modal-card(?![\w-])", re.split(r"[\s>+~]+", part.strip())[-1])
               for part in selector.split(","))

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


def _rules_around(css: str, prop: str) -> list[tuple[tuple[str, ...], str, str]]:
    """(every rule around it, outermost first; property; value) for each declaration in
    `css` whose property name fully matches the pattern `prop`.

    declarations() reads the same rules and keeps only the nearest selector, which is why a
    dark rule moved into a media query that is not dark still passed the test that reads it.
    A property name here may hold digits, as `--shadow-2xl` would."""
    css = re.sub(r"/\*.*?\*/", lambda m: " " * len(m.group(0)), css, flags=re.S)
    stack: list[str] = []
    found = []
    start = 0
    for index, char in enumerate(css):
        if char not in "{};":
            continue
        chunk = css[start:index]
        if char == "{":
            stack.append(" ".join(chunk.split()))
        else:
            declaration = re.fullmatch(r"\s*([\w-]+)\s*:\s*(.+?)\s*", chunk, flags=re.S)
            if declaration and stack and re.fullmatch(prop, declaration.group(1), flags=re.I):
                found.append((tuple(stack), declaration.group(1),
                              " ".join(declaration.group(2).split())))
            if char == "}":
                assert stack, "a `}` closes nothing: a brace inside a string, or a broken sheet"
                stack.pop()
        start = index + 1
    assert not stack, f"{len(stack)} rule(s) never close: {stack[-1]!r}"
    return found


def _box_shadows() -> list[tuple[str, str, str]]:
    """(sheet, selector, value) for every box-shadow in a sheet this repository authors."""
    return [(sheet.relative_to(ROOT).as_posix(), selector, value)
            for sheet in authored()
            for selector, prop, value, _line in declarations(sheet.read_text(encoding="utf-8"))
            if prop == "box-shadow"]


@pytest.mark.parametrize("token", sorted(SHADOWS))
def test_each_shadow_token_is_the_string_tailwinds_theme_declares(token):
    light = _declared().get((LIGHT, token))
    assert light == SHADOWS[token], (
        f"design/tokens.css's :root declares {token} as {light!r}. Supabase's atoms render "
        f"{SHADOWS[token]!r}: tailwindcss/theme.css@v{READING['tailwind']}, the version their "
        f"lockfile resolves at the pin, as tools/read_supabase_values.py read it (#1049).")


def test_the_unconditional_root_declares_the_four_and_the_alias():
    """Every --shadow* in tokens.css sits directly in a top-level `:root`, with no at-rule
    and no other rule around it. A declaration inside any other rule applies only where that
    rule does, so moved into the prefers-contrast `:root` or a trailing `@media`, the alias
    was undefined everywhere else and the eight bare `var(--shadow)` readers cast `none`.
    Reading the text of the first `:root {` block caught those two but not a nested
    `@media` or `@supports` inside it, a nested `:root` (which is `:root :root`), or an
    `@media` around the whole block. So the whole stack of rules around each one is held."""
    placed = sorted(_rules_around(TOKENS.read_text(encoding="utf-8"), r"--shadow.*"))
    expected = sorted(((":root",), token, value) for token, value in [*SHADOWS.items(), ALIAS])
    assert placed == expected, (
        f"design/tokens.css's --shadow* declarations are not the {len(expected)} below, each "
        f"directly in a top-level :root.\n"
        f"  declared, not expected: {sorted((Counter(placed) - Counter(expected)).elements())}\n"
        f"  expected, not declared: {sorted((Counter(expected) - Counter(placed)).elements())}\n"
        f"A --shadow* inside any other rule is undefined wherever that rule does not apply, "
        f"and every reader of it casts nothing there (#1049).")


def test_no_dark_block_re_declares_a_shadow():
    """Supabase renders the same shadow-* classes in both schemes. The one atom that swaps is
    the Dialog, and it swaps at the atom (`dark:shadow-xs`), not by re-toning a token."""
    redeclared = sorted(f"{block} {token}" for (block, token) in _declared()
                        if block != LIGHT and token.startswith("--shadow"))
    assert not redeclared, (
        f"a dark block re-declares {redeclared}. Supabase's shadow-* classes resolve to "
        f"Tailwind's theme in both schemes, so dark re-toning is this product's own (#1049).")


def test_the_shadow_tokens_are_declared_once_and_nowhere_else():
    """The tests above read only tokens.css, and two of them only the first of each of its
    three blocks; the cascade obeys the last declaration anywhere. A trailing `:root`, the
    prefers-contrast block, a dark block in another sheet, or the alias re-pointed to lg
    each changed what every reader cast while they passed. So every --shadow* declaration
    in tokens.css and every sheet this repository authors is listed here, duplicates
    included."""
    found = sorted((sheet.relative_to(ROOT).as_posix(), selector, prop, value)
                   for sheet in [TOKENS, *authored()]
                   for selector, prop, value, _line in declarations(sheet.read_text(encoding="utf-8"))
                   if prop.startswith("--shadow"))
    expected = sorted(("design/tokens.css", ":root", token, value)
                      for token, value in [*SHADOWS.items(), ALIAS])
    assert found == expected, (
        f"the --shadow* declarations are not the {len(expected)} in tokens.css's :root.\n"
        f"  declared, not expected: {sorted((Counter(found) - Counter(expected)).elements())}\n"
        f"  expected, not declared: {sorted((Counter(expected) - Counter(found)).elements())}\n"
        f"Supabase's shadow-* classes render Tailwind's strings in every scheme and mode, and "
        f"the one atom that swaps does it in its own rule (#1049).")


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


def test_each_dialog_shadow_sits_where_its_scheme_is():
    """The test above reads each selector and not the rules around it. Moved under
    `prefers-color-scheme: light`, the device-dark rule dropped the light Dialog to xs; moved
    into the dark media query, the explicit-dark rule left a reader who picks Dark on a light
    device (design/appearance.js sets data-theme only then) with md. Nested in another style
    rule, either one matched nothing. And the base: moved into `prefers-color-scheme: light`
    or a width query, a reader who picks Light on a dark device, or a narrow panel, got no
    shadow at all (#1357's gate). Each passed it. So did a fourth rule under a selector the
    table did not name, `:root[data-theme="light"] .modal-card { box-shadow: none }` among
    them, because only the three known selectors were collected; every rule that styles the
    Dialog is collected now, keyed by its innermost style rule."""
    placed = {}
    for rules, _prop, _value in _rules_around(APP_CSS.read_text(encoding="utf-8"), "box-shadow"):
        assert not any("&" in rule for rule in rules), (
            f"{rules}: a nested `&` selector is not resolved here; write the rule out in full")
        selector = next((rule for rule in reversed(rules) if not rule.startswith("@")), "")
        if _names_the_dialog(selector):
            placed.setdefault(selector, []).append(rules)
    assert placed == DIALOG_RULES, (
        f"extension/app.css places the Dialog's shadows at {placed}; {DIALOG} needs "
        f"{DIALOG_RULES}.")


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
    assert f"packages/tailwindcss/theme.css at v{READING['tailwind']}" in notice, (
        "the notice does not say the shadows are Tailwind's theme at the version the pin resolves")
