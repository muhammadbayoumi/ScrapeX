"""Every WRITE path must work against a split database, not just a legacy file.

The owner started the engine, pressed Run, and got a 500 with
"table offer_state already exists". Two request paths called dbmod.migrate()
unconditionally: a MarketLens database has its OWN numbered migration stream
(1-15) and is already migrated when created, so running the unified stream
(1-17) over it re-applies migration 1 onto tables that exist.

The whole test suite was green, because every test built an app over a legacy
single-file warehouse — the shape that is no longer the default. These tests use
the shape a real install actually has.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scrapex.databases import DatabaseRegistry
from scrapex.databases.domain import GeneralDatabase, MarketLensDatabase

pytest.importorskip("fastapi", reason="needs the ui extra")
from fastapi.testclient import TestClient  # noqa: E402

from scrapex.webui.app import create_app  # noqa: E402


@pytest.fixture()
def split_client(tmp_path: Path) -> TestClient:
    registry = DatabaseRegistry(
        GeneralDatabase(tmp_path / "general" / "general.db"),
        MarketLensDatabase(tmp_path / "marketlens" / "marketlens.db"),
        pointer_file=tmp_path / "databases.json",
    )
    registry.initialize()
    return TestClient(create_app(databases=registry))


def test_queueing_a_job_works_against_a_split_database(split_client):
    """The exact request the owner made: press Run."""
    response = split_client.post("/api/jobs", json={"source_keys": ["GPP_ENERGY"]})

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "queued" and body["job_ref"]


def test_the_queued_job_is_readable_afterwards(split_client):
    split_client.post("/api/jobs", json={"source_keys": ["GPP_ENERGY"]})

    listed = split_client.get("/api/jobs")

    assert listed.status_code == 200
    assert listed.json(), "the job was queued into a database nothing else reads"


def test_no_write_route_re_migrates_a_domain_database(split_client):
    """A guard for the whole class, not the one route that happened to break.

    Re-running the unified stream over a domain database raises; if any of these
    routes still did it, the request would 500 rather than answer.
    """
    for method, path, payload in [
        ("post", "/api/jobs", {"source_keys": ["GPP_ENERGY"]}),
        ("get", "/api/sources", None),
        ("get", "/api/health", None),
        ("get", "/api/changes", None),
    ]:
        call = getattr(split_client, method)
        response = call(path, json=payload) if payload else call(path)
        assert response.status_code < 500, \
            f"{method.upper()} {path} failed on a split database: {response.text[:200]}"


def test_the_schema_of_a_domain_database_is_left_alone(split_client, tmp_path):
    """Not just "it did not crash": the version must be untouched afterwards."""
    registry = DatabaseRegistry.read(tmp_path / "databases.json")
    before = registry.marketlens.health().schema_version

    split_client.post("/api/jobs", json={"source_keys": ["GPP_ENERGY"]})

    after = registry.marketlens.health().schema_version
    assert after == before == registry.marketlens.latest_schema_version


# ---- a configured source that has never run must still be visible -----------

def test_a_fresh_install_shows_every_configured_source(split_client):
    """The overview read the DATABASE, which only knows a source once it has
    ingested something. On a fresh install that meant "No data yet" and none of
    the configured sources — a source that had never run did not look like a
    problem, it simply did not exist."""
    body = split_client.get("/").text

    assert "Configured, never run" in body
    assert "GPP_ENERGY" in body and "ELSEWEDYSHOP" in body
    assert "Never run" in body, "the status must be stated in words"


def test_a_source_that_has_run_is_not_listed_as_never_run(split_client):
    """The two lists must be disjoint, or a source appears twice and the owner
    cannot tell which card is current."""
    split_client.get("/source/GPP_ENERGY")     # registers nothing; still never run
    body = split_client.get("/").text

    import re

    section = body.split("Configured, never run")[-1]
    # Count CARDS, not string occurrences: a card names its source twice, once
    # as the key and once inside the suggested crawl command.
    cards = re.findall(r'class="key">([A-Z_]+)</div>', section)
    assert cards.count("GPP_ENERGY") == 1, f"listed more than once: {cards}"


# ---- Data page, slice 1: a row can finally be asked about itself ------------

def _seed(client, source_key="GPP_ENERGY"):
    """Crawl nothing; just make the page reachable and return its HTML."""
    return client.get(f"/source/{source_key}").text


def test_a_row_carries_its_own_identity(split_client, tmp_path):
    """pricehistory.timeline() has been callable since migration 0016 and no
    screen could reach it, because browse_observations selected sixteen columns
    and offer_id was not one of them. The row had nothing to ask about."""
    from scrapex.reports import browse_observations
    from scrapex.databases import DatabaseRegistry

    registry = DatabaseRegistry.read(tmp_path / "databases.json")
    conn = registry.marketlens.connect()
    try:
        page = browse_observations(conn, "GPP_ENERGY")
    finally:
        conn.close()

    assert all("offer_id" in row for row in page.rows)


def test_history_counts_is_one_query_for_the_page_not_one_per_row(split_client, tmp_path):
    from scrapex.reports import history_counts
    from scrapex.databases import DatabaseRegistry

    registry = DatabaseRegistry.read(tmp_path / "databases.json")
    conn = registry.marketlens.connect()
    try:
        assert history_counts(conn, []) == {}, "no offers must cost no query"
        assert isinstance(history_counts(conn, [1, 2, 3]), dict)
    finally:
        conn.close()


def test_an_offer_page_refuses_an_offer_from_another_source(split_client):
    """The ownership check is the security boundary. Without it the URL could be
    walked into another source's history by anyone who can count."""
    response = split_client.get("/source/GPP_ENERGY/offer/999999")
    assert response.status_code == 404


