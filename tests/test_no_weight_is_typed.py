"""Every font-weight a stylesheet writes is a token, `inherit` or `normal` (#713).

Supabase's ramp is 450, 500 and 600, with 600 its ceiling (their atoms render no font-bold and
no font-extrabold; design/tokens.css records the measurement). The #699 axis in
tools/value_literals.py cannot hold that ceiling, because it allows Tailwind's whole 100-900,
so a 700 or a 750 typed into a sheet passed it. Here a weight is named by its token, and only
`inherit` and `normal` are written as words; `bold` and `bolder` are 700 by another name.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools.value_literals import authored, declarations

# Guards stylesheets the extension ships; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parents[1]
#: A weight token, with or without a numeric fallback (test_design_system.py holds every
#: fallback to its token), or one of the two keywords that name no number.
ALLOWED = re.compile(r"var\(--fw-[a-z-]+(?:,\s*[0-9]+)?\)|inherit|normal")
ALIAS = re.compile(r"var\((--[a-z0-9-]+)\)")
#: The weight in a `font` shorthand comes before the size; a number or `bold` there is a weight.
SHORTHAND_WEIGHT = re.compile(r"(?<![\w.(-])(?:[1-9]00|[1-9][0-9]{2}|bold|bolder|lighter)(?![\w.%-])")


def _aliases() -> dict[str, str]:
    """Custom properties declared in the sheets and tokens, so a component token that names a
    weight token (`--grid-header-weight: var(--fw-heavy)`) is followed one step."""
    found = {}
    for sheet in [*authored(), ROOT / "design" / "tokens.css"]:
        for _selector, prop, value, _line in declarations(sheet.read_text(encoding="utf-8")):
            if prop.startswith("--"):
                found.setdefault(prop, " ".join(value.split()))
    return found


def _allowed(value: str, aliases: dict[str, str]) -> bool:
    if ALLOWED.fullmatch(value):
        return True
    alias = ALIAS.fullmatch(value)
    return bool(alias and ALLOWED.fullmatch(aliases.get(alias.group(1), "")))


def _typed_weights():
    wrong, read, aliases = [], 0, _aliases()
    for sheet in authored():
        name = sheet.relative_to(ROOT).as_posix()
        for selector, prop, value, line in declarations(sheet.read_text(encoding="utf-8")):
            value = " ".join(value.split())
            if prop == "font-weight":
                read += 1
                if not _allowed(value, aliases):
                    wrong.append(f"{name}:{line} {selector.strip()[:60]} {{font-weight: {value}}}")
            elif prop == "font" and SHORTHAND_WEIGHT.search(re.sub(r"var\([^)]*\)", "", value)):
                wrong.append(f"{name}:{line} {selector.strip()[:60]} {{font: {value}}}")
    return wrong, read


def test_no_weight_is_typed():
    wrong, read = _typed_weights()
    assert read > 100, f"only {read} font-weight declarations were read"
    assert not wrong, "weights written as numbers or words other than inherit and normal:\n  " + "\n  ".join(wrong)


@pytest.mark.parametrize("value,typed", [
    ("var(--fw-bold)", False), ("inherit", False), ("normal", False),
    ("var(--fw-medium, 500)", False), ("var(--grid-header-weight)", False),
    ("600", True), ("750", True), ("bold", True), ("bolder", True), ("var(--not-a-weight)", True),
])
def test_the_weight_rule_reads_tokens_and_two_keywords_only(value, typed):
    assert (not _allowed(value, _aliases())) is typed
