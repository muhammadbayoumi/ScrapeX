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

TWO PROOFS, AND THE SECOND ONE IS A CORRECTION OF THIS FILE'S FIRST CLAIM.

  * THE WITNESS PROOF — page 1 returns the same id sequence after the read, so the
    generation never rolled, so the pages were disjoint and one pass covered the
    cell.
  * THE COUNTING PROOF — `|distinct| == N`. A cell that declares N rows cannot show
    N DISTINCT ids unless it has shown all of them, and the ids may be accumulated
    over any number of reads.

**This module originally said the union "can reach N by luck … and that proves
nothing", and required the witness. That was wrong.** There is no luck in it: every
id came off that cell's own filtered pages, so the cell contains at least the
distinct ids seen, and it declares exactly N. Both proofs rest on the SAME
assumption — that the paginator's N is true — and the witness adds no completeness
that the count does not.

The error was not free. It made the six cells measured above the 31-page ceiling
unprovable **by construction** — no single read of them can hold one generation — so
the first real run reported a 3,690 deficit with no route to close it. The counting
proof is the route, and `HEAVY_ATTEMPTS` is how far it is pursued.

WHAT THE WITNESS STILL EARNS. It says a cell was closed in ONE pass rather than
several, which is the difference between 12 requests and 120; it detects the
generation rolling, which is how a cell is known to be too big; and it is the only
check that would notice a paginator declaring FEWER rows than the cell holds, since a
too-small N makes the count agree for the wrong reason.

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
import threading
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from .connectors.base import declare_frontier
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

#: How many reads a cell ABOVE that ceiling is allowed, so the counting proof has a
#: chance to close it. MODELLED, and the model is the one the blind sweep validated:
#: a pass over a cell read across generations sees about `N(1 − 1/e)` of it, so the
#: expected unseen after `k` passes is `N·e^(−k)`. It predicted 42.9 unseen after six
#: passes where the sweep observed 38.
#:
#: Ten gives an expected unseen below 1 for the worst cell measured — `region_id=1 ×
#: verysmall`, 4,704 rows: `4704·e^(−10) ≈ 0.2`. It also bounds the cost: ten reads of
#: a 236-page cell is 2,360 requests, which is why this is a CEILING on effort and not
#: a loop that runs until it succeeds. A cell that has not closed in ten reads reports
#: its deficit, which is the honest outcome and the input to a finer partition.
HEAVY_ATTEMPTS = 10

#: Consecutive reads that add NOT ONE new id before a cell is left alone. `N.e^(-k)`
#: says the returns fall away; this is where they are measured instead of assumed.
#:
#: MEASURED ON THE OWNER'S OWN CRAWL, 2026-08-21, which is why this exists. The
#: residual run fetched **7,898 pages** against the first crawl's 1,982, and the ids
#: it found per hour went
#:
#:     1,125 -> 459 -> 50 -> 7 -> 1 -> 902 -> 87 -> 2
#:
#: and then **43 minutes of continuous fetching produced zero**. `HEAVY_ATTEMPTS` is a
#: fixed count, so a cell that had converged kept being read until its allowance ran
#: out. Two dry reads is the evidence that the tail has been reached.
#:
#: TWO AND NOT ONE, because a single dry read is not evidence. A cell is a randomised
#: ordering: one pass can legitimately repeat a previous pass's rows and the next can
#: still surface new ones. Two in a row is the cheapest number that is not noise.
DRY_ATTEMPTS = 2


