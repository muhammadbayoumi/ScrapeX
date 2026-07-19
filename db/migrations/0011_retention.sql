-- =====================================================================
-- migration 0011: retention policy, pinning and run lineage (spec 18).
--
-- The product must offer data retention, but price_observation is
-- append-only and STAYS append-only: schema.sql:217-227 defines
-- trg_price_obs_no_update / trg_price_obs_no_delete and nothing in this
-- migration weakens them. Retention is therefore expressed as policy,
-- protection and lineage — never as a delete path.
--
-- Space is reclaimed by building a NEW database containing the retained
-- rows and sealing the old file beside it. The old file is never removed
-- by ScrapeX, so a retention run can always be undone by pointing back
-- at the sealed archive.
-- =====================================================================

-- One policy per dataset, plus the global default row (source_key = '*').
CREATE TABLE retention_policy (
    retention_policy_id INTEGER PRIMARY KEY,
    source_key          TEXT NOT NULL UNIQUE,
    detail_days         INTEGER NOT NULL CHECK (detail_days >= 7),
    older_than_action   TEXT NOT NULL CHECK (older_than_action IN (
                            'keep_all',        -- carry every row forward (a no-op)
                            'daily_summary',   -- one row per offer per day
                            'weekly_summary',  -- one row per offer per ISO week
                            'archive_only')),  -- carry nothing but the protected set
    excluded            INTEGER NOT NULL DEFAULT 0 CHECK (excluded IN (0,1)),
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- The shipped default changes nothing until the owner decides otherwise.
INSERT INTO retention_policy (source_key, detail_days, older_than_action)
VALUES ('*', 3650, 'keep_all');

-- Observations the owner marked as important. Added and removed by the owner;
-- removing a pin removes a MARK, never an observation.
--
-- A pin addresses the natural key (offer, business date, record hash) rather
-- than a rowid, because a compacted successor renumbers its primary keys.
CREATE TABLE retention_pin (
    retention_pin_id INTEGER PRIMARY KEY,
    offer_id         INTEGER NOT NULL REFERENCES source_offer(offer_id),
    business_date    TEXT NOT NULL,
    record_hash      TEXT NOT NULL,
    note             TEXT NOT NULL DEFAULT '',
    pinned_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE (offer_id, business_date, record_hash)
);

CREATE INDEX ix_retention_pin_offer ON retention_pin (offer_id);

-- Every preview and every compaction, so the lineage of a warehouse is legible
-- from inside it. Written to the SUCCESSOR after promotion, never left behind
-- in a 'running' state in the file that gets sealed.
CREATE TABLE retention_run (
    retention_run_id    INTEGER PRIMARY KEY,
    mode                TEXT NOT NULL CHECK (mode IN ('preview','compact','prune')),
    finished_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    status              TEXT NOT NULL CHECK (status IN ('succeeded','failed','aborted')),
    observations_before INTEGER NOT NULL DEFAULT 0,
    observations_after  INTEGER NOT NULL DEFAULT 0,
    protected_count     INTEGER NOT NULL DEFAULT 0,
    bytes_before        INTEGER NOT NULL DEFAULT 0,
    bytes_after         INTEGER NOT NULL DEFAULT 0,
    sealed_path         TEXT NOT NULL DEFAULT '',
    detail              TEXT NOT NULL DEFAULT ''
);

-- The always-preserve set, defined ONCE in SQL so no caller can forget a term:
-- the first and latest observation of every offer, its cheapest and dearest,
-- and anything the owner pinned. Selection uses this view; verification
-- deliberately derives the same set a second way and compares.
CREATE VIEW v_retention_protected AS
    SELECT po.offer_id, po.business_date, po.record_hash, 'first' AS reason
      FROM price_observation po
      JOIN (SELECT offer_id, MIN(observed_at) AS edge FROM price_observation
             GROUP BY offer_id) e
        ON e.offer_id = po.offer_id AND e.edge = po.observed_at
UNION
    SELECT po.offer_id, po.business_date, po.record_hash, 'latest'
      FROM price_observation po
      JOIN (SELECT offer_id, MAX(observed_at) AS edge FROM price_observation
             GROUP BY offer_id) e
        ON e.offer_id = po.offer_id AND e.edge = po.observed_at
UNION
    SELECT po.offer_id, po.business_date, po.record_hash, 'minimum'
      FROM price_observation po
      JOIN (SELECT offer_id, MIN(effective_price) AS edge FROM price_observation
             WHERE effective_price IS NOT NULL GROUP BY offer_id) e
        ON e.offer_id = po.offer_id AND e.edge = po.effective_price
UNION
    SELECT po.offer_id, po.business_date, po.record_hash, 'maximum'
      FROM price_observation po
      JOIN (SELECT offer_id, MAX(effective_price) AS edge FROM price_observation
             WHERE effective_price IS NOT NULL GROUP BY offer_id) e
        ON e.offer_id = po.offer_id AND e.edge = po.effective_price
UNION
    SELECT p.offer_id, p.business_date, p.record_hash, 'pinned'
      FROM retention_pin p;

PRAGMA user_version = 11;
