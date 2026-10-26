"""Supabase's status steps and status borders are declared, at their values (#633).

His ruling of 2026-08-29 said no to the numeric ramps and yes to the four status borders;
the roadmap he approved on 2026-09-24 (#1040, the comment on #633) rescoped it to both: the
steps their components read (Button.tsx@86c813ec:28-96, badge.tsx, alert.tsx, Admonition,
StatusIcon) and the four --border-{brand,destructive,info,warning}. Each step takes the
literal tests/fixtures/supabase-design-tokens.json read at the pin; --info and the borders
are OKLCH expressions there, so they are checked at their evaluated values, as --amber and
--red already are. A role token that equals a step names it, so each value is written once.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.test_the_provenance_markers_say_who_owns_each_value import _blocks, _without_comment_bodies

# design/tokens.css is synced into the extension; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parents[1]
LITERALS = json.loads((ROOT / "tests/fixtures/supabase-design-tokens.json").read_text(encoding="utf-8"))["literals"]
STEPS = [(family, step) for family in ("brand", "destructive", "warning") for step in (200, 300, 400, 500, 600)]
DECLARED = re.compile(r"^[ \t]*(--[a-z0-9-]+)[ \t]*:[ \t]*([^;]+);", re.M)


def _declared(block: str) -> dict[str, str]:
    return {name: " ".join(value.split()) for name, value in DECLARED.findall(_without_comment_bodies(block))}


@pytest.mark.parametrize("index", range(3), ids=["light", "dark", "device-dark"])
@pytest.mark.parametrize("family,step", STEPS)
def test_each_step_their_components_read_is_declared_at_its_fixture_value(index, family, step):
    theme, block = _blocks()[index]
    name = f"--{family}-{step}"
    assert _declared(block).get(name, "").lower() == LITERALS[theme][name]["hex"].lower(), (theme, name)


def test_the_info_base_is_their_oklch():
    """Their --info is an OKLCH expression with no literal at the pin; evaluated, it is these."""
    expected = {"light": "#6c5eba", "dark": "#9b8ff0"}
    for theme, block in _blocks():
        assert _declared(block).get("--info", "").lower() == expected[theme], theme


@pytest.mark.parametrize("index", range(3), ids=["light", "dark", "device-dark"])
def test_no_step_literal_is_written_twice_in_a_block(index):
    """A role token equal to a step names the step, so the hex is written once."""
    theme, block = _blocks()[index]
    declared = _declared(block)
    steps = {LITERALS[theme][f"--{f}-{s}"]["hex"].lower() for f, s in STEPS}
    written = {}
    for name, value in declared.items():
        if value.lower() in steps:
            written.setdefault(value.lower(), []).append(name)
    twice = {value: names for value, names in written.items() if len(names) > 1}
    assert not twice, f"{theme}: a step's literal written by more than one token: {twice}"
