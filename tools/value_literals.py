"""Every hard-coded value on a design axis in the stylesheets this repository authors, and
whether Supabase uses it (#699).

A value that `var()`s a token is not a literal and is never read here. A literal is
allowed when it is one Supabase declares or renders on that axis at the pinned commit,
as tools/read_supabase_values.py reads them into tests/fixtures/supabase-value-axes.json.
Every other literal is an OFFENDER, and today's are frozen, by axis, file and value with
how many times each occurs, in tests/fixtures/value-literals-frozen.json. The guard,
tests/test_every_value_is_one_supabase_uses.py, fails on a new one and on a frozen one
that has gone, so the list only shrinks.

    python tools/value_literals.py --freeze     # rewrite the frozen list from today

AUTHORED means written here: design/components.css is read, and its two synced copies are
not, or every value in it would count three times. design/tokens.css is where the tokens
are defined, so it is not read either. Vendor sheets are not ours.

WHAT IS NOT READ. Keywords (`bold`, `ease-out`, `auto`), zero, and any value that holds a
`var()`. The `font` and `inset` shorthands. Colour has its own guard
(tests/test_vendor.py).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.sync_design_assets import ASSETS  # noqa: E402

SUPABASE = ROOT / "tests" / "fixtures" / "supabase-value-axes.json"
FROZEN = ROOT / "tests" / "fixtures" / "value-literals-frozen.json"
FOLDERS = (ROOT / "design", ROOT / "extension", ROOT / "scrapex" / "webui" / "static")

PROPERTIES = {
    "spacing": re.compile(r"(padding|margin)(-(top|right|bottom|left|inline|block)(-(start|end))?)?|gap|row-gap|column-gap"),
    "radius": re.compile(r"border(-(top|bottom)-(left|right)|-(start|end)-(start|end))?-radius"),
    "font-size": re.compile(r"font-size"),
    "line-height": re.compile(r"line-height"),
    "font-weight": re.compile(r"font-weight"),
    "duration": re.compile(r"(transition|animation)(-(duration|delay))?"),
    "easing": re.compile(r"(transition|animation)(-timing-function)?"),
    "z-index": re.compile(r"z-index"),
    "focus": re.compile(r"outline(-(width|offset))?"),
}
LENGTH = re.compile(r"(?<![\w.#-])(-?\d*\.?\d+)(px|rem|em|%|vh|vw|ch)(?![\w-])")
NUMBER = re.compile(r"(?<![\w.#-])(-?\d*\.?\d+)(?![\w.%-])")
TIME = re.compile(r"(?<![\w.#-])(-?\d*\.?\d+)(ms|s)(?![\w-])")
CURVE = re.compile(r"cubic-bezier\(([^)]*)\)")
MONO = re.compile(r"(?:^|[\s>+~(,])(?:code|pre|kbd|samp)(?![\w-])|\.font-mono(?![\w-])|\.code-content(?![\w-])")


def authored() -> list[Path]:
    copies = {copy.resolve() for destinations in ASSETS.values() for copy in destinations}
    tokens = (ROOT / "design" / "tokens.css").resolve()
    return [sheet for folder in FOLDERS for sheet in sorted(folder.rglob("*.css"))
            if "vendor" not in sheet.parts and sheet.resolve() not in copies | {tokens}]


def declarations(css: str) -> list[tuple[str, str, str, int]]:
    """(selector, property, value, line) for every declaration, the selector being the
    nearest enclosing rule that is not an at-rule. Comments go first and keep their
    newlines, so each line number is the file's own."""
    css = re.sub(r"/\*.*?\*/", lambda m: "\n" * m.group(0).count("\n"), css, flags=re.S)
    stack: list[str] = []
    found = []
    start = 0
    for index, char in enumerate(css):
        if char not in "{};":
            continue
        chunk = css[start:index]
        if char == "{":
            stack.append(" ".join(chunk.split()))
        else:
            declaration = re.fullmatch(r"\s*([a-zA-Z-]+)\s*:\s*(.+?)\s*", chunk, flags=re.S)
            if declaration and stack:
                selector = next((s for s in reversed(stack) if not s.startswith("@")), "")
                line = css.count("\n", 0, start + len(chunk) - len(chunk.lstrip())) + 1
                found.append((selector, declaration.group(1).lower(),
                              " ".join(declaration.group(2).split()), line))
            if char == "}":
                if not stack:
                    raise ValueError("a `}` closes nothing: a brace inside a string, or a broken sheet")
                stack.pop()
        start = index + 1
    if stack:
        raise ValueError(f"{len(stack)} rule(s) never close: {stack[-1]!r}")
    return found


