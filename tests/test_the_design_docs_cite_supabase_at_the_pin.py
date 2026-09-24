"""The design documents cite Supabase at the commit this product is built from, never master.

#1040 makes one commit of `supabase/supabase` the basis for everything Supabase covers:
the one `design/supabase.NOTICE.txt` pins. A link to `master` points at whatever Supabase
merged since, so a reader following it checks this product against a system it was never
built from, and nothing says so. Two files that the documents linked on master were
measured absent at the pin (`AGENTS.md` and `apps/studio/AGENTS.md`), and one the
roadmap called dead (`.claude/skills/copywriting/SKILL.md`) is there, and gone from master.

The live site, supabase.com/design-system, is built from master too. It stays useful to
look at, but it cannot be the citation, so every line that links it also links the `.mdx`
that page is built from, at the pin.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.docs

ROOT = Path(__file__).resolve().parent.parent
NOTICE = ROOT / "design" / "supabase.NOTICE.txt"
DESIGN_DOCS = ("docs/DESIGN-SYSTEM.md", "docs/UI-KIT.md", "docs/DESIGN-SYSTEM-SOURCES.md")

# The trailing slash is the point: `github.com/supabase/supabase-ui-web` is a different,
# deprecated repository, and the repository root with no path names no file.
REPO_LINK = re.compile(r"(?:https?://)?github\.com/supabase/supabase/([^\s)\]>\"'`]*)")
LIVE_LINK = re.compile(r"(?:https?://)?supabase\.com/design-system(/[^\s)\]>\"'`#?]*)?")


def _pin() -> str:
    """The commit, read from the notice rather than typed here a second time."""
    found = re.findall(r"^\s*Commit\s+([0-9a-f]{40})\b", NOTICE.read_text(encoding="utf-8"), re.M)
    assert len(found) == 1, f"{NOTICE.name} should pin exactly one commit, found {found}"
    return found[0]


def _lines():
    for relative in DESIGN_DOCS:
        for number, line in enumerate((ROOT / relative).read_text(encoding="utf-8").splitlines(), 1):
            yield f"{relative}:{number}", line


def test_every_link_into_supabases_repository_is_pinned():
    pin = _pin()
    pinned = re.compile(rf"(?:tree|blob)/{pin}(?:/|$)")
    seen, unpinned = 0, []
    for where, line in _lines():
        for match in REPO_LINK.finditer(line):
            seen += 1
            if not pinned.match(match.group(1)):
                unpinned.append(f"{where}: {match.group(0)}")

    # Without this, a pattern that stopped matching the documents' links would pass.
    assert seen, "found no github.com/supabase/supabase/ link in the design documents at all"
    assert not unpinned, (
        f"{len(unpinned)} link(s) into Supabase's repository do not name the pinned commit "
        f"{pin[:8]}, so they show whatever Supabase merged since:\n" + "\n".join(unpinned)
    )


def test_every_live_design_system_page_sits_beside_its_pinned_source():
    """The page on the live site and the file it is built from, on one line.

    Checked by path, not by the pin appearing somewhere on the line, so a line that
    pairs Typography with the pinned Icons page fails too.
    """
    pin = _pin()
    missing = []
    for where, line in _lines():
        for match in LIVE_LINK.finditer(line):
            page = (match.group(1) or "").strip("/")
            if not page:
                source = "apps/design-system"
            else:
                assert page.startswith("docs/"), f"{where}: unexpected live-site path {page!r}"
                source = f"apps/design-system/content/{page}.mdx"
            counterpart = re.compile(
                rf"github\.com/supabase/supabase/(?:tree|blob)/{pin}/{re.escape(source)}(?![\w./-])"
            )
            if not counterpart.search(line):
                missing.append(f"{where}: {match.group(0)} has no {source}@{pin[:8]} beside it")

    assert not missing, (
        "the live site follows master; each link to it needs the pinned file it is built "
        "from on the same line:\n" + "\n".join(missing)
    )
