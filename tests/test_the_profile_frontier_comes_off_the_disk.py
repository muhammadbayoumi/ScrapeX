"""Nothing walked the profile frontier, and building it the obvious way took over two minutes.

WHAT WAS MISSING. `detail_urls` had callers, `belongs_to_slice` had callers, and no
command fetched a single profile page for muqawil. The 48 columns the owner wants are on
those pages; 21 of them are on the listing and the rest are not.

WHERE THE FRONTIER COMES FROM, and the first answer was wrong by a factor of about 1,500.
Deriving it from stored listing pages means decoding and parsing 14,727 of them: measured
at **over 120 seconds and still running when it was killed**. `dataset_sighting` already
holds every contractor id the site has ever shown us — that is what the ledger is for —
so the full frontier is one indexed SELECT: **0.08 s for 34,834 URLs**.

A SLICE STILL NEEDS THE PAGES, because the city is on the card and the ledger holds ids
alone. That asymmetry is deliberate and is why the two paths are not merged.

AND `sighted_ids` IS NOT `stored_ids`. Measured on the live warehouse: 17,417 sighted
against 15,707 stored, because a row exists only once its page has been approved. A
frontier built from stored rows would skip the 1,710 contractors we have seen and not yet
interpreted — the population a profile crawl most needs.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scrapex.crawlscope import CrawlScope
from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.directories import get as get_directory
from scrapex.sightings import record_sightings, sighted_ids

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "muqawil"


@pytest.fixture(autouse=True)
def _log_somewhere_harmless(tmp_path, monkeypatch):
    """`say` appends to the owner's real crawl log otherwise — `OP-39`."""
    from scrapex import contractors

    monkeypatch.setattr(contractors, "LOG", tmp_path / "contractors.log")


@pytest.fixture()
def conn(tmp_path: Path):
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    connection = registry.engine.connect()
    try:
        yield connection
    finally:
        connection.close()


def _registered(conn, scope: str, slice_of: str | None = None) -> None:
    """muqawil in `site_profile`, at the scope this test is about.

    THE SCOPE IS WRITTEN TO THE DATABASE AND NEVER PASSED IN, because that is the rule
    the code under test enforces: `PLATFORM-PLAN` Decision 23 makes it the owner's
    answer per source, and a scope a caller could also supply is a scope enforced in
    neither place.
    """
    conn.execute(
        "INSERT INTO site_profile (site_key, display_name, base_url, crawl_scope, "
        " crawl_slice) VALUES ('muqawil_org','Contractors','https://muqawil.org',?,?)",
        (scope, slice_of))
    conn.commit()


def _a_stored_listing(conn, *, run_ref: str = "listing-1",
                      name: str = "listing-en.html") -> None:
    conn.execute(
        "INSERT INTO generic_page_snapshot (source_url, html_content, content_hash, "
        " crawl_run_ref) VALUES (?,?,?,?)",
        ("https://muqawil.org/en/contractors?page=1",
         (FIXTURES / name).read_text(encoding="utf-8"), "h1", run_ref))
    conn.commit()


def _fetch_recording(asked: list[str], fails: set[str] = frozenset()):
    def fetch(url: str) -> str:
        asked.append(url)
        if url in fails:
            raise TimeoutError("the site did not answer")
        return f"<html>{url}</html>"

    return fetch


# ---- the registration decides -------------------------------------------------

def test_a_listing_only_source_fetches_no_profile_and_says_why(conn, capsys):
    """NOT AN ERROR. The registration is his answer; a command that fetched profiles
    anyway would be answering for him, which is what Decision 23 made the column for."""
    from scrapex.contractors import details

    _registered(conn, "listing_only")
    asked: list[str] = []

    details(conn, get_directory(None), _fetch_recording(asked), None, "r1")

    assert asked == []
    said = capsys.readouterr().out
    assert "listing_only" in said
    assert "site_profile.crawl_scope" in said, "it must say how to change the answer"


