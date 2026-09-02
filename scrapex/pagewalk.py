"""The walker: everything about a crawl that is NOT about the site.

Step 2 of docs/GENERIC-FETCH-SEAM.md, and the other half of `pagesource.py`.
That file says what one site knows about its own layout; this one fetches,
paces, counts, decides how deep to go, and hands each page on. The split is
deliberate and `pagesource.py` states why:

    A `PageSource` that reaches past this line is the reason two sources will
    one day differ for no reason anybody can name.

So the walker owns pacing, the request budget, the scope, and what happens when
one page fails — and every site gets the same answer to all four.

IT DOES NOT PARSE, AND IT DOES NOT STORE. A page is handed to `on_page` exactly
as it arrived. What a page MEANS is decided later, against the stored copy,
which is what makes a wrong parse a re-read rather than a re-crawl. On a source
measured at thirty-four hours that distinction is the product.

THE ONE NUMBER THAT MATTERS. muqawil's listing is 860 pages — fourteen minutes
at the shipped pace. Its detail pages are 121,157: thirty-four hours. The scope
is what stands between those two, and the walker is where the scope is
enforced rather than merely recorded.
"""
from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from .crawlscope import CrawlScope
from .crawlscope import plan as plan_scope
from .pagesource import (
    FetchedPage,
    PageKind,
    PageSource,
    SliceNotSupported,
    slice_rows,
)

#: What the fetcher is: a url in, the page's text out. Anything that raises is
#: a failed page, and the walk goes on — see `WalkReport.failures`.
Fetch = Callable[[str], str]

#: Where a page goes once it has arrived. The walker never inspects it.
OnPage = Callable[[FetchedPage], None]


@dataclass
class WalkReport:
    """What a walk did, in the terms the owner asked the question in.

    Counted rather than inferred from the sink, because the sink may reject a
    page and the owner's question — "how much of the site did we fetch?" — is
    about requests made, not rows stored.
    """

    scope: CrawlScope
    listing_pages: int = 0
    detail_pages: int = 0
    #: (url, reason) for every page that did not arrive. Never raised: one dead
    #: detail page out of 121,157 must not discard the 121,156 that worked.
    failures: list[tuple[str, str]] = field(default_factory=list)
    #: Detail pages the slice ruled out. Named separately from `failures`
    #: because "we chose not to" and "we could not" are different answers.
    skipped: int = 0
    stopped_early: str = ""

    @property
    def requests(self) -> int:
        return self.listing_pages + self.detail_pages + len(self.failures)


