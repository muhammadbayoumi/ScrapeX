"""A request of his, quoted inside a finding, must reach the request board.

WHY THIS IS A GUARD AND NOT A CONVENTION. `docs/REQUESTS.md` exists because
`REQ-04` sat ruled and unbuilt for sixteen days after dropping out of view, and it
states the boundary itself: *"The owner asked for it -> this file, `REQ-nn`"*.
`tests/test_the_request_board_matches_its_entries.py` already keeps that file
honest against its own entries. **Nothing checked that a request of his was on the
board at all**, and on 2026-08-20 three were not:

  * `DEC-9` was 40 lines of storage research he had asked for, with no `REQ`.
  * `DEC-8` answered a direct question of his and `REQ-07` -- that same question on
    the board -- did not cite it, in either direction.
  * `DEC-11` was 150 lines of crawl research quoting his instruction twice, with no
    `REQ`.

Three in one file is not an accident, and each was found by hand. This is the
mechanical version.

THE SIGNAL, and why it is this one. A quotation of his **in Arabic** inside a
`BACKLOG.md` entry is the signature of a request rather than a finding: findings
here are written in English, and the guillemets are reserved for his words. That
makes it cheap and exact. `OP-6`, `BV-5` and `SEP-5` quote him too and are
correctly in `BACKLOG.md` -- as review comments on things WE found -- which is why
the rule is not "no Arabic in BACKLOG" but "something on the board must cite it".

WHAT SATISFIES IT, either direction, because both are real links:
  * the entry cites a `REQ-nn`, or
  * `REQUESTS.md` names the entry.

A guillemet with no Arabic inside it does not count: `DEC-11` writes
*"as of «timestamp»"* as ordinary emphasis, and a guard that flagged that would be
teaching people to avoid a punctuation mark.
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.docs

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"

#: Any Arabic letter. Enough to tell his words from ours.
ARABIC = re.compile(r"[؀-ۿ]")
#: A guillemet quotation, which this repository reserves for what he said.
QUOTED = re.compile(r"«([^»]*)»", re.DOTALL)
#: The identifier at the head of a BACKLOG entry.
ENTRY = re.compile(r"### ((?:OP|DEC|DEBT|BV|SEP|Q)-\d+)")


def _entries() -> list[tuple[str, str]]:
    """(identifier, body) for every `### `-headed entry in BACKLOG.md."""
    text = (DOCS / "BACKLOG.md").read_text(encoding="utf-8")
    found = []
    for part in re.split(r"\n(?=### )", text):
        if match := ENTRY.match(part):
            found.append((match.group(1), part))
    return found


def _quotes_him(body: str) -> list[str]:
    """His quoted words in this entry -- Arabic inside guillemets, nothing else."""
    return [q.strip() for q in QUOTED.findall(body) if ARABIC.search(q)]


def test_the_signal_still_finds_something():
    """A vacuous guard is worse than none: it reports success for a corpus it can
    no longer read. If the guillemets or the language ever change, this fails and
    says so instead of passing silently for ever.

    Asserted on the mechanism -- at least one entry quotes him -- and not on a
    count, because the count is supposed to move."""
    quoting = [ident for ident, body in _entries() if _quotes_him(body)]
    assert quoting, (
        "no BACKLOG entry quotes the owner in Arabic inside guillemets any more, so "
        "this guard is checking nothing. Either the convention changed -- update "
        "ARABIC/QUOTED here -- or the entries moved, and this file is now a "
        "comment pretending to be a test")


def test_every_finding_that_quotes_him_is_reachable_from_the_request_board():
    """THE DEFECT THIS FILE WAS WRITTEN FOR, three times over in one afternoon.

    Research he asked for, correctly recorded and invisible on the board that
    tracks what he asked for. `REQUESTS.md` calls that out as the failure it exists
    to prevent, and had it three times."""
    requests = (DOCS / "REQUESTS.md").read_text(encoding="utf-8")

    orphaned = []
    for ident, body in _entries():
        quotes = _quotes_him(body)
        if not quotes:
            continue
        if re.search(r"REQ-\d+", body) or ident in requests:
            continue
        orphaned.append(
            f"{ident} quotes him and nothing on the board cites it:\n"
            f"      «{quotes[0][:90]}»")

    assert not orphaned, (
        "these findings carry a request of his that never reached "
        "docs/REQUESTS.md. Capture it as a REQ-nn in his own words, or cite the "
        "REQ it belongs to:\n  " + "\n  ".join(orphaned))


def test_a_guillemet_without_arabic_is_not_treated_as_his_words():
    """`DEC-11` writes *"complete as of «timestamp»"* as emphasis. A guard that
    counted that would push people away from a punctuation mark to stay green,
    which is how a guard starts shaping the prose instead of checking it."""
    assert not _quotes_him("complete as of «timestamp», never before")
    assert _quotes_him("he said «اريد كل ما ينشره الموقع» today")
