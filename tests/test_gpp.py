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
from scrapex.rowspec import COMMODITY_PRICE, RowView
from scrapex.vocab import ExtractKind, ExtractScope

FX = Path(__file__).parent / "fixtures"


def _read(name): return (FX / name).read_text(encoding="utf-8")


class _Resp:
    def __init__(self, text): self.text = text


class _StubFetcher:
    def __init__(self): self.requests_count = 0
    def get(self, url, **kwargs):
        self.requests_count += 1
        if url.endswith("/diesel_prices/"):
            return _Resp(_read("gpp_diesel.html"))
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
    fetcher = _StubFetcher()
    table = next(iter(GlobalPetrolPricesConnector(fetcher).fetch(make_entry())))
    assert fetcher.requests_count == 1          # only the DIESEL page is contracted here
    assert len(table.rows) == 3                 # Atlantis (unmapped) skipped
    view = RowView(COMMODITY_PRICE, table.header)

    egypt = view.as_dict(table.rows[0])
    assert egypt["material_key"] == "DIESEL" and egypt["region"] == "EG"
    assert egypt["effective_price"] == "0.404" and egypt["currency"] == "USD"
    assert egypt["unit"] == "USD/liter" and egypt["vat_included"] == "1"

    ksa = view.as_dict(table.rows[1])
    assert ksa["region"] == "SA" and ksa["effective_price"] == "0.476"


def test_one_failing_page_does_not_kill_the_crawl():
    """Q3 resilience: the GASOLINE page 404s in the stub; the DIESEL rows still land."""
    fetcher = _StubFetcher()
    table = next(iter(GlobalPetrolPricesConnector(fetcher).fetch(
        make_entry(materials=("DIESEL", "GASOLINE")))))
    assert fetcher.requests_count == 2       # both pages attempted
    assert len(table.rows) == 3              # the DIESEL page survived the GASOLINE failure
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
    assert len(table.rows) == 3            # the DIESEL page survived
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
    # one product (DIESEL), one implicit variant, three region offers:
    assert (result.products, result.variants, result.observations) == (1, 1, 3)
    assert offers == 3
