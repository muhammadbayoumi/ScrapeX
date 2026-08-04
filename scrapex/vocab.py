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


class Block(StrEnum):
    """Which part of the sentence a MAIN-TABLE column belongs to.

    DetailGroup below files a fact into the record panel. This files a column
    into the table itself, and they are different questions: a column can be
    in the table and still belong to a block, and a fact can be in a group and
    never be a column at all.

    The owner's agreed reading order, «الهوية ثم العرض ثم التصنيف»:

      IDENTITY    which thing this row is — the name, the sku, the variant
      OFFER       what it costs and on what terms — the reason the table exists
      FILING      where the shop files it — brand, category, every level
      PROVENANCE  where the row came from and when it was last true

    It exists because the table opened with twenty-seven filing columns before
    the price. Measured on the owner's MADAR: price at grid index 18, and ten
    of the eighteen before it were classification.
    """

    IDENTITY = "identity"
    OFFER = "offer"
    FILING = "filing"
    PROVENANCE = "provenance"


# The reading order itself. A column's block decides where it sits; its
# position inside the block stays exactly where its author put it.
BLOCK_ORDER: tuple[Block, ...] = (
    Block.IDENTITY, Block.OFFER, Block.FILING, Block.PROVENANCE)


class DetailGroup(StrEnum):
    """Where a detail is filed in the record panel. Owner ruling
    2026-07-26: FIVE groups, and anything a future site publishes goes
    under one of them.

    === THE OWNER'S FILING RULES — THIS IS THE FIXED PLACE ==============
    Recorded here at his explicit instruction («سجل المعلومات هذه فى مكان
    ثابت فى الكود بحيث لا ينسى اى شخص من استخدامها») so no connector
    author can miss them:

    1. `STORE` — facts about THIS store's handling of the product rather
       than the product itself: availability (متوفر أم لا), stock count
       (sika states its pieces), shipping method (madar's «طريقة الشحن»),
       and the store's own code for the item (sku).

    2. THE BOUNDARY between Specifications and More information is what
       the fact DESCRIBES: a property OF the product (coating, grade,
       thickness) files under SPECIFICATIONS; information ABOUT the
       product (manufacturer, origin, country of manufacture) files
       under MORE_INFORMATION.

    3. `SITE_METADATA` — facts about the PAGE, not about the product or
       the store. madar publishes no_index / no_follow / no_archive on
       every product: robots directives for its own site, which arrived
       here only because the connector takes every visible attribute.
       Kept rather than dropped (owner, 2026-07-28) so nothing the site
       states is silently discarded — but filed where it cannot crowd
       out a product fact. sika's search `keywords` file here too.

    4. STANDING RULE — a NEW kind of fact, from any site, is NEVER filed
       by a developer's judgement. ASK THE OWNER which group it belongs
       to, or whether it needs a new group. He said exactly this: «اى
       معلومة نلاقيها عن منتج فى المستقبل اسالنى نحطها فى انهو جروب».
       group_for_code() below reports every code it did NOT recognise so
       the question can actually be asked, instead of the fallback
       quietly absorbing it.
    ====================================================================

    Closed on purpose. Every connector used to invent its own headings,
    so one warehouse held ten — Specifications AND Specs on the same
    source, beside Measurements, Attributes, Classification and Filters.
    A reader learning where to look had to learn it again per site.

    "The site filters by this" is NOT a group: it is a property of the
    row (`is_site_filter`), because it says something about the fact
    rather than about where a person should look for it.
    """

    DESCRIPTION = "Description"            # prose the site wrote
    SPECIFICATIONS = "Specifications"      # properties OF the product
    ATTACHMENTS = "Attachments"            # files to open: datasheets, manuals
    MORE_INFORMATION = "More information"  # information ABOUT the product
    MEDIA = "Media"                        # images
    STORE = "Store"                        # THIS store's handling of it
    SITE_METADATA = "Site metadata"        # about the PAGE, not the product