class PageWalker:
    """One crawl of one site, at one scope."""

    def __init__(self, source: PageSource, fetch: Fetch, *,
                 pace_s: float = 1.0, sleep: Callable[[float], None] = time.sleep) -> None:
        self._source = source
        self._fetch = fetch
        self._pace_s = pace_s
        # Injected so a test can prove the pace is honoured without waiting for
        # it. A test that sets pace_s to 0 proves nothing about the shipped
        # value; one that records the sleeps proves exactly what was asked for.
        self._sleep = sleep
        self._fetched_any = False

    def walk(self, base_url: str, scope: CrawlScope, *, slice_of: str = "",
             max_requests: int | None = None, on_page: OnPage | None = None,
             listing_phase_only: bool = False) -> WalkReport:
        """Fetch what the scope allows, and no more.

        `max_requests` is a ceiling the caller sets, not a default: a walk that
        silently stopped at some built-in number would report a partial crawl as
        a complete one. When it bites, `stopped_early` says so.

        `listing_phase_only` IS NOT A SECOND SCOPE, and the distinction is the whole
        reason it can exist without breaking `snapshotcrawl`'s rule that the scope comes
        from the database and nowhere else. The scope says how deep a crawl of the SOURCE
        may go. This says which PHASE is running — and the partitioned listing crawl is
        the listing phase by construction: it partitions, witnesses and counts listing
        pages, and no detail page takes part in any of its proofs.
        """
        # REFUSED BEFORE THE FIRST REQUEST. `plan_scope` raises SliceRequired
        # for a slice scope with no slice named, and asking it here means the
        # refusal costs nothing instead of arriving after fourteen minutes of
        # listing pages.
        #
        # AND IT IS ASKED ABOUT THE PHASE, NOT THE REGISTRATION. Under
        # `listing_phase_only` the loop below never reaches `_details_wanted`, so a
        # slice is not consulted and "name the slice" is a demand this run cannot
        # act on and does not need. Measured 2026-09-02: a partitioned listing crawl
        # of a site registered `listing_plus_slice` with no slice died on it, having
        # fetched nothing, in a run that was never going to look at a slice.
        plan_scope(CrawlScope.LISTING_ONLY if listing_phase_only else scope,
                   listing_pages=0, detail_pages=0, slice_of=slice_of)

        report = WalkReport(scope=scope)
        for url in self._source.listing_urls(base_url):
            if self._over(report, max_requests):
                return report
            page = self._get(url, PageKind.LISTING, report)
            if page is None:
                continue
            report.listing_pages += 1
            if on_page is not None:
                on_page(page)

            if scope is CrawlScope.LISTING_ONLY or listing_phase_only:
                # `listing_phase_only` STOPPED A REAL CRAWL FROM BEING BROKEN BY A
                # CONFIGURATION CHANGE. On 2026-08-21 `source_site.crawl_scope` was set
                # to `listing_plus_slice` while a partitioned listing crawl was running —
                # the scope is read per cell, not once per run — so cell five began
                # asking `belongs_to_slice` about listing rows it had no interest in, and
                # a single card without a city ended the run after four cells had closed
                # with D=0.
                continue
            for detail in self._details_wanted(page, scope, slice_of, report):
                if self._over(report, max_requests):
                    return report
                fetched = self._get(detail, PageKind.DETAIL, report)
                if fetched is None:
                    continue
                report.detail_pages += 1
                if on_page is not None:
                    on_page(fetched)
        return report

    # -- the four things that are the walker's and never the site's ----------

    def _get(self, url: str, kind: PageKind, report: WalkReport) -> FetchedPage | None:
        """Pace, fetch, and turn a failure into a record rather than an end.

        THE PACE IS PAID BEFORE THE REQUEST AND NOT AFTER, and never before the
        first: a crawl that sleeps after its last page bills the owner for a
        second it did not need, and one that sleeps before its first delays
        every run by a second for nothing.
        """
        if self._fetched_any and self._pace_s > 0:
            self._sleep(self._pace_s)
        self._fetched_any = True
        try:
            html = self._fetch(url)
        except Exception as exc:
            # NOT RAISED. One dead page out of a hundred thousand must not
            # discard the rest, and a crawl that stops at the first 404 of a
            # thirty-four hour run is a crawl nobody can finish.
            report.failures.append((url, f"{type(exc).__name__}: {exc}"))
            return None
        return FetchedPage(url=url, html=html, kind=kind)

    def _details_wanted(self, page: FetchedPage, scope: CrawlScope,
                        slice_of: str, report: WalkReport) -> Iterable[str]:
        """Which detail pages this listing page earns, under this scope."""
        if scope is CrawlScope.FULL_THEN_LISTING:
            # NO PAIRING NEEDED: every URL is wanted, so which row it came from does
            # not matter and `detail_urls` is the honest thing to ask.
            return list(self._source.detail_urls(page))
        # A SLICE NEEDS THE ROW, AND `enumerate` WAS GUESSING IT. muqawil yields a URL
        # per locale, so index 1 was contractor 0's Arabic page being asked about card 1
        # — a different contractor — and half the indices pointed past the last card.
        # `slice_rows` gets the pairing from the source, or refuses.
        wanted = []
        for index, url in slice_rows(self._source, page):
            try:
                if self._source.belongs_to_slice(page, index, slice_of):
                    wanted.append(url)
                else:
                    report.skipped += 1
            except SliceNotSupported:
                # SURFACED, NOT SWALLOWED. Treating a site that cannot answer as
                # a site that answered "no" would produce an empty crawl wearing
                # the clothes of a successful one — which is the exact failure
                # `SliceNotSupported` was created to prevent.
                raise
        return wanted

    @staticmethod
    def _over(report: WalkReport, max_requests: int | None) -> bool:
        if max_requests is not None and report.requests >= max_requests:
            report.stopped_early = (
                f"stopped at the {max_requests}-request ceiling the caller set; "
                "this crawl is PARTIAL")
            return True
        return False
