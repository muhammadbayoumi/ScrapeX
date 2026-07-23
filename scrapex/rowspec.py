"""Canonical row specs — the ONE column contract per extract kind (Q1/Q2 DRY).

Connectors never hardcode column order: they build rows via RowBuilder against
the spec, and ingest reads rows by column NAME via RowView. Column identity is
defined here exactly once, so a connector and the ingester can never disagree
about what column 3 means.
"""
from __future__ import annotations

from dataclasses import dataclass

from .vocab import ExtractKind


@dataclass(frozen=True)
class RowSpec:
    """The fixed column set a connector must emit for a given kind."""

    kind: ExtractKind
    columns: tuple[str, ...]
    required: frozenset[str]
    # Columns added AFTER this contract first shipped. A header that predates
    # them is still readable; they arrive as "". Everything else must be
    # present, so a renamed or dropped original column still fails loud.
    #
    # This exists because the payload contract spans two engines: rows captured
    # by the Chrome extension, or already sitting in the local inbox, carry the
    # header of the day they were made. Without this, widening the spec would
    # make every stored payload unreplayable — the data would still be on disk
    # and no longer readable, which is the worst of both.
    additive: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        missing = self.required - set(self.columns)
        if missing:  # a spec that requires a column it doesn't define is a bug
            raise ValueError(f"{self.kind}: required columns not in spec: {missing}")
        stray = self.additive - set(self.columns)
        if stray:
            raise ValueError(f"{self.kind}: additive columns not in spec: {stray}")
        both = self.additive & self.required
        if both:  # a column cannot be optional-when-absent AND mandatory
            raise ValueError(f"{self.kind}: columns both additive and required: {both}")

    def index(self, column: str) -> int:
        return self.columns.index(column)


# ---- product_prices: every e-commerce connector emits exactly this ----------
PRODUCT_PRICES = RowSpec(
    kind=ExtractKind.PRODUCT_PRICES,
    columns=(
        "external_product_id",
        "external_variant_id",   # "" when the platform gives none -> fingerprint fallback
        "external_sku",
        "product_name",
        "brand_raw",
        "option_label",
        "option_fingerprint",
        "product_url",
        "region",
        "currency",
        "vat_included",          # "0" | "1"
        "regular_price",
        "sale_price",
        "effective_price",
        "availability",          # in_stock | out_of_stock | unknown
        "stock_quantity",
        # --- added 2026-07-20, owner-approved contract widening --------------
        # These are the fields that belong to the PRICE itself: what quantity of
        # what unit it buys, and how the product is identified and classified.
        # Open-ended per-product attributes (colour, voltage, warranty...) do
        # NOT live here — their number differs per site, so fixed columns would
        # be mostly empty. They go to ENRICHMENT below, one row per attribute.
        "unit",                  # the SELLING unit: m | kg | liter | item | tonne
        "basis_quantity",        # how many of `unit` one offer buys ("100" for a 100 m roll)
        "product_name_en",       # the English name, kept SEPARATE, never merged
        "lang",                  # which language `product_name` is in: ar | en
        "category_path",         # "Concrete additives" or "Cables > Low voltage"
        "category_path_en",      # the SAME path in English, when the site publishes it
        "category_external_id",  # the site's own id for that category, when it has one
    ),
    required=frozenset({"external_product_id", "region", "currency", "vat_included", "effective_price"}),
    additive=frozenset({"unit", "basis_quantity", "product_name_en", "lang",
                        "category_path", "category_path_en",
                        "category_external_id"}),
)

# ---- enrichment: the open-ended attribute bag, one ROW per attribute ---------
#
# Sameh Gabriel publishes weight, colours, cable type, length, brand, size,
# application, voltage type and warranty — and a different site publishes a
# different nine. A long format takes any number of attributes from any site
# without the contract changing again, which is exactly why the owner chose a
# separate bag over more fixed columns.
ENRICHMENT = RowSpec(
    kind=ExtractKind.ENRICHMENT,
    columns=(
        "external_product_id",
        "external_variant_id",   # "" when the attribute belongs to the product
        "attribute_code",        # stable key: "voltage_type"
        "attribute_label",       # as printed on the page: "Voltage type"
        "raw_value",             # as printed: "100 meters"
        "numeric_value",         # "100" when the value is measurable, else ""
        "unit_raw",              # "meters" — the unit AS WRITTEN, not normalised here
        "value_url",             # attribute values are often links; keep the link
        "lang",                  # ar | en — the language of label and raw_value
        "attribute_group",       # the page's own grouping: "Specifications"
    ),
    required=frozenset({"external_product_id", "attribute_code", "raw_value"}),
)

