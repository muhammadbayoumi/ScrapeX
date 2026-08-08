"""Stable physical identities for ScrapeX operational databases.

An application id is written into the SQLite header and is how a file says what
it is BEFORE anything reads a table out of it. That matters most in the cases
where a name cannot be trusted: a backup restored into the wrong place, a file
copied between machines, a path typed with one letter wrong.

M5 replaces the two with one. `engine` is the whole warehouse — the priced
offers and the generic records in one file — and takes the engine's own name, so
`scrapex-engine.exe` is paired with `scrapex-engine.db`.

THE OLD TWO ARE KEPT DELIBERATELY. They are what `db/engine/schema.sql` is
derived from, and tests/test_one_schema_carries_both_streams.py re-derives on
every run to prove the one schema still carries everything the two carried. They
retire together with their migration streams, once nothing is left on them.
"""

ENGINE_APPLICATION_ID = 0x5358454E  # "SXEN"

GENERAL_APPLICATION_ID = 0x5358474E  # "SXGN"
MARKETLENS_APPLICATION_ID = 0x53584D4C  # "SXML"

ENGINE_DATABASE_KIND = "engine"

GENERAL_DATABASE_KIND = "general"
MARKETLENS_DATABASE_KIND = "marketlens"
