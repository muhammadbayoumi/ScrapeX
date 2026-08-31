"""Provider registry for organization enrichment."""
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..models import ProviderName
from .google_places import GooglePlacesProvider
from .website import WebsiteProvider


class ProviderSet(list):
    """A provider batch owns reusable network clients for exactly one job."""

    def close(self) -> None:
        for provider in self:
            close = getattr(provider, "close", None)
            if close is not None:
                close()

    def __del__(self):  # pragma: no cover - the explicit job close is authoritative
        try:
            self.close()
        except Exception:
            pass


@dataclass(frozen=True)
class ProviderSpec:
    key: str
    label: str
    reason: Callable[[], str]
    available: Callable[[], bool]
    factory: Callable[[], Any] | None
    version: str
    estimated_requests_per_entity: int


_REGISTRY: dict[str, ProviderSpec] = {}


def register_provider(spec: ProviderSpec) -> None:
    """Register one provider capability without changing the job service."""
    if spec.key in _REGISTRY:
        raise ValueError(f"provider {spec.key!r} is already registered")
    _REGISTRY[spec.key] = spec


def _google_ready() -> bool:
    return bool(os.environ.get("SCRAPEX_GOOGLE_PLACES_API_KEY", "").strip())


register_provider(ProviderSpec(
    key=ProviderName.WEBSITE.value,
    label="Official Website",
    available=lambda: True,
    reason=lambda: "Uses a non-generic organization email or a mapped website field.",
    factory=WebsiteProvider,
    version=WebsiteProvider.version,
    estimated_requests_per_entity=WebsiteProvider.estimated_requests_per_entity,
))
register_provider(ProviderSpec(
    key=ProviderName.GOOGLE_PLACES.value,
    label="Google Places (Place ID only)",
    available=_google_ready,
    reason=lambda: (
        "Ready in policy-safe Place ID-only storage mode. Billing and quotas apply."
        if _google_ready()
        else "Set SCRAPEX_GOOGLE_PLACES_API_KEY before starting the engine."
    ),
    factory=lambda: GooglePlacesProvider(
        api_key=os.environ.get("SCRAPEX_GOOGLE_PLACES_API_KEY", "").strip()
    ),
    version=GooglePlacesProvider.version,
    estimated_requests_per_entity=GooglePlacesProvider.estimated_requests_per_entity,
))
register_provider(ProviderSpec(
    key=ProviderName.LINKEDIN.value,
    label="LinkedIn",
    available=lambda: False,
    reason=lambda: "No verified LinkedIn data provider is configured.",
    factory=None,
    version="unavailable",
    estimated_requests_per_entity=0,
))


def provider_availability() -> list[dict[str, Any]]:
    return [{
        "key": spec.key,
        "label": spec.label,
        "available": spec.available(),
        "reason": spec.reason(),
        "version": spec.version,
        "estimated_requests_per_entity": spec.estimated_requests_per_entity,
    } for spec in _REGISTRY.values()]


def build_providers(names: list[str]):
    providers = ProviderSet()
    for name in names:
        spec = _REGISTRY.get(name)
        if spec is not None and spec.available() and spec.factory is not None:
            providers.append(spec.factory())
    return providers


def provider_versions(names: list[str]) -> dict[str, str]:
    return {name: _REGISTRY[name].version for name in names if name in _REGISTRY}


def estimate_requests(names: list[str], organizations: int) -> int:
    return organizations * sum(
        _REGISTRY[name].estimated_requests_per_entity
        for name in names if name in _REGISTRY
    )
