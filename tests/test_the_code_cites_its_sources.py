"""A citation key in a comment is a lookup, and a broken one fails silently.

THE SAME DEFECT HAS ALREADY SHIPPED HERE, and it was invisible to every other guard in
this suite: fifty-three comments in `design/tokens.css` and `design/appearance.js` cited
`R-84` for rules that `R-85` makes, because the ruling was renumbered mid-branch and
nothing compared a cited number against what it names.
`tests/test_the_design_system_cites_its_own_rulings.py` was written for that. This is the
same idea pointed at the registers that say what a decision RESTS ON.

AND THE OTHER HALF HAS ALREADY SHIPPED TOO, which is why reachability is checked at all.
Measured 2026-09-23: `git grep -l DESIGN-SYSTEM-SOURCES` outside the file itself returns
nothing. 228 lines of the authority the whole design system is measured against, and no
inbound link — not from `CLAUDE.md`, not from `docs/DESIGN-SYSTEM.md`, not from a test,
not from a comment. A reference a session can only find by already knowing it exists is
not a reference.

A TABLE, NOT A HEURISTIC. "Is this comment about ES-1?" cannot be decided from prose.
What can be decided is whether a key that IS cited names an entry that EXISTS, and whether
an entry that exists is used. Both are exact, so this can only fail when something is
wrong.

ONE ROW PER REGISTER, so the second one costs a row and not a file. `REGISTERS` below
carries the engineering register; the design session adds its own row in its own change,
once `docs/DESIGN-SYSTEM.md` cites its authority list and that list names its pinned
basis commit. Two registers, two rows, one set of rules — and the last check below is
what stops them both claiming the same surface.
"""
from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass

import pytest

# THIS FILE NAMES `extension/` -- the engineering register's citations may live in
# the panel too, so `REGISTERS` searches it. The gate is one-directional
# (reads-extension implies marked), so carrying the mark costs nothing and its
# absence would stop this guard running on an extension-only change.
pytestmark = pytest.mark.extension

ROOT = pathlib.Path(__file__).resolve().parents[1]
HERE = pathlib.Path(__file__).resolve()
RULES = ROOT / "CLAUDE.md"


@dataclass(frozen=True)
class Register:
    """One authority list, and how its citations are spelled."""

    #: The file, relative to the repository root.
    path: str
    #: `ES` for `ES-1`. One prefix per register, so a key names its register.
    prefix: str
    #: The surface it governs. No two registers may claim the same one — see the last
    #: test. `CLAUDE.md` makes the panel the only interface, so "interface" and "engine"
    #: is the whole division.
    governs: str
    #: Where a citation of this register may live: (folder, glob).
    searched: tuple[tuple[str, str], ...]
    #: Documents that must link to it, beyond `CLAUDE.md`, which every register needs.
    linked_from: tuple[str, ...] = ()


REGISTERS: tuple[Register, ...] = (
    Register(
        path="docs/ENGINEERING-SOURCES.md",
        prefix="ES",
        governs="engine",
        searched=(("scrapex", "*.py"), ("extension", "*.js"), ("tests", "*.py")),
    ),
    # The design row belongs to the design session's own change, not to this one: adding
    # it here would fail CI on a file that change has not written yet.
)

IDS = [register.prefix for register in REGISTERS]


def _text(register: Register) -> str:
    path = ROOT / register.path
    assert path.exists(), (
        f"{register.path} is missing. It is the register every `{register.prefix}-n` in "
        f"the code resolves against; without it every citation is a dangling pointer."
    )
    return path.read_text(encoding="utf-8")


def _entries(register: Register) -> dict[str, str]:
    """`{"ES-1": "A pipeline stage is not a user step"}` from the `##` headings."""
    heading = re.compile(rf"^## ({register.prefix}-(\d+)) · (.+)$", re.MULTILINE)
    return {key: title for key, _, title in heading.findall(_text(register))}


def _citations(register: Register) -> dict[str, list[str]]:
    """Every key of this register cited in code, mapped to the files citing it.

    THE REGISTER AND THIS FILE ARE BOTH EXCLUDED, and this file caught itself the first
    time it ran: the guard names keys as EXAMPLES, and an example is not a citation. A
    file that describes the scheme cannot also be evidence of it being used.
    """
    citation = re.compile(rf"\b{register.prefix}-(\d+)\b")
    register_path = ROOT / register.path
    found: dict[str, list[str]] = {}
    for folder, pattern in register.searched:
        for path in sorted((ROOT / folder).rglob(pattern)):
            if path in (register_path, HERE) or "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for number in set(citation.findall(text)):
                found.setdefault(f"{register.prefix}-{number}", []).append(
                    str(path.relative_to(ROOT)).replace("\\", "/"))
    return found


@pytest.mark.parametrize("register", REGISTERS, ids=IDS)
def test_every_key_cited_in_the_code_names_a_real_entry(register: Register):
    """A citation that points at nothing sends the next session looking for a rationale
    that was never written — and it does it with full confidence."""
    entries = _entries(register)
    dangling = {key: files for key, files in _citations(register).items()
                if key not in entries}

    assert not dangling, (
        f"these keys are cited in code and are not in {register.path}:\n  "
        + "\n  ".join(f"{key} — cited in {', '.join(files)}"
                      for key, files in sorted(dangling.items()))
        + "\n\nEither the entry was never written, or the key drifted. A register never "
          "renumbers an entry, so the citation is the thing to fix."
    )


