"""G0 feature gates: planned generic work is never advertised as shipped."""
from __future__ import annotations

import pytest

from scrapex.features import DeliveryStage, FeatureKey, is_enabled, manifest


def test_price_tracking_is_the_enabled_compatibility_baseline():
    """Enabled, because it works end to end and nothing else may break it.

    NOT production_ready: an audit of 121 capabilities against the product spec
    graded exactly one at that level. This manifest exists to stop capabilities
    being oversold, which makes it the last place that may oversell one.
    """
    assert is_enabled(FeatureKey.PRICE_TRACKING) is True
    price = next(f for f in manifest()["features"] if f["key"] == "price_tracking")
    assert price["enabled"] is True
    assert price["stage"] == DeliveryStage.PARTIAL.value


def test_the_two_generic_capabilities_the_owner_lit_are_partial_not_ready():
    """Lit 2026-08-20, and the point of this manifest is that lighting one is a
    CLAIM. Both are PARTIAL rather than production_ready: one site, one dataset,
    listing pages only. A flag that jumped straight to production_ready would be
    the overselling this file exists to prevent."""
    for key in ("generic_dataset_catalog", "generic_extraction"):
        feature = next(f for f in manifest()["features"] if f["key"] == key)
        assert feature["enabled"] is True, key
        assert feature["stage"] == DeliveryStage.PARTIAL.value, key
        assert feature["stage"] != DeliveryStage.PRODUCTION_READY.value, key

    assert is_enabled(FeatureKey.GENERIC_DATASET_CATALOG) is True
    assert is_enabled(FeatureKey.GENERIC_EXTRACTION) is True


def test_a_lit_flag_says_what_evidence_lit_it():
    """The detail is the whole value of an honest manifest: `enabled: true` with
    no evidence is indistinguishable from optimism. Both entries name the
    measurement and the pull requests, and both name what is NOT done."""
    for key in ("generic_dataset_catalog", "generic_extraction"):
        detail = next(f for f in manifest()["features"] if f["key"] == key)["detail"]
        assert "2026-08-20" in detail, key
        assert "11,059" in detail, key
        assert "PARTIAL" in detail, key


@pytest.mark.parametrize("feature", [
    FeatureKey.CRAWL_FRONTIER,
    FeatureKey.SITE_DATA_MODEL,
])
def test_unfinished_generic_capabilities_are_disabled(feature):
    assert is_enabled(feature) is False


def test_the_public_manifest_uses_stable_strings_not_python_enums():
    payload = manifest()
    assert payload["features"]
    assert all(isinstance(item["key"], str) and isinstance(item["stage"], str)
               for item in payload["features"])
