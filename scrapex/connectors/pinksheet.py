"""worldbank-pink-sheet family connector: world commodity prices, monthly since 1960.

Studied in #1912. The source is one workbook on thedocs.worldbank.org, linked from a
landing page on www.worldbank.org: 71 columns, months in rows. There is no API. A value
is a month's average in US dollars of a named international market. It is not an offer:
nobody sells at it, so no row says retail.

A NORMAL RUN reads the newest month as `observed`, and every month of the last twelve as
`reported` so that a revised month lands: 10 of July 2026's values moved between two
editions (LNG Japan by +17.4%, #1912 §5). Every month, not its change points: a month
revised to equal the one before it would otherwise keep its old value (his answer on
#1919). A HISTORY run adds every older month back to 1960 as `reported` change points
(his rule, connectors/gpp.py). Corrections older than the window arrive only that way.
Each row inside the window carries its EDITION, the sheet's newest month, so a month
revised back to a value an earlier edition held is stored again (his answer on #1993).

HIS WORD ON THE HIDDEN SHEET, against my recommendation (#1912 Q6): «تتبع اسعار طالما
مذكورة». `Mismatch Details`, a hidden QA sheet, holds barley and sorghum prices that the
published sheet blanks after 2020-08. They are taken while they exist, marked so that
they never read as published ones, and their absence is a visible warning, not a failure.

Every parse asserts its shape: a moved header, a renamed sheet or an unknown unit fails
here, loudly, rather than quietly as wrong data.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from decimal import Decimal
from io import BytesIO

from ..config import SourceEntry
from ..localsheets import _openpyxl
from ..normalize import EXCEL_ERRORS, parse_month_stamp, parse_quoted_unit, parse_sheet_amount
from ..rowspec import COMMODITY_PRICE, ENRICHMENT, RowBuilder
from ..vocab import DetailGroup
from .base import HttpFetcher, ScrapedTable

PAGE_PATH = "/en/research/commodity-markets"
# Only this host, only this file name: the page is scraped content, and it decides nothing
# about where the engine goes next.
_WORKBOOK_LINK = re.compile(
    r'href="(https://thedocs\.worldbank\.org/[^"\s]+/CMO-Historical-Data-Monthly\.xlsx)"')
# The file is about 590 KB. Refusing a 40x larger one costs nothing and bounds what an
# unexpected body can do to the engine's memory.
MAX_WORKBOOK_BYTES = 25_000_000

PRICES_SHEET = "Monthly Prices"
DESCRIPTION_SHEET = "Description"
HIDDEN_SHEET = "Mismatch Details"
_HIDDEN_HEADER = ("Period", "Commodity", "Current Cell", "Current Display", "Uploaded Cell",
                  "Uploaded Display", "Difference Type")
_HIDDEN_KIND = "Blank vs number"
#: The sheet's other kind: the older edition of a value the published sheet still states.
_HIDDEN_PASSED_OVER = "Value mismatch"
#: Who a hidden value is marked as coming from, on its own row.
HIDDEN_SOURCE = "World Bank Pink Sheet workbook, hidden sheet 'Mismatch Details'"

#: How many of the newest months a normal run re-reads. July 2026 was revised in the
#: October edition; a year leaves room for the corrections the change log dates.
REVISION_WINDOW = 12
#: A series is "current" when its newest value is this close to the sheet's newest month.
#: Tobacco arrives two months late by the change log's own words, so 2 is not enough.
CURRENT_WINDOW = 3
#: The fewest priced series a real edition can hold; 67 of 70 reach the newest month.
MIN_SERIES = 60

#: Not a price: an index has no currency, and `price_observation` requires one.
INDEX_SERIES = "Natural gas index"
#: The workbook's unit row says ($/dmtu), but the value is per dry ton: 97.7, the PDF prints
#: `$/dmt`, and the Description says spot is in dollars per dry ton, contracts in cents per
#: dmtu (#1912 §5). Keyed on the exact words it corrects, so a workbook that changes them
#: is read as written and said out loud. The workbook's words stay in `unit_as_published`.
_UNIT_OVERRIDE = {"Iron ore, cfr spot": ("($/dmtu)", "dmt")}

# The header as the workbook writes it, with its " **" flag stripped, to the material key,
# the group, and how its row in the Description tab begins. Names are the only key this
# source has. A new or renamed one is a warning for review, never a guess.
_SERIES: dict[str, tuple[str, str, str]] = {
    "Crude oil, average": ("CRUDE_OIL_AVERAGE", "Energy", "Crude oil, average spot price"),
    "Crude oil, Brent": ("CRUDE_OIL_BRENT", "Energy", "Crude oil, UK Brent"),
    "Crude oil, Dubai": ("CRUDE_OIL_DUBAI", "Energy", "Crude oil, Dubai"),
    "Crude oil, WTI": ("CRUDE_OIL_WTI", "Energy", "Crude oil, US, West Texas"),
    "Coal, Australian": ("COAL_AUSTRALIA", "Energy", "Coal (Australia)"),
    "Coal, South African": ("COAL_SOUTH_AFRICA", "Energy", "Coal (South Africa)"),
    "Natural gas, US": ("NATURAL_GAS_US", "Energy", "Natural Gas (U.S.)"),
    "Natural gas, Europe": ("NATURAL_GAS_EUROPE", "Energy", "Natural Gas (Europe)"),
    "Liquefied natural gas, Japan": ("LNG_JAPAN", "Energy", "Liquefied natural gas (Japan)"),
    "Cocoa": ("COCOA", "Beverages", "Cocoa (ICCO)"),
    "Coffee, Arabica": ("COFFEE_ARABICA", "Beverages", "Coffee, Arabica (ICO)"),
    "Coffee, Robusta": ("COFFEE_ROBUSTA", "Beverages", "Coffee, Robusta (ICO)"),
    "Tea, avg 3 auctions": ("TEA_AVERAGE", "Beverages", "Tea, average three auctions"),
    "Tea, Colombo": ("TEA_COLOMBO", "Beverages", "Tea (Colombo auctions)"),
    "Tea, Kolkata": ("TEA_KOLKATA", "Beverages", "Tea (Kolkata auctions)"),
    "Tea, Mombasa": ("TEA_MOMBASA", "Beverages", "Tea (Mombasa/Nairobi auctions)"),
    "Coconut oil": ("COCONUT_OIL", "Oils and meals", "Coconut oil"),
    "Groundnuts": ("GROUNDNUTS", "Oils and meals", "Peanut (Groundnut), U.S."),
    "Fish meal": ("FISH_MEAL", "Oils and meals", "Fish meal"),
    "Groundnut oil": ("GROUNDNUT_OIL", "Oils and meals", "Peanut (Groundnut) oil"),
    "Palm oil": ("PALM_OIL", "Oils and meals", "Palm oil (Malaysia)"),
    "Palm kernel oil": ("PALM_KERNEL_OIL", "Oils and meals", "Palmkernel oil"),
    "Soybeans": ("SOYBEANS", "Oils and meals", "Soybeans"),
    "Soybean oil": ("SOYBEAN_OIL", "Oils and meals", "Soybean oil"),
    "Soybean meal": ("SOYBEAN_MEAL", "Oils and meals", "Soybean meal"),
    "Rapeseed oil": ("RAPESEED_OIL", "Oils and meals", "Rapeseed Oil"),
    "Sunflower oil": ("SUNFLOWER_OIL", "Oils and meals", "Sunflower oil"),
    "Barley": ("BARLEY", "Grains", "Barley (U.S.)"),
    "Maize": ("MAIZE", "Grains", "Maize (U.S.)"),
    "Sorghum": ("SORGHUM", "Grains", "Sorghum (US)"),
    "Rice, Thai 5%": ("RICE_THAI_5", "Grains", "Rice (Thailand), 5%"),
    "Rice, Thai 25%": ("RICE_THAI_25", "Grains", "Rice (Thailand), 25%"),
    "Rice, Thai A.1": ("RICE_THAI_A1", "Grains", "Rice (Thailand), 100%"),
    "Rice, Viet Namese 5%": ("RICE_VIETNAM_5", "Grains", "Rice (Vietnam), 5%"),
    "Wheat, US SRW": ("WHEAT_US_SRW", "Grains", "Wheat (U.S.), no. 2, soft red"),
    "Wheat, US HRW": ("WHEAT_US_HRW", "Grains", "Wheat (U.S.), no. 2 hard red"),
    "Banana, Europe": ("BANANA_EUROPE", "Other food",
                       "Bananas (Central & South America), major brands, free on truck"),
    "Banana, US": ("BANANA_US", "Other food",
                   "Bananas (Central & South America), major brands, US import"),
    "Orange": ("ORANGE", "Other food", "Oranges (Mediterranean"),
    "Beef": ("BEEF", "Other food", "Beef (New Zealand)"),
    "Chicken": ("CHICKEN", "Other food", "Chicken (Brazil)"),
    "Lamb": ("LAMB", "Other food", "Lamb (New Zealand)"),
    "Shrimps, Mexican": ("SHRIMP", "Other food", "Shrimp"),
    "Sugar, EU": ("SUGAR_EU", "Other food", "Sugar (EU)"),
    "Sugar, US": ("SUGAR_US", "Other food", "Sugar (U.S.)"),
    "Sugar, world": ("SUGAR_WORLD", "Other food", "Sugar (World)"),
    "Logs, Cameroon": ("LOGS_CAMEROON", "Timber", "Logs (Africa)"),
    "Logs, Malaysian": ("LOGS_MALAYSIA", "Timber", "Logs (Southeast Asia)"),
    "Sawnwood, Cameroon": ("SAWNWOOD_CAMEROON", "Timber", "Sawnwood (Africa)"),
    "Sawnwood, Malaysian": ("SAWNWOOD_MALAYSIA", "Timber", "Sawnwood (Southeast Asia)"),
    "Plywood": ("PLYWOOD", "Timber", "Plywood"),
    "Cotton, A Index": ("COTTON_A_INDEX", "Other raw materials", "Cotton (Cotton Outlook"),
    "Rubber, TSR20": ("RUBBER_TSR20", "Other raw materials", "Rubber (Asia), TSR 20"),
    "Rubber, RSS3": ("RUBBER_RSS3", "Other raw materials", "Rubber (Asia), RSS3"),
    "Tobacco, US import u.v.": ("TOBACCO_US", "Other raw materials", "Tobacco (any origin)"),
    "Phosphate rock": ("PHOSPHATE_ROCK", "Fertilizers", "Phosphate rock"),
    "DAP": ("DAP", "Fertilizers", "DAP"),
    "TSP": ("TSP", "Fertilizers", "TSP"),
    "Urea": ("UREA", "Fertilizers", "Urea,"),
    "Potassium chloride": ("POTASSIUM_CHLORIDE", "Fertilizers", "Potassium chloride"),
    "Aluminum": ("ALUMINUM", "Metals and minerals", "Aluminum (LME)"),
    "Iron ore, cfr spot": ("IRON_ORE", "Metals and minerals", "Iron ore (any origin)"),
    "Copper": ("COPPER", "Metals and minerals", "Copper (LME)"),
    "Lead": ("LEAD", "Metals and minerals", "Lead (LME)"),
    "Tin": ("TIN", "Metals and minerals", "Tin (LME)"),
    "Nickel": ("NICKEL", "Metals and minerals", "Nickel (LME)"),
    "Zinc": ("ZINC", "Metals and minerals", "Zinc (LME)"),
    "Gold": ("GOLD", "Precious metals", "Gold,"),
    "Platinum": ("PLATINUM", "Precious metals", "Platinum,"),
    "Silver": ("SILVER", "Precious metals", "Silver (UK)"),
}


def series_name(header: str) -> str:
    """'Coal, South African **' -> 'Coal, South African'. The flag comes and goes between
    editions, so it is never part of a series' identity."""
    return header.removesuffix("**").strip()


