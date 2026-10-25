"""A small uppercase label is Supabase's heading-meta, written once and composed (#713).

heading-meta is `text-xs font-mono uppercase tracking-wider font-medium`
(packages/config/typography.css@86c813ec:22-24), and it sets no colour: Studio composes it
with foreground-light in 19 of its 21 uses, here `.muted`. design/components.css holds it
once, and each label carries it in its markup, the way Studio does; the page's own class keeps
only its layout. A menu's group heading is the same utility at normal weight in
foreground-muted (CommandGroup, packages/ui/src/components/shadcn/ui/command.tsx@86c813ec:
122-126), here `--text-subtle`, which is their --tertiary-foreground like foreground-muted.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools.value_literals import authored, declarations

# Guards the extension's pages; see tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parents[1]
#: Classes whose element is a meta label: a kicker above a title, a label above a value.
LABELS = ("page-eyebrow", "appearance-eyebrow", "appearance-popover-eyebrow", "data-grid-eyebrow",
          "eyebrow", "schedules-eyebrow", "settings-eyebrow")
#: A menu's group heading: heading-meta at normal weight in --text-subtle.
GROUP = "grid-feature-section"
#: Classes that held only the label's type and colour, and are gone with it.
RETIRED = ("data-landing-eyebrow", "appearance-page-eyebrow", "finance-page-eyebrow", "workspace-menu-eyebrow")
TYPE = {"font-family", "font-size", "font-weight", "letter-spacing", "text-transform", "color", "font"}
MARKUP = [*sorted((ROOT / "extension").glob("*.html")), *sorted((ROOT / "scrapex/webui/templates").glob("*.html")),
          ROOT / "scrapex/webui/static/pages/data-model.js", ROOT / "design/gallery.html"]


def _rules(selector_pattern):
    found = []
    for sheet in authored():
        for selector, prop, value, line in declarations(sheet.read_text(encoding="utf-8")):
            if re.search(selector_pattern, selector):
                found.append((f"{sheet.relative_to(ROOT).as_posix()}:{line}", " ".join(selector.split()), prop,
                              " ".join(value.split())))
    return found


def test_heading_meta_is_supabases_utility_and_only_it():
    declared = {prop: value for where, selector, prop, value in _rules(r"^\.heading-meta$")
                if where.startswith("design/components.css")}
    assert declared == {
        "font-family": "var(--font-mono)", "--fw-regular": "var(--fw-regular-mono)",
        "font-size": "var(--fs-xs)", "line-height": "var(--lh-xs)", "font-weight": "var(--fw-medium)",
        "letter-spacing": ".05em", "text-transform": "uppercase"}, declared


def test_every_meta_label_carries_heading_meta():
    classes = re.compile(r"""class=["']([^"']*)["']""")
    missing, retired, labels = [], [], 0
    for path in MARKUP:
        text = path.read_text(encoding="utf-8")
        for match in classes.finditer(text):
            names = match.group(1).split()
            where = f"{path.relative_to(ROOT).as_posix()}:{text.count(chr(10), 0, match.start()) + 1}"
            if any(name in names for name in (*LABELS, GROUP)):
                labels += 1
                if "heading-meta" not in names:
                    missing.append(where)
            retired += [f"{where} {name}" for name in RETIRED if name in names]
        # The data-source overview's panel heads label their counts with a bare <small>.
        if path.name == "_source_overview.html":
            for match in re.finditer(r"data-source-overview-panel-head[^>]*>\s*(?:<[^>]+>\s*)*?<small([^>]*)>", text, re.S):
                labels += 1
                if "heading-meta" not in match.group(1):
                    missing.append(f"{path.name} panel-head small")
    assert labels >= 50, labels
    assert not missing, f"meta labels without heading-meta: {missing}"
    assert not retired, f"classes that held only the label's type, still in markup: {retired}"


def test_no_label_rule_restates_heading_meta():
    """The label's type and colour live in heading-meta and `.muted`; its own rule keeps layout."""
    pattern = r"\.(" + "|".join(re.escape(name) for name in LABELS) + r")(?![\w-])|data-source-overview-panel-head small"
    wrong = [f"{where} {selector} {{{prop}: {value}}}" for where, selector, prop, value in _rules(pattern)
             if prop in TYPE]
    assert not wrong, "label rules that set type or colour heading-meta owns:\n  " + "\n  ".join(wrong)
    group = {(prop, value) for _w, selector, prop, value in _rules(rf"^\.{GROUP}$") if prop in TYPE}
    assert group == {("font-weight", "var(--fw-regular)"), ("color", "var(--text-subtle)")}, group
    assert not _rules(r"\.(" + "|".join(RETIRED) + r")(?![\w-])"), "a retired label class still has a rule"
