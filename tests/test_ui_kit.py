"""A class in markup has to resolve to a rule, or it is a lie about the page.

I shipped `class="btn"` and `class="btn icon-btn"` on 2026-08-05. Neither name
exists in any stylesheet in this repository; the codebase already had `ghost`,
`icon-button` and `compact`. Both buttons rendered unstyled, every gate was
green, and the mistake was found by looking at the page.

Nothing structural stopped it, because `class` is being asked to do three
different jobs at once — carry styling, mark JS hooks, and mark test selectors
— and only the first has anything checking it.

THE RULE THIS FILE ENFORCES:

    `class` is for styling. Every class in markup must resolve to a rule in
    some stylesheet the page loads.

    JavaScript hooks and test selectors use `data-*` or `id`. They are not
    styling and must not borrow the attribute that is.

MEASURED ON THE DAY THE RULE WAS WRITTEN: 994 class names defined across 18
stylesheets, 647 statically resolvable uses in markup, and 17 that resolved to
nothing. Sixteen were dead attributes carrying meaning no rule gave them —
`dataset-group` beside a JS hook that actually reads `[data-dataset-group]`,
`class="primary"` on a button whose base rule is already primary, `my-1` from a
utility framework this project does not use. One, `tabs`, was a real selector
hook, and it moved to the class that already described the element.

WHAT THIS DOES NOT CHECK. A class added by JavaScript never appears in markup,
so it cannot be checked here; `is-rail-active` and `is-open` are invisible to
this test. That is a real gap and naming it is better than implying coverage
this does not have.
"""

from __future__ import annotations

import collections
import pathlib
import re

import pytest

# Guards the extension: this file reads extension/ sources, so a change to a
# button must run it. See tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Stylesheets whose rules are available to the markup checked below. The two
#: canonical sheets in `design/` are the shared vocabulary; the rest are the
#: per-surface sheets. Distributed copies under `extension/` and
#: `scrapex/webui/static/` are byte-equal to the canon (tests/test_vendor.py),
#: so reading the canon is reading both.
CANONICAL = ("design/components.css", "design/tokens.css")
SURFACE_SHEETS = ("extension/app.css", "extension/onboarding.css",
                  "extension/console.css")

#: Class attributes a template computes cannot be resolved by reading the file.
JINJA = re.compile(r"\{\%.*?\%\}|\{\{.*?\}\}", re.S)
COMPUTED = ""

#: Names that are legitimately in markup without a styling rule. Every entry
#: needs a reason, and "it is used somewhere" is not one — a JS or test hook
#: belongs on `data-*` or `id`. This list is empty on purpose: it was emptied
#: when the rule was written, and an addition to it is a decision, not a fix.
ALLOWED_WITHOUT_A_RULE: dict[str, str] = {}


def _classes_defined_in(css: str) -> set[str]:
    """Class names a stylesheet defines rules for.

    Comments and `url("…")` values are stripped first. Without that,
    `url("x-mark.svg")` reads as a rule for a class named `svg` — which does
    not break the "used but undefined" direction (it only adds a name nobody
    writes) but does break the catalogue's own check, where a stray name looks
    like a component defined on the wrong page.
    """
    body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    body = re.sub(r"url\([^)]*\)", "", body)
    return set(re.findall(r"\.([a-zA-Z][\w-]*)", body))


def _webui_sheets() -> list[pathlib.Path]:
    static = ROOT / "scrapex" / "webui" / "static"
    return [p for p in sorted(static.rglob("*.css"))
            if p.name not in ("components.css", "tokens.css")]


@pytest.fixture(scope="module")
def defined() -> set[str]:
    sheets = [ROOT / p for p in CANONICAL + SURFACE_SHEETS] + _webui_sheets()
    present = [p for p in sheets if p.exists()]
    assert len(present) == len(sheets), (
        f"a stylesheet named here is missing: "
        f"{[str(p) for p in sheets if not p.exists()]}")
    names: set[str] = set()
    for path in present:
        names |= _classes_defined_in(path.read_text(encoding="utf-8"))
    return names


def _markup() -> list[pathlib.Path]:
    """EVERY page the extension ships, not just the panel.

    This globbed nothing but app.html until 2026-08-12, so onboarding.html's
    classes were never resolved and neither would any new page's have been —
    a gate that grows blind spots as the product grows is worse than one that
    fails, because its green keeps meaning what it used to mean.

    tests/ is excluded: the diagnostic twin exists to be minimal, and holding
    it to the shared vocabulary would be holding it to the opposite of its
    purpose.
    """
    pages = sorted(page for page in (ROOT / "extension").glob("*.html"))
    return pages + sorted((ROOT / "scrapex" / "webui" / "templates").rglob("*.html"))