def find_workbook_url(html: str) -> str:
    """The monthly workbook's address from the landing page. Its folder name carries a
    hash, so the address is read each run. None, or two different ones, is LOUD."""
    found = set(_WORKBOOK_LINK.findall(html))
    if len(found) != 1:
        raise ValueError(
            f"the Commodity Markets page should link one monthly workbook on "
            f"thedocs.worldbank.org and links {len(found)}: layout change, nothing parsed")
    return found.pop()


@dataclass
class Series:
    name: str
    unit_raw: str
    #: Period -> amount as the workbook writes it. Period order is the sheet's.
    values: dict[str, Decimal] = field(default_factory=dict)
    zero_cells: int = 0
    error_cells: int = 0


def _is_month(cell) -> bool:
    try:
        parse_month_stamp(cell)
    except ValueError:
        return False
    return True


def read_prices(sheet) -> tuple[list[str], dict[str, Series], list[str]]:
    """(periods oldest first, series by name, warnings) from `Monthly Prices`.

    Finds the first `YYYYMmm` in column A; the two rows above it are the header and the
    unit row. Nothing else about the rows' positions is assumed.
    """
    rows = list(sheet.iter_rows(values_only=True))
    if not rows or "nominal US dollars" not in str(rows[1][0] if len(rows) > 1 else ""):
        raise ValueError(f"{PRICES_SHEET} no longer says its prices are in nominal US "
                         "dollars: layout change, nothing parsed")
    first = next((i for i, r in enumerate(rows) if _is_month(r[0])), None)
    if first is None or first < 2:
        raise ValueError(f"{PRICES_SHEET} has no YYYYMmm row with a header and a unit row "
                         "above it: layout change, nothing parsed")
    header, units = rows[first - 2], rows[first - 1]
    warnings: list[str] = []
    series: dict[str, Series] = {}
    columns: list[tuple[int, Series]] = []
    for col, raw in enumerate(header):
        if col == 0 or raw is None or not str(raw).strip():
            continue
        name = series_name(str(raw))
        if name == INDEX_SERIES:
            continue
        if name not in _SERIES:
            warnings.append(f"new or renamed series {str(raw)!r}: not collected until it has "
                            "a key; review it against the Description tab")
            continue
        if name in series:
            raise ValueError(f"{PRICES_SHEET} has the series {name!r} twice: layout change")
        unit = units[col]
        one = Series(name=name, unit_raw=str(unit or "").strip())
        series[name] = one
        columns.append((col, one))
    periods: list[str] = []
    for row in rows[first:]:
        stamp = row[0]
        if stamp is None:
            continue
        stamp = str(stamp).strip()
        if not _is_month(stamp):
            raise ValueError(f"{PRICES_SHEET} column A holds {stamp!r} where a month belongs: "
                             "layout change, nothing parsed")
        if periods and stamp <= periods[-1]:
            raise ValueError(f"{PRICES_SHEET} months are out of order at {stamp!r}: "
                             "layout change, nothing parsed")
        periods.append(stamp)
        for col, one in columns:
            cell = row[col] if col < len(row) else None
            if isinstance(cell, str) and cell.strip() in EXCEL_ERRORS:
                one.error_cells += 1
                continue
            amount = parse_sheet_amount(cell)
            if amount is None:
                continue
            if amount <= 0:
                # Rice, Thai 25% holds 0 in four months of 2008. A price of nothing is a
                # hole in the sheet, and it would store as a real price.
                one.zero_cells += 1
                continue
            one.values[stamp] = amount
    return periods, series, warnings


