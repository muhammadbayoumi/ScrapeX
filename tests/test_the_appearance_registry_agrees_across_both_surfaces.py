"""One appearance registry, declared twice, and nothing used to compare them.

THE FAILURE THIS EXISTS TO CATCH IS SILENT, PERMANENT, AND WAS REACHABLE BY A
ONE-LINE CHANGE.

`design/appearance.js` holds the palettes the panel can offer.
`scrapex/webui/app.py` holds the palettes the engine will persist. The two
surfaces cannot import from each other at runtime -- that is the whole reason the
design assets are copied rather than shared -- so the lists are written twice, and
before R-73 nothing anywhere asserted they matched.

What happened when they diverged, traced end to end on this code:

  1. The user picks the new palette. `set()` stores it locally, so the panel
     looks correct and the choice appears to work.
  2. `pushRemote` POSTs it. `_appearance_value` raises 400.
  3. `pushRemote` returns `response.ok` from inside a `try`, and BOTH of its call
     sites discard the return value. Nothing is logged, thrown, or shown.
  4. `pullRemote` keeps polling every 2 seconds. Its GET answers **200** with
     `{"appearance": null}` -- because the route swallows a rejected stored value
     -- so `consecutiveFailures = 0` runs on every tick and the
     QUIET_AFTER_FAILURES backoff never engages.
  5. `!remote && current.updatedAt` is true, so every tick calls `pushRemote`
     again. A permanent 2-second write loop, for as long as the panel is open,
     that never persists anything and never says so.

And the suite could not have noticed: the only POST in it sent `whatsapp` and
expected 200, and one other sent `popular-blush` and expected 400. That pair
returns the same verdict whether a third palette is allowed or not.

WHY THE TEST PARSES JAVASCRIPT. Because the alternative is a third hand-written
list, which is the defect. Reading the source is what makes adding a palette in
one place fail here rather than in production.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# Guards the extension: this reads a design/ source that is copied into
# extension/. See tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
APPEARANCE = ROOT / "design" / "appearance.js"


def _registry() -> tuple[list[str], dict[str, str], str]:
    """The palette ids, the alias map and the default, read from the engine."""
    source = APPEARANCE.read_text(encoding="utf-8")

    entries = source.split("const PALETTES = new Map([", 1)[1]
    entries = entries.split("const PALETTE_ALIASES", 1)[0]
    ids = re.findall(r'^\s{4}\["([a-z-]+)", \{', entries, re.M)

    alias_block = source.split("const PALETTE_ALIASES = new Map([", 1)[1]
    alias_block = alias_block.split("]);", 1)[0]
    aliases = dict(re.findall(r'\["([a-z-]+)", "([a-z-]+)"\]', alias_block))

    default = re.search(r'palette: "([a-z-]+)",', source.split("const DEFAULTS", 1)[1])

    assert ids, "could not parse any palette id out of design/appearance.js"
    assert aliases, "could not parse the alias map out of design/appearance.js"
    assert default, "could not parse DEFAULTS.palette out of design/appearance.js"
    return ids, aliases, default.group(1)


def test_the_parser_actually_finds_the_registry():
    """A PARSER THAT MATCHED NOTHING WOULD MAKE EVERY TEST BELOW VACUOUS, which
    is the failure mode of reading a file instead of importing it. Floors, not
    exact numbers, so adding a palette does not have to edit this."""
    ids, aliases, default = _registry()
    # `>= 3` until R-84 left one colour choice. Same correction as its sibling:
    # what must hold is that the parse produced something and that `supabase` is in
    # it, not a count that encodes how many palettes existed on one afternoon.
    assert ids, "parsed no palette ids; the registry's shape changed"
    assert "supabase" in ids, ids
    assert len(aliases) >= 2, aliases
    assert default in ids, (default, ids)


def test_both_surfaces_offer_the_same_palettes():
    from scrapex.webui.app import APPEARANCE_PALETTES

    ids, _, _ = _registry()
    assert sorted(APPEARANCE_PALETTES) == sorted(ids), (
        "design/appearance.js and scrapex/webui/app.py disagree about which "
        f"palettes exist: engine offers {sorted(ids)}, server accepts "
        f"{sorted(APPEARANCE_PALETTES)}. A palette the panel can pick and the "
        "server refuses becomes a silent 2-second write loop -- see this "
        "module's docstring.")


def test_both_surfaces_resolve_the_same_legacy_aliases():
    from scrapex.webui.app import APPEARANCE_PALETTE_ALIASES

    _, aliases, _ = _registry()
    assert APPEARANCE_PALETTE_ALIASES == aliases, (
        "the legacy alias maps disagree: appearance.js resolves "
        f"{aliases}, app.py resolves {APPEARANCE_PALETTE_ALIASES}. Every "
        "appearance stored before 2026-08-28 carries a legacy id, so a "
        "disagreement here loses a real user's choice on one surface and keeps "
        "it on the other.")


def test_every_palette_the_server_accepts_can_actually_be_painted():
    """An id on the allowlist with no entry in the Map is worse than a refusal.

    `paletteFor` falls back to the default when a name is missing, so the server
    would accept the name, the engine would store it, and the panel would paint
    something else -- with `data-palette` claiming the stored one. A wrong colour
    that reports the right name is not findable by looking at it."""
    from scrapex.webui.app import APPEARANCE_PALETTES

    ids, _, _ = _registry()
    orphans = sorted(set(APPEARANCE_PALETTES) - set(ids))
    assert not orphans, (
        f"{orphans} are accepted by scrapex/webui/app.py and have no entry in "
        "design/appearance.js")


def test_no_alias_shadows_a_real_palette():
    """An alias that is also a Map key would make resolution order decide the
    answer, and `resolvePalette` checks the alias map FIRST -- so the real entry
    would become unreachable while still appearing in the tile list."""
    ids, aliases, _ = _registry()
    collisions = sorted(set(aliases) & set(ids))
    assert not collisions, (
        f"{collisions} are both a legacy alias and a registry key; "
        "resolvePalette would send the real palette to the aliased one")


def test_every_alias_points_at_a_palette_that_exists():
    ids, aliases, _ = _registry()
    dangling = sorted(
        f"{name} -> {target}" for name, target in aliases.items()
        if target not in ids)
    assert not dangling, (
        f"{dangling}: an alias whose target was renamed resolves to the "
        "default, which silently resets the stored preference it exists to "
        "preserve")


def test_the_server_accepts_the_engines_own_default():
    """The one that would have fired on the R-73 rename in the wrong order.

    If DEFAULTS.palette moves to a name the server does not accept, then EVERY
    fresh install that turns device colours off starts the silent write loop --
    not an edge case, the default path."""
    from scrapex.webui.app import APPEARANCE_PALETTES

    _, _, default = _registry()
    assert default in APPEARANCE_PALETTES, (
        f"the engine's default palette is {default!r} and the server does not "
        f"accept it (accepts {sorted(APPEARANCE_PALETTES)})")
