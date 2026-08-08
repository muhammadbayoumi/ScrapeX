"""The engine database's stable physical identity.

An application id is written into the SQLite header, so a file says what it is
BEFORE anything reads a table out of it. That matters most where a name cannot
be trusted: a backup restored into the wrong place, a copy carried between
machines, a path typed with one letter wrong.

There was one of these per database until M5. There is one database now, and it
takes the engine's own name, so `scrapex-engine.exe` is paired with
`scrapex-engine.db`.
"""

ENGINE_APPLICATION_ID = 0x5358454E  # "SXEN"

ENGINE_DATABASE_KIND = "engine"
