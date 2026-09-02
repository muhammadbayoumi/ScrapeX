"""R-74, enforced: the design system is Supabase's and a palette may change only colour.

> «design system هو supabase ولكن قد ضفنا له استثناء 3 palette الوان واتساب وجت هب و device»
> «whatsapp, github الوان theme يمكن اختيارها بواسطة المستخدم فتعدل على الالوان فقط لا تعدل
>  على design system»
> «واى تعارض معاها يلغى»

WHY THIS IS A TEST AND NOT A COMMENT. The failure it catches is silent in both directions.

Adding a non-colour key to a palette entry does not raise: `themeFor` dashes every key it
finds into a custom property, so a `design` object becomes `--design: [object Object]` and a
`radius` key becomes a real `--radius` override. Nothing throws, nothing looks broken enough
to notice in a screenshot, and the palette has quietly taken over the design system.

And the reverse: R-73 shipped the opposite architecture — a per-palette design axis — and it
was measured on the built engine as giving the design system to `supabase` and to nobody
else. `brand`, `blue` and device colours all fell back to the pre-Supabase 9px radius, 14px
body and Segoe UI. **Three of four colour choices lost it, and device is what a fresh install
uses.** That is the defect this file exists to make impossible, and it was invisible until
somebody enumerated the four choices and asked what each one actually applied.

WHAT IS DELIBERATELY *NOT* ASSERTED HERE: that tokens.css holds particular Supabase values.
That belongs to `tests/test_vendor.py`, which already owns the canonical-colour-system rules.
This file owns one question — may a palette reach past colour? — and answers it.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# Guards the extension: this reads a design/ source that is copied into extension/.
# See tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
APPEARANCE = ROOT / "design" / "appearance.js"
TOKENS = ROOT / "design" / "tokens.css"

#: Every key a palette entry may legally carry. The four metadata keys, plus the
#: 36 colour properties in camelCase. Derived from THEME_PROPERTIES rather than
#: retyped, so adding a colour property cannot make this list stale.
METADATA_KEYS = {"id", "label", "description", "colors", "themes"}

#: Non-colour token families a palette must never reach. Each entry is the prefix
#: of a design-system custom property, and the reason it is withheld.
FORBIDDEN_FAMILIES = {
    "radius": "shape is the design system's, not a palette's",
    "font": "typography is the design system's",
    "fs": "the type scale is the design system's",
    "fw": "font weights are the design system's",
    "lh": "line heights are the design system's",
    "sp": "the spacing scale is the design system's",
    "shadow": "elevation is the design system's -- EXCEPT shadow-color, see below",
    "dur": "motion timing is the design system's",
    "ease": "easing curves are the design system's",
    "control-height": "control metrics carry the panel's 48px touch floor",
    "touch-target": "the touch floor is not an appearance choice",
    "focus-ring": "focus geometry is the design system's; only --focus is a colour",
    "z": "layering is not an appearance choice",
    "google-btn": "third-party brand values fixed by Google's branding guidelines",
}

#: The two properties whose NAME starts with a forbidden family but which are
#: genuinely colours, and are therefore legal. Named explicitly so the check
#: above can stay a simple prefix match.
COLOUR_EXCEPTIONS = {"shadow-color"}


def _theme_properties() -> list[str]:
    source = APPEARANCE.read_text(encoding="utf-8")
    block = source.split("const THEME_PROPERTIES = Object.freeze([", 1)[1]
    block = block.split("]);", 1)[0]
    names = re.findall(r'"([a-z-]+)"', block)
    assert len(names) >= 30, (
        f"parsed only {len(names)} theme properties; the shape of "
        "design/appearance.js changed and this guard is not covering them")
    return names


def _camel(dashed: str) -> str:
    head, *rest = dashed.split("-")
    return head + "".join(part.capitalize() for part in rest)


def _palette_entries() -> dict[str, str]:
    """id -> the raw source text of that palette's entry."""
    source = APPEARANCE.read_text(encoding="utf-8")
    registry = source.split("const PALETTES = new Map([", 1)[1]
    registry = registry.split("const PALETTE_ALIASES", 1)[0]

    entries: dict[str, str] = {}
    starts = [(m.start(), m.group(1))
              for m in re.finditer(r'^\s{4}\["([a-z-]+)", \{', registry, re.M)]
    # `>= 3` UNTIL R-84, WHICH DELETED TWO OF THE THREE. The number was standing in
    # for "the parser still finds entries"; asserting the id by name says the same
    # thing and cannot rot when the registry shrinks again.
    assert starts, f"parsed no palette entries from {ENTRY_PATTERN.pattern!r}"
    for index, (offset, name) in enumerate(starts):
        stop = starts[index + 1][0] if index + 1 < len(starts) else len(registry)
        entries[name] = registry[offset:stop]
    return entries


def test_the_parser_finds_the_registry_and_the_properties():
    """A PARSER THAT MATCHED NOTHING WOULD MAKE EVERY TEST BELOW VACUOUS."""
    entries = _palette_entries()
    # Was {"brand", "blue", "supabase"}. R-84 deleted the first two — «احذف الثلاثة
    # وابق supabase وحده» — so the registry is one entry and this asserts the one
    # that must always be there rather than a set that recorded a deleted world.
    assert set(entries) == {"supabase"}, sorted(entries)
    assert len(_theme_properties()) >= 30


