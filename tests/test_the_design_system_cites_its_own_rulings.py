"""A ruling number in a comment is a lookup key, and the wrong one fails silently.

THE DEFECT THIS EXISTS TO CATCH WAS SHIPPED, AND IT WAS INVISIBLE TO EVERY OTHER
GUARD IN THIS SUITE.

`design/tokens.css` and `design/appearance.js` carried fifty-three comments citing
`R-84` for the design system -- "R-84: ONE COLOUR CHOICE", "R-84 deleted device
colours", "THERE IS NO DEVICE COLOUR PATH, AND THAT IS R-84 RATHER THAN AN
OMISSION". The ruling that says those things is `R-85`. `R-84` is
"The base changes now -- and at publication no migration is ever deleted again",
and `scrapex/dbupgrade.py` cites the same number, correctly, for that.

It happened because the ruling was renumbered mid-branch after the comments were
written, and nothing anywhere compared a cited number against what it names.

WHY IT MATTERS MORE NOW THAN IT DID WHEN IT WAS WRITTEN. `CLAUDE.md` makes
`git log --grep=R-84`, then `docs/archive/`, the supported way to learn why a line
exists, and names the code's citations as the only reason that archive is kept at
all. So a wrong number is not stale prose in a frozen file -- it is a broken lookup
in the mechanism that replaced the registers. And it fails the worst way a lookup
can: the reader lands on a real ruling, in a different domain, with nothing to
suggest they are in the wrong place.

WHY A TABLE RATHER THAN A HEURISTIC. "Is this ruling about the design system?"
cannot be decided from the text. What can be decided is whether the number still
names the ruling it was cited for, so `DESIGN_RULINGS` below pins the number to its
heading. The archive is frozen and no new number is ever issued from it, which
makes that mapping permanent: a row here can only be wrong if the citation is.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# Guards the extension (it reads design/ sources that are copied into extension/)
# and reads a document. Both gates check for their mark; see
# tests/test_the_extension_gate_is_complete.py and tests/test_the_docs_gate_is_complete.py.
pytestmark = [pytest.mark.extension, pytest.mark.docs]

ROOT = Path(__file__).resolve().parent.parent
RULINGS = ROOT / "docs" / "archive" / "RULINGS.md"

# Every file whose R- citations are about the design system, and only about it.
# The three copies of each design asset are listed because the sync tool copies
# comments too -- a wrong number is wrong in three places at once.
DESIGN_SURFACE = (
    "design/tokens.css",
    "design/appearance.js",
    "extension/tokens.css",
    "extension/appearance.js",
    "scrapex/webui/static/tokens.css",
    "scrapex/webui/static/appearance.js",
)

# The ruling each number must still name. Taken from the archive's own headings,
# which are frozen. A renumber moves the heading out from under the number, and
# that is exactly the failure this table converts into a red test.
DESIGN_RULINGS = {
    "R-59": "The palette registry: `brand` is default, `alternatives` is extensible, teal is debt",
    "R-73": "An appearance is a whole design system, and `supabase` is the default one",
    "R-74": "The design system is Supabase's, always, and a palette may change nothing but colour",
    "R-79": "Device colours reach the user, and the ink is derived rather than trusted",
    "R-85": "The system is Supabase's exactly, and `supabase` is the only colour choice",
}

CITATION = re.compile(r"\bR-(\d+)\b")


def _headings() -> dict[str, str]:
    """Every ruling in the frozen archive, number to heading text."""
    found: dict[str, str] = {}
    for match in re.finditer(
        r"^### (R-\d+) · (.+?)\s*$", RULINGS.read_text(encoding="utf-8"), re.M
    ):
        # A superseded ruling keeps its heading and its number; first wins, which
        # is the original statement rather than a later reference to it.
        found.setdefault(match.group(1), match.group(2))
    return found


@pytest.fixture(scope="module")
def headings() -> dict[str, str]:
    return _headings()


@pytest.mark.parametrize("relative", DESIGN_SURFACE)
def test_the_design_surface_cites_only_design_rulings(relative, headings):
    """A number cited here must be one this table knows, and it must still fit.

    The failure it catches is a citation that resolves -- to something else. That
    is why the assertion prints the heading the number actually carries: a reader
    who sees "no migration is ever deleted again" under a colour comment does not
    need the rest of the explanation.
    """
    path = ROOT / relative
    source = path.read_text(encoding="utf-8")

    for number in sorted({f"R-{n}" for n in CITATION.findall(source)}):
        assert number in DESIGN_RULINGS, (
            f"{relative} cites {number}, which is not a design-system ruling. "
            f"The archive says {number} is "
            f"{headings.get(number, '(not in the archive at all)')!r}. "
            f"Either the citation is wrong, or a design ruling was added and "
            f"belongs in DESIGN_RULINGS."
        )


def test_every_pinned_ruling_still_carries_the_heading_it_was_pinned_for(headings):
    """The table is only worth having if it is checked against the archive.

    Without this, a row could drift into agreeing with nothing, and the test above
    would keep passing while pointing readers at the wrong ruling -- the defect it
    was written to stop, moved one level up.
    """
    for number, expected in DESIGN_RULINGS.items():
        assert number in headings, f"{number} is not in {RULINGS.name}"
        assert headings[number] == expected, (
            f"{number} is pinned as {expected!r} but the archive now heads it "
            f"{headings[number]!r}"
        )


def test_no_pinned_ruling_has_stopped_being_cited():
    """A row nothing cites is a row nobody maintains.

    It is kept as a floor rather than an equality: a ruling may legitimately be
    cited by only one of the three copies of an asset.
    """
    cited: set[str] = set()
    for relative in DESIGN_SURFACE:
        source = (ROOT / relative).read_text(encoding="utf-8")
        cited.update(f"R-{n}" for n in CITATION.findall(source))

    unused = sorted(set(DESIGN_RULINGS) - cited)
    assert not unused, (
        f"{unused} are pinned as design rulings and cited by no design file. "
        f"Delete the rows, or find out what dropped the citation."
    )
