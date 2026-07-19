-- migration 0002: contract-version stamp (two-engine guardrail).
-- Records which contract version wrote this warehouse. An engine whose
-- CONTRACT_VERSION differs must refuse to write (see scrapex/contract.py),
-- so two engines can never fork one warehouse's fingerprints.
CREATE TABLE scrapex_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

PRAGMA user_version = 2;
