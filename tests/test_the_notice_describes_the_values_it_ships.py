"""A licence notice that nothing checks is a licence notice that goes false quietly.

WHAT HAPPENED, AND IT IS THE REASON THIS FILE EXISTS.
`design/supabase.NOTICE.txt` carries the statement of changes Apache-2.0 section
4(b) asks for. It listed five colour values as deliberately replaced. Every one of
the five was wrong, and it took two review passes to establish that:

  * `--line-strong`, `--amber` and `--focus` were replacements until 2026-08-31,
    when `R-85` restored them to Supabase's own values.
  * A fourth described an on-colour for device colour mode, a path `R-85` deleted.
  * And `--accent-contrast` was never a replacement at all. It ships `#030303` in
    light and `#131413` in dark, and both are Supabase's `--primary-foreground`
    resolved from their own expression with their own published scalars.

A separate item claimed neither easing curve in `design/tokens.css` appears in
Supabase's source; both do, in `packages/config/css/animations.css` at the commit
the notice pins.

None of that broke a test, because nothing compared the notice against the file it
describes. The values moved for good reasons, under a ruling, and the document that
tells a recipient what was changed simply stopped being true.

WHY THIS ASSERTS THE LINK AND NOT ONLY THE VALUES. Pinning values alone would
catch a value moving. It would not catch the failure that actually occurred, which
is a value moving *while the notice kept its old sentence*. So the load-bearing
assertion is set equality between what the notice NAMES as replaced and what this
file pins as replaced. That set is now EMPTY, and an empty set is still a claim:
declare a departure in the notice without making one in the code, or make one
without declaring it, and this fails.

It does NOT check every value that came from Supabase -- that is the wider gap, and
it is open work rather than something this file quietly half-does.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# Guards a design asset that is copied into the extension by
# tools/sync_design_assets.py; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "design" / "tokens.css"
NOTICE = ROOT / "design" / "supabase.NOTICE.txt"

# Values the notice states are SUPABASE'S OWN, in the theme block each belongs to.
# The light/dark split matters: an earlier version of this guard read only the first
# :root block, so a dark value could move without anything noticing.
THEIRS = {
    "light": {
        "--line-strong": "#d0d0d0",
        "--focus": "#98e3c0",
        "--amber": "#ca8a10",
        "--amber-ink": "#080503",
        # Their --primary-foreground resolved: oklch(0.1 0 159) from light's own
        # surface 0.995 / foreground-lightness 0.1 / chroma 0.
        "--accent-contrast": "#030303",
    },
    "dark": {
        "--focus": "#2f7a57",
        # oklch(0.19 0.00225 159) from dark's surface 0.19 / 0.95 / chroma 0.005.
        # This one is what validates the arithmetic: two independent scalars sets
        # reproducing two shipped values byte-for-byte is not a coincidence.
        "--accent-contrast": "#131413",
    },
}

# EMPTY, and deliberately so. The notice declares no deliberate colour replacement.
# Adding a row here without adding the entry to the notice fails the set test below,
# and so does the reverse.
OURS: dict[str, str] = {}

# Both curves are Supabase's, inlined in their --animate-* declarations. If a curve
# is swapped for one of ours the notice becomes wrong in the direction that credits
# this product with their work.
THEIR_CURVES = ("cubic-bezier(0.16, 1, 0.3, 1)", "cubic-bezier(0.87, 0, 0.13, 1)")


def _blocks() -> dict[str, str]:
    """The light and dark declaration blocks, by brace matching from each selector.

    The light block is the first `:root {`. The dark block is the first
    `:root[data-theme="dark"]`. Comments are stripped FIRST so that a brace inside
    a comment cannot end a block early -- the file's comments are long and contain
    both braces and the string ':root'.
    """
    source = re.sub(r"/\*.*?\*/", "", TOKENS.read_text(encoding="utf-8"), flags=re.S)
    found: dict[str, str] = {}
    for name, pattern in (("light", r":root\s*\{"), ("dark", r':root\[data-theme="dark"\]\s*\{')):
        match = re.search(pattern, source)
        assert match, f"no {name} block in design/tokens.css"
        depth, start = 0, match.end() - 1
        for i in range(start, len(source)):
            if source[i] == "{":
                depth += 1
            elif source[i] == "}":
                depth -= 1
                if depth == 0:
                    found[name] = source[start:i]
                    break
        else:
            raise AssertionError(f"the {name} block in design/tokens.css does not close")
    return found


def _declared(block: str, token: str) -> str | None:
    found = re.search(rf"^\s*{re.escape(token)}\s*:\s*([^;]+);", block, re.M)
    return found.group(1).strip() if found else None


@pytest.fixture(scope="module")
def blocks() -> dict[str, str]:
    return _blocks()


@pytest.fixture(scope="module")
def notice() -> str:
    return NOTICE.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    "scheme,token,value",
    [(scheme, token, value) for scheme, pairs in sorted(THEIRS.items())
     for token, value in sorted(pairs.items())],
)
def test_a_value_the_notice_credits_to_supabase_still_holds_it(scheme, token, value, blocks):
    """If one of these moves, the notice's Statement of Changes needs an entry.

    The failure message names the document, because the defect is never in the value
    alone -- a value may move on his ruling at any time -- it is in the two
    disagreeing.
    """
    assert _declared(blocks[scheme], token) == value, (
        f"{scheme} {token} is no longer {value}. That is not necessarily wrong, but "
        f"design/supabase.NOTICE.txt credits this value to Supabase, and one of the "
        f"two has to change. EDIT THE NOTICE FIRST, then this pin -- in that order, "
        f"because the notice is the licence obligation and this is only its guard."
    )


def test_the_notice_declares_no_deliberate_colour_replacement(notice):
    """The load-bearing assertion: the document and the code name the same set.

    This is the one that catches the real failure. Four entries went stale because
    the notice kept listing tokens the code had restored, and a fifth was never a
    replacement at all; no value assertion can see either, because each value was
    exactly what it was supposed to be. Only comparing the two lists can.
    """
    marker = "2. NO COLOUR VALUE IS DELIBERATELY REPLACED"
    assert marker in notice, (
        "design/supabase.NOTICE.txt no longer opens item 2 with the sentence this "
        "guard reads. If a deliberate replacement has been introduced, add it to "
        "OURS above and rewrite this assertion deliberately rather than deleting it."
    )
    end = "  3. NAMES DIVERGE"
    assert end in notice, "item 3's heading moved; this guard delimits item 2 by it"
    item_two = notice.split(marker, 1)[1].split(end, 1)[0]

    # An ENTRY is a token at the entry indentation followed by its reason -- the
    # shape every one of the five removed entries had. Prose that merely NAMES a
    # token, as the paragraphs explaining what was removed do, is not an entry and
    # must not be counted as one. An earlier version of this test read the two
    # sentences before those paragraphs, a window that contains no token at all, so
    # it compared set() with set() and could not fail. It is asserted against the
    # WHOLE of item 2 now, and against the shape rather than the mention.
    entries = set(re.findall(r"^ {7}(--[a-z0-9-]+)\s{2,}\S", item_two, re.M))
    assert entries == set(OURS), (
        f"item 2 lists {sorted(entries) or 'no'} entries; this guard pins "
        f"{sorted(OURS) or 'none'}. A value was replaced without the notice saying "
        f"so, or the notice says so without the value being replaced."
    )


@pytest.mark.parametrize("curve", THEIR_CURVES)
def test_both_easing_curves_are_declared_and_attributed_to_supabase(curve, blocks, notice):
    """Asserted against the DECLARATIONS, not the prose that describes them.

    An earlier version tested `curve in light` against the raw file, which the
    comment above the tokens satisfies on its own -- so deleting the declaration
    would have left the test green. The block this reads has its comments stripped.
    """
    declared = {_declared(blocks["light"], name) for name in ("--ease", "--ease-travel")}
    assert curve in declared, (
        f"{curve} is not declared by --ease or --ease-travel in design/tokens.css "
        f"(they hold {sorted(v for v in declared if v)}). "
        f"design/supabase.NOTICE.txt item 4 states both curves are Supabase's own; a "
        f"curve of ours in its place makes that item false."
    )
    assert curve in notice, (
        f"{curve} is declared in design/tokens.css and is not named in the notice, "
        f"so the notice no longer accounts for what ships."
    )


def test_no_device_colour_path_survives_outside_a_comment():
    """The notice says R-85 deleted this path. If it returns, item 2 needs it back."""
    code = re.sub(r"/\*.*?\*/", "", TOKENS.read_text(encoding="utf-8"), flags=re.S)
    for marker in ("data-color-mode", "AccentColor"):
        assert marker not in code, (
            f"{marker} is live code in design/tokens.css. design/supabase.NOTICE.txt "
            f"records that R-85 deleted the device colour path; a returning device "
            f"path needs its own entry in the Statement of Changes."
        )