class NotASubdivision(ValueError):
    """The cells handed in are not all inside the parent they claim to subdivide.

    REFUSED RATHER THAN AUDITED, and this is the one refusal in this module that
    survives: it is about the ARITHMETIC, not about configuration. The nested audit's
    whole claim is
    `Sum N_child == N_parent`, and a child that dropped one of the parent's
    filters is measured over a different, larger set. Such a run could report a
    zero deficit while covering none of the parent — a completeness claim that is
    false rather than merely weak, and the one failure this module is built to
    make impossible.
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

    #: Matches `source_site.site_key`, which is how the crawl finds its scope.
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
    #: The cell, sized again after it was read. `None` when it was not asked.
    #:
    #: WHY A CELL NEEDS ITS OWN RE-SIZE AND NOT JUST THE LISTING'S. On the first real
    #: run three cells finished one or two ids short — `235 of 236`, `148 of 149`,
    #: `405 of 413` — and nothing could say whether a contractor had been MISSED or
    #: had LEFT. The listing shrank by 25 rows that same night, so departure was the
    #: likelier explanation and there was no way to prefer it. One request per cell
    #: settles it, and a deficit that turns out to be churn is not a gap to go
    #: hunting for.
    size_at_end: CellSize | None = None

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
        """The attempt that proves this cell complete by the WITNESS, if one did."""
        for attempt in self.attempts:
            if attempt.witnessed and attempt.distinct == self.size.declared:
                return attempt
        return None

    @property
    def departures(self) -> int:
        """How many rows the cell LOST between being sized and being re-sized.

        A deficit no larger than this is churn rather than a gap: the cell declared
        `N` when it was measured and holds fewer now, so ids counted against the
        original `N` were never all there to be read.
        """
        if self.size_at_end is None:
            return 0
        return max(0, self.size.declared - self.size_at_end.declared)

    @property
    def deficit_is_churn(self) -> bool:
        """Whether this cell's shortfall is fully explained by rows leaving it."""
        return (not self.provably_complete
                and 0 < self.observed_deficit <= self.departures)

    def went_dry(self, dry_attempts: int = DRY_ATTEMPTS) -> bool:
        """Did this cell stop because its last reads returned nothing new?

        DERIVED FROM THE ATTEMPTS RATHER THAN RECORDED, so it cannot disagree with
        them — the same reasoning `provably_complete` follows. A cell that stopped on
        a proof is not dry, however much its last read repeated: the proof is the
        reason it stopped and saying otherwise would misreport why.
        """
        if self.provably_complete or len(self.attempts) <= dry_attempts:
            return False
        union: set[str] = set()
        gains = []
        for attempt in self.attempts:
            fresh = set(attempt.ids)
            gain = len(fresh - union)
            union |= fresh
            # ONLY ATTEMPTS THAT ASKED THE SITE COUNT, which is the same rule the
            # loop applies and has to be: this property describes that decision and
            # would otherwise contradict it. A resumed attempt has its stored pages
            # removed before the fetch and its ids recovered off disk, so it returns
            # exactly what the previous one did — zero gain by construction.
            if attempt.pages_read > 0:
                gains.append(gain)
        if len(gains) <= dry_attempts:
            return False
        return all(gain == 0 for gain in gains[-dry_attempts:])

    @property
    def counted_complete(self) -> bool:
        """THE SECOND PROOF, AND THE ONLY ONE AVAILABLE TO A HEAVY CELL.

        A cell that declares `N` rows cannot show `N` DISTINCT ids unless it has
        shown all of them. That is a complete proof of coverage and it needs no
        generation, no witness, and no single pass — the ids may be accumulated
        across any number of reads.

        WHY THIS WAS MISSING, and it is a correction rather than an addition.
        `provably_complete` originally required the witness AND the count, which is
        stricter than the logic needs and is exactly the wrong constraint for the six
        cells measured above the 31-page ceiling on 2026-08-21: those can never hold
        one generation, so under the old rule they were unprovable **by
        construction**, and the method reported a 3,690 deficit it had no route to
        close. The counting proof is the route.

        WHAT THE WITNESS STILL EARNS, so it is not now redundant: it proves the pages
        were DISJOINT, which is what makes `distinct == declared` reachable in a
        single pass instead of by repetition — and it is the only check that would
        notice a paginator declaring fewer rows than the cell holds, because a
        too-small `N` makes the count agree for the wrong reason.
        """
        return bool(self.attempts) and len(self.ids) == self.size.declared

    @property
    def provably_complete(self) -> bool:
        """Either proof suffices, and the report says which one carried it."""
        return self.proof is not None or self.counted_complete

    @property
    def proof_kind(self) -> str:
        if self.proof is not None:
            return "witness"
        if self.counted_complete:
            return "count"
        return ""

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
            verdict = (f"COMPLETE, D=0 over {self.size.declared:,} "
                       f"[by {self.proof_kind}]")
        elif self.deficit_is_churn:
            verdict = (f"{len(self.ids):,} of {self.size.declared:,}, "
                       f"D={self.observed_deficit:,} — and the cell LOST "
                       f"{self.departures:,} row(s) while it was read, which accounts "
                       "for it: nothing was missed")
        else:
            verdict = (f"{len(self.ids):,} of {self.size.declared:,}, "
                       f"D={self.observed_deficit:,}")
        return (f"{self.size.cell.label}: {verdict} "
                f"[{len(self.attempts)} attempt(s), {self.requests} requests]")