# One presentation order for every surface that lists detail groups. Media is
# last because the record card already renders its gallery before the inspector.
DETAIL_GROUP_ORDER = (
    DetailGroup.DESCRIPTION.value,
    DetailGroup.SPECIFICATIONS.value,
    DetailGroup.MORE_INFORMATION.value,
    DetailGroup.STORE.value,
    DetailGroup.SITE_METADATA.value,
    DetailGroup.ATTACHMENTS.value,
    DetailGroup.MEDIA.value,
)


# WHERE EACH KNOWN FACT IS FILED — the fixed place the owner asked for, so no
# connector author has to remember the rules or invent an answer.
#
# Every code below was read out of the live warehouse, not imagined: these are
# the facts madar, sika and samehgabriel actually publish today.
_DETAIL_GROUP_BY_CODE: dict[str, DetailGroup] = {
    # THIS STORE's handling of the product, not the product.
    "am_shipping_type": DetailGroup.STORE,      # madar's «طريقة الشحن»
    "stock_quantity": DetailGroup.STORE,
    "min_stock_level": DetailGroup.STORE,
    "max_stock_level": DetailGroup.STORE,
    "availability": DetailGroup.STORE,
    "sku": DetailGroup.STORE,                   # the store's own code for it
    "trade_tier_price": DetailGroup.STORE,      # until it becomes a price column
    # About the PAGE. Robots directives madar publishes per product.
    "no_index": DetailGroup.SITE_METADATA,
    "no_follow": DetailGroup.SITE_METADATA,
    "no_archive": DetailGroup.SITE_METADATA,
    "keywords": DetailGroup.SITE_METADATA,
    # The page's own <title>, which is not the product's name and sometimes
    # disagrees with it: madar's epoxy rebar is «من حديد» (Hadeed) in `name`
    # while meta_title says «سابك» (SABIC), and the image is epoxy_sabic.png.
    # That is the SITE's inconsistency and we record it rather than resolve
    # it — source truth is never edited. Filed here because it describes the
    # PAGE, so it cannot crowd out a product fact.
    "meta_title": DetailGroup.SITE_METADATA,
    "meta_description": DetailGroup.SITE_METADATA,
    "meta_keyword": DetailGroup.SITE_METADATA,
    # Information ABOUT the product — the owner's own three examples.
    "manufacturer": DetailGroup.MORE_INFORMATION,
    "origin": DetailGroup.MORE_INFORMATION,
    "country_of_manufacture": DetailGroup.MORE_INFORMATION,
    "brand": DetailGroup.MORE_INFORMATION,
    "category": DetailGroup.MORE_INFORMATION,
    "tag": DetailGroup.MORE_INFORMATION,
    # Properties OF the product. Everything here used to sit in More
    # information because the connector had no rule finer than "not an image,
    # not a description, not a facet".
    "coating": DetailGroup.SPECIFICATIONS,      # the owner's own example
    "color": DetailGroup.SPECIFICATIONS,
    "pa_color": DetailGroup.SPECIFICATIONS,
    "size": DetailGroup.SPECIFICATIONS,
    "surface": DetailGroup.SPECIFICATIONS,
    "surface_finish": DetailGroup.SPECIFICATIONS,
    "material_type": DetailGroup.SPECIFICATIONS,
    "material_grade": DetailGroup.SPECIFICATIONS,
    "reinforcement_type": DetailGroup.SPECIFICATIONS,
    "reinforcement_weight": DetailGroup.SPECIFICATIONS,
    "feature": DetailGroup.SPECIFICATIONS,
    "chuck_size": DetailGroup.SPECIFICATIONS,
    "no_load_speed": DetailGroup.SPECIFICATIONS,
    "power_input": DetailGroup.SPECIFICATIONS,
    "power_source": DetailGroup.SPECIFICATIONS,
    "voltage": DetailGroup.SPECIFICATIONS,
    "wattage": DetailGroup.SPECIFICATIONS,
    "weight": DetailGroup.SPECIFICATIONS,
    # The 41 the live warehouse held that the map had never been taught.
    # Read out of madar and samehgabriel with a real value beside each, and
    # filed under the owner's OWN boundary rather than a developer's taste:
    # every one is a stated property of the product.
    "amperage": DetailGroup.SPECIFICATIONS,
    "base_type": DetailGroup.SPECIFICATIONS,
    "battery_capacity": DetailGroup.SPECIFICATIONS,
    "battery_type": DetailGroup.SPECIFICATIONS,
    "blade_size": DetailGroup.SPECIFICATIONS,
    "breaking_capacity_ka": DetailGroup.SPECIFICATIONS,
    "cct": DetailGroup.SPECIFICATIONS,          # colour temperature, 2700K
    "cement_type": DetailGroup.SPECIFICATIONS,
    "conduit_type": DetailGroup.SPECIFICATIONS,
    "cylinder_size": DetailGroup.SPECIFICATIONS,
    "density": DetailGroup.SPECIFICATIONS,
    "density_kgm3": DetailGroup.SPECIFICATIONS,
    "drill_bit_type": DetailGroup.SPECIFICATIONS,
    "drying_method": DetailGroup.SPECIFICATIONS,
    "ff_type": DetailGroup.SPECIFICATIONS,      # film-faced type
    "gangs": DetailGroup.SPECIFICATIONS,
    "glue_type": DetailGroup.SPECIFICATIONS,
    "grade": DetailGroup.SPECIFICATIONS,
    "horse_power": DetailGroup.SPECIFICATIONS,
    "lock_body_size": DetailGroup.SPECIFICATIONS,
    "max_disc_diameter": DetailGroup.SPECIFICATIONS,
    "mesh_size": DetailGroup.SPECIFICATIONS,
    "module_capacity": DetailGroup.SPECIFICATIONS,
    "moisture_content": DetailGroup.SPECIFICATIONS,
    "mounting_type": DetailGroup.SPECIFICATIONS,
    "number_of_ways": DetailGroup.SPECIFICATIONS,
    "poles": DetailGroup.SPECIFICATIONS,
    "port_type": DetailGroup.SPECIFICATIONS,
    "rated_current_a": DetailGroup.SPECIFICATIONS,
    "shape": DetailGroup.SPECIFICATIONS,
    "socket_type": DetailGroup.SPECIFICATIONS,
    "suction_force": DetailGroup.SPECIFICATIONS,
    "switch_function": DetailGroup.SPECIFICATIONS,
    "switch_type": DetailGroup.SPECIFICATIONS,
    "treatment": DetailGroup.SPECIFICATIONS,
    "veneer_type": DetailGroup.SPECIFICATIONS,
    # heidelbergmaterials.eg publishes four technical blocks per cement and
    # none of their codes was in this map, so group_for_code reported all four
    # as unrecognised and the standing ASK rule above fired. The owner ruled on
    # 2026-07-29: all four under Specifications, by his own boundary — every one
    # of them states a property OF the cement (setting time, SO3 <=3.5%,
    # conformity to ES 4756/1-2022, what the cement is for), not information
    # about it. Recorded here so the fallback never absorbs them again.
    "physical_characteristics": DetailGroup.SPECIFICATIONS,
    "chemical_characteristics": DetailGroup.SPECIFICATIONS,
    "characteristics": DetailGroup.SPECIFICATIONS,
    "applications": DetailGroup.SPECIFICATIONS,
    # samehgabriel names its attributes in Arabic, `pa_` prefixed.
    "pa_المقاس": DetailGroup.SPECIFICATIONS,
    "pa_التطبيق": DetailGroup.SPECIFICATIONS,
    "pa_توع-الفولت": DetailGroup.SPECIFICATIONS,
    "pa_نوع-الكابل": DetailGroup.SPECIFICATIONS,
    # ...except the warranty, which the owner ruled is a COMMITMENT made
    # with the sale and not a property of the goods: two shops selling the
    # same item can warrant it differently.
    "pa_الضمان": DetailGroup.STORE,
}

