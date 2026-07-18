"""Probe: platform detection from injected responses (no network)."""
from __future__ import annotations

import pytest

from scrapex.probe import _key_from_host, probe
from scrapex.vocab import ConnectorFamily


class _Resp:
    def __init__(self, payload=None, text="", ok=True):
        self._payload, self._text, self._ok = payload, text, ok
    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload
    @property
    def text(self):
        return self._text


class _StubFetcher:
    """Maps url-substring -> _Resp; raises (endpoint absent) for anything else."""
    def __init__(self, routes: dict):
        self.routes, self.requests_count = routes, 0
    def get(self, url, **kw):
        self.requests_count += 1
        for needle, resp in self.routes.items():
            if needle in url:
                return resp
        raise RuntimeError("404")
    def close(self):
        pass


def test_detects_shopify():
    f = _StubFetcher({"/products.json": _Resp(payload={"products": [{"id": 1}]})})
    r = probe("https://shop.example.com", fetcher=f)
    assert r.family == ConnectorFamily.SHOPIFY_JSON and r.implemented is True
    assert r.suggested["source_key"] == "SHOP"


def test_detects_woocommerce():
    f = _StubFetcher({"/wp-json/wc/store/products": _Resp(payload=[{"id": 10}])})
    r = probe("https://store.example.eg", fetcher=f)
    assert r.family == ConnectorFamily.WOOCOMMERCE_STOREAPI
    assert r.suggested["default_region"] == "EG"  # from .eg TLD


def test_detects_magento_with_currency_and_region():
    f = _StubFetcher({"/graphql": _Resp(payload={"data": {"storeConfig": {
        "store_code": "en_SA", "base_currency_code": "SAR"}}})})
    r = probe("https://www.madar.com", fetcher=f)
    assert r.family == ConnectorFamily.MAGENTO_GRAPHQL
    assert r.suggested["currency"] == "SAR" and r.suggested["default_region"] == "SA"


def test_detects_salla_by_homepage_marker():
    f = _StubFetcher({"://": _Resp(text="<html>powered by salla cdn.salla.sa</html>")})
    r = probe("https://alsweed.sa", fetcher=f)
    assert r.family == ConnectorFamily.SALLA_HTML and r.implemented is False


def test_unknown_platform_is_tbd_probe():
    f = _StubFetcher({"://": _Resp(text="<html>just a site</html>")})
    r = probe("https://mystery.example.com", fetcher=f)
    assert r.family == ConnectorFamily.TBD_PROBE
    assert r.implemented is False and r.reachable is True


def test_unreachable_site():
    r = probe("https://nothing.invalid", fetcher=_StubFetcher({}))
    assert r.reachable is False and r.family == ConnectorFamily.TBD_PROBE


def test_key_from_host_sanitizes():
    assert _key_from_host("www.el-buroj.com") == "EL_BUROJ"
    assert _key_from_host("123shop.com").startswith("SRC_")