def _without_tokens(value: str) -> str:
    """The value with every var() gone, and every color-mix(), whose percentages are
    proportions of a colour and not lengths."""
    while "var(" in value:
        value = re.sub(r"var\([^()]*\)", "", value)
    return re.sub(r"color-mix\([^()]*\)", "", value)


def literals(axis: str, prop: str, value: str) -> list[str]:
    """The hard-coded values one declaration states on one axis."""
    if not PROPERTIES[axis].fullmatch(prop):
        return []
    value = _without_tokens(value).replace("!important", "")
    if axis == "easing":
        return ["cubic-bezier(" + ", ".join(f"{float(x):g}" for x in curve.split(",")) + ")"
                for curve in CURVE.findall(value)]
    value = CURVE.sub("", re.sub(r"steps\([^)]*\)", "", value))
    if axis == "duration":
        return [f"{n}{u}" for n, u in TIME.findall(value) if float(n) != 0]
    if axis in ("font-weight", "z-index"):
        return [n for n in NUMBER.findall(value) if float(n) != 0]
    if axis == "line-height":
        lengths = [f"{n}{u}" for n, u in LENGTH.findall(value) if float(n) != 0]
        return lengths or [n for n in NUMBER.findall(value) if float(n) != 0]
    return [f"{n}{u}" for n, u in LENGTH.findall(value) if float(n) != 0]


def _px(value: str) -> float | None:
    found = re.fullmatch(r"(-?\d*\.?\d+)(px|rem)", value)
    if not found:
        return None
    return float(found.group(1)) * (16 if found.group(2) == "rem" else 1)


def _ms(value: str) -> float | None:
    found = re.fullmatch(r"(-?\d*\.?\d+)(ms|s)", value)
    return None if not found else float(found.group(1)) * (1 if found.group(2) == "ms" else 1000)


def _number(value: str) -> float | None:
    calc = re.fullmatch(r"calc\(\s*([\d.]+)\s*/\s*([\d.]+)\s*\)", value)
    if calc:
        return float(calc.group(1)) / float(calc.group(2))
    return float(value) if re.fullmatch(r"-?\d*\.?\d+", value) else None