def test_no_palette_declares_a_design_block():
    """R-73's axis, removed by R-74. A `design` key would be dashed straight into
    a `--design` property whose value is the string "[object Object]"."""
    offenders = [name for name, body in _palette_entries().items()
                 if re.search(r"^\s*design:\s*\{", body, re.M)]
    assert not offenders, (
        f"{offenders} declare a `design` block. R-74: a palette changes colour "
        "only -- «فتعدل على الالوان فقط لا تعدل على design system». The design "
        "system belongs to design/tokens.css so that all four colour choices sit "
        "on it, including device, which applies no palette at all.")


def test_no_palette_sets_a_non_colour_token():
    """The general form, so a future session cannot reach past colour by spelling
    it differently -- `radius: "6px"` at the top level instead of inside a
    `design` block would have the identical effect."""
    allowed = METADATA_KEYS | {_camel(name) for name in _theme_properties()}
    offenders: list[str] = []

    for name, body in _palette_entries().items():
        for match in re.finditer(r"^\s*([A-Za-z][A-Za-z0-9]*):", body, re.M):
            key = match.group(1)
            if key in allowed or key in {"light", "dark"}:
                continue
            dashed = re.sub(r"([A-Z])", lambda m: "-" + m.group(1).lower(), key)
            if dashed in COLOUR_EXCEPTIONS:
                continue
            family = next((f for f in FORBIDDEN_FAMILIES
                           if dashed == f or dashed.startswith(f + "-")), None)
            reason = FORBIDDEN_FAMILIES.get(family, "not a colour property")
            offenders.append(f"{name}.{key} ({reason})")

    assert not offenders, (
        "these palette keys are not colours, and R-74 says a palette may change "
        f"nothing but colour: {offenders}")


def test_supabase_declares_no_colours_because_it_is_the_baseline():
    """It is not one option among three -- it is what tokens.css declares.

    Spelling its colours here as well would put the same values in two files with
    nothing keeping them equal. `brand` and `blue` have entries precisely because
    they DIFFER from the baseline; `supabase` does not.
    """
    body = _palette_entries()["supabase"]
    assert re.search(r"themes:\s*\{light:\s*\{\},\s*dark:\s*\{\}\}", body), (
        "the supabase entry declares colours. Under R-74 its colours are "
        "design/tokens.css's -- it exists to be selectable, to label its tile, "
        "and to name itself in `data-palette`.")


def test_the_baseline_carries_the_design_system_rather_than_a_palette():
    """The other half of the same ruling: if tokens.css did NOT hold the Supabase
    design system, removing the axis would have left the product on the old one.

    Pins one value per family, chosen because each is a value the pre-Supabase
    system had different: 6px control radius, a 15px body size, the 450 text
    weight Supabase uses instead of 400, its two named easing curves, and the
    2px focus ring. Not the whole scale -- that would fail on every tuning.
    """
    tokens = TOKENS.read_text(encoding="utf-8")
    root = tokens.split(":root {", 1)[1].split("\n}", 1)[0]

    for declaration, why in (
        ("--radius: 0.375rem", "Supabase's universal 6px control radius"),
        ("--fs: 0.9375rem", "their text-base is 15px, not 14px"),
        ("--fw-regular: 450", "their --font-weight-normal is 450, not 400"),
        ("--fw-heavy: 600", "they have no bold; the ceiling is Manrope 600"),
        ("--ease: cubic-bezier(0.16, 1, 0.3, 1)", "their curve for things that appear"),
        ("--ease-travel: cubic-bezier(0.87, 0, 0.13, 1)", "and for things that travel"),
        ("--focus-ring-width: 2px", "their ring-2"),
        ("Inter", "the body face they migrated to from Circular"),
        ("Manrope", "the heading face they pair with it"),
        ("Noto Sans Arabic", "kept in every stack: this product is used in Arabic"),
    ):
        assert declaration in root, (
            f"design/tokens.css's :root no longer carries `{declaration}` -- {why}. "
            "Under R-74 this file IS the Supabase design system, and a palette "
            "cannot put it back.")

    # The teal R-59 decision 2 called migration debt. It was the :root fallback,
    # so it was what a fresh user actually saw; R-74 deletes it rather than
    # deprecating it a second time.
    assert "#00adb5" not in tokens and "#35c8ce" not in tokens, (
        "the deprecated teal is back in design/tokens.css. R-59 decision 2 called "
        "it 'legacy colour residue and migration debt' and R-74 discharged it by "
        "making the baseline Supabase.")


def test_both_dark_blocks_agree():
    """A dark scheme that differs depending on HOW it was reached is a defect
    nobody looking at one block can see.

    `:root[data-theme="dark"]` is the explicit choice and the
    `prefers-color-scheme` copy is the device following the OS. They must hold the
    same values. Compared as a property map so comments and order do not matter.
    """
    tokens = TOKENS.read_text(encoding="utf-8")

    def properties(block: str) -> dict[str, str]:
        block = re.sub(r"/\*.*?\*/", "", block, flags=re.S)
        return {m.group(1): m.group(2).strip()
                for m in re.finditer(r"(--[a-z0-9-]+):\s*([^;]+);", block)}

    explicit = properties(
        tokens.split(':root[data-theme="dark"] {', 1)[1].split("\n}", 1)[0])
    media = properties(
        tokens.split('@media (prefers-color-scheme: dark) {', 1)[1]
        .split(':root:not([data-theme="light"]) {', 1)[1].split("\n  }", 1)[0])

    assert explicit and media, (len(explicit), len(media))
    only_explicit = {k: v for k, v in explicit.items() if media.get(k) != v}
    only_media = {k: v for k, v in media.items() if explicit.get(k) != v}
    assert not only_explicit and not only_media, (
        "the two dark blocks disagree.\n"
        f"  in [data-theme=dark] only: {only_explicit}\n"
        f"  in prefers-color-scheme only: {only_media}")