def test_a_slice_scope_with_no_slice_named_is_refused(conn):
    """`crawlscope.plan` raises `SliceRequired` for this too, and the duplication is of
    a CHECK rather than of the rule: refusing here costs nothing, and refusing after the
    frontier is built costs the frontier."""
    from scrapex.contractors import details

    _registered(conn, "listing_plus_slice", None)

    with pytest.raises(SystemExit) as raised:
        details(conn, get_directory(None), _fetch_recording([]), None, "r1")

    assert raised.value.code == 2


# ---- where the URLs come from -------------------------------------------------

def test_the_full_frontier_is_read_off_the_ledger_and_not_off_the_pages(conn):
    """THE PROOF IS THE ABSENCE OF PAGES. Not one listing snapshot is stored here, so a
    frontier derived by parsing stored listings would be empty. It is not, because
    `dataset_sighting` is the record of what the site showed us.
    """
    from scrapex.contractors import detail_frontier

    _registered(conn, "full_then_listing")
    record_sightings(conn, "contractors", ["1004", "20044482"])

    urls, outside = detail_frontier(conn, get_directory(None),
                                    CrawlScope.FULL_THEN_LISTING, "")

    assert outside == 0
    assert urls == [
        "https://muqawil.org/en/contractors/1004/143",
        "https://muqawil.org/ar/contractors/1004/143",
        "https://muqawil.org/en/contractors/20044482/143",
        "https://muqawil.org/ar/contractors/20044482/143",
    ]


def test_the_ledger_reaches_contractors_that_have_no_row_yet(conn):
    """`sighted_ids` IS NOT `stored_ids`, and the gap is the point: 17,417 against
    15,707 on the live warehouse. A row exists only once its page is approved, so a
    frontier built from rows skips exactly the contractors not yet interpreted."""
    _registered(conn, "full_then_listing")
    record_sightings(conn, "contractors", ["1004", "20044482"])
    # One of them has a row; the other has only ever been seen.
    conn.execute("INSERT INTO dataset_definition (site_profile_id, dataset_key, "
                 " original_name, dataset_kind, discovery_method, locator_json) "
                 "VALUES (1,'contractors','c','table','html_table','{}')")
    conn.execute("INSERT INTO dataset_schema_version (dataset_definition_id, "
                 " version_number, schema_hash) VALUES (1,1,'h')")
    conn.execute(
        "INSERT INTO generic_page_snapshot (source_url, html_content, content_hash) "
        "VALUES ('u','<html></html>','hh')")
    conn.execute(
        "INSERT INTO generic_record (dataset_definition_id, record_key, "
        " schema_version_id, data_json, source_snapshot_id, source_locator, "
        " content_hash) VALUES (1,'k',1,?,1,'x','c')",
        (json.dumps({"contractor_id": "1004"}),))
    conn.commit()

    from scrapex.sightings import stored_ids

    assert set(sighted_ids(conn, "contractors")) == {"1004", "20044482"}
    assert set(stored_ids(conn, "contractors")) == {"1004"}


def test_a_slice_reads_the_pages_because_the_city_is_on_the_card(conn):
    """The asymmetry, asserted. The ledger holds ids alone, so a slice cannot come from
    it — and this frontier is smaller than the page's row count, which is what selecting
    means."""
    from scrapex.contractors import detail_frontier

    _registered(conn, "listing_plus_slice", "RIYADH")
    _a_stored_listing(conn)

    urls, outside = detail_frontier(conn, get_directory(None),
                                    CrawlScope.LISTING_PLUS_SLICE, "RIYADH")

    assert urls, "the committed listing has at least one Riyadh contractor"
    assert outside > 0, "and at least one that is not, or nothing is being selected"
    assert all("/contractors/" in url and url.endswith("/143") for url in urls)


