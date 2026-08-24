"""An orphan closing tag is invisible: browsers drop it and every gate stays green.

WHY THIS FILE EXISTS. Removing the `.coverage-open` example from `design/gallery.html`
deleted the block's OPENING tags and left its tail behind — two orphan `</div>`, an
orphan `</section>`, and a bare `<pre>` teaching a class that had just been moved out of
the shared sheet. The commit that did it says *"the example is gone"*. It was not, and
the catalogue closed its "Choosing sources" section four lines early.

NOTHING IN THE SUITE COULD SEE IT, and that is the point worth a file of its own:

  * `tests/test_ui_kit.py` scans `class="…"` attributes for names the shared sheet
    defines. `.coverage-open` had just LEFT that sheet, so there was no obligation and
    nothing to fail.
  * `tools/sync_design_assets.py --check` exits 0 — the catalogue is not a generated
    artefact, only its embedded sprite and mask are.
  * Browsers discard a closer with no opener silently. There is no console error, no
    layout collapse loud enough to notice, and no red anywhere.

So the one page whose entire job is to show components correctly can be broken by an
edit to itself, and the only thing that catches it is a person looking. An adversarial
review was that person. This is the guard that means it does not have to be next time.

WHAT THIS CHECKS AND WHAT IT DOES NOT. A stack walk over the element tags, ignoring
void elements and the contents of `<script>`, `<style>` and comments. It answers one
question — does every closer match the innermost open element — which is exactly the
class of damage a careless delete does. It is not an HTML validator and does not try to
be: attribute syntax, nesting rules and accessibility are somebody else's job.
"""
from __future__ import annotations

import pathlib
import re

import pytest

# TWO MARKS, BECAUSE `PAGES` STRADDLES TWO CI TIERS. The extension mark came first
# and was not enough: `docs/picker/scrapex-picker.html` matches ci.yml's
# `documentation` scope pattern, so a change to that page alone selects `-m docs` and
# this guard — written for exactly that kind of page — never ran. Measured:
# `pytest -m docs --collect-only` did not list this file at all.
#
# `tests/test_the_docs_gate_is_complete.py` could not catch it either: its detector
# looks for `*.md` or `ROOT / "docs"`, and this file names its pages as bare strings
# and joins them with `ROOT / page`. So a gate's own pattern missed its subject —
# `LESSONS` §7, for the third time in this repository.
pytestmark = [pytest.mark.extension, pytest.mark.docs]

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Hand-authored markup we ship or serve. Jinja templates are excluded on purpose: a
#: `{% block %}` legitimately opens a tag one file closes elsewhere, so a stack walk
#: over one of them measures nothing. The pages here are whole documents.
#: `console.html` AND `data.html` WERE MISSING from the first version, and the panel
#: opens both at runtime — `chrome.runtime.getURL("console.html")` and the dataset
#: table. Both are clean today, so that was a coverage hole rather than a live defect;
#: they are named because they are the same KIND of page as the two that were listed,
#: and a list of surfaces somebody has to remember to extend fails on the one nobody
#: added.
PAGES = (
    "design/gallery.html",
    "extension/app.html",
    "extension/onboarding.html",
    "extension/console.html",
    "extension/data.html",
    "docs/picker/scrapex-picker.html",
)

#: Elements whose children are FOREIGN content, where `<x/>` really does self-close.
#: In HTML proper the slash is ignored, which is the whole of the two defects the
#: walk below now handles.
FOREIGN = frozenset({"svg", "math"})

#: Elements that never close. `<p>` and `<li>` are NOT here — they are optional-close in
#: the standard, and this repository writes them closed; a file that stops doing so
#: should fail here rather than teach the guard to shrug.
VOID = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "param", "source", "track", "wbr",
})

#: Comments, and anything inside a script or style block, are not markup. Blanked
#: rather than deleted so the reported line numbers stay the file's own — a guard that
#: names the wrong line sends its reader hunting.
_OPAQUE = re.compile(
    r"<!--.*?-->|<script\b.*?</script\s*>|<style\b.*?</style\s*>|<!\[CDATA\[.*?\]\]>",
    re.S | re.I)
_TAG = re.compile(r"<(/?)([a-zA-Z][\w:-]*)([^>]*?)(/?)>", re.S)


def _blanked(text: str) -> str:
    return _OPAQUE.sub(lambda found: re.sub(r"[^\n]", " ", found.group(0)), text)


