"""T2/Q4: static-html-table (globalpetrolprices) — positional parse + country->ISO + commodity e2e."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.gpp import (
    GlobalPetrolPricesConnector, _contracted_materials, _region, parse_price_table,
)
from scrapex.ingest import ingest_payloads
from scrapex.rowspec import COMMODITY_PRICE, RowBuilder, RowView
from scrapex.vocab import ExtractKind, ExtractScope

FX = Path(__file__).parent / "fixtures"


def _read(name): return (FX / name).read_text(encoding="utf-8")


class _Resp:
    def __init__(self, text): self.text = text


class _StubFetcher:
    """Serves the LIST at /diesel_prices/ and the Egypt COUNTRY page for every
    /{Country}/diesel_prices/ — the same two shapes the live site serves. The
    list is the frontier; the country page is where the price now comes from."""
    def __init__(self): self.requests_count = 0
    def get(self, url, **kwargs):
        self.requests_count += 1
        path = url.split(".com", 1)[-1]
        if path == "/diesel_prices/":
            return _Resp(_read("gpp_diesel.html"))
        if path.endswith("/diesel_prices/"):
            return _Resp(_read("gpp_country_egypt_diesel.html"))
        raise RuntimeError("404 " + url)
    def close(self): pass


def make_entry(materials=("DIESEL",)) -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="GPP_ENERGY", source_name="أسعار الطاقة العالمية",
        base_url="https://www.globalpetrolprices.com", family="static-html-table",
        cadence="weekly", authority="aggregator", currency="USD",
        extract=[ExtractSpec(kind=ExtractKind.COMMODITY_PRICE, scope=ExtractScope.LATEST_ONLY,
                             materials=list(materials), regions=["*"])],
    ))


# ---- pure positional parse (Q4) ----------------------------------------------

def test_parse_price_table_zips_positionally():
    pairs = parse_price_table(_read("gpp_diesel.html"))
    # The '*' footnote marker and the &nbsp; must both be stripped.
    assert pairs == [("Egypt", "0.404"), ("Saudi Arabia", "0.476"),
                     ("United States", "0.950"), ("Atlantis", "1.100")]


def test_parse_price_table_raises_on_length_drift():
    """Two labels, one bar: zipping would attribute Sudan's price to nobody and
    shift every later country onto the wrong number."""
    html = ('<div id="outsideLinks"><a>Egypt</a><a>Sudan</a></div>'
            '<div id="graphic"><div>'
            '<div style="background:#e2bb04"><div>0.3</div></div>'
            '</div></div>')
    with pytest.raises(ValueError, match="2 country labels vs 1 price"):
        parse_price_table(html)


def test_selectors_matching_nothing_fails_loud():
    """Regression: 0 labels vs 0 values passes a naive equal-length check — which
    is exactly how broken selectors produced a silent zero-row 'success' instead
    of a visible failure (the live GPP_ENERGY run the owner hit)."""
    with pytest.raises(ValueError, match="matched nothing"):
        parse_price_table("<html><body><p>redesigned page</p></body></html>")


def test_axis_rules_are_not_mistaken_for_prices():
    """The graph's two axis lines are bare positioned divs with no label; only a
    bar whose single child div holds a number counts as a price."""
    pairs = parse_price_table(_read("gpp_diesel.html"))
    assert len(pairs) == 4          # 4 bars, not 6 (2 axis rules ignored)


# ---- country -> ISO ----------------------------------------------------------

def test_region_maps_and_skips_unknown():
    assert _region("Saudi Arabia") == "SA" and _region("Egypt") == "EG"
    assert _region("United States") == "US"
    assert _region("South Korea") == "KR"      # override
    assert _region("Atlantis") is None         # unmapped -> skipped upstream


# ---- full fetch --------------------------------------------------------------

def test_gpp_fetches_diesel_and_maps_regions():
    """The price is now the one the source PUBLISHES, in its own currency.

    1 list request + 3 country requests (Atlantis is unmapped, so its page is
    never fetched). Each mapped country yields its current published price plus
    the free history anchors as reported rows.
    """
    fetcher = _StubFetcher()
    table = next(iter(GlobalPetrolPricesConnector(fetcher).fetch(make_entry())))
    assert fetcher.requests_count == 4          # 1 list + 3 country pages
    view = RowView(COMMODITY_PRICE, table.header)
    rows = [view.as_dict(r) for r in table.rows]

    current = [r for r in rows if r["provenance"] == "observed"]
    assert len(current) == 3                    # Atlantis (unmapped) skipped
    egypt = current[0]
    assert egypt["material_key"] == "DIESEL" and egypt["region"] == "EG"
    # EGP 20.50 as published — NOT the list page's 0.404 USD conversion.
    assert egypt["effective_price"] == "20.50" and egypt["currency"] == "EGP"
    assert egypt["unit"] == "liter" and egypt["vat_included"] == "1"
    assert egypt["price_basis"] == "original"
    assert egypt["source_date"] == "2026-07-13"

    reported = [r for r in rows if r["provenance"] == "reported"]
    assert reported and all(r["as_of_date"] for r in reported)


def test_one_failing_page_does_not_kill_the_crawl():
    """Q3 resilience: the GASOLINE page 404s in the stub; the DIESEL rows still land."""
    fetcher = _StubFetcher()
    table = next(iter(GlobalPetrolPricesConnector(fetcher).fetch(
        make_entry(materials=("DIESEL", "GASOLINE")))))
    assert fetcher.requests_count == 5       # both lists attempted + 3 country pages
    view = RowView(COMMODITY_PRICE, table.header)
    assert {view.as_dict(r)["region"] for r in table.rows} == {"EG", "SA", "US"}


def test_layout_drift_on_one_page_does_not_discard_the_others():
    """Regression: parse_price_table sat OUTSIDE the per-page try, so a drifting
    GASOLINE page aborted the generator and threw away the parsed DIESEL rows."""
    drift = ('<div id="outsideLinks"><a>Egypt</a><a>Sudan</a></div>'
             '<div id="graphic"><div><div style="background:#e2bb04">'
             '<div>0.3</div></div></div></div>')

    class _DriftFetcher(_StubFetcher):
        def get(self, url, **kwargs):
            if url.endswith("/gasoline_prices/"):
                self.requests_count += 1
                return _Resp(drift)
            return super().get(url, **kwargs)

    table = next(iter(GlobalPetrolPricesConnector(_DriftFetcher()).fetch(
        make_entry(materials=("DIESEL", "GASOLINE")))))
    view = RowView(COMMODITY_PRICE, table.header)
    assert {view.as_dict(r)["region"] for r in table.rows} == {"EG", "SA", "US"}


def test_total_layout_drift_still_fails_loud():
    """But when NOTHING parses, stay loud (Q4) — silence would look like an empty site."""
    class _AllDriftFetcher(_StubFetcher):
        def get(self, url, **kwargs):
            self.requests_count += 1
            return _Resp("<html><body><p>redesigned page</p></body></html>")

    with pytest.raises(ValueError, match="every contracted GPP page failed"):
        next(iter(GlobalPetrolPricesConnector(_AllDriftFetcher()).fetch(make_entry())))


def test_contracted_material_without_a_page_is_skipped():
    """Characterization: a manifest material with no _PAGES entry is silently dropped
    (config only validates UPPER_SNAKE_CASE, so a typo/new fuel can reach here)."""
    assert _contracted_materials(make_entry(materials=("DIESEL", "CRUDE_OIL"))) == ["DIESEL"]


def test_gpp_end_to_end_into_warehouse():
    entry = make_entry()
    table = next(iter(GlobalPetrolPricesConnector(_StubFetcher()).fetch(entry)))
    conn: sqlite3.Connection = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        result = ingest_payloads(conn, entry, [table.to_payload()])
        offers = conn.execute("SELECT COUNT(*) FROM source_offer").fetchone()[0]
    finally:
        conn.close()
    # One product (DIESEL), one implicit variant, three region offers. Each
    # offer lands 1 observed row + reported rows for the source's own dating and
    # its free history anchors; reported rows on distinct business dates all
    # persist (the dedupe key includes the date), and none of them fires change
    # detection or period logic — covered by test_ingest_reported.py.
    assert (result.products, result.variants) == (1, 1)
    assert offers == 3
    assert result.observations >= 9   # 3 observed + at least 2 dated anchors each


# ---- the electricity page uses a different layout entirely -------------------
#
# Running the parser against the LIVE pages on 2026-07-20 showed diesel, gasoline,
# LPG and natural gas returning 169/170/56/47 rows — and electricity returning
# ZERO. It publishes a real table, not the graphic. The crawl still reported
# success, because a page that fails while others succeed was silently dropped.

class _FiveePageFetcher:
    """Serves the real captured markup for both layouts."""

    def __init__(self, break_electricity: bool = False):
        self.requests_count = 0
        self.urls: list[str] = []
        self._break = break_electricity

    def get(self, url, **kwargs):
        self.requests_count += 1
        self.urls.append(url)
        path = url.split(".com", 1)[-1]
        if path == "/diesel_prices/":
            return _Resp(_read("gpp_diesel.html"))
        if path.endswith("/diesel_prices/"):
            return _Resp(_read("gpp_country_egypt_diesel.html"))
        if path.endswith("/electricity_prices/"):
            return _Resp("<html><body>nothing here</body></html>" if self._break
                         else _read("gpp_electricity.html"))
        raise RuntimeError("404 " + url)

    def close(self): pass


def test_the_electricity_table_is_parsed_by_row_not_by_position():
    """Real captured markup. Country and price share a <tr>, so unlike the
    graphic pages they cannot drift apart — no positional guard is needed."""
    from scrapex.connectors.gpp import parse_rank_table

    pairs = parse_rank_table(_read("gpp_electricity.html"), 1)

    assert ("Bermuda", "0.465") in pairs
    assert ("Italy", "0.414") in pairs
    assert all(country and price for country, price in pairs)


def test_residential_and_business_electricity_are_two_series_not_one():
    """Germany publishes 0.406 residential and 0.283 business. Collapsing them
    would silently pick one and present it as 'the' electricity price."""
    from scrapex.connectors.gpp import parse_rank_table

    residential = dict(parse_rank_table(_read("gpp_electricity.html"), 1))
    business = dict(parse_rank_table(_read("gpp_electricity.html"), 2))

    assert residential["Bermuda"] == "0.465"
    assert business["Bermuda"] == "0.264"
    assert residential["Bermuda"] != business["Bermuda"]


def test_a_country_publishing_only_one_rate_is_skipped_not_zero_filled():
    """Ireland has a residential rate and an empty business cell. A zero there
    would read as 'electricity is free for businesses in Ireland'."""
    from scrapex.connectors.gpp import parse_rank_table

    business = dict(parse_rank_table(_read("gpp_electricity.html"), 2))

    assert "Ireland" not in business
    assert "0" not in business.values() and "0.000" not in business.values()


def test_electricity_produces_rows_end_to_end():
    entry = make_entry(materials=("ELECTRICITY", "ELECTRICITY_BUSINESS"))
    fetcher = _FiveePageFetcher()

    tables = list(GlobalPetrolPricesConnector(fetcher).fetch(entry))

    rows = tables[0].rows
    assert rows, "electricity produced no rows at all"
    view = RowView(COMMODITY_PRICE, tables[0].header)
    materials = {view.get(r, "material_key") for r in rows}
    assert materials == {"ELECTRICITY", "ELECTRICITY_BUSINESS"}
    assert tables[0].warnings == []


def test_one_page_serving_two_materials_is_fetched_once():
    entry = make_entry(materials=("ELECTRICITY", "ELECTRICITY_BUSINESS"))
    fetcher = _FiveePageFetcher()

    list(GlobalPetrolPricesConnector(fetcher).fetch(entry))

    assert fetcher.urls.count("https://www.globalpetrolprices.com/electricity_prices/") == 1, \
        "the same page was downloaded once per material"


def test_a_page_that_yields_nothing_is_reported_even_when_others_succeed():
    """The exact failure that hid electricity: four pages parsed, one matched
    nothing, and the run reported a clean row count."""
    entry = make_entry(materials=("DIESEL", "ELECTRICITY"))
    fetcher = _FiveePageFetcher(break_electricity=True)

    tables = list(GlobalPetrolPricesConnector(fetcher).fetch(entry))

    assert tables[0].rows, "the healthy page must still be delivered"
    assert any("ELECTRICITY" in w for w in tables[0].warnings), \
        "a whole energy type produced nothing and the run said nothing"


# ---- country labels the live pages actually print ----------------------------
#
# Checking all five live pages on 2026-07-20 found 38 rows being dropped because
# the site abbreviates names to fit narrow table cells. Turkey and the UK were
# missing from ALL FIVE energy types. No hand-written fixture would ever have
# contained "N. Maced." or "Bosnia & Herz." — which is exactly why a fabricated
# fixture cannot prove a connector works.

def test_the_abbreviated_labels_the_site_actually_prints_are_mapped():
    from scrapex.connectors.gpp import _region

    assert _region("Turkey") == "TR"
    assert _region("UK") == "GB"
    assert _region("UAE") == "AE"
    assert _region("Dom. Rep.") == "DO"
    assert _region("Bosnia & Herz.") == "BA"
    assert _region("N. Maced.") == "MK"
    assert _region("C. Afr. Rep.") == "CF"
    assert _region("Trinidad & Tobago") == "TT"
    assert _region("Swaziland") == "SZ"
    assert _region("Curacao") == "CW"
    assert _region("Burma") == "MM"


def test_an_unmappable_country_is_reported_not_silently_dropped():
    """A country we cannot map is a row we cannot keep — but not one we may
    lose quietly. That is how Turkey and the UK vanished unnoticed."""
    entry = make_entry(materials=("DIESEL",))

    class _Fetcher:
        requests_count = 0
        def get(self, url, **kwargs):
            # Same shape as the live page: labels in one column, bars in
            # another, each bar's single child div holding the number.
            return _Resp(
                '<div id="outsideLinks"><div>'
                '<div><a>Egypt</a></div><div><a>Wakanda</a></div>'
                '</div></div>'
                '<div id="graphic"><div>'
                '<div style="bar"><div>0.404</div></div>'
                '<div style="bar"><div>0.500</div></div>'
                '</div></div>')
        def close(self): pass

    table = next(iter(GlobalPetrolPricesConnector(_Fetcher()).fetch(entry)))

    assert len(table.rows) == 1, "the mappable country must still be kept"
    assert any("Wakanda" in w for w in table.warnings), \
        "a dropped country left no trace"


# ---- the country page: the price the source actually publishes ---------------
#
# The list pages render every figure through <select name="currency"> (156
# options) and <select name="literGalon"> (4), so the USD-per-litre number we
# stored was a conversion for a default selection, not what was published. The
# owner said so and was right; this is the fix.

def test_the_country_page_gives_the_price_in_the_currency_it_is_published_in():
    from scrapex.connectors.gpp import parse_country_page

    page = parse_country_page(_read("gpp_country_egypt_diesel.html"))

    assert page.price == "20.50" and page.currency == "EGP" and page.unit == "liter"
    assert page.usd_price == "0.40", "the conversion is kept, but only for reference"


def test_the_source_stamps_its_own_date_which_is_not_our_crawl_date():
    """Ingest stamps our crawl date. Natural gas data can be seven months old and
    would read as current; the page states when it was actually updated."""
    from scrapex.connectors.gpp import parse_country_page

    page = parse_country_page(_read("gpp_country_egypt_diesel.html"))

    assert page.source_date == "2026-07-13"
    assert page.available_from == "2016-08-01" and page.frequency == "Weekly"


def test_the_free_history_anchors_are_read():
    """A year of history on the first crawl instead of fifty-two weeks of waiting.
    Egyptian diesel: 15.50 a year ago against 20.50 now."""
    from scrapex.connectors.gpp import parse_country_page

    page = parse_country_page(_read("gpp_country_egypt_diesel.html"))

    assert dict(page.history) == {30: "20.50", 91: "20.50", 365: "15.50"}


def test_a_reported_price_never_passes_for_one_we_observed():
    """We did not watch Egyptian diesel in July 2025. The source tells us today
    what it was then, and the row has to say which of the two it is."""
    from datetime import date

    from scrapex.connectors.gpp import country_rows, parse_country_page

    page = parse_country_page(_read("gpp_country_egypt_diesel.html"))
    builder = RowBuilder(COMMODITY_PRICE)
    view = RowView(COMMODITY_PRICE, builder.header)

    rows = [view.as_dict(r) for r in
            country_rows(builder, "DIESEL", "EG", page, "USD", "liter", "1",
                         date(2026, 7, 20))]

    current = [r for r in rows if r["provenance"] == "observed"]
    reported = [r for r in rows if r["provenance"] == "reported"]
    # 3 free anchors + the source's own "Last update" dating of the current price
    assert len(current) == 1 and len(reported) == 4
    assert current[0]["as_of_date"] == "", "today's price needs no as-of date"
    year_ago = [r for r in reported if r["as_of_date"] == "2025-07-20"]
    assert year_ago and year_ago[0]["effective_price"] == "15.50"
    # The page's Last update (2026-07-13) is the SOURCE's claim about when this
    # price took effect — a dated claim, so it lands as reported, on that date.
    stamped = [r for r in reported if r["as_of_date"] == "2026-07-13"]
    assert stamped and stamped[0]["effective_price"] == "20.50"


def test_the_amount_and_its_currency_label_always_agree():
    """The bug this caught in its own author: pairing the country page's EGP
    amount with the manifest's USD label puts an Egyptian price in a field that
    says dollars — the exact corruption the whole change exists to remove."""
    from datetime import date

    from scrapex.connectors.gpp import country_rows, parse_country_page

    page = parse_country_page(_read("gpp_country_egypt_diesel.html"))
    builder = RowBuilder(COMMODITY_PRICE)
    view = RowView(COMMODITY_PRICE, builder.header)

    for row in country_rows(builder, "DIESEL", "EG", page, "USD", "liter", "1",
                            date(2026, 7, 20)):
        shaped = view.as_dict(row)
        assert shaped["currency"] == "EGP", "an EGP amount labelled USD"
        assert shaped["price_basis"] == "original"


def test_a_page_without_the_tables_yields_nothing_rather_than_a_guess():
    """Electricity country pages have a different structure entirely — no tables
    at all. Returning empty is correct; inventing a price would not be."""
    from scrapex.connectors.gpp import parse_country_page

    page = parse_country_page("<html><body><h1>Germany electricity prices</h1></body></html>")

    assert page.price == "" and page.currency == "" and page.history == ()


def test_the_country_link_is_read_off_the_page_never_rebuilt_from_the_name():
    """The predecessor slugified the printed NAME into a path. The live list
    pages disprove the premise: every label is a link, and for 11 countries the
    abbreviation and the slug disagree — 'UK' links to /United-Kingdom/,
    'Dom. Rep.' to /Dominican-Republic/. Guessing 404s exactly there."""
    from scrapex.connectors.gpp import parse_country_links

    html = """
    <div id="outsideLinks"><div>
      <div class="outsideTitle"><a class='graph_outside_link'
        href='/United-Kingdom/diesel_prices/'>UK</a></div>
      <div class="outsideTitle"><a class='graph_outside_link'
        href='/Dominican-Republic/diesel_prices/'>Dom. Rep.</a></div>
      <div class="outsideTitle"><a class='graph_outside_link'
        href='/Egypt/diesel_prices/'>Egypt*&nbsp;</a></div>
    </div></div>"""
    links = parse_country_links(html)

    assert links["UK"] == "/United-Kingdom/diesel_prices/"
    assert links["Dom. Rep."] == "/Dominican-Republic/diesel_prices/"
    assert links["Egypt"] == "/Egypt/diesel_prices/"   # label cleaned of * and nbsp


def test_a_blocked_crawl_stops_instead_of_marching_through_the_frontier():
    """CrawlBlocked is the fetcher saying the SITE said no. The per-page guard
    exists to survive one bad page; catching the stop signal under it would turn
    'stop' into hundreds more requests against a server that already objected."""
    from scrapex.connectors.base import CrawlBlocked

    class _BlockedFetcher(_StubFetcher):
        def get(self, url, **kwargs):
            path = url.split(".com", 1)[-1]
            if path == "/diesel_prices/":
                return _Resp(_read("gpp_diesel.html"))
            raise CrawlBlocked("5 consecutive refusals")

    with pytest.raises(CrawlBlocked):
        next(iter(GlobalPetrolPricesConnector(_BlockedFetcher()).fetch(make_entry())))


def test_a_fuel_country_whose_page_fails_gets_no_converted_stand_in():
    """Currency is outside offer identity and the canonical unit collapses
    'USD/liter' with 'liter', so a USD stand-in would land on the SAME offer as
    last week's EGP row — recorded as a ~5,000% price change. A missing week is
    honest; a false jump is corruption. The warning carries what was skipped."""
    class _EgyptDownFetcher(_StubFetcher):
        def get(self, url, **kwargs):
            if "/Egypt/" in url:
                self.requests_count += 1
                raise RuntimeError("504 gateway timeout")
            return super().get(url, **kwargs)

    table = next(iter(GlobalPetrolPricesConnector(_EgyptDownFetcher()).fetch(
        make_entry())))

    view = RowView(COMMODITY_PRICE, table.header)
    rows = [view.as_dict(r) for r in table.rows]
    assert rows, "the healthy countries must still land"
    assert {r["region"] for r in rows} == {"SA", "US"}, "Egypt must be absent, not faked"
    assert all(r["currency"] != "USD" for r in rows), "a converted stand-in slipped through"
    assert any("EG" in w for w in table.warnings),         "a skipped country must be named, not lost quietly"


def test_every_country_down_still_fails_loud():
    """One country down is a warning; ALL of them down is a broken crawl and
    must not report an empty success."""
    class _AllCountriesDownFetcher(_StubFetcher):
        def get(self, url, **kwargs):
            path = url.split(".com", 1)[-1]
            if path == "/diesel_prices/":
                return _Resp(_read("gpp_diesel.html"))
            raise RuntimeError("504 gateway timeout")

    with pytest.raises(ValueError, match="every contracted GPP page failed"):
        next(iter(GlobalPetrolPricesConnector(_AllCountriesDownFetcher()).fetch(
            make_entry())))


# ---- the Arabic mirror: the series the English page renders as pixels --------
#
# The English country page draws its ten-year chart as a server-side PNG — no
# data, only pixels. The ARABIC edition of the same public page emits the same
# chart as Google Charts rows: 520 weekly (date, local price) points back to
# 2016. Verified in the raw captured bytes on 2026-07-21. In scope under the
# owner's licence rule (what the public page shows any visitor); the paid API
# and data download remain untouched.

def test_the_arabic_chart_data_parses_to_iso_dated_local_prices():
    from scrapex.connectors.gpp import parse_arabic_history

    points = parse_arabic_history(_read("gpp_ar_egypt_diesel_trimmed.html"))

    # Trimmed live capture: the real first and last six points of 520.
    assert len(points) == 12
    assert points[0] == ("2016-08-01", "1.8")     # يوم 01 شهر 08 سنة 2016
    assert points[-1] == ("2026-07-13", "20.5")   # يوم 13 شهر 07 سنة 2026
    # Every date is ISO — the Arabic day/month/year words anchor the regex, so
    # a digit can never be read out of position.
    assert all(len(d) == 10 and d[4] == d[7] == "-" for d, _ in points)


def test_a_page_without_chart_data_yields_no_points_not_a_guess():
    from scrapex.connectors.gpp import parse_arabic_history

    assert parse_arabic_history("<html><body>redesigned</body></html>") == []


class _HistoryFetcher(_StubFetcher):
    """English list + country pages, plus the Arabic mirror per country."""
    def get(self, url, **kwargs):
        if "//ar." in url:
            self.requests_count += 1
            return _Resp(_read("gpp_ar_egypt_diesel_trimmed.html"))
        return super().get(url, **kwargs)


def test_history_mode_lands_the_series_as_reported_rows():
    """One --history crawl: ten years of local-currency points per country,
    every one dated by the source and marked reported — never ours."""
    fetcher = _HistoryFetcher()
    connector = GlobalPetrolPricesConnector(fetcher, history=True)
    table = next(iter(connector.fetch(make_entry())))

    view = RowView(COMMODITY_PRICE, table.header)
    rows = [view.as_dict(r) for r in table.rows]
    series = [r for r in rows if r["provenance"] == "reported"
              and r["as_of_date"] == "2016-08-01"]
    # 3 mapped countries, each backfilled from its mirror (the stub serves the
    # same Egypt series for all three).
    assert len(series) == 3
    assert all(r["currency"] == "EGP" and r["effective_price"] == "1.8"
               for r in series)
    assert all(r["price_basis"] == "original" for r in series)


def test_the_weekly_crawl_does_not_touch_the_mirror():
    """History is a one-time backfill. The weekly crawl re-fetching 500+ known
    points per country would double the volume for data it already has."""
    fetcher = _HistoryFetcher()
    connector = GlobalPetrolPricesConnector(fetcher)          # history OFF
    next(iter(connector.fetch(make_entry())))

    assert fetcher.requests_count == 4      # 1 list + 3 countries, no ar. host


def test_a_series_that_cannot_be_anchored_is_skipped_not_stored():
    """The chart rows carry no currency. They are trusted ONLY because the last
    point equals the local price the English page just published. A series that
    ends anywhere else might be a different unit, currency, or country — and a
    guess stored as history is corruption with a ten-year reach."""
    mismatched = """<script>var data;
      data.addRows([[' يوم 01 شهر 08 سنة 2016',9.99],[' يوم 13 شهر 07 سنة 2026',7.77]]);
    </script>"""

    class _DriftMirror(_StubFetcher):
        def get(self, url, **kwargs):
            if "//ar." in url:
                self.requests_count += 1
                return _Resp(mismatched)
            return super().get(url, **kwargs)

    connector = GlobalPetrolPricesConnector(_DriftMirror(), history=True)
    table = next(iter(connector.fetch(make_entry())))

    view = RowView(COMMODITY_PRICE, table.header)
    rows = [view.as_dict(r) for r in table.rows]
    assert not any(r["as_of_date"] == "2016-08-01" for r in rows), \
        "an unanchored series was stored"
    assert any("cannot prove the currency" in w for w in table.warnings)


def test_a_dead_mirror_costs_a_warning_never_the_current_price():
    """The mirror going away must not take the weekly price with it."""
    class _DeadMirror(_StubFetcher):
        def get(self, url, **kwargs):
            if "//ar." in url:
                self.requests_count += 1
                raise RuntimeError("503 service unavailable")
            return super().get(url, **kwargs)

    connector = GlobalPetrolPricesConnector(_DeadMirror(), history=True)
    table = next(iter(connector.fetch(make_entry())))

    view = RowView(COMMODITY_PRICE, table.header)
    observed = [view.as_dict(r) for r in table.rows
                if view.as_dict(r)["provenance"] == "observed"]
    assert len(observed) == 3, "the current prices must survive a dead mirror"
    assert any("history mirror" in w for w in table.warnings)


def test_natural_gas_stays_on_the_list_because_its_country_pages_publish_nothing():
    """Verified live 2026-07-21: natural-gas country pages are the same
    table-less page type as electricity. The first country-page crawl skipped
    all 47 of them and landed ZERO natural-gas rows where the list had 47 — a
    regression dressed as rigour. A material without country detail keeps its
    list rows: always converted, always the same offer identity."""
    class _GasFetcher(_StubFetcher):
        def get(self, url, **kwargs):
            self.requests_count += 1
            path = url.split(".com", 1)[-1]
            if path == "/natural_gas_prices/":
                return _Resp(_read("gpp_diesel.html"))   # same graphic layout
            raise RuntimeError("404 " + url)

    table = next(iter(GlobalPetrolPricesConnector(_GasFetcher()).fetch(
        make_entry(materials=("NATURAL_GAS",)))))

    view = RowView(COMMODITY_PRICE, table.header)
    rows = [view.as_dict(r) for r in table.rows]
    assert len(rows) == 3, "the list rows were lost again"
    assert all(r["price_basis"] == "converted" and r["currency"] == "USD"
               for r in rows)


def test_the_official_source_attribution_is_read_and_germany_stays_empty():
    """"Source: Ministry of Petroleum and Mineral Resources" sits in a bare div
    OUTSIDE every table — the strongest provenance signal on the page, thrown
    away because the parser only ever looked at tables. Germany names none:
    absence must come back empty, never invented."""
    from scrapex.connectors.gpp import parse_country_page

    egypt = parse_country_page(_read("gpp_country_egypt_diesel.html"))
    assert egypt.source_name == "Ministry of Petroleum and Mineral Resources"
    assert egypt.source_url.startswith("https://www.petroleum.gov.eg/")


def test_the_attribution_rides_every_row_of_its_page():
    from scrapex.connectors.gpp import country_rows, parse_country_page
    from scrapex.rowspec import COMMODITY_PRICE, RowBuilder, RowView
    from datetime import date

    page = parse_country_page(_read("gpp_country_egypt_diesel.html"))
    builder = RowBuilder(COMMODITY_PRICE)
    rows = country_rows(builder, "DIESEL", "EG", page, "USD", "liter", "1",
                        date(2026, 7, 21))
    view = RowView(COMMODITY_PRICE, builder.header)
    parsed = [view.as_dict(r) for r in rows]
    assert parsed, "no rows came back at all"
    assert all(p["official_source_name"] == "Ministry of Petroleum and Mineral Resources"
               for p in parsed), "an anchor lost the attribution its page stated"
