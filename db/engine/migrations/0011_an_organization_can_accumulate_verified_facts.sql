-- =====================================================================
-- 0011 — AN ORGANIZATION CAN ACCUMULATE VERIFIED FACTS
--
-- A directory crawl and an enrichment run answer different questions. The
-- crawl records what its source publishes; enrichment links that source row
-- to evidence found elsewhere and must never overwrite the source row. The
-- visible result is another generic dataset, while these tables retain the
-- definition, stable organization identity, field-level evidence and job
-- lineage needed to rebuild that result without guessing.
-- =====================================================================

ALTER TABLE crawl_job ADD COLUMN job_kind TEXT NOT NULL DEFAULT 'crawl'
    CHECK (job_kind IN ('crawl', 'organization_enrichment'));

CREATE TABLE organization_enrichment_definition (
    enrichment_definition_id INTEGER PRIMARY KEY,
    site_profile_id           INTEGER NOT NULL
        REFERENCES site_profile(site_profile_id),
    source_dataset_id         INTEGER NOT NULL
        REFERENCES dataset_definition(dataset_definition_id),
    detail_dataset_id         INTEGER
        REFERENCES dataset_definition(dataset_definition_id),
    output_dataset_id         INTEGER NOT NULL UNIQUE
        REFERENCES dataset_definition(dataset_definition_id),
    entity_key_field          TEXT NOT NULL,
    detail_key_field          TEXT,
    field_mapping_json        TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(field_mapping_json)
               AND json_type(field_mapping_json) = 'object'),
    providers_json            TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(providers_json)
               AND json_type(providers_json) = 'array'),
    status                    TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'retired')),
    created_at                TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at                TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    last_run_at               TEXT,
    UNIQUE (source_dataset_id)
);

CREATE TABLE organization_entity (
    organization_id TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    updated_at      TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE organization_source_record (
    enrichment_definition_id INTEGER NOT NULL
        REFERENCES organization_enrichment_definition(enrichment_definition_id)
        ON DELETE CASCADE,
    generic_record_id         INTEGER NOT NULL
        REFERENCES generic_record(generic_record_id) ON DELETE CASCADE,
    organization_id           TEXT NOT NULL
        REFERENCES organization_entity(organization_id),
    source_external_id        TEXT NOT NULL,
    first_seen_at             TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    last_seen_at              TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    PRIMARY KEY (enrichment_definition_id, generic_record_id),
    UNIQUE (enrichment_definition_id, source_external_id)
);

CREATE INDEX ix_organization_source_record_org
    ON organization_source_record(enrichment_definition_id, organization_id);

CREATE TABLE organization_fact (
    organization_fact_id INTEGER PRIMARY KEY,
    organization_id      TEXT NOT NULL
        REFERENCES organization_entity(organization_id),
    field_key             TEXT NOT NULL,
    value_json            TEXT NOT NULL CHECK (json_valid(value_json)),
    value_hash            TEXT NOT NULL,
    provider              TEXT NOT NULL,
    source_url            TEXT,
    confidence            REAL NOT NULL DEFAULT 0.0
        CHECK (confidence >= 0.0 AND confidence <= 1.0),
    verification_status   TEXT NOT NULL
        CHECK (verification_status IN (
            'verified', 'probable', 'candidate', 'conflict',
            'manual_review', 'not_found')),
    evidence_json         TEXT NOT NULL DEFAULT '{}'
        CHECK (json_valid(evidence_json)
               AND json_type(evidence_json) = 'object'),
    first_seen_at         TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    last_seen_at          TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    valid_to              TEXT
);

CREATE UNIQUE INDEX ux_organization_fact_current
    ON organization_fact(organization_id, field_key, provider)
    WHERE valid_to IS NULL;

CREATE INDEX ix_organization_fact_review
    ON organization_fact(verification_status, organization_id)
    WHERE valid_to IS NULL;

CREATE TABLE organization_enrichment_job (
    job_id                       INTEGER PRIMARY KEY
        REFERENCES crawl_job(job_id) ON DELETE CASCADE,
    enrichment_definition_id     INTEGER NOT NULL
        REFERENCES organization_enrichment_definition(enrichment_definition_id),
    providers_json               TEXT NOT NULL DEFAULT '[]'
        CHECK (json_valid(providers_json)
               AND json_type(providers_json) = 'array'),
    created_at                   TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TRIGGER trg_enrichment_definition_same_site_insert
BEFORE INSERT ON organization_enrichment_definition
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

CREATE TRIGGER trg_enrichment_definition_datasets_differ_insert
BEFORE INSERT ON organization_enrichment_definition
FOR EACH ROW
WHEN NEW.source_dataset_id = NEW.output_dataset_id
  OR NEW.detail_dataset_id = NEW.source_dataset_id
  OR NEW.detail_dataset_id = NEW.output_dataset_id
BEGIN
    SELECT RAISE(ABORT, 'the enrichment output must be a new dataset');
END;
