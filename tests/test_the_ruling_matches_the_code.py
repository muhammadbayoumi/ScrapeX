"""docs/data-page-schema.md calls itself the ruling. It has to be true.

It had drifted into stating the opposite of the code, in five ways at once:

  * classification levels L1 to L4, while CATEGORY_LEVELS is 10
  * Brand filed under identity, where reports.py files it under the filing
  * the reading order given as identity, classification, the offer — the exact
    order the owner's agreement replaced
  * display_method, minimum_quantity, quantity_increment and stock_quantity
    absent, though all four are columns
  * eight price columns absent

A document nobody can trust is worse than no document, and PR #63 was sent
back partly for leaving this one behind. The tables are generated now; these
tests are what stop them going stale again.
"""

from __future__ import annotations

import argparse
import pathlib
import re

import pytest

from scrapex import reports
from scrapex.cli import _render_data_page_schema, build_parser
from scrapex.vocab import BLOCK_ORDER

# THIS FILE IS WHY THE DOCS TIER EXISTS. It reads docs/data-page-schema.md and
# asserts it equals what the generator produces -- and it carried no mark at all,
# while `docs/` was already inside the extension-only path filter. So a
# documentation-only change ran `pytest -m extension`, this file was not in that
# set, and a hand-edited copy of the ruling would have passed CI on exactly the
# kind of pull request that hand-edits it. No extension mark: it touches no
# extension file, which is also why the extension tier now runs
# `-m "extension or docs"` rather than `-m extension`.
pytestmark = pytest.mark.docs

RULING = pathlib.Path(__file__).resolve().parent.parent / "docs" / "data-page-schema.md"


def test_the_committed_file_is_what_the_generator_produces():
    """The golden test. Regenerate with:

        python -m scrapex.cli export-version

    A file that can be hand-edited is a file that will be, and the edit will be
    the one nobody notices — this document went five facts out of date without
    a single test failing."""
    assert RULING.read_text(encoding="utf-8") == _render_data_page_schema() + "\n", (
        "docs/data-page-schema.md no longer matches the code it claims to "
        "describe. Run `python -m scrapex.cli export-version` and commit it.")


def test_every_column_in_the_table_appears_in_the_ruling():
    """A column the ruling does not mention is a column whose placement was
    never ruled on — which is exactly how display_method came to be captured
    for 868 products and shown nowhere."""
    text = RULING.read_text(encoding="utf-8")

    missing = [label or key for key, label in reports.browse_columns()
               if (label or key) not in text]

    assert not missing, f"the ruling does not mention: {missing}"


def test_the_ruling_states_the_agreed_reading_order():
    """Identity, then the offer, then the filing. The old file put the
    classification second and the price third, which is the arrangement the
    owner replaced — and it kept saying so for weeks after the code changed."""
    text = RULING.read_text(encoding="utf-8")
    positions = [text.index(f"**{block.value.capitalize()}**"
                            if block.value != "offer" else "**The offer**")
                 for block in BLOCK_ORDER
                 if (f"**{block.value.capitalize()}**" in text
                     or (block.value == "offer" and "**The offer**" in text))]

    assert positions == sorted(positions), (
        "the ruling's blocks are out of the agreed reading order")
    assert text.index("**The offer**") < text.index("**The filing**"), (
        "the ruling still files the classification in front of the price")


def test_the_category_ceiling_in_the_ruling_is_the_real_one():
    """It said L1–L4 while the code generated ten. Anyone reading it to find
    out how deep a source could be filed got a wrong answer, and a wrong answer
    from the document that calls itself the ruling is worse than silence."""
    text = RULING.read_text(encoding="utf-8")

    assert f"CATEGORY_LEVELS = {reports.CATEGORY_LEVELS}" in text
    assert f"Category L{reports.CATEGORY_LEVELS}" in text, (
        "the deepest level the code generates is not in the ruling")


def test_the_owners_prose_survives_generation():
    """The rules are HIS and no code derives them. A generator that dropped
    them would leave a file of tables nobody argues with — and the arguable
    part is the point."""
    text = RULING.read_text(encoding="utf-8")

    for ruling in ("A column's name states the language of its content",
                   "One language at a time",
                   "A missing translation shows the fact, never a blank",
                   "Presence is per source",
                   "An order you arranged is yours",
                   "Nothing is computed into a price"):
        assert ruling in text, f"the generator dropped a ruling: {ruling!r}"


def test_the_file_says_it_is_generated_and_how_to_regenerate_it():
    """Otherwise the next person edits it by hand, the golden test fails on
    their unrelated PR, and they learn the rule from a red build instead of
    from the file.

    AND THE COMMAND IT NAMES HAS TO EXIST. This read
    `assert "export-docs" in text or "export-version" in text`, and that `or`
    is the whole reason it stood green while the file told its reader to run
    `python -m scrapex.cli export-docs` -- which argparse answers with
    "invalid choice: 'export-docs'". A guard that accepts either of two names
    can never report the wrong one. Found 2026-08-20; the generator was
    emitting it at `scrapex/cli.py:302`."""
    text = RULING.read_text(encoding="utf-8")

    assert "GENERATED from `scrapex/reports.py`" in text

    named = re.findall(r"python -m scrapex\.cli ([a-z][a-z0-9-]*)", text)
    assert named, "the file no longer says which command regenerates it"

    real = _subcommands()
    for command in named:
        assert command in real, (
            f"docs/data-page-schema.md tells the reader to run `python -m "
            f"scrapex.cli {command}`, which is not a scrapex subcommand. "
            f"Real ones: {sorted(real)}")


def _subcommands() -> set[str]:
    """The real subcommand names, read out of the parser rather than from a
    list kept beside it -- a list would drift the way the sentence above did."""
    parser = build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    raise AssertionError("scrapex.cli.build_parser() has no subparsers")
