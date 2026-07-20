-- =====================================================================
-- migration 0017: the same field-paging index for a unified warehouse.
--
-- The split gives General its own chain, but the unified database is still
-- the compatibility path for rollback and for explicit --db sessions. An
-- index that exists in one and not the other would make the same query
-- fast in a split install and slow in a unified one, which is exactly the
-- kind of divergence that gets diagnosed as "the split made it faster".
--
-- See db/general/migrations/0003 for why the original index could not
-- serve this read.
-- =====================================================================

CREATE INDEX ix_field_definition_paging
    ON field_definition (dataset_definition_id, field_definition_id)
    WHERE valid_to IS NULL;

PRAGMA user_version = 17;
