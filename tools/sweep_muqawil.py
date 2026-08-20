"""Pass over muqawil's listing until the new names stop coming.

A MEASUREMENT, NOT A PRODUCTION CRAWL, and the difference decides what it keeps.
The question is "how many contractors does this directory actually have?" — the
first full pass found 11,059 and could not know what it missed. So passes here
FETCH AND COUNT, they do not store snapshots: three more passes at 652 MB each
would put 2 GB of largely identical HTML on disk to answer a question about a
set of integers. Pass one's evidence is already stored and stays.

Once the true number is known, how to crawl for production is a separate
decision, taken with the number in hand rather than guessed at without it.

AND IT NOW KEEPS THE IDS, WHICH IS THE WHOLE POINT AND WAS MISSING. The first
version called `sweep.record()`, printed `sweep.summary()` and exited — so six
passes over 8h37m produced a COUNT in a log file and threw away the SET. When the
owner later asked whether membership 10001274 was in the warehouse, the answer
"we do not know what we are missing, only how much" was the honest one, and it
should not have been. `Sweep` had held every id in `found` the whole time and
nobody read it.

Every pass now writes its ids to `dataset_sighting`, so "which contractors has
the site shown us that we never stored" is a query instead of a rerun.

Run it with the repo's own venv:  python tools/sweep_muqawil.py
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scrapex.connectors.base import HttpFetcher          # noqa: E402
from scrapex.databases import DatabaseRegistry
from scrapex.extract.muqawil import read_listing         # noqa: E402
from scrapex.sightings import coverage, record_sightings
from scrapex.sites.muqawil import read_last_page  # noqa: E402
from scrapex.sweep import Sweep                          # noqa: E402

BASE = "https://muqawil.org"
OUT = Path.home() / ".scrapex" / "trial" / "sweep.log"


def say(line: str) -> None:
    print(line, flush=True)
    with OUT.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def one_pass(fetch, last_page: int, number: int) -> list[str]:
    """Every contractor id the English listing shows, this time round.

    ENGLISH ONLY. The Arabic pages carry the same ids — the id comes from the
    href, which is language-independent — so fetching both would double a
    measurement's cost to learn nothing. The production crawl needs both
    locales because it needs both languages' VALUES; this needs neither.
    """
    ids: list[str] = []
    started = time.monotonic()
    for page in range(1, last_page + 1):
        url = f"{BASE}/en/contractors?page={page}"
        try:
            ids.extend(row["contractor_id"] for row in read_listing(fetch(url)))
        except Exception as exc:                          # noqa: BLE001
            say(f"    pass {number} page {page}: {type(exc).__name__}: {exc}")
        if page % 100 == 0:
            say(f"    pass {number}: {page}/{last_page} pages, "
                f"{len(set(ids)):,} ids, {(time.monotonic()-started)/60:.0f} min")
    return ids


def main() -> None:
    fetcher = HttpFetcher(min_interval_s=1.0)
    def fetch(url: str) -> str:
        return fetcher.get(url).text

    last = read_last_page(fetch(f"{BASE}/en/contractors"))
    sweep = Sweep(dry_passes_before_stopping=2, max_passes=6)
    say(f"\n=== sweep started, {last} pages a pass, ~{last*5.84/3600:.1f} h each ===")

    # OPENED BEFORE THE FIRST PASS, so a sweep that cannot persist what it sees
    # fails now rather than after eight hours of fetching.
    conn = DatabaseRegistry.defaults().engine.connect()
    try:
        while sweep.keep_going:
            number = len(sweep.passes) + 1
            started = time.monotonic()
            ids = one_pass(fetch, last, number)
            made = sweep.record(ids)
            # WRITTEN PER PASS, not once at the end. A sweep killed on pass four
            # used to leave nothing; now it leaves four passes of sightings, which
            # is the same reasoning snapshotcrawl applies to a page.
            fresh = record_sightings(conn, "contractors", ids,
                                     run_ref=f"sweep-{number}")
            say(f"  pass {number}: +{made.fresh:,} new, {made.seen:,} total, "
                f"{fresh:,} newly sighted, {(time.monotonic()-started)/60:.0f} min")

        say("")
        say(sweep.summary())
        say("")
        say(str(coverage(conn, "contractors")))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
