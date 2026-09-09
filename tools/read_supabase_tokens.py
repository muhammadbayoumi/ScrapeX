"""Regenerate tests/fixtures/supabase-design-tokens.json from Supabase's own sources.

WHY A FIXTURE AND NOT A TABLE IN THE TEST. The first version of the marker guard typed
Supabase's stepped colour scales into the test file by hand -- 43 entries. Their sources
declare 631 token names and 107 colour literals, so that table was missing 64 literals,
including every one of the 52 in global.css. The consequence was not a smaller check but a
WRONG one: a marker reading `derived` on a value Supabase publishes outright passed
silently, because the guard could not find the literal to contradict it. Under-crediting
them is the direction every provenance error in this repository has run in.

Reading their files and writing what is there removes the transcription step entirely.

RUN IT WHEN THE PINNED COMMIT MOVES, and only then. design/supabase.NOTICE.txt pins the
commit the values were taken from; this fixture records the same commit, and a test asserts
the two agree. So bumping one without the other fails rather than drifting.

    python tools/read_supabase_tokens.py

It needs the network and the `gh` CLI. Tests never do: they read the fixture.
"""
from __future__ import annotations

import argparse
import colorsys
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURE = ROOT / "tests" / "fixtures" / "supabase-design-tokens.json"
NOTICE = ROOT / "design" / "supabase.NOTICE.txt"

# EVERY CSS FILE OF THEIRS THAT DECLARES A CUSTOM PROPERTY, and which theme each one's
# literals belong to. `None` means read it for its NAMES only, so a marker naming a token
# they COMPUTE is still recognised as one of theirs.
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
}

DECLARATION = re.compile(r"^\s*(--[A-Za-z0-9-]+)\s*:\s*([^;]+);", re.M)
# They write literals three ways and the first version of this tool saw only two of them.
# `hsl(39, 70%, 99%)` is the dominant form -- 445 of their 607 literals, 397 in colors.css
# and 48 in global.css, a file this tool already read and whose literals it still missed.
HSL_FUNCTION = re.compile(r"hsla?\(\s*([\d.]+)(?:deg)?\s*[, ]\s*([\d.]+)%\s*[, ]\s*([\d.]+)%\s*(?:[,/].*)?\)")
HSL_TRIPLE = re.compile(r"([\d.]+)deg\s+([\d.]+)%\s+([\d.]+)%")
HEX = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})")


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


def _hsl(hue: str, sat: str, light: str) -> str:
    red, green, blue = colorsys.hls_to_rgb(
        float(hue) / 360, float(light) / 100, float(sat) / 100
    )
    return "#%02x%02x%02x" % (round(red * 255), round(green * 255), round(blue * 255))


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
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return "#" + digits[:6]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", help="commit to read; defaults to the one the notice pins")
    args = parser.parse_args()
    ref = args.ref or pinned_commit()

    names: set[str] = set()
    literals: dict[str, dict[str, str]] = {"light": {}, "dark": {}, "root": {}}
    for path, scope in SOURCES.items():
        body = re.sub(r"/\*.*?\*/", "", fetch(path, ref), flags=re.S)
        blocks = _selector_blocks(body)
        for selector, block in blocks:
            # A FILE CAN CARRY MORE THAN ONE THEME, and reading it linearly loses one.
            # colors.css declares all 204 of its names TWICE -- once under `:root` and
            # once under `[data-theme*='dark']` -- with 185 of the pairs differing. A
            # last-wins scan of the whole file therefore stored the DARK value for every
            # one of them and dropped all 185 light values, which is how a correct light
            # marker would have been failed with Supabase's dark number quoted back at it.
            block_scope = "dark" if "dark" in selector else scope
            for match in DECLARATION.finditer(block):
                token, value = match.group(1), " ".join(match.group(2).split())
                names.add(token)
                hexed = as_hex(value)
                if hexed and block_scope:
                    literals[block_scope][token] = hexed
        print(f"  read {path} ({len(blocks)} block{'' if len(blocks) == 1 else 's'})")

    FIXTURE.write_text(json.dumps({
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
        "names": sorted(names),
        "literals": {k: dict(sorted(v.items())) for k, v in literals.items()},
    }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    print(f"\n  {len(names)} names, "
          f"{sum(len(v) for v in literals.values())} literals "
          f"(light {len(literals['light'])}, dark {len(literals['dark'])}, "
          f"root {len(literals['root'])})")
    print(f"  wrote {FIXTURE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
