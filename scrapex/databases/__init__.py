"""Typed access to ScrapeX's operational database.

One file since M5. GeneralDatabase and MarketLensDatabase are still exported
because db/engine/schema.sql is DERIVED from their two streams and
tests/test_one_schema_carries_both_streams.py re-derives on every run. They
retire together with those streams once nothing is left on them.
"""

from .domain import (
    DatabaseHealth,
    DatabaseKindError,
    DatabaseMigrationError,
    DatabaseUnavailableError,
    EngineDatabase,
    GeneralDatabase,
    MarketLensDatabase,
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
    "GeneralDatabase",
    "MarketLensDatabase",
]
