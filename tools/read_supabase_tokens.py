"""Regenerate tests/fixtures/supabase-design-tokens.json from Supabase's own sources.

WHY A FIXTURE AND NOT A TABLE IN THE TEST. The first version of the marker guard typed
Supabase's stepped colour scales into the test file by hand -- 43 entries, against the 607
colour literals the files below actually declare. The consequence was not a smaller check
but a WRONG one: a marker reading `derived` on a value Supabase publishes outright passed
silently, because the guard could not find the literal to contradict it. Under-crediting
them is the direction every provenance error in this repository has run in.

Reading their files and writing what is there removes the transcription step entirely.

EVERY COUNT WRITTEN IN THIS FILE IS MEASURED AT THE PINNED COMMIT and moves when it does.
Two of them were left behind once already: this docstring said their sources declare "107
colour literals" while a comment below said "445 of their 607", and the two described
readings this tool no longer performs. Re-run it and read the summary it prints rather
than trusting a number written here.

RUN IT WHEN THE PINNED COMMIT MOVES, and only then. design/supabase.NOTICE.txt pins the
commit the values were taken from; this fixture records the same commit, and a test asserts
the two agree. So bumping one without the other fails rather than drifting.

    python tools/read_supabase_tokens.py              # rewrite the fixture
    python tools/read_supabase_tokens.py --check      # exit 1 if it WOULD change

`--check` is the convention tools/sync_design_assets.py already uses for a generated file
in this repository. It needs the network and the `gh` CLI, so CI does not run it; what CI
runs instead is the guard's `test_every_stored_literal_is_what_the_converter_produces`,
which re-derives every literal from the raw declaration stored beside it and needs neither.
"""
from __future__ import annotations

import argparse
import colorsys
import json
import math
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "supabase-design-tokens.json"
NOTICE = ROOT / "design" / "supabase.NOTICE.txt"

# THEIR DESIGN-SYSTEM TOKEN FILES, and which theme each one's literals belong to. `None`
# means read it for its NAMES only, so a marker naming a token they COMPUTE is still
# recognised as one of theirs.
#
# WHAT THIS LIST IS NOT. It is not every CSS file of theirs that declares a custom
# property: at the pinned commit their repository holds 118 CSS files, and 36 of the 105
# not listed here declare one. Those are application and example code -- `apps/learn`,
# `apps/studio`, the ten `examples/user-management/*` starters -- plus two inside
# `packages/`: a promo banner's CSS module and a tailwind plugin. None of them is a design
# token this product could have taken a value from, and admitting them would let a marker
# cite `--ion-background-color` from an Ionic demo and pass. The scope is
# `packages/ui/build/css/**` and `packages/config/css/**`, which is what these thirteen are.
#
# BASE.CSS AND VARIANTS.CSS DECLARE NOTHING at the pinned commit, and are listed anyway so
# that a future commit which starts declaring in them is read rather than missed. The
# guard asserts which files are empty, so this stops being true loudly.
#
# THE TWO CLASSIC-DARK THEMES ARE NAMES-ONLY DELIBERATELY. They declare 27 literals each
# for the same tokens themes/dark.css declares -- a second and third dark. This product
# ships ONE dark and it matches themes/dark.css, so admitting their values into the dark
# scope would let a marker cite a value from a theme this product does not ship and pass.
SOURCES = {
    "packages/ui/build/css/themes/light.css": "light",
    "packages/ui/build/css/themes/dark.css": "dark",
    "packages/ui/build/css/themes/classic-dark.css": None,
    "packages/ui/build/css/themes/faux-classic-dark.css": None,
    "packages/ui/build/css/source/global.css": "root",
    "packages/ui/build/css/source/semantic.css": None,
    "packages/ui/build/css/source/compat.css": None,
    "packages/config/css/animations.css": None,
    "packages/config/css/base.css": None,
    "packages/config/css/colors.css": "root",
    "packages/config/css/theme.css": None,
    "packages/config/css/utilities.css": None,
    "packages/config/css/variants.css": None,
    # THE DESIGN SITE'S OWN SHEET, NAMES ONLY (#1017). The font stacks, the type ramp and the
    # heading rule this product took are declared here (`--font-heading` at :15, the ramp at
    # :23-34), so a marker naming one must be recognised. Its colour literals are the site's
    # chrome, not a theme this product ships, so none of them is admitted as a value.
    "apps/design-system/styles/globals.css": None,
}