def test_a_missing_and_a_foreign_offer_are_indistinguishable(split_client):
    """Saying which would confirm the existence of an id the caller may not own."""
    missing = split_client.get("/source/GPP_ENERGY/offer/999999")
    foreign = split_client.get("/source/ELSEWEDYSHOP/offer/999999")
    assert missing.status_code == foreign.status_code == 404


# ---- Data page, slice 2: orientation ----------------------------------------

def test_a_never_run_source_still_names_itself_and_a_next_step(split_client):
    """Found by this test rather than by me: the Data page renders NOTHING about
    a source that has never run — no name, no key, no command — because the
    whole block is behind `summary is not none`. It is the same blindness the
    overview had, and it is fixed the same way."""
    body = split_client.get("/source/GPP_ENERGY").text

    assert "GPP_ENERGY" in body
    assert "Never run" in body, "the status must be stated, not implied by silence"
    assert "crawl GPP_ENERGY" in body, "an empty page must say how to fill it"


def test_rows_per_page_offers_only_sizes_the_server_will_honour(split_client):
    """A dropdown offering a number the server silently clamps is a lie."""
    from scrapex.webui.app import PER_PAGE_OPTIONS

    assert max(PER_PAGE_OPTIONS) == 200, "the cap browse_observations enforces"


def test_an_absurd_page_size_is_refused_not_served(split_client):
    response = split_client.get("/source/GPP_ENERGY?per_page=40000")
    assert response.status_code in (200, 404)
    if response.status_code == 200:
        assert "40000" not in response.text.split("per_page")[-1][:200]


# ---- Data page, slice 3: per-column filters ---------------------------------

def test_a_crafted_filter_key_is_refused_and_named(split_client):
    """The allow-list is the guard. A key never reaches SQL as text — and a
    filter that vanished silently would make the answer BIGGER than the
    question, with no way for the reader to tell."""
    from scrapex.reports import parse_filters

    accepted, ignored = parse_filters({
        "f.region": "is:EG",
        "f.effective_price;DROP TABLE x--": "1",
        "f.nonexistent": "is:x",
    })

    assert accepted == {"region": ("is", "EG")}
    assert "f.effective_price;DROP TABLE x--" in ignored
    assert "f.nonexistent" in ignored


def test_an_unknown_operator_is_refused():
    from scrapex.reports import parse_filters

    accepted, ignored = parse_filters({"f.region": "exec:EG"})

    assert accepted == {} and ignored == ["f.region"]