def read_descriptions(sheet) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """(series name -> (the Description tab's text, its named sources), warnings).

    A row carries no key and differs in spelling from the headers, so a row is found by
    how it begins. A series' row is exactly two cells, the text and its sources; the
    change-log lines that share a prefix are one cell. A prefix that finds no such row,
    or two, gives the series no text rather than a guess: its sources would land on every
    price row. The prices do not depend on this.
    """
    rows: list[tuple[str, str]] = []
    for row in sheet.iter_rows(values_only=True):
        cells = [str(c).strip() for c in row if c is not None and str(c).strip()]
        # A leading '*' or '*, **' is the forecast mark, not the description.
        while cells and set(cells[0]) <= set("*, "):
            cells = cells[1:]
        if len(cells) == 2:
            rows.append((cells[0], cells[1]))
    out: dict[str, tuple[str, str]] = {}
    warnings: list[str] = []
    for name, (_key, _group, prefix) in _SERIES.items():
        found = [row for row in rows if row[0].startswith(prefix)]
        if len(found) == 1:
            out[name] = found[0]
        elif found:
            warnings.append(f"{len(found)} Description rows begin {prefix!r}: {name!r} gets no "
                            "text or sources until one is chosen")
    return out, warnings


def read_hidden(workbook, periods: list[str], series: dict[str, Series]
                ) -> tuple[dict[str, dict[str, Decimal]], list[str]]:
    """(series -> period -> amount, warnings) from the hidden sheet, where it exists.

    Only `Blank vs number` rows, and only where the published cell really holds nothing:
    every other row of that sheet is an older edition of a value the published sheet still
    states. It is a QA sheet with no promise behind it, so any change in it is a warning.
    """
    if HIDDEN_SHEET not in workbook.sheetnames:
        return {}, [f"the hidden sheet {HIDDEN_SHEET!r} is gone from this edition, so the "
                    "barley and sorghum prices it held stop here; what is stored stays"]
    rows = list(workbook[HIDDEN_SHEET].iter_rows(values_only=True))
    first = next((i for i, r in enumerate(rows) if tuple(r[:7]) == _HIDDEN_HEADER), None)
    if first is None:
        return {}, [f"the hidden sheet {HIDDEN_SHEET!r} changed its columns: read nothing "
                    "from it; review it"]
    known = set(periods)
    out: dict[str, dict[str, Decimal]] = {}
    filled = outside = unreadable = candidates = 0
    # A renamed kind would otherwise end the hidden prices with nothing said.
    strange: dict[str, int] = {}
    for row in rows[first + 1:]:
        if row[0] is None or row[6] == _HIDDEN_PASSED_OVER:
            continue
        if row[6] != _HIDDEN_KIND:
            kind = str(row[6])[:40]
            strange[kind] = strange.get(kind, 0) + 1
            continue
        candidates += 1
        one = series.get(series_name(str(row[1])))
        period = str(row[0]).strip()
        if one is None or period not in known:
            outside += 1
            continue
        if period in one.values:
            filled += 1
            continue
        try:
            amount = parse_sheet_amount(row[5])
        except ValueError:
            amount = None
        if amount is None or amount <= 0:
            unreadable += 1
            continue
        out.setdefault(one.name, {})[period] = amount
    warnings = []
    if strange:
        kinds = ", ".join(f"{kind!r} x{count}" for kind, count in sorted(strange.items())[:3])
        warnings.append(f"{sum(strange.values())} hidden row(s) of a kind this reader does not "
                        f"know ({kinds}): read as nothing; review the sheet")
    if not candidates:
        warnings.append(f"the hidden sheet holds no {_HIDDEN_KIND!r} row: no hidden price "
                        "this run")
    if filled:
        warnings.append(f"{filled} hidden value(s) ignored: the published sheet now states "
                        "those months")
    if outside:
        warnings.append(f"{outside} hidden row(s) skipped: a series or a month the published "
                        "sheet does not have")
    if unreadable:
        warnings.append(f"{unreadable} hidden row(s) skipped: no price above 0 in "
                        "`Uploaded Display`")
    return out, warnings


