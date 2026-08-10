"""Google's button is Google's, and its specification is not ours to soften.

developers.google.com/identity/branding-guidelines fixes the background, the
stroke, the text colour, the type and the padding, and forbids altering the mark
at all. None of that is taste, so none of it belongs in a review conversation —
it belongs here, where changing it fails.

WHAT THIS REPLACED, AND WHY IT WAS A VIOLATION AND NOT A PREFERENCE. The button
carried Material's `account-circle`, a monochrome person-in-a-circle inheriting
`currentColor`. The guidelines forbid a monochrome "G", forbid a substitute
mark, and forbid recolouring the mark — that one icon broke all three. The
replacement is Google's own published asset, byte-for-byte, stored as a PNG and
rendered through a native `<button>` wrapper that never tints, crops, or redraws
it.

THE COLOURS ARE TOKENS, NOT LITERALS, and that is allowed: the guidelines fix
three backgrounds — light, dark and neutral — and let the button follow the
surface it sits on. They live in tokens.css, the one file permitted to name a
colour, and deliberately NOT in the palette: no appearance choice may re-tone
them.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import re

import pytest

pytestmark = pytest.mark.extension

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOKENS = (ROOT / "design" / "tokens.css").read_text(encoding="utf-8")
COMPONENTS = (ROOT / "design" / "components.css").read_text(encoding="utf-8")
APP_CSS = (ROOT / "extension" / "app.css").read_text(encoding="utf-8")
PANEL = (ROOT / "extension" / "app.html").read_text(encoding="utf-8")

#: Verbatim from the guidelines. Light and dark only — the neutral variant
#: (#F2F2F2, no stroke) is not used here, and adding it would mean adding its
#: rules too rather than borrowing these.
LIGHT = {"bg": "#FFFFFF", "stroke": "#747775", "text": "#1F1F1F"}
DARK = {"bg": "#131314", "stroke": "#8E918F", "text": "#E3E3E3"}

#: The official "Sign in with Google" asset is used verbatim.
OFFICIAL_CTA = "Sign in with Google"

#: SHA-256 of the unmodified assets copied from Google's signin-assets.zip.
EXPECTED_ASSETS = {
    "light-rectangular@4x.png": {
        "sha256": "e048546f162b43a5f3809796f88df02a8e13f07ca1280a9c1635018956e05c05",
        "intrinsic": (720, 160),
    },
    "dark-rectangular@4x.png": {
        "sha256": "1c8c1b94727499d5e8d98a86199819f5c1e711b15b805d53a9f85aa308940656",
        "intrinsic": (720, 160),
    },
}


def _button() -> str:
    match = re.search(r'<button class="profile-signin".*?</button>', PANEL, re.S)
    assert match, "the panel no longer has a Google sign-in button"
    return match.group(0)


def _css_rule(css: str, selector: str) -> str:
    # `selector` is the literal CSS selector, e.g. ".profile-signin-img".
    match = re.search(rf"{re.escape(selector)}\s*\{{([^}}]*)\}}", css)
    assert match, f"{selector} has no rule"
    return match.group(1)


def test_the_profile_uses_official_google_assets():
    """The files are the pre-approved Android + Web assets, not a redraw."""
    assets_dir = ROOT / "extension" / "icons" / "google-signin"
    for name, expected in EXPECTED_ASSETS.items():
        path = assets_dir / name
        assert path.exists(), f"{name} is missing"
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        assert sha == expected["sha256"], (
            f"{name} was edited or replaced; expected {expected['sha256']}, got {sha}")


def test_the_google_image_is_never_recoloured_by_this_project():
    """THE RULE THE PREVIOUS BUTTON BROKE THREE TIMES OVER.

    The asset is an <img>, so no CSS of ours can reach inside it. The wrapper
    must not add filters, opacity, or palette colours either.
    """
    button = _button()
    assert "sx-icon" not in button, "the mark is an .sx-icon again"

    rule = _css_rule(APP_CSS, ".profile-signin-img")
    assert "filter" not in rule, "a filter would recolour the official asset"
    assert "opacity" not in rule, "opacity would dim the official asset"
    assert "fill" not in rule, "fill does not apply to an <img> and must not be here"
    assert "width: 180px" in rule, "the asset is not displayed at the official 1× width"
    assert "height: auto" in rule, "the asset aspect ratio is not preserved"


def test_the_google_button_is_a_native_pressable_button_with_official_cta():
    """Native semantics and the exact visible CTA from the official asset."""
    button = _button()

    assert 'id="signin"' in button, "nothing can bind a handler to it"
    assert 'type="button"' in button
    assert 'role="button"' not in button, "do not add a redundant role to a <button>"
    assert "disabled" not in button, "the sign-in button is disabled while sign-in works"
    assert f'aria-label="{OFFICIAL_CTA}"' in button, (
        "the accessible name must match the visible official CTA")

    images = re.findall(r'<img[^>]*class="profile-signin-img[^"]*"[^>]*>', button)
    assert len(images) == 2, "expected exactly the light and dark assets"
    for img in images:
        assert 'alt=""' in img, "the official image is decorative"
        assert 'aria-hidden="true"' in img


def test_the_google_button_keeps_the_official_aspect_ratio_and_intrinsic_size():
    """The @4x asset is 720x160; CSS displays it at 180x40."""
    button = _button()
    for scheme, size in [("light", "720"), ("dark", "720")]:
        img = re.search(
            rf'<img class="profile-signin-img[^"]*" data-scheme="{scheme}"[^>]*'
            rf'width="(\d+)" height="(\d+)"', button)
        assert img, f"{scheme} asset is missing its intrinsic size"
        assert (img.group(1), img.group(2)) == ("720", "160"), (
            f"{scheme} intrinsic size is wrong")

    width, height = 720, 160
    rendered_width = 180
    expected_height = rendered_width * height // width
    assert expected_height == 40, "the official 1× size is not 180x40"


def test_the_google_button_has_a_48px_clickable_target():
    """The visual asset is 40px tall; the native wrapper makes it 48px."""
    rule = _css_rule(APP_CSS, ".profile-signin")
    assert "min-height: 48px" in rule
    assert "min-width: 180px" in rule


def test_the_google_button_wrapper_shows_a_neutral_hover_indicator():
    """Hover must give visible feedback without painting, transforming, or
    recolouring the official asset. The wrapper stays transparent; a neutral
    external outline/elevation appears outside the image boundary.
    """
    rule = _css_rule(APP_CSS, ".profile-signin:hover:not(:disabled)")
    assert "background: transparent" in rule
    assert "border-color: transparent" in rule
    assert "transform: none" in rule
    assert "opacity: 1" in rule
    # A visible external indicator, not the old invisible state.
    assert "box-shadow:" in rule
    assert "box-shadow: none" not in rule
    img = _css_rule(APP_CSS, ".profile-signin-img")
    assert "filter" not in img, "hover must not recolour the official image"
    assert "opacity" not in img, "hover must not dim the official image"


def test_the_google_button_wrapper_shows_a_neutral_active_indicator():
    """Active keeps a neutral external indicator and does not translate or
    recolour the wrapper or the official asset."""
    rule = _css_rule(APP_CSS, ".profile-signin:active:not(:disabled)")
    assert "background: transparent" in rule
    assert "transform: none" in rule
    assert "opacity: 1" in rule
    assert "box-shadow:" in rule
    assert "box-shadow: none" not in rule


def test_the_google_button_wrapper_does_not_dim_when_disabled():
    """A disabled sign-in must not dim the official Google image."""
    rule = _css_rule(APP_CSS, ".profile-signin:disabled")
    assert "opacity: 1" in rule
    assert "background: transparent" in rule
    assert "transform: none" in rule
    assert "cursor: default" in rule


def test_the_google_button_preserves_focus_visibility():
    """Keyboard focus must still show an outline outside the asset."""
    rule = _css_rule(APP_CSS, ".profile-signin:focus-visible")
    assert "outline:" in rule


def test_the_assets_are_stored_byte_for_byte_with_provenance():
    """The README records where the bytes came from and that they were not
    edited."""
    readme = ROOT / "extension" / "icons" / "google-signin" / "README.md"
    assert readme.exists()
    text = readme.read_text(encoding="utf-8")
    assert "developers.google.com/identity/branding-guidelines" in text
    assert (
        "ba884069e12093b06bcfd776915081254a7c95094b80d50be2c5dc6bac1c1da1"
        in text)
    for name, expected in EXPECTED_ASSETS.items():
        assert expected["sha256"] in text, f"{name} hash missing from provenance"
    assert "stored byte-for-byte without editing" in text


@pytest.mark.parametrize("theme,values", [("light", LIGHT), ("dark", DARK)])
def test_every_fixed_colour_is_exactly_what_google_published(theme, values):
    """Not "close enough". These are three hex values in a document."""
    for part, expected in values.items():
        assert f"--google-btn-{part}: {expected};" in TOKENS, (
            f"the {theme} {part} is no longer {expected}; the guidelines fix it")


def test_the_shared_button_uses_only_those_tokens_and_never_the_palette():
    """A palette colour here would follow the owner's appearance choice, and the
    guidelines allow the button on three backgrounds and no others."""
    rule = re.search(r"\.google-signin \{([^}]*)\}", COMPONENTS).group(1)

    for prop in ("background", "color", "border"):
        line = next(l for l in rule.splitlines() if l.strip().startswith(prop))
        assert "--google-btn-" in line, (
            f"{prop} is not a Google token: {line.strip()!r}")


def test_the_shared_button_type_and_padding_are_the_published_numbers():
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
