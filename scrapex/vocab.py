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
    ARAMCO_FUEL_PAGE = "aramco-fuel-page"
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


class RunMode(StrEnum):
    """How a job treats existing data (spec section 13). FULL_REBUILD always
    archives first — old data is never destroyed silently."""

    INITIAL_CRAWL = "initial_crawl"
    UPDATE = "update"
    FULL_REBUILD = "full_rebuild"
    # Collect the source's OWN published history (e.g. ten years of weekly
    # prices) as reported rows. A capability, not a universal mode: only a
    # connector that knows where its source publishes history can run it, and
    # the Run panel offers it per source accordingly. Idempotent by
    # construction — the observation dedupe key includes the business date.
    HISTORY_BACKFILL = "history_backfill"


class JobStatus(StrEnum):
    """Persisted job lifecycle (spec section 23). A job outlives the side panel:
    closing the panel never stops it, reopening re-reads this status."""

    SCHEDULED = "scheduled"
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    PAUSING = "pausing"
    PAUSED = "paused"
    RESUMING = "resuming"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    # Every source ran, but at least one run degraded (partial ingest). Distinct
    # from PARTIALLY_COMPLETED (a whole source failed) and from COMPLETED — a
    # job that swallowed ingest errors used to finish 'completed' with the
    # messages discarded, which is how a stranded run went unnoticed live.
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"
    REQUIRES_REVIEW = "requires_review"


# Statuses that mean "this job will never run again" — safe to ignore on restart.
TERMINAL_JOB_STATUSES = frozenset({
    JobStatus.CANCELLED, JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_ERRORS,
    JobStatus.PARTIALLY_COMPLETED, JobStatus.FAILED,
})

# Statuses where the worker is actively holding the job, so a pause/cancel has to
# wait for its next safe boundary. Anything else is settled immediately instead —
# the worker only ever picks up `queued`, so a transitional status on a job it is
# not holding would never be resolved by anyone.
WORKER_HELD_STATUSES = frozenset({
    JobStatus.PREPARING.value, JobStatus.RUNNING.value, JobStatus.RESUMING.value,
})

# "Occupying the worker, or waiting for it." Deliberately NOT every non-terminal
# status: `paused` and `requires_review` wait on the OWNER and never advance on
# their own, so treating them as busy would silently block a source's schedule
# forever.
BLOCKING_JOB_STATUSES = frozenset({
    JobStatus.SCHEDULED.value, JobStatus.QUEUED.value, JobStatus.PREPARING.value,
    JobStatus.RUNNING.value, JobStatus.RESUMING.value, JobStatus.PAUSING.value,
    JobStatus.CANCELLING.value,
})


class JobControl(StrEnum):
    """Owner intent, stored in the DB (not in memory) so pause/cancel survives a
    runtime restart and is visible to any process reading the job."""

    NONE = "none"
    PAUSE = "pause"
    RESUME = "resume"
    CANCEL = "cancel"


class JobStage(StrEnum):
    """Coarse stage inside a running job — aggregated progress only (spec 25:
    never one UI event per record)."""

    PREPARING = "preparing"
    FETCHING = "fetching"
    INGESTING = "ingesting"
    FINALIZING = "finalizing"


class LogLevel(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ScheduleFrequency(StrEnum):
    MANUAL = "manual"
    DAILY = "daily"
    WEEKLY = "weekly"


class MissedRunPolicy(StrEnum):
    """What to do about a slot that passed while the machine was off.

    Browser alarms cannot wake a sleeping or powered-off device, and neither can
    we — so a missed slot is a real, expected state, not an error.
    """

    RUN_WHEN_AVAILABLE = "run_when_available"   # fire ONCE on catch-up
    SKIP = "skip"                               # let it go, wait for the next slot


class OverlapPolicy(StrEnum):
    """What to do when the previous run for this source is still going."""

    QUEUE = "queue"     # let it line up behind the running one
    SKIP = "skip"       # drop this occurrence entirely


class ChangeType(StrEnum):
    """Field-level change classification (spec section 15).

    price_increase/decrease are split out because they are what the owner
    actually watches; field_updated covers everything else (name, url, brand).
    'removed' is only ever emitted by a sweep after a COMPLETE crawl — a partial
    crawl must never be allowed to declare a catalogue gone.
    """

    NEW = "new"
    FIELD_UPDATED = "field_updated"
    PRICE_INCREASE = "price_increase"
    PRICE_DECREASE = "price_decrease"
    UNAVAILABLE = "unavailable"
    RETURNED = "returned"
    REMOVED = "removed"
