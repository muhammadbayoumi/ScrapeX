"""Probe a URL to detect its platform and suggest a manifest entry (S5 helper).

Reuses HttpFetcher (DRY, F5 politeness) and is fully injectable so tests run
with a stub — no network. Detection mirrors the live 10-site survey: try the
platform's own open API first, fall back to homepage markers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from .connectors.base import HttpFetcher
from .connectors.factory import _BUILDERS
from .vocab import Cadence, ConnectorFamily, ExtractKind, ExtractScope, VatMode

# TLD -> region guess (best-effort; the owner confirms in the form).
_TLD_REGION = {"sa": "SA", "eg": "EG", "ae": "AE", "kw": "KW", "qa": "QA"}


@dataclass
class ProbeResult:
    url: str
    reachable: bool
    family: ConnectorFamily
    implemented: bool
    evidence: list[str] = field(default_factory=list)
    suggested: dict = field(default_factory=dict)
    notes: str = ""

    def to_json(self) -> dict:
        return {
            "url": self.url, "reachable": self.reachable, "family": self.family.value,
            "implemented": self.implemented, "evidence": self.evidence,
            "suggested": self.suggested, "notes": self.notes,
        }


def _base(url: str) -> tuple[str, str]:
    parsed = urlparse(url if "//" in url else f"https://{url}")
    host = (parsed.hostname or "").lower()
    scheme = parsed.scheme or "https"
    return f"{scheme}://{host}", host


def _key_from_host(host: str) -> str:
    label = host.removeprefix("www.").split(".")[0]
    key = "".join(ch if ch.isalnum() else "_" for ch in label).upper().strip("_")
    if not key or not key[0].isalpha():
        key = f"SRC_{key}" if key else "NEW_SOURCE"
    return key[:64]


def _try_json(fetcher, url: str, **kw):
    """GET and parse JSON, returning None on any failure (probe is best-effort)."""
    try:
        resp = fetcher.get(url, **kw)
    except Exception:  # noqa: BLE001 — a missing endpoint is a negative signal, not an error
        return None
    try:
        return resp.json()
    except ValueError:
        return None


def probe(url: str, fetcher: HttpFetcher | None = None) -> ProbeResult:
    own = fetcher is None
    fetcher = fetcher or HttpFetcher()
    base, host = _base(url)
    evidence: list[str] = []
    family = ConnectorFamily.TBD_PROBE
    currency: str | None = None
    region = _TLD_REGION.get(host.rsplit(".", 1)[-1], "*")
    reachable = False
    try:
        # 1) Shopify — /products.json
        data = _try_json(fetcher, f"{base}/products.json", params={"limit": 1})
        if isinstance(data, dict) and isinstance(data.get("products"), list):
            reachable = True
            family = ConnectorFamily.SHOPIFY_JSON
            evidence.append("/products.json returned a Shopify products array")
        # 2) WooCommerce Store API
        if family == ConnectorFamily.TBD_PROBE:
            data = _try_json(fetcher, f"{base}/wp-json/wc/store/products", params={"per_page": 1})
            if isinstance(data, list):
                reachable = True
                family = ConnectorFamily.WOOCOMMERCE_STOREAPI
                evidence.append("/wp-json/wc/store/products returned a WooCommerce array")
        # 3) Magento 2 GraphQL (also yields currency + store region)
        if family == ConnectorFamily.TBD_PROBE:
            data = _try_json(fetcher, f"{base}/graphql",
                             params={"query": "{storeConfig{store_code base_currency_code}}"})
            cfg = (data or {}).get("data", {}).get("storeConfig") if isinstance(data, dict) else None
            if cfg:
                reachable = True
                family = ConnectorFamily.MAGENTO_GRAPHQL
                currency = cfg.get("base_currency_code")
                store_code = (cfg.get("store_code") or "")
                if "_" in store_code:
                    region = store_code.split("_")[-1].upper()
                evidence.append(f"/graphql storeConfig: {store_code}, {currency}")
        # 4) Homepage markers (Salla / Zid / Shopify CDN / Woo)
        if family == ConnectorFamily.TBD_PROBE:
            html = _get_text(fetcher, base)
            if html:
                reachable = True
                low = html.lower()
                if "salla" in low:
                    family = ConnectorFamily.SALLA_HTML
                    evidence.append("homepage carries Salla markers")
                elif "zid.store" in low or "cdn.zid" in low:
                    family = ConnectorFamily.ZID_HTML
                    evidence.append("homepage carries Zid markers")
                elif "cdn.shopify" in low:
                    family = ConnectorFamily.SHOPIFY_JSON
                    evidence.append("homepage carries Shopify CDN markers")
                elif "wp-content" in low or "woocommerce" in low:
                    family = ConnectorFamily.WOOCOMMERCE_STOREAPI
                    evidence.append("homepage carries WordPress/WooCommerce markers")
                else:
                    evidence.append("reachable, but no known platform markers found")
    finally:
        if own:
            fetcher.close()

    suggested = {
        "source_key": _key_from_host(host),
        "source_name": host.removeprefix("www."),
        "base_url": base,
        "family": family.value,
        "currency": currency or "",
        "default_region": region,
        "vat_mode": VatMode.INCLUSIVE.value,
        "fetcher": "http",
        "cadence": Cadence.DAILY.value,
        "authority": "shop",
        "kind": ExtractKind.PRODUCT_PRICES.value,
        "scope": ExtractScope.CENSUS.value,
        "active": False,
    }
    implemented = family in _BUILDERS
    notes = (
        "Known family with a connector — you can capture immediately."
        if implemented else
        "No connector for this family yet. You can still register it; capture "
        "lights up once its connector lands."
    )
    return ProbeResult(url=url, reachable=reachable, family=family,
                       implemented=implemented, evidence=evidence,
                       suggested=suggested, notes=notes)


def _get_text(fetcher, url: str) -> str | None:
    try:
        return fetcher.get(url).text
    except Exception:  # noqa: BLE001
        return None
