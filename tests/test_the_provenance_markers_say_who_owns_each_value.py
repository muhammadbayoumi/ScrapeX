"""Every colour in design/tokens.css says whose it is, and nothing checked the answer.

WHAT THE MARKERS ARE. Each colour declaration in design/tokens.css carries an inline
comment naming the Supabase token it came from and one of two words:

    --accent-ink: #097c4f;      /* brand-600 light       PUBLISHED */
    --amber:      #f2af48;      /* --warning dark        derived   */

`PUBLISHED` means Supabase declares that value as a literal -- their stepped numeric
scales are per-theme HSL triples, and converting a triple to hex is a change of
notation, not an evaluation. `derived` means the value is this product's own
evaluation of one of their expressions.

WHY THAT IS A LICENCE STATEMENT AND NOT A CONVENIENCE. design/supabase.NOTICE.txt
discharges Apache-2.0 section 4(b), and it delegates the per-value record to this
file: "WHICH IS WHICH IS RECORDED AT EACH VALUE in design/tokens.css". So a marker
pointing the wrong way is a wrong statement of changes, in the document a recipient
reads to learn what was taken.

WHAT WENT WRONG WITHOUT IT. Three markers drifted and no test could see any of them:
dark `--focus` and dark `--amber-ink` were marked PUBLISHED although their upstream
tokens -- `--ring` and `--warning-foreground` -- are expressions, and dark
`--line-strong` named `scale-900`, a token that exists nowhere in Supabase's themes.
All three over-credited Supabase with this product's own arithmetic.

HOW THIS CHECKS THEM WITHOUT A NETWORK. SUPABASE_SCALES below is Supabase's stepped
numeric scales, transcribed verbatim from packages/ui/build/css/themes/light.css and
dark.css at the commit design/supabase.NOTICE.txt pins. That is the complete set of
colour LITERALS they publish; everything else in their system is computed. So:

  * a `PUBLISHED` marker must name a token in that table, and the declaration must
    equal that literal converted to hex;
  * a `derived` marker must name a token that is NOT in it.

Both directions matter. The first stops us claiming their authorship; the second
stops us claiming ours.
"""
from __future__ import annotations

import colorsys
import re
from pathlib import Path

import pytest

# Guards a design asset copied into the extension by tools/sync_design_assets.py;
# see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
TOKENS = ROOT / "design" / "tokens.css"
NOTICE = ROOT / "design" / "supabase.NOTICE.txt"

# Verbatim from Supabase's own theme files at 86c813ec, under their comment
# "Stepped numeric scales (per-theme literals; mapped in theme.css)". These are the
# only colour literals their system publishes.
SUPABASE_SCALES = {
    "light": {
        "--secondary-default": "247.8deg 100% 70%",
        "--secondary-400": "248.3deg 54.5% 25.9%",
        "--secondary-200": "248deg 53.6% 11%",
        "--brand-link": "153.4deg 86.5% 27.8%",
        "--brand-default": "152.9deg 60% 52.9%",
        "--brand-600": "156.5deg 86.5% 26.1%",
        "--brand-500": "155.3deg 78.4% 40%",
        "--brand-400": "151.3deg 66.9% 66.9%",
        "--brand-300": "147.5deg 72% 80.4%",
        "--brand-200": "147.6deg 72.5% 90%",
        "--warning-600": "30.3deg 80.3% 47.8%",
        "--warning-500": "36.3deg 85.7% 67.1%",
        "--warning-400": "41.9deg 100% 81.8%",
        "--warning-300": "44.3deg 100% 91.8%",
        "--warning-200": "40deg 81.8% 97.8%",
        "--destructive-default": "10.2deg 77.9% 53.9%",
        "--destructive-600": "9.9deg 82% 43.5%",
        "--destructive-500": "10.4deg 77.1% 79.4%",
        "--destructive-400": "7.1deg 91.3% 91%",
        "--destructive-300": "7.1deg 100% 96.7%",
        "--destructive-200": "0deg 100% 99.4%",
    },
    "dark": {
        "--secondary-default": "247.8deg 100% 70%",
        "--secondary-400": "248.3deg 54.5% 25.9%",
        "--secondary-200": "248deg 53.6% 11%",
        "--brand-link": "155deg 100% 38.6%",
        "--brand-default": "153.1deg 60.2% 52.7%",
        "--brand-600": "154.9deg 59.5% 70%",
        "--brand-500": "154.9deg 100% 19.2%",
        "--brand-400": "155.5deg 100% 9.6%",
        "--brand-300": "155.1deg 100% 8%",
        "--brand-200": "162deg 100% 2%",
        "--warning-default": "38.9deg 100% 42.9%",
        "--warning-600": "38.9deg 100% 42.9%",
        "--warning-500": "34.8deg 90.9% 21.6%",
        "--warning-400": "33.2deg 100% 14.5%",
        "--warning-300": "32.3deg 100% 10.2%",
        "--warning-200": "36.6deg 100% 8%",
        "--destructive-default": "10.2deg 77.9% 53.9%",
        "--destructive-600": "9.7deg 85.2% 62.9%",
        "--destructive-500": "7.9deg 71.6% 29%",
        "--destructive-400": "6.7deg 60% 20.6%",
        "--destructive-300": "7.5deg 51.3% 15.3%",
        "--destructive-200": "10.9deg 23.4% 9.2%",
    },
}

MARKED = re.compile(
    r"^\s*(--[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\s*;\s*/\*\s*([^*]+?)\s*\*/", re.M
)


