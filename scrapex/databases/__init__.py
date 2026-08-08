"""Typed access to ScrapeX's operational database.

One file since M5, and one name for it: the engine's own. What the two
databases before it carried, it carries — see db/engine/derived-from.json, which
records what they had at the moment they were collapsed.
"""

from .domain import (
    DatabaseHealth,
    DatabaseKindError,
    DatabaseMigrationError,
    DatabaseUnavailableError,
    EngineDatabase,
)
from .registry import DatabasePointerError, DatabaseRegistry

__all__ = [
    "DatabaseHealth",
    "DatabaseKindError",
    "DatabaseMigrationError",
    "DatabasePointerError",
    "DatabaseRegistry",
    "DatabaseUnavailableError",
    "EngineDatabase",
]
