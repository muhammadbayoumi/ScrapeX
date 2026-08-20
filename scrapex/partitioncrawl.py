"""A listing crawl that can PROVE it read everything, instead of hoping it did.

THE INCIDENT THIS ANSWERS. The owner asked whether membership 10001274 was in the
warehouse. It was not, the site answers 200 for it, and the warehouse had no way
to know it was guessing — «لا اريد تكرار هذا الامر». `scrapex/sightings.py` made
"what did the site show us that we did not store" a query. This module makes the
harder half answerable: **what did the site not show us at all.**

WHY A BLIND PASS CANNOT ANSWER IT, measured rather than argued. muqawil's listing
order is not randomised per request: it is a randomised ordering held in a cache
whose generation lasts at least 157 s and had rolled by 282 s. So

  * inside one generation, pagination is an EXACT PARTITION — pages disjoint,
    together covering every published row once;
  * across generations it is INDEPENDENT RESAMPLING.

871 pages take far longer than one generation, so a full pass is a sample and not
a census: six passes over 8h37m saw 11,059 of 17,275 slots and the sixth pass
still brought 62 names never seen before. The blind model — expected unseen
`N·e^(−k)` after k passes — was validated (it predicted 42.9 unseen after six; the
sweep observed 38) and it can never report "complete", only "probably".

THE METHOD, and `docs/BACKLOG.md` DEC-11 carries its measurements:

  0 · SIZE THE WHOLE LISTING.  `N = (L−1)·S + c`, with L from the paginator's own
      `»` link, S the cards on page 1 and c the cards on page L. S IS READ, NEVER
      ASSUMED: the last page carried 15 cards on 2026-08-16, 2 on the morning of
      2026-08-20 and 13 on the evening. Two requests, where a six-pass sweep cost
      8h54m to reach a smaller and less exact answer.
  1 · SIZE EVERY CELL the same way, from its own paginator.
  2 · READ each cell whole, then RE-FETCH ITS PAGE 1 and compare THE ID SEQUENCE.
      Same sequence ⇒ the generation never rolled ⇒ those pages were one true
      partition. **Never the bytes**: a re-fetched page 1 whose id order was
      identical was measured NOT byte-identical, so a byte comparison would have
      certified nothing, ever, while looking like it worked.
  3 · AUDIT EXHAUSTIVENESS. Is `Σ N_cell` equal to `N_whole`? A shortfall is
      exactly the count of contractors whose facet value is null — the
      "contractor in no partition" case, counted instead of silently dropped.
  4 · REPORT THE DEFICIT. `D = N − |distinct ids|`. `D > 0` proves incompleteness
      and names its size; `D == 0` with a held witness proves every published row
      position was read.

TWO NUMBERS PER CELL, BECAUSE THERE ARE TWO QUESTIONS. What we OBSERVED (the
union of ids over every attempt) and what we can PROVE (one attempt whose witness
held and whose own ids accounted for the cell). The union can reach N by luck
across two generations and that proves nothing, so `provably_complete` is never
computed from it.

WHAT THIS STILL CANNOT SEE, and it is the most important paragraph here. It
proves it read every row the paginated listing PUBLISHES. It cannot prove the
listing publishes every contractor the site knows: the site's own header counts
123,842 "Saudi Contractor" against 17,413 published rows, a factor of 7.1. So the
only honest warehouse claim is *"every contractor findable in the muqawil.org
contractor listing as of «timestamp»"* — never *"every Saudi contractor"*.

EVERY CELL IS SIZED BEFORE ANY PAGE IS STORED, AND THAT IS A REAL COST STATED
RATHER THAN HIDDEN. The frontier is declared once, after sizing, so it is a COUNT
and not an estimate — every cell has published its own page count by then. The price
is that the first ~112 requests store nothing (about six minutes on muqawil), and a
resumed run pays them again because sizing is not resumable: ~5.7% overhead on each
resume of a ~2,000-request crawl. Worth it for a progress denominator that is
arithmetic, and `--plan` exists so the sizing can be paid once on purpose and read.

PACING IS THE FETCHER'S, AND IN ONE LAYER ONLY. `HttpFetcher(min_interval_s=…)`
rate-limits with jitter, honours `Retry-After` and breaks its own circuit; this
module adds nothing on top and passes `pace_s=0` down to the walker on purpose. A
crawl that paced in two layers would pay both — a second per request over ~2,000
requests is thirty-three minutes — and neither layer would know about the other.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .connectors.base import declare_frontier
from .crawlscope import CrawlScope
from .pagesource import WHOLE, Cell, PageSource
from .sightings import record_sightings
from .snapshotbody import decode
from .snapshotcrawl import already_stored, crawl_to_snapshots, read_scope

Fetch = Callable[[str], str]

#: Cells larger than this are read ONCE and their witness is reported rather than
#: retried. MEASURED, not chosen: the generation floor is 157 s and a filtered
#: page costs a few seconds, so about 31 pages is where a cell stops fitting
#: inside one generation. Five city×size cells stay above it whatever axis is
#: used — worst RIYADH×verysmall at ~212 pages — and `user_type` only halves it.
#: Retrying those is a cost with no prospect of a proof: a failed witness still
#: contributes every id it read, so reading such a cell twice buys ids we already
#: have. The verdict is reported honestly instead of bought expensively.
RETRY_PAGE_CEILING = 31


class ScopeNotPartitionable(ValueError):
    """This site is registered for a scope a listing partition cannot honour.

    REFUSED RATHER THAN NARROWED. The scope comes from `site_profile` and from
    nowhere else — that is `snapshotcrawl`'s rule and the reason it has no scope
    parameter. A partition crawl under `full_then_listing` would fetch twenty
    profile pages for every listing page it read, so a run priced at ~2,000
    requests would silently become ~40,000 and take a day. Quietly downgrading
    the scope instead would be this module deciding what the owner registered.
    """


@runtime_checkable
class PartitionedListing(Protocol):
    """What one site knows about how its own listing can be cut into slices.

    THE SAME SPLIT AS `pagesource.py` AND `pagewalk.py`, for the same stated
    reason: a `PageSource` that reaches past its line "is the reason two sites
    will one day differ for no reason anybody can name". Which query parameters
    exist, which of their values are exhaustive, and how an id is read off a card
    are facts about ONE SITE. Size, witness, deficit and audit are facts about the
    METHOD, and they live here.
    """

    #: Matches `site_profile.site_key`, which is how the crawl finds its scope.
    site_key: str

    #: The locales every page is fetched in, and the one the arithmetic reads.
    locales: tuple[str, ...]
    primary_locale: str

    def cells(self) -> tuple[Cell, ...]:
        """The partition. Exhaustive, or the audit will say by how much it is not."""

    def listing_url(self, base_url: str, *, locale: str, page: int,
                    cell: Cell = WHOLE) -> str:
        """One listing page's URL. The site's only URL builder — see its own note
        on why a second one breaks resume."""

    def read_last_page(self, html: str) -> int:
        """The highest page this listing's own paginator links to."""

    def read_ids(self, html: str) -> tuple[str, ...]:
        """Every row id on this page, IN PUBLISHED ORDER and keeping duplicates."""

    def in_cell(self, cell: Cell, *, last_page: int) -> PageSource:
        """A `PageSource` naming exactly this cell's pages."""


