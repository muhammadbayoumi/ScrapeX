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
from urllib.parse import urlsplit

from .robots import RobotsChoice


@dataclass(frozen=True)
class Measured:
    """A source's size as its study measured it, before any job of ours has counted it.

    The cost question asks with these until a run has counted; after that, with the
    stored count, dated by it (#1701, "What the engine must send").
    """

    #: Requests for a whole first crawl: the count itself, then every page of every area.
    requests: int
    total: int
    areas: int
    #: When it was measured, as a date: what the question shows beside the figure.
    counted_at: str


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
    #: Its size, measured by its study, for the cost question before any count.
    measured: Measured
    #: OFF FOR SCHEDULES UNTIL HE TURNS IT ON. `CLAUDE.md`: no source is made active
    #: without his word. A run started from the panel does not read it.
    active: bool = False

    @property
    def host(self) -> str:
        """The host his panel names a tender source by (#1701's sentences)."""
        return urlsplit(self.base_url).hostname or self.key

    @property
    def runs_blocked(self) -> dict[str, str]:
        """The modes a tender source does not run, each with the sentence that says why.

        A FULL REBUILD, his ruling of 2026-10-17 (#1701 Q3, option (a)): a tender source
        keeps every notice as it was read (the history is append-only), so a rebuild has
        nothing to archive. The panel draws the mode disabled with this sentence, and the
        route refuses it with the same one.
        """
        return {"full_rebuild": f"Full rebuild is not offered for {self.host}: it keeps "
                                "every notice as it was read, so there is nothing to "
                                "archive."}


def _worldbank() -> TenderSource:
    return TenderSource(
        key="worldbank_org",
        display_name="World Bank procurement notices",
        base_url="https://search.worldbank.org",
        robots=RobotsChoice.OBEY,
        crawl_pace_s=2.5,
        # #1647 request 12, 10 Oct 2026: 422,285 notices in 184 areas, 536 pages of
        # 1,000 and the count -- the 537 #1701's question shows.
        measured=Measured(requests=537, total=422_285, areas=184, counted_at="2026-10-10"),
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
