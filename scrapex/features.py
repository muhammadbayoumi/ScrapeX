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
        DeliveryStage.PARTIAL,
        "Usable end to end and the compatibility baseline every other slice must "
        "not break. Not production_ready: an audit against the product spec found "
        "most of its capabilities missing states, recovery paths or tests.",
    ),
    FeatureState(
        FeatureKey.GENERIC_DATASET_CATALOG,
        True,
        DeliveryStage.PARTIAL,
        "Enabled 2026-08-20 on the owner's instruction. One dataset is catalogued "
        "and browsable: /api/sources reports `contractors` with kind=dataset among "
        "thirteen entries (#212), /source/contractors renders it (#220), and "
        "/api/table/contractors answers 22 columns over 11,059 rows. PARTIAL, not "
        "production_ready: there is exactly one dataset, no dataset-only page, and "
        "the relationship and promotion paths are untested for this kind.",
    ),
    FeatureState(
        FeatureKey.GENERIC_EXTRACTION,
        True,
        DeliveryStage.PARTIAL,
        "Enabled 2026-08-20 on the owner's instruction, its written condition met: "
        "11,059 muqawil.org contractors reached generic storage through the approval "
        "path over 1,728 ingestions -- 864 English pages and 864 Arabic -- every one "
        "of them status=success with none refused, and all seven declared bilingual "
        "pairs carry Arabic values (#202-#212, #220). PARTIAL: one site, "
        "listing pages only, and the ~6,224 contractors the sweep counted have no "
        "evidence stored.",
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
    """The gate that NAVIGATION and UI must call before advertising a capability.

    Deliberately not applied to the catalogue API routes themselves: they are
    mounted so the slice can be exercised and tested, on a server bound to
    127.0.0.1. What the flag governs is whether anything tells a user the
    capability exists — which is the claim spec section 40 forbids inflating.
    """
    return next(feature.enabled for feature in _FEATURES if feature.key == key)