@dataclass(frozen=True)
class CellSize:
    """What one cell's own paginator says it holds, and what that cost to ask.

    `(L−1)·S + c` AND NOT `L·S`. The last page is short by definition, and using
    `L·S` overstated the directory by up to nineteen contractors — small, and
    still the difference between a deficit of zero and a deficit that sends
    someone looking for rows that were never published.
    """

    cell: Cell
    last_page: int
    cards_per_page: int
    tail_cards: int
    #: Requests spent measuring it: 2, or 1 when the cell is a single page.
    requests: int

    @property
    def declared(self) -> int:
        return (self.last_page - 1) * self.cards_per_page + self.tail_cards

    def __str__(self) -> str:
        return (f"{self.cell.label}: L={self.last_page} S={self.cards_per_page} "
                f"c={self.tail_cards} N={self.declared:,}")


@dataclass(frozen=True)
class Attempt:
    """One read of one cell, and whether its witness held.

    ITS OWN IDS, NEVER THE UNION. `deficit` here is what THIS read accounted for,
    which is the only quantity a proof can be built on: ids gathered across two
    generations can add up to N without any single read having covered the cell.
    """

    #: The ids this read saw, in page order, duplicates kept.
    ids: tuple[str, ...]
    pages_read: int
    witnessed: bool
    #: Why the witness held or did not, in words a person can act on.
    note: str
    #: The `crawl_run_ref` this attempt's evidence was stored under.
    run_ref: str
    snapshots: tuple[int, ...] = ()
    unstored: tuple[tuple[str, str], ...] = ()
    #: Pages that did not ARRIVE. Each one cost a request.
    failures: tuple[tuple[str, str], ...] = ()
    #: Pages that arrived and could not be READ. Counted apart from `failures`
    #: because they are not the same event and not the same cost: a fetch failure
    #: is a request spent for nothing, a parse failure is a page already counted in
    #: `pages_read` and already stored as evidence. Adding them together made
    #: `CellOutcome.requests` report a cost the crawl never paid.
    parse_failures: tuple[tuple[str, str], ...] = ()
    #: Pages this ref had already stored, so a resume did not store them twice.
    skipped: tuple[str, ...] = ()
    #: Pages whose ids were read back off disk instead of off the wire — a resume
    #: working. See `_ids_from_disk`.
    recovered: tuple[str, ...] = ()
    #: 1 when the witness re-fetched page 1, 0 when it had nothing to compare and
    #: never asked. A flat 1 charged the crawl for a request it did not make.
    witness_requests: int = 1

    @property
    def distinct(self) -> int:
        return len(set(self.ids))


