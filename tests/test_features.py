"""G0 feature gates: planned generic work is never advertised as shipped."""
from __future__ import annotations

import pytest

from scrapex.features import DeliveryStage, FeatureKey, is_enabled, manifest


def test_price_tracking_is_the_enabled_compatibility_baseline():
    assert is_enabled(FeatureKey.PRICE_TRACKING) is True
    price = next(f for f in manifest()["features"] if f["key"] == "price_tracking")
    assert price["stage"] == DeliveryStage.PRODUCTION_READY.value


def test_generic_catalogue_foundation_is_visible_but_not_enabled():
    feature = next(
        f for f in manifest()["features"] if f["key"] == "generic_dataset_catalog"
    )
    assert feature["stage"] == DeliveryStage.FOUNDATION.value
    assert feature["enabled"] is False


@pytest.mark.parametrize("feature", [
    FeatureKey.GENERIC_DATASET_CATALOG,
    FeatureKey.GENERIC_EXTRACTION,
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
