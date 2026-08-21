"""The provable listing crawl of muqawil.org, and the interpretation of it.

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
import sys
import time
from pathlib import Path

from .connectors.base import HttpFetcher
from .databases import DatabaseRegistry
from .extract import service
from .extract.models import ApprovalField, CandidateApproval
from .extract.muqawil import bilingual_listing_candidate
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
    missing_ids,
    sighting_frequencies,
)
from .sites.muqawil import MuqawilPartition
from .snapshotbody import decode

BASE = "https://muqawil.org"
DATASET = "contractors"
SITE_NAME = "Saudi Contractors Authority"
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

def plan(partition: MuqawilPartition, fetch, started: float) -> None:
    whole = size_cell(fetch, partition, BASE)
    say(f"listing now: {whole}")
    pages = 0
    declared = 0
    over = []
    for cell in partition.cells():
        size = size_cell(fetch, partition, BASE, cell)
        pages += size.last_page
        declared += size.declared
        if size.last_page > RETRY_PAGE_CEILING:
            over.append(size)
        say(f"  {size}")
    locales = len(partition.locales)
    requests = pages * locales + len(partition.cells()) * 3 + 2
    say("")
    say(f"cells {len(partition.cells())}  pages {pages} "
        f"(+{pages - whole.last_page} over the unfiltered {whole.last_page})")
    say(f"declared {declared:,} against the listing's {whole.declared:,} — "
        f"exhaustiveness deficit {whole.declared - declared:,}")
    say(f"locales {partition.locales} -> about {requests:,} requests for the crawl")
    # PRICED FROM THIS RUN'S OWN LATENCY, not from a number in a document. The
    # study measured 5.84 s a request; the sizing just made 100-odd requests, so
    # the honest estimate is the one it just paid for.
    per = (time.monotonic() - started) / max(1, whole.requests + len(partition.cells()) * 2)
    say(f"measured {per:.2f} s a request just now -> about {requests * per / 3600:.1f} h")
    if over:
        say(f"{len(over)} cell(s) above the {RETRY_PAGE_CEILING}-page witness ceiling, "
            f"without a retry: {', '.join(s.cell.label for s in over)}")


# ---- --crawl: the partition, witnessed --------------------------------------

def crawl(conn, partition: MuqawilPartition, fetch, fetcher, run_ref: str,
          max_attempts: int, only: str = "", heavy_attempts: int = HEAVY_ATTEMPTS
          ) -> None:
    """The partition, or NAMED CELLS OF IT.

    `--only` is what makes the residual addressable on its own, which
    `R-26` requires: the first run proved 47 of 56 cells, and a crawl that can only
    run the whole partition would re-read all 47 to reach the 9 that are open. It is
    matched on the cell LABEL — the same string the report prints and the run ref
    carries — so a cell can be copied straight out of the log into the next command.
    """
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

    say(f"crawl {run_ref} starting")
    outcome = crawl_partition(conn, partition, BASE, fetch=fetch, run_ref=run_ref,
                              dataset_key=DATASET, max_attempts=max_attempts,
                              heavy_attempts=heavy_attempts, cells=chosen,
                              fetcher=fetcher, on_cell=report)
    say("")
    say(str(outcome))
    say("")
    say(str(coverage(conn, DATASET)))


# ---- --coverage: what the warehouse knows about its own gaps ------------------

def report_coverage(conn, not_seen_since: str) -> None:
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
    say(str(coverage(conn, DATASET)))
    say("")

    frequencies = sighting_frequencies(conn, DATASET)
    if frequencies:
        say("how many ids the site showed us N times — the sample itself:")
        for times in sorted(frequencies):
            say(f"    seen {times:>2}x   {frequencies[times]:>7,}")
        say("  (kept as observations. Turning this into a population estimate is a "
            "statistical choice — Chao1 and Lincoln-Petersen disagree — and this "
            "module does not pick a school.)")
        say("")

    gap = missing_ids(conn, DATASET, limit=20)
    say(f"sighted and never stored: {len(gap)} shown (ordered by how often the site "
        "showed it — one seen six times and still unstored is a stronger signal "
        "than one glimpsed once)")
    if gap:
        say(f"    {', '.join(gap)}")
    say("")

    say(str(departures(conn, DATASET, not_seen_since=not_seen_since)))
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


def _approval(candidate) -> CandidateApproval:
    """The owner's answer, every field text-typed, `contractor_id` the identity.

    TEXT FOR EVERYTHING, and it is not laziness: type inference over twenty rows
    of one page guesses `integer` for a rating that reads `4.5` on the next page,
    and the schema hash then differs per page and every approval after the first
    is refused. `listing_candidate` already declines to guess for the same reason.
    """
    return CandidateApproval(
        table_index=0, site_key=MuqawilPartition.site_key,
        site_display_name=SITE_NAME, dataset_key=DATASET,
        dataset_name="Contractors",
        fields=[ApprovalField(field_key=one.field_key, display_name=one.source_name,
                              data_type="text",
                              identity=(one.field_key == "contractor_id"))
                for one in candidate.fields])


def approve(conn, run_ref: str) -> None:
    pairs = _pairs(conn, run_ref)
    say(f"approve {run_ref}: {len(pairs)} page(s) on disk")
    made = 0
    recovered = 0
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
        candidate = bilingual_listing_candidate(english[1], arabic[1] if arabic else "")
        if not candidate.approvable:
            refused.append((key, candidate.warnings[0] if candidate.warnings else "?"))
            continue
        try:
            result = service.approve_candidate(conn, english[0], _approval(candidate),
                                               candidate=candidate)
        except Exception as exc:
            conn.rollback()
            refused.append((key, f"{type(exc).__name__}: {exc}"))
            continue
        conn.commit()
        made += 1
        if result.get("recovered"):
            # ALREADY APPROVED, AND IT WROTE NOTHING. `DEC-10`: the idempotency
            # key is `(snapshot, locator)` plus the schema hash, so a corrected
            # parser re-run over stored pages returns `recovered=True` and
            # changes not one row. Counted out loud so a re-run that repaired
            # nothing cannot be mistaken for one that did.
            recovered += 1
    say(f"approved {made} page(s), of which {recovered} were already approved and "
        f"wrote nothing (DEC-10); {lonely} page(s) missing a locale half")
    for key, why in refused[:20]:
        say(f"  refused {key}: {why}")
    if len(refused) > 20:
        say(f"  … and {len(refused) - 20} more")
    say("")
    say(str(coverage(conn, DATASET)))


def add_arguments(parser: argparse.ArgumentParser) -> None:
    """The flags, declared ONCE for two front doors.

    `scrapex contractors` and `python -m scrapex.contractors` must not drift into
    two different vocabularies for the same operation — the same reasoning
    `publish.workbook_tables` gives for being the one place that decides what an
    export contains (P1). A flag added here appears in both.
    """
    parser.add_argument("--plan", action="store_true",
                       help="size all 56 cells and price the crawl. Costs ~114 "
                            "requests and answers 'what will this cost today'")
    parser.add_argument("--crawl", action="store_true")
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
    if not (args.plan or args.crawl or args.approve or args.coverage):
        _refuse("choose one of --plan, --crawl, --approve or --coverage")
    if (args.crawl or args.approve) and not args.run_ref:
        _refuse("--crawl and --approve need --run-ref: it is what makes an "
                "interrupted crawl resumable and what --approve reads")


def _refuse(message: str) -> None:
    print(f"scrapex contractors: {message}", file=sys.stderr)
    raise SystemExit(2)


def run(args: argparse.Namespace) -> int:
    """Do what the arguments ask. THE ONE IMPLEMENTATION both front doors call."""
    validate(args)
    partition = MuqawilPartition()
    started = time.monotonic()
    if args.plan:
        _, fetch = make_fetch(args.pace)
        plan(partition, fetch, started)
        return 0

    conn = open_engine()
    try:
        if args.crawl:
            fetcher, fetch = make_fetch(args.pace)
            crawl(conn, partition, fetch, fetcher, args.run_ref,
                  args.max_attempts, only=args.only,
                  heavy_attempts=args.heavy_attempts)
        if args.approve:
            approve(conn, args.run_ref)
        if args.coverage:
            # THE DEFAULT WINDOW IS THE LEDGER'S OWN NEWEST SIGHTING, so running this
            # straight after a crawl asks "who did THAT crawl not show us" without
            # anyone having to type a timestamp — and a mistyped one silently reports
            # every contractor as departed.
            since = args.not_seen_since or (conn.execute(
                "SELECT MAX(last_seen_at) FROM dataset_sighting WHERE dataset_key = ?",
                (DATASET,)).fetchone()[0] or "")
            if not since:
                say("no sightings recorded for this dataset, so there is no window "
                    "to measure departures against. Crawl first.")
            else:
                say(f"departures measured against sightings on or after {since}")
                report_coverage(conn, since)
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
