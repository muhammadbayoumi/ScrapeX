-- =====================================================================
-- 0059 — A COLUMN ORDER THAT SAYS WHO ARRANGED IT
--
-- The owner drags a column in Choose Columns. The panel says it saved. The
-- page reloads. The table is byte-for-byte what it was.
--
-- That is not a rendering bug. The grid takes its order from the literal
-- BROWSE_COLUMNS list in reports.py and has never read dataset_field at
-- all — `display_order` occurs zero times in reports.py and zero times in
-- grid.js. Meanwhile the Choose-Columns panel and the Current-View export
-- both order BY display_order. So the same warehouse answers "what order
-- are my columns in" three ways, and they disagree at position 0: on MADAR
-- the grid opens product_name and the panel opens product_name_ar, with
-- price at grid index 18 against panel index 13.
--
-- The fix is for the grid to read the same order. But a stored order can
-- only be trusted if we can tell whether a PERSON put it there, and today
-- nothing records that:
--
--   dataset_field_id | source_key | field_key | original_name |
--   display_name | data_type | is_hidden | display_order | first_seen_at
--
-- Nothing temporal but first_seen_at, and reorder() stamps nothing. That
-- gap is not new — migration 0051 hit the same wall and had to INFER
-- authorship from proxies, writing that nothing owner-authored was lost
-- because every row carried display_name NULL and is_hidden 0.
--
-- SO THIS MIGRATION ADDS PROVENANCE AND NOTHING ELSE. It does not write a
-- single display_order. An order the owner arranged is his, and a
-- migration that "corrected" it would be the very defect being fixed,
-- committed by the fix.
--
-- THE BACKFILL, AND WHY IT IS AN INVERSION RATHER THAN A GUESS. A source
-- whose display_order is exactly its insertion order was never touched by
-- a person — that is what ensure_fields writes and what reset_view
-- restores. Any source whose order DEVIATES from dataset_field_id has been
-- through reorder(), and reorder() is only reachable from the drag handles
-- in Choose Columns. So deviation is the signature of a hand, and it is
-- the only signature available. Measured read-only on the live warehouse
-- 2026-08-03: 11 of 12 sources sit in exact insertion order, 0 rows carry
-- a display_name, 2 rows are hidden, and saved_view is empty — so exactly
-- one source is stamped here, and it is stamped because its owner moved
-- two fields into the details zone.
--
-- The stamp is the migration's own timestamp, not a fabricated past: we
-- know THAT it was arranged, never when. Recording a date we do not have
-- would be inventing source truth about the owner himself.
-- =====================================================================

ALTER TABLE dataset_field ADD COLUMN arranged_at TEXT;

UPDATE dataset_field
   SET arranged_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
 WHERE source_key IN (
       SELECT source_key
         FROM (SELECT source_key,
                      dataset_field_id,
                      display_order,
                      ROW_NUMBER() OVER (PARTITION BY source_key
                                         ORDER BY dataset_field_id) AS by_insertion,
                      ROW_NUMBER() OVER (PARTITION BY source_key
                                         ORDER BY display_order, dataset_field_id) AS by_order
                 FROM dataset_field)
        WHERE by_insertion <> by_order
        GROUP BY source_key);

PRAGMA user_version = 59;