def _hsl_to_hex(triple: str) -> str:
    hue, sat, light = re.match(
        r"([\d.]+)deg\s+([\d.]+)%\s+([\d.]+)%$", triple.strip()
    ).groups()
    red, green, blue = colorsys.hls_to_rgb(
        float(hue) / 360, float(light) / 100, float(sat) / 100
    )
    return "#%02x%02x%02x" % (round(red * 255), round(green * 255), round(blue * 255))


def _blocks() -> list[tuple[str, str]]:
    """(scheme, block text) for the light and dark declaration blocks.

    The scheme comes from WHICH BLOCK the declaration is in, never from the comment
    beside it. An earlier version read the word "dark" out of the comment text, so a
    dark declaration whose comment omitted the word was checked against the light
    table -- which is how a wrong marker could be right for the wrong reason.
    """
    source = re.sub(r"/\*(?![^*]*(?:PUBLISHED|derived))[^*]*(?:\*(?!/)[^*]*)*\*/", "",
                    TOKENS.read_text(encoding="utf-8"))
    out = []
    for scheme, pattern in (("light", r":root\s*\{"), ("dark", r':root\[data-theme="dark"\]\s*\{')):
        match = re.search(pattern, source)
        assert match, f"no {scheme} block in design/tokens.css"
        depth, start = 0, match.end() - 1
        for i in range(start, len(source)):
            if source[i] == "{":
                depth += 1
            elif source[i] == "}":
                depth -= 1
                if depth == 0:
                    out.append((scheme, source[start:i]))
                    break
        else:
            raise AssertionError(f"the {scheme} block does not close")
    return out


def _markers() -> list[tuple[str, str, str, str, str]]:
    """(scheme, our token, our value, marker word, the upstream token it names)."""
    found = []
    for scheme, block in _blocks():
        for match in MARKED.finditer(block):
            token, value = match.group(1), match.group(2).lower()
            note = " ".join(match.group(3).split())
            marker = "PUBLISHED" if "PUBLISHED" in note else "derived" if "derived" in note else None
            if marker is None:
                continue
            claim = note.replace("PUBLISHED", "").replace("derived", "")
            claim = claim.replace("dark", "").replace("light", "").strip()
            named = claim if claim.startswith("--") else "--" + claim
            found.append((scheme, token, value, marker, named))
    return found


ALL = _markers()
PUBLISHED = [m for m in ALL if m[3] == "PUBLISHED"]
DERIVED = [m for m in ALL if m[3] == "derived"]


def test_the_file_still_carries_markers_to_check():
    """A regex that silently matches nothing is a green test that checks nothing.

    This is the floor: the parse found markers of both kinds. If the comment format
    changes, this fails first and says so, instead of every test below passing on an
    empty list.
    """
    assert len(PUBLISHED) >= 8 and len(DERIVED) >= 8, (
        f"parsed {len(PUBLISHED)} PUBLISHED and {len(DERIVED)} derived markers in "
        f"design/tokens.css. The comment format has changed and this guard is no "
        f"longer reading it; fix the parser rather than the floor."
    )


@pytest.mark.parametrize("scheme,token,value,_marker,named", PUBLISHED,
                         ids=[f"{m[0]}{m[1]}" for m in PUBLISHED])
def test_a_published_marker_names_a_literal_supabase_actually_publishes(
    scheme, token, value, _marker, named
):
    """PUBLISHED is a claim about THEIR authorship, so it is checked against them.

    The failure mode this catches, three times over: a semantic token Supabase
    computes, marked as though they had published the number this product arrived at
    by evaluating their expression.
    """
    literal = SUPABASE_SCALES[scheme].get(named)
    assert literal is not None, (
        f"{scheme} {token} is marked PUBLISHED naming {named}, which is not one of "
        f"Supabase's published scale literals. Either it is a token they COMPUTE -- "
        f"in which case this value is ours and the marker should read `derived` -- or "
        f"the name is wrong. There is no --scale-900; that exact mistake is why this "
        f"guard exists."
    )
    assert _hsl_to_hex(literal) == value, (
        f"{scheme} {token} is marked PUBLISHED as {named}, but {named} is {literal} "
        f"= {_hsl_to_hex(literal)} and this ships {value}. A PUBLISHED value must be "
        f"their literal, converted and nothing else."
    )


@pytest.mark.parametrize("scheme,token,value,_marker,named", DERIVED,
                         ids=[f"{m[0]}{m[1]}" for m in DERIVED])
def test_a_derived_marker_does_not_name_a_published_literal(
    scheme, token, value, _marker, named
):
    """The mirror, and it matters as much.

    `derived` claims the arithmetic is ours. If the named token is one they publish
    outright, the claim takes credit for a transcription -- the same error in the
    direction that under-credits them.
    """
    literal = SUPABASE_SCALES[scheme].get(named)
    if literal is None:
        return
    assert _hsl_to_hex(literal) != value, (
        f"{scheme} {token} is marked derived naming {named}, but {named} is a "
        f"published literal and this value equals it exactly. The marker should read "
        f"PUBLISHED: nothing was derived."
    )


def test_the_notice_still_delegates_the_record_to_these_markers():
    """The markers are only a licence statement while the notice says they are.

    If that delegation is ever removed from design/supabase.NOTICE.txt, this guard
    stops guarding an obligation and starts guarding a convention -- which is worth
    knowing rather than discovering.
    """
    notice = NOTICE.read_text(encoding="utf-8")
    assert "RECORDED AT EACH VALUE in design/tokens.css" in notice, (
        "design/supabase.NOTICE.txt no longer delegates the per-value provenance "
        "record to design/tokens.css. If the notice now states provenance itself, "
        "this guard should be checking the notice instead."
    )
