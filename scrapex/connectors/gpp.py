"""static-html-table family connector — globalpetrolprices (ENGINEERING.md A3).

globalpetrolprices publishes one weekly list page per energy type: ~180 countries,
each with a single current price. This is a COMMODITY_PRICE source: one row per
(material, country). Country names map to ISO alpha-2 regions via pycountry (the
[commodity] extra), so the warehouse region joins feed_assignment directly.

LICENSE (owner decision, revised 2026-07-20): take what the PUBLIC PAGE shows any
visitor, and nothing more. Their paid product is the full weekly series back to
2016, reachable through the API and the data download — this connector touches
neither. The three past figures printed on each country page are published free
to every reader, so they are in scope; they are stored as 'reported', never as
something we watched happen.

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
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from bs4 import BeautifulSoup

from ..config import SourceEntry
from ..rowspec import COMMODITY_PRICE, RowBuilder
from ..vocab import ExtractKind
from .base import CrawlBlocked, HttpFetcher, ScrapedTable

# material_key -> (page slug, price unit, rank-table column).
# Fuels are per-liter; power is per-kWh.
#
# `column` is None for the graphic layout (the parallel-list pages) and an int
# for the #RankTable layout. Electricity uses the table and publishes TWO
# materially different rates per country — residential and business, e.g. Germany
# 0.406 vs 0.283 — so they are two SERIES, not one price with a lost qualifier.
# Collapsing them would silently pick one and call it "the" electricity price.
# The 4th flag says whether this material's COUNTRY pages publish the price in
# local currency. Verified live 2026-07-21: diesel/gasoline/LPG pages carry the
# "Price (EGP/Liter)" table; electricity and natural-gas country pages are a
# different page type with no price table at all — the parser reads them as
# empty, and their first crawl under the country-page design skipped all 47
# natural-gas countries with a swallowed warning each, landing ZERO rows where
# the list had 47. A material without country detail stays on its list page,
# every week, so its offers are ALWAYS the same converted-USD series — one
# stable identity, honestly marked, rather than a mix that reads as jumps.
_PAGES = {
    "DIESEL":                ("diesel_prices",      "USD/liter", None, True),
    "GASOLINE":              ("gasoline_prices",    "USD/liter", None, True),
    "LPG":                   ("lpg_prices",         "USD/liter", None, True),
    "ELECTRICITY":           ("electricity_prices", "USD/kWh",   1,    False),
    "ELECTRICITY_BUSINESS":  ("electricity_prices", "USD/kWh",   2,    False),
    "NATURAL_GAS":           ("natural_gas_prices", "USD/kWh",   None, False),
}

# Verified against the live page. Country labels live in their own column;
# the price sits inside each graph bar as its only child div.
_COUNTRY_SEL = "#outsideLinks a"
_BAR_SEL = "#graphic div > div"
# The electricity page carries neither of the above — it publishes a real table.
_RANK_TABLE_SEL = "#RankTable"
_PRICE_TEXT = re.compile(r"^\d+(?:[.,]\d+)?$")

# GPP English names that pycountry.lookup doesn't resolve on its own.
_REGION_OVERRIDES = {
    "South Korea": "KR", "North Korea": "KP", "Russia": "RU", "Iran": "IR",
    "Syria": "SY", "Venezuela": "VE", "Bolivia": "BO", "Tanzania": "TZ",
    "Vietnam": "VN", "Laos": "LA", "Moldova": "MD", "Brunei": "BN",
    "Ivory Coast": "CI", "DR Congo": "CD", "Republic of the Congo": "CG",
    "Czech Republic": "CZ", "Cape Verde": "CV", "Myanmar": "MM",
    "Palestine": "PS", "Taiwan": "TW", "Kosovo": "XK",
    # Abbreviated and older labels the live pages actually print. Every one of
    # these was silently dropped: checking all five pages on 2026-07-20 found
    # 38 rows lost, with Turkey and the UK missing from ALL FIVE energy types.
    # The table cells are narrow, so the site shortens names — a shape no
    # hand-written fixture would ever have thought to include.
    "Turkey": "TR", "UK": "GB", "UAE": "AE", "Burma": "MM",
    "Curacao": "CW", "Swaziland": "SZ", "Trinidad & Tobago": "TT",
    "Dom. Rep.": "DO", "Bosnia & Herz.": "BA", "N. Maced.": "MK",
    "C. Afr. Rep.": "CF",
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


def parse_rank_table(html: str, column: int) -> list[tuple[str, str]]:
    """(country, price) from the #RankTable layout, joined by ROW, not position.

    The electricity page does not use the graphic at all: it publishes a real
    table whose header is `Countries | Residential ... | Business ...`. That was
    invisible until the parser was run against the live page, where it matched
    nothing and the whole energy type silently produced zero rows.

    A row-wise join needs none of the positional guarding above — the country and
    its price are in the same <tr>, so they cannot drift apart. Blank cells are
    real (some countries publish only one of the two rates) and are skipped.
    """
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one(_RANK_TABLE_SEL)
    if table is None:
        raise ValueError(
            f"GPP layout drift: no {_RANK_TABLE_SEL} on this page — "
            "the page structure has changed")
    pairs: list[tuple[str, str]] = []
    for row in table.find_all("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) <= column:
            continue
        country = _clean_country(cells[0].get_text(" ", strip=True))
        price = cells[column].get_text(" ", strip=True)
        if country and _PRICE_TEXT.match(price):
            pairs.append((country, price))
    if not pairs:
        raise ValueError(
            f"GPP layout drift: {_RANK_TABLE_SEL} column {column} yielded no "
            "priced rows — the page structure has changed")
    return pairs


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

    def __init__(self, fetcher: HttpFetcher, *, history: bool = False) -> None:
        self._fetcher = fetcher
        # One-time backfill mode (owner decision 2026-07-21): also read each
        # country's ARABIC mirror, whose chart data carries the full weekly
        # series in local currency. Off for the weekly crawl — the series only
        # grows by the point the weekly crawl already collects, so re-fetching
        # 500+ known points every week would double the volume for nothing.
        self._history = history

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        builder = RowBuilder(COMMODITY_PRICE)
        base = source.base_url.rstrip("/")
        currency = source.currency or "USD"
        vat = "1" if source.vat_mode.value == "incl" else "0"
        today = date.today()
        rows: list[list[str]] = []
        page_errors: list[str] = []
        unmapped: set[str] = set()

        pages: dict[str, str] = {}   # slug -> html, so two materials on one page
        for material_key in _contracted_materials(source):            # fetch it once
            slug, unit, column, country_detail = _PAGES[material_key]
            url = f"{base}/{slug}/"
            # The PARSE belongs inside the guard too: a layout drift on one fuel
            # page must not discard the four sibling pages already parsed (Q3).
            try:
                if slug not in pages:
                    pages[slug] = self._fetcher.get(url).text
                html = pages[slug]
                pairs = (parse_rank_table(html, column) if column is not None
                         else parse_price_table(html))
            except CrawlBlocked:
                # The fetcher counted five straight refusals: the site said no.
                # This guard exists to survive ONE bad page, and catching the
                # stop signal under it would turn "stop" into hundreds more
                # requests against a server that already objected.
                raise
            except Exception as exc:  # noqa: BLE001 — one page down never kills the crawl
                page_errors.append(f"{material_key}: {exc}")
                continue

            # For a material WITH country detail, the list page is the FRONTIER
            # and the CANARY, not the price: its figures are conversions the
            # site computed for a default dropdown selection, and the published
            # price lives on each country's own page. Electricity and natural
            # gas have no such pages (see _PAGES), so their list rows remain
            # the record, honestly marked price_basis='converted'.
            links = parse_country_links(html) if country_detail else {}

            for country, price in pairs:
                region = _region(country)
                if region is None:
                    # A country we cannot map is a row we cannot keep, but it is
                    # not a row we may lose quietly: that is how Turkey and the
                    # UK went missing from all five energy types unnoticed.
                    unmapped.add(country)
                    continue

                href = links.get(country, "")
                if not href:
                    # Electricity, or a label the list page did not link. The
                    # converted figure is all there is, and the row says so.
                    row = _row(builder, material_key, region, price, currency, unit, vat)
                    if row is not None:
                        rows.append(row)
                    continue

                # NO converted fallback for a fuel country whose page fails.
                # Currency is excluded from offer identity and the canonical
                # unit collapses 'USD/liter' and 'liter' together, so a USD
                # stand-in would land on the SAME offer as last week's EGP row
                # and be recorded as a ~5,000% price change. A missing week is
                # honest; a false jump is data corruption. The warning carries
                # what was skipped.
                try:
                    detail = parse_country_page(self._fetcher.get(base + href).text)
                except CrawlBlocked:
                    raise
                except Exception as exc:  # noqa: BLE001 — isolate per country
                    page_errors.append(f"{material_key}/{region}: {exc}")
                    continue
                if not (detail.price and detail.currency):
                    page_errors.append(
                        f"{material_key}/{region}: country page published no "
                        "local price — no row this week (never the conversion)")
                    continue
                rows.extend(country_rows(builder, material_key, region, detail,
                                         currency, unit, vat, today))

                if self._history:
                    rows.extend(self._history_rows(
                        builder, material_key, region, detail, base, href,
                        currency, unit, vat, page_errors))

        # A total layout change still fails LOUD (Q4) — but only when nothing at
        # all could be parsed, never when some pages succeeded.
        if page_errors and not rows:
            raise ValueError("every contracted GPP page failed: " + "; ".join(page_errors))
        return self._finish(source, base, builder, rows, page_errors, unmapped)

    def _history_rows(self, builder: RowBuilder, material_key: str, region: str,
                      detail: "CountryPrice", base: str, href: str,
                      currency: str, unit: str, vat: str,
                      page_errors: list[str]) -> list[list[str]]:
        """The full weekly series from the Arabic mirror, as reported rows.

        Same path, different host — the Arabic edition mirrors the English URL
        shape exactly. The series carries no currency of its own, so it is
        accepted ONLY when its last point equals the local price the English
        page just published: that anchor proves the series is in the same
        currency and unit, and a series that cannot be anchored is skipped with
        a warning rather than stored on a guess.
        """
        ar_url = base.replace("//www.", "//ar.", 1) + href
        try:
            points = parse_arabic_history(self._fetcher.get(ar_url).text)
        except CrawlBlocked:
            raise
        except Exception as exc:  # noqa: BLE001 — history is additive, not vital
            page_errors.append(f"{material_key}/{region}: history mirror: {exc}")
            return []
        if not points:
            page_errors.append(
                f"{material_key}/{region}: history mirror carried no chart data")
            return []
        try:
            anchored = float(points[-1][1]) == float(detail.price)
        except ValueError:
            anchored = False
        if not anchored:
            page_errors.append(
                f"{material_key}/{region}: history series ends at "
                f"{points[-1][1]!r} but the page publishes {detail.price!r} — "
                "cannot prove the currency; series skipped, not guessed")
            return []
        # CHANGE POINTS ONLY (owner rule: history is real changes, and the
        # backfill must follow it too). The site samples weekly, so a fixed
        # price repeats for years — Egypt diesel was 522 stored points holding
        # 13 distinct price levels. The first point and each point whose price
        # differs from the one before it carry ALL the information: between
        # two kept points the price held, by construction. Measured across the
        # whole backfill this drops 135,774 rows to 59,541.
        out: list[list[str]] = []
        previous_value: str | None = None
        for as_of, value in points:
            if previous_value is not None and value == previous_value:
                continue
            previous_value = value
            row = _row(builder, material_key, region, "", currency, unit, vat,
                       detail, as_of=as_of, provenance="reported", value=value)
            if row is not None:
                out.append(row)
        return out

    def _finish(self, source: SourceEntry, base: str, builder: RowBuilder,
                rows: list[list[str]], page_errors: list[str],
                unmapped: set[str]) -> Iterable[ScrapedTable]:

        warnings = list(page_errors)
        if unmapped:
            warnings.append(
                f"{len(unmapped)} country label(s) could not be mapped to an ISO "
                f"code and their prices were dropped: {', '.join(sorted(unmapped))}")
        yield ScrapedTable(source.source_key, COMMODITY_PRICE.kind, base,
                           builder.header, rows, warnings=warnings)


def _row(builder: RowBuilder, material_key: str, region: str, price: str,
         currency: str, unit: str, vat: str, country: "CountryPrice | None" = None,
         *, as_of: str = "", provenance: str = "observed", value: str = ""):
    """One commodity row. `country` carries what the country page published.

    Without it the row is the list-page figure: a conversion the site computed
    for a default currency and unit, which price_basis records honestly as
    'converted'. With it, the ORIGINAL price and its own currency are carried
    alongside, and the row is 'original'.
    """
    amount = value or price
    if not any(ch.isdigit() for ch in amount):
        return None  # '-' / 'N/A' cells — skip, don't feed the money parser garbage
    fields = dict(
        material_key=material_key, region=region, currency=currency, unit=unit,
        vat_included=vat, effective_price=amount, observed_label="",
        provenance=provenance, as_of_date=as_of,
        price_basis="converted",
    )
    if country and country.price and country.currency:
        # The price becomes the one the SOURCE publishes, in the currency it
        # publishes it in. Carrying an EGP amount in a field labelled USD — which
        # is what pairing them naively does — is the exact corruption this whole
        # change exists to remove. A different currency is a different offer, and
        # the warehouse is right to treat it as one.
        fields.update(
            currency=country.currency,
            original_price=amount,
            original_currency=country.currency,
            source_date=country.source_date,
            price_basis="original",
        )
        if provenance == "observed" and country.usd_price:
            # Only the CURRENT price has the printed USD twin; anchors do not.
            fields["converted_usd_price"] = country.usd_price
        if country.unit:
            fields["unit"] = country.unit
    if country:
        # Rides every row of the page it was read from, anchors included: the
        # attribution belongs to the page's figures as a set, and an absent one
        # stays empty — "not stated" is an answer, invention is not.
        fields.update(official_source_name=country.source_name,
                      official_source_url=country.source_url)
    return builder.row(**fields)


def country_rows(builder: RowBuilder, material_key: str, region: str,
                 country: "CountryPrice", currency: str, unit: str, vat: str,
                 today: date) -> list[list[str]]:
    """The current price plus whatever history the country page published.

    The past figures become their OWN rows, dated to the day they refer to and
    marked 'reported', so a year of history lands on the first crawl and none of
    it pretends to be something we watched happen.
    """
    rows: list[list[str]] = []
    current = _row(builder, material_key, region, country.price or "", currency,
                   unit, vat, country)
    if current is not None:
        rows.append(current)
    # The page stamps its own "Last update" — the day the price took effect,
    # which is not the day we happened to read it. That dating is the source's
    # claim, so it lands the way every source claim does: a reported row on that
    # date. Idempotent across weeks (same date + same price = same dedupe key),
    # and our own observation above keeps our crawl date untouched.
    if country.source_date and country.price:
        anchor = _row(builder, material_key, region, "", currency, unit, vat,
                      country, as_of=country.source_date, provenance="reported",
                      value=country.price)
        if anchor is not None:
            rows.append(anchor)
    for days_ago, past_price in country.history:
        row = _row(builder, material_key, region, "", currency, unit, vat, country,
                   as_of=(today - timedelta(days=days_ago)).isoformat(),
                   provenance="reported", value=past_price)
        if row is not None:
            rows.append(row)
    return rows


# ---- the country page: where the price is actually published -----------------
#
# The list pages we crawl weekly render EVERY figure through two dropdowns —
# <select name="currency"> with 156 options and <select name="literGalon"> with
# four. So the USD-per-litre number we have been storing is a conversion the
# site computed for a default selection, not what the source published.
#
# The per-country page states the real thing, and a great deal more, in one
# request (verified live 2026-07-20 on /Egypt/diesel_prices/):
#
#   Price (EGP/Liter)  20.50     the published price, in the currency it is set in
#   Current price       0.40     the USD conversion, for reference
#   Last update   2026-07-13     the SOURCE's date, not our crawl date
#   Data available from 2016-08-01
#   One month ago      20.50
#   Three months ago   20.50
#   One year ago       15.50     +32.3%
#   ...plus eight analytics (correlation with crude, with the USD rate, ...)
#
# The three past figures are the reason an initial crawl is worth its requests:
# they are a year of history on day one, instead of fifty-two weeks of waiting.
# They are NOT our observations — we did not watch that price in July 2025 — so
# they are stored with provenance='reported' (migration 0019) and can never pass
# for something we saw.
#
# LICENCE: only what the public page shows any visitor. Their paid product is
# the full weekly series back to 2016, reachable through the API and the data
# download; this connector touches neither.

_AGO_LABELS = {
    "one month ago": 30,
    "three months ago": 91,
    "six months ago": 182,
    "one year ago": 365,
}
_CURRENCY_UNIT = re.compile(r"Price\s*\(([A-Za-z]{3})\s*/\s*([^)]+)\)", re.I)


@dataclass(frozen=True)
class CountryPrice:
    """Everything one country page publishes about one energy type."""

    price: str = ""            # in the source's own currency
    currency: str = ""
    unit: str = ""
    usd_price: str = ""        # the site's own conversion, kept for reference
    source_date: str = ""      # what the site calls "Last update"
    available_from: str = ""
    frequency: str = ""
    history: tuple[tuple[int, str], ...] = ()   # (days ago, price)
    analytics: tuple[tuple[str, str], ...] = ()
    # "Source: Ministry of Petroleum and Mineral Resources" + link — the
    # official body the page names for its figure. Absent on some countries
    # (Germany names none): empty means "not stated", never invented.
    source_name: str = ""
    source_url: str = ""


def _rows_of(table) -> list[list[str]]:
    return [[c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            for tr in table.find_all("tr")]


def parse_country_page(html: str) -> CountryPrice:
    """Read one country page. Absent fields come back empty, never guessed."""
    soup = BeautifulSoup(html, "lxml")
    price = currency = unit = usd = source_date = available = frequency = ""
    history: list[tuple[int, str]] = []
    analytics: list[tuple[str, str]] = []

    for table in soup.find_all("table"):
        rows = _rows_of(table)
        if not rows:
            continue
        header = " ".join(rows[0]).lower()
        labelled = {r[0].strip().lower(): r[1:] for r in rows[1:] if len(r) >= 2}

        # The overview table: USD figure, the source's own date, coverage.
        if "current price" in labelled and "last update" in labelled:
            usd = labelled["current price"][0]
            source_date = labelled["last update"][0]
            available = labelled.get("data availability from", [""])[0]
            frequency = labelled.get("data frequency", [""])[0]
            continue

        # The local-currency table. Its HEADER carries the currency and unit —
        # "Price (EGP/Liter)" — which is the only place either is stated.
        found = _CURRENCY_UNIT.search(" ".join(rows[0]))
        if found and "current price" in labelled:
            currency = found.group(1).upper()
            unit = found.group(2).strip().lower()
            price = labelled["current price"][0]
            for label, days in _AGO_LABELS.items():
                if label in labelled and labelled[label][0]:
                    history.append((days, labelled[label][0]))
            continue

        if "analytics" in header:
            analytics.extend((r[0], r[1]) for r in rows[1:] if len(r) >= 2)

    # The official attribution is NOT in any table: it is a bare div right
    # after the metadata table — `Source: <a href>Ministry of ...</a>`. It is
    # the strongest provenance signal on the page and was thrown away for
    # exactly that reason: the parser only ever looked at tables. Germany's
    # page names none; absence stays empty rather than being invented.
    source_name = source_url = ""
    marker = soup.find(string=re.compile(r"^\s*Source:\s*$|^\s*Source:"))
    if marker is not None and marker.parent is not None:
        link = marker.parent.find("a")
        if link is not None and link.get_text(strip=True):
            source_name = link.get_text(" ", strip=True)
            source_url = (link.get("href") or "").strip()

    return CountryPrice(price=price, currency=currency, unit=unit, usd_price=usd,
                        source_date=source_date, available_from=available,
                        frequency=frequency, history=tuple(history),
                        analytics=tuple(analytics),
                        source_name=source_name, source_url=source_url)


# The Arabic mirror's inline chart data. The English page renders the full
# weekly series as a server-side PNG — pixels, not data. The Arabic edition of
# the SAME public page emits it as Google Charts rows: 520 weekly points of
# (date, local-currency price) back to 2016, readable by any visitor's browser.
# In scope under the owner's licence rule (what the public page shows any
# visitor); the paid API and data download remain untouched.
_ADDROWS = re.compile(r"data\.addRows\(\[(.*?)\]\);", re.S)
_AR_POINT = re.compile(r"\[\s*'([^']*)'\s*,\s*([\d.]+)\s*\]")
# The labels read 'يوم DD شهر MM سنة YYYY' — day, month, year, in words the
# regex anchors on so a digit can never be read out of position.
_AR_DATE = re.compile(r"يوم\s*(\d{1,2})\s*شهر\s*(\d{1,2})\s*سنة\s*(\d{4})")


def parse_arabic_history(html: str) -> list[tuple[str, str]]:
    """(ISO date, price) points from the Arabic mirror's chart data.

    Points whose label does not parse as an Arabic date are DROPPED, not
    guessed: a mis-read date would file a real price under a day it never held.
    """
    found = _ADDROWS.search(html)
    if not found:
        return []
    points: list[tuple[str, str]] = []
    for label, value in _AR_POINT.findall(found.group(1)):
        stamp = _AR_DATE.search(label)
        if not stamp:
            continue
        day, month, year = (int(x) for x in stamp.groups())
        points.append((f"{year:04d}-{month:02d}-{day:02d}", value))
    return points


def parse_country_links(html: str, country_sel: str = _COUNTRY_SEL) -> dict[str, str]:
    """country label -> the country page's path, read off the list page VERBATIM.

    An earlier version rebuilt the path by slugifying the printed name, on the
    belief that the name was "the only identifier the two pages share". The
    captured bytes refute that: every list-page label IS a link, and for 11
    countries the printed abbreviation and the real slug disagree — 'UK' links
    to /United-Kingdom/, 'Dom. Rep.' to /Dominican-Republic/, 'DR Congo' to
    /Democratic-Republic-of-the-Congo/. A crawler that guesses 404s on exactly
    those; a crawler that reads the href cannot be wrong about it.
    """
    soup = BeautifulSoup(html, "lxml")
    links: dict[str, str] = {}
    for a in soup.select(country_sel):
        href = a.get("href") or ""
        if href:
            links[_clean_country(a.get_text(strip=True))] = href
    return links
