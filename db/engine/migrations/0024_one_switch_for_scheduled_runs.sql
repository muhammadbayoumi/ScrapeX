-- One switch for a source's scheduled runs: a paused schedule becomes `active = 0`.
--
-- HIS RULING ON #1596, D1, 2026-10-09: option 2. A schedule fired only when THREE things
-- held -- the source's `active`, the schedule's `enabled`, and a frequency other than
-- manual (`scheduler.fire_due`, `due_schedules`) -- and the panel drew the first two as
-- two switches on two pages. Now each Schedules row carries one Active switch, and
-- `source_setting.active` stays the stored truth. So every schedule he paused with
-- `enabled = 0` is folded into `active = 0` for its source, and `enabled` goes back to 1.
--
-- FIRING IS IDENTICAL, row for row. A schedule with `enabled = 0` never fired; with
-- `active = 0` it re-arms without firing (`fire_due`, "if not active"). `active` gates
-- only schedules -- `POST /api/jobs` never reads it -- so a manual run is unchanged too.
--
-- A SCHEDULE WHOSE SOURCE HAS NO `source_site` ROW IS LEFT AS IT IS. `source_setting`
-- hangs off `source_site.source_id`, and a source is registered by its first ingest with
-- its name, address, platform and currency (`ingest.get_source_id`) -- a row inserted here
-- would carry none of them, and nothing fills them later. Such a schedule keeps
-- `enabled = 0` and so keeps not firing; the panel reads it as off, and the first save
-- from its switch registers the source and stores `active` the way the route does.
--
-- `next_run_at` IS NOT TOUCHED: a paused schedule holds NULL there, and `fire_due` skips
-- NULL. Turning the switch on saves the schedule again, which arms its next slot.
--
-- DATA ONLY, no table changes: `schema.sql`, the CHECKs and the drift tests stand as they
-- were. `updated_at` is stamped as `source_settings.save` stamps it.

PRAGMA user_version = 24;

INSERT INTO source_setting (source_id, active)
SELECT ss.source_id, 0
  FROM schedule AS sc
  JOIN source_site AS ss ON ss.source_key = sc.source_key
 WHERE sc.enabled = 0
ON CONFLICT (source_id) DO UPDATE
   SET active = 0,
       updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now');

UPDATE schedule
   SET enabled = 1
 WHERE enabled = 0
   AND source_key IN (SELECT source_key FROM source_site);
