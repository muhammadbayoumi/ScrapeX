"""A licence notice that nothing checks is a licence notice that goes false quietly.

WHAT HAPPENED, AND IT IS THE REASON THIS FILE EXISTS.
`design/supabase.NOTICE.txt` carries the statement of changes Apache-2.0 section
4(b) asks for. It listed five colour values as deliberately replaced. By
2026-09-07 four of the five were wrong: `R-85` restored `--line-strong`, `--amber`
and `--focus` to Supabase's published values on 2026-08-31, and deleted the device
colour path the fifth described. A separate item claimed neither easing curve in
`design/tokens.css` appears in Supabase's source; both do, in
`packages/config/css/animations.css` at the commit the notice pins.

None of that broke a test, because nothing compared the notice against the file it
describes. The values moved for good reasons, under a ruling, and the document that
tells a recipient what was changed simply stopped being true.

WHY THIS ASSERTS THE LINK AND NOT ONLY THE VALUES. Pinning values alone would
catch a value moving. It would not catch the failure that actually occurred, which
is a value moving *while the notice kept its old sentence*. So the load-bearing
assertion here is set equality: the tokens the notice names as replaced must be
exactly the tokens this file pins as replaced. Replace one more value without
saying so, or say so without replacing it, and this fails.

It does NOT check every value that came from Supabase — that is the wider gap, and
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

# Values the notice states are SUPABASE'S OWN. Each was a deliberate replacement
# until R-85 restored it on 2026-08-31, which is exactly the move that made the
# notice false, so each is pinned at the value the notice now implies.
THEIRS = {
    "--line-strong": "#d0d0d0",
    "--focus": "#98e3c0",
    "--amber": "#ca8a10",
    "--amber-ink": "#080503",
}

# The one value the notice still declares replaced, and the reason is written at
# the value in tokens.css: their brand green is 1.99:1 against white.
OURS = {"--accent-contrast": "#030303"}

# Both curves are Supabase's, inlined in their --animate-* declarations. The
# notice says so; if a curve is swapped for one of ours the notice becomes wrong
# in the direction that credits us with their work.
THEIR_CURVES = ("cubic-bezier(0.16, 1, 0.3, 1)", "cubic-bezier(0.87, 0, 0.13, 1)")


def _light_block() -> str:
    """The first :root block, which is where the light values are declared."""
    source = TOKENS.read_text(encoding="utf-8")
    start = source.index(":root")
    depth = 0
    for i in range(source.index("{", start), len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i]
    raise AssertionError("the first :root block in design/tokens.css does not close")


def _declared(block: str, token: str) -> str | None:
    found = re.search(rf"^\s*{re.escape(token)}\s*:\s*([^;]+);", block, re.M)
    return found.group(1).strip() if found else None


@pytest.fixture(scope="module")
def light() -> str:
    return _light_block()


@pytest.fixture(scope="module")
def notice() -> str:
    return NOTICE.read_text(encoding="utf-8")


@pytest.mark.parametrize("token,value", sorted(THEIRS.items()))
def test_a_value_the_notice_credits_to_supabase_still_holds_it(token, value, light):
    """If one of these moves, the notice's Statement of Changes needs an entry.

    The failure message says which document to edit, because the defect is never
    in the value alone — a value may move on his ruling at any time — it is in the
    two disagreeing.
    """
    assert _declared(light, token) == value, (
        f"{token} is no longer {value}. That is not necessarily wrong, but "
        f"design/supabase.NOTICE.txt credits this value to Supabase, and one of "
        f"the two has to change. Update the Statement of Changes, then this pin."
    )


@pytest.mark.parametrize("token,value", sorted(OURS.items()))
def test_the_one_value_the_notice_declares_replaced_is_still_replaced(token, value, light):
    assert _declared(light, token) == value, (
        f"{token} is no longer {value}. design/supabase.NOTICE.txt item 2 names it "
        f"as the single deliberate replacement; if it has been restored to theirs, "
        f"that item has nothing left in it."
    )


def test_the_notice_names_exactly_the_tokens_this_file_pins_as_replaced(notice):
    """The load-bearing assertion: the document and the code name the same set.

    This is the one that would have caught the real failure. Four entries went
    stale because the notice kept listing tokens the code had restored, and no
    value assertion can see that — only a comparison of the two lists can.
    """
    item_two = notice.split("2. ONE VALUE IS STILL DELIBERATELY REPLACED", 1)
    assert len(item_two) == 2, (
        "design/supabase.NOTICE.txt no longer opens item 2 with the sentence this "
        "guard reads. If the count of replaced values changed, this test's "
        "expectations have to change with it, deliberately."
    )
    body = item_two[1].split("FOUR ENTRIES STOOD HERE", 1)[0]
    named = set(re.findall(r"--[a-z0-9-]+", body))
    assert named == set(OURS), (
        f"the notice names {sorted(named)} as deliberately replaced; this guard "
        f"pins {sorted(OURS)}. A value was replaced without the notice saying so, "
        f"or the notice says so without the value being replaced."
    )


@pytest.mark.parametrize("curve", THEIR_CURVES)
def test_both_easing_curves_are_the_ones_the_notice_attributes_to_supabase(curve, light, notice):
    assert curve in light, (
        f"{curve} is gone from design/tokens.css. design/supabase.NOTICE.txt item 4 "
        f"states both curves are Supabase's own; a curve of ours in its place makes "
        f"that item false."
    )
    assert curve in notice, (
        f"{curve} is in design/tokens.css and is not named in the notice, so the "
        f"notice no longer accounts for what ships."
    )


def test_no_device_colour_path_survives_outside_a_comment():
    """The notice says R-85 deleted this path. If it returns, item 2 needs it back."""
    source = TOKENS.read_text(encoding="utf-8")
    code = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    for marker in ("data-color-mode", "AccentColor"):
        assert marker not in code, (
            f"{marker} is live code in design/tokens.css. design/supabase.NOTICE.txt "
            f"records that R-85 deleted the device colour path; a returning device "
            f"path needs its own entry in the Statement of Changes."
        )
