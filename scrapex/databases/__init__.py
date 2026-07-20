"""Typed access to ScrapeX's physically isolated operational databases."""

from .domain import (
    DatabaseHealth,
    DatabaseKindError,
    DatabaseMigrationError,
    DatabaseUnavailableError,
    GeneralDatabase,
    MarketLensDatabase,
)
from .registry import DatabaseRegistry, LegacyDatabaseRequiresSplit

__all__ = [
    "DatabaseHealth",
    "DatabaseKindError",
    "DatabaseMigrationError",
    "DatabaseRegistry",
    "DatabaseUnavailableError",
    "GeneralDatabase",
    "LegacyDatabaseRequiresSplit",
    "MarketLensDatabase",
]
