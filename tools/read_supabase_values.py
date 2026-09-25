"""Regenerate tests/fixtures/supabase-value-axes.json: every value Supabase declares or
renders on each axis a stylesheet here can hard-code, at the pinned commit (#699).

WHAT AN AXIS HOLDS. Two halves, read separately:

  declared  the scales their tokens name -- Tailwind's theme at the version their lockfile
            pins, as their own files override it (text sizes, the 450 weight, the mono
            ramp inside code), plus the tokens of their own that Tailwind does not have
            (--spacing-*, --radius-panel, --spacing-content, the --animate-* durations,
            the focus geometry of `focus-ring` and `focus-inset`);
  atoms     what `packages/ui/src/components` actually renders: every sizing class in
            their component sources, resolved to the value it produces, with how often
            and where it first appears. Arbitrary values -- `px-[5.5px]`, `z-[60]` --
            are the reason this half exists: no scale holds them, and they are theirs.

The guard, tests/test_every_value_is_one_supabase_uses.py, allows on each axis the union
of the two and freezes every other literal found today, by file and value.

RUN IT WHEN THE PINNED COMMIT MOVES, and only then.

    python tools/read_supabase_values.py              # rewrite the fixture
    python tools/read_supabase_values.py --check      # exit 1 if it WOULD change
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.read_supabase_tokens import fetch, pinned_commit  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "supabase-value-axes.json"
LOCKFILE = "pnpm-lock.yaml"
TYPE_RAMPS = "apps/design-system/styles/globals.css"
SPACING = "packages/ui/build/css/source/global.css"
THEME = "packages/config/css/theme.css"
ANIMATIONS = "packages/config/css/animations.css"
UTILITIES = "packages/config/css/utilities.css"
ATOMS = "packages/ui/src/components/"

DECLARATION = re.compile(r"^\s*(--[\w-]+)\s*:\s*([^;]+);", re.M)


def _declared(body: str, pattern: str) -> dict[str, str]:
    return {name: " ".join(value.split()) for name, value in DECLARATION.findall(body)
            if re.fullmatch(pattern, name)}


def _one(found: dict[str, str], what: str) -> dict[str, str]:
    """Every parse asserts its shape: a scale that reads as empty is a moved file."""
    if not found:
        sys.exit(f"read nothing for {what}; the file changed shape at the pin")
    return found


def tailwind_version(lock: str) -> str:
    """The tailwindcss packages/ui resolves, from its importer block in the lockfile."""
    block = re.search(r"\n  packages/ui:\n(.*?)(?=\n  [^\s])", lock, flags=re.S)
    if not block:
        sys.exit("the lockfile has no packages/ui importer")
    found = re.search(r"\n\s+tailwindcss:\n\s+specifier: .*\n\s+version: (\d+\.\d+\.\d+)",
                      block.group(1))
    if not found:
        sys.exit("packages/ui resolves no tailwindcss in the lockfile")
    return found.group(1)


def _block(body: str, selector: str) -> str:
    """The body of the first rule whose selector list is exactly `selector`."""
    found = re.search(rf"{re.escape(selector)}\s*\{{", body)
    if not found:
        sys.exit(f"no `{selector}` rule")
    depth, end = 1, found.end()
    while depth:
        depth += {"{": 1, "}": -1}.get(body[end], 0)
        end += 1
    return body[found.end():end - 1]


# A sizing class in their sources, and the axis it sets. The value group is a scale name,
# a number of --spacing steps, or an arbitrary `[...]`.
VALUE = r"(\[[^\]\s]+\]|\d+(?:\.\d+)?|px|none|full|xs|sm|base|md|lg|xl|[2-9]xl|tight|snug|normal|relaxed|loose|thin|extralight|light|medium|semibold|bold|extrabold|black)"
CLASSES = {
    "spacing": rf"-?(?:p[xytrblse]?|m[xytrblse]?|gap(?:-[xy])?|space-[xy])-{VALUE}",
    "radius": rf"rounded(?:-(?:[trblse]|[trbl][lr]|s[se]|e[se]))?(?:-{VALUE})?",
    "font-size": rf"text-{VALUE}",
    "line-height": rf"leading-{VALUE}",
    "font-weight": rf"font-{VALUE}",
    "duration": rf"duration-{VALUE}",
    "z-index": rf"-?z-{VALUE}",
}
CLASS = {axis: re.compile(rf"(?<![\w\[/-]){pattern}(?![\w.\]/-])") for axis, pattern in CLASSES.items()}


def _resolve(axis: str, token: str, scales: dict) -> str | None:
    """The value one class produces, or None when the class is not a sizing class."""
    name = token.rsplit("-", 1)[-1] if "[" not in token else token[token.index("[") + 1:-1]
    if "[" in token:
        return name.replace("_", " ")
    if axis == "spacing":
        if name == "px":
            return "1px"
        return f"{float(name) * scales['spacing']:g}rem" if re.fullmatch(r"\d+(\.\d+)?", name) else None
    if axis == "radius":
        # A bare `rounded` resolves the theme's own `--radius` (utilities.ts@v4.2.4:404-411).
        if token == "rounded" or re.fullmatch(r"rounded-(?:[trblse]|[trbl][lr]|s[se]|e[se])", token):
            return scales["radius"].get("--radius")
        return "full" if name == "full" else "0" if name == "none" else scales["radius"].get(f"--radius-{name}")
    if axis == "font-size":
        return scales["font-size"].get(f"--text-{name}")
    if axis == "line-height":
        if re.fullmatch(r"\d+(\.\d+)?", name):
            return f"{float(name) * scales['spacing']:g}rem"
        return "1" if name == "none" else scales["line-height"].get(f"--leading-{name}")
    if axis == "font-weight":
        return scales["font-weight"].get(f"--font-weight-{name}")
    if axis == "duration":
        return f"{name}ms" if re.fullmatch(r"\d+", name) else None
    if axis == "z-index":
        return ("-" if token.startswith("-") else "") + name if re.fullmatch(r"\d+", name) else None
    return None


def read(pin: str) -> dict:
    lock = fetch(LOCKFILE, pin)
    version = tailwind_version(lock)
    tailwind = fetch("packages/tailwindcss/theme.css", f"v{version}", repo="tailwindlabs/tailwindcss")
    ramps = fetch(TYPE_RAMPS, pin)
    theme = fetch(THEME, pin)
    animations = fetch(ANIMATIONS, pin)
    utilities = fetch(UTILITIES, pin)

    base = _one(_declared(tailwind, r"--spacing"), "Tailwind's --spacing")["--spacing"]
    step = float(re.fullmatch(r"([\d.]+)rem", base).group(1))
    sans = _one(_declared(tailwind, r"--text-(xs|sm|base|lg|xl|[2-9]xl)"), "Tailwind's text sizes")
    sans.update(_one(_declared(_block(ramps, "@theme"), r"--text-[\w]+"), "their text ramp"))
    mono = _one(_declared(_block(ramps, ".font-mono"), r"--text-[\w]+"), "their mono ramp")
    weights = _one(_declared(tailwind, r"--font-weight-\w+"), "Tailwind's weights")
    their_normal = _declared(_block(ramps, "@theme"), r"--font-weight-normal")
    mono_normal = _declared(_block(ramps, ".font-mono"), r"--font-weight-normal")
    leading = _one(_declared(tailwind, r"--leading-\w+"), "Tailwind's leading")
    text_leading = _one(_declared(tailwind, r"--text-(xs|sm|base|lg|xl|[2-9]xl)--line-height"),
                        "Tailwind's text line heights")
    radius = _one(_declared(tailwind, r"--radius(-\w+)?"), "Tailwind's radius")
    focus_inset = _block(utilities, "@utility focus-inset")
    ring = re.search(r"@utility focus-ring\s*\{([^}]*)\}", utilities)
    if not ring:
        sys.exit("no focus-ring utility")

    scales = {"spacing": step, "radius": radius, "font-size": sans,
              "line-height": leading, "font-weight": {**weights, **their_normal}}

    atoms: dict[str, dict[str, dict]] = {axis: {} for axis in CLASSES}
    tree = subprocess.run(["gh", "api", f"repos/supabase/supabase/git/trees/{pin}?recursive=1"],
                          capture_output=True, text=True, encoding="utf-8")
    if tree.returncode != 0:
        sys.exit(f"could not read the tree at {pin[:8]}: {tree.stderr.strip()}")
    listing = json.loads(tree.stdout)
    if listing.get("truncated"):
        sys.exit(f"GitHub truncated the tree at {pin[:8]}; a missing atom would be a guess")
    sources = sorted(entry["path"] for entry in listing["tree"] if entry["type"] == "blob"
                     and entry["path"].startswith(ATOMS) and entry["path"].endswith((".ts", ".tsx")))
    if not sources:
        sys.exit(f"no component sources under {ATOMS}")
    for path in sources:
        for number, line in enumerate(fetch(path, pin).splitlines(), 1):
            for axis, pattern in CLASS.items():
                for found in pattern.finditer(line):
                    value = _resolve(axis, found.group(0).lstrip("-") if axis != "z-index" else found.group(0), scales)
                    if value is None:
                        continue
                    seen = atoms[axis].setdefault(value, {"count": 0, "first": f"{path}:{number}"})
                    seen["count"] += 1

    return {
        "commit": pin,
        "tailwind": version,
        "atoms_read": len(sources),
        "axes": {
            "spacing": {"step_rem": step / 2, "declared": {
                **_one(_declared(fetch(SPACING, pin), r"--spacing-(scale|xs|sm|md|lg|xl)"), "their spacing"),
                **_one(_declared(theme, r"--spacing-content"), "--spacing-content")}},
            "radius": {"declared": {**radius, **_one(_declared(theme, r"--radius-panel"), "--radius-panel"),
                                    "full": "calc(infinity * 1px)"}},
            "font-size": {"sans": sans, "mono": mono},
            "line-height": {"declared": {**leading, **text_leading, "--leading-none": "1"}},
            "font-weight": {"declared": {**weights, **{f"{k} (theirs)": v for k, v in their_normal.items()},
                                         **{f"{k} (mono)": v for k, v in mono_normal.items()}}},
            "duration": {"declared": {
                **_one(_declared(tailwind, r"--default-transition-duration"), "Tailwind's default duration"),
                **{name: re.search(r"(\d*\.?\d+m?s)\b", value).group(1)
                   for name, value in _declared(_block(animations, "@theme"), r"--animate-[\w-]+").items()
                   if re.search(r"(\d*\.?\d+m?s)\b", value)}}},
            "easing": {"declared": {
                **_one(_declared(tailwind, r"--ease-(in|out|in-out)"), "Tailwind's easings"),
                **{f"{name} (curve)": curve for name, value in
                   _declared(_block(animations, "@theme"), r"--animate-[\w-]+").items()
                   for curve in re.findall(r"cubic-bezier\([^)]*\)", value)}}},
            "focus": {"declared": {
                "focus-ring ring width": re.search(r"ring-(\d+)\b", ring.group(1)).group(1) + "px",
                "focus-ring ring offset": re.search(r"ring-offset-(\d+)\b", ring.group(1)).group(1) + "px",
                "focus-inset outline-width": re.search(r"outline-width:\s*([^;]+);", focus_inset).group(1),
                "focus-inset outline-offset": re.search(r"outline-offset:\s*([^;]+);", focus_inset).group(1)}},
        },
        "atoms": {axis: dict(sorted(values.items())) for axis, values in atoms.items()},
    }


def rendered(data: dict) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if regenerating would change the fixture, and write nothing")
    args = parser.parse_args()
    pin = pinned_commit()
    text = rendered(read(pin))
    data = json.loads(text)
    print(f"  Tailwind {data['tailwind']}, {data['atoms_read']} component sources, "
          + ", ".join(f"{axis} {len(values)}" for axis, values in data["atoms"].items()))
    if args.check:
        current = FIXTURE.read_text(encoding="utf-8") if FIXTURE.exists() else ""
        if current == text:
            print(f"  {FIXTURE.relative_to(ROOT)} is up to date")
            return
        sys.exit(f"  {FIXTURE.relative_to(ROOT)} is STALE at {pin[:8]}. "
                 "Run `python tools/read_supabase_values.py`.")
    FIXTURE.write_text(text, encoding="utf-8", newline="\n")
    print(f"  wrote {FIXTURE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
