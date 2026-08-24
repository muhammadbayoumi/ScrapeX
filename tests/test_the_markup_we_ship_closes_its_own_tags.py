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

# Guards the extension: this file reads `extension/app.html` and
# `extension/onboarding.html`, so an extension-only change must run it. Without the
# mark this file would stop running on exactly the change most likely to unbalance
# a tag — which `tests/test_the_extension_gate_is_complete.py` caught the moment it
# was written, in the full suite it was written to be part of.
pytestmark = pytest.mark.extension

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Hand-authored markup we ship or serve. Jinja templates are excluded on purpose: a
#: `{% block %}` legitimately opens a tag one file closes elsewhere, so a stack walk
#: over one of them measures nothing. The pages here are whole documents.
PAGES = (
    "design/gallery.html",
    "extension/app.html",
    "extension/onboarding.html",
    "docs/picker/scrapex-picker.html",
)

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
    """Every closer that does not match the innermost open element, with its line."""
    body = _blanked(text)
    stack: list[tuple[str, int]] = []
    problems: list[str] = []
    for found in _TAG.finditer(body):
        closing, name, attributes, self_closing = found.groups()
        name = name.lower()
        if name in ("!doctype", "doctype"):
            continue
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
        elif name not in VOID and not self_closing and not attributes.rstrip().endswith("/"):
            stack.append((name, line))
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

    The input is the damage as it really shipped — an orphan `</div>` and an orphan
    `</section>` after a section had already closed."""
    broken = ('<section class="g-section">\n  <div class="g-item">\n'
              "  </div>\n</section>\n    </div>\n</section>\n")
    problems = _mismatches(broken)
    assert len(problems) == 2, f"the walk missed one of the two orphans: {problems}"
    assert "line 5" in problems[0] and "nothing open" in problems[0]

    assert not _mismatches('<section><div><p>x</p></div></section>')
    assert not _mismatches('<div><br><img src="x"><input type="text"></div>'), (
        "a void element was pushed onto the stack")
    assert not _mismatches('<div><svg><path d="M0 0"/></svg></div>'), (
        "a self-closing tag was pushed onto the stack")
    assert not _mismatches('<div><!-- </div> --></div>'), (
        "a tag inside a comment was counted")
    assert not _mismatches('<div><script>if (a < b) {}</script></div>'), (
        "script contents were parsed as markup")
