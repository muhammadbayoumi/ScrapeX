-- =====================================================================
-- 0012 — ENRICHMENT RUNS OBSERVE BEFORE THEY REPLACE
--
-- A result is current only while a completed provider observation supports
-- it. A run also owns an immutable input set, so commits cannot mix crawls.
-- Owner review remains durable evidence rather than an in-place edit.
-- =====================================================================

ALTER TABLE organization_enrichment_definition
    ADD COLUMN configuration_version INTEGER NOT NULL DEFAULT 1
        CHECK (configuration_version >= 1);

ALTER TABLE organization_enrichment_job
    ADD COLUMN definition_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(definition_json) AND json_type(definition_json) = 'object');
ALTER TABLE organization_enrichment_job
    ADD COLUMN provider_versions_json TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(provider_versions_json)
               AND json_type(provider_versions_json) = 'object');
ALTER TABLE organization_enrichment_job
    ADD COLUMN estimated_requests INTEGER NOT NULL DEFAULT 0
        CHECK (estimated_requests >= 0);

ALTER TABLE organization_fact ADD COLUMN observation_id INTEGER;
ALTER TABLE organization_fact ADD COLUMN entity_match_confidence REAL
    CHECK (entity_match_confidence IS NULL OR
           entity_match_confidence BETWEEN 0.0 AND 1.0);
ALTER TABLE organization_fact ADD COLUMN extraction_confidence REAL
    CHECK (extraction_confidence IS NULL OR
           extraction_confidence BETWEEN 0.0 AND 1.0);
ALTER TABLE organization_fact ADD COLUMN source_authority REAL
    CHECK (source_authority IS NULL OR source_authority BETWEEN 0.0 AND 1.0);
ALTER TABLE organization_fact ADD COLUMN observed_at TEXT;

ALTER TABLE organization_entity ADD COLUMN canonical_organization_id TEXT
    REFERENCES organization_entity(organization_id);

CREATE INDEX ix_organization_entity_canonical
    ON organization_entity(canonical_organization_id);

CREATE TRIGGER trg_organization_entity_canonical_cycle_insert
BEFORE INSERT ON organization_entity
FOR EACH ROW
WHEN NEW.canonical_organization_id IS NOT NULL AND (
    NEW.canonical_organization_id = NEW.organization_id OR EXISTS (
        WITH RECURSIVE ancestors(organization_id) AS (
            SELECT NEW.canonical_organization_id
            UNION
            SELECT entity.canonical_organization_id
            FROM organization_entity AS entity
            JOIN ancestors ON entity.organization_id=ancestors.organization_id
            WHERE entity.canonical_organization_id IS NOT NULL
        )
        SELECT 1 FROM ancestors WHERE organization_id=NEW.organization_id
    )
)
BEGIN
    SELECT RAISE(ABORT, 'organization canonical identity cycle');
END;

CREATE TRIGGER trg_organization_entity_canonical_cycle_update
BEFORE UPDATE OF canonical_organization_id ON organization_entity
FOR EACH ROW
WHEN NEW.canonical_organization_id IS NOT NULL AND (
    NEW.canonical_organization_id = NEW.organization_id OR EXISTS (
        WITH RECURSIVE ancestors(organization_id) AS (
            SELECT NEW.canonical_organization_id
            UNION
            SELECT entity.canonical_organization_id
            FROM organization_entity AS entity
            JOIN ancestors ON entity.organization_id=ancestors.organization_id
            WHERE entity.canonical_organization_id IS NOT NULL
        )
        SELECT 1 FROM ancestors WHERE organization_id=NEW.organization_id
    )
)
BEGIN
    SELECT RAISE(ABORT, 'organization canonical identity cycle');
END;

