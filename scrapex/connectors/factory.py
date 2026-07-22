"""Family -> connector dispatch (ENGINEERING.md A3, P5 explicit registry).

Only families with a landed, tested connector appear here. An unimplemented
family fails loud with a clear message — never a silent no-op.
"""
from __future__ import annotations

from ..config import SourceEntry
from ..vocab import ConnectorFamily
from .base import HttpFetcher, SiteConnector, resolve_fetcher
from .custom_json import CustomJsonConnector
from .gpp import GlobalPetrolPricesConnector
from .hybris import HybrisOccConnector
from .magento import MagentoGraphqlConnector
from .salla import SallaConnector
from .shopify import ShopifyConnector
from .woocommerce import WooCommerceConnector
from .zid import ZidConnector

# Families whose connector can collect the source's OWN published history
# (the `_history` mode). Declared here beside the builders so a new family
# cannot gain the capability without the registry saying so — and the Run
# panel offers History backfill only to sources on this list.
HISTORY_CAPABLE = frozenset({ConnectorFamily.STATIC_HTML_TABLE})


def supports_history(family: ConnectorFamily) -> bool:
    return family in HISTORY_CAPABLE


_BUILDERS = {
    ConnectorFamily.SHOPIFY_JSON: lambda fetcher: ShopifyConnector(fetcher),
    ConnectorFamily.MAGENTO_GRAPHQL: lambda fetcher: MagentoGraphqlConnector(fetcher),
    ConnectorFamily.WOOCOMMERCE_STOREAPI: lambda fetcher: WooCommerceConnector(fetcher),
    ConnectorFamily.SALLA_HTML: lambda fetcher: SallaConnector(fetcher),
    ConnectorFamily.HYBRIS_OCC: lambda fetcher: HybrisOccConnector(fetcher),
    ConnectorFamily.ZID_HTML: lambda fetcher: ZidConnector(fetcher),
    ConnectorFamily.CUSTOM_JSON_API: lambda fetcher: CustomJsonConnector(fetcher),
    ConnectorFamily.STATIC_HTML_TABLE: lambda fetcher: GlobalPetrolPricesConnector(fetcher),
}


def build_connector(source: SourceEntry,
                    crawl_settings: dict | None = None) -> tuple[SiteConnector, HttpFetcher]:
    """Return (connector, fetcher) for a source. The caller owns the fetcher's
    lifetime (close it after the crawl) so request counts can be recorded.

    `crawl_settings` carries the owner's politeness and timeout choices (spec 33).
    They are passed in rather than read here, so this module keeps no opinion
    about where settings live and a test needs no database to build a connector.
    """
    builder = _BUILDERS.get(source.family)
    if builder is None:
        raise NotImplementedError(
            f"no connector implemented for family {source.family.value!r} "
            f"(source {source.source_key}); implemented: "
            f"{[f.value for f in _BUILDERS]}"
        )
    fetcher = resolve_fetcher(source, crawl_settings)
    return builder(fetcher), fetcher
