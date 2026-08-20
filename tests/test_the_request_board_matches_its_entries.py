"""docs/REQUESTS.md carries the same requests twice -- once as a scannable board,
once as the entries beneath it -- and nothing derived either from the other, so
they drifted. Found 2026-08-20: REQ-03 sat at "In flight" on the board while the
register it describes had already merged in #214, and REQ-04's cell claimed
"16 days" that had become nineteen.

THE BOARD CANNOT SIMPLY BE GENERATED, and that is why this is a test rather than
a `_render_` function beside `_render_data_page_schema`. The `request` column is
independently worded from the entry heading in five of nine rows -- "One
documentation system, in the repo, all English" against the heading "One
documentation system, in the repository" -- so a generator would have to invent
that summary or destroy it.

What IS derivable is checked here: which ids appear and in what order, each
anchor, each state, and each `since` date. The prose stays hand-written. That is
the same split docs/data-page-schema.md draws between its generated tables and
the owner's rulings, applied to a file whose generated part is four columns wide.

Not marked `extension`, because it reads nothing under that tree -- only
docs/REQUESTS.md. tests/test_the_extension_gate_is_complete.py owns that rule, and
note it matches on the literal path string: a sentence merely *mentioning* the
tree is enough to trip it, which is why this paragraph talks around the name. That
is the same prose-inference limit LESSONS.md records twice over.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
BOARD = ROOT / "docs" / "REQUESTS.md"

# The pipeline in docs/REQUESTS.md "## The pipeline". Ordered, and closed: a state
# outside this tuple is a typo or an invention, and either way the board and the
# entry can no longer be compared.
STATES = ("Captured", "Ruled", "Planned", "In flight", "Done", "Dropped")

# Below today's nine on purpose -- requests are added rather than removed, but a
# rewrite may renumber. It may not fall to nothing: a guard that can be emptied
# without anyone noticing is the defect this file exists to answer.
FLOOR = 6

# Elapsed time rots. A count of days is true on the day it is typed and silently
# false the next, which is exactly how "16 days" became nineteen.
ELAPSED = re.compile(r"\b\d+\s+(?:day|days|week|weeks|month|months)\b", re.I)

# The middle dot between an id and its title. It is deleted when GitHub slugs the
# heading, and both spaces around it survive -- which is why every anchor in the
# board carries TWO hyphens after `req-nn`.
DOT = "·"


def _text() -> str:
    assert BOARD.is_file(), "docs/REQUESTS.md is gone"
    return BOARD.read_text(encoding="utf-8")


def _slug(heading: str) -> str:
    """GitHub's rule: lowercase, drop what is neither word nor space nor hyphen,
    then replace EACH space with a hyphen. Runs are NOT collapsed."""
    kept = re.sub(r"[^\w\s-]", "", heading.strip().lower())
    return kept.replace(" ", "-")


def _cells(row: str) -> list[str]:
    r"""Split a markdown row on unescaped pipes only. docs/REQUESTS.md contains
    exactly one escaped pipe -- `AR\|EN` in REQ-06 -- and a plain split("|")
    gives that row five cells and every other row four."""
    return [cell.strip() for cell in re.split(r"(?<!\\)\|", row)[1:-1]]


def _board() -> list[dict]:
    text = _text()
    start = text.index("## The board")
    block = text[start:text.index("\n---", start)]

    rows = []
    for line in block.splitlines():
        if not line.startswith("| [REQ-"):
            continue
        cells = _cells(line)
        assert len(cells) == 4, f"board row has {len(cells)} cells, not 4:\n  {line}"
        link, request, state, since = cells
        match = re.fullmatch(r"\[(REQ-\d+)\]\(#([^)]+)\)", link)
        assert match, f"a board row's first cell is not an anchored id:\n  {link}"
        rows.append({"id": match.group(1), "anchor": match.group(2),
                     "request": request, "state": state, "since": since,
                     "line": line})
    return rows


def _entries() -> list[dict]:
    lines = _text().splitlines()
    entries = []
    for index, line in enumerate(lines):
        match = re.fullmatch(rf"## (REQ-\d+) {DOT} (.+)", line)
        if not match:
            continue
        state_line = next(x for x in lines[index + 1:] if x.strip())
        assert state_line.startswith("**"), (
            f"{match.group(1)}'s state line does not follow its heading:\n  "
            f"{state_line}")
        entries.append({"id": match.group(1), "heading": line[3:],
                        "state_line": state_line})
    return entries


def _reached(state_line: str) -> str | None:
    """The furthest state an entry claims, which is the LAST one it names. These
    lines are prose around the states, not a fixed set of fields: REQ-04 reads
    `Ruled (...) -- not built, measured 2026-08-20` and REQ-05 names four."""
    best: tuple[int, str] | None = None
    for state in STATES:
        for match in re.finditer(rf"\b{re.escape(state)}\b", state_line):
            if best is None or match.start() > best[0]:
                best = (match.start(), state)
    return best[1] if best else None


def test_the_board_lists_every_entry_and_nothing_else():
    board = [row["id"] for row in _board()]
    entries = [entry["id"] for entry in _entries()]

    assert board == entries, (
        "the board and the entries below it disagree about which requests exist, "
        f"or about their order.\n  board:   {board}\n  entries: {entries}")


def test_every_board_anchor_reaches_its_entry():
    """A row whose link is dead is worse than no row: it reads as a promise that
    the detail exists somewhere."""
    headings = {entry["id"]: entry["heading"] for entry in _entries()}

    wrong = [f"{row['id']} links to #{row['anchor']}, but its heading slugs to "
             f"#{_slug(headings[row['id']])}"
             for row in _board() if row["anchor"] != _slug(headings[row["id"]])]

    assert not wrong, ("these board anchors do not reach their entry:\n  "
                       + "\n  ".join(wrong))


def test_every_board_state_is_the_state_its_entry_reached():
    """THE DRIFT THIS FILE WAS WRITTEN FOR. REQ-03's board cell read
    `**In flight**` while its own entry had reached Done in #214."""
    lines = {entry["id"]: entry["state_line"] for entry in _entries()}

    wrong = []
    for row in _board():
        reached = _reached(lines[row["id"]])
        shown = re.match(r"\*\*([^*]+)\*\*", row["state"])
        assert shown, (f"{row['id']}'s board state is not a bold state token: "
                       f"{row['state']!r}")
        if shown.group(1) != reached:
            wrong.append(f"{row['id']}: board says {shown.group(1)!r}, entry "
                         f"reached {reached!r}\n      entry: {lines[row['id']][:110]}")

    assert not wrong, ("the board contradicts the entries it summarises:\n  "
                       + "\n  ".join(wrong))