# ---- commodity_price: globalpetrolprices / aramco fuel rows -----------------
COMMODITY_PRICE = RowSpec(
    kind=ExtractKind.COMMODITY_PRICE,
    columns=(
        "material_key",          # DIESEL | GASOLINE_91 | ...
        "region",                # country ISO code, or 'SA'
        "currency",
        "unit",                  # 'USD/liter' historically; 'liter' going forward
        "vat_included",
        "effective_price",
        "observed_label",        # the date string printed on the page
        # --- added 2026-07-20 -----------------------------------------------
        # globalpetrolprices renders BOTH the currency and the unit from user
        # dropdowns (156 currencies, 4 units), so `effective_price` above is a
        # conversion the site computed for a default selection — not what the
        # source published. The original is stated on each country page:
        # "EGP 20.50 per liter or USD 0.40 per liter". Keeping them apart is
        # the owner's rule: a converted price is never the authority.
        "original_price",
        "original_currency",
        "price_basis",           # 'original' | 'converted' — what THIS row is
        "geo_region",            # the site groups countries: 'Africa', 'Europe'
        "consumer_segment",      # 'household' | 'business' — power prices differ
        "tax_evidence",          # 'stated' | 'general' | 'unknown' — never assumed
        "tax_statement_url",     # where that evidence can be read
        # --- added 2026-07-20 -----------------------------------------------
        # A price we READ today, versus a price the source TELLS us held on an
        # earlier date. globalpetrolprices prints, free on each country page,
        # what a price was one month, three months and a year ago — a year of
        # history on the first crawl instead of fifty-two weeks of waiting.
        # They are not our observations and must never pass for them, so the row
        # carries which it is and, for a reported one, which date it refers to.
        "provenance",            # 'observed' | 'reported'
        "as_of_date",            # 'YYYY-MM-DD' the price refers to; blank = today
        "source_date",           # the date the SOURCE stamps on its own figure
        # --- added 2026-07-22 -----------------------------------------------
        # The official body the page names for its figure ("Source: Ministry of
        # Petroleum and Mineral Resources" + link). The strongest provenance
        # signal on the page; absent on some countries (Germany), so both are
        # optional and an empty value means "not stated" — never invented.
        "official_source_name",
        "official_source_url",
        # The site's OWN USD conversion, printed beside the local price. Kept
        # because the pair IMPLIES the exchange rate the publisher used —
        # local/usd — which feeds currency_rate and the ranked USD column.
        "converted_usd_price",
    ),
    required=frozenset({"material_key", "region", "currency", "effective_price"}),
    additive=frozenset({"original_price", "original_currency", "price_basis",
                        "geo_region", "consumer_segment",
                        "tax_evidence", "tax_statement_url",
                        "provenance", "as_of_date", "source_date",
                        "official_source_name", "official_source_url",
                        "converted_usd_price"}),
)

_BY_KIND = {spec.kind: spec for spec in (PRODUCT_PRICES, COMMODITY_PRICE, ENRICHMENT)}


def spec_for(kind: ExtractKind) -> RowSpec:
    try:
        return _BY_KIND[kind]
    except KeyError:
        raise ValueError(f"no row spec defined for kind {kind!r}") from None


class RowBuilder:
    """Connector-side helper: build a spec-ordered row from named fields.

    Missing optional fields become "" (never None on the wire — the payload is
    all strings, Q2/Q5). Unknown fields fail loud (Q4).
    """

    def __init__(self, spec: RowSpec) -> None:
        self._spec = spec

    @property
    def header(self) -> list[str]:
        return list(self._spec.columns)

    def row(self, **fields: object) -> list[str]:
        unknown = set(fields) - set(self._spec.columns)
        if unknown:
            raise ValueError(f"unknown fields for {self._spec.kind}: {sorted(unknown)}")
        row = [_stringify(fields.get(col, "")) for col in self._spec.columns]
        for col in self._spec.required:
            if row[self._spec.index(col)] == "":
                raise ValueError(f"{self._spec.kind}: required field {col!r} is empty")
        return row


class RowView:
    """Ingest-side helper: read a row by column NAME, tolerant of header order.

    Validates the incoming header carries every spec column exactly once (Q4);
    a connector drift (renamed/dropped column) fails loud at ingest, never as
    silently-misaligned data.
    """

    def __init__(self, spec: RowSpec, header: list[str]) -> None:
        self._spec = spec
        missing = set(spec.columns) - set(header)
        # Columns added after this contract shipped may legitimately be absent
        # from an older payload; anything else missing is drift and fails loud.
        drift = missing - spec.additive
        if drift:
            raise ValueError(f"{spec.kind}: incoming header missing columns {sorted(drift)}")
        self._pos = {col: header.index(col) for col in spec.columns if col in header}
        self._absent = frozenset(missing)

    def get(self, row: list[str], column: str) -> str:
        pos = self._pos.get(column)
        if pos is None:
            if column in self._absent:
                return ""      # this payload predates the column
            raise KeyError(f"{self._spec.kind}: {column!r} is not in this spec")
        # A short row (a payload truncated mid-write) must read as empty rather
        # than raise an IndexError nothing upstream would recognise.
        return row[pos] if pos < len(row) else ""

    def as_dict(self, row: list[str]) -> dict[str, str]:
        return {col: self.get(row, col) for col in self._spec.columns}


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):  # explicit: True -> "1" (P5)
        return "1" if value else "0"
    return str(value)
