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
#: A class whose element is a meta label, by its name: a kicker above a title, a label above a
#: value. Derived, so a new or renamed one is held without being listed.
LABEL_CLASS = re.compile(r"(?:[\w-]+-)?(?:eyebrow|kicker)")
#: A label with no class of its own, by its file and its words.
BARE = {"extension/app.html": ("Personalize", "Exchange rates", "Full Workspace"),
        "scrapex/webui/templates/data.html": ("Data workspace",),
        "scrapex/webui/templates/_source_overview.html": ("Health", "Inventory")}
#: A menu's group heading: heading-meta at normal weight in --text-subtle.
GROUP = "grid-feature-section"
#: Classes that held only the label's type and colour, and are gone with it.
RETIRED = ("data-landing-eyebrow", "appearance-page-eyebrow", "finance-page-eyebrow", "workspace-menu-eyebrow")
TYPE = {"font-family", "font-size", "font-weight", "line-height", "letter-spacing", "text-transform", "color", "font"}
MARKUP = [*sorted((ROOT / "extension").glob("*.html")), *sorted((ROOT / "scrapex/webui/templates").glob("*.html")),
          ROOT / "design/gallery.html"]
SCRIPTS = [*sorted((ROOT / "extension").glob("*.js")), *sorted((ROOT / "design").glob("*.js")),
           *sorted((ROOT / "scrapex/webui/static").glob("*.js")), *sorted((ROOT / "scrapex/webui/static/pages").glob("*.js"))]
#: A string in a script that could be a class list, for a builder that does not write `class=`.
CLASS_LIST = re.compile(r"""["'`]([\w-]+(?: [\w-]+)*)["'`]""")
#: How many elements carry heading-meta in each file. A label whose own class is renamed to
#: something else and which drops heading-meta with it leaves no other trace.
COUNTS = {"extension/app.html": 3,
          "extension/data.html": 3,
          "extension/enrichment.html": 10,
          "scrapex/webui/templates/_source_overview.html": 2,
          "scrapex/webui/templates/changes.html": 1,
          "scrapex/webui/templates/data.html": 1,
          "scrapex/webui/templates/data_model.html": 4,
          "scrapex/webui/templates/datasets.html": 1,
          "scrapex/webui/templates/excel.html": 5,
          "scrapex/webui/templates/google_finance_dataset.html": 2,
          "scrapex/webui/templates/history.html": 1,
          "scrapex/webui/templates/jobs.html": 1,
          "scrapex/webui/templates/logs.html": 1,
          "scrapex/webui/templates/manage.html": 1,
          "scrapex/webui/templates/overview.html": 5,
          "scrapex/webui/templates/review.html": 1,
          "scrapex/webui/templates/schedules.html": 1,
          "scrapex/webui/templates/settings.html": 2,
          "scrapex/webui/templates/source.html": 3,
          "scrapex/webui/templates/sync.html": 9,
          "design/gallery.html": 5,
          "scrapex/webui/static/pages/data-model.js": 1}


def _rules(selector_pattern):
    found = []
    for sheet in authored():
        for selector, prop, value, line in declarations(sheet.read_text(encoding="utf-8")):
            if re.search(selector_pattern, selector):
                found.append((f"{sheet.relative_to(ROOT).as_posix()}:{line}", " ".join(selector.split()), prop,
                              " ".join(value.split())))
    return found


def test_heading_meta_is_supabases_utility_and_only_it():
    """One rule, here. Another sheet's `.heading-meta`, or a page's `.x .heading-meta`, is a second say."""
    rules = _rules(r"\.heading-meta(?![\w-])")
    assert {(where.rsplit(":", 1)[0], selector) for where, selector, _prop, _value in rules} \
        == {("design/components.css", ".heading-meta")}, rules
    assert {prop: value for _where, _selector, prop, value in rules} == {
        "font-family": "var(--font-mono)", "--fw-regular": "var(--fw-regular-mono)",
        "font-size": "var(--fs-xs)", "line-height": "var(--lh-xs)", "font-weight": "var(--fw-medium)",
        "letter-spacing": ".05em", "text-transform": "uppercase"}, rules


def _wrong_classes(names, where):
    """A label carries `heading-meta muted`, and a group heading carries heading-meta alone."""
    if GROUP in names:
        return [] if "heading-meta" in names and "muted" not in names else [f"{where} {names}"]
    if any(LABEL_CLASS.fullmatch(name) and name not in RETIRED for name in names) or "heading-meta" in names:
        return [] if "heading-meta" in names and "muted" in names else [f"{where} {names}"]
    return []


def test_every_meta_label_carries_heading_meta_and_muted():
    classes = re.compile(r"""class=["']([^"']*)["']""")
    wrong, retired, counts = [], [], {}
    for path in [*MARKUP, ROOT / "scrapex/webui/static/pages/data-model.js"]:
        text = path.read_text(encoding="utf-8")
        name = path.relative_to(ROOT).as_posix()
        for match in classes.finditer(text):
            names = match.group(1).split()
            where = f"{name}:{text.count(chr(10), 0, match.start()) + 1}"
            counts[name] = counts.get(name, 0) + ("heading-meta" in names)
            wrong += _wrong_classes(names, where)
            retired += [f"{where} {label}" for label in RETIRED if label in names]
    assert not wrong, f"meta labels not carrying what they should: {wrong}"
    assert not retired, f"classes that held only the label's type, still in markup: {retired}"
    assert {name: count for name, count in counts.items() if count} == COUNTS


def test_a_script_that_builds_a_label_gives_it_heading_meta_and_muted():
    wrong = []
    for path in SCRIPTS:
        text = path.read_text(encoding="utf-8")
        for match in [*CLASS_LIST.finditer(text), *re.finditer(r"""class=["']([^"']*)["']""", text)]:
            wrong += _wrong_classes(match.group(1).split(), path.relative_to(ROOT).as_posix())
    assert not wrong, wrong


@pytest.mark.parametrize("path,label", [(path, label) for path, labels in BARE.items() for label in labels])
def test_a_label_with_no_class_of_its_own_stays_one(path, label):
    text = (ROOT / path).read_text(encoding="utf-8")
    assert re.search(rf"""class=["']heading-meta muted["']>\s*{re.escape(label)}\s*<""", text), (path, label)


def test_no_label_rule_restates_heading_meta():
    """The label's type and colour live in heading-meta and `.muted`; its own rule keeps layout."""
    rules = _rules(r"\.(?:[\w-]+-)?(?:eyebrow|kicker)(?![\w-])")
    assert len(rules) >= 10, f"only {len(rules)} declarations were read, so this measured little: {rules}"
    wrong = [f"{where} {selector} {{{prop}: {value}}}" for where, selector, prop, value in rules if prop in TYPE]
    assert not wrong, "label rules that set type or colour heading-meta owns:\n  " + "\n  ".join(wrong)
    group = {(prop, value) for _w, selector, prop, value in _rules(rf"^\.{GROUP}$") if prop in TYPE}
    assert group == {("font-weight", "var(--fw-regular)"), ("color", "var(--text-subtle)")}, group
    assert not _rules(r"\.(" + "|".join(RETIRED) + r")(?![\w-])"), "a retired label class still has a rule"