@dataclass(frozen=True)
class PartitionOutcome:
    """What the whole partition read, and what it can and cannot claim."""

    #: THE SCOPE THIS RUN AUDITS AGAINST, sized before the first cell. The
    #: unfiltered listing for a top-level run; the PARENT CELL for a nested one.
    #: Named `whole` because it is the whole of whatever is being accounted for,
    #: and `parent` below says which — read the two together, never this alone.
    whole: CellSize
    cells: tuple[CellOutcome, ...] = ()
    #: The scope, sized again at the end. `None` if it was not asked.
    whole_at_end: CellSize | None = None
    #: The cell being subdivided. `WHOLE` for a top-level run, and then `whole`
    #: above is the unfiltered listing and a completeness claim is site-wide.
    #: Anything else means every claim here is ABOUT THAT CELL ONLY.
    parent: Cell = WHOLE
    #: Ids recorded into `dataset_sighting`, cumulatively, as the run went.
    newly_sighted: int = 0
    #: Cells whose OWN PAGINATOR could not be read, with why. They were not read at
    #: all, so they contribute nothing to `declared_sum` — which is what makes them
    #: show up as an exhaustiveness deficit rather than vanish. Kept as a field and
    #: not merely a note because `provably_complete` has to see them.
    unsized: tuple[tuple[str, str], ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def nested(self) -> bool:
        """Is this a subdivision of ONE cell rather than a run over the listing?"""
        return bool(self.parent.params)

    @property
    def scope(self) -> str:
        """What every number here is about, in words fit for a report line."""
        return f"cell {self.parent.label}" if self.nested else "listing"

    @property
    def declared_sum(self) -> int:
        return sum(cell.size.declared for cell in self.cells)

    @property
    def exhaustiveness_deficit(self) -> int:
        """`N_scope − Σ N_cell`. Above zero means rows in NO cell — the case that
        makes a partition method unsound, counted rather than assumed away. On
        muqawil it was 1,437 until `region_id=0` was found to address exactly
        them.

        NESTED, THIS IS THE WHOLE OF REQ-21: `Σ N_child` against `N_parent`, so a
        subdivision chosen from incomplete evidence says by HOW MUCH it is
        incomplete instead of being trusted. Measured on the worst cell, the 48
        city cells derived from two thirds of the contractors declared 4,665
        against the parent's 4,697 — a deficit of 32, which is 0.68% and is
        NAMED rather than lost. A subdivision is an optimisation; the parent
        remains the fallback and the counting proof on it needs no child list.
        """
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
        """How the listing's size MOVED while the crawl ran. `0` if not re-sized.

        SIGNED, AND IT GOES BOTH WAYS — which the first real run proved and the first
        wording denied. This was called "how much the listing grew", and the report
        said *"the listing grew by -25 rows"*, because a directory can shrink: over
        the night of 2026-08-20 it went 17,417 → 17,392 as twenty-five contractors
        left. A number named for one direction hides the other, and a departure is
        the more interesting event of the two — it is the reason a cell can end one
        id short of its own declared count without anything having been missed.
        """
        if self.whole_at_end is None:
            return 0
        return self.whole_at_end.declared - self.whole.declared

    @property
    def provably_complete(self) -> bool:
        """Every cell proven, and no row outside every cell — WITHIN `parent`.

        IT IS A CLAIM ABOUT `scope` AND NEVER MORE. True on a nested run means
        the parent cell is fully accounted for; it says nothing whatever about
        the rest of the listing. `__str__` spells that out, because `True` read
        off this property alone is the one way this method could mislead.

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

    @property
    def sizing_requests(self) -> int:
        """Requests that MEASURED and stored nothing — the ones a resume pays twice.

        THIS NUMBER ONLY EVER EXISTED IN A DOCSTRING, which is the defect this closes.
        The module header above states the price of sizing-before-storing — *"the first
        ~112 requests store nothing … ~5.7% overhead on each resume"* — and somebody
        running the command never reads a module header.

        WORSE, `~112` IS A MEASUREMENT OF ONE SITE ON ONE DAY. It moves with the
        partition: a source with 12 cells or 500 pays something else entirely, and a
        constant written into prose cannot follow it. So this is computed from what the
        run actually paid, and `__str__` prints it.

        That is the checklist item taking its second branch on purpose — *"make sizing
        resumable, OR state its cost in the tool's own output"*. Making it resumable
        changes what the progress denominator MEANS, because the frontier is declared
        once after sizing and that is what makes it a count rather than an estimate.
        Stating the cost only stops hiding a number.
        """
        return self.whole.requests + sum(cell.size.requests for cell in self.cells) \
            + (self.whole_at_end.requests if self.whole_at_end else 0)

    def __str__(self) -> str:
        proven = sum(1 for cell in self.cells if cell.provably_complete)
        lines = [
            f"{self.scope} declared {self.whole.declared:,} rows over "
            f"{self.whole.last_page} pages",
            f"partition declared {self.declared_sum:,} over {len(self.cells)} cells "
            f"— exhaustiveness deficit {self.exhaustiveness_deficit:,}",
            f"distinct ids seen {len(self.ids):,} — D = {self.deficit:,}",
            f"cells proven complete {proven} of {len(self.cells)}",
            f"requests {self.requests:,}",
        ]
        if self.sizing_requests:
            share = self.sizing_requests / self.requests if self.requests else 0.0
            lines.append(
                f"  of those, {self.sizing_requests:,} ({share:.1%}) sized cells and "
                "stored nothing — a resumed run pays them again, because sizing is "
                "not resumable. `--plan` pays them once, on purpose, and prints them")
        if self.provably_complete and self.nested:
            lines.append(
                f"PROVABLY COMPLETE FOR {self.scope} — AND FOR THAT CELL ONLY. It "
                "says nothing about the rest of the listing, which still needs its "
                "own accounting; this run subdivided one cell and proved that cell.")
        elif self.provably_complete:
            lines.append(
                "PROVABLY COMPLETE for the listing as published. This is a claim "
                "about what the listing PUBLISHES and never about every "
                "contractor the site knows.")
        else:
            lines.append(
                f"NOT proven complete for {self.scope}. The deficit above is a "
                "floor on what is missing, not an estimate of it.")
        if self.arrivals > 0:
            lines.append(
                f"and the {self.scope} GREW by {self.arrivals:,} rows while this "
                "ran, so "
                "the claim is 'complete as of the start, with those deferred'")
        elif self.arrivals < 0:
            lines.append(
                f"and the {self.scope} SHRANK by {-self.arrivals:,} rows while "
                f"this ran "
                f"({self.whole.declared:,} -> {self.whole_at_end.declared:,}), so a "
                "cell ending one or two short of its declared count may have lost a "
                "contractor rather than missed one")
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

    def detail_rows(self, page):
        """FORWARDED, and forgetting to would have been silent.

        This wrapper exists to hide already-stored listing URLs from a resume, and
        every other method of the source is delegated. A `detail_rows` that was NOT
        delegated would make `slice_rows` fall through to its `enumerate` default and
        reinstate exactly the off-by-a-locale pairing this method was added to remove —
        for the wrapped source only, which is the one production actually uses.
        """
        return self._inner.detail_rows(page)

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
               run_id: int | None = None,
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
        pace_s=0, fetcher=None, run_ref=run_ref, run_id=run_id,
        # THE LISTING PHASE, DECLARED. This crawl's whole product is a proof about the
        # LISTING — the witness compares id sequences and the count compares distinct
        # against declared — and a detail page takes part in neither. Without saying so,
        # a registered `listing_plus_slice` made the walker ask `belongs_to_slice` about
        # listing rows mid-run: measured 2026-08-21, four cells closed with D=0 and the
        # fifth ended on one card that publishes no city.
        listing_phase_only=True)

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


def _crawl_one_cell(size: CellSize, *, conn: sqlite3.Connection,
                    partition: PartitionedListing, base_url: str, fetch: Fetch,
                    run_ref: str, dataset_key: str, max_attempts: int,
                    heavy_attempts: int, dry_attempts: int, run_id: int | None = None,
                    retry_page_ceiling: int, resize_cells: bool
                    ) -> tuple[CellOutcome, int]:
    """One cell, read until it is proven, counted out, or dry.

    LIFTED OUT OF THE LOOP SO IT CAN RUN IN A WORKER, and it took no rewriting to
    do it: a cell was already self-contained, which is the same property that makes
    each one provable on its own. It touches `conn` and nothing else shared, so a
    worker with its own connection has no shared state at all.

    Returns the outcome and how many ids were newly sighted, because the caller adds
    those up and a worker cannot.
    """
    attempts: list[Attempt] = []
    newly_sighted = 0
    # A HEAVY CELL GETS ITS RETRIES BACK, and that is the whole point of the
    # counting proof. `RETRY_PAGE_CEILING` used to cut such a cell to ONE
    # attempt, on the reasoning that a second read "buys ids it already has and
    # no proof" — true of the witness, false of the count. Measured 2026-08-21:
    # the six cells above the ceiling were read once each and left a deficit of
    # 3,680 with no route to close it. Accumulating distinct ids IS the route,
    # so the ceiling now decides how many reads a cell is ALLOWED, not whether
    # it gets more than one.
    allowed = (heavy_attempts if size.last_page > retry_page_ceiling
               else max_attempts)
    union: set[str] = set()
    dry = 0
    for number in range(1, allowed + 1):
        attempt = _read_cell(
            conn, partition, base_url, size, fetch=fetch,
            run_ref=f"{run_ref}-{size.cell.label}-a{number}", run_id=run_id)
        attempts.append(attempt)
        # WRITTEN PER ATTEMPT, not once at the end — the same reasoning
        # `snapshotcrawl` applies to a page and `sweep_muqawil` to a pass. A
        # crawl killed in cell forty leaves thirty-nine cells of sightings.
        newly_sighted += record_sightings(conn, dataset_key, attempt.ids,
                                          run_ref=attempt.run_ref)
        # `ids` IS A TUPLE, not a set: it is the PUBLISHED ORDER with
        # duplicates kept, because that is what the witness compares. The
        # conversion is here rather than in `Attempt` for that reason.
        fresh = set(attempt.ids)
        gained = len(fresh - union)
        union |= fresh
        # STOP ON EITHER PROOF. Witnessed-and-counted ends it in one pass; the
        # union reaching the declared count ends it however many it took.
        if attempt.witnessed and attempt.distinct == size.declared:
            break
        if len(union) == size.declared:
            break
        # AND STOP WHEN THE READS GO DRY, which is the third reason and the one
        # that was missing. Counted from the SECOND attempt: the first cannot be
        # dry, since an empty union means everything it read was new.
        dry = dry + 1 if number > 1 and gained == 0 else 0
        if dry >= dry_attempts:
            break
    # RE-SIZED ONLY WHEN IT MATTERS. One request a cell over 56 cells is 56
    # requests spent to explain a deficit most cells do not have, so it is asked
    # for exactly the cells that fell short.
    seen_here = {one for a in attempts for one in a.ids}
    at_end = None
    if resize_cells and len(seen_here) != size.declared:
        try:
            at_end = size_cell(fetch, partition, base_url, size.cell)
        except Exception:
            # Failing to explain a deficit is not a reason to lose the cell.
            at_end = None
    return (CellOutcome(size=size, attempts=tuple(attempts), size_at_end=at_end),
            newly_sighted)


def _run_and_close(body, index, size, connect) -> None:
    """Open a connection IN THIS THREAD, run one cell on it, and close it.

    THE FACTORY IS PASSED, NOT A CONNECTION, and the first attempt got that wrong:
    calling `connect()` on the submitting thread and handing the result to a worker
    raises `SQLite objects created in a thread can only be used in that same thread`
    — on the `close()`, after the cell had already been crawled. So the connection is
    created here, inside the worker, which is the only thread that will touch it.

    CLOSED IN A `finally`, because a pool that leaks one connection per cell leaks
    fifty-six over a crawl, and on Windows an unclosed SQLite handle keeps the `-wal`
    file alive after the process believes it is done.
    """
    worker_conn = connect()
    try:
        body(index, size, worker_conn)
    finally:
        worker_conn.close()


def crawl_partition(conn: sqlite3.Connection, partition: PartitionedListing,
                    base_url: str, *, fetch: Fetch, run_ref: str,
                    dataset_key: str, run_id: int | None = None,
                    cells: Sequence[Cell] | None = None,
                    parent: Cell = WHOLE,
                    max_attempts: int = 2,
                    heavy_attempts: int = HEAVY_ATTEMPTS,
                    dry_attempts: int = DRY_ATTEMPTS,
                    workers: int = 1,
                    connect: Callable[[], sqlite3.Connection] | None = None,
                    retry_page_ceiling: int = RETRY_PAGE_CEILING,
                    fetcher: object | None = None,
                    resize_at_end: bool = True,
                    resize_cells: bool = True,
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

    `workers` CRAWLS CELLS CONCURRENTLY, and it needs `connect` because each worker
    must have its own `sqlite3` connection — one is refused across threads. Default
    1, so nothing changes for a caller that does not ask.

    WHAT IT BUYS AND WHAT IT MUST NOT. muqawil answers in about six seconds while
    the pace is one request a second, so the wall clock is latency and not
    politeness: overlapping the waits is the whole win. It does NOT raise the rate —
    `HttpFetcher._throttle` holds a lock across its sleep, and without that lock,
    measured on 2026-08-21, four workers made twenty requests in 1.02 s where 3.80 s
    was owed. Concurrency without that fix would have quadrupled the real request
    rate against a live site and called itself a speedup.

    A CELL IS LEFT ALONE FOR THREE REASONS, not one: it was witnessed and counted;
    its union reached the declared count; or `dry_attempts` consecutive reads added
    not one new id. The third is `DRY_ATTEMPTS`, and it exists because the owner's
    residual crawl fetched 7,898 pages — four times the first crawl's 1,982 — to
    find nothing in its last 43 minutes. An allowance is not a stopping rule.

    THIS IS THE LISTING PHASE AND IT CANNOT BE ANYTHING ELSE, which is why it no
    longer asks `source_site.crawl_scope` for permission. `listing_phase_only=True`
    goes to the walker unconditionally below, and the walker short-circuits on that
    flag before it reads the scope -- so a detail page cannot be fetched from here
    under any registration. `test_the_listing_phase_fetches_no_detail_page_under_any_scope`
    asserts that over all three scopes, which is the property the old
    `ScopeNotPartitionable` refusal was standing in for.

    IT REFUSED `full_then_listing` UNTIL 2026-09-02, and the reason it gave --
    "would fetch twenty profile pages for every listing page it read" -- was already
    impossible when it was written down. What the refusal actually did was leave that
    scope's own second phase, the "then the listing catches the changes" half of its
    name, with no way to run: the only route offered was editing the row and editing
    it back, because the detail crawl reads the same column.

    `parent` IS THE NESTED AUDIT, AND IT IS ONE SIZING REQUEST. Every number this
    returns is measured against `parent`: pass `WHOLE` (the default) and the
    accounting is against the unfiltered listing exactly as before; pass a cell
    and `Σ N_child` is compared against THAT CELL's declared count instead.
    Without it a subdivision could only be audited against the whole listing —
    running the 151 city cells of one region would have compared them to 17,414
    and reported a deficit of thirteen thousand rows that were never in scope, a
    number so wrong it would have to be ignored, which is how a check stops being
    one. The cells must actually lie inside `parent` or this raises
    `NotASubdivision`.
    """
    # READ FOR THE REGISTRATION, NOT FOR PERMISSION. `read_scope` raises
    # `SiteNotRegistered` for a site nobody has decided about, and that check is worth
    # keeping: a crawl that picked the default would be answering for the owner. The
    # scope VALUE is not this function's business -- see `_the_listing_phase_only` in
    # the docstring above.
    read_scope(conn, partition.site_key)

    plan = tuple(cells) if cells is not None else partition.cells()

    # CHECKED BEFORE A SINGLE REQUEST IS SPENT. The alternative is discovering it
    # after hours of fetching, and the cost of the check is a set comparison.
    outside = [cell.label for cell in plan if not cell.is_under(parent)]
    if outside:
        raise NotASubdivision(
            f"{len(outside)} of {len(plan)} cell(s) are not inside "
            f"{parent.label!r}, so `Σ N_child == N_parent` would be measured over "
            f"a different set than the parent: {', '.join(outside[:6])}"
            + (f" and {len(outside) - 6} more" if len(outside) > 6 else "")
            + ". A subdividing cell must carry every one of the parent's filters.")

    whole = size_cell(fetch, partition, base_url, parent)

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

    per_cell = {
        "partition": partition, "base_url": base_url, "fetch": fetch,
        "run_ref": run_ref, "dataset_key": dataset_key, "run_id": run_id,
        "max_attempts": max_attempts, "heavy_attempts": heavy_attempts,
        "dry_attempts": dry_attempts, "retry_page_ceiling": retry_page_ceiling,
        "resize_cells": resize_cells}
    newly_sighted = 0
    found: dict[int, CellOutcome] = {}
    # ONE LOCK FOR THE CALLBACK AND THE COUNTER, so `on_cell` does not have to be
    # thread-safe. A caller's progress reporter writes to a log and a dict; making
    # every caller learn that is how a convenience becomes a defect.
    guard = threading.Lock()
    # SET BY THE FIRST CELL TO RAISE, AND READ BY EVERY CELL THAT HAS NOT STARTED.
    # `ThreadPoolExecutor.__exit__` calls `shutdown(wait=True)` without
    # `cancel_futures`, so every cell already submitted RUNS even after a worker has
    # raised -- and `on_cell` is where a caller asks whether the run may continue.
    # Measured on the shape of the 2026-09-03 job: a pause requested at cell 3 of 56
    # would have fetched the remaining 53 before the `CrawlStopped` raised by cell 3
    # was re-raised below. That is a pause that crawls the whole site.
    #
    # THE SEQUENTIAL PATH NEVER HAD THIS, which is why it went unnoticed: `raise` from
    # `on_cell` leaves the `for` loop and no further cell is read.
    #
    # ANY EXCEPTION, NOT ONLY A STOP. `future.result()` re-raises the first one and the
    # `PartitionOutcome` is discarded either way, so the queued cells were going to be
    # fetched and thrown away.
    stopping = threading.Event()

    def one(index: int, size: CellSize, worker_conn: sqlite3.Connection) -> None:
        nonlocal newly_sighted
        if stopping.is_set():
            return
        try:
            outcome, sighted = _crawl_one_cell(size, conn=worker_conn, **per_cell)
            with guard:
                found[index] = outcome
                newly_sighted += sighted
                if on_cell is not None:
                    on_cell(outcome)
        except BaseException:
            stopping.set()
            raise

    if workers > 1 and connect is not None:
        # A CONNECTION PER WORKER, NOT A SHARED ONE. `sqlite3` refuses a connection
        # used from a thread it was not created on, and the alternative — one
        # connection behind a lock — would serialise the writes AND the reads that
        # sit between the fetches. Every connection sets `journal_mode=WAL` and
        # `busy_timeout=5000`, so concurrent writers wait for each other instead of
        # failing, which is the property that makes this safe.
        #
        # THE PACE IS STILL ONE REQUEST PER INTERVAL. `HttpFetcher._throttle` holds
        # a lock across its sleep, measured 2026-08-21 — without it four workers
        # made 20 requests in 1.02 s where 3.80 s was owed. The concurrency buys
        # OVERLAP on a six-second latency, never a higher rate.
        with ThreadPoolExecutor(max_workers=workers,
                                thread_name_prefix="cell") as pool:
            futures = [
                pool.submit(_run_and_close, one, index, size, connect)
                for index, size in enumerate(sizes)]
            for future in futures:
                future.result()        # re-raise anything a worker hit
    else:
        for index, size in enumerate(sizes):
            one(index, size, conn)

    # ORDERED BY THE PLAN, not by which worker finished first, so two runs of the
    # same partition produce the same report.
    outcomes: list[CellOutcome] = [found[i] for i in sorted(found)]

    # THE SAME SCOPE, so `arrivals` measures the movement of what was audited. A
    # nested run re-sizing the whole listing would report the site's churn as the
    # parent cell's, and then a child ending one short would be excused by a
    # departure that happened somewhere else entirely.
    at_end = size_cell(fetch, partition, base_url, parent) if resize_at_end else None
    notes: list[str] = []
    above = [size.cell.label for size in sizes if size.last_page > retry_page_ceiling]
    if above:
        notes.append(
            f"{len(above)} cell(s) were above the {retry_page_ceiling}-page witness "
            f"ceiling, so no single read of them can hold one cache generation and "
            f"the witness cannot carry them: {', '.join(above)}. They were read up to "
            f"{heavy_attempts} times each and closed by COUNTING instead — "
            "`distinct == declared` — or reported with the deficit they were left at.")
    if unsized:
        notes.append(
            f"{len(unsized)} cell(s) could not be sized and were NOT READ: "
            + "; ".join(f"{label} ({why})" for label, why in unsized))
    return PartitionOutcome(whole=whole, cells=tuple(outcomes),
                            whole_at_end=at_end, parent=parent,
                            newly_sighted=newly_sighted,
                            unsized=tuple(unsized), notes=tuple(notes))
