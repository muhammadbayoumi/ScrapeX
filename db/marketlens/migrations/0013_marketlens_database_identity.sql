-- MarketLens migration 0013: identify the independent price database stream.
-- Versions 0001-0012 reuse the immutable price-warehouse history. The legacy
-- stream's unrelated 0013 generic catalogue migration is deliberately excluded.

PRAGMA application_id = 1398295884;

CREATE TABLE database_migration (
    migration_number INTEGER PRIMARY KEY,
    migration_name   TEXT NOT NULL,
    sha256            TEXT NOT NULL,
    applied_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

INSERT INTO scrapex_meta (key, value) VALUES
    ('database_kind', 'marketlens'),
    ('migration_stream', 'marketlens');

PRAGMA user_version = 13;
