-- A record card finds its change events by index, not by reading all of them.
--
-- MEASURED ON A COPY OF HIS WAREHOUSE, 2026-10-03 (#1206). `changes.changes_for_offer`
-- asks for one offer's events:
--
--     WHERE c.offer_id = ?
--        OR (c.offer_id IS NULL AND c.source_variant_id = (SELECT ... WHERE offer_id = ?))
--
-- and no index covers either column: the three on `change_event` are by product, by
-- run and by time (schema.sql, "indexes"). So every card read all 173,742 events
-- (`EXPLAIN QUERY PLAN`: `SCAN c`). That is about 43 ms per card on the engine's own
-- `/api/offer`, and it was 90-95% of building the light file (#1199): 557-613 s for
-- the whole warehouse.
--
-- With these two the plan is `MULTI-INDEX OR`. Measured on the same copy:
-- - the whole light-file build took 47-51 s, and all 54 files were byte-identical;
-- - all 19,218 cards took 2.1 s;
-- - building the two indexes took 0.12-0.17 s.
--
-- TWO SINGLE-COLUMN INDEXES, NOT ONE. The query is an OR across two columns, and SQLite
-- answers an OR from an index only when each side has its own (the MULTI-INDEX OR
-- strategy). One composite index would serve the first side and scan for the second.
--
-- NOT IN `schema.sql`, like every migration after the baseline: a fresh install runs
-- the baseline and then every migration, so declaring them in both would make this
-- CREATE fail on a new warehouse. His approval, 2026-10-03: «ضيفهم فى PR لوحده».

CREATE INDEX ix_change_event_offer ON change_event(offer_id);

CREATE INDEX ix_change_event_variant ON change_event(source_variant_id);