def test_the_ledger_holds_one_row_however_often_a_contractor_is_seen(conn):
    """THE FULL PATH CANNOT PRODUCE A DUPLICATE, and saying so is worth a test because
    it explains why the deduplication below is about the SLICE path.

    `record_sightings` upserts, so being seen five times is still one ledger row. A
    mutation removing `dict.fromkeys` from the frontier survived against this path for
    exactly that reason — the guard is real, and this is not where it acts.
    """
    from scrapex.contractors import detail_frontier

    _registered(conn, "full_then_listing")
    record_sightings(conn, "contractors", ["1004"])
    record_sightings(conn, "contractors", ["1004"])

    urls, _ = detail_frontier(conn, get_directory(None),
                              CrawlScope.FULL_THEN_LISTING, "")

    assert len(urls) == 2, "one per locale, not four"


def test_a_contractor_on_two_stored_listing_pages_is_fetched_once(conn):
    """WHERE THE DEDUPLICATION ACTUALLY EARNS ITS PLACE. A live listing reorders between
    requests — the entire reason the witness compares id sequences rather than counts —
    so the same contractor really does end up on two stored pages. On the slice path the
    frontier is built by reading those pages, so without this the profile is fetched
    twice: a wasted request and a second snapshot of the same page, times however many
    contractors the reorder touched.
    """
    from scrapex.contractors import detail_frontier

    _registered(conn, "listing_plus_slice", "RIYADH")
    listing = (FIXTURES / "listing-en.html").read_text(encoding="utf-8")
    for page in (1, 2):
        # THE SAME PAGE UNDER TWO URLS, which is what a reorder looks like from disk:
        # two stored listing pages whose card sets overlap.
        conn.execute(
            "INSERT INTO generic_page_snapshot (source_url, html_content, "
            " content_hash, crawl_run_ref) VALUES (?,?,?,'listing-1')",
            (f"https://muqawil.org/en/contractors?page={page}", listing, f"h{page}"))
    conn.commit()

    urls, _ = detail_frontier(conn, get_directory(None),
                              CrawlScope.LISTING_PLUS_SLICE, "RIYADH")

    assert urls, "the committed listing has Riyadh contractors"
    assert len(urls) == len(set(urls)), "the same profile URL twice"


# ---- the walk ------------------------------------------------------------------

def test_every_frontier_url_is_fetched_and_stored(conn, capsys):
    from scrapex.contractors import details

    _registered(conn, "full_then_listing")
    record_sightings(conn, "contractors", ["1004"])
    asked: list[str] = []

    details(conn, get_directory(None), _fetch_recording(asked), None, "profiles-1")

    assert len(asked) == 2
    stored = conn.execute(
        "SELECT COUNT(*) FROM generic_page_snapshot WHERE crawl_run_ref = 'profiles-1'"
    ).fetchone()[0]
    assert stored == 2
    assert "profiles stored 2" in capsys.readouterr().out


def test_a_resume_skips_what_this_run_already_stored_and_counts_it(conn, capsys):
    """COUNTED, NEVER SILENT: the difference is the hours a resume saved, and a resume
    that says nothing is indistinguishable from a crawl that fetched everything."""
    from scrapex.contractors import details

    _registered(conn, "full_then_listing")
    record_sightings(conn, "contractors", ["1004", "20044482"])
    details(conn, get_directory(None), _fetch_recording([]), None, "profiles-1")

    second: list[str] = []
    details(conn, get_directory(None), _fetch_recording(second), None, "profiles-1")

    assert second == [], "everything was already on disk under this ref"
    assert "4 already stored under profiles-1 — resuming" in capsys.readouterr().out


def test_a_dead_profile_does_not_end_the_run(conn, capsys):
    """One dead page out of thirty-four thousand must not discard the rest. A crawl that
    stops at the first 404 of an eleven-hour run is a crawl nobody can finish."""
    from scrapex.contractors import details

    _registered(conn, "full_then_listing")
    record_sightings(conn, "contractors", ["1004", "20044482"])
    dead = "https://muqawil.org/en/contractors/1004/143"

    details(conn, get_directory(None), _fetch_recording([], fails={dead}), None, "p1")

    said = capsys.readouterr().out
    assert "profiles stored 3, failed 1" in said


