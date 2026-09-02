"""A crawl whose output is EVIDENCE, not rows.

Step 4 of docs/GENERIC-FETCH-SEAM.md, and the wiring that document says has
never been written. `scrapex/pagewalk.py` shipped in July with zero production
callers; `scrapex/extract/service.py:save_snapshot` has only ever been reached
by a human pressing a button in the General workspace. This joins them, and it
is the whole of what it does.

ONE PAGE IN, ONE SNAPSHOT OUT, AND NOTHING IS PARSED ON THE WAY. The seam's
central rule, and the reason is arithmetic rather than taste: interpretation
re-run against stored snapshots re-fetches nothing. On a source whose full pass
is thirty-five thousand requests, a parse that turns out wrong costs minutes
instead of ten hours. That is the product, not an optimisation — so this module
has no idea what a contractor is, and must not learn.

THE SCOPE COMES FROM THE DATABASE AND NOWHERE ELSE. `source_site.crawl_scope`
and `crawl_slice` were added by M6a and, until this file, **nothing in Python
read them**. A scope the caller could also pass would be a scope enforced in two
places, which is a scope enforced in neither — so the signature does not offer
one. `docs/PLATFORM-PLAN.md` Decision 23 is the reason it is per-source at all:
a new source has no default, and no crawl starts until the owner has answered.

EACH PAGE IS COMMITTED AS IT ARRIVES. A crawl interrupted at page 800 keeps 800
pages, which is the same reasoning the price side's job journal already
follows — and evidence is worth less the moment it can be lost by stopping.

AND UNTIL 2026-08-20 THAT SENTENCE WAS ONLY HALF TRUE. The 800 pages survived;
the knowledge of WHICH 800 did not. `generic_page_snapshot` carried no run
column, so a second attempt re-fetched every one of them — on a full pass, hours
of requests to re-learn what was already on disk. Keeping the evidence and
re-fetching it anyway is not a resume.

`run_ref` fixes it, and the shape of the fix is the point: a resume SKIPS URLS
THIS RUN ALREADY STORED, and only this run. Not "already stored ever" — a
listing is live, and a later run must re-read it to see what changed. The scope
of the skip is one run because that is exactly the scope of an interruption.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field

from .connectors.base import declare_frontier
from .crawlscope import CrawlScope, Plan, plan
from .extract.models import SnapshotCreate
from .extract.service import save_snapshot
from .pagesource import FetchedPage, PageSource
from .pagewalk import PageWalker, WalkReport
from .snapshotbody import label_for

Fetch = Callable[[str], str]


class SiteNotRegistered(LookupError):
    """No `source_site` row, so nobody has said how deep this crawl may go.

    RAISED RATHER THAN DEFAULTED. The column's default is `listing_only`, which
    is the safe scope — but a site with no row at all has not been ASKED, and
    quietly crawling it at the cheapest scope answers a question the owner was
    supposed to answer.
    """


@dataclass(frozen=True)
class CrawlOutcome:
    """What one snapshot crawl fetched, stored, and failed to."""

    plan: Plan
    report: WalkReport
    #: `generic_page_snapshot` ids, in the order the pages arrived.
    snapshots: tuple[int, ...] = ()
    #: Pages fetched but NOT stored, with why. Separate from the walker's own
    #: fetch failures because the two have different remedies: a fetch failure
    #: is the site's or the network's, a storage failure is ours.
    unstored: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    #: URLs this run had already stored, so a resume did not store them twice.
    #: NOT merged into `unstored`: that field means something went wrong, and a
    #: skip is the resume working.
    skipped: tuple[str, ...] = field(default_factory=tuple)

    @property
    def stored(self) -> int:
        return len(self.snapshots)


def read_scope(conn: sqlite3.Connection, site_key: str) -> tuple[CrawlScope, str]:
    """The scope and slice this site was registered with.

    The first reader these two columns have ever had.
    """
    row = conn.execute(
        "SELECT crawl_scope, crawl_slice FROM source_site WHERE source_key = ?",
        (site_key,)).fetchone()
    if row is None:
        raise SiteNotRegistered(
            f"no source_site row for {site_key!r}, so how deep its crawl may "
            "go has never been decided. Register the site first — a crawl that "
            "picked the default would be answering for the owner.")
    return CrawlScope(row[0]), (row[1] or "")


def already_stored(conn: sqlite3.Connection, run_ref: str) -> frozenset[str]:
    """URLs this run has already turned into evidence.

    Empty for a run nobody has started, which makes a first attempt and a resume
    the same code path — the alternative is a `resuming` flag, and a flag is a
    second place for the two to disagree.
    """
    return frozenset(row[0] for row in conn.execute(
        "SELECT source_url FROM generic_page_snapshot WHERE crawl_run_ref = ?",
        (run_ref,)))


def crawl_to_snapshots(conn: sqlite3.Connection, source: PageSource,
                       base_url: str, *, fetch: Fetch,
                       listing_pages: int, detail_pages: int = 0,
                       slice_pages: int = 0, pace_s: float = 1.0,
                       max_requests: int | None = None,
                       fetcher: object | None = None,
                       run_ref: str | None = None,
                       # `R-54`: the typed run this crawl belongs to. `run_ref` is
                       # the operator's label and is derived per cell; this is one
                       # id for the whole crawl and it is what the State column
                       # compares against.
                       run_id: int | None = None,
                       listing_phase_only: bool = False) -> CrawlOutcome:
    """Walk this site at its registered scope, storing every page as evidence.

    `listing_pages` and `detail_pages` are MEASURED BY THE CALLER and passed in,
    because only the caller has them — 865 is a fact about muqawil discovered by
    reading page one, and neither this module nor `crawlscope` may carry one
    site's numbers as though they were every site's.

    `fetcher` is optional and is only ever used to declare the frontier. It is
    passed through `declare_frontier`, which tolerates a fetcher that cannot
    hear it: reaching for `expect_requests` directly once turned a progress
    display into an AttributeError that failed real crawls.

    `listing_phase_only` IS NOT A SECOND SCOPE, which is what lets it exist beside the
    rule above. The scope still comes from the database and only from there; this says
    which PHASE the caller is running. The partitioned listing crawl is the listing phase
    by construction — it partitions, witnesses and counts listing pages, and no detail
    page enters any of its proofs — and on 2026-08-21 the absence of this distinction let
    a live change to `crawl_scope` break a crawl that was already four cells in.
    """
    scope, slice_of = read_scope(conn, source.site_key)

    # PLANNED BEFORE THE FIRST REQUEST, and by `crawlscope` rather than here.
    # It raises SliceRequired for a slice scope with no slice named, and asking
    # it now means the refusal costs nothing instead of arriving after fourteen
    # minutes of listing pages. The walker asks it again for itself; that is
    # deliberate duplication of a CHECK, never of the rule.
    #
    # AND THE PHASE DECIDES WHICH PLAN IS BEING MADE. `listing_phase_only` means no
    # detail page will be fetched, so planning the registered scope's detail pages
    # would declare a frontier this run cannot reach -- progress stalling at a
    # fraction it can never close. It also asked `SliceRequired` a question the phase
    # does not have: measured 2026-09-02, a partitioned listing crawl of a site
    # registered `listing_plus_slice` with no slice raised "listing_plus_slice needs
    # the slice named" out of a run that was never going to look at a slice. Same
    # shape as the scope refusal `partitioncrawl` dropped the same day -- a
    # whole-crawl check standing over one phase of it.
    phase_scope = CrawlScope.LISTING_ONLY if listing_phase_only else scope
    intended = plan(phase_scope, listing_pages=listing_pages,
                    detail_pages=detail_pages, slice_pages=slice_pages,
                    slice_of=slice_of)
    declare_frontier(fetcher, intended.requests)

    snapshots: list[int] = []
    unstored: list[tuple[str, str]] = []
    # READ ONCE, BEFORE THE FIRST REQUEST. Asking per page would be one query
    # per fetch for a set that only this loop appends to, and the loop knows
    # what it added.
    seen = set(already_stored(conn, run_ref)) if run_ref else set()
    skipped: list[str] = []

    def store(page: FetchedPage) -> None:
        """One page, straight into evidence, unparsed and committed at once."""
        if page.url in seen:
            # THE RESUME. Counted rather than silent: a resume that says nothing
            # is indistinguishable from a crawl that fetched everything, and the
            # difference is the hours it saved.
            skipped.append(page.url)
            return
        try:
            # THE REF GOES IN WITH THE ROW, not by a later UPDATE:
            # `trg_generic_page_snapshot_immutable_update` aborts any update to
            # this table, and the first draft of this resume learned that from a
            # test failure reading "saved HTML snapshots are immutable". The
            # trigger is right — who fetched a page is fixed at capture.
            # COMPRESSED AGAINST ITS OWN KIND. `docs/STORAGE.md` measured 187x
            # on listings and 46x on profiles with one real page of the same
            # kind as a raw zstd dictionary -- against zlib's 15.6x and 7.7x,
            # because zlib's 32 KB window never sees across a 121 KB page. This
            # is the path the 36,548 pages of «كلّ ما ينشره الموقع» arrive on, so
            # it is the path that had to learn it: 4.55 GB becomes about 90 MB.
            saved = save_snapshot(conn, SnapshotCreate(
                source_url=page.url, html_content=page.html,
                crawl_run_ref=run_ref, run_id=run_id,
                body_class=label_for(page.url, page.kind)))
            conn.commit()
        except Exception as exc:
            # NOT RAISED. One page too large, or one URL the model refuses,
            # must not discard the eight hundred already stored — the same
            # reasoning the walker applies to a dead page, one level down.
            conn.rollback()
            unstored.append((page.url, f"{type(exc).__name__}: {exc}"))
            return
        snapshots.append(int(saved["page_snapshot_id"]))
        seen.add(page.url)

    walker = PageWalker(source, fetch, pace_s=pace_s)
    report = walker.walk(base_url, scope, slice_of=slice_of,
                         max_requests=max_requests, on_page=store,
                         listing_phase_only=listing_phase_only)

    return CrawlOutcome(plan=intended, report=report,
                        snapshots=tuple(snapshots), unstored=tuple(unstored),
                        skipped=tuple(skipped))