def change_points(values: dict[str, Decimal], periods: Iterable[str]
                  ) -> Iterator[tuple[str, Decimal]]:
    """The first value and each one that differs from the one before it (his rule for
    history): between two kept points the price held, by construction.

    connectors/gpp.py holds the same rule in its own loop, over its string points. Both
    apply it only where no new edition revises a value: inside the revision window this
    module sends every month instead (his answer on #1919)."""
    previous = None
    for period in periods:
        amount = values.get(period)
        if amount is None:
            continue
        if amount != previous:
            yield period, amount
        previous = amount


def _amount_fields(amount: Decimal, per_unit: Decimal, period: str) -> dict[str, str]:
    """One month's amount as row fields. Plywood alone is quoted in cents: it is stated
    in dollars so one currency runs through the source, and the workbook's figure stays
    beside it as `original_price`."""
    return {"price": format(amount * per_unit, "f"),
            "original_price": format(amount, "f") if per_unit != 1 else "",
            "source_date": parse_month_stamp(period)}


class PinkSheetConnector:
    connector_id = "worldbank-pink-sheet"

    def __init__(self, fetcher: HttpFetcher, history: bool = False) -> None:
        self._fetcher = fetcher
        # On for a History backfill: every month back to 1960. Off for the weekly check,
        # where a year of months is what can still be revised.
        self._history = history

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        page = source.base_url.rstrip("/") + PAGE_PATH
        url = find_workbook_url(self._fetcher.get(page).text)
        body = self._fetcher.get(url).content
        if len(body) > MAX_WORKBOOK_BYTES:
            raise ValueError(f"the monthly workbook is {len(body):,} bytes, far past its "
                             f"usual size: nothing parsed")
        workbook = _openpyxl().load_workbook(BytesIO(body), data_only=True)
        for sheet in (PRICES_SHEET, DESCRIPTION_SHEET):
            if sheet not in workbook.sheetnames:
                raise ValueError(f"the monthly workbook no longer has a sheet {sheet!r}: "
                                 "layout change, nothing parsed")
        periods, series, warnings = read_prices(workbook[PRICES_SHEET])
        priced = [one for one in series.values() if one.values]
        if len(priced) < MIN_SERIES:
            raise ValueError(f"{PRICES_SHEET} yielded {len(priced)} known series with a value, "
                             f"of {len(_SERIES)}: layout change, nothing parsed")
        missing = sorted(set(_SERIES) - set(series))
        defects = [f"the series {name!r} is gone from the workbook or renamed: no price for "
                   "it this run" for name in missing]
        defects += [f"the series {one.name!r} holds no value in any month: no price for it "
                    "this run" for one in series.values() if not one.values]
        hidden, hidden_warnings = read_hidden(workbook, periods, series)
        warnings += hidden_warnings
        descriptions, description_warnings = read_descriptions(workbook[DESCRIPTION_SHEET])
        warnings += description_warnings
        warnings += [f"no Description row for {name!r}"
                     for name in sorted(set(series) - set(descriptions))]

        builder = RowBuilder(COMMODITY_PRICE)
        rows: list[list[str]] = []
        details = RowBuilder(ENRICHMENT)
        detail_rows: list[list[str]] = []
        # Every month the window holds, or a month revised to equal the one before it keeps
        # its old value; ingest ignores a month it already holds unchanged. Before the window
        # nothing is revised, so his change-points rule holds there (#1919).
        revisable = periods[-REVISION_WINDOW:]
        settled = periods[:-REVISION_WINDOW] if self._history else []
        # The edition a window row came from. Older months carry none, so a second
        # History run in a later edition does not store its forty thousand again.
        edition = periods[-1]
        # The stored bit only, and no claim: with no `tax:` rule this reads Unverified.
        tax = "1" if source.vat_mode.value == "incl" else "0"
        for name, one in series.items():
            key, group, _prefix = _SERIES[name]
            currency, per_unit, unit = parse_quoted_unit(one.unit_raw)
            if name in _UNIT_OVERRIDE:
                corrects, instead = _UNIT_OVERRIDE[name]
                if one.unit_raw == corrects:
                    unit = instead
                else:
                    warnings.append(f"{name}: the unit now reads {one.unit_raw!r}, not "
                                    f"{corrects!r}, so it is stored as written; review "
                                    "the correction")
            text, sources = descriptions.get(name, ("", ""))
            common = {"material_key": key, "material_label": name, "country_code_alpha2": "*",
                      "currency": currency, "unit": unit, "tax_included": tax,
                      "consumer_segment": "wholesale", "official_source_link": url,
                      "price_basis": "original" if per_unit == 1 else "converted"}
            if one.zero_cells or one.error_cells:
                warnings.append(f"{name}: {one.zero_cells} cell(s) of 0 and {one.error_cells} "
                                "Excel error(s) are holes in the sheet, not prices")

            before = len(rows)
            current = [p for p in periods[-CURRENT_WINDOW:] if p in one.values]
            if current:
                rows.append(builder.row(
                    **common, provenance="observed", official_source_name=sources,
                    **_amount_fields(one.values[current[-1]], per_unit, current[-1])))
            elif one.values:
                warnings.append(f"{name}: no current price, last published "
                                f"{max(one.values)} (the sheet reaches {periods[-1]})")
            for values, named in ((one.values, sources), (hidden.get(name, {}), HIDDEN_SOURCE)):
                kept = [*change_points(values, settled),
                        *((period, values[period]) for period in revisable if period in values)]
                for period, amount in kept:
                    fields = _amount_fields(amount, per_unit, period)
                    rows.append(builder.row(
                        **common, provenance="reported", official_source_name=named,
                        as_of_date=fields["source_date"],
                        edition=edition if period in revisable else "", **fields))

            if len(rows) == before:
                # Ingest refuses a detail for a product this run did not register. Shrimp
                # stopped in 2023, so a normal run has nothing to attach one to.
                continue
            facts = [("commodity_group", "Commodity group", group, DetailGroup.MORE_INFORMATION),
                     ("price_period", "Price period", "Monthly average, dated the month's first day",
                      DetailGroup.MORE_INFORMATION),
                     ("unit_as_published", "Unit as published", one.unit_raw,
                      DetailGroup.SPECIFICATIONS)]
            if text:
                facts.append(("market_terms", "Market and terms", text, DetailGroup.DESCRIPTION))
            detail_rows += [details.row(
                external_product_id=key, attribute_code=code, attribute_label=label,
                raw_value=value, lang="en", attribute_group=filed.value)
                for code, label, value, filed in facts]
        yield ScrapedTable(source.source_key, COMMODITY_PRICE.kind, url, builder.header, rows,
                           warnings=warnings, defects=defects)
        yield ScrapedTable(source.source_key, ENRICHMENT.kind, url, details.header, detail_rows)