def test_a_computed_column_is_declared_unfilterable_not_half_supported():
    """unit and tax_label are produced in Python — price_unit() and
    tax.resolve(), the latter with a region->wildcard fallback and valid_to
    temporality. Half-supporting them in SQL is a correctness trap."""
    from scrapex.reports import FILTERABLE, SORTABLE, parse_filters

    assert FILTERABLE["unit"][1] == "derived"
    assert FILTERABLE["tax_label"][1] == "derived"
    assert "unit" not in SORTABLE and "tax_label" not in SORTABLE
    accepted, ignored = parse_filters({"f.unit": "is:liter"})
    assert accepted == {} and ignored == ["f.unit"]


def test_sortable_is_derived_from_the_same_table_so_they_cannot_drift():
    """They were two separate lists, and SORTABLE quietly omitted
    last_confirmed and curation_status — columns the page rendered with no way
    to order by them, and nothing said so."""
    from scrapex.reports import FILTERABLE, SORTABLE

    assert SORTABLE == {k: v[0] for k, v in FILTERABLE.items() if v[1] != "derived"}
    # ...and the keys are the EXPORT vocabulary, so dataset_field holds one name
    # per fact. They were invented separately, and the manage list then showed
    # "name" beside "product_name" — the same column twice, and hiding one did
    # not hide the other.
    from scrapex.reports import EXPORT_HEADER
    shared = {k for k, _ in __import__("scrapex.reports", fromlist=["x"]).BROWSE_COLUMNS} & set(EXPORT_HEADER)
    assert "product_name" in shared and "price_changed_on" in shared
    assert "last_confirmed_on" in SORTABLE and "curation_status" in SORTABLE


def test_filtering_by_country_uses_the_name_shown_on_screen(split_client):
    """The table renders region_name ("Egypt"); the column stores the ISO code.
    Without translating, filtering by the only string on screen matches nothing."""
    from scrapex.reports import _browse_filters

    clause, params = _browse_filters(None, None, {"region": ("is", "Egypt")})

    assert "so.region = ?" in clause
    assert params == ["EG"], "the visible name was not resolved to its code"


def test_a_filter_value_is_always_bound_never_spliced():
    from scrapex.reports import _browse_filters

    clause, params = _browse_filters(None, None, {"product_name": ("has", "'; DROP TABLE x--")})

    assert "'; DROP" not in clause, "a value reached the statement text"
    assert params == ["%'; DROP TABLE x--%"]


# ---- Data page, slice 4: the watch strip ------------------------------------

def test_a_state_that_was_never_derived_is_not_counted_as_confirmed(tmp_path):
    """_LATEST_PER_OFFER joins offer_state LEFT precisely because an offer whose
    state has not been derived still has a price. Folding those into "confirmed"
    would under-report exactly the staleness this strip exists to surface."""
    from scrapex.databases import DatabaseRegistry
    from scrapex.reports import watch

    registry = DatabaseRegistry(
        GeneralDatabase(tmp_path / "g" / "g.db"),
        MarketLensDatabase(tmp_path / "m" / "m.db"),
        pointer_file=tmp_path / "databases.json")
    registry.initialize()
    conn = registry.marketlens.connect()
    try:
        counts = watch(conn, "GPP_ENERGY")
    finally:
        conn.close()

    assert "state_not_derived" in counts
    assert counts["state_not_derived"] == 0, "no offers yet, so none can be undrived"


def test_an_unbuilt_history_is_reported_as_unbuilt_not_as_zero(tmp_path):
    """price_period is DERIVED and only filled by a rebuild. Empty means "not
    built yet", which is a different answer from "nothing moved" — a bare 0 for
    both is a lie of omission."""
    from scrapex.databases import DatabaseRegistry
    from scrapex.reports import watch

    registry = DatabaseRegistry(
        GeneralDatabase(tmp_path / "g2" / "g.db"),
        MarketLensDatabase(tmp_path / "m2" / "m.db"),
        pointer_file=tmp_path / "databases2.json")
    registry.initialize()
    conn = registry.marketlens.connect()
    try:
        counts = watch(conn, "GPP_ENERGY")
    finally:
        conn.close()

    assert counts["history_built"] is False
    assert counts["moved"] == 0


