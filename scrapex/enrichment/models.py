"""Typed boundaries shared by organization enrichment providers and APIs."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..catalog_models import CatalogKey


class ProviderName(StrEnum):
    WEBSITE = "website"
    GOOGLE_PLACES = "google_places"
    LINKEDIN = "linkedin"


FIELD_ROLES = (
    "company_name",
    "company_name_ar",
    "email",
    "phone",
    "latitude",
    "longitude",
    "city",
    "country",
    "profile_url",
    "website",
)


class DefinitionCreate(BaseModel):
    """The reviewed mapping that turns a source dataset into organizations."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_dataset_key: CatalogKey
    detail_dataset_key: CatalogKey | None = None
    output_dataset_key: CatalogKey | None = None
    output_dataset_name: str | None = Field(default=None, max_length=200)
    entity_key_field: CatalogKey
    detail_key_field: CatalogKey | None = None
    field_mapping: dict[str, CatalogKey] = Field(default_factory=dict)
    providers: list[ProviderName] = Field(
        default_factory=lambda: [ProviderName.WEBSITE]
    )

    @field_validator("field_mapping")
    @classmethod
    def mapping_roles_are_known(cls, value: dict[str, str]) -> dict[str, str]:
        unknown = sorted(set(value) - set(FIELD_ROLES))
        if unknown:
            raise ValueError(f"unknown organization field roles: {unknown}")
        return {key: field for key, field in value.items() if field}

    @field_validator("providers")
    @classmethod
    def providers_are_unique(cls, value: list[ProviderName]) -> list[ProviderName]:
        return list(dict.fromkeys(value))

    @model_validator(mode="after")
    def detail_join_is_complete(self) -> DefinitionCreate:
        if bool(self.detail_dataset_key) != bool(self.detail_key_field):
            raise ValueError(
                "detail_dataset_key and detail_key_field must be provided together"
            )
        if not self.field_mapping.get("company_name") and not self.field_mapping.get(
            "company_name_ar"
        ):
            raise ValueError("map at least one company name field")
        return self


@dataclass(frozen=True)
class OrganizationIdentity:
    organization_id: str
    external_id: str
    source_record_id: int
    source_snapshot_id: int
    source_url: str
    company_name: str = ""
    company_name_ar: str = ""
    email: str = ""
    phone: str = ""
    latitude: float | None = None
    longitude: float | None = None
    city: str = ""
    country: str = ""
    profile_url: str = ""
    website: str = ""


@dataclass(frozen=True)
class FieldFact:
    field_key: str
    value: Any
    provider: str
    source_url: str = ""
    confidence: float = 0.0
    verification_status: str = "candidate"
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    facts: tuple[FieldFact, ...] = ()
    checked: bool = True
    error: str = ""


@dataclass(frozen=True)
class OutputField:
    key: str
    data_type: str = "text"
    identity: bool = False


OUTPUT_FIELDS: tuple[OutputField, ...] = (
    OutputField("organization_id", identity=True),
    OutputField("source_record_id", "integer"),
    OutputField("source_external_id"),
    OutputField("company_name"),
    OutputField("company_name_ar"),
    OutputField("website_url", "url"),
    OutputField("company_domain"),
    OutputField("website_match_status"),
    OutputField("website_match_score", "decimal"),
    OutputField("website_description"),
    OutputField("core_specialties", "json"),
    OutputField("iso_certifications", "json"),
    OutputField("careers_url", "url"),
    OutputField("careers_email"),
    OutputField("careers_contact"),
    OutputField("verified_phone_secondary"),
    OutputField("google_place_id"),
    OutputField("google_maps_url", "url"),
    OutputField("google_business_name"),
    OutputField("google_formatted_address"),
    OutputField("google_phone"),
    OutputField("google_website", "url"),
    OutputField("google_business_status"),
    OutputField("gmaps_rating", "decimal"),
    OutputField("reviews_count", "integer"),
    OutputField("google_match_status"),
    OutputField("google_match_score", "decimal"),
    OutputField("linkedin_company_url", "url"),
    OutputField("linkedin_employee_count", "integer"),
    OutputField("key_decision_makers", "json"),
    OutputField("linkedin_match_status"),
    OutputField("linkedin_match_score", "decimal"),
    OutputField("verification_status"),
    OutputField("verification_score", "decimal"),
    OutputField("manual_review_status"),
    OutputField("providers_checked", "json"),
    OutputField("evidence_urls", "json"),
    OutputField("first_enriched_at", "datetime"),
    OutputField("last_enriched_at", "datetime"),
)
