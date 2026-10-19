"""The TVTC register reader: the JSON shape, the paginator arithmetic, the locale pair, the crawl.

No network. The happy paths run against four pages captured on 2026-10-17 (`#1716`), two
page numbers in two languages, with every person's name, ID, mobile and e-mail, and every
establishment's phone, fax and e-mail, replaced by same-shape fakes. Page 1 was chosen
because it holds two of the census's nine violations; page 38 because it holds the one
establishment with no region.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from scrapex.pagesource import WHOLE, PageSource, SliceNotSupported
from scrapex.sites.tvtc import (
    BASE_URL,
    LIST_PATH,
    LOCALES,
    PAGE_SIZE,
    PRIMARY_LOCALE,
    SITE_KEY,
    RegisterShapeError,
    TvtcPageSource,
    TvtcPartition,
    identity_evidence,
    listing_url,
    locale_in_query,
    read_ids,
    read_last_page,
    read_page,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _fixture(page: int, locale: str) -> str:
    return (FIXTURES / f"tvtc_establishments_p{page}_{locale}.json").read_text(
        encoding="utf-8")


def _body(rows: list[dict], *, total: int, per_page: int, current: int,
          last_page: int | None = None, **meta) -> str:
    """A list response in the register's own shape."""
    last = last_page if last_page is not None else max(1, -(-total // per_page))
    return json.dumps({"data": rows, "links": {},
                       "meta": {"total": total, "per_page": per_page,
                                "current_page": current, "last_page": last, **meta}})


def _rows(*ids) -> list[dict]:
    return [{"id": key, "name": f"n{key}"} for key in ids]


# --- the real pages -----------------------------------------------------------------

def test_the_real_page_reads_its_own_total_and_ten_rows():
    page = read_page(_fixture(1, "en"))
    assert (page.total, page.per_page, page.current_page) == (3141, 10, 1)
    assert page.last_page == 315 and len(page.rows) == 10


def test_both_languages_of_a_real_page_hold_the_same_ids_in_the_same_order():
    """The stability the witness leans on, and the join the candidate leans on."""
    for number in (1, 38):
        assert read_ids(_fixture(number, "en")) == read_ids(_fixture(number, "ar"))


def test_read_ids_is_the_published_order_as_text():
    assert read_ids(_fixture(1, "ar"))[:2] == ("859310", "56738")


def test_read_ids_keeps_a_repeated_id_rather_than_hiding_it():
    body = _body(_rows(7, 7, 8), total=3, per_page=3, current=1)
    assert read_ids(body) == ("7", "7", "8")


def test_a_row_carries_its_key_and_no_registration():
    """The unified CR is shared by up to 60 branches in the census, so it is not an id
    that says "the same establishment under another key"."""
    evidence = identity_evidence(_fixture(1, "en"))
    assert [one.key for one in evidence] == list(read_ids(_fixture(1, "en")))
    assert all(one.registration is None and one.second_key is None for one in evidence)


# --- the shape is asserted, loudly ---------------------------------------------------

@pytest.mark.parametrize("body, said", [
    ("<html>an error page</html>", "not JSON"),
    ("[1, 2]", "not an object"),
    (json.dumps({"meta": {}}), "no `data` list"),
    (json.dumps({"data": []}), "no `meta` object"),
    (json.dumps({"data": [], "meta": {"total": "3", "per_page": 1, "current_page": 1,
                                      "last_page": 3}}), "meta.total"),
    (json.dumps({"data": [], "meta": {"total": 3, "per_page": True, "current_page": 1,
                                      "last_page": 3}}), "meta.per_page"),
    (json.dumps({"data": [], "meta": {"total": 3, "per_page": 0, "current_page": 1,
                                      "last_page": 3}}), "meta.per_page is 0"),
])
def test_a_body_of_another_shape_is_refused_by_name(body, said):
    with pytest.raises(RegisterShapeError, match=re.escape(said)):
        read_page(body)


def test_a_last_page_that_disagrees_with_the_total_is_refused():
    """The only end the crawl has, so it is checked against the arithmetic."""
    with pytest.raises(RegisterShapeError, match="meta.last_page is 2"):
        read_page(_body(_rows(1, 2), total=10, per_page=2, current=1, last_page=2))


def test_an_inner_page_holding_fewer_rows_than_a_page_is_refused():
    with pytest.raises(RegisterShapeError, match="page 1 of 3 carries 1 rows, not 2"):
        read_page(_body(_rows(1), total=5, per_page=2, current=1))


def test_the_last_page_holds_the_remainder_and_reads():
    page = read_page(_body(_rows(5), total=5, per_page=2, current=3))
    assert page.last_page == 3 and len(page.rows) == 1


def test_a_last_page_holding_a_full_page_beyond_the_total_is_refused():
    with pytest.raises(RegisterShapeError, match="page 3 of 3 carries 2 rows, not 1"):
        read_page(_body(_rows(5, 6), total=5, per_page=2, current=3))


def test_a_page_past_the_end_is_empty_and_reads_as_no_ids():
    """Measured: `page=99999` answered 200 with `data: []`."""
    assert read_ids(_body([], total=5, per_page=2, current=99)) == ()


def test_a_page_past_the_end_that_carries_rows_is_refused():
    with pytest.raises(RegisterShapeError, match="past the last"):
        read_page(_body(_rows(1), total=5, per_page=2, current=4))


def test_an_empty_register_is_one_empty_page():
    assert read_last_page(_body([], total=0, per_page=10, current=1)) == 1


@pytest.mark.parametrize("key", [None, "", True, 1.5, {"x": 1}])
def test_a_row_without_a_usable_id_is_refused(key):
    with pytest.raises(RegisterShapeError, match="no usable `id`"):
        read_page(_body([{"id": key}], total=1, per_page=1, current=1))


def test_a_row_that_is_not_an_object_is_refused():
    with pytest.raises(RegisterShapeError, match="row 0 is a str"):
        read_page(_body(["x"], total=1, per_page=1, current=1))


# --- the URL and the locale pair -----------------------------------------------------

def test_the_url_writes_locale_limit_and_page_in_one_order():
    assert listing_url(locale="ar", page=3) == (
        f"{BASE_URL}{LIST_PATH}?locale=ar&limit={PAGE_SIZE}&page=3")


def test_the_page_size_is_the_measured_thousand():
    """3,141 establishments are four pages per language at 1,000 (`#1716`); at 100 the
    crawl would be ten times the requests, and at 5,000 a page would pass the 32 MB cap."""
    assert PAGE_SIZE == 1000
    assert "&limit=1000&" in listing_url(page=1)


def test_the_url_refuses_page_zero_and_an_unknown_locale():
    with pytest.raises(ValueError, match="at least 1"):
        listing_url(page=0)
    with pytest.raises(ValueError, match="locale must be one of"):
        listing_url(locale="fr")


def test_the_two_languages_of_a_page_share_one_key():
    english = locale_in_query(listing_url(locale="en", page=4))
    arabic = locale_in_query(listing_url(locale="ar", page=4))
    assert english[1] == "en" and arabic[1] == "ar"
    assert english[0] == arabic[0] and "locale" not in english[0]


def test_two_pages_do_not_share_a_key():
    one = locale_in_query(listing_url(locale="en", page=1))[0]
    two = locale_in_query(listing_url(locale="en", page=2))[0]
    assert one != two


@pytest.mark.parametrize("url", [
    f"{BASE_URL}{LIST_PATH}?limit=1000&page=1",
    f"{BASE_URL}{LIST_PATH}?locale=fr&limit=1000&page=1",
    f"{BASE_URL}{LIST_PATH}?locale=en&locale=ar&page=1",
])
def test_a_url_naming_no_single_known_locale_is_not_half_of_a_pair(url):
    assert locale_in_query(url) is None


# --- the partition --------------------------------------------------------------------

def test_the_partition_satisfies_the_protocol_the_crawl_expects():
    from scrapex.partitioncrawl import PartitionedListing
    assert isinstance(TvtcPartition(), PartitionedListing)
    assert isinstance(TvtcPartition().in_cell(WHOLE, last_page=3), PageSource)


def test_there_is_one_cell_because_the_order_is_stable():
    assert TvtcPartition().cells() == (WHOLE,)


def test_the_partition_declares_both_locales_and_english_as_the_primary():
    part = TvtcPartition()
    assert part.locales == LOCALES == ("en", "ar")
    assert part.primary_locale == PRIMARY_LOCALE == "en"


def test_the_pages_are_interleaved_by_language_not_grouped_by_it():
    urls = list(TvtcPartition().in_cell(WHOLE, last_page=2).listing_urls(BASE_URL))
    assert [(locale_in_query(u)[1], u.endswith("page=1")) for u in urls] == [
        ("en", True), ("ar", True), ("en", False), ("ar", False)]


def test_the_page_source_offers_no_detail_urls_and_refuses_a_slice():
    source = TvtcPartition().in_cell(WHOLE, last_page=1)
    assert tuple(source.detail_urls(object())) == ()
    with pytest.raises(SliceNotSupported, match=SITE_KEY):
        source.belongs_to_slice(object(), 0, "region=1")


def test_a_page_source_refuses_no_pages_and_no_locales():
    with pytest.raises(ValueError, match="at least 1"):
        TvtcPageSource(last_page=0)
    with pytest.raises(ValueError, match="no locale"):
        TvtcPageSource(last_page=1, locales=())


# --- the registry ---------------------------------------------------------------------

def test_the_entry_carries_the_four_facts_and_its_partition():
    from scrapex import directories
    from scrapex.extract.tvtc import bilingual_listing_candidate
    entry = directories.get(SITE_KEY)
    assert entry.base_url == BASE_URL
    assert entry.dataset_key == "tvtc_training_establishments"
    assert entry.identity_field == "establishment_id"
    assert entry.candidate is bilingual_listing_candidate
    assert entry.locale_pairing is locale_in_query
    assert isinstance(entry.partition(), TvtcPartition)


def test_the_register_is_read_from_the_api_host_not_the_shell():
    """Measured (`#1716`): `pt-web` answers every path with the same 1,379-byte HTML
    shell, status 200; the rows are on `pt-api`. Pointed at the shell, every page would
    be refused as not JSON -- after the whole crawl had been spent."""
    assert BASE_URL == "https://pt-api.tvtc.gov.sa"
    assert LIST_PATH == "/api/v1/public-inquiries/licensed-establishments"


def test_the_entry_has_no_profile_reader_and_no_registration_field():
    from scrapex import directories
    entry = directories.get(SITE_KEY)
    assert entry.profiles is None and entry.registration_field is None


def test_the_entry_ships_off_so_the_schedule_does_not_crawl_it_without_his_word():
    from scrapex import directories
    assert directories.get(SITE_KEY).active is False


def test_muqawil_is_still_the_default():
    from scrapex import directories
    assert directories.get().key == "muqawil_org"


def test_the_shipped_switch_reaches_the_settings_he_reads(tmp_path):
    """`active=False` is not only a field: it is what his settings start from."""
    from scrapex import db as dbmod, directories, source_settings
    conn = dbmod.connect(tmp_path / "engine.db")
    try:
        dbmod.migrate(conn)
        settings = source_settings.effective(conn, SITE_KEY, directories.get(SITE_KEY))
    finally:
        conn.close()
    assert settings.active is False


# --- a stored page this size is kept ------------------------------------------------

def test_a_page_twice_the_largest_measured_plans_page_is_stored(tmp_path):
    """The largest 1,000-plan page measured 10.96 MB over the full crawl (`#1716` step 2);
    at 16 MB a page with less than 1.5x growth was refused, its ids still counted read."""
    from scrapex import db as dbmod
    from scrapex.extract.models import SnapshotCreate
    from scrapex.extract.service import save_snapshot
    body = _body(_rows(1), total=1, per_page=1, current=1)
    body = body[:-1] + ', "pad": "' + "x" * 22_000_000 + '"}'
    conn = dbmod.connect(tmp_path / "engine.db")
    try:
        dbmod.migrate(conn)
        stored = save_snapshot(conn, SnapshotCreate(
            source_url=listing_url(page=1), html_content=body))
    finally:
        conn.close()
    assert stored["page_snapshot_id"] > 0


def test_a_page_over_the_cap_is_refused_by_name_not_truncated(tmp_path):
    from pydantic import ValidationError

    from scrapex.extract.models import MAX_STORED_BODY_BYTES, SnapshotCreate
    assert MAX_STORED_BODY_BYTES == 32_000_000
    with pytest.raises(ValidationError, match="at most"):
        SnapshotCreate(source_url=listing_url(page=1),
                       html_content="x" * (MAX_STORED_BODY_BYTES + 1))


def test_a_page_saved_by_hand_keeps_the_two_megabyte_limit_its_parse_needs():
    """#1739: the hand-saved page's tables are parsed inside a write, measured at 29.9 s and
    1.27 GB for 15.9 MB. The crawl's limit must not reach it."""
    from pydantic import ValidationError

    from scrapex.extract.models import MAX_HTML_BYTES, SavedPageCreate, SnapshotCreate
    assert MAX_HTML_BYTES == 2_000_000
    page = "<table><tr><td>x</td></tr></table>"
    assert SavedPageCreate(source_url="https://example.test/",
                           html_content=page + " " * (MAX_HTML_BYTES - len(page)))
    with pytest.raises(ValidationError, match="at most 2000000"):
        SavedPageCreate(source_url="https://example.test/",
                        html_content="x" * (MAX_HTML_BYTES + 1))
    assert issubclass(SavedPageCreate, SnapshotCreate)


def test_the_save_a_page_route_refuses_a_page_over_two_megabytes(tmp_path):
    """Through the real route: a 2 MB + 1 body is a 422, and nothing is stored."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from scrapex.databases import DatabaseRegistry, EngineDatabase
    from scrapex.extract.models import MAX_HTML_BYTES
    from scrapex.webui.app import create_app
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    with TestClient(create_app(databases=registry)) as client:
        refused = client.post("/api/general/extract/snapshots", json={
            "source_url": "https://example.test/big",
            "html_content": "<p>" + "x" * MAX_HTML_BYTES + "</p>"})
        kept = client.post("/api/general/extract/snapshots", json={
            "source_url": "https://example.test/small",
            "html_content": "<table><tr><td>x</td></tr></table>"})
    assert refused.status_code == 422, refused.text[:200]
    assert kept.status_code == 201, kept.text[:200]
    conn = registry.engine.connect()
    try:
        urls = [u for (u,) in conn.execute("SELECT source_url FROM generic_page_snapshot")]
    finally:
        conn.close()
    assert urls == ["https://example.test/small"]


# --- end to end -------------------------------------------------------------------------

def _registry(tmp_path):
    from scrapex.databases import DatabaseRegistry, EngineDatabase
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    return registry


def test_the_register_is_proven_complete_by_count_through_the_real_crawl(tmp_path):
    """`crawl_partition` on the real reader: five establishments declared over three
    pages, five read, so the one cell closes on its first read."""
    from scrapex.partitioncrawl import crawl_partition

    pages = {1: _rows(11, 12), 2: _rows(13, 14), 3: _rows(15)}
    asked: list[str] = []

    def fetch(url: str) -> str:
        asked.append(url)
        number = int(re.search(r"[?&]page=(\d+)", url).group(1))
        return _body(pages.get(number, []), total=5, per_page=2, current=number)

    conn = _registry(tmp_path).engine.connect()
    try:
        conn.execute("INSERT INTO source_site (source_key, source_name, base_url, "
                     "crawl_scope) VALUES (?, 'TVTC', ?, 'listing_only')",
                     (SITE_KEY, BASE_URL))
        conn.commit()
        outcome = crawl_partition(conn, TvtcPartition(), BASE_URL, fetch=fetch,
                                  run_ref="run-1",
                                  dataset_key="tvtc_training_establishments",
                                  resize_at_end=False)
        stored = conn.execute("SELECT source_url FROM generic_page_snapshot").fetchall()
    finally:
        conn.close()

    only = outcome.cells[0]
    assert only.size.declared == 5, str(only.size)
    assert outcome.deficit == 0 and only.provably_complete, str(outcome)
    assert set(outcome.ids) == {"11", "12", "13", "14", "15"}
    # Both languages of every page were stored, so every page can be paired.
    assert {locale_in_query(url)[1] for (url,) in stored} == {"en", "ar"}
    assert all("locale=" in url for url in asked), "a URL without locale= is English"


def test_the_stored_pages_of_both_locales_meet_in_pairs(tmp_path):
    from scrapex import contractors, db as dbmod, directories

    conn = dbmod.connect(tmp_path / "engine.db")
    try:
        dbmod.migrate(conn)
        directory = directories.get(SITE_KEY)
        for page in (1, 2):
            for locale in LOCALES:
                url = listing_url(directory.base_url, locale=locale, page=page)
                conn.execute(
                    "INSERT INTO generic_page_snapshot (source_url, html_content, "
                    " content_hash, crawl_run_ref) VALUES (?, ?, ?, ?)",
                    (url, f"{{}} {locale} {page}", f"h{locale}{page}", "tvtc-1-whole-1"))
        conn.commit()
        pairs = contractors._pairs(conn, directory, "tvtc-1")
    finally:
        conn.close()
    assert len(pairs) == 2
    assert all(set(halves) == {"en", "ar"} for halves in pairs.values())


def test_the_stored_body_limit_is_counted_in_bytes_not_characters(tmp_path):
    """#1749's review: under the character limit, over it in UTF-8 -- refused by name."""
    from scrapex import db as dbmod
    from scrapex.extract.models import (
        MAX_STORED_BODY_BYTES,
        CandidateNotApprovable,
        SnapshotCreate,
    )
    from scrapex.extract.service import save_snapshot
    body = "ب" * (MAX_STORED_BODY_BYTES // 2 + 1)
    assert len(body) <= MAX_STORED_BODY_BYTES < len(body.encode("utf-8"))
    conn = dbmod.connect(tmp_path / "engine.db")
    try:
        dbmod.migrate(conn)
        with pytest.raises(CandidateNotApprovable, match="exceeds"):
            save_snapshot(conn, SnapshotCreate(source_url=listing_url(page=1),
                                               html_content=body))
    finally:
        conn.close()


def test_a_multibyte_page_saved_by_hand_is_held_to_two_megabytes_of_bytes(tmp_path):
    """Through the real route: 1M Arabic characters are ~2 MB of characters and ~4 MB of
    UTF-8 -- it was a 201 while the limit counted characters."""
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from scrapex.databases import DatabaseRegistry, EngineDatabase
    from scrapex.extract.models import MAX_HTML_BYTES
    from scrapex.webui.app import create_app
    body = "<p>" + "ب" * (MAX_HTML_BYTES // 2) + "</p>"
    assert len(body) <= MAX_HTML_BYTES < len(body.encode("utf-8"))
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    with TestClient(create_app(databases=registry)) as client:
        refused = client.post("/api/general/extract/snapshots", json={
            "source_url": "https://example.test/arabic", "html_content": body})
    assert refused.status_code == 422, refused.text[:200]
    assert "at most 2,000,000" in refused.text
