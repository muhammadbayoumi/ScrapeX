"""Tender sources, declared -- so the second one is an entry, not a module.

HIS RULING OF 2026-10-10 on milestone 51, option (a): a tender source registers in a
registry of its own, the way `scrapex/directories.py` registers a directory, with the
World Bank as its first entry. The job route, the panel's source list and `sourceboard`
learn it the way they learned directories (part 3b-2).

WHAT AN ENTRY CARRIES is what the release says about the source, beside the facts a run
needs: its robots choice and its pace, the two answers `source_settings` layers his own
choices over (#1584). A directory ships neither, and falls to his general settings; a
tender source ships both, because he ruled them for it.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .robots import RobotsChoice


@dataclass(frozen=True)
class TenderSource:
    """One tender source: who it is, and what it ships with."""

    #: Matches `source_site.source_key`, the key his choices and the job are filed under.
    key: str
    display_name: str
    base_url: str
    #: WHAT IT SHIPS WITH FOR robots.txt. The World Bank's: obey, and the user can change
    #: it in Library -> Edit source (his ruling on #1701 Q2, 2026-10-17).
    robots: RobotsChoice
    #: SECONDS BETWEEN REQUESTS that it ships with. The World Bank's: 2.5, the pace
    #: #1647's Q2 put to him with the whole world's 536 pages.
    crawl_pace_s: float
    #: OFF FOR SCHEDULES UNTIL HE TURNS IT ON. `CLAUDE.md`: no source is made active
    #: without his word. A run started from the panel does not read it.
    active: bool = False


def _worldbank() -> TenderSource:
    return TenderSource(
        key="worldbank_org",
        display_name="World Bank procurement notices",
        base_url="https://search.worldbank.org",
        robots=RobotsChoice.OBEY,
        crawl_pace_s=2.5,
    )


#: Every tender source this build can collect, by `source_site.source_key`.
BUILDERS: dict[str, Callable[[], TenderSource]] = {
    "worldbank_org": _worldbank,
}


def keys() -> tuple[str, ...]:
    return tuple(sorted(BUILDERS))


def get(key: str) -> TenderSource:
    """The tender source named, refused by name when it is not one: a mistyped key that
    fell back to the World Bank would collect the wrong source and report success."""
    build = BUILDERS.get(key)
    if build is None:
        raise KeyError(
            f"{key!r} is not a tender source this build can collect. Known: "
            f"{', '.join(keys())}. A new one is a `TenderSource` in scrapex/tenders.py.")
    return build()
