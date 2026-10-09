-- His choices about one source live in the warehouse, for every kind of source.
--
-- HIS RULING ON #1584, 2026-10-08: option C, and `active` moves with the rules. What a
-- source is crawled AS -- active, robots choice, the custom robots rule, user agent and
-- pace -- is his choice about his installation, and it had two homes and one of them
-- loses it:
--
--   * a PRICE source kept it in `sources.yaml`, which ships INSIDE the PyInstaller
--     `--onefile` bundle (`packaging/build_engine.py`, `config.MANIFEST_FILE`). That
--     folder is deleted when the engine exits, so on his packaged engine every panel
--     edit to these five fields is gone at the next restart (#1583);
--   * a DIRECTORY source (muqawil_org, the Oman register) is in `source_site` and not
--     in `sources.yaml`, so it had no home for them at all, and `/api/sources/{key}/robots`
--     and `/edit` answer 404 for it.
--
-- His GENERAL rules already live here (`scrapex_meta`, `scrapex/settings.py`), so the
-- per-source layer now sits beside them, in the one store every kind of source shares.
-- What a site IS -- its extract specs, family, partition -- stays in `sources.yaml` and
-- `directories.py`, because that changes with a release and this changes from the panel.
--
-- EVERY RULE COLUMN IS NULLABLE, AND NULL MEANS "HE HAS NOT CHOSEN; INHERIT". The order a
-- source's answer is read in is `scrapex/source_settings.py` `effective`: his choice
-- here, else what the source shipped with in `sources.yaml`, else no per-source opinion
-- at all -- which hands the question to his general rules exactly as it does today. A NOT
-- NULL column could not say "inherit", and a default would be a choice he never made.
--
-- `robots_choice = 'default'` IS NOT NULL'S TWIN. 'default' is a choice he made: follow
-- the tool-wide setting even though the source shipped `obey`. NULL is not having chosen.
--
-- ITS OWN TABLE, NOT MORE COLUMNS ON `source_site`. The registry is the list of sources;
-- this is what he decided about each. Keyed on `source_id` and not `source_key`, so
-- `sources_admin.rename_source` -- which moves every table that names a source by its key
-- -- carries these rows without having to learn they exist.
--
-- THE VOCABULARY IS `robots.RobotsChoice`'S, ALL OF IT AND NOTHING ELSE. The study on
-- #1584 listed an `ignore` choice; the code has three (`default`, `obey`, `custom`), and a
-- fourth stored here would be a value `RobotsChoice(...)` raises on the moment a crawl
-- reads it. `tests/test_source_settings.py` holds this CHECK to the enum, so adding a
-- choice is a migration and an enum member in one change.
--
-- THE BOUNDS ARE THE ONES ALREADY IN FORCE. `crawl_pace_s > 0` is `SourceEntry`'s
-- `Field(gt=0)` (`config.py`). A custom crawl delay may be 0 -- "do not wait for this
-- site" -- because `robots.decide` applies a custom delay AS SET (#1413). `typeof` is in
-- the REAL checks because a comparison does not refuse text in SQLite: `'abc' > 0` is
-- true, so a CHECK of the bound alone would store a word as a pace. `< 9e999` is "finite":
-- SQLite reads 9e999 as infinity, and an infinite pace is a crawl that never makes its
-- next request. `source_settings._seconds` refuses the same values, and
-- `config.SourceEntry.crawl_pace_s` does too (`allow_inf_nan=False`).
--
-- THE CUSTOM RULE EXISTS EXACTLY WHEN THE CHOICE IS `custom`, both ways round. Custom
-- with no rule is what `robots.decide` refuses at crawl time, so it is refused here at
-- write time instead. A rule under any other choice is the one `/api/sources/{key}/edit`
-- already clears (`webui/app.py`, "ENFORCED HERE, not trusted from the form"): left
-- behind, it silently governs the site again the day somebody switches back to custom.
-- `IS` and `IS NOT` rather than `=`, because `NULL = 'custom'` is NULL and a CHECK passes
-- on NULL.
--
-- CREATE TABLE AND NOT A REBUILD: nothing existing changes, so no row can fail this. NOT
-- IN `schema.sql`, like every migration after the baseline: a fresh install runs the
-- baseline and then every migration, so declaring it in both would make this CREATE fail
-- on a new warehouse (`tests/test_migration_drift.py`).

PRAGMA user_version = 22;

CREATE TABLE source_setting (
    source_id               INTEGER PRIMARY KEY REFERENCES source_site(source_id),
    -- Is this source crawled by the schedule. 1 or 0; NULL inherits.
    active                  INTEGER CHECK (active IN (0, 1)),
    -- `robots.RobotsChoice`: default | obey | custom. NULL inherits.
    robots_choice           TEXT CHECK (robots_choice IN ('default', 'obey', 'custom')),
    -- The custom rule's two knobs (`robots.RobotsCustom`). Present only under custom.
    robots_enforce_disallow INTEGER CHECK (robots_enforce_disallow IN (0, 1)),
    -- NULL under custom means "the site's own Crawl-delay".
    robots_crawl_delay_s    REAL CHECK (robots_crawl_delay_s IS NULL OR (
                                typeof(robots_crawl_delay_s) = 'real'
                                AND robots_crawl_delay_s >= 0
                                AND robots_crawl_delay_s < 9e999)),
    -- An empty agent would read as "unset" to `resolve_user_agent`'s `or` chain while
    -- this row claimed a choice; clearing is NULL, so empty is refused. Printable ASCII
    -- only (0x20-0x7E), because a header value is: httpx refuses a request whose agent
    -- holds anything else, so 'متصفح/1' stored here would fail the source's next crawl.
    -- `GLOB '*[^ -~]*'` finds any character outside space..tilde; with every other
    -- whitespace refused by it, `trim` -- which strips spaces only -- is enough for blank.
    user_agent              TEXT CHECK (user_agent IS NULL OR (
                                typeof(user_agent) = 'text'
                                AND user_agent NOT GLOB '*[^ -~]*'
                                AND length(trim(user_agent)) > 0)),
    -- Seconds between requests for this source alone. It can only slow a crawl:
    -- `connectors.base.resolve_fetcher` takes the slowest of every opinion.
    crawl_pace_s            REAL CHECK (crawl_pace_s IS NULL OR (
                                typeof(crawl_pace_s) = 'real' AND crawl_pace_s > 0
                                AND crawl_pace_s < 9e999)),
    updated_at              TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    CHECK ((robots_choice IS 'custom' AND robots_enforce_disallow IS NOT NULL)
           OR (robots_choice IS NOT 'custom'
               AND robots_enforce_disallow IS NULL
               AND robots_crawl_delay_s IS NULL))
);