def allowances(supabase: dict) -> dict:
    """What each axis allows, from the reading of Supabase at the pin."""
    axes, atoms = supabase["axes"], supabase["atoms"]

    def px_set(*groups):
        return {round(p, 4) for group in groups for v in group if (p := _px(v)) is not None}

    return {
        "spacing_step_px": axes["spacing"]["step_rem"] * 16,
        # A negative margin uses the same step as a positive one, so spacing is compared
        # by magnitude.
        "spacing": {abs(p) for p in px_set(axes["spacing"]["declared"].values(), atoms["spacing"])},
        "radius": px_set(axes["radius"]["declared"].values(), atoms["radius"]),
        "font-size": px_set(axes["font-size"]["sans"].values(), atoms["font-size"]),
        "font-size mono": px_set(axes["font-size"]["mono"].values(), atoms["font-size"]),
        "line-height": {round(n, 4) for v in [*axes["line-height"]["declared"].values(), *atoms["line-height"]]
                        if (n := _number(v)) is not None},
        "line-height px": px_set(atoms["line-height"]),
        "font-weight": {int(v) for v in [*axes["font-weight"]["declared"].values(), *atoms["font-weight"]]
                        if re.fullmatch(r"\d+", v)},
        "duration": {round(m, 4) for v in [*axes["duration"]["declared"].values(), *atoms["duration"]]
                     if (m := _ms(v)) is not None},
        "easing": {"cubic-bezier(" + ", ".join(f"{float(x):g}" for x in c.split(",")) + ")"
                   for v in axes["easing"]["declared"].values() for c in CURVE.findall(v)},
        "z-index": {int(v) for v in atoms["z-index"] if re.fullmatch(r"-?\d+", v)},
        # focus-ring draws a 2px ring at a 2px offset; focus-inset a 2px outline at -2px.
        "focus": {"outline-width": px_set([axes["focus"]["declared"]["focus-inset outline-width"]]),
                  "outline-offset": px_set([axes["focus"]["declared"]["focus-inset outline-offset"],
                                            axes["focus"]["declared"]["focus-ring ring offset"]])},
    }


def allowed(axis: str, selector: str, prop: str, literal: str, rules: dict) -> bool:
    if axis == "spacing":
        px = _px(literal)
        if px is None:
            return False
        step = rules["spacing_step_px"]
        return abs(px / step - round(px / step)) < 1e-6 or round(abs(px), 4) in rules["spacing"]
    if axis in ("radius", "font-size"):
        px = _px(literal)
        pool = rules["font-size mono"] if axis == "font-size" and MONO.search(selector) else rules[axis]
        return px is not None and round(px, 4) in pool
    if axis == "line-height":
        px = _px(literal)
        if px is not None:
            return abs(px / 4 - round(px / 4)) < 1e-6 or round(px, 4) in rules["line-height px"]
        number = _number(literal)
        return number is not None and any(abs(number - n) < 1e-3 for n in rules["line-height"])
    if axis == "font-weight":
        return int(float(literal)) in rules["font-weight"]
    if axis == "duration":
        ms = _ms(literal)
        return ms is not None and round(ms, 4) in rules["duration"]
    if axis == "easing":
        return literal in rules["easing"]
    if axis == "z-index":
        return int(float(literal)) in rules["z-index"]
    if axis == "focus":
        if ":focus" not in selector:
            return True
        px = _px(literal)
        pool = rules["focus"]["outline-offset" if prop == "outline-offset" else "outline-width"]
        return px is not None and round(px, 4) in pool
    raise ValueError(axis)


def offenders(supabase: dict | None = None) -> dict[str, dict[str, dict[str, int]]]:
    """{axis: {file: {literal: count}}} for every literal Supabase does not use."""
    rules = allowances(supabase or json.loads(SUPABASE.read_text(encoding="utf-8")))
    found: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    for sheet in authored():
        name = sheet.relative_to(ROOT).as_posix()
        for selector, prop, value, _line in declarations(sheet.read_text(encoding="utf-8")):
            for axis in PROPERTIES:
                for literal in literals(axis, prop, value):
                    if not allowed(axis, selector, prop, literal, rules):
                        found[axis][name][literal] += 1
    return {axis: {name: dict(sorted(values.items())) for name, values in sorted(files.items())}
            for axis, files in sorted(found.items())}


def rendered(data: dict) -> str:
    return json.dumps(data, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", action="store_true", help="rewrite the frozen list from today")
    args = parser.parse_args()
    data = offenders()
    total = sum(n for files in data.values() for values in files.values() for n in values.values())
    print(f"  {total} literals Supabase does not use: "
          + ", ".join(f"{axis} {sum(sum(v.values()) for v in files.values())}" for axis, files in data.items()))
    if args.freeze:
        FROZEN.write_text(rendered(data), encoding="utf-8", newline="\n")
        print(f"  wrote {FROZEN.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
