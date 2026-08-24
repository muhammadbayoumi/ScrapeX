"""Provider registry for organization enrichment."""
from __future__ import annotations

import os
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


def provider_availability() -> list[dict[str, Any]]:
    google_ready = bool(os.environ.get("SCRAPEX_GOOGLE_PLACES_API_KEY", "").strip())
    return [
        {
            "key": ProviderName.WEBSITE.value,
            "label": "Official Website",
            "available": True,
            "reason": "Uses a non-generic organization email or a mapped website field.",
        },
        {
            "key": ProviderName.GOOGLE_PLACES.value,
            "label": "Google Places",
            "available": google_ready,
            "reason": (
                "Ready. Google billing and quota limits apply."
                if google_ready
                else "Set SCRAPEX_GOOGLE_PLACES_API_KEY before starting the engine."
            ),
        },
        {
            "key": ProviderName.LINKEDIN.value,
            "label": "LinkedIn",
            "available": False,
            "reason": "No verified LinkedIn data provider is configured.",
        },
    ]


def build_providers(names: list[str]):
    providers = ProviderSet()
    for name in names:
        if name == ProviderName.WEBSITE.value:
            providers.append(WebsiteProvider())
        elif name == ProviderName.GOOGLE_PLACES.value:
            key = os.environ.get("SCRAPEX_GOOGLE_PLACES_API_KEY", "").strip()
            if key:
                providers.append(GooglePlacesProvider(api_key=key))
    return providers