def test_every_state_named_anywhere_is_one_the_pipeline_declares():
    """`DONE` in an entry and `**Done**` on the board are one state spelled two
    ways, and a comparison cannot know that. One spelling, and it is the table's."""
    unknown = [f"{entry['id']} reaches no declared state: {entry['state_line'][:110]}"
               for entry in _entries() if _reached(entry["state_line"]) is None]
    assert not unknown, "\n  ".join(unknown)

    text = _text()
    for state in STATES:
        assert f"| **{state}** |" in text, (
            f"{state!r} is in this guard's vocabulary but the pipeline table in "
            "docs/REQUESTS.md no longer declares it -- one of the two is wrong")

    shouted = re.findall(r"\b(?:DONE|CAPTURED|RULED|PLANNED|DROPPED)\b", text)
    assert not shouted, (
        f"{len(shouted)} state name(s) are shouted rather than spelled the way "
        f"the pipeline table spells them: {sorted(set(shouted))}")


def test_no_state_field_claims_an_elapsed_duration():
    """`**Ruled**, not built -- **16 days**` was true the day it was typed and read
    nineteen when it was next opened. A state field may carry a DATE, from which a
    reader computes the age; it may not carry the answer, because nothing
    recomputes it.

    THE STRUCTURED FIELDS ONLY, and that boundary was measured rather than chosen.
    The same rule over the registers' free prose was written, run and withdrawn:
    it flagged twelve lines and essentially every one was honest history -- "no one
    noticed for eleven days", "Sixteen days later nothing had been built", "two
    days after this was captured". A closed past interval does not rot; an open
    count against today does, and no regex over prose tells them apart. Here the
    fields are parsed, so the rule is exact instead of approximate."""
    offenders = []
    for row in _board():
        if match := ELAPSED.search(row["state"]):
            offenders.append(f"{row['id']} board cell: {match.group(0)!r} in "
                             f"{row['state']!r}")
    for entry in _entries():
        if match := ELAPSED.search(entry["state_line"]):
            offenders.append(f"{entry['id']} state line: {match.group(0)!r} in "
                             f"{entry['state_line'][:110]!r}")

    assert not offenders, (
        "these state fields count elapsed time, which is false the day after it "
        "is written. Give the date the thing happened:\n  " + "\n  ".join(offenders))


def test_every_since_is_the_date_its_entry_was_captured():
    """`since` is the day he asked, not the day anything happened afterwards.
    REQ-08 and REQ-09 were ruled on 2026-08-19 and are still `since 2026-08-17`,
    which is correct and is the reason this has to be stated."""
    captured = {}
    for entry in _entries():
        match = re.search(r"Captured (\d{4}-\d{2}-\d{2})", entry["state_line"])
        assert match, (f"{entry['id']} does not say when it was captured:\n  "
                       f"{entry['state_line'][:110]}")
        captured[entry["id"]] = match.group(1)

    wrong = [f"{row['id']}: board says {row['since']}, entry was captured "
             f"{captured[row['id']]}"
             for row in _board() if row["since"] != captured[row["id"]]]

    assert not wrong, "\n  ".join(wrong)


def test_this_guard_cannot_be_quietly_emptied():
    rows, entries = _board(), _entries()

    assert len(rows) >= FLOOR, (
        f"{len(rows)} board rows, and the floor is {FLOOR}. A row goes when a "
        "request is renumbered, never to silence a failure.")
    assert len(entries) >= FLOOR, f"{len(entries)} entries, and the floor is {FLOOR}"
