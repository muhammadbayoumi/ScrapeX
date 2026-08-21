"""The provable listing crawl of a DIRECTORY, and the interpretation of it.

WHY THIS FILE EXISTS AT ALL, and it is the finding rather than the feature. Every
piece of the pipeline that produced the warehouse is committed — `snapshotcrawl`,
`extract/muqawil.py`, `bilingual_listing_candidate`, `approve_candidate` — and
**not one of them had a caller in this repository.** `crawl_to_snapshots` had zero
production callers; `bilingual_listing_candidate` was reached only by tests. The
11,059 contractors on disk were produced by scratchpad scripts on ONE of the two
machines the owner works from, and the 2026-08-20 bilingual repair by another.
That is `CLAUDE.md`'s founding failure one level down: the code was committed and
the INVOCATION was not, so the other machine could read how it worked and could
not run it.

TWO PHASES, DELIBERATELY SEPARATE, which is `docs/GENERIC-FETCH-SEAM.md`'s central
rule and not a convenience:

    crawl    fetch every page and store it UNPARSED, plus every id seen
    approve  interpret the stored pages into rows, re-fetching NOTHING

A parse that turns out wrong then costs minutes instead of the whole crawl. It has
already paid for itself once: a defect in the bilingual merge was repaired from
disk on 2026-08-20 with nothing re-fetched.

  scrapex contractors --plan                       # 114 sizing requests
  scrapex contractors --crawl   --run-ref listing-2026-08-21
  scrapex contractors --approve --run-ref listing-2026-08-21

`--plan` FIRST, ALWAYS. It sizes all 56 cells and prints what the full crawl will
cost against today's live directory — about five minutes to find out, against
hours to discover it the other way. The owner warned the data is live before any
of this was measured, and the listing's last page has held 15, 2 and 13 cards on
three different readings.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
import time
from collections.abc import Iterator
from pathlib import Path

from . import validators as validator_store
from .connectors.base import HttpFetcher, declare_frontier
from .crawlscope import CrawlScope
from .databases import DatabaseRegistry
from .directories import Directory
from .directories import get as get_directory
from .extract import service
from .extract.models import ApprovalField, CandidateApproval, SnapshotCreate
from .features import FeatureKey, is_enabled
from .pagesource import FetchedPage, PageKind, slice_rows
from .partitioncrawl import (
    HEAVY_ATTEMPTS,
    RETRY_PAGE_CEILING,
    CellOutcome,
    crawl_partition,
    size_cell,
)
from .sightings import (
    coverage,
    departures,
    mark_unavailable,
    missing_ids,
    record_absences,
    sighted_ids,
    sighting_frequencies,
)
from .sites.muqawil import MuqawilPageSource
from .snapshotbody import decode, label_for
from .snapshotcrawl import already_stored, read_scope

# THE FOUR CONSTANTS THAT USED TO BE HERE were `BASE`, `DATASET`, `SITE_NAME` and
# a `MuqawilPartition()`, and they are why a second contractor directory would have
# needed a copy of this file (`REQ-27`). They now come from
# `scrapex/directories.py`, which is to this module what `connectors/factory.py` is
# to a products source.
LOG = Path.home() / ".scrapex" / "contractors.log"


def say(line: str) -> None:
    """One line to the console and to the log, and IT MAY NOT RAISE.

    THIS KILLED A RUN, which is why it is four lines instead of one. A Windows
    console defaults to cp1252, and `print("… -> …")` raises UnicodeEncodeError on
    U+2192 — a character this file had in one f-string. The sizing pass completed
    all 114 requests correctly and then died printing its own summary. On the crawl
    itself that is hours of fetching thrown away by a log line.

    Em-dash and «» survive because they ARE in cp1252; the arrow is not, and no
    reviewer would ever spot which of two similar punctuation marks is safe. So the
    stream is reconfigured to UTF-8 where it can be, and the write is guarded where
    it cannot: a log that cannot represent a character must lose the character, never
    the run.
    """
    try:
        print(line, flush=True)
    except UnicodeEncodeError:
        print(line.encode("ascii", "replace").decode("ascii"), flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def open_engine():
    """The live database, with the two-machine failure named if it bites.

    `DatabaseRegistry.defaults()` raises on a pointer written before the two
    databases were collapsed into one, and the message it raises is good. This
    adds what that message cannot know: the crawl about to run is hours long, so
    finding out here is worth a great deal more than finding out at cell forty.
    """
    try:
        registry = DatabaseRegistry.defaults()
    except Exception as exc:
        say(f"cannot open the warehouse: {exc}")
        raise SystemExit(2) from exc
    if not registry.engine.path.is_file():
        say(f"no database at {registry.engine.path}. A crawl into a database that "
            "does not exist yet would create an empty warehouse beside whatever "
            "the real one is — run 'scrapex database-status' first.")
        raise SystemExit(2)
    say(f"warehouse: {registry.engine.path}")
    return registry.engine.connect()


def make_fetch(pace_s: float):
    """One fetcher, and PACING LIVES HERE AND NOWHERE ELSE.

    `HttpFetcher` rate-limits with jitter, replays ETags so an unchanged page
    answers 304 with no body, honours `Retry-After` and breaks its own circuit
    after five refusals. `partitioncrawl` therefore adds no pace of its own: two
    layers would each charge for the wait, and a second per request over ~2,000
    requests is thirty-three minutes nobody chose to spend.
    """
    fetcher = HttpFetcher(min_interval_s=pace_s)

    def fetch(url: str) -> str:
        return fetcher.get(url).text

    return fetcher, fetch


# ---- --plan: what the crawl will cost, against today's live directory --------

def plan(directory: Directory, fetch, started: float) -> None:
    partition = directory.partition()
    whole = size_cell(fetch, partition, directory.base_url)
    say(f"listing now: {whole}")
    pages = 0
    declared = 0
    over = []
    sizing = whole.requests
    for cell in partition.cells():
        size = size_cell(fetch, partition, directory.base_url, cell)
        pages += size.last_page
        declared += size.declared
        sizing += size.requests
        if size.last_page > RETRY_PAGE_CEILING:
            over.append(size)
        say(f"  {size}")
    locales = len(partition.locales)
    requests = pages * locales + len(partition.cells()) * 3 + 2
    say("")
    # WHAT THIS COMMAND JUST SPENT, and the reason to print it is that `--crawl` now
    # names the same cost in its own report and points here. Every cell is sized before
    # any page is stored, and a resumed crawl pays that again because sizing is not
    # resumable — so `--plan` is the way to pay it once, deliberately, and read the
    # answer. A pointer to a cheaper route is worth nothing if the route never says
    # what it cost.
    say(f"this plan cost {sizing:,} request(s) sizing {len(partition.cells())} cells "
        f"and the listing; a crawl re-pays that, and this run has now measured it "
        f"rather than estimating it")
    say(f"cells {len(partition.cells())}  pages {pages} "
        f"(+{pages - whole.last_page} over the unfiltered {whole.last_page})")
    say(f"declared {declared:,} against the listing's {whole.declared:,} — "
        f"exhaustiveness deficit {whole.declared - declared:,}")
    say(f"locales {partition.locales} -> about {requests:,} requests for the crawl")
    # PRICED FROM THIS RUN'S OWN LATENCY, not from a number in a document. The
    # study measured 5.84 s a request; the sizing just made 100-odd requests, so
    # the honest estimate is the one it just paid for.
    #
    # AND THE DIVISOR IS NOW COUNTED RATHER THAN GUESSED. It was
    # `whole.requests + len(cells) * 2` — two requests per cell, assumed. `size_cell`
    # reports what each one actually cost, and a cell that needed a third probe made
    # the old divisor too small, which inflated the seconds-per-request and every hour
    # figure derived from it. Same expression, real numerator and real denominator.
    per = (time.monotonic() - started) / max(1, sizing)
    say(f"measured {per:.2f} s a request just now -> about {requests * per / 3600:.1f} h")
    if over:
        say(f"{len(over)} cell(s) above the {RETRY_PAGE_CEILING}-page witness ceiling, "
            f"without a retry: {', '.join(s.cell.label for s in over)}")


# ---- --crawl: the partition, witnessed --------------------------------------

def crawl(conn, directory: Directory, fetch, fetcher, run_ref: str,
          max_attempts: int, only: str = "", heavy_attempts: int = HEAVY_ATTEMPTS,
          workers: int = 1, connect=None) -> None:
    """The partition, or NAMED CELLS OF IT.

    `--only` is what makes the residual addressable on its own, which
    `R-26` requires: the first run proved 47 of 56 cells, and a crawl that can only
    run the whole partition would re-read all 47 to reach the 9 that are open. It is
    matched on the cell LABEL — the same string the report prints and the run ref
    carries — so a cell can be copied straight out of the log into the next command.
    """
    partition = directory.partition()
    chosen = None
    if only:
        wanted = {name.strip() for name in only.split(",") if name.strip()}
        chosen = tuple(one for one in partition.cells() if one.label in wanted)
        unknown = wanted - {one.label for one in chosen}
        if unknown:
            # REFUSED, NOT IGNORED. A mistyped label would otherwise crawl fewer
            # cells than asked for and report success over the ones it did.
            raise SystemExit(
                f"--only names {sorted(unknown)}, which are not cells of this "
                f"partition. A label looks like "
                f"{partition.cells()[0].label!r}.")
        say(f"crawling {len(chosen)} named cell(s) of {len(partition.cells())}")

    total = len(chosen) if chosen is not None else len(partition.cells())
    done = {"cells": 0}

    def report(outcome: CellOutcome) -> None:
        done["cells"] += 1
        say(f"  [{done['cells']}/{total}] {outcome}")
        if not outcome.provably_complete:
            say(f"        {outcome.attempts[-1].note}")

    # ITEM 2, AND THE CALLER THAT NEVER EXISTED. `HttpFetcher` has kept every
    # response's ETag and replayed it on the next visit since it was written — its
    # docstring says so — but `remember_validators` and `validators()` had **zero
    # callers anywhere**, so the dict died with the process and every re-crawl asked
    # for full bodies for pages that had not changed. A capability with no caller is
    # a claim; this is the claim being made true.
    # GUARDED ON THE FETCHER, because `crawl_partition` already accepts
    # `fetcher=None` — it is optional for `declare_frontier` — and a crawl driven by
    # a plain callable has no validators to replay. Crashing on that would make the
    # conditional-request work a precondition for crawling at all, which is the
    # opposite of an optimisation.
    kept = validator_store.load(conn) if fetcher is not None else {}
    if kept:
        fetcher.remember_validators(kept)
        say(f"replaying {len(kept):,} conditional validator(s) — an unchanged page "
            "answers 304 with no body")

    say(f"crawl {run_ref} starting")
    outcome = crawl_partition(conn, partition, directory.base_url, fetch=fetch,
                              run_ref=run_ref,
                              dataset_key=directory.dataset_key,
                              max_attempts=max_attempts,
                              heavy_attempts=heavy_attempts, cells=chosen,
                              workers=workers, connect=connect,
                              fetcher=fetcher, on_cell=report)
    # KEPT AFTER THE CRAWL AND NOT DURING IT, deliberately: a validator is only
    # worth storing if the page it describes was actually read, and writing them per
    # page would put a commit between every fetch on a path that already has one.
    written = (validator_store.save(conn, fetcher.validators())
               if fetcher is not None else 0)
    say("")
    say(str(outcome))
    if written:
        saved = getattr(fetcher, "not_modified_count", 0)
        say(f"kept {written:,} validator(s) for the next crawl; this one was "
            f"answered 304 for {saved:,} page(s)")
    say("")
    mark_departures(conn, directory, outcome, run_ref)
    say(str(coverage(conn, directory.dataset_key)))


def mark_departures(conn, directory: Directory, outcome, run_ref: str) -> None:
    """Write down who left, but ONLY off the back of a proof.

    `OP-26`, RULED 2026-08-21: a delisted contractor becomes `unavailable`. The
    schema has offered that value since the table was created and **the whole chain
    had no caller** — not `record_absences`, which writes the one fact that cannot be
    recomputed, and not the status write that depends on it. So a contractor the
    directory removed kept `status='active'` with a frozen `last_seen_at`, which is
    indistinguishable from one this crawl did not reach.

    THE GATE IS THE POINT OF THIS FUNCTION. `record_absences` says its caller must
    guarantee the crawl was complete, because it cannot see that from inside. Here is
    that caller, and the guarantee is `outcome.provably_complete` — which already
    means every cell proven, none unsized, and no row outside every cell.

    AND `nested` IS CHECKED SEPARATELY BECAUSE `provably_complete` IS DELIBERATELY
    NARROWER THAN IT LOOKS. Its own docstring: *"IT IS A CLAIM ABOUT `scope` AND NEVER
    MORE"* — true on a nested run it means the PARENT CELL is accounted for and says
    nothing about the rest of the listing. Marking absences from a nested proof would
    delist every contractor outside that one cell.

    `--only` IS REFUSED BY THE SAME PROPERTY, AND THE TEST SAYS SO OUT LOUD. A subset
    run sizes the whole listing and sums only the cells it was given, so its
    `exhaustiveness_deficit` is the thousands of rows in the cells it skipped and
    `provably_complete` is False. That is the right answer arrived at indirectly, so
    it is asserted rather than assumed — an implicit safety property with no test is
    one refactor away from being gone.

    IT SAYS WHY IT DECLINED. A crawl that silently marked nothing would be
    indistinguishable from one that found no departures, and those are opposite facts.
    """
    if outcome.nested:
        say(f"departures not marked: this crawl proves {outcome.scope} only, and a "
            f"cell's proof says nothing about the rest of the listing")
        return
    if not outcome.provably_complete:
        say(f"departures not marked: the crawl is not provably complete "
            f"(deficit {outcome.deficit:,}, exhaustiveness "
            f"{outcome.exhaustiveness_deficit:,}). A partial crawl misses "
            f"contractors for its own reasons and marking those as gone would "
            f"delist them because the crawler had a bad afternoon")
        return

    proven = record_absences(conn, directory.dataset_key,
                            seen=outcome.ids, run_ref=run_ref,
                            id_field=directory.identity_field)
    marking = mark_unavailable(conn, directory.dataset_key,
                               id_field=directory.identity_field)
    say(f"the crawl is provably complete, so absence is evidence: "
        f"{proven:,} row(s) proved absent by {run_ref}")
    say(f"  {marking}")



# ---- --details: the profile frontier, built from disk ------------------------

#: A stored page is a LISTING if its path ends at `contractors`, with or without a
#: query. A profile carries the contractor id and the self-build tail after it.
#: Derived from the URL because `generic_page_snapshot` has no kind column —
#: `body_class` is chosen at write time to pick a compression dictionary and is not
#: kept.
_LISTING = re.compile(r"/(?:en|ar)/contractors(?:\?|$)")


def listing_pages(conn) -> Iterator[FetchedPage]:
    """Every listing page on disk, decoded, latest write per URL.

    **NO NETWORK, AND THAT IS THE POINT.** `docs/GENERIC-FETCH-SEAM.md` separates
    fetching from interpreting so that a wrong parse costs minutes. A frontier IS an
    interpretation, so it comes off the evidence rather than off the wire — rebuilding
    it by re-crawling 871 listing pages would cost an hour to learn what is on disk.

    IT IS ALSO WHY THIS FRONTIER SURVIVES A RESTART. `features.CRAWL_FRONTIER` is
    disabled for exactly one missing piece, persistent discovery, and discovery that
    reads stored snapshots persists because they do. It does not light that flag on its
    own: the flag covers the price side's frontier too.

    ACROSS EVERY RUN, NOT ONE. The question is *which contractors has the site ever
    shown us*, and one first seen three crawls ago still counts. A run ref scopes a
    RESUME, which is a different question and is asked separately below.
    """
    latest: dict[str, sqlite3.Row] = {}
    for row in conn.execute(
            "SELECT page_snapshot_id, source_url, html_content, html_codec, "
            "       html_dict_id "
            "  FROM generic_page_snapshot ORDER BY page_snapshot_id"):
        if _LISTING.search(row["source_url"]):
            # LAST WRITE WINS, the rule `_pairs` already follows: a retried cell stored
            # the same page twice and the later read is the current one.
            latest[row["source_url"]] = row
    for url, row in latest.items():
        yield FetchedPage(url=url, html=decode(conn, row), kind=PageKind.LISTING)


def _locale_of(url: str) -> str:
    """`en` or `ar`, from the path. The only two muqawil publishes.

    READ FROM THE URL because that is where the fact is: the crawl fetches
    `/en/contractors` and `/ar/contractors` as separate pages, so the locale is part of
    the identity of a stored snapshot rather than something to infer from its content.
    """
    for locale in ("en", "ar"):
        if f"/{locale}/" in url:
            return locale
    return "?"


def detail_frontier(conn, directory: Directory, scope: CrawlScope,
                    slice_of: str) -> tuple[list[str], int]:
    """The profile URLs this scope earns. Returns `(urls, rows_outside_the_slice)`.

    THE SCOPE COMES FROM THE DATABASE AND A CALLER MAY NOT PASS ONE.
    `site_profile.crawl_scope` is the owner's answer for this source
    (`PLATFORM-PLAN` Decision 23), and a scope enforced in two places is a scope
    enforced in neither.

    A SLICE ASKS EACH URL'S OWN ROW, through `slice_rows`. The reason is measured
    rather than defensive: muqawil yields one URL per LOCALE, so pairing by position
    asked the wrong card about every URL but the first and dropped the half that
    indexed past the last card.
    """
    source = MuqawilPageSource(last_page=1)
    wanted: list[str] = []
    outside = 0
    if scope is CrawlScope.FULL_THEN_LISTING:
        # OFF THE SIGHTING LEDGER, NOT OFF THE PAGES, and it is a 40x difference rather
        # than a tidy-up. `dataset_sighting` already holds every contractor id the site
        # has ever shown us — that is what it is for — so the full frontier is a SELECT.
        # Deriving it from the pages instead means decoding and BeautifulSoup-parsing
        # 14,727 stored listings, which took **over two minutes** and was still running
        # when it was killed; the ledger answers in well under a second.
        #
        # A SLICE STILL NEEDS THE PAGES, because the city is on the card and the ledger
        # holds ids alone. That asymmetry is the reason this is an `if` and not a
        # refactor of both paths onto one source.
        for contractor_id in sighted_ids(conn, directory.dataset_key):
            wanted.extend(source.profile_urls(directory.base_url, contractor_id))
        return list(dict.fromkeys(wanted)), 0
    # ONE PASS, KEPT PER LOCALE, AND THE LOCALE DECIDED AT THE END. A slice is named in
    # the language of the page — `MuqawilPageSource.belongs_to_slice` says so, and
    # measured against the committed fixtures: `RIYADH` matches 3 of 4 cards on the
    # English listing and **0 of 4** on the Arabic, and `الرياض` the reverse.
    #
    # So scanning every stored page against one slice value counts every row of the other
    # locale as *outside the slice* — a report that is simply false — and makes the whole
    # frontier depend on that locale's pages happening to be on disk. `R-39` records the
    # measurement; this is the code it asked for.
    #
    # ONE PASS AND NOT TWO, because the scan is the expensive half: a slice must parse
    # stored listing pages, and doing it twice to choose a locale first would double the
    # cost of the only frontier that cannot come off the ledger.
    per_locale: dict[str, tuple[list[str], int]] = {}
    for page in listing_pages(conn):
        locale = _locale_of(page.url)
        matched, missed = per_locale.setdefault(locale, ([], 0))
        # GROUPED BY ROW BEFORE ASKING, for two reasons that both matter.
        #
        # THE COUNT IS ABOUT ROWS. `slice_rows` yields one entry per URL and muqawil
        # publishes one URL per LOCALE, so asking per entry counted two skips for one
        # card — measured, a four-card page reported eight rows examined. "Rows outside
        # the slice" then meant nothing a reader could compare with the page.
        #
        # AND `belongs_to_slice` RE-PARSES THE PAGE EVERY CALL: it runs `_cards(html)`
        # from scratch, so asking twice per card is two full BeautifulSoup parses of the
        # same page for one answer. On the stored listing that doubling is the difference
        # this frontier already had to route around once.
        by_row: dict[int, list[str]] = {}
        for row_index, url in slice_rows(source, page):
            by_row.setdefault(row_index, []).append(url)
        for row_index, urls in by_row.items():
            if source.belongs_to_slice(page, row_index, slice_of):
                matched.extend(urls)
            else:
                missed += 1
        per_locale[locale] = (matched, missed)

    answered = {locale: pair for locale, pair in per_locale.items() if pair[0]}
    if len(answered) > 1:
        # A SLICE VALUE THAT MATCHES IN TWO LANGUAGES is either a name that happens to be
        # written the same way in both, or a marker that has moved. Either way the counts
        # below would be the sum of two different questions, so it is refused rather than
        # added up.
        raise ValueError(
            f"the slice {slice_of!r} matched rows in more than one locale "
            f"({sorted(answered)}), so 'outside the slice' has two different meanings. "
            "Name the slice in one language.")
    if not answered:
        # NOT AN ERROR, AND NOT SILENT EITHER. A city with no contractors is a real
        # answer; so is a slice named in the wrong language, and the caller's report says
        # how many rows were examined so the two can be told apart.
        return [], sum(missed for _, missed in per_locale.values())
    matched, outside = next(iter(answered.values()))
    wanted.extend(matched)
    # DEDUPLICATED HERE, NOT IN THE SOURCE. One contractor can appear on two stored
    # listing pages — a live listing reorders between requests, which is the entire
    # reason the witness compares id sequences — and fetching a profile twice is a
    # wasted request and a second snapshot of the same page.
    return list(dict.fromkeys(wanted)), outside


def details(conn, directory: Directory, fetch, fetcher, run_ref: str,
            ceiling: int = 0) -> None:
    """Fetch the profile pages the registered scope asks for, each stored as evidence.

    WHY THIS IS A PHASE OF ITS OWN AND NOT PART OF `--crawl`. The listing crawl is
    PROVABLE: it partitions, witnesses and counts, and its whole worth is the claim
    that it read everything the listing publishes. A profile crawl has no such theorem
    to offer — the frontier is a list, and reading a list proves nothing. Folding them
    together would also put a seventeen-hour walk behind the command somebody runs to
    check coverage.

    `--ceiling` EXISTS BECAUSE 34,806 PAGES IS ABOUT SEVENTEEN HOURS. A first run that
    only wants to see the shape of the data must be able to stop, and a run that
    stopped has to say so rather than look finished.
    """
    scope, slice_of = read_scope(conn, directory.key)
    say(f"registered scope: {scope.value}"
        + (f", slice {slice_of!r}" if slice_of else ""))
    if scope is CrawlScope.LISTING_ONLY:
        # NOT AN ERROR. The registration is his answer, and a command that fetched
        # profiles anyway would be answering for him — which is what Decision 23 made
        # the column for.
        say("listing_only, so there are no profile pages to fetch. Change "
            "site_profile.crawl_scope to ask for them.")
        return
    if scope is CrawlScope.LISTING_PLUS_SLICE and not slice_of.strip():
        _refuse(f"{directory.key} is registered listing_plus_slice and no slice is "
                "named, so there is nothing to select. Set site_profile.crawl_slice")

    frontier, outside = detail_frontier(conn, directory, scope, slice_of)
    held = already_stored(conn, run_ref)
    todo = [url for url in frontier if url not in held]
    resumed = len(frontier) - len(todo)
    say(f"frontier {len(frontier):,} profile page(s), read from disk with no network")
    if outside:
        say(f"  {outside:,} row(s) outside the slice, not fetched")
    if resumed:
        # COUNTED, NEVER SILENT: the difference is the hours a resume saved, and a
        # resume that says nothing is indistinguishable from a crawl that fetched
        # everything.
        say(f"  {resumed:,} already stored under {run_ref} — resuming")
    if ceiling and len(todo) > ceiling:
        todo = todo[:ceiling]
        say(f"  stopping at the {ceiling:,}-page ceiling, so this run is PARTIAL")
    declare_frontier(fetcher, len(todo))

    stored = failed = 0
    for number, url in enumerate(todo, start=1):
        try:
            html = fetch(url)
        except Exception as exc:
            # NOT RAISED. One dead profile out of thirty-four thousand must not discard
            # the rest — the walker's own rule — and a crawl that stops at the first
            # 404 of a seventeen-hour run is a crawl nobody can finish.
            failed += 1
            say(f"  [{number}/{len(todo)}] {url}: {type(exc).__name__}: {exc}")
            continue
        try:
            service.save_snapshot(conn, SnapshotCreate(
                source_url=url, html_content=html, crawl_run_ref=run_ref,
                body_class=label_for(url, PageKind.DETAIL)))
            conn.commit()
            stored += 1
        except Exception as exc:
            conn.rollback()
            failed += 1
            say(f"  [{number}/{len(todo)}] storing {url}: {type(exc).__name__}: {exc}")
        if number % 200 == 0:
            say(f"  [{number:,}/{len(todo):,}] stored {stored:,}, failed {failed}")
    say("")
    say(f"profiles stored {stored:,}, failed {failed}, resumed {resumed:,}")
    if len(todo) + resumed < len(frontier):
        say("PARTIAL: the ceiling stopped this run. The same --run-ref continues it.")

# ---- --coverage: what the warehouse knows about its own gaps ------------------

def report_coverage(conn, directory: Directory, not_seen_since: str) -> None:
    """Every coverage question this warehouse can answer, in one place.

    WHY THIS EXISTS: `missing_ids`, `sighting_frequencies` and `departures` had
    **zero callers between them**. They are the answer to "what are we missing", they
    were written for the 10001274 incident, and nothing ever asked them — which is
    the same defect as `crawl_to_snapshots` having no caller, one layer up. A
    capability with no caller is a claim.

    THE FOUR QUESTIONS ARE NOT THE SAME QUESTION, and the report keeps them apart
    because conflating them is how "we are missing 3,690" turns into a hunt for rows
    that were never lost:

        stored vs sighted   what the site showed us and we did not keep
        the frequencies     the capture-recapture sample itself
        departures          what we hold that the site stopped showing
        NEVER SEEN          not here at all — only the crawl's own D reaches those
    """
    say(str(coverage(conn, directory.dataset_key)))
    say("")

    frequencies = sighting_frequencies(conn, directory.dataset_key)
    if frequencies:
        say("how many ids the site showed us N times — the sample itself:")
        for times in sorted(frequencies):
            say(f"    seen {times:>2}x   {frequencies[times]:>7,}")
        say("  (kept as observations. Turning this into a population estimate is a "
            "statistical choice — Chao1 and Lincoln-Petersen disagree — and this "
            "module does not pick a school.)")
        say("")

    gap = missing_ids(conn, directory.dataset_key, limit=20)
    say(f"sighted and never stored: {len(gap)} shown (ordered by how often the site "
        "showed it — one seen six times and still unstored is a stronger signal "
        "than one glimpsed once)")
    if gap:
        say(f"    {', '.join(gap)}")
    say("")

    say(str(departures(conn, directory.dataset_key, not_seen_since=not_seen_since)))
    say("")
    say("AND WHAT NONE OF THIS REACHES: a contractor the site has never shown us. "
        "Only the crawl's own deficit D counts those, and membership 10001274 was "
        "that case — found because he knew the company, which does not scale.")


# ---- --approve: interpret what is on disk, re-fetching nothing ---------------

def _pairs(conn, run_ref: str) -> dict[str, dict[str, tuple[int, str]]]:
    """The stored pages of this run, grouped so each page's two locales meet.

    KEYED ON THE URL WITH THE LOCALE TAKEN OUT, so `en?region_id=1&page=7` and
    `ar?region_id=1&page=7` land together and nothing else does. Not on the
    snapshot's arrival order: the two locales of one page are two separate
    requests against a listing that reorders, so ordering by id pairs page 7's
    English with whatever Arabic page happened to be stored next.
    """
    # ESCAPED, BECAUSE `_` IS A LIKE WILDCARD. Every cell ref carries them —
    # `region_id_1-company_size_big` — and a run ref of the owner's choosing may
    # too. Unescaped, `--run-ref my_run` would also gather `myXrun`'s pages and
    # approve another run's evidence under this one's name.
    pattern = (run_ref.replace("\\", "\\\\").replace("%", "\\%")
               .replace("_", "\\_")) + "-%"
    found: dict[str, dict[str, tuple[int, str]]] = {}
    rows = conn.execute(
        "SELECT page_snapshot_id, source_url, html_content, html_codec, html_dict_id "
        "  FROM generic_page_snapshot WHERE crawl_run_ref LIKE ? ESCAPE '\\' "
        " ORDER BY page_snapshot_id", (pattern,))
    for row in rows:
        url = row["source_url"]
        for locale in ("en", "ar"):
            marker = f"/{locale}/contractors"
            if marker in url:
                key = url.replace(marker, "/contractors")
                # LAST ONE WINS. A retried cell stored the same page twice, in two
                # generations, and the later read is the one whose ids the crawl's
                # own witness was computed against.
                found.setdefault(key, {})[locale] = (
                    int(row["page_snapshot_id"]), decode(conn, row))
                break
    return found


def _approval(directory: Directory, candidate) -> CandidateApproval:
    """The owner's answer, every field text-typed, the directory's id the identity.

    TEXT FOR EVERYTHING, and it is not laziness: type inference over twenty rows
    of one page guesses `integer` for a rating that reads `4.5` on the next page,
    and the schema hash then differs per page and every approval after the first
    is refused. `listing_candidate` already declines to guess for the same reason.
    """
    return CandidateApproval(
        table_index=0, site_key=directory.key,
        site_display_name=directory.display_name,
        dataset_key=directory.dataset_key,
        dataset_name=directory.display_name,
        fields=[ApprovalField(field_key=one.field_key, display_name=one.source_name,
                              data_type="text",
                              identity=(one.field_key
                                        == directory.identity_field))
                for one in candidate.fields])


def approve(conn, directory: Directory, run_ref: str) -> None:
    pairs = _pairs(conn, run_ref)
    say(f"approve {run_ref}: {len(pairs)} page(s) on disk")
    made = 0
    recovered = 0
    reparsed = 0
    lonely = 0
    refused: list[tuple[str, str]] = []
    for key, halves in sorted(pairs.items()):
        english = halves.get("en")
        arabic = halves.get("ar")
        if english is None:
            # NOT APPROVED FROM ARABIC ALONE. The English label is the parser's
            # key and the Arabic value is taken by index from it; an Arabic-only
            # page has nothing to index against.
            lonely += 1
            continue
        if arabic is None:
            lonely += 1
        candidate = directory.candidate(english[1], arabic[1] if arabic else "")
        if not candidate.approvable:
            refused.append((key, candidate.warnings[0] if candidate.warnings else "?"))
            continue
        try:
            result = service.approve_candidate(
                conn, english[0], _approval(directory, candidate),
                candidate=candidate)
        except Exception as exc:
            conn.rollback()
            refused.append((key, f"{type(exc).__name__}: {exc}"))
            continue
        conn.commit()
        made += 1
        if result.get("recovered"):
            # ALREADY APPROVED AND IDENTICAL, so it wrote nothing — and since `R-40`
            # that is a claim about the ROWS and not just the request. The digest of
            # what the parser produced is compared against the digest the previous
            # ingestion stored, so this count now means "nothing had changed" rather
            # than the old "we did not look".
            recovered += 1
        elif result.get("reparsed"):
            # THE CASE DEC-10 EXISTED FOR. Same page, same schema, DIFFERENT values —
            # a parser that was corrected. It used to be indistinguishable from the
            # line above and wrote nothing at all.
            reparsed += 1
    say(f"approved {made} page(s): {recovered} unchanged and wrote nothing, "
        f"{reparsed} re-parsed with new values (DEC-10 / R-40); "
        f"{lonely} page(s) missing a locale half")
    for key, why in refused[:20]:
        say(f"  refused {key}: {why}")
    if len(refused) > 20:
        say(f"  … and {len(refused) - 20} more")
    say("")
    say(str(coverage(conn, directory.dataset_key)))


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """The flags, declared ONCE for two front doors.

    `scrapex contractors` and `python -m scrapex.contractors` must not drift into
    two different vocabularies for the same operation — the same reasoning
    `publish.workbook_tables` gives for being the one place that decides what an
    export contains (P1). A flag added here appears in both.
    """
    parser.add_argument("--source", default=None,
                       help="which directory to crawl, by site key. Defaults to "
                            "the only one this build has. A mistyped name is "
                            "REFUSED, never quietly replaced by the default")
    parser.add_argument("--plan", action="store_true",
                       help="size all 56 cells and price the crawl. Costs ~114 "
                            "requests and answers 'what will this cost today'")
    parser.add_argument("--crawl", action="store_true")
    parser.add_argument("--details", action="store_true",
                       help="fetch the PROFILE page of every contractor the "
                            "registered scope asks for. The frontier is built from "
                            "stored listing pages with no network; the scope comes "
                            "from site_profile.crawl_scope and never from a flag")
    parser.add_argument("--ceiling", type=int, default=0,
                       help="for --details: stop after this many profile pages. "
                            "34,806 pages is about seventeen hours, and a first run "
                            "that only wants the shape of the data should be able to "
                            "stop. A stopped run says PARTIAL and the same --run-ref "
                            "continues it")
    parser.add_argument("--coverage", action="store_true",
                       help="what the warehouse knows about its own gaps: stored "
                            "vs sighted, the frequency sample, sighted-and-never-"
                            "stored, and departures. Reads nothing from the network")
    parser.add_argument("--not-seen-since", default="",
                       help="for --coverage: a contractor stored and active whose "
                            "last sighting predates this is a DEPARTURE, but only "
                            "if the crawl covering it was provably complete. "
                            "Defaults to the newest sighting in the ledger")
    parser.add_argument("--approve", action="store_true",
                       help="interpret the stored pages of --run-ref into rows. "
                            "Re-fetches nothing")
    parser.add_argument("--run-ref", default="",
                       help="required for --crawl and --approve. Reused, it "
                            "RESUMES: pages this ref already stored are not "
                            "fetched again")
    parser.add_argument("--pace", type=float, default=1.0,
                       help="minimum seconds between requests, at the transport")
    parser.add_argument("--max-attempts", type=int, default=2,
                       help="reads of a cell before its witness is given up on")
    parser.add_argument("--only", default="",
                       help="crawl ONLY these cells, by label, comma-separated "
                            "(e.g. region_id_1-company_size_verysmall). This is how "
                            "the residual is closed without re-reading the cells "
                            "already proven — 47 of 56 on the first run")
    parser.add_argument("--workers", type=int, default=1,
                       help="crawl this many cells at once. The site answers in "
                            "about six seconds while the pace is one request a "
                            "second, so overlapping the waits is the win — the "
                            "RATE does not change, the transport still allows one "
                            "request per interval however many workers there are")
    parser.add_argument("--heavy-attempts", type=int, default=HEAVY_ATTEMPTS,
                       help="reads allowed to a cell too big to witness, so the "
                            "counting proof has a chance to close it")

def validate(args: argparse.Namespace) -> None:
    """Refuse an argument set that cannot mean anything, before any work starts.

    EXIT 2, WHICH IS WHAT `argparse` ITSELF USES for a usage error, so the shell
    sees the same code whichever front door was used. This is a function rather
    than two `parser.error` calls because the subcommand's parser is not the one
    that would have to raise it, and a usage error printed by the wrong parser
    prints the wrong usage line.
    """
    if not (args.plan or args.crawl or args.details or args.approve or args.coverage):
        _refuse("choose one of --plan, --crawl, --details, --approve or --coverage")
    if (args.crawl or args.details or args.approve) and not args.run_ref:
        _refuse("--crawl, --details and --approve need --run-ref: it is what makes an "
                "interrupted crawl resumable and what --approve reads")
    if args.ceiling and not args.details:
        # REFUSED RATHER THAN IGNORED. A ceiling silently dropped on the wrong phase
        # would let somebody believe a full crawl was bounded when it was not.
        _refuse("--ceiling applies to --details only")
    # THE SECOND CALLER `is_enabled` NEVER HAD, and the reason it belongs here rather
    # than beside the API routes: those are mounted on 127.0.0.1 so the slice can be
    # exercised and tested, and `is_enabled`'s docstring excludes them on purpose. This
    # is the SHIPPED COMMAND — `REQ-24` made it one — so it is a user-facing surface in
    # the same category as navigation, and a command that performs a capability the
    # manifest calls unavailable is the inflated claim the flag exists to stop.
    #
    # IT REFUSES RATHER THAN SKIPPING. A run that quietly did nothing would look like a
    # crawl with nothing to approve, and those are opposite facts.
    if args.approve and not is_enabled(FeatureKey.GENERIC_EXTRACTION):
        _refuse("generic extraction is disabled in this build "
                "(scrapex/features.py), so --approve would write rows the feature "
                "manifest says are not available. Nothing was read or written")


def _refuse(message: str) -> None:
    print(f"scrapex contractors: {message}", file=sys.stderr)
    raise SystemExit(2)


def run(args: argparse.Namespace) -> int:
    """Do what the arguments ask. THE ONE IMPLEMENTATION both front doors call."""
    validate(args)
    directory = get_directory(getattr(args, "source", None))
    started = time.monotonic()
    if args.plan:
        _, fetch = make_fetch(args.pace)
        plan(directory, fetch, started)
        return 0

    conn = open_engine()
    try:
        if args.crawl:
            fetcher, fetch = make_fetch(args.pace)
            # THE FACTORY, NOT A CONNECTION: `sqlite3` refuses one across
            # threads, so each worker opens its own. Only passed when it is
            # actually needed, so a single-worker crawl keeps using `conn`.
            factory = None
            if args.workers > 1:
                registry = DatabaseRegistry.defaults()
                factory = registry.engine.connect
                say(f"crawling with {args.workers} workers — the pace is unchanged, "
                    "the waits overlap")
            crawl(conn, directory, fetch, fetcher, args.run_ref,
                  args.max_attempts, only=args.only,
                  heavy_attempts=args.heavy_attempts,
                  workers=args.workers, connect=factory)
        if args.details:
            fetcher, fetch = make_fetch(args.pace)
            details(conn, directory, fetch, fetcher, args.run_ref,
                    ceiling=args.ceiling)
        if args.approve:
            approve(conn, directory, args.run_ref)
        if args.coverage:
            # THE DEFAULT WINDOW IS THE LEDGER'S OWN NEWEST SIGHTING, so running this
            # straight after a crawl asks "who did THAT crawl not show us" without
            # anyone having to type a timestamp — and a mistyped one silently reports
            # every contractor as departed.
            since = args.not_seen_since or (conn.execute(
                "SELECT MAX(last_seen_at) FROM dataset_sighting WHERE dataset_key = ?",
                (directory.dataset_key,)).fetchone()[0] or "")
            if not since:
                say("no sightings recorded for this dataset, so there is no window "
                    "to measure departures against. Crawl first.")
            else:
                say(f"departures measured against sightings on or after {since}")
                report_coverage(conn, directory, since)
    finally:
        conn.close()
    say(f"took {(time.monotonic() - started) / 60:.1f} min")
    return 0


def main(argv: list[str] | None = None) -> int:
    """`python -m scrapex.contractors`, for a developer with the repo in hand.

    KEPT ALONGSIDE THE SUBCOMMAND rather than replaced by it, because the two
    have different audiences: `scrapex contractors` is what a user has after
    `pip install`, and this is what runs without one. Both go through
    `add_arguments` and `run`, so neither can grow a flag the other lacks.
    """
    parser = argparse.ArgumentParser(prog="python -m scrapex.contractors",
                                     description=__doc__)
    add_arguments(parser)
    return run(parser.parse_args(argv))


if __name__ == "__main__":
    raise SystemExit(main())
