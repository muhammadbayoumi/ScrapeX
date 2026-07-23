"""aramco-fuel-page family connector — the official Saudi monthly fuel prices.

Probed live 2026-07-23: aramco.com/ar/what-we-do/energy-products/retail-fuels
publishes the month's retail prices under one heading — «أسعار المنتجات لشهر
يوليو 2026 م (﷼ / لتر)» — followed by value/label pairs (2.18 / بنزين 91 …).
The heading's month is the SOURCE's own dating for every figure and rides
source_date. robots.txt allows the path.

Parsed from the tag-stripped TEXT, deliberately: the page is a React build
whose class names churn per release, while the reading order — heading, then
number, then product name — IS the published content. Selectors would rot;
the words are the contract.
"""
from __future__ import annotations

import re
from typing import Iterable

from ..config import SourceEntry
from ..rowspec import COMMODITY_PRICE, RowBuilder
from .base import CrawlBlocked, HttpFetcher, ScrapedTable

PRICES_PATH = "/ar/what-we-do/energy-products/retail-fuels"
# The SAME page in English — one extra request for the second half of the
# owner's standing bilingual rule (the Arabic page was read and only
# English machine keys were kept).
PRICES_PATH_EN = "/en/what-we-do/energy-products/retail-fuels"
# Verified live 2026-07-23: "Prices for the month of July 2026 (﷼ /liter)".
_HEADING_EN = "Prices for the month of"

_HEADING = "أسعار المنتجات لشهر"
_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")
_MONTH_IN_HEADING = re.compile(r"لشهر\s+(\S+)\s+(\d{4})")
_MONTHS = {"يناير": 1, "فبراير": 2, "مارس": 3, "أبريل": 4, "مايو": 5,
           "يونيو": 6, "يوليو": 7, "أغسطس": 8, "سبتمبر": 9,
           "أكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12}

# The labels the page prints, mapped to material keys. An unmapped label is a
# warning, never a silent drop — that is how Turkey vanished from GPP.
# The English edition's labels, lowercased — the same five materials.
_MATERIALS_EN = {
    "gasoline 91": "GASOLINE_91",
    "gasoline 95": "GASOLINE_95",
    "gasoline 98": "GASOLINE_98",
    "diesel": "DIESEL",
    "kerosene": "KEROSENE",
}

_MATERIALS = {
    "بنزين 91": "GASOLINE_91",
    "بنزين 95": "GASOLINE_95",
    "بنزين 98": "GASOLINE_98",
    "ديزل": "DIESEL",
    "الكيروسين": "KEROSENE",
    "كيروسين": "KEROSENE",
}


def page_lines(html: str) -> list[str]:
    """The page as reading-order text lines, styles and scripts removed."""
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.S)
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.S)
    text = re.sub(r"\n\s*", "\n",
                  re.sub(r"<[^>]+>", "\n", re.sub(r"\s+", " ", html)))
    return [line.strip() for line in text.splitlines() if line.strip()]


def parse_month(heading: str) -> str:
    """«… لشهر يوليو 2026 م …» -> '2026-07-01'.

    LOUD when unreadable (Q4): the month is the source's dating for every
    figure on the page — stamping today instead would file an official
    monthly price under the wrong date."""
    found = _MONTH_IN_HEADING.search(heading)
    month = _MONTHS.get(found.group(1)) if found else None
    if not month:
        raise ValueError(
            f"the Aramco prices heading no longer carries a readable month: "
            f"{heading[:80]!r}")
    return f"{int(found.group(2)):04d}-{month:02d}-01"


def parse_pairs(lines: list[str], start: int) -> list[tuple[str, str]]:
    """(price, label) pairs in reading order after the heading.

    The sequence ends at the first line that breaks the number/label rhythm.
    Fewer than three pairs is a redesigned page, not a small month — LOUD."""
    pairs: list[tuple[str, str]] = []
    i = start + 1
    while i + 1 < len(lines) and _NUMBER.match(lines[i]):
        pairs.append((lines[i], lines[i + 1]))
        i += 2
    if len(pairs) < 3:
        raise ValueError(
            f"the Aramco prices section yielded only {len(pairs)} value/label "
            "pair(s) — the page layout has changed")
    return pairs


class AramcoFuelConnector:
    connector_id = "aramco-fuel-page"

    def __init__(self, fetcher: HttpFetcher) -> None:
        self._fetcher = fetcher

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        builder = RowBuilder(COMMODITY_PRICE)
        url = source.base_url.rstrip("/") + PRICES_PATH
        html = self._fetcher.get(url).text
        lines = page_lines(html)
        try:
            start = next(i for i, line in enumerate(lines) if _HEADING in line)
        except StopIteration:
            raise ValueError(
                "the Aramco retail-fuels page no longer carries the prices "
                f"heading «{_HEADING}» — layout change, nothing parsed") from None
        month = parse_month(lines[start])
        vat = "1" if source.vat_mode.value == "incl" else "0"
        english = self._english_labels(source, warnings_out := [])
        rows: list[list[str]] = []
        warnings: list[str] = list(warnings_out)
        for price, label in parse_pairs(lines, start):
            material = _MATERIALS.get(label)
            if material is None:
                warnings.append(
                    f"price {price} carries the unmapped label {label!r} — "
                    "dropped OUT LOUD; extend the label map if it is a fuel")
                continue
            rows.append(builder.row(
                # The site's own words, in both languages: «بنزين 91» here and
                # "Gasoline 91" from the English edition of the same page.
                material_label=label,
                material_label_en=english.get(material, ""),
                material_key=material, region=source.default_region or "SA",
                currency=source.currency or "SAR", unit="liter",
                vat_included=vat, effective_price=price,
                provenance="observed",
                # The heading's month is the source's own dating — the pump
                # price it announced FOR that month, not our crawl date.
                source_date=month,
                price_basis="original",
            ))
        yield ScrapedTable(source.source_key, COMMODITY_PRICE.kind, url,
                           builder.header, rows, warnings=warnings)

    def _english_labels(self, source: SourceEntry, warnings: list) -> dict:
        """material key -> the English page's own label. {} when unavailable.

        Same page, same value/label rhythm, English words: the mapping is by
        PRICE, because the two editions publish the same figures in the same
        order and the price is the one thing that cannot be translated."""
        try:
            html = self._fetcher.get(source.base_url.rstrip("/") + PRICES_PATH_EN).text
            lines = page_lines(html)
            start = next(i for i, line in enumerate(lines) if _HEADING_EN in line)
            labels = {}
            for price, label in parse_pairs(lines, start):
                material = _MATERIALS_EN.get(label.strip().lower())
                if material:
                    labels[material] = label.strip()
            return labels
        except CrawlBlocked:
            raise
        except Exception as exc:  # noqa: BLE001 — the Arabic prices are the point
            warnings.append(f"english edition unavailable — labels stay "
                            f"Arabic-only this run: {exc}")
            return {}