def _used() -> dict[str, set[str]]:
    """Every statically resolvable class in markup, and the files it is in.

    A class attribute the template computes is replaced by a sentinel and any
    token touching it is skipped — `schedule-state-{{ state }}` is not the
    class `schedule-state-`. Its static neighbours in the same attribute are
    still checked, which is where the value is.
    """
    where: dict[str, set[str]] = collections.defaultdict(set)
    for path in _markup():
        text = JINJA.sub(COMPUTED, path.read_text(encoding="utf-8"))
        for attribute in re.findall(r'class="([^"]*)"', text):
            for name in attribute.split():
                if COMPUTED in name or not re.fullmatch(r"[a-zA-Z][\w-]*", name):
                    continue
                where[name].add(str(path.relative_to(ROOT)).replace("\\", "/"))
    return dict(where)


def test_every_class_in_markup_resolves_to_a_rule(defined):
    """THE GUARD. An unresolvable class renders as nothing and reads as a
    feature, and no other test in this repository can tell the difference."""
    unresolved = {name: files for name, files in _used().items()
                  if name not in defined and name not in ALLOWED_WITHOUT_A_RULE}

    assert not unresolved, "classes in markup that no stylesheet defines:\n" + "\n".join(
        f"  {name:<28} {', '.join(sorted(files))}" for name, files in sorted(unresolved.items()))


def test_the_shared_vocabulary_is_reachable_from_both_surfaces(defined):
    """The point of a shared sheet is that one fix reaches both UIs. If the
    extension or the web UI stopped loading it, every component in it would
    quietly become a per-surface reimplementation again — which is the state
    this whole effort exists to leave."""
    panel = (ROOT / "extension" / "app.html").read_text(encoding="utf-8")
    assert "components.css" in panel, "the panel no longer loads the shared sheet"

    base = (ROOT / "scrapex" / "webui" / "templates" / "base.html").read_text(encoding="utf-8")
    assert "components.css" in base, "the web UI no longer loads the shared sheet"


def test_every_shared_component_is_in_the_catalogue(defined):
    """UI-1. Nobody reuses what nobody can see.

    `design/components.css` holds the vocabulary both surfaces share, and until
    2026-08-05 there was no page that showed it. A hand-written list in a
    document goes stale in a week; this fails the moment a component exists in
    the sheet and nowhere on the catalogue page.

    The rule is presence, not a section per class — a modifier like `hi` or
    `compact` appears on the base component it modifies, which is exactly where
    a reader needs to see it. The commonest reason a modifier "does not work"
    is that its rule is `.card.hi` and it was written on a `<div>`.
    """
    css = (ROOT / "design" / "components.css").read_text(encoding="utf-8")
    shared = _classes_defined_in(css)

    gallery = (ROOT / "design" / "gallery.html")
    assert gallery.exists(), "the catalogue is gone; UI-KIT.md §6 says why it exists"
    shown: set[str] = set()
    for attribute in re.findall(r'class="([^"]*)"', gallery.read_text(encoding="utf-8")):
        shown |= set(attribute.split())

    missing = sorted(shared - shown)
    assert not missing, (
        "shared components with no live example in design/gallery.html:\n  "
        + "\n  ".join(missing))


def test_the_catalogue_uses_only_the_canonical_sheets(defined):
    """The catalogue has to be the real thing or it teaches a fiction.

    It loads `tokens.css` and `components.css` from beside it — the canonical
    files, not the distributed copies — so a change to the canon shows up here
    the moment it is made, with no sync step in between.
    """
    gallery = (ROOT / "design" / "gallery.html").read_text(encoding="utf-8")
    for sheet in ('href="tokens.css"', 'href="components.css"'):
        assert sheet in gallery, f"the catalogue no longer loads {sheet}"

    # Its own chrome is allowed one <style> block, and every rule in it is
    # prefixed `g-`. A component styled here rather than in components.css
    # would look right on this page and be missing everywhere else.
    chrome = re.search(r"<style>(.*?)</style>", gallery, re.S)
    assert chrome, "the catalogue lost its own chrome styles"
    own = {name for name in _classes_defined_in(chrome.group(1))
           if not name.startswith("g-")}
    assert not own, (
        f"the catalogue styles {sorted(own)} itself; a component belongs in "
        f"design/components.css, or it exists only on this page")


def test_the_allow_list_cannot_grow_without_a_reason():
    """An allow-list with bare names becomes a place to hide mistakes. Every
    entry states why the class exists with no rule behind it; a name and an
    empty string is how this guard stops being a guard."""
    for name, reason in ALLOWED_WITHOUT_A_RULE.items():
        assert len(reason.split()) >= 5, (
            f"{name!r} is allowed without a rule but the reason is {reason!r}")