CREATE TABLE organization_identity_alias (
    identity_alias_id       INTEGER PRIMARY KEY,
    organization_id        TEXT NOT NULL
        REFERENCES organization_entity(organization_id),
    alias_type              TEXT NOT NULL
        CHECK (alias_type IN ('source_external_id','domain','phone','registry_id')),
    normalized_value        TEXT NOT NULL,
    value_hash              TEXT NOT NULL,
    source_provider         TEXT NOT NULL,
    confidence              REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    review_status           TEXT NOT NULL DEFAULT 'candidate'
        CHECK (review_status IN ('candidate','confirmed','rejected')),
    first_seen_at           TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    last_seen_at            TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE (organization_id, alias_type, value_hash, source_provider)
);

CREATE INDEX ix_organization_identity_alias_candidates
    ON organization_identity_alias(alias_type, value_hash, review_status);

CREATE TABLE organization_merge_event (
    organization_merge_id  INTEGER PRIMARY KEY,
    source_organization_id TEXT NOT NULL
        REFERENCES organization_entity(organization_id),
    target_organization_id TEXT NOT NULL
        REFERENCES organization_entity(organization_id),
    reviewer               TEXT NOT NULL DEFAULT 'owner',
    reason                 TEXT NOT NULL,
    merged_at              TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    reversed_at            TEXT,
    reversed_by            TEXT,
    reverse_reason         TEXT,
    CHECK (source_organization_id <> target_organization_id)
);

CREATE TABLE organization_merge_member (
    organization_merge_id  INTEGER NOT NULL
        REFERENCES organization_merge_event(organization_merge_id)
        ON DELETE CASCADE,
    organization_id        TEXT NOT NULL
        REFERENCES organization_entity(organization_id),
    previous_canonical_id  TEXT
        REFERENCES organization_entity(organization_id),
    PRIMARY KEY (organization_merge_id, organization_id)
);

CREATE TABLE organization_enrichment_definition_history (
    definition_history_id     INTEGER PRIMARY KEY,
    enrichment_definition_id  INTEGER NOT NULL
        REFERENCES organization_enrichment_definition(enrichment_definition_id)
        ON DELETE CASCADE,
    configuration_version     INTEGER NOT NULL CHECK (configuration_version >= 1),
    definition_json           TEXT NOT NULL
        CHECK (json_valid(definition_json) AND json_type(definition_json) = 'object'),
    replaced_at               TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE (enrichment_definition_id, configuration_version)
);

CREATE TABLE organization_enrichment_run_item (
    job_id                  INTEGER NOT NULL
        REFERENCES organization_enrichment_job(job_id) ON DELETE CASCADE,
    generic_record_id       INTEGER NOT NULL,
    source_snapshot_id      INTEGER NOT NULL,
    source_data_json        TEXT CHECK (
        source_data_json IS NULL OR json_valid(source_data_json)),
    source_content_hash     TEXT NOT NULL,
    detail_data_json        TEXT CHECK (
        detail_data_json IS NULL OR json_valid(detail_data_json)),
    detail_content_hash     TEXT,
    source_url              TEXT NOT NULL DEFAULT '',
    source_external_id      TEXT NOT NULL,
    item_status             TEXT NOT NULL DEFAULT 'pending'
        CHECK (item_status IN ('pending','running','completed','failed')),
    attempts                INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error              TEXT,
    completed_at            TEXT,
    PRIMARY KEY (job_id, generic_record_id),
    UNIQUE (job_id, source_external_id)
);

CREATE INDEX ix_organization_enrichment_run_item_work
    ON organization_enrichment_run_item(job_id, item_status, generic_record_id);

CREATE TABLE organization_provider_observation (
    observation_id          INTEGER PRIMARY KEY,
    job_id                  INTEGER NOT NULL
        REFERENCES organization_enrichment_job(job_id) ON DELETE CASCADE,
    organization_id         TEXT NOT NULL
        REFERENCES organization_entity(organization_id),
    provider                TEXT NOT NULL,
    provider_version        TEXT NOT NULL,
    input_hash              TEXT NOT NULL,
    observation_status      TEXT NOT NULL
        CHECK (observation_status IN (
            'completed','not_found','cached','skipped','failed','system_error')),
    fields_seen_json        TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(fields_seen_json)
               AND json_type(fields_seen_json) = 'array'),
    request_count           INTEGER NOT NULL DEFAULT 0 CHECK (request_count >= 0),
    latency_ms              INTEGER NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
    error                   TEXT,
    observed_at             TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE (job_id, organization_id, provider)
);