def _mismatches(text: str) -> list[str]:
    """Every closer that does not match the innermost open element, with its line.

    A TRAILING SLASH SELF-CLOSES ONLY INSIDE FOREIGN CONTENT, and that one rule is
    what makes this walk agree with a browser on two cases the first version got
    wrong — both found by an adversarial review, neither present in this repository
    today.

      * `<div class="card"/>` OPENS a div. HTML ignores the slash on its own
        elements, so a following `<p>` nests INSIDE the card. That is precisely the
        "renders as something nobody wrote" damage this file exists to catch, and the
        first version reported no problem at all.
      * `<a href=/docs/>` is an unquoted attribute value ending in a slash, not a
        self-closing tag. The first version read the slash as a self-close and then
        reported the matching `</a>` as an orphan — a false alarm on valid markup.

    The `<!DOCTYPE html>` special case the first version carried is gone with them:
    `_TAG` requires a letter after `<`, so a doctype never matched it in the first
    place and the branch could only ever have fired on `<doctype …>`, which is not
    HTML. A dead branch in a guard reads as a handled case.
    """
    body = _blanked(text)
    stack: list[tuple[str, int]] = []
    problems: list[str] = []
    foreign = 0
    for found in _TAG.finditer(body):
        closing, name, _attributes, slash = found.groups()
        name = name.lower()
        line = body.count("\n", 0, found.start()) + 1
        if closing:
            if not stack:
                problems.append(f"line {line}: </{name}> with nothing open at all")
            elif stack[-1][0] != name:
                open_name, open_line = stack[-1]
                problems.append(
                    f"line {line}: </{name}> but the innermost open element is "
                    f"<{open_name}> from line {open_line}")
            else:
                stack.pop()
                if name in FOREIGN:
                    foreign = max(0, foreign - 1)
        elif name in VOID or (slash and foreign):
            continue
        else:
            stack.append((name, line))
            if name in FOREIGN:
                foreign += 1
    problems += [f"<{name}> opened at line {line} and never closed"
                 for name, line in reversed(stack)]
    return problems


@pytest.mark.parametrize("page", PAGES)
def test_every_page_we_ship_closes_what_it_opens(page):
    """THE GUARD. An unbalanced tag renders as something nobody wrote and reads as a
    styling problem — which is how the gallery's broken section survived a commit whose
    own message described it as removed."""
    path = ROOT / page
    if not path.is_file():
        pytest.skip(f"{page} is not in this checkout")
    problems = _mismatches(path.read_text(encoding="utf-8"))
    assert not problems, (
        f"{page} does not close its own tags. A browser discards the extras in "
        f"silence, so this is the only thing that will tell you:\n  "
        + "\n  ".join(problems))


def test_the_walk_actually_notices_an_orphan_closer():
    """A GUARD ON THE GUARD, because a stack walk with a bug in it passes everything.

    THE INPUT IS THE DAMAGE AS IT REALLY SHIPPED, and the count is now the real one.
    An adversarial review measured `b443518:design/gallery.html` at **three** problems
    — `</div>` on 841, `</div>` on 843, `</section>` on 844 — while this fixture had
    two. A fixture that is one orphan short of the thing it names is a fixture that
    could pass while the walk under-reports.
    """
    broken = ('<section class="g-section">\n  <div class="g-item">\n'
              "  </div>\n</section>\n    </div>\n    <pre>x</pre>\n"
              "  </div>\n</section>\n")
    problems = _mismatches(broken)
    assert len(problems) == 3, f"expected the shipped damage's three orphans: {problems}"
    assert all("nothing open" in problem for problem in problems), problems
    assert ["line 5", "line 7", "line 8"] == [problem.split(":")[0] for problem in problems]

    assert not _mismatches('<section><div><p>x</p></div></section>')
    assert not _mismatches('<div><br><img src="x"><input type="text"></div>'), (
        "a void element was pushed onto the stack")
    assert not _mismatches('<div><svg><path d="M0 0"/></svg></div>'), (
        "a self-closed tag inside foreign content was pushed onto the stack")
    assert not _mismatches('<div><!-- </div> --></div>'), (
        "a tag inside a comment was counted")
    assert not _mismatches('<div><script>if (a < b) {}</script></div>'), (
        "script contents were parsed as markup")


def test_a_slash_on_an_html_element_does_not_close_it():
    """FINDING L1. HTML ignores the slash outside foreign content, so this opens a
    div and the paragraph nests inside the card. Every browser agrees; the first
    version of this walk did not, and returned no problems at all."""
    problems = _mismatches('<section><div class="card"/><p>text</p></section>')
    assert problems, (
        "a self-closed <div> was treated as closed, which is the rendering nobody "
        "wrote and the reason this file exists")


def test_an_unquoted_attribute_ending_in_a_slash_is_not_a_self_close():
    """FINDING L2, the same rule from the other side. The first version read the
    trailing slash of an unquoted href as a self-close and then called the real
    closer an orphan — a false alarm on valid markup, which is how a guard earns
    being switched off."""
    assert not _mismatches("<div><a href=/docs/>x</a></div>")


def test_a_doctype_is_not_an_element():
    """The dead branch that used to name it is gone; this asserts the reason it was
    dead, so nobody adds it back."""
    assert not _TAG.findall("<!DOCTYPE html>")
    assert not _mismatches("<!DOCTYPE html>\n<html><body></body></html>")