# The files above that declare no custom property at the pinned commit. Recorded so the
# fixture can carry it and the guard can assert it, rather than leaving a reader to wonder
# whether an empty file means "they declare nothing" or "this tool failed to read it".
DECLARE_NOTHING = (
    "packages/config/css/base.css",
    "packages/config/css/variants.css",
)

# `_` IS A LEGAL CUSTOM-PROPERTY CHARACTER AND THEY USE IT. Excluding it hid 11 names --
# `--_base`, `--_highlight`, `--_spread`, `--color-_secondary` and the five
# `--color-code_block-N` -- which is 11 names a `derived` marker could have invented
# without being caught, since the name check can only reject what it cannot find.
DECLARATION = re.compile(r"^\s*(--[A-Za-z0-9_-]+)\s*:\s*([^;]+);", re.M)

# They write literals three ways and the first version of this tool saw only two of them.
# The `hsl(...)`/`hsla(...)` function form is the dominant one by a long way; run the tool
# and read the summary for the split at the current commit.
#
# THE FOURTH GROUP IS THE ALPHA AND IT IS KEPT. It used to be matched by `(?:[,/].*)?` and
# thrown away, which recorded 62 alpha-bearing declarations as fully opaque -- including
# `--colors-gray-dark-alpha-100: hsla(0, 0%, 0%, 0)`, stored as `#000000`, an assertion
# that Supabase publishes opaque black where they publish full transparency.
HSL_FUNCTION = re.compile(
    r"hsla?\(\s*([\d.]+)(?:deg)?\s*[, ]\s*([\d.]+)%\s*[, ]\s*([\d.]+)%"
    r"(?:\s*[,/]\s*([\d.]+%?))?\s*\)"
)
# THE SPACE-SEPARATED FORM, AND IT IS NOT A RARE ONE: 106 of the 514 distinct conversions
# at the pinned commit come through here, second only to the function form's 406. An
# earlier comment called this whole path latent. That was wrong, and a wrong claim of
# latency is how a live branch goes untested.
#
# WHAT IS LATENT IS THE SPELLING WITHOUT `deg`. All 106 carry the unit today; `12 76% 61%`
# is the bare CSS Color 4 form and requiring the unit made it unreadable, so the unit is
# optional here -- it costs nothing and closes a shape that would otherwise be dropped in
# silence. Both spellings are driven by test_as_hex_reads_a_triple_with_and_without_deg.
HSL_TRIPLE = re.compile(r"([\d.]+)(?:deg)?\s+([\d.]+)%\s+([\d.]+)%")
HEX = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})")


def pinned_commit() -> str:
    """The commit design/supabase.NOTICE.txt says the values came from."""
    found = re.search(r"^\s*Commit\s+([0-9a-f]{40})", NOTICE.read_text(encoding="utf-8"), re.M)
    if not found:
        sys.exit("design/supabase.NOTICE.txt does not pin a 40-character commit")
    return found.group(1)