CREATE INDEX ix_organization_provider_observation_fresh
    ON organization_provider_observation(
        organization_id, provider, provider_version, input_hash,
        observation_status, observed_at);

-- SQLite cannot retrofit a foreign-key clause onto organization_fact. These
-- triggers enforce the nullable observation reference and clear it when a job
-- is removed while preserving the historical fact itself.
CREATE TRIGGER trg_organization_fact_observation_insert
BEFORE INSERT ON organization_fact
FOR EACH ROW
WHEN NEW.observation_id IS NOT NULL
 AND NOT EXISTS (SELECT 1 FROM organization_provider_observation
                 WHERE observation_id = NEW.observation_id)
BEGIN
    SELECT RAISE(ABORT, 'organization fact references an unknown observation');
END;

CREATE TRIGGER trg_organization_fact_observation_update
BEFORE UPDATE OF observation_id ON organization_fact
FOR EACH ROW
WHEN NEW.observation_id IS NOT NULL
 AND NOT EXISTS (SELECT 1 FROM organization_provider_observation
                 WHERE observation_id = NEW.observation_id)
BEGIN
    SELECT RAISE(ABORT, 'organization fact references an unknown observation');
END;

CREATE TRIGGER trg_organization_observation_delete
BEFORE DELETE ON organization_provider_observation
FOR EACH ROW
BEGIN
    UPDATE organization_fact SET observation_id = NULL
    WHERE observation_id = OLD.observation_id;
END;

CREATE TABLE organization_review_decision (
    review_decision_id      INTEGER PRIMARY KEY,
    organization_fact_id   INTEGER NOT NULL
        REFERENCES organization_fact(organization_fact_id),
    action                  TEXT NOT NULL
        CHECK (action IN ('approve','reject','override')),
    override_value_json     TEXT CHECK (
        override_value_json IS NULL OR json_valid(override_value_json)),
    reviewer                TEXT NOT NULL DEFAULT 'owner',
    reason                  TEXT NOT NULL DEFAULT '',
    decided_at              TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE INDEX ix_organization_review_decision_fact
    ON organization_review_decision(organization_fact_id, review_decision_id DESC);
CREATE INDEX ix_organization_enrichment_job_definition
    ON organization_enrichment_job(enrichment_definition_id, job_id DESC);

-- Versioned configuration uses UPDATE, so the insert invariants must cover it.
CREATE TRIGGER trg_enrichment_definition_same_site_update
BEFORE UPDATE OF site_profile_id, source_dataset_id, detail_dataset_id,
                 output_dataset_id ON organization_enrichment_definition
FOR EACH ROW
WHEN (SELECT site_profile_id FROM dataset_definition
      WHERE dataset_definition_id = NEW.source_dataset_id LIMIT 1)
        <> NEW.site_profile_id
  OR (NEW.detail_dataset_id IS NOT NULL AND
      (SELECT site_profile_id FROM dataset_definition
       WHERE dataset_definition_id = NEW.detail_dataset_id LIMIT 1)
        <> NEW.site_profile_id)
  OR (SELECT site_profile_id FROM dataset_definition
      WHERE dataset_definition_id = NEW.output_dataset_id LIMIT 1)
        <> NEW.site_profile_id
BEGIN
    SELECT RAISE(ABORT, 'enrichment datasets must belong to the same site profile');
END;

CREATE TRIGGER trg_enrichment_definition_datasets_differ_update
BEFORE UPDATE OF source_dataset_id, detail_dataset_id, output_dataset_id
ON organization_enrichment_definition
FOR EACH ROW
WHEN NEW.source_dataset_id = NEW.output_dataset_id
  OR NEW.detail_dataset_id = NEW.source_dataset_id
  OR NEW.detail_dataset_id = NEW.output_dataset_id
BEGIN
    SELECT RAISE(ABORT, 'the enrichment output must be a new dataset');
END;