@pytest.mark.parametrize("register", REGISTERS, ids=IDS)
def test_every_entry_is_cited_by_the_code_it_governs(register: Register):
    """AN ENTRY WITH NO CITATION IS A READING LIST, and this repository has already
    decided what it thinks of those: `docs/UI-KIT.md` refuses to let its own catalogue be
    padded, for the same reason — a list nobody trusts is worse than a short one."""
    cited = set(_citations(register))
    orphans = {key: title for key, title in _entries(register).items()
               if key not in cited}

    assert not orphans, (
        f"these entries of {register.path} exist and no line of code cites them:\n  "
        + "\n  ".join(f"{key} · {title}" for key, title in sorted(orphans.items()))
        + "\n\nAn entry earns its place by being cited at a line that would be built "
          "differently without it. Cite it, or remove it."
    )


@pytest.mark.parametrize("register", REGISTERS, ids=IDS)
def test_each_entry_is_cited_where_it_says_it_is(register: Register):
    """`Cited at:` IS LOAD-BEARING, and a mutation is what made it so.

    The guard above asks only that SOMETHING cites an entry, and a test citing it counts
    — so removing the citation from the production code it governs survived, because the
    test that exercises that code names the key in its own docstring. That is exactly the
    drift this file exists to catch, one level in.

    So each entry NAMES the files it is cited at, and this asserts those files really do.
    The entry stops being able to describe a state the code is not in.
    """
    cited_at = re.compile(r"^\*\*Cited at:\*\* (.+)$", re.MULTILINE)
    text = _text(register)
    heading = re.compile(rf"^## ({register.prefix}-\d+) · ", re.MULTILINE)
    sections = heading.split(text)
    missing: list[str] = []
    for key, body in zip(sections[1::2], sections[2::2], strict=True):
        named = cited_at.search(body)
        assert named, (
            f"{key} does not say where it is cited. Every entry carries a "
            f"`**Cited at:**` line naming the files that use it."
        )
        for path in re.findall(r"`([^`]+\.(?:py|js|css|mjs))`", named.group(1)):
            whole = (ROOT / path)
            if not whole.exists():
                missing.append(f"{key} names {path}, which does not exist")
            elif key not in whole.read_text(encoding="utf-8"):
                missing.append(f"{key} says it is cited at {path}, and it is not")
    assert not missing, (
        f"{register.path} describes citations that are not there:\n  "
        + "\n  ".join(missing)
        + "\n\nEither cite it there, or correct the entry. A register that can describe "
          "a state the code is not in is a register nobody can trust."
    )


@pytest.mark.parametrize("register", REGISTERS, ids=IDS)
def test_the_register_is_reachable(register: Register):
    """THE ORPHAN FAILURE, GUARDED — because it has already happened here.

    `docs/DESIGN-SYSTEM-SOURCES.md` carries the authority the design system is measured
    against and, measured 2026-09-23, nothing in the repository links to it. Every
    session that needed it had to already know it existed.
    """
    name = pathlib.Path(register.path).stem
    rules = RULES.read_text(encoding="utf-8")
    assert name in rules, (
        f"CLAUDE.md does not name {register.path}, so a session reading the rules has no "
        f"way to reach what they rest on. That is exactly how "
        f"docs/DESIGN-SYSTEM-SOURCES.md became unreachable."
    )
    for document in register.linked_from:
        text = (ROOT / document).read_text(encoding="utf-8")
        assert name in text, f"{document} does not link to {register.path}"


@pytest.mark.parametrize("register", REGISTERS, ids=IDS)
def test_a_key_is_spelled_one_way(register: Register):
    """`ES-01` and `ES-1` would be two keys for one entry, and the guard above would
    accept the padded form as a dangling citation forever."""
    padded = re.findall(rf"\b{register.prefix}-0\d+\b", _text(register))
    assert not padded, (
        f"{register.path} spells a key with a leading zero: {sorted(set(padded))}. "
        f"One spelling only — `{register.prefix}-1`, never `{register.prefix}-01`."
    )


@pytest.mark.parametrize("register", REGISTERS, ids=IDS)
def test_the_register_states_its_precedence_order(register: Register):
    """Without it, "several trusted sources" is a longer way of saying "whichever one the
    session found first". The owner asked for the order explicitly on 2026-09-23."""
    text = _text(register).lower()
    assert "precedence" in text or "resolution order" in text, (
        f"{register.path} names sources but not which one wins when two disagree"
    )


def test_no_two_registers_claim_the_same_surface():
    """TWO AUTHORITIES OVER ONE SURFACE IS NOT TWO OPINIONS, IT IS NO AUTHORITY.

    The engineering register's precedence order puts a normative standard above
    everything; the design register's puts Supabase above WCAG, which the owner ruled
    again on 2026-09-23. Both are right on their own surface and neither is right on the
    other's, so the division has to be exact rather than understood.
    """
    surfaces = [register.governs for register in REGISTERS]
    assert len(surfaces) == len(set(surfaces)), (
        f"two registers claim the same surface: {sorted(surfaces)}"
    )
    for register in REGISTERS:
        text = _text(register).lower()
        others = [one.governs for one in REGISTERS if one is not register]
        for other in others:
            assert other in text, (
                f"{register.path} does not say which register governs the {other!r} "
                f"surface. A session that lands on the wrong register follows the wrong "
                f"precedence order and never finds out."
            )