# Shapes rather than names, for the families a site invents freely. A
# measurement is a property of the product whatever the shop calls it, and
# waiting to be asked about `width_mm` when `length_mm` is already known would
# be pedantry rather than care.
_DETAIL_GROUP_BY_SUFFIX: tuple[tuple[str, DetailGroup], ...] = (
    ("_mm", DetailGroup.SPECIFICATIONS),
    ("_cm", DetailGroup.SPECIFICATIONS),
    ("_inch", DetailGroup.SPECIFICATIONS),
    ("_meters", DetailGroup.SPECIFICATIONS),
    ("_kg", DetailGroup.SPECIFICATIONS),
)
_DETAIL_GROUP_BY_PREFIX: tuple[tuple[str, DetailGroup], ...] = (
    ("image", DetailGroup.MEDIA),
    ("attachment", DetailGroup.ATTACHMENTS),
    ("attr_", DetailGroup.SPECIFICATIONS),      # sika's own numbered spec slots
    ("description", DetailGroup.DESCRIPTION),
    ("short_description", DetailGroup.DESCRIPTION),
    ("full_description", DetailGroup.DESCRIPTION),
    ("summary", DetailGroup.DESCRIPTION),
)


def group_for_code(code: str) -> "tuple[DetailGroup, bool]":
    """(group, recognised) for one attribute code.

    The language mark is stripped first: `coating` and `coating_ar` are ONE
    fact in two languages and must never file in two places.

    `recognised` is False when nothing matched and the catch-all was used. It
    exists so the owner's standing rule can actually run — a connector reports
    what it did not recognise, and he is asked where it belongs, instead of the
    fallback silently absorbing every new fact forever.
    """
    base = code.removesuffix("_ar")
    if base in _DETAIL_GROUP_BY_CODE:
        return _DETAIL_GROUP_BY_CODE[base], True
    for prefix, group in _DETAIL_GROUP_BY_PREFIX:
        if base.startswith(prefix):
            return group, True
    for suffix, group in _DETAIL_GROUP_BY_SUFFIX:
        if base.endswith(suffix):
            return group, True
    return DetailGroup.MORE_INFORMATION, False


