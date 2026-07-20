-- =====================================================================
-- General 0003: an index the paginated field read can actually use.
--
-- list_fields pages with:
--     WHERE dataset_definition_id = ? AND valid_to IS NULL
--       AND field_definition_id > ?
--     ORDER BY field_definition_id
--
-- The existing ix_field_definition_dataset leads with
-- (dataset_definition_id, display_order, ...). display_order is neither
-- filtered nor ordered by here, so SQLite could use only the first column
-- and then had to scan and sort every field of the dataset for every page
-- — the cost growing with the dataset while the page size stayed the same.
--
-- The old index is kept: it is the right one for reading a dataset's
-- fields IN DISPLAY ORDER, which is what the workspace table does.
-- =====================================================================

CREATE INDEX ix_field_definition_paging
    ON field_definition (dataset_definition_id, field_definition_id)
    WHERE valid_to IS NULL;

PRAGMA user_version = 3;