def fetch(path: str, ref: str) -> str:
    """One of their files, verbatim. Raw bytes, not a rendering or a summary."""
    result = subprocess.run(
        ["gh", "api", f"repos/supabase/supabase/contents/{path}?ref={ref}",
         "-H", "Accept: application/vnd.github.raw"],
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        sys.exit(f"could not read {path} at {ref[:8]}: {result.stderr.strip()}")
    return result.stdout


def _channel(value: float) -> int:
    """0-255, rounded HALF AWAY FROM ZERO -- which is what a CSS engine does.

    NOT Python's round(), which rounds ties to EVEN. Two of their literals land on an
    exact tie and the two rules disagree on both:

        hsl(206, 100%, 50%)   green = 144.5 exactly   round() 144   engine 145
        hsl(211, 100%, 15%)   blue  =  76.5 exactly   round()  76   engine  77

    Measured against Chromium 151, which returns `rgb(0, 145, 255)` and `rgb(0, 37, 77)`
    for those two. The Python answers are #0090ff and #00254c; the browser's are #0091ff
    and #00254d.

    WHY A ONE-UNIT DIFFERENCE MATTERS HERE. It is a false RED on a truthful PUBLISHED
    marker, and the repair a reader applies to a convincing false failure is to downgrade
    the marker to `derived` -- writing a false statement into the Apache 4(b) record, in
    the direction every provenance error in this repository has already run in.

    Every channel `colorsys.hls_to_rgb` can produce is in 0-1, so floor(v + 0.5) is
    exactly half-away-from-zero over that range -- swept at 0.5-degree steps across the
    whole h/s/l space, 0 of 1.4M points disagree with true half-away-from-zero and 0 fall
    outside 0-255.

    AND IT ASSERTS THAT RATHER THAN ASSUMING IT. `HSL_FUNCTION` and `HSL_TRIPLE` match
    `[\\d.]+` with no bound while a CSS engine clamps s and l to 0-100%, so a declaration
    like `hsl(0, 100%, 110%)` would reach here at 306 and `"%02x" % 306` is `"132"` --
    which pads and never truncates, producing `#ff132132`: a WELL-FORMED eight-digit hex
    that the guard's marker regex accepts and would store as a colour they publish. A
    browser renders that input `#ffffff`. No declaration at the pinned commit exceeds
    100%, so this is latent -- and this branch closed two other latent paths on exactly
    that reasoning, because a parse that fails loudly beats one that is quietly wrong.
    """
    byte = math.floor(value + 0.5)
    if not 0 <= byte <= 255:
        # NOT AN `assert`. PYTHONOPTIMIZE strips those, and issue 833 is open against
        # exactly that: a guard enforced with `assert` that goes green under -O. A
        # ValueError is also what scrapex/normalize.py raises when a parse will not
        # yield, and `sys.exit` is what this tool's other failure paths use -- both
        # survive the flag.
        raise ValueError(
            f"a colour channel converted to {byte}, which is not a byte. Their source "
            f"declared a value outside the range CSS clamps to, and '%02x' pads rather "
            f"than truncates -- so this would have been rendered as a plausible-looking "
            f"hex and stored as a colour they publish."
        )
    return byte


def _alpha_byte(alpha: str) -> int:
    """An hsl()/hsla() alpha -- `0.5` or `50%` -- as 0-255, rounded the same way."""
    raw = float(alpha[:-1]) / 100 if alpha.endswith("%") else float(alpha)
    return _channel(max(0.0, min(1.0, raw)) * 255)


def _hsl(hue: str, sat: str, light: str, alpha: str | None = None) -> str:
    """An HSL triple as hex; 8 digits when it carries an alpha that is not opaque."""
    red, green, blue = colorsys.hls_to_rgb(
        float(hue) / 360, float(light) / 100, float(sat) / 100
    )
    out = "#%02x%02x%02x" % (_channel(red * 255), _channel(green * 255), _channel(blue * 255))
    if alpha is None:
        return out
    opacity = _alpha_byte(alpha)
    return out if opacity == 255 else f"{out}{opacity:02x}"


#: Their classic themes -- a second and third dark this product does not ship. A block
#: selecting one of them contributes names and nothing else.
NOT_OUR_THEME = re.compile(r"classic", re.I)


def _names_a_theme_we_do_not_ship(selector: str) -> bool:
    """Does this block belong to a theme this product never renders?

    Such a block contributes NAMES ONLY, whatever scope its file carries. `colors.css`
    holds its dark under `[data-theme*='dark']` -- the dark that ships, and the one whose
    values belong in the dark table. `[data-theme='classic-dark'], .classic-dark` contains
    the same word and is a SECOND dark this product never renders.

    Returning the file's own scope for such a block is not a safe fallback either: a
    classic block inside a root-scoped file would then overwrite the true ROOT values.
    Names only is the reading the SOURCES map always meant.
    """
    return bool(NOT_OUR_THEME.search(selector))


def _selector_blocks(body: str) -> list[tuple[str, str]]:
    """(selector, declarations) for each top-level block, so a per-theme file is read
    as the several themes it is rather than as one flat list."""
    out, depth, start, selector = [], 0, None, ""
    for i, char in enumerate(body):
        if char == "{":
            if depth == 0:
                selector = body[:i].rsplit("}", 1)[-1].strip()
                start = i + 1
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start is not None:
                out.append((selector, body[start:i]))
                start = None
    return out or [("", body)]


def as_hex(value: str) -> str | None:
    """A published literal as hex, or None if the value is an expression.

    An HSL triple or an hsl() call converted to hex is a change of NOTATION, and the
    number is still theirs. Anything containing `var(`, `calc(`, `from ` or a `--value()`
    is arithmetic, and its output belongs to whoever evaluated it.

    ALPHA IS CARRIED, as a fourth hex byte. A value they publish with transparency is not
    the value they publish opaque, and recording it as the opaque one asserts something
    about their work that is not true.
    """
    if any(marker in value for marker in ("var(", "calc(", "from ", "--value(", "color-mix(")):
        return None
    call = HSL_FUNCTION.fullmatch(value)
    if call:
        return _hsl(*call.groups())
    triple = HSL_TRIPLE.fullmatch(value)
    if triple:
        return _hsl(triple.group(1), triple.group(2), triple.group(3))
    solid = HEX.fullmatch(value)
    if not solid:
        return None
    digits = solid.group(1).lower()
    if len(digits) in (3, 4):
        digits = "".join(c * 2 for c in digits)
    # An explicit fully-opaque alpha is dropped so the two spellings of the same opaque
    # colour compare equal; any other alpha is kept.
    if len(digits) == 8 and digits[6:] == "ff":
        digits = digits[:6]
    return "#" + digits


def read_declarations(body: str, scope: str | None):
    """One file's names, per-theme literals and conversions, read block by block.

    SEPARATE FROM `read()` SO THE SCOPING RULE CAN BE DRIVEN WITHOUT THE NETWORK. The two
    defects this function has had were both invisible in the real sources -- a last-wins
    scan that lost 185 light values, and a `None` scope promoted to dark by a substring --
    and neither could be reproduced from the fixture, because today's files happen to
    agree. `test_a_names_only_source_never_reaches_a_theme_table` drives it with input
    that has the defect.

    Returns (names, literals, conversions, declared). `declared` counts every
    declaration seen, which `read()` uses to record the files that declare nothing.
    """
    names: set[str] = set()
    literals: dict[str, dict[str, dict[str, str]]] = {"light": {}, "dark": {}, "root": {}}
    conversions: dict[str, str] = {}
    declared = 0

    for selector, block in _selector_blocks(body):
        # A FILE CAN CARRY MORE THAN ONE THEME, and reading it linearly loses one.
        # colors.css declares all 204 of its names TWICE -- once under `:root` and
        # once under `[data-theme*='dark']` -- with 185 of the pairs differing. A
        # last-wins scan of the whole file therefore stored the DARK value for every
        # one of them and dropped all 185 light values, which is how a correct light
        # marker would have been failed with Supabase's dark number quoted back at it.
        # A `None` SCOPE IS NAMES-ONLY AND NOTHING MAY PROMOTE IT. `"dark" in
        # selector` is a substring test, and both classic themes select on
        # `[data-theme='classic-dark'], .classic-dark` -- which contains the word.
        # So their 27 literals each were admitted into the dark table and overwrote
        # `themes/dark.css`, the exact thing the SOURCES comment says must not
        # happen. It passed only because the later of the two files happens to be
        # byte-identical to the dark this product ships; swapping those two keys
        # fails two TRUTHFUL `PUBLISHED` markers with a classic-dark value quoted
        # back at them.
        #
        # This is the substring-versus-whole-word class the guard already fixed once
        # in `_named_token`, where removing "dark" as a substring turned
        # `--colors-gray-light-900` into `--colors-gray--900`.
        if scope is None or _names_a_theme_we_do_not_ship(selector):
            block_scope = None
        elif "dark" in selector:
            block_scope = "dark"
        else:
            block_scope = scope
        for match in DECLARATION.finditer(block):
            token, value = match.group(1), " ".join(match.group(2).split())
            names.add(token)
            declared += 1
            hexed = as_hex(value)
            if hexed:
                conversions[value] = hexed
            if hexed and block_scope:
                # THE RAW DECLARATION IS STORED WITH THE TOKEN, not only in the
                # value-keyed `conversions` map, because the map cannot say WHICH
                # token a value belongs to or WHICH theme it landed in -- and that
                # association is exactly what a PUBLISHED marker is a statement
                # about. Without it, re-deriving the table proved only that `as_hex`
                # still works: overwriting all 299 root literals with other
                # converter-produced hexes failed nothing, and so did re-introducing
                # the per-theme defect the commit below this one fixed.
                literals[block_scope][token] = {"raw": value, "hex": hexed}
    return names, literals, conversions, declared


def read(ref: str) -> dict:
    """The whole reading at one commit: names, per-theme literals, and every conversion."""
    names: set[str] = set()
    literals: dict[str, dict[str, dict[str, str]]] = {"light": {}, "dark": {}, "root": {}}
    conversions: dict[str, str] = {}
    empty: list[str] = []

    for path, scope in SOURCES.items():
        body = re.sub(r"/\*.*?\*/", "", fetch(path, ref), flags=re.S)
        blocks = _selector_blocks(body)
        found, theirs, converted, declared = read_declarations(body, scope)
        names |= found
        conversions.update(converted)
        for theme, table in theirs.items():
            literals[theme].update(table)
        if declared == 0:
            empty.append(path)
        print(f"  read {path} ({len(blocks)} block{'' if len(blocks) == 1 else 's'}, "
              f"{declared} declaration{'' if declared == 1 else 's'})")

    return {
        "_what": "Supabase's declared custom-property names and colour literals, read from "
                 "their own sources at the commit design/supabase.NOTICE.txt pins. Generated "
                 "by reading those files, never typed.",
        "_why": "design/tokens.css marks each colour PUBLISHED or derived, and the notice "
                "delegates the Apache 4(b) per-value record to those markers. Checking a "
                "marker needs BOTH the set of names they declare -- so an invented name like "
                "--scale-900 fails -- and the set of values they publish, so a literal of "
                "theirs cannot be claimed as ours.",
        "_regenerate": "tools/read_supabase_tokens.py",
        "commit": ref,
        "files_read": sorted(SOURCES),
        # THE SCOPE HALF OF `SOURCES`, AND NOT ONLY ITS KEYS. Which theme each file's
        # literals are admitted into is a licence-correctness decision -- admitting the
        # classic-dark themes would let a marker cite a value from a dark this product
        # does not ship and pass -- and it was stated in prose and enforced by nothing.
        # Recording it lets the guard assert the fixture was read under the same map the
        # tool declares, the way `files_declaring_nothing` already does.
        "scopes": {path: scope for path, scope in sorted(SOURCES.items())},
        "files_declaring_nothing": sorted(empty),
        "names": sorted(names),
        "literals": {k: dict(sorted(v.items())) for k, v in literals.items()},
        # THE RAW DECLARATION BESIDE WHAT IT CONVERTED TO, which is what lets a test
        # re-derive the whole table offline and fail when this tool's arithmetic changes
        # without the fixture being regenerated. Nothing else asserted that.
        "conversions": dict(sorted(conversions.items())),
    }


def rendered(data: dict) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", help="commit to read; defaults to the one the notice pins")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if regenerating would change the fixture, and write nothing")
    args = parser.parse_args()
    ref = args.ref or pinned_commit()

    data = read(ref)
    text = rendered(data)

    literals = data["literals"]
    total = sum(len(v) for v in literals.values())
    print(f"\n  {len(data['names'])} names, {total} literals "
          f"(light {len(literals['light'])}, dark {len(literals['dark'])}, "
          f"root {len(literals['root'])}), {len(data['conversions'])} distinct conversions")
    if data["files_declaring_nothing"]:
        print(f"  declaring nothing: {', '.join(data['files_declaring_nothing'])}")

    if args.check:
        current = FIXTURE.read_text(encoding="utf-8") if FIXTURE.exists() else ""
        if current == text:
            print(f"  {FIXTURE.relative_to(ROOT)} is up to date")
            return
        sys.exit(
            f"  {FIXTURE.relative_to(ROOT)} is STALE at {ref[:8]}. Run "
            f"`python tools/read_supabase_tokens.py` and re-check every marker against it."
        )

    FIXTURE.write_text(text, encoding="utf-8", newline="\n")
    print(f"  wrote {FIXTURE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
