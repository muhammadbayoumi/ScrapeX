"""Google's button is Google's, and its specification is not ours to soften.

developers.google.com/identity/branding-guidelines fixes the background, the
stroke, the text colour, the type and the padding, and forbids altering the mark
at all. None of that is taste, so none of it belongs in a review conversation —
it belongs here, where changing it fails.

WHAT THIS REPLACED, AND WHY IT WAS A VIOLATION AND NOT A PREFERENCE. The button
carried Material's `account-circle`, a monochrome person-in-a-circle inheriting
`currentColor`. The guidelines forbid a monochrome "G", forbid a substitute
mark, and forbid recolouring the mark — that one icon broke all three. The
replacement is Google's own published asset, byte-for-byte, and it is an `<img>`
rather than an `.sx-icon` precisely because every icon in this project inherits
`currentColor` and would have recoloured it again.

THE COLOURS ARE TOKENS, NOT LITERALS, and that is allowed: the guidelines fix
three backgrounds — light, dark and neutral — and let the button follow the
surface it sits on. They live in tokens.css, the one file permitted to name a
colour, and deliberately NOT in the palette: no appearance choice may re-tone
them.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

pytestmark = pytest.mark.extension

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOKENS = (ROOT / "design" / "tokens.css").read_text(encoding="utf-8")
COMPONENTS = (ROOT / "design" / "components.css").read_text(encoding="utf-8")
PANEL = (ROOT / "extension" / "app.html").read_text(encoding="utf-8")

#: Verbatim from the guidelines. Light and dark only — the neutral variant
#: (#F2F2F2, no stroke) is not used here, and adding it would mean adding its
#: rules too rather than borrowing these.
LIGHT = {"bg": "#FFFFFF", "stroke": "#747775", "text": "#1F1F1F"}
DARK = {"bg": "#131314", "stroke": "#8E918F", "text": "#E3E3E3"}

#: "we recommend the call-to-action text 'Sign in with Google', 'Sign up with
#: Google', or 'Continue with Google'." Localisation is allowed; invention is
#: not, and a fourth string is invention.
SANCTIONED = ("Sign in with Google", "Sign up with Google", "Continue with Google")


def _button() -> str:
    match = re.search(r'<button class="google-signin".*?</button>', PANEL, re.S)
    assert match, "the panel no longer has a Google sign-in button"
    return match.group(0)


def test_the_mark_is_googles_own_asset_and_not_a_drawing_of_it():
    """An invented path is a wrong logo that looks deliberate.

    The file is the 128px PNG Google publishes, saved unmodified. Its size is
    asserted so a "helpful" re-export — which would change the pixels the
    guidelines forbid changing — is visible.
    """
    for path in (ROOT / "design" / "google-g.png",
                 ROOT / "extension" / "icons" / "google-g.png"):
        assert path.exists(), f"{path} is missing, so the button has no mark"
        assert path.stat().st_size == 33661, (
            f"{path.name} is not the published asset any more; it was "
            "re-exported or redrawn, and the guidelines forbid altering it")


def test_the_mark_is_never_recoloured_by_this_project():
    """THE RULE THE PREVIOUS BUTTON BROKE THREE TIMES OVER.

    `.sx-icon` sets `fill: currentColor`, which is right for every icon this
    project owns and forbidden for this one. The mark is an <img>, so no CSS
    of ours can reach inside it.
    """
    button = _button()

    assert "sx-icon" not in button, (
        "the mark is an .sx-icon again, so it inherits currentColor and is "
        "recoloured — the first thing the guidelines forbid")
    assert re.search(r'<img class="google-signin-mark"[^>]*src="[^"]*google-g\.png"',
                     button), "the button does not carry Google's own mark"
    # The published asset's OWN size, so the box is reserved before it loads.
    # The display size is CSS's, and it sets height alone — see below.
    assert 'width="200" height="204"' in button, (
        "the intrinsic size is wrong, so the reserved box has the wrong shape")

    rule = re.search(r"\.google-signin-mark \{([^}]*)\}", COMPONENTS)
    assert rule, "the mark has no rule of its own"
    assert "fill" not in rule.group(1) and "filter" not in rule.group(1), (
        "something is recolouring the mark")


def test_the_icon_never_stands_alone():
    """"Don't use the Google icon or logo by itself without the button boundary
    and without text." Both halves, asserted together."""
    button = _button()

    assert any(text in button for text in SANCTIONED), (
        f"the button says something outside {SANCTIONED}")
    assert "border" in re.search(r"\.google-signin \{([^}]*)\}",
                                 COMPONENTS).group(1), (
        "the button has no boundary, so the mark is standing on its own")


@pytest.mark.parametrize("theme,values", [("light", LIGHT), ("dark", DARK)])
def test_every_fixed_colour_is_exactly_what_google_published(theme, values):
    """Not "close enough". These are three hex values in a document."""
    for part, expected in values.items():
        assert f"--google-btn-{part}: {expected};" in TOKENS, (
            f"the {theme} {part} is no longer {expected}; the guidelines fix it")


def test_the_button_uses_only_those_tokens_and_never_the_palette():
    """A palette colour here would follow the owner's appearance choice, and the
    guidelines allow the button on three backgrounds and no others."""
    rule = re.search(r"\.google-signin \{([^}]*)\}", COMPONENTS).group(1)

    for prop in ("background", "color", "border"):
        line = next(l for l in rule.splitlines() if l.strip().startswith(prop))
        assert "--google-btn-" in line, (
            f"{prop} is not a Google token: {line.strip()!r}")


def test_the_type_and_the_padding_are_the_published_numbers():
    """Google Sans Medium 14/20, 12px before the mark, 10px after it, 12px
    after the text. The stack falls back to the panel's because Google Sans is
    not a free webfont — the guidelines name the face, and naming it first is
    what they ask for."""
    rule = re.search(r"\.google-signin \{([^}]*)\}", COMPONENTS).group(1)

    mark = re.search(r"\.google-signin-mark \{([^}]*)\}", COMPONENTS).group(1)
    assert "width: auto" in mark and "height: 20px" in mark, (
        "both axes are pinned again, which stretches a 200x204 mark into a "
        "square — the guidelines forbid stretching the logo")

    assert '"Google Sans"' in rule and "var(--font)" in rule
    assert "font-size: 14px" in rule
    assert "line-height: 20px" in rule
    assert "gap: 10px" in rule, "the 10px between the mark and the text is gone"
    assert "padding: 0 12px 0 12px" in rule, "the 12px either side is gone"
    assert "min-height: 40px" in rule


def test_the_button_is_pressable_now_that_it_signs_people_in():
    """This asserted the OPPOSITE until M1c, and the reason it did is worth
    keeping: a pressable button that cannot sign anyone in reads as broken
    rather than unbuilt, so it was disabled on purpose while it was a shape.

    The OAuth client now exists and the button works, so the disabled attribute
    would be the lie instead. Inverted rather than deleted, because the rule
    behind it — a control is pressable exactly when it does something — is the
    thing worth guarding.
    """
    assert "disabled" not in _button(), (
        "the sign-in button is disabled again while sign-in works")
    assert 'id="signin"' in _button(), "nothing can bind a handler to it"


def test_the_mark_ships_with_the_extension():
    """A src the packaged extension cannot resolve is a button with a hole in
    it, and nothing in the panel tests would see it — the harness inlines the
    page from a temporary directory."""
    manifest_dir = ROOT / "extension"
    src = re.search(r'src="([^"]*google-g\.png)"', _button()).group(1)

    assert (manifest_dir / src).exists(), (
        f"the button points at {src}, which is not in the shipped extension")