@dataclass(frozen=True)
class CellOutcome:
    """One cell, after every attempt it was given."""

    size: CellSize
    attempts: tuple[Attempt, ...] = ()

    @property
    def ids(self) -> frozenset[str]:
        """Every id any attempt saw. A failed witness still contributes its ids —
        DEC-11 is explicit about it, and they are the only evidence that exists
        for the contractors on the pages that were read."""
        return frozenset(one for attempt in self.attempts for one in attempt.ids)

    @property
    def observed_deficit(self) -> int:
        """`N − |distinct seen|`. Negative means MORE distinct ids than the cell
        declared, which is what a rolled generation or an arrival looks like: not
        an error, and not a proof either."""
        return self.size.declared - len(self.ids)

    @property
    def proof(self) -> Attempt | None:
        """The attempt that proves this cell complete, if one did."""
        for attempt in self.attempts:
            if attempt.witnessed and attempt.distinct == self.size.declared:
                return attempt
        return None

    @property
    def provably_complete(self) -> bool:
        return self.proof is not None

    @property
    def requests(self) -> int:
        """Every request this cell cost: sizing, its pages, and its witnesses.

        A PARSE FAILURE IS NOT A REQUEST and a witness that had nothing to compare
        did not make one. Both were counted here once, and a cost report that
        overstates is as useless as one that understates.
        """
        return (self.size.requests
                + sum(attempt.pages_read + len(attempt.failures)
                      + attempt.witness_requests
                      for attempt in self.attempts))

    def __str__(self) -> str:
        if self.provably_complete and not self.size.declared:
            # "COMPLETE, D=0 over 0" is arithmetically right and unreadable in a
            # fifty-six line report. A cell the site publishes nothing in should
            # say so.
            verdict = "EMPTY — the site publishes no rows in this cell"
        elif self.provably_complete:
            verdict = f"COMPLETE, D=0 over {self.size.declared:,}"
        elif self.observed_deficit == 0:
            verdict = (f"{len(self.ids):,} of {self.size.declared:,} seen and none "
                       "missing, but no witness held — observed, not proven")
        else:
            verdict = (f"{len(self.ids):,} of {self.size.declared:,}, "
                       f"D={self.observed_deficit:,}")
        return (f"{self.size.cell.label}: {verdict} "
                f"[{len(self.attempts)} attempt(s), {self.requests} requests]")