class DisplayMethod(StrEnum):
    """HOW THE SITE PRESENTS A PRODUCT — a property of the product, constant
    across every row it produces.

    Not to be confused with what one unit of the price BUYS, which is a
    property of the OFFER and differs per member (source_offer carries that:
    selling_unit_id, basis_quantity, minimum_quantity, quantity_increment,
    quantity_is_decimal). Conflating the two is what made a MADAR row
    unreadable: a grouped rebar member and a simple bag of cement arrived
    looking identical, and neither said which it was.

    THE STRUCTURAL POINT, measured on madar's live census 2026-07-29: "sold by
    a bulk unit" is NOT a fourth shape. It appears INSIDE GroupedProduct (96
    leaves) and INSIDE ConfigurableProduct (13 leaves, the steel mesh). So it
    cannot be a fifth value here — a single enum over `__typename` would miss
    it — and it lives on the offer instead. Two columns, two questions.

    `has_variants` is NOT this column and must never be reused as it: it reads
    1 for 763 of 763 madar products and for every product of sources 1,2,3,4,7,
    8,9, because a simple product is emitted as row(uid, uid) and the flag only
    ever asked whether external_variant_id was non-empty.

    '' is a shape nobody has studied yet, and it is NEVER guessed. A future
    BundleProduct arrives blank rather than filed as the nearest thing.
    """

    SINGLE = "single"                       # one product, one price
    OPTIONS_ONE_PRICE = "options_one_price"  # options, all at the same price
    OPTIONS_PRICED = "options_priced"       # options priced apart ("from X")
    MEMBER_LIST = "member_list"             # the page prices the MEMBERS


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
    # A bespoke ASP.NET Web API on a host of its own, whose price is not a
    # number on the product but a row in a separate matrix keyed by
    # governorate, plant, quantity tier and customer segment. custom-json-api
    # is the near miss and cannot serve it: it composes its endpoint from
    # base_url and never reads api.base_url, and its price model is a scalar.
    HEIDELBERG_PRICE_MATRIX = "heidelberg-price-matrix"
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
