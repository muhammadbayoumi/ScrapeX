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

    def __post_init__(self) -> None:
        missing = self.required - set(self.columns)
        if missing:  # a spec that requires a column it doesn't define is a bug
            raise ValueError(f"{self.kind}: required columns not in spec: {missing}")

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
    ),
    required=frozenset({"external_product_id", "region", "currency", "vat_included", "effective_price"}),
)

# ---- commodity_price: globalpetrolprices / aramco fuel rows -----------------
COMMODITY_PRICE = RowSpec(
    kind=ExtractKind.COMMODITY_PRICE,
    columns=(
        "material_key",          # DIESEL | GASOLINE_91 | ...
        "region",                # country ISO code, or 'SA'
        "currency",
        "unit",                  # 'USD/liter'
        "vat_included",
        "effective_price",
        "observed_label",        # the date string printed on the page
    ),
    required=frozenset({"material_key", "region", "currency", "effective_price"}),
)

_BY_KIND = {spec.kind: spec for spec in (PRODUCT_PRICES, COMMODITY_PRICE)}


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
        if missing:
            raise ValueError(f"{spec.kind}: incoming header missing columns {sorted(missing)}")
        self._pos = {col: header.index(col) for col in spec.columns}

    def get(self, row: list[str], column: str) -> str:
        return row[self._pos[column]]

    def as_dict(self, row: list[str]) -> dict[str, str]:
        return {col: row[pos] for col, pos in self._pos.items()}


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):  # explicit: True -> "1" (P5)
        return "1" if value else "0"
    return str(value)
