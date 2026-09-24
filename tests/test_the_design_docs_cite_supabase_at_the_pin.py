"""The design documents cite Supabase at the commit this product is built from, never master.

#1040 makes one commit of `supabase/supabase` the basis for everything Supabase covers:
the one `design/supabase.NOTICE.txt` pins. A link to `master` points at whatever Supabase
merged since, so a reader following it checks this product against a system it was never
built from, and nothing says so. A pinned link can still point at nothing: the documents
linked `AGENTS.md` and `apps/studio/AGENTS.md` on master, and at the pin those instructions
are `.claude/CLAUDE.md` and `apps/studio/CLAUDE.md`.

The live site, supabase.com/design-system, is built from master too. It stays useful to
look at, but it cannot be the citation, so every line that links it also links the source
that page is built from, at the pin.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tools.read_supabase_linked_paths import DESIGN_DOCS, FIXTURE, REPO_LINK, linked_paths, pinned_path

pytestmark = pytest.mark.docs

ROOT = Path(__file__).resolve().parent.parent
NOTICE = ROOT / "design" / "supabase.NOTICE.txt"

LIVE_LINK = re.compile(r"(?:https?://)?(?:www\.)?supabase\.com/design-system(/[^\s)\]>\"'`#?]*)?", re.I)

# Commits the documents name without linking them, so the link tests never see them:
# `path@<ref>:line` cites a line in Supabase's repository (any ref, so `@master:28` is
# caught); `path@<hex>` cites a whole file; and a backticked hex names the basis in prose.
# The backticked form needs one letter, so a backticked number is never read as a commit.
# An unbackticked hash in prose is not seen; the documents never write one.
AT_COMMIT = re.compile(r"[\w./-]+@([\w.-]+):\d+")
AT_HEX = re.compile(r"[\w./-]+@([0-9a-f]{7,40})(?![\w.-])", re.I)
TICKED_HEX = re.compile(r"`(?=[0-9a-f]*[a-f])([0-9a-f]{7,40})`", re.I)


def _pin() -> str:
    """The commit, read from the notice rather than typed here a second time."""
    found = re.findall(r"^\s*Commit\s+([0-9a-f]{40})\b", NOTICE.read_text(encoding="utf-8"), re.M)
    assert len(found) == 1, f"design/supabase.NOTICE.txt should pin exactly one commit, found {found}"
    return found[0]


def _lines():
    for relative in DESIGN_DOCS:
        for number, line in enumerate((ROOT / relative).read_text(encoding="utf-8").splitlines(), 1):
            yield f"{relative}:{number}", line


def test_every_link_into_supabases_repository_is_pinned():
    pin = _pin()
    seen, unpinned = 0, []
    for where, line in _lines():
        for match in REPO_LINK.finditer(line):
            seen += 1
            if not pinned_path(match, pin):
                unpinned.append(f"{where}: {match.group(0)}")

    # Without this, a pattern that stopped matching the documents' links would pass.
    assert seen, "found no link into Supabase's repository in the design documents at all"
    assert not unpinned, (
        f"{len(unpinned)} link(s) into Supabase's repository do not link tree/ or blob/ at the "
        f"pinned commit {pin[:8]}, so they show whatever Supabase merged since:\n" + "\n".join(unpinned)
    )


# Forms the documents do not hold today, so the document tests above never exercise them.
# "<pin>" is replaced by the notice's commit. None means the link is not pinned.
LINK_CASES = [
    ("https://raw.githubusercontent.com/supabase/supabase/master/x.css", None),
    ("https://raw.githubusercontent.com/supabase/supabase/<pin>/packages/ui/x.css", ("blob", "packages/ui/x.css")),
    ("https://raw.githubusercontent.com/supabase/supabase/<pin>5/x.css", None),
    ("https://raw.githubusercontent.com/supabase/supabase/<pin>-old/x.css", None),
    ("https://raw.githubusercontent.com/supabase/supabase/<pin>", None),
    ("https://raw.githubusercontent.com/supabase/supabase/<pin>/", None),
    ("https://GitHub.com/Supabase/supabase/blob/master/x.css", None),
    ("https://github.com/supabase/supabase/tree/master/x", None),
    ("https://github.com/supabase/supabase/blob/<pin>x/AGENTS.md", None),
    ("https://www.github.com/supabase/supabase/tree/<pin>/x#readme", ("tree", "x")),
    ("https://github.com/supabase/supabase/blob/<pin>/x.css?plain=1", ("blob", "x.css")),
    ("https://github.com/supabase/supabase/tree/<pin>/packages/ui/", ("tree", "packages/ui")),
    ("https://github.com/supabase/supabase/tree/<pin>", ("tree", "")),
]


@pytest.mark.parametrize("link, expected", LINK_CASES)
def test_a_link_is_pinned_only_when_it_names_the_commit(link, expected):
    pin = _pin()
    matches = list(REPO_LINK.finditer(link.replace("<pin>", pin)))
    assert len(matches) == 1, f"{link} should be read as one link into Supabase's repository"
    assert pinned_path(matches[0], pin) == expected


def test_a_neighbouring_repository_is_not_supabases():
    assert not REPO_LINK.search("https://github.com/supabase/supabase-ui-web")


def test_every_live_design_system_page_sits_beside_its_pinned_source():
    """The page on the live site and the file it is built from, on one line.

    Checked by path, not by the pin appearing somewhere on the line, so a line that
    pairs Typography with the pinned Icons page fails too.
    """
    pin = _pin()
    seen, missing = 0, []
    for where, line in _lines():
        for match in LIVE_LINK.finditer(line):
            seen += 1
            page = (match.group(1) or "").strip("/")
            if not page:
                source = "apps/design-system"
            else:
                assert page.startswith("docs/"), f"{where}: unexpected live-site path {page!r}"
                source = f"apps/design-system/content/{page}.mdx"
            counterpart = re.compile(
                rf"github\.com/supabase/supabase/(?:tree|blob)/{pin}/{re.escape(source)}(?![\w./-])", re.I
            )
            if not counterpart.search(line):
                missing.append(f"{where}: {match.group(0)} has no {source}@{pin[:8]} beside it")

    # Without this, a pattern that stopped matching the documents' links would pass.
    assert seen, "found no link to the live design-system site in the design documents at all"
    assert not missing, (
        "the live site follows master; each link to it needs the pinned file it is built "
        "from on the same line:\n" + "\n".join(missing)
    )


def test_every_commit_the_documents_name_is_the_pin():
    """A re-pin that moves the notice and the links would otherwise leave these behind.

    The lines they cite were read at the old commit, so they are re-read at the new one
    before the SHA beside them changes.
    """
    pin = _pin()
    patterns = {"path@ref:line": AT_COMMIT, "path@hex": AT_HEX, "a backticked hex": TICKED_HEX}
    seen = dict.fromkeys(patterns, 0)
    refs: dict[tuple[str, int], tuple[str, str]] = {}
    for where, line in _lines():
        for name, pattern in patterns.items():
            for match in pattern.finditer(line):
                seen[name] += 1
                # One citation can match two patterns; it is one reference, reported once.
                refs[(where, match.start(1))] = (match.group(1).lower(), match.group(0))
    stale = [f"{where}: {text}" for (where, _), (ref, text) in sorted(refs.items())
             if len(ref) < 7 or not pin.startswith(ref)]

    # One floor per pattern, so none can stop matching behind the others.
    silent = [name for name, count in seen.items() if not count]
    assert not silent, f"found no {' / '.join(silent)} in the design documents at all"
    assert not stale, (
        f"{len(stale)} reference(s) name a commit other than the pin {pin[:8]}; a re-pin re-reads "
        "each cited line at the new commit before it changes the SHA:\n" + "\n".join(stale)
    )


def test_every_pinned_link_names_a_path_the_pin_holds():
    """Pinned is not enough: the path has to be there, and be the kind of thing linked."""
    pin = _pin()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["commit"] == pin, (
        f"{FIXTURE.name} was read at {fixture['commit'][:8]} and the notice pins {pin[:8]}. "
        "Run tools/read_supabase_linked_paths.py."
    )
    held, absent = fixture["present"], set(fixture["absent"])
    linked = linked_paths(pin)
    # Without this, a parser that stopped returning paths would check nothing, and the tool
    # the failure message names would write an empty fixture to match.
    assert linked, "no pinned link in the design documents names a path"

    wrong = []
    for path, kinds in sorted(linked.items()):
        if path in absent:
            wrong.append(f"{path} is linked and is absent at {pin[:8]}")
        elif path not in held:
            wrong.append(f"{path} is linked and was never read: run tools/read_supabase_linked_paths.py")
        else:
            wrong.extend(f"{path} is linked as {kind}/ and the pin holds a {held[path][0]}"
                         for kind in sorted(kinds) if kind != held[path][0])
    assert not wrong, "\n".join(wrong)

    # The fixture is the reading of what the documents link now, not an accumulation.
    unlinked = sorted((set(held) | absent) - set(linked))
    assert not unlinked, (
        f"{FIXTURE.name} records {unlinked}, which no design document links any more. "
        "Run tools/read_supabase_linked_paths.py."
    )
