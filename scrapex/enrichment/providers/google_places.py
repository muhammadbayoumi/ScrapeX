"""Google Places Text Search provider with conservative entity matching."""
from __future__ import annotations

from collections.abc import Callable

import httpx

from ..matching import (
    email_domain,
    haversine_metres,
    host_of,
    name_similarity,
    normalized_phone,
    status_for_score,
)
from ..models import FieldFact, OrganizationIdentity, ProviderResult

ENDPOINT = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join((
    "places.id",
    "places.displayName",
    "places.formattedAddress",
    "places.nationalPhoneNumber",
    "places.internationalPhoneNumber",
    "places.websiteUri",
    "places.googleMapsUri",
    "places.businessStatus",
    "places.rating",
    "places.userRatingCount",
    "places.location",
))


def _post_with_client(client: httpx.Client, api_key: str, body: dict) -> dict:
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


class GooglePlacesProvider:
    name = "google_places"

    def __init__(self, api_key: str, post: Callable[[str, dict], dict] | None = None):
        self._api_key = api_key
        self._client = None
        if post is not None:
            self._post = post
        else:
            self._client = httpx.Client(
                timeout=httpx.Timeout(15.0, connect=6.0), trust_env=False
            )
            self._post = lambda key, body: _post_with_client(self._client, key, body)

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def run(self, identity: OrganizationIdentity) -> ProviderResult:
        query = " ".join(filter(None, (
            identity.company_name or identity.company_name_ar,
            identity.city,
            identity.country,
        )))
        if not query:
            return ProviderResult(self.name, checked=False, error="no searchable name")
        body: dict = {"textQuery": query, "pageSize": 5, "languageCode": "en"}
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
        candidates = payload.get("places") or []
        if not candidates:
            return ProviderResult(self.name, (
                FieldFact(
                    "google_match_status", "not_found", self.name,
                    source_url=ENDPOINT, confidence=0.0,
                    verification_status="not_found", evidence={"query": query},
                ),
            ))
        ranked = sorted(
            ((_score(identity, place), place) for place in candidates),
            key=lambda pair: pair[0], reverse=True,
        )
        score, place = ranked[0]
        status = status_for_score(score)
        maps_url = str(place.get("googleMapsUri") or "")
        evidence = {
            "query": query,
            "candidate_count": len(candidates),
            "candidate_name": (place.get("displayName") or {}).get("text", ""),
        }
        common = {
            "provider": self.name,
            "source_url": maps_url or ENDPOINT,
            "confidence": score,
            "verification_status": status,
            "evidence": evidence,
        }
        google_phone = str(
            place.get("internationalPhoneNumber")
            or place.get("nationalPhoneNumber")
            or ""
        )
        values = {
            "google_place_id": place.get("id"),
            "google_maps_url": maps_url,
            "google_maps_cid_url": maps_url if "cid=" in maps_url.casefold() else None,
            "google_business_name": (place.get("displayName") or {}).get("text"),
            "google_formatted_address": place.get("formattedAddress"),
            "google_phone": google_phone,
            "google_website": place.get("websiteUri"),
            "google_business_status": place.get("businessStatus"),
            "gmaps_rating": place.get("rating"),
            "reviews_count": place.get("userRatingCount"),
            "google_match_status": status,
            "google_match_score": score,
        }
        source_phone = normalized_phone(identity.phone)
        candidate_phone = normalized_phone(google_phone)
        if (
            status == "verified"
            and len(candidate_phone) >= 7
            and candidate_phone != source_phone
        ):
            values["verified_phone_secondary"] = google_phone
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
        distance = haversine_metres(
            identity.latitude, identity.longitude,
            float(location["latitude"]), float(location["longitude"]),
        )
        coordinate_score = 1.0 if distance <= 150 else 0.8 if distance <= 1_000 \
            else 0.45 if distance <= 5_000 else 0.0
        score += 0.23 * coordinate_score
    phone = str(place.get("internationalPhoneNumber")
                or place.get("nationalPhoneNumber") or "")
    website = str(place.get("websiteUri") or "")
    identity_phone = normalized_phone(identity.phone)
    candidate_phone = normalized_phone(phone)
    phone_matches = bool(
        len(identity_phone) >= 7 and identity_phone == candidate_phone
    )
    domain = email_domain(identity.email)
    domain_matches = bool(domain and domain == host_of(website))
    if phone_matches or domain_matches:
        score += 0.15
    return round(min(score, 1.0), 4)