@dataclass(frozen=True)
class PartitionOutcome:
    """What the whole partition read, and what it can and cannot claim."""

    #: The unfiltered listing, sized before the first cell.
    whole: CellSize
    cells: tuple[CellOutcome, ...] = ()
    #: The unfiltered listing, sized again at the end. `None` if it was not asked.
    whole_at_end: CellSize | None = None
    #: Ids recorded into `dataset_sighting`, cumulatively, as the run went.
    newly_sighted: int = 0
    #: Cells whose OWN PAGINATOR could not be read, with why. They were not read at
    #: all, so they contribute nothing to `declared_sum` — which is what makes them
    #: show up as an exhaustiveness deficit rather than vanish. Kept as a field and
    #: not merely a note because `provably_complete` has to see them.
    unsized: tuple[tuple[str, str], ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def declared_sum(self) -> int:
        return sum(cell.size.declared for cell in self.cells)

    @property
    def exhaustiveness_deficit(self) -> int:
        """`N_whole − Σ N_cell`. Above zero means rows in NO cell — the case that
        makes a partition method unsound, counted rather than assumed away. On
        muqawil it was 1,437 until `region_id=0` was found to address exactly
        them."""
        return self.whole.declared - self.declared_sum

    @property
    def ids(self) -> frozenset[str]:
        return frozenset().union(*(cell.ids for cell in self.cells)) \
            if self.cells else frozenset()

    @property
    def deficit(self) -> int:
        """`N_whole − |distinct ids|`, the number the owner's question reduces to."""
        return self.whole.declared - len(self.ids)

    @property
    def arrivals(self) -> int:
        """How much the listing grew while the crawl ran. `0` if not re-sized."""
        if self.whole_at_end is None:
            return 0
        return self.whole_at_end.declared - self.whole.declared

    @property
    def provably_complete(self) -> bool:
        """Every cell proven, and no row outside every cell.

        BOTH HALVES ARE REQUIRED. Fifty-six proven cells that together declare
        fewer rows than the listing prove fifty-six things and not the one that
        was asked. And a cell that could not be SIZED is not a cell that was read:
        it would otherwise be silently absent from a partition still calling itself
        exhaustive.
        """
        return (bool(self.cells)
                and not self.unsized
                and self.exhaustiveness_deficit == 0
                and all(cell.provably_complete for cell in self.cells))

    @property
    def requests(self) -> int:
        return self.whole.requests + sum(cell.requests for cell in self.cells) \
            + (self.whole_at_end.requests if self.whole_at_end else 0)

    def __str__(self) -> str:
        proven = sum(1 for cell in self.cells if cell.provably_complete)
        lines = [
            f"listing declared {self.whole.declared:,} rows over "
            f"{self.whole.last_page} pages",
            f"partition declared {self.declared_sum:,} over {len(self.cells)} cells "
            f"— exhaustiveness deficit {self.exhaustiveness_deficit:,}",
            f"distinct ids seen {len(self.ids):,} — D = {self.deficit:,}",
            f"cells proven complete {proven} of {len(self.cells)}",
            f"requests {self.requests:,}",
        ]
        if self.provably_complete:
            lines.append(
                "PROVABLY COMPLETE for the listing as published. This is a claim "
                "about what the listing PUBLISHES and never about every "
                "contractor the site knows.")
        else:
            lines.append(
                "NOT proven complete. The deficit above is a floor on what is "
                "missing, not an estimate of it.")
        if self.arrivals:
            lines.append(
                f"and the listing grew by {self.arrivals:,} rows while this ran, so "
                "the claim is 'complete as of the start, with those deferred'")
        lines.extend(self.notes)
        return "\n".join(lines)


def size_cell(fetch: Fetch, partition: PartitionedListing, base_url: str,
              cell: Cell = WHOLE) -> CellSize:
    """`(L, S, c)` for one cell, from the cell's own paginator. One or two requests.

    THE PAGE COUNT NEVER NEEDED A SWEEP, and this is the request that replaced
    one. The paginator publishes its own last page in a `»` link, filtered or
    not — `read_last_page` reads the filtered case correctly since #229, where it
    used to raise on `&amp;page=322` and let a caller read a 322-page region as a
    single page of twenty.
    """
    first = fetch(partition.listing_url(base_url, locale=partition.primary_locale,
                                        page=1, cell=cell))
    last_page = partition.read_last_page(first)
    cards_per_page = len(partition.read_ids(first))
    if last_page == 1:
        return CellSize(cell=cell, last_page=1, cards_per_page=cards_per_page,
                        tail_cards=cards_per_page, requests=1)
    tail = fetch(partition.listing_url(base_url, locale=partition.primary_locale,
                                       page=last_page, cell=cell))
    return CellSize(cell=cell, last_page=last_page, cards_per_page=cards_per_page,
                    tail_cards=len(partition.read_ids(tail)), requests=2)


class _Unstored:
    """A `PageSource` with the pages this run already stored TAKEN OUT.

    THIS IS WHERE THE RESUME SAVES REQUESTS, and it has to be here because
    `snapshotcrawl`'s does not. Its resume is checked inside `on_page`, which the
    walker calls AFTER fetching — so a re-run re-fetches every page and then
    declines to store it. That saves the write and none of the hours; measured, by
    a resumed crawl of a nine-row cell costing exactly as many requests as the
    first run. Recorded as an open problem against that module rather than fixed
    here, because the scope of its resume is its own decision (`R-01`).

    A CELL, NOT A SITE. `already_stored` is keyed on `crawl_run_ref`, and each
    attempt has its own ref — so this removes only what THIS attempt stored, which
    is exactly the scope of an interruption. A retry gets a fresh ref and
    therefore removes nothing, which is what a retry is for.

    THE PAGES IT REMOVES ARE NOT LOST TO THE ARITHMETIC. Their ids are read back
    off the stored snapshot by `_ids_from_disk`, so the deficit is computed over
    everything the cell was ever read to hold, and not over what this process
    happened to fetch.
    """

    def __init__(self, inner: PageSource, stored: frozenset[str]) -> None:
        self.site_key = inner.site_key
        self._inner = inner
        self._stored = stored

    def listing_urls(self, base_url: str) -> Iterable[str]:
        return (url for url in self._inner.listing_urls(base_url)
                if url not in self._stored)

    def detail_urls(self, page):
        return self._inner.detail_urls(page)

    def belongs_to_slice(self, page, row_index: int, slice_of: str) -> bool:
        return self._inner.belongs_to_slice(page, row_index, slice_of)


def _ids_from_disk(conn: sqlite3.Connection, partition: PartitionedListing,
                   urls: Iterable[str]) -> dict[str, tuple[str, ...]]:
    """Ids for pages this run had already stored, read back off the evidence.

    THIS IS WHAT THE SNAPSHOTS ARE FOR, and without it a resumed run reports a
    false deficit. `snapshotcrawl`'s resume SKIPS urls this run already stored —
    correctly, they are on disk — but a skipped page is never fetched, so nothing
    harvests its ids and the cell looks emptier than it was read. Re-parsing the
    stored copy costs no request, which is the whole economics of storing it.

    THE WITNESS WILL THEN LEGITIMATELY FAIL, and that is the right answer rather
    than a shortcoming. Pages recovered from disk were read in an earlier
    generation; the cell was NOT read inside one, so it cannot be proven from
    this attempt, and the retry that follows is the method working.
    """
    found: dict[str, tuple[str, ...]] = {}
    for url in urls:
        row = conn.execute(
            "SELECT page_snapshot_id, source_url, html_content, html_codec, "
            "       html_dict_id FROM generic_page_snapshot "
            " WHERE source_url = ? ORDER BY page_snapshot_id DESC LIMIT 1",
            (url,)).fetchone()
        if row is None:
            continue
        try:
            found[url] = partition.read_ids(decode(conn, row))
        except Exception:
            # A page that cannot be decoded or parsed contributes nothing and
            # must not end the crawl. It shows up as a smaller `recovered` set
            # against a larger `skipped` one, which is visible in the report.
            continue
    return found


def witness(fetch: Fetch, partition: PartitionedListing, base_url: str,
            cell: Cell, before: Sequence[str] | None) -> tuple[bool, str]:
    """Re-fetch this cell's page 1 and say whether the generation held.

    THE COMPARISON IS THE ID SEQUENCE. Order included, duplicates included, bytes
    never — see `read_ids` and DEC-11's correction, which is the one that would
    have broken everything: a byte comparison fails on every response because the
    body carries per-render noise, so the method would have certified nothing at
    all while appearing to run.

    AND `before` IS PAGE 1 AS THE READ SAW IT, not as the sizing saw it. The
    window that has to be free of a generation roll is exactly the window in which
    the cell's pages were read; bracketing a wider one would fail witnesses for
    time spent measuring rather than reading.
    """
    if before is None:
        # `None` IS NOT `()`, AND CONFLATING THEM COSTS A CELL ITS PROOF. `None`
        # means page 1 was never read in this attempt — the absence of evidence.
        # `()` means it WAS read and published no rows, which is a real state and
        # a witnessable one: measured 2026-08-20, `region_id=8 & company_size=big`
        # publishes zero contractors and still serves a paginator. Treating its
        # empty page 1 as "nothing to witness" would leave that cell forever
        # unproven, and one unprovable cell makes the whole partition unprovable.
        return False, ("page 1 of this cell was never read in this attempt, so "
                       "there is nothing to witness against")
    try:
        after = partition.read_ids(fetch(partition.listing_url(
            base_url, locale=partition.primary_locale, page=1, cell=cell)))
    except Exception as exc:
        # A FAILED WITNESS IS A VERDICT, NOT AN END. Found by a test that made the
        # parser throw: the fetch and the parse here were unguarded, so one
        # unreadable page 1 out of fifty-six would have raised out of
        # `crawl_partition` and discarded every cell already read — after hours.
        # Not being able to witness is exactly what `witnessed=False` means.
        return False, (f"the witness could not be read: {type(exc).__name__}: "
                       f"{exc}. This cell's ids still count; its completeness is "
                       "not claimed.")
    if tuple(after) == tuple(before):
        if not after:
            return True, ("page 1 published no rows on both readings, so this cell "
                          "is empty — complete by having nothing in it")
        return True, (f"page 1 came back in the same order ({len(after)} ids), so "
                      "the listing's generation never rolled while this cell was "
                      "read: its pages were one true partition")
    common = len(set(after) & set(before))
    return False, (f"page 1 came back reordered — {common} of {len(before)} ids in "
                   "common. The generation rolled during the read, so these pages "
                   "were not one partition. Their ids still count.")


def _read_cell(conn: sqlite3.Connection, partition: PartitionedListing,
               base_url: str, size: CellSize, *, fetch: Fetch, run_ref: str,
               ) -> Attempt:
    """One attempt at one cell: read every page, then witness it."""
    cell = size.cell
    # EXACT URLS, NOT A SUBSTRING TEST. The harvester has to recognise the
    # primary-locale pages among the fetches the walker makes, and it recognises
    # them by asking the site to build the same URLs it will walk. Matching
    # `"/en/"` inside a url would be a heuristic where an equality is available.
    wanted = {partition.listing_url(base_url, locale=partition.primary_locale,
                                    page=page, cell=cell): page
              for page in range(1, size.last_page + 1)}
    seen: dict[int, tuple[str, ...]] = {}
    parse_failures: list[tuple[str, str]] = []

    def harvesting(url: str) -> str:
        html = fetch(url)
        page = wanted.get(url)
        if page is not None:
            try:
                seen[page] = partition.read_ids(html)
            except Exception as exc:
                # A PARSE MUST NOT BREAK A FETCH. The walker turns any exception
                # from `fetch` into a failed page, so letting a parse error
                # escape here would discard a page the site served perfectly and
                # report it as the site's fault.
                parse_failures.append((url, f"{type(exc).__name__}: {exc}"))
        return html

    # THE RESUME, AND IT REMOVES THE PAGES BEFORE THEY ARE FETCHED. See
    # `_Unstored` for why that cannot be left to `snapshotcrawl`.
    stored = already_stored(conn, run_ref)
    source = _Unstored(partition.in_cell(cell, last_page=size.last_page), stored)
    outcome = crawl_to_snapshots(
        conn, source, base_url, fetch=harvesting,
        listing_pages=size.last_page * len(partition.locales),
        # PACED BY THE FETCHER AND NOWHERE ELSE — see the module docstring. And
        # `fetcher=None` so the frontier is declared ONCE for the whole
        # partition rather than reset fifty-six times.
        pace_s=0, fetcher=None, run_ref=run_ref)

    # BOTH SETS, and they should not overlap. `_Unstored` removes a page before it
    # is fetched; `outcome.skipped` is a page the walker fetched and the store
    # declined. Reading both means a change in either module leaves the arithmetic
    # right rather than quietly short by a page.
    left_out = [url for url in wanted if url in stored]
    recovered = _ids_from_disk(
        conn, partition, dict.fromkeys(left_out + list(outcome.skipped)))
    for url, ids in recovered.items():
        if url in wanted:
            seen.setdefault(wanted[url], ids)

    ordered = tuple(one for page in sorted(seen) for one in seen[page])
    # `seen.get(1)` GIVES `None` FOR A PAGE NEVER READ AND `()` FOR ONE READ EMPTY,
    # and `witness` needs to tell those apart. See its own note. The same
    # distinction decides whether a request was spent: `witness` returns early on
    # `None` without fetching anything.
    baseline = seen.get(1)
    held, note = witness(fetch, partition, base_url, cell, baseline)
    return Attempt(
        ids=ordered, pages_read=outcome.report.listing_pages, witnessed=held,
        note=note, run_ref=run_ref, snapshots=outcome.snapshots,
        unstored=outcome.unstored, failures=tuple(outcome.report.failures),
        parse_failures=tuple(parse_failures),
        skipped=tuple(left_out) + outcome.skipped,
        recovered=tuple(sorted(recovered)),
        witness_requests=0 if baseline is None else 1)


def crawl_partition(conn: sqlite3.Connection, partition: PartitionedListing,
                    base_url: str, *, fetch: Fetch, run_ref: str,
                    dataset_key: str, cells: Sequence[Cell] | None = None,
                    max_attempts: int = 2,
                    retry_page_ceiling: int = RETRY_PAGE_CEILING,
                    fetcher: object | None = None,
                    resize_at_end: bool = True,
                    on_cell: Callable[[CellOutcome], None] | None = None,
                    ) -> PartitionOutcome:
    """Read every cell, witness each one, and report what can be proven.

    `run_ref` IS REQUIRED, unlike in `crawl_to_snapshots` where it is optional.
    Without it there is no resume, and this crawl is ~2,000 requests over hours —
    the exact length at which an interruption that cannot be resumed means paying
    for everything already on disk a second time. Each cell attempt gets its own
    derived ref (`{run_ref}-{cell}-a{n}`), and a RETRY DELIBERATELY GETS A NEW
    ONE: a retry exists to read the cell inside a fresh generation, so it must
    re-fetch rather than be skipped as already stored. The second copy costs
    almost nothing — the store compresses a listing page 187× against its own
    kind — and it is evidence of two generations rather than a duplicate.

    IT REFUSES A SCOPE IT CANNOT HONOUR rather than narrowing one. See
    `ScopeNotPartitionable`.
    """
    scope, _slice = read_scope(conn, partition.site_key)
    if scope is not CrawlScope.LISTING_ONLY:
        raise ScopeNotPartitionable(
            f"{partition.site_key} is registered as {scope.value!r}. A partition "
            "crawl is the LISTING half and would fetch a detail page for every "
            "row it read under that scope — thousands of requests nobody asked "
            f"for. Register it as {CrawlScope.LISTING_ONLY.value!r} for this "
            "crawl, or run the detail crawl deliberately.")

    whole = size_cell(fetch, partition, base_url)
    plan = tuple(cells) if cells is not None else partition.cells()

    # ONE UNSIZEABLE CELL MUST NOT END A TWO-THOUSAND-REQUEST CRAWL. `size_cell`
    # raises when a cell's page 1 does not arrive or publishes no paginator, and
    # letting that propagate would discard fifty-five sized cells over one — the
    # same reasoning `pagewalk` applies to a dead page and `snapshotcrawl` to a page
    # it cannot store. The cell is NAMED instead, contributes nothing to
    # `declared_sum`, and therefore shows up as an exhaustiveness deficit rather
    # than as a smaller directory.
    sizes: list[CellSize] = []
    unsized: list[tuple[str, str]] = []
    for cell in plan:
        try:
            sizes.append(size_cell(fetch, partition, base_url, cell))
        except Exception as exc:
            unsized.append((cell.label, f"{type(exc).__name__}: {exc}"))

    # DECLARED ONCE, AFTER SIZING, AND THAT IS WHY IT CAN BE A COUNT. Every cell
    # has published its own page count by now, so the frontier is arithmetic
    # rather than an estimate: the pages, in every locale, plus one witness each.
    declare_frontier(fetcher, sum(size.last_page * len(partition.locales) + 1
                                  for size in sizes))

    outcomes: list[CellOutcome] = []
    newly_sighted = 0
    for size in sizes:
        attempts: list[Attempt] = []
        # ONE ATTEMPT FOR A CELL TOO BIG TO WITNESS. See RETRY_PAGE_CEILING: a
        # second read of a 235-page cell buys ids it already has and no proof.
        allowed = 1 if size.last_page > retry_page_ceiling else max_attempts
        for number in range(1, allowed + 1):
            attempt = _read_cell(
                conn, partition, base_url, size, fetch=fetch,
                run_ref=f"{run_ref}-{size.cell.label}-a{number}")
            attempts.append(attempt)
            # WRITTEN PER ATTEMPT, not once at the end — the same reasoning
            # `snapshotcrawl` applies to a page and `sweep_muqawil` to a pass. A
            # crawl killed in cell forty leaves thirty-nine cells of sightings.
            newly_sighted += record_sightings(conn, dataset_key, attempt.ids,
                                              run_ref=attempt.run_ref)
            if attempt.witnessed and attempt.distinct == size.declared:
                break
        outcome = CellOutcome(size=size, attempts=tuple(attempts))
        outcomes.append(outcome)
        if on_cell is not None:
            on_cell(outcome)

    at_end = size_cell(fetch, partition, base_url) if resize_at_end else None
    notes: list[str] = []
    above = [size.cell.label for size in sizes if size.last_page > retry_page_ceiling]
    if above:
        notes.append(
            f"{len(above)} cell(s) were above the {retry_page_ceiling}-page witness "
            f"ceiling and were read once without a retry: {', '.join(above)}. "
            "Their ids count; their completeness is not claimed.")
    if unsized:
        notes.append(
            f"{len(unsized)} cell(s) could not be sized and were NOT READ: "
            + "; ".join(f"{label} ({why})" for label, why in unsized))
    return PartitionOutcome(whole=whole, cells=tuple(outcomes),
                            whole_at_end=at_end, newly_sighted=newly_sighted,
                            unsized=tuple(unsized), notes=tuple(notes))
