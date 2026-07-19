"""static-html-table family connector — globalpetrolprices (ENGINEERING.md A3).

globalpetrolprices publishes one weekly list page per energy type: ~180 countries,
each with a single current price. This is a COMMODITY_PRICE source: one row per
(material, country). Country names map to ISO alpha-2 regions via pycountry (the
[commodity] extra), so the warehouse region joins feed_assignment directly.

LICENSE (owner decision, T6 / scope: latest_only): take ONLY the latest published
price, never the paid historical series. This connector fetches only the current
list page; history accrues from OUR weekly crawls (ingest stamps business_date =
our crawl date), never from their feed.

POSITIONAL PARSING (Q4): the page renders country labels and price bars as two
PARALLEL lists, both sorted by price, with no shared id to join on — so position
is the only link available. That makes an equal-length check load-bearing: a
mismatch means the layout moved and zipping would silently mis-attribute every
price to the wrong country.

Selectors VERIFIED against the live page 2026-07-19: 169 countries, 169 values,
pairing spot-checked (Venezuela 0.004, Egypt 0.404, Saudi Arabia 0.476 USD/litre).
"""
from __future__ import annotations

import re
from typing import Iterable

from bs4 import BeautifulSoup

from ..config import SourceEntry
from ..rowspec import COMMODITY_PRICE, RowBuilder
from ..vocab import ExtractKind
from .base import HttpFetcher, ScrapedTable

# material_key -> (page slug, price unit). Fuels are per-liter; power is per-kWh.
_PAGES = {
    "DIESEL":      ("diesel_prices",      "USD/liter"),
    "GASOLINE":    ("gasoline_prices",    "USD/liter"),
    "LPG":         ("lpg_prices",         "USD/liter"),
    "ELECTRICITY": ("electricity_prices", "USD/kWh"),
    "NATURAL_GAS": ("natural_gas_prices", "USD/kWh"),
}

# Verified against the live page. Country labels live in their own column;
# the price sits inside each graph bar as its only child div.
_COUNTRY_SEL = "#outsideLinks a"
_BAR_SEL = "#graphic div > div"
_PRICE_TEXT = re.compile(r"^\d+(?:[.,]\d+)?$")

# GPP English names that pycountry.lookup doesn't resolve on its own.
_REGION_OVERRIDES = {
    "South Korea": "KR", "North Korea": "KP", "Russia": "RU", "Iran": "IR",
    "Syria": "SY", "Venezuela": "VE", "Bolivia": "BO", "Tanzania": "TZ",
    "Vietnam": "VN", "Laos": "LA", "Moldova": "MD", "Brunei": "BN",
    "Ivory Coast": "CI", "DR Congo": "CD", "Republic of the Congo": "CG",
    "Czech Republic": "CZ", "Cape Verde": "CV", "Myanmar": "MM",
    "Palestine": "PS", "Taiwan": "TW", "Kosovo": "XK",
}


def parse_price_table(html: str, country_sel: str = _COUNTRY_SEL,
                      bar_sel: str = _BAR_SEL) -> list[tuple[str, str]]:
    """(country_label, price_text) pairs, zipped POSITIONALLY.

    Raises rather than emit misaligned rows (Q4) — and, just as importantly,
    raises when the selectors match NOTHING. An empty-vs-empty comparison passes
    a naive equal-length check, which is exactly how a broken selector once
    produced a silent zero-row "success" instead of a visible failure.
    """
    soup = BeautifulSoup(html, "lxml")
    names = [_clean_country(a.get_text(strip=True)) for a in soup.select(country_sel)]

    values: list[str] = []
    for bar in soup.select(bar_sel):
        inner = bar.find_all("div", recursive=False)
        if len(inner) == 1:                      # a bar carries exactly one label
            text = inner[0].get_text(strip=True)
            if _PRICE_TEXT.match(text):
                values.append(text)

    if not names or not values:
        raise ValueError(
            f"GPP layout drift: selectors matched nothing "
            f"({len(names)} country labels, {len(values)} price values) — "
            "the page structure has changed")
    if len(names) != len(values):
        raise ValueError(
            f"GPP layout drift: {len(names)} country labels vs {len(values)} price "
            "values (positional parse would misalign — refusing)")
    return list(zip(names, values))


def _clean_country(label: str) -> str:
    """'Saudi Arabia\\xa0*' -> 'Saudi Arabia'. The asterisk is a footnote marker
    on the page, not part of the country name, and would defeat the ISO lookup."""
    return label.replace(" ", " ").strip().rstrip("*").strip()


def _region(country: str) -> str | None:
    """Country name -> ISO alpha-2, or None when unmapped (skipped upstream)."""
    override = _REGION_OVERRIDES.get(country)
    if override:
        return override
    try:
        import pycountry
    except ImportError as exc:  # lazy: the extra is only needed to crawl this family
        raise RuntimeError(
            "static-html-table needs the commodity extra: pip install -e .[commodity]"
        ) from exc
    try:
        return pycountry.countries.lookup(country).alpha_2
    except LookupError:
        return None


def _contracted_materials(source: SourceEntry) -> list[str]:
    """The _PAGES we are contracted to crawl (manifest materials, else all)."""
    wanted: set[str] = set()
    for spec in source.extract:
        if spec.kind == ExtractKind.COMMODITY_PRICE:
            wanted.update(spec.materials or _PAGES.keys())
    return [m for m in _PAGES if m in wanted]


class GlobalPetrolPricesConnector:
    connector_id = "static-html-table"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        builder = RowBuilder(COMMODITY_PRICE)
        base = source.base_url.rstrip("/")
        currency = source.currency or "USD"
        vat = "1" if source.vat_mode.value == "incl" else "0"
        rows: list[list[str]] = []
        page_errors: list[str] = []

        for material_key in _contracted_materials(source):
            slug, unit = _PAGES[material_key]
            url = f"{base}/{slug}/"
            # The PARSE belongs inside the guard too: a layout drift on one fuel
            # page must not discard the four sibling pages already parsed (Q3).
            try:
                html = self._fetcher.get(url).text
                pairs = parse_price_table(html)
            except Exception as exc:  # noqa: BLE001 — one page down never kills the crawl
                page_errors.append(f"{material_key}: {exc}")
                continue
            for country, price in pairs:
                region = _region(country)
                if region is None:
                    continue  # unmapped country — skipped (broad reference; owner cares SA/EG)
                row = _row(builder, material_key, region, price, currency, unit, vat)
                if row is not None:
                    rows.append(row)

        # A total layout change still fails LOUD (Q4) — but only when nothing at
        # all could be parsed, never when some pages succeeded.
        if page_errors and not rows:
            raise ValueError("every contracted GPP page failed: " + "; ".join(page_errors))

        yield ScrapedTable(source.source_key, COMMODITY_PRICE.kind, base, builder.header, rows)


def _row(builder: RowBuilder, material_key: str, region: str, price: str,
         currency: str, unit: str, vat: str):
    if not any(ch.isdigit() for ch in price):
        return None  # '-' / 'N/A' cells — skip, don't feed the money parser garbage
    return builder.row(
        material_key=material_key, region=region, currency=currency, unit=unit,
        vat_included=vat, effective_price=price, observed_label="",
    )
