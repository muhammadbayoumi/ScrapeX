-- ============================================================================
-- ScrapeX Warehouse — schema.sql (migration 0001, PRAGMA user_version = 1)
-- ============================================================================
-- The owner's 12-section relational model, verbatim, plus two additions decided
-- in design review: source_product.curation_status (census curation gate) and
-- feed_assignment (section 13, row-level publish preference).
--
-- RULES THIS FILE ENFORCES (ENGINEERING.md):
--   A7  price_observation is append-only — enforced by triggers, not convention.
--   A8  expected volumes + index notes documented here, in the DDL itself.
--   Q1  this file is the ONLY source of DDL truth; code never builds schema.
--   S6  applied via numbered migrations + PRAGMA user_version.
--
-- EXPECTED VOLUMES (A8, revisit when reality disagrees):
--   material / material_variant : hundreds — thousands
--   source_product / _variant   : ~10k across ~10-30 sources
--   source_offer                : ~10-50k
--   price_observation           : the ONLY fast-growing table. ~10 sources x
--                                 daily-weekly cadence => ~1-5M rows/year.
--                                 All reads MUST be paginated or capped and go
--                                 through ix_price_obs_offer_time.
--   crawl_run / raw_snapshot    : 1 row/run + 1 row/fetched page; snapshots
--                                 live gzipped on disk, path stored here.
-- ============================================================================

PRAGMA foreign_keys = ON;

-- ============================================================
-- SECTION 0: SMALL REFERENCE TABLES
-- ============================================================

