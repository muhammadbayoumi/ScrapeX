"""ScrapeX ecosystem — contract-driven collection into a SQLite warehouse."""

# Re-exported, not restated: scrapex/version.py is the authority and everything
# that reports a version reads it from there. This name stays because packaging
# tools and existing call sites look for it.
from .version import VERSION as __version__

__all__ = ["__version__"]
