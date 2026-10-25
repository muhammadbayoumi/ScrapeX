"""A control's hover fill is Supabase's `--accent`, read from `--chip` in every block (#1053).

Supabase fills a hovered ghost, outline or text button with `bg-accent`
(packages/ui/src/components/shadcn/ui/button.tsx@86c813ec:17, :19; Button.tsx@86c813ec:75),
and a focused menu item with `bg-overlay-hover`, which is `var(--accent)`
(dropdown-menu.tsx@86c813ec:51; packages/ui/build/css/source/compat.css@86c813ec:34).
Here `--chip` carries their `--accent`, so `--control-hover` names it rather than holding a
second value: `--surface-subtle` (their `--muted`) in light until #1053, and the literal
`#1e1f1e` in both dark blocks, the same colour written out where a change to `--chip`
would not reach it.
"""
from __future__ import annotations

import re

from tests.test_the_provenance_markers_say_who_owns_each_value import (
    _blocks,
    _without_comment_bodies,
)


def test_every_block_reads_the_hover_fill_from_the_accent():
    declared = {}
    for index, (theme, block) in enumerate(_blocks()):
        found = re.findall(r"^[ \t]*--control-hover[ \t]*:[ \t]*([^;]+);", _without_comment_bodies(block), re.M)
        declared[f"{theme} #{index}"] = [" ".join(value.split()) for value in found]
    assert declared and all(declared.values()), f"a block no longer declares --control-hover: {declared}"
    wrong = {block: values for block, values in declared.items() if values != ["var(--chip)"]}
    assert not wrong, f"--control-hover is not Supabase's --accent (var(--chip)) in: {wrong}"


def test_the_chip_is_the_accent_it_stands_for():
    """The test above is only as true as `--chip` being their `--accent`: its note says so
    in both declared blocks, and the provenance tests verify the value behind the note."""
    notes = {theme: re.search(r"^[ \t]*--chip[ \t]*:[^;]+;[ \t]*/\*([^*]*)\*/", block, re.M)
             for theme, block in _blocks()[:2]}
    assert all(note and "--accent" in note.group(1) for note in notes.values()), notes
