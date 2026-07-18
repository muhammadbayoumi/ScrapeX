"""Single source of truth for all enum vocabularies (ENGINEERING.md Q1, Q5).

Every status/kind/mode string used anywhere in the codebase is defined HERE
and only here. Modules import these enums; string literals of these values
elsewhere are a review defect.

The CHECK constraints in db/schema.sql mirror these values; test_schema.py
asserts the two never drift.
"""
from __future__ import annotations

import enum


class StrEnum(str, enum.Enum):
    """str-valued enum: JSON/SQLite-friendly, explicit over clever (P5)."""

    def __str__(self) -> str:  # so f"{CurationStatus.SELECTED}" == "selected"
        return self.value


class CurationStatus(StrEnum):
    """The owner's census gate on source_product (gate 3 of 5, A5)."""

    INVENTORIED = "inventoried"
    SELECTED = "selected"
    IGNORED = "ignored"


class ReviewStatus(StrEnum):
    """Human review verdict on matches / classification mappings (gate 4 of 5)."""

    PENDING = "pending"
    APPROVED = "approved"
    IGNORED = "ignored"


class Authority(StrEnum):
    """Trust tier of a source; official outranks aggregator at publish."""

    OFFICIAL = "official"
    AGGREGATOR = "aggregator"
    SHOP = "shop"


class Cadence(StrEnum):
    """How often a source is collected (mirrors the add-in's SyncFrequency)."""

    MANUAL = "manual"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class ExtractKind(StrEnum):
    """What a manifest extract block is allowed to produce."""

    PRODUCT_PRICES = "product_prices"
    COMMODITY_PRICE = "commodity_price"
    ENRICHMENT = "enrichment"


class ExtractScope(StrEnum):
    """Contract width. CENSUS temporarily opens the contract gate (A5);
    LATEST_ONLY is the globalpetrolprices license obligation (tested, T6)."""

    TARGETED = "targeted"
    CENSUS = "census"
    LATEST_ONLY = "latest_only"


class Fetcher(StrEnum):
    """Transport a connector requests. BROWSER = Playwright (owner-decided
    day-one infrastructure, A3 carve-out)."""

    HTTP = "http"
    BROWSER = "browser"


class ConnectorFamily(StrEnum):
    """The proven connector families (one per probed platform contract)."""

    MAGENTO_GRAPHQL = "magento-graphql"
    SHOPIFY_JSON = "shopify-json"
    WOOCOMMERCE_STOREAPI = "woocommerce-storeapi"
    HYBRIS_OCC = "hybris-occ"
    CUSTOM_JSON_API = "custom-json-api"
    SALLA_HTML = "salla-html"
    ZID_HTML = "zid-html"
    STATIC_HTML_TABLE = "static-html-table"
    DATASHEET_ENRICHMENT = "datasheet-enrichment"
    TBD_PROBE = "TBD-probe"  # placeholder until `scrapex probe` classifies the site


class RunStatus(StrEnum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class Availability(StrEnum):
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    UNKNOWN = "unknown"


class VatMode(StrEnum):
    INCLUSIVE = "incl"
    EXCLUSIVE = "excl"


class PayloadClient(StrEnum):
    """Which producer emitted a funnel payload (T8: both speak ONE contract)."""

    CLI = "cli"
    EXTENSION = "extension"