def test_the_ceiling_stops_the_run_and_calls_it_partial(conn, capsys):
    """34,834 pages is about eleven hours at the rate six workers measured — 52.5 pages
    a minute over 87 minutes of real crawling. A first run that only wants the shape of
    the data has to be able to stop, and a stopped run must not look finished."""
    from scrapex.contractors import details

    _registered(conn, "full_then_listing")
    record_sightings(conn, "contractors", ["1004", "20044482"])
    asked: list[str] = []

    details(conn, get_directory(None), _fetch_recording(asked), None, "p1", ceiling=3)

    assert len(asked) == 3
    said = capsys.readouterr().out
    assert "3-page ceiling" in said
    assert "PARTIAL" in said


def test_a_ceiling_on_the_wrong_phase_is_refused_not_ignored(conn):
    """A ceiling silently dropped would let somebody believe a full crawl was bounded
    when it was not."""
    import argparse

    from scrapex.contractors import add_arguments, validate

    parser = argparse.ArgumentParser()
    add_arguments(parser)

    with pytest.raises(SystemExit) as raised:
        validate(parser.parse_args(["--crawl", "--run-ref", "r", "--ceiling", "10"]))

    assert raised.value.code == 2


def test_the_stored_profile_is_labelled_as_a_profile(conn, monkeypatch):
    """`body_class` PICKS THE COMPRESSION DICTIONARY. `docs/STORAGE.md` measured 46x on
    profiles against zlib's 7.7x, because zlib's 32 KB window never sees across a 121 KB
    page — so on 34,834 pages a profile stored under the listing's dictionary is
    gigabytes, not untidiness.

    THIS TEST USED TO ASSERT `html_codec is not None` AND IT PASSED WITH `body_class=None`
    — a mutation that survived being committed and was caught by the lint gate noticing
    an unused import, not by this file. A test that holds under the defect it is named
    for proves nothing.

    So it asserts the LABEL that was passed, which is the decision being made:
    `muqawil.org/detail` and never `muqawil.org/listing` or the `muqawil.org/page`
    fallback that `label_for` returns when no kind is given.
    """
    from scrapex import contractors
    from scrapex.contractors import details

    seen: list[str | None] = []
    real = contractors.service.save_snapshot

    def watching(conn_, request):
        seen.append(request.body_class)
        return real(conn_, request)

    monkeypatch.setattr(contractors.service, "save_snapshot", watching)
    _registered(conn, "full_then_listing")
    record_sightings(conn, "contractors", ["1004"])

    details(conn, get_directory(None), _fetch_recording([]), None, "p1")

    assert seen == ["muqawil.org/detail", "muqawil.org/detail"]


# ---- a slice is named in ONE language, and the scan has to know that ----------
#
# `R-39` RECORDS THE MEASUREMENT THAT PRODUCED THIS. `belongs_to_slice` compares the
# slice value against the card's own city text, and the card is in the page's language:
#
#     en page, slice 'RIYADH'  -> 3 of 4 cards match
#     en page, slice 'الرياض'  -> 0 of 4
#     ar page, slice 'RIYADH'  -> 0 of 4
#     ar page, slice 'الرياض'  -> 3 of 4
#
# Scanning every stored page against one value therefore counts every row of the OTHER
# locale as "outside the slice". The frontier still came out right — `detail_rows` yields
# both locales' profile URLs for a matched row — but the report was false, and the whole
# slice depended on the matching locale's pages happening to be on disk.