CREATE TABLE brand (
    brand_id     INTEGER PRIMARY KEY,
    brand_name   TEXT NOT NULL UNIQUE,
    brand_name_ar TEXT,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE selling_unit (
    selling_unit_id INTEGER PRIMARY KEY,
    unit_code       TEXT NOT NULL UNIQUE,   -- 'piece' | 'm' | 'm2' | 'pack' | 'liter' | 'kg' | 'sheet' ...
    name_ar         TEXT,
    name_en         TEXT
);

-- ============================================================
-- SECTION 1: THE UNIFIED MATERIAL (الخامة الموحدة)
-- Represents the real product regardless of site. NO PRICE HERE.
-- ============================================================

CREATE TABLE material (
    material_id              INTEGER PRIMARY KEY,
    material_name_ar         TEXT,
    material_name_en         TEXT,
    brand_id                 INTEGER REFERENCES brand(brand_id),
    manufacturer_part_number TEXT,
    gtin                     TEXT,           -- barcode/EAN when known (masdaronline delivers real ones)
    material_type            TEXT NOT NULL DEFAULT 'raw_material'
        CHECK (material_type IN ('raw_material','product','accessory','service','commodity')),
    status                   TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active','discontinued','needs_review')),
    created_at               TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX ix_material_gtin ON material(gtin) WHERE gtin IS NOT NULL;

-- ============================================================
-- SECTION 2: MATERIAL VARIANTS (حالات الخامة)
-- Every size/thickness/color/pack is an independent variant.
-- spec_fingerprint example: 'length=3.66m|width=2.74m|thickness=12mm|unit=sheet'
-- ============================================================

CREATE TABLE material_variant (
    variant_id       INTEGER PRIMARY KEY,
    material_id      INTEGER NOT NULL REFERENCES material(material_id),
    variant_code     TEXT,
    variant_name     TEXT,
    selling_unit_id  INTEGER REFERENCES selling_unit(selling_unit_id),
    pack_quantity    REAL,
    spec_fingerprint TEXT,
    status           TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','discontinued')),
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX ix_material_variant_material ON material_variant(material_id);
CREATE UNIQUE INDEX ux_material_variant_fingerprint
    ON material_variant(material_id, spec_fingerprint) WHERE spec_fingerprint IS NOT NULL;

-- ============================================================
-- SECTION 3: SOURCE SITES (المواقع والمصادر)
-- ============================================================

CREATE TABLE source_site (
    source_id        INTEGER PRIMARY KEY,
    source_key       TEXT NOT NULL UNIQUE,   -- join key with sources.yaml (the Harvest Manifest)
    source_name      TEXT NOT NULL,          -- 'المدار', 'السويد', ...
    base_url         TEXT,
    platform         TEXT,                   -- 'Magento2' | 'Salla' | 'Zid' | 'Shopify' | ... | 'Unknown'
    currency         TEXT,                   -- 'SAR' | 'EGP' | 'USD'
    timezone         TEXT,                   -- 'Asia/Riyadh'
    default_vat_mode TEXT NOT NULL DEFAULT 'incl' CHECK (default_vat_mode IN ('incl','excl')),
    authority        TEXT NOT NULL DEFAULT 'shop' CHECK (authority IN ('official','aggregator','shop')),
    active           INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0,1))
);

-- ============================================================
-- SECTION 4: PRODUCT AS SEEN AT THE SOURCE (المنتج كما يظهر في المصدر)
-- Source-local vocabulary preserved verbatim; never mutated by matching.
-- curation_status = the owner's census gate (design review addition):
--   inventoried -> census landed it, no decision yet
--   selected    -> owner admitted it into match/classify
--   ignored     -> owner rejected it; kept so re-crawls never resurface it as new
-- ============================================================

CREATE TABLE source_product (
    source_product_id   INTEGER PRIMARY KEY,
    source_id           INTEGER NOT NULL REFERENCES source_site(source_id),
    external_product_id TEXT NOT NULL,       -- the site's own id ('4672', UUID, slug)
    external_sku        TEXT,
    source_name         TEXT,                -- the product's original name at the source
    product_url         TEXT,
    brand_raw           TEXT,                -- brand exactly as the site wrote it
    has_variants        INTEGER NOT NULL DEFAULT 0 CHECK (has_variants IN (0,1)),
    raw_specs_json      TEXT,
    curation_status     TEXT NOT NULL DEFAULT 'inventoried'
        CHECK (curation_status IN ('inventoried','selected','ignored')),
    first_seen_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    last_seen_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    status              TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','vanished','discontinued')),
    UNIQUE (source_id, external_product_id)  -- the owner's mandated constraint
);

CREATE INDEX ix_source_product_curation ON source_product(source_id, curation_status);

-- ============================================================
-- SECTION 5: VARIANT AS SEEN AT THE SOURCE (حالة المنتج داخل الموقع)
-- Preferred key: source + external_variant_id (madar delivers real ids).
-- Fallback when the site gives no variant id: product + option_fingerprint.
-- Never key on SKU alone (owner rule; proven by madar sharing SKUs).
-- ============================================================

CREATE TABLE source_variant (
    source_variant_id   INTEGER PRIMARY KEY,
    source_product_id   INTEGER NOT NULL REFERENCES source_product(source_product_id),
    external_variant_id TEXT,                -- '4670' when the platform provides one
    external_sku        TEXT,
    option_fingerprint  TEXT,                -- 'thickness_mm=12' — canonical, sorted, lowercase
    option_label        TEXT,                -- what the user sees: '12 mm'
    raw_options_json    TEXT,
    first_seen_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    last_seen_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE UNIQUE INDEX ux_source_variant_external
    ON source_variant(source_product_id, external_variant_id)
    WHERE external_variant_id IS NOT NULL;
CREATE UNIQUE INDEX ux_source_variant_fingerprint
    ON source_variant(source_product_id, option_fingerprint)
    WHERE external_variant_id IS NULL AND option_fingerprint IS NOT NULL;

-- ============================================================
-- SECTION 6: OFFERS (العروض)
-- One source variant can carry several offers (branch/region/segment/unit).
-- region: ISO 3166-1 alpha-2 ('SA','EG') or '*' — TEXT by design so it joins
-- feed_assignment.region and the manifest vocabulary directly.
-- ============================================================

CREATE TABLE source_offer (
    offer_id          INTEGER PRIMARY KEY,
    source_variant_id INTEGER NOT NULL REFERENCES source_variant(source_variant_id),
    branch_id         TEXT,                  -- site branch/store code when present
    region            TEXT NOT NULL DEFAULT '*',
    customer_segment  TEXT NOT NULL DEFAULT 'retail'
        CHECK (customer_segment IN ('retail','wholesale','contractor','business')),
    selling_unit_id   INTEGER REFERENCES selling_unit(selling_unit_id),
    basis_quantity    REAL NOT NULL DEFAULT 1,   -- price is per how many units
    minimum_quantity  REAL,
    currency          TEXT NOT NULL,
    vat_included      INTEGER NOT NULL CHECK (vat_included IN (0,1))
);

CREATE UNIQUE INDEX ux_source_offer_identity
    ON source_offer(source_variant_id, COALESCE(branch_id,''), region, customer_segment,
                    COALESCE(selling_unit_id,0), basis_quantity);

-- ============================================================
-- SECTION 7: PRICE OBSERVATIONS (تاريخ الأسعار)
-- THE most important table. APPEND-ONLY: no row is ever updated or deleted —
-- enforced structurally by the two triggers below (A7).
-- Idempotent ingest: INSERT OR IGNORE against ux_price_obs_dedupe.
-- ============================================================

CREATE TABLE price_observation (
    price_observation_id INTEGER PRIMARY KEY,
    offer_id             INTEGER NOT NULL REFERENCES source_offer(offer_id),
    observed_at          TEXT NOT NULL,      -- UTC ISO8601: when the price was read
    business_date        TEXT NOT NULL,      -- 'YYYY-MM-DD' working day
    regular_price        REAL,
    sale_price           REAL,
    effective_price      REAL NOT NULL,
    currency             TEXT NOT NULL,
    vat_included         INTEGER NOT NULL CHECK (vat_included IN (0,1)),
    availability         TEXT NOT NULL DEFAULT 'unknown'
        CHECK (availability IN ('in_stock','out_of_stock','unknown')),
    stock_quantity       REAL,
    run_id               INTEGER NOT NULL REFERENCES crawl_run(run_id),
    snapshot_id          INTEGER REFERENCES raw_snapshot(snapshot_id),
    record_hash          TEXT NOT NULL       -- hash of price+state; the change/dedupe key
);

-- The owner's mandated primary read path:
CREATE INDEX ix_price_obs_offer_time ON price_observation(offer_id, observed_at DESC);
-- Idempotency: same offer, same business day, same content -> one row.
CREATE UNIQUE INDEX ux_price_obs_dedupe ON price_observation(offer_id, business_date, record_hash);

-- A7: append-only, enforced in the schema itself (not by convention, not by grep).
CREATE TRIGGER trg_price_obs_no_update
BEFORE UPDATE ON price_observation
BEGIN
    SELECT RAISE(ABORT, 'price_observation is append-only (ENGINEERING.md A7)');
END;

CREATE TRIGGER trg_price_obs_no_delete
BEFORE DELETE ON price_observation
BEGIN
    SELECT RAISE(ABORT, 'price_observation is append-only (ENGINEERING.md A7)');
END;

-- ============================================================
-- SECTION 8: ATTRIBUTES (المواصفات) — hybrid: raw text + normalized value
-- ============================================================

CREATE TABLE attribute_definition (
    attribute_id        INTEGER PRIMARY KEY,
    attribute_code      TEXT NOT NULL UNIQUE,  -- 'length'
    name_ar             TEXT,                  -- 'الطول'
    name_en             TEXT,
    data_type           TEXT NOT NULL DEFAULT 'text' CHECK (data_type IN ('number','text','bool','date')),
    canonical_unit_id   INTEGER REFERENCES selling_unit(selling_unit_id),
    is_variant_defining INTEGER NOT NULL DEFAULT 0 CHECK (is_variant_defining IN (0,1)),
    is_matching_key     INTEGER NOT NULL DEFAULT 0 CHECK (is_matching_key IN (0,1))
);

CREATE TABLE variant_attribute_value (
    variant_attribute_value_id INTEGER PRIMARY KEY,
    variant_id          INTEGER NOT NULL REFERENCES material_variant(variant_id),
    attribute_id        INTEGER NOT NULL REFERENCES attribute_definition(attribute_id),
    raw_value           TEXT,                -- '3660 مم' exactly as captured
    numeric_value       REAL,                -- 3.66
    normalized_unit_id  INTEGER REFERENCES selling_unit(selling_unit_id),
    source_snapshot_id  INTEGER REFERENCES raw_snapshot(snapshot_id),
    valid_from          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    valid_to            TEXT                 -- NULL = current (retirement, never deletion)
);

CREATE INDEX ix_variant_attr_current ON variant_attribute_value(variant_id, attribute_id) WHERE valid_to IS NULL;

CREATE TABLE material_attribute_value (
    material_attribute_value_id INTEGER PRIMARY KEY,
    material_id         INTEGER NOT NULL REFERENCES material(material_id),
    attribute_id        INTEGER NOT NULL REFERENCES attribute_definition(attribute_id),
    raw_value           TEXT,
    numeric_value       REAL,
    normalized_unit_id  INTEGER REFERENCES selling_unit(selling_unit_id),
    source_snapshot_id  INTEGER REFERENCES raw_snapshot(snapshot_id),
    valid_from          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    valid_to            TEXT
);

CREATE INDEX ix_material_attr_current ON material_attribute_value(material_id, attribute_id) WHERE valid_to IS NULL;

-- ============================================================
-- SECTION 9: CLASSIFICATIONS (التصنيفات المتعددة والداخلية)
-- Hub-and-spoke: every site's tree is preserved; equivalence across sites is
-- expressed transitively through internal-scheme nodes (never pairwise).
-- ============================================================

CREATE TABLE classification_scheme (
    scheme_id   INTEGER PRIMARY KEY,
    scheme_name TEXT NOT NULL UNIQUE,        -- 'تصنيفات المدار' | 'التصنيف التجاري الداخلي' | 'UNSPSC'
    scheme_type TEXT NOT NULL CHECK (scheme_type IN ('source','internal','standard')),
    source_id   INTEGER REFERENCES source_site(source_id)  -- set when scheme_type='source'
);

CREATE TABLE classification_node (
    node_id        INTEGER PRIMARY KEY,
    scheme_id      INTEGER NOT NULL REFERENCES classification_scheme(scheme_id),
    parent_node_id INTEGER REFERENCES classification_node(node_id),
    external_id    TEXT,                     -- site category id (madar uid, salla c-id)
    node_code      TEXT,
    node_name      TEXT NOT NULL,
    category_url   TEXT,
    level          INTEGER NOT NULL DEFAULT 1
);

CREATE UNIQUE INDEX ux_classification_node_external
    ON classification_node(scheme_id, external_id) WHERE external_id IS NOT NULL;
CREATE INDEX ix_classification_node_parent ON classification_node(parent_node_id);

CREATE TABLE material_classification (
    material_classification_id INTEGER PRIMARY KEY,
    material_id INTEGER NOT NULL REFERENCES material(material_id),
    node_id     INTEGER NOT NULL REFERENCES classification_node(node_id),
    is_primary  INTEGER NOT NULL DEFAULT 0 CHECK (is_primary IN (0,1)),
    confidence  REAL NOT NULL DEFAULT 1.0,
    assigned_by TEXT NOT NULL DEFAULT 'manual' CHECK (assigned_by IN ('manual','auto')),
    valid_from  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    valid_to    TEXT
);

CREATE INDEX ix_material_classification_current
    ON material_classification(material_id) WHERE valid_to IS NULL;

-- ============================================================
-- SECTION 10: SOURCE-TO-INTERNAL CLASSIFICATION MAPPING
-- The owner's manual declaration: 'site node X == internal node Y'.
-- ============================================================

CREATE TABLE classification_mapping (
    classification_mapping_id INTEGER PRIMARY KEY,
    source_node_id INTEGER NOT NULL REFERENCES classification_node(node_id),
    target_node_id INTEGER NOT NULL REFERENCES classification_node(node_id),
    confidence     REAL NOT NULL DEFAULT 1.0,
    mapping_method TEXT NOT NULL DEFAULT 'manual' CHECK (mapping_method IN ('manual','rule','ai')),
    review_status  TEXT NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending','approved','ignored')),
    valid_from     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    valid_to       TEXT
);

CREATE UNIQUE INDEX ux_classification_mapping_active
    ON classification_mapping(source_node_id) WHERE valid_to IS NULL AND review_status = 'approved';

-- ============================================================
-- SECTION 11: MATCHING SOURCE ITEMS TO THE UNIFIED MATERIAL
-- The human gate: NO confidence level auto-approves (ENGINEERING.md A5).
-- ============================================================

CREATE TABLE source_product_match (
    source_product_match_id INTEGER PRIMARY KEY,
    source_product_id INTEGER NOT NULL REFERENCES source_product(source_product_id),
    material_id       INTEGER NOT NULL REFERENCES material(material_id),
    confidence        REAL NOT NULL DEFAULT 0,
    match_method      TEXT NOT NULL DEFAULT 'manual',   -- 'gtin' | 'fingerprint' | 'name_fuzzy' | 'brand_category' | 'manual'
    evidence_json     TEXT,
    review_status     TEXT NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending','approved','ignored')),
    valid_from        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    valid_to          TEXT
);

CREATE UNIQUE INDEX ux_source_product_match_active
    ON source_product_match(source_product_id) WHERE valid_to IS NULL AND review_status = 'approved';

CREATE TABLE source_variant_match (
    source_variant_match_id INTEGER PRIMARY KEY,
    source_variant_id INTEGER NOT NULL REFERENCES source_variant(source_variant_id),
    variant_id        INTEGER NOT NULL REFERENCES material_variant(variant_id),
    confidence        REAL NOT NULL DEFAULT 0,
    match_method      TEXT NOT NULL DEFAULT 'manual',
    evidence_json     TEXT,
    review_status     TEXT NOT NULL DEFAULT 'pending' CHECK (review_status IN ('pending','approved','ignored')),
    valid_from        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    valid_to          TEXT
);

CREATE UNIQUE INDEX ux_source_variant_match_active
    ON source_variant_match(source_variant_id) WHERE valid_to IS NULL AND review_status = 'approved';

-- ============================================================
-- SECTION 12: PROVENANCE (إثبات مصدر السعر)
-- Every price points to run_id + snapshot_id -> the exact page/JSON it came from.
-- ============================================================

CREATE TABLE crawl_run (
    run_id              INTEGER PRIMARY KEY,
    source_id           INTEGER NOT NULL REFERENCES source_site(source_id),
    started_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    finished_at         TEXT,
    status              TEXT NOT NULL DEFAULT 'running'
        CHECK (status IN ('running','success','partial','failed')),
    products_discovered INTEGER NOT NULL DEFAULT 0,
    variants_discovered INTEGER NOT NULL DEFAULT 0,
    errors_count        INTEGER NOT NULL DEFAULT 0,
    requests_count      INTEGER NOT NULL DEFAULT 0,    -- F5 politeness accounting
    durations_json      TEXT,                          -- F7 per-phase wall-times
    extractor_version   TEXT
);

CREATE INDEX ix_crawl_run_source_time ON crawl_run(source_id, started_at DESC);

CREATE TABLE raw_snapshot (
    snapshot_id  INTEGER PRIMARY KEY,
    run_id       INTEGER NOT NULL REFERENCES crawl_run(run_id),
    source_url   TEXT NOT NULL,
    captured_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    content_type TEXT,
    content_hash TEXT NOT NULL,              -- F4 short-circuit + dedupe key
    storage_path TEXT,                       -- gzipped file on disk (A8)
    http_status  INTEGER
);

CREATE INDEX ix_raw_snapshot_hash ON raw_snapshot(content_hash);

-- ============================================================
-- SECTION 13: FEED ASSIGNMENTS (design review addition)
-- Owner-declared publish preference per (material [x variant] x region).
-- WRITE permission lives in the manifest scope guard; this is READ preference
-- at publish time. Everything still lands append-only in price_observation.
-- ============================================================

CREATE TABLE feed_assignment (
    feed_assignment_id INTEGER PRIMARY KEY,
    material_id        INTEGER NOT NULL REFERENCES material(material_id),
    variant_id         INTEGER REFERENCES material_variant(variant_id),  -- NULL = all variants
    region             TEXT NOT NULL DEFAULT '*',
    source_id          INTEGER NOT NULL REFERENCES source_site(source_id),
    priority           INTEGER NOT NULL DEFAULT 1,       -- 1 = designated feeder; 2+ = declared fallbacks
    freshness_days     INTEGER NOT NULL,                 -- max age before this feeder counts stale
    review_status      TEXT NOT NULL DEFAULT 'approved'
        CHECK (review_status IN ('approved','pending','retired')),
    valid_from         TEXT NOT NULL DEFAULT (date('now')),
    valid_to           TEXT,                             -- temporal history; never DELETE
    notes              TEXT
);

CREATE UNIQUE INDEX ux_feed_assignment_active
    ON feed_assignment(material_id, COALESCE(variant_id,0), region, priority)
    WHERE valid_to IS NULL;
CREATE INDEX ix_feed_assignment_lookup
    ON feed_assignment(material_id, region) WHERE valid_to IS NULL;

-- ============================================================
-- FLAT VIEW (Phase 0 skeleton)
-- v_material_price_tracking: latest observation per offer, joined flat.
-- The feed_assignment selection layer (freshness/priority/wildcards) is added
-- in Phase 3 per the plan; this skeleton exists so publish plumbing can be
-- built and tested end-to-end before the selection policy lands.
-- ============================================================

CREATE VIEW v_material_price_tracking AS
SELECT
    po.business_date                AS observation_date,
    ss.source_name                  AS source_name,
    m.material_id                   AS material_id,
    COALESCE(m.material_name_en, m.material_name_ar) AS material_name,
    mv.variant_id                   AS variant_id,
    mv.variant_name                 AS variant_description,
    sv.external_sku                 AS external_sku,
    sp.source_product_id            AS source_product_id,
    sv.source_variant_id            AS source_variant_id,
    COALESCE(b.brand_name, sp.brand_raw) AS brand,
    mv.spec_fingerprint             AS specification_summary,
    po.regular_price                AS regular_price,
    po.sale_price                   AS sale_price,
    po.effective_price              AS effective_price,
    po.currency                     AS currency,
    su.unit_code                    AS selling_unit,
    so.basis_quantity               AS basis_quantity,
    po.vat_included                 AS vat_included,
    po.availability                 AS availability,
    po.stock_quantity               AS stock_quantity,
    sp.product_url                  AS product_url,
    po.snapshot_id                  AS snapshot_id
FROM price_observation po
JOIN source_offer so        ON so.offer_id = po.offer_id
JOIN source_variant sv      ON sv.source_variant_id = so.source_variant_id
JOIN source_product sp      ON sp.source_product_id = sv.source_product_id
JOIN source_site ss         ON ss.source_id = sp.source_id
JOIN source_variant_match svm ON svm.source_variant_id = sv.source_variant_id
                             AND svm.review_status = 'approved' AND svm.valid_to IS NULL
JOIN material_variant mv    ON mv.variant_id = svm.variant_id
JOIN material m             ON m.material_id = mv.material_id
LEFT JOIN brand b           ON b.brand_id = m.brand_id
LEFT JOIN selling_unit su   ON su.selling_unit_id = so.selling_unit_id
WHERE po.price_observation_id = (
    SELECT po2.price_observation_id FROM price_observation po2
    WHERE po2.offer_id = po.offer_id
    ORDER BY po2.observed_at DESC LIMIT 1
);

PRAGMA user_version = 1;
