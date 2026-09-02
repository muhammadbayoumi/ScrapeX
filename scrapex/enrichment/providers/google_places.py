"""Google Places Text Search provider with conservative entity matching."""
from __future__ import annotations

import math
import os
import threading
import time
from collections.abc import Callable

import httpx

from ..matching import (
    email_domain,
    haversine_metres,
    name_similarity,
    normalized_phone,
    registrable_domain,
    status_for_score,
)
from ..models import FieldFact, OrganizationIdentity, ProviderResult

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join((
    "places.id",
    "places.displayName",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.websiteUri",
    "places.location",
))
_RATE_LOCK = threading.Lock()
_NEXT_REQUEST_AT = 0.0


def _pace_requests() -> None:
    global _NEXT_REQUEST_AT
    try:
        configured_qps = float(os.environ.get("SCRAPEX_GOOGLE_PLACES_QPS", "5") or 5)
    except ValueError:
        configured_qps = 5.0
    if not math.isfinite(configured_qps):
        configured_qps = 5.0
    qps = max(configured_qps, 0.1)
    with _RATE_LOCK:
        now = time.monotonic()
        wait = max(0.0, _NEXT_REQUEST_AT - now)
        _NEXT_REQUEST_AT = max(now, _NEXT_REQUEST_AT) + (1.0 / qps)
    if wait:
        time.sleep(wait)


def _post_with_client(
    client: httpx.Client,
    api_key: str,
    body: dict,
    before_request: Callable[[], None] | None = None,
) -> dict:
    for attempt in range(3):
        if before_request is not None:
            before_request()
        try:
            response = client.post(
                ENDPOINT,
                json=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Goog-Api-Key": api_key,
                    "X-Goog-FieldMask": FIELD_MASK,
                },
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            response = exc.response
            if response.status_code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
            retry_after = response.headers.get("Retry-After", "")
            try:
                delay = min(max(float(retry_after), 0.0), 10.0)
            except ValueError:
                delay = float(2 ** attempt)
            time.sleep(delay)
        except (httpx.TransportError, ValueError):
            if attempt == 2:
                raise
            time.sleep(float(2 ** attempt))
    raise RuntimeError("unreachable Google Places retry state")


class GooglePlacesProvider:
    name = "google_places"
    version = "3-strict-place-id-only"
    ttl_seconds = 30 * 24 * 60 * 60
    estimated_requests_per_entity = 3

    def __init__(self, api_key: str, post: Callable[[str, dict], dict] | None = None):
        self._api_key = api_key
        self._client = None
        self.requests_made = 0
        if post is None:
            self._client = httpx.Client(
                timeout=httpx.Timeout(15.0, connect=6.0), trust_env=False
            )

            def before_request() -> None:
                _pace_requests()
                self.requests_made += 1

            def raw_post(key: str, body: dict) -> dict:
                return _post_with_client(
                    self._client, key, body, before_request=before_request
                )

            self._post = raw_post
        else:
            def counted_post(key: str, body: dict) -> dict:
                _pace_requests()
                self.requests_made += 1
                return post(key, body)

            self._post = counted_post

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def run(self, identity: OrganizationIdentity) -> ProviderResult:
        query = " ".join(filter(None, (
            identity.company_name or identity.company_name_ar,
            identity.city,
            identity.country,
        )))[:256]
        if not query:
            return ProviderResult(self.name, checked=False, error="no searchable name")
        selected_name = identity.company_name or identity.company_name_ar
        language = "ar" if any("\u0600" <= char <= "\u06ff" for char in selected_name) else "en"
        body: dict = {"textQuery": query, "pageSize": 5, "languageCode": language}
        if identity.latitude is not None and identity.longitude is not None:
            body["locationBias"] = {"circle": {"center": {
                "latitude": identity.latitude,
                "longitude": identity.longitude,
            }, "radius": 5000.0}}
        try:
            payload = self._post(self._api_key, body)
        except Exception as exc:
            return ProviderResult(
                self.name, checked=False, error=str(exc), system_error=True
            )
        if not isinstance(payload, dict):
            return ProviderResult(
                self.name, checked=False, error="Google Places returned a non-object payload",
                system_error=True,
            )
        candidates = [item for item in (payload.get("places") or [])
                      if isinstance(item, dict)]
        if not candidates:
            return ProviderResult(self.name)
        ranked = sorted(
            ((_score(identity, place), place) for place in candidates),
            key=lambda pair: pair[0], reverse=True,
        )
        score, place = ranked[0]
        status = status_for_score(score)
        if status != "verified" or not place.get("id"):
            # Candidate content and the decision score are transient. Only an
            # unambiguous Place ID association crosses the durable boundary.
            return ProviderResult(self.name)
        evidence = {
            "query": query,
            "storage_mode": "place_id_only",
            "attribution": "Google Maps",
            "match_decision": "transient_verified_threshold",
        }
        common = {
            "provider": self.name,
            "source_url": ENDPOINT,
            "confidence": 1.0,
            "verification_status": "verified",
            "evidence": evidence,
            "entity_match_confidence": 1.0,
            "extraction_confidence": 1.0,
            "source_authority": 0.95,
        }
        # Durable Places storage is intentionally ID-only.  Names, addresses,
        # phones, websites, ratings and counts are used transiently for entity
        # matching and are never returned as facts.  They may later be rendered
        # on demand by a policy-compliant attributed UI.
        values = {
            "google_place_id": place.get("id"),
            "google_attribution": "Google Maps",
        }
        facts = [FieldFact(key, value, **common)
                 for key, value in values.items() if value not in (None, "")]
        return ProviderResult(self.name, tuple(facts))


def _score(identity: OrganizationIdentity, place: dict) -> float:
    display_name = str((place.get("displayName") or {}).get("text") or "")
    name_score = max(
        name_similarity(identity.company_name, display_name),
        name_similarity(identity.company_name_ar, display_name),
    )
    score = 0.62 * name_score
    location = place.get("location") or {}
    if identity.latitude is not None and identity.longitude is not None and \
            location.get("latitude") is not None and location.get("longitude") is not None:
        try:
            candidate_latitude = float(location["latitude"])
            candidate_longitude = float(location["longitude"])
        except (TypeError, ValueError):
            candidate_latitude = candidate_longitude = math.nan
        if math.isfinite(candidate_latitude) and math.isfinite(candidate_longitude) \
                and -90 <= candidate_latitude <= 90 \
                and -180 <= candidate_longitude <= 180:
            distance = haversine_metres(
                identity.latitude, identity.longitude,
                candidate_latitude, candidate_longitude,
            )
            coordinate_score = 1.0 if distance <= 150 else 0.8 if distance <= 1_000 \
                else 0.45 if distance <= 5_000 else 0.0
            score += 0.10 * coordinate_score
    phone = str(place.get("internationalPhoneNumber")
                or place.get("nationalPhoneNumber") or "")
    website = str(place.get("websiteUri") or "")
    identity_phone = normalized_phone(identity.phone)
    candidate_phone = normalized_phone(phone)
    phone_matches = bool(
        len(identity_phone) >= 7 and identity_phone == candidate_phone
    )
    domain = email_domain(identity.email)
    domain_matches = bool(domain and domain == registrable_domain(website))
    if phone_matches or domain_matches:
        score += 0.28
    return round(min(score, 1.0), 4)