def _both_locales_stored(conn) -> None:
    for locale in ("en", "ar"):
        conn.execute(
            "INSERT INTO generic_page_snapshot (source_url, html_content, "
            " content_hash, crawl_run_ref) VALUES (?,?,?,'listing-1')",
            (f"https://muqawil.org/{locale}/contractors?page=1",
             (FIXTURES / f"listing-{locale}.html").read_text(encoding="utf-8"),
             f"h-{locale}"))
    conn.commit()


def test_the_other_locales_rows_are_not_counted_as_outside_the_slice(conn):
    """THE FALSE REPORT THIS FIXES. With both locales on disk and an English slice, the
    Arabic page's rows are not the answer to "how many did we skip" — they were never
    asked the question."""
    from scrapex.contractors import detail_frontier

    _registered(conn, "listing_plus_slice", "RIYADH")
    _both_locales_stored(conn)

    urls, outside = detail_frontier(conn, get_directory(None),
                                    CrawlScope.LISTING_PLUS_SLICE, "RIYADH")

    english_only, english_outside = detail_frontier(
        conn, get_directory(None), CrawlScope.LISTING_PLUS_SLICE, "RIYADH")
    assert urls == english_only
    # The committed listing has four cards, three of them Riyadh — so exactly one row is
    # genuinely outside the slice, not one plus the whole Arabic page.
    assert outside == english_outside == 1


def test_the_frontier_is_the_same_whichever_language_the_slice_is_named_in(conn):
    """THE PROOF THAT SCANNING ONE LOCALE LOSES NOTHING: a matched row yields BOTH
    locales' profile URLs, so naming the slice in Arabic must produce the identical
    frontier."""
    from scrapex.contractors import detail_frontier

    _registered(conn, "listing_plus_slice", "RIYADH")
    _both_locales_stored(conn)

    english = detail_frontier(conn, get_directory(None),
                              CrawlScope.LISTING_PLUS_SLICE, "RIYADH")
    arabic = detail_frontier(conn, get_directory(None),
                             CrawlScope.LISTING_PLUS_SLICE, "الرياض")

    assert english == arabic
    assert english[0], "and it is not empty, or this proves nothing"


def test_a_slice_that_matches_nothing_says_how_many_rows_it_looked_at(conn):
    """A CITY WITH NO CONTRACTORS AND A SLICE NAMED IN THE WRONG LANGUAGE both produce an
    empty frontier, and the examined count is what tells them apart."""
    from scrapex.contractors import detail_frontier

    _registered(conn, "listing_plus_slice", "ATLANTIS")
    _both_locales_stored(conn)

    urls, examined = detail_frontier(conn, get_directory(None),
                                     CrawlScope.LISTING_PLUS_SLICE, "ATLANTIS")

    assert urls == []
    assert examined == 8, ("four CARDS on each of the two stored pages — rows, not "
                           "URLs, which is two per card on this site")


def test_a_slice_matching_in_two_locales_is_refused(conn):
    """THE COUNTS WOULD BE THE SUM OF TWO DIFFERENT QUESTIONS. A value that matches in
    both languages is either a name written the same way in both — which is possible —
    or a marker that has moved. Adding them up would hide either."""
    from scrapex.contractors import detail_frontier

    _registered(conn, "listing_plus_slice", "RIYADH")
    # The SAME English page stored under both locale paths, which is what a value
    # matching in two locales looks like from disk.
    listing = (FIXTURES / "listing-en.html").read_text(encoding="utf-8")
    for locale in ("en", "ar"):
        conn.execute(
            "INSERT INTO generic_page_snapshot (source_url, html_content, "
            " content_hash, crawl_run_ref) VALUES (?,?,?,'listing-1')",
            (f"https://muqawil.org/{locale}/contractors?page=1", listing, f"h{locale}"))
    conn.commit()

    with pytest.raises(ValueError) as raised:
        detail_frontier(conn, get_directory(None),
                        CrawlScope.LISTING_PLUS_SLICE, "RIYADH")

    assert "more than one locale" in str(raised.value)
