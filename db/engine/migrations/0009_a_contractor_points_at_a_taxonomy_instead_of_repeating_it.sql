-- =====================================================================
-- 0009 — A CONTRACTOR POINTS AT A TAXONOMY INSTEAD OF REPEATING IT
--
-- `R-36`, his ruling of 2026-08-21: `R-19`'s five multi-valued groups are a
-- TAXONOMY plus a link table — shape D — and not five child datasets inside
-- `generic_record`, which was shape F and what the study recommended.
--
-- HE OVERRULED THE RECOMMENDATION AND WAS RIGHT. F's headline argument was
-- that it reuses machinery this warehouse already contains. Measured the
-- same day: `classification_node`, `classification_scheme`,
-- `dataset_relationship` and `relationship_field_pair` hold **zero rows
-- between them**. Existing machinery that has never carried a row is not an
-- asset — one session found `is_enabled` with no callers, `record_absences`
-- with no callers, and a slice scope that was "built, tested, never used"
-- and turned out to be WRONG.
--
-- AND F PAID A WHOLE RECORD FOR A TWO-INTEGER JOIN ROW. Measured on the live
-- warehouse, each `generic_record` row carries `data_json` averaging 1,049
-- bytes, a 64-character `record_key`, a 64-character `content_hash`, two
-- timestamps, a status and four foreign keys. A membership fact — this
-- contractor holds this node — is two integers. At the study's ~500K rows
-- that is the measured 4.7x, and it is conservative.
--
-- WHY THE TAXONOMY HALF NEEDS NO TABLE. `classification_node` is already a
-- generic self-referencing tree with `parent_node_id`, `node_name`,
-- `node_name_ar` and `level`, and `ux_classification_node_name` makes
-- `(scheme_id, ifnull(parent_node_id,0), node_name_ar)` its identity. That
-- is exactly the shape the hierarchical groups need, which is the finding
-- that produced shapes D and F in the first place. Only the LINK is new.
--
-- WHAT THIS CARRIES OVER FROM F, and it is the one advantage F really had:
-- `source_snapshot_id NOT NULL`, so provenance is enforced by the schema
-- rather than remembered. One column, one constraint.
--
-- AND WHY THE PRIMARY KEY INCLUDES `group_key`. The licensed-activities
-- values look like the same two-level activity paths the interests tree
-- publishes — measured, both are `parent - child` strings from the same
-- vocabulary — so ONE node can legitimately be held by a contractor as an
-- interest AND as a licensed activity. Keying on `(record, node)` alone
-- would silently merge those two facts into one.
-- =====================================================================

CREATE TABLE IF NOT EXISTS generic_record_node (
    generic_record_id  INTEGER NOT NULL
        REFERENCES generic_record(generic_record_id) ON DELETE CASCADE,
    node_id            INTEGER NOT NULL
        REFERENCES classification_node(node_id),

    -- `R-39`: the DECLARED name of the group this membership belongs to, from
    -- `MULTI_VALUED_GROUPS`. Never the table's position and never its heading —
    -- the detector returns `Table 1`…`Table 5`, three of the five tables share
    -- one heading, and two share a column signature while both being empty.
    group_key          TEXT NOT NULL,

    -- ENFORCED, NOT REMEMBERED. This is F's one real advantage carried across:
    -- every membership names the stored page it was read from, so "why does this
    -- contractor hold this node" is answerable from the warehouse and not from a
    -- log. NOT NULL is the whole point of the column.
    source_snapshot_id INTEGER NOT NULL
        REFERENCES generic_page_snapshot(page_snapshot_id),

    first_seen_at      TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    last_seen_at       TEXT NOT NULL
        DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),

    -- HOW MANY TIMES THIS MEMBERSHIP HAS BEEN READ, and it exists because the
    -- timestamps cannot answer "was this new" — both come from
    -- `strftime(...,'now')` at SECOND resolution, so a first write and its
    -- confirmation in the same second produce `first_seen_at = last_seen_at` and
    -- the caller cannot tell them apart. Measured: a second identical pass over
    -- one profile reported all 25 memberships as new.
    --
    -- `dataset_sighting` already carries a `seen_count` for the same reason, so
    -- this is the schema's existing answer rather than a new idea. The upsert
    -- increments it and returns it, so `= 1` means "written just now" with no
    -- extra read and no dependence on a clock.
    seen_count         INTEGER NOT NULL DEFAULT 1 CHECK (seen_count >= 1),

    -- IDEMPOTENT BY CONSTRUCTION, which is `R-36`'s fourth reason for choosing
    -- D. Shape F would have written these through `approve_candidate` — the
    -- function whose idempotency key `R-38` had to repair. Here a re-parse that
    -- finds the same membership hits this key and updates `last_seen_at`; it
    -- cannot write a duplicate, and no later fix is needed to make that true.
    PRIMARY KEY (generic_record_id, node_id, group_key)
) WITHOUT ROWID;

-- "Everything in this group for this contractor" is the read the panel and the
-- export will both make, and the primary key already serves it left-to-right.
-- This is the OTHER direction: "every contractor holding this node", which is
-- the query `R-19` was ruled on — «كل المقاولين فى نشاط معيّن».
CREATE INDEX IF NOT EXISTS ix_record_node_by_node
    ON generic_record_node(node_id, group_key);

-- A DELETED CONTRACTOR TAKES ITS MEMBERSHIPS WITH IT, which is why the foreign
-- key above cascades. `OP-25` was settled on 2026-08-21 by wiping
-- `generic_record` and re-approving from disk — 1,172 rows became 13,892 with
-- zero network — so deletion is a route this warehouse actually takes, and
-- links that survived it would be orphans pointing at nothing.
