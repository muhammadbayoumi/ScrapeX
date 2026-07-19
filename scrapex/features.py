"""One honest manifest for shipped and planned product capabilities.

The generic-platform work lands in vertical slices. Until a slice has a real
storage path, API, UI, recovery behavior, and tests, its flag stays disabled and
no navigation may advertise it as available. This avoids scattering optimistic
``if experimental`` checks across the extension and workspace.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum


class DeliveryStage(StrEnum):
    NOT_STARTED = "not_started"
    FOUNDATION = "foundation"
    PARTIAL = "partial"
    PRODUCTION_READY = "production_ready"


class FeatureKey(StrEnum):
    PRICE_TRACKING = "price_tracking"
    GENERIC_DATASET_CATALOG = "generic_dataset_catalog"
    GENERIC_EXTRACTION = "generic_extraction"
    CRAWL_FRONTIER = "crawl_frontier"
    SITE_DATA_MODEL = "site_data_model"


@dataclass(frozen=True)
class FeatureState:
    key: FeatureKey
    enabled: bool
    stage: DeliveryStage
    detail: str

    def public(self) -> dict:
        value = asdict(self)
        value["key"] = self.key.value
        value["stage"] = self.stage.value
        return value


_FEATURES = (
    FeatureState(
        FeatureKey.PRICE_TRACKING,
        True,
        DeliveryStage.PRODUCTION_READY,
        "Existing product and price workflows remain the compatibility baseline.",
    ),
    FeatureState(
        FeatureKey.GENERIC_DATASET_CATALOG,
        False,
        DeliveryStage.NOT_STARTED,
        "Enabled only after G1 stores and displays an arbitrary dataset end to end.",
    ),
    FeatureState(
        FeatureKey.GENERIC_EXTRACTION,
        False,
        DeliveryStage.NOT_STARTED,
        "Enabled only after an approved non-product extraction reaches generic storage.",
    ),
    FeatureState(
        FeatureKey.CRAWL_FRONTIER,
        False,
        DeliveryStage.NOT_STARTED,
        "Enabled only after persistent discovery, limits, and checkpoint recovery ship.",
    ),
    FeatureState(
        FeatureKey.SITE_DATA_MODEL,
        False,
        DeliveryStage.NOT_STARTED,
        "Enabled only after reviewed dataset relationships are persistent and navigable.",
    ),
)


def manifest() -> dict:
    """Public, deterministic feature state for UI and integration clients."""
    return {"features": [feature.public() for feature in _FEATURES]}


def is_enabled(key: FeatureKey) -> bool:
    """The single gate future routes and navigation must call."""
    return next(feature.enabled for feature in _FEATURES if feature.key == key)