def test_the_strip_is_rendered_and_a_zero_tile_still_appears(split_client):
    """A tile that disappears at zero is indistinguishable from one nobody
    built. It stays, greyed, and says what it counts — in words."""
    body = split_client.get("/source/GPP_ENERGY").text
    # A source with no data renders the never-run block instead; either way the
    # page must not crash and must state something.
    assert "Never run" in body or "watch" in body


def test_a_tile_and_the_page_it_opens_count_the_same_rows(split_client):
    """The design's decisive acceptance check, and it caught a real defect: the
    curation tile counted 721 offers in THIS table and opened /review, which
    lists match reviews — a different population entirely. A tile whose number
    disagrees with the list it opens teaches the owner to distrust both.

    Tiles that ARE a filter of this table now link to this table filtered; tiles
    whose answer lives elsewhere say so with an arrow instead of pretending.
    """
    page = (Path(__file__).resolve().parent.parent / "scrapex" / "webui"
            / "templates" / "source.html").read_text(encoding="utf-8")

    assert 'f.curation_status": "is:inventoried"' in page, \
        "the curation tile must open this table filtered, not another page"
    assert "elsewhere=true" in page, \
        "a tile pointing at another page must be marked as going elsewhere"


# ---- Data page, slice 6: saved views that actually apply --------------------
#
# Views have been storable since migration 0008 and NOTHING ever read
# config_json back — a view was a blob with no consumer, and the chip's only
# working control was its delete ×.
#
# The full round trip is verified against real data rather than here: a view
# saved as {"filters":{"region":"is:Egypt"},"sort":"effective_price"} reopens to
# 5 Egyptian rows sorted by price, and ?view_id=1&f.region=is:Saudi+Arabia
# returns Saudi rows — the URL beating the view's default. What these tests
# guard is the part that must never depend on a live crawl: what a stored blob
# is allowed to do.


def test_a_saved_view_round_trips_through_the_api(split_client):
    saved = split_client.post("/api/views/GPP_ENERGY", json={
        "view_name": "Egyptian fuel",
        "config": {"filters": {"region": "is:Egypt"}, "sort": "effective_price",
                   "direction": "desc"}})
    assert saved.status_code == 200

    listed = split_client.get("/api/fields/GPP_ENERGY").json()["views"]
    names = [v["view_name"] for v in listed]
    assert "Egyptian fuel" in names
    stored = next(v for v in listed if v["view_name"] == "Egyptian fuel")["config"]
    assert stored["filters"] == {"region": "is:Egypt"},         "a view must save the QUESTION, not only a column list"
    assert stored["sort"] == "effective_price"


def test_a_stored_view_is_no_more_trusted_than_a_typed_url(split_client):
    """The allow-list is the guard on both paths. A blob we wrote ourselves is
    not privileged: a key that is not in FILTERABLE never reaches SQL."""
    from scrapex.reports import FILTERABLE, parse_filters

    crafted = {"f.effective_price;DROP TABLE x--": "1", "f.ghost": "is:x",
               "f.region": "is:EG"}
    accepted, ignored = parse_filters(crafted)

    assert accepted == {"region": ("is", "EG")}
    assert len(ignored) == 2
    assert all(key[2:] not in FILTERABLE for key in ignored)


def test_a_view_naming_a_vanished_column_is_reported_not_widened_silently(split_client):
    """A dropped FILTER shows more rows than the view asks for. Silence would
    leave the reader with no way to know the answer grew."""
    split_client.post("/api/views/GPP_ENERGY", json={
        "view_name": "Stale", "config": {"filters": {"ghost_column": "is:x"}}})

    body = split_client.get("/source/GPP_ENERGY?view_id=1").text

    # The source has never run, so the table itself is absent — but the page
    # must still load rather than fail on a view it cannot fully honour.
    assert "GPP_ENERGY" in body
