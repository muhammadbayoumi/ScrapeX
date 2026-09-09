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

# Their files, and which theme each one's literals belong to. `None` means the file
# declares no per-theme literals -- it is read for its NAMES, so that a marker naming a
# token they compute is still recognised as one of theirs.
SOURCES = {
    "packages/ui/build/css/themes/light.css": "light",
    "packages/ui/build/css/themes/dark.css": "dark",
    "packages/ui/build/css/source/global.css": "root",
    "packages/ui/build/css/source/semantic.css": None,
    "packages/ui/build/css/source/compat.css": None,
    "packages/config/css/animations.css": None,
    "packages/config/css/theme.css": None,
}

DECLARATION = re.compile(r"^\s*(--[A-Za-z0-9-]+)\s*:\s*([^;]+);", re.M)
HSL_TRIPLE = re.compile(r"([\d.]+)deg\s+([\d.]+)%\s+([\d.]+)%")
HEX = re.compile(r"#([0-9a-fA-F]{6})")


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


def as_hex(value: str) -> str | None:
    """A published literal as hex, or None if the value is an expression.

    An HSL triple converted to hex is a change of NOTATION. Anything containing
    `oklch(`, `var(`, `calc(` or `from ` is arithmetic, and its output belongs to
    whoever evaluated it.
    """
    triple = HSL_TRIPLE.fullmatch(value)
    if triple:
        red, green, blue = colorsys.hls_to_rgb(
            float(triple.group(1)) / 360, float(triple.group(3)) / 100, float(triple.group(2)) / 100
        )
        return "#%02x%02x%02x" % (round(red * 255), round(green * 255), round(blue * 255))
    solid = HEX.fullmatch(value)
    return "#" + solid.group(1).lower() if solid else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", help="commit to read; defaults to the one the notice pins")
    args = parser.parse_args()
    ref = args.ref or pinned_commit()

    names: set[str] = set()
    literals: dict[str, dict[str, str]] = {"light": {}, "dark": {}, "root": {}}
    for path, scope in SOURCES.items():
        body = re.sub(r"/\*.*?\*/", "", fetch(path, ref), flags=re.S)
        for match in DECLARATION.finditer(body):
            token, value = match.group(1), " ".join(match.group(2).split())
            names.add(token)
            hexed = as_hex(value)
            if hexed and scope:
                literals[scope][token] = hexed
        print(f"  read {path}")

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
