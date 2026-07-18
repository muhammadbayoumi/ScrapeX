"""Family -> connector dispatch (ENGINEERING.md A3, P5 explicit registry).

Only families with a landed, tested connector appear here. An unimplemented
family fails loud with a clear message — never a silent no-op.
"""
from __future__ import annotations

from ..config import SourceEntry
from ..vocab import ConnectorFamily
from .base import HttpFetcher, SiteConnector, resolve_fetcher
from .shopify import ShopifyConnector

_BUILDERS = {
    ConnectorFamily.SHOPIFY_JSON: lambda fetcher: ShopifyConnector(fetcher),
}


def build_connector(source: SourceEntry) -> tuple[SiteConnector, HttpFetcher]:
    """Return (connector, fetcher) for a source. The caller owns the fetcher's
    lifetime (close it after the crawl) so request counts can be recorded."""
    builder = _BUILDERS.get(source.family)
    if builder is None:
        raise NotImplementedError(
            f"no connector implemented for family {source.family.value!r} "
            f"(source {source.source_key}); implemented: "
            f"{[f.value for f in _BUILDERS]}"
        )
    fetcher = resolve_fetcher(source)
    return builder(fetcher), fetcher
