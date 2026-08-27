"""Typed boundaries shared by organization enrichment providers and APIs."""
from __future__ import annotations

import re
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

    site_key: CatalogKey | None = None
    source_dataset_key: CatalogKey
    detail_dataset_key: CatalogKey | None = None
    output_dataset_key: CatalogKey | None = None
    output_dataset_name: str | None = Field(default=None, max_length=200)
    entity_key_field: CatalogKey
    detail_key_field: CatalogKey | None = None
    # A role points at a dataset-qualified field (`source:name` or
    # `detail:name`).  Unqualified keys remain accepted for definitions made by
    # the first release and retain its source-first behaviour.
    field_mapping: dict[str, str] = Field(default_factory=dict)
    providers: list[str] = Field(
        default_factory=lambda: [ProviderName.WEBSITE.value], min_length=1
    )

    @field_validator("field_mapping")
    @classmethod
    def mapping_roles_are_known(cls, value: dict[str, str]) -> dict[str, str]:
        unknown = sorted(set(value) - set(FIELD_ROLES))
        if unknown:
            raise ValueError(f"unknown organization field roles: {unknown}")
        cleaned = {}
        for role, reference in value.items():
            if not reference:
                continue
            if not re.fullmatch(r"(?:(?:source|detail):)?[a-z][a-z0-9_]{1,63}", reference):
                raise ValueError(
                    f"field mapping for {role!r} must be source:<field> or detail:<field>"
                )
            cleaned[role] = reference
        return cleaned

    @field_validator("providers")
    @classmethod
    def providers_are_unique(cls, value: list[str]) -> list[str]:
        invalid = [item for item in value if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", item)]
        if invalid:
            raise ValueError(f"invalid provider keys: {invalid}")
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
    entity_match_confidence: float | None = None
    extraction_confidence: float | None = None
    source_authority: float | None = None


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    facts: tuple[FieldFact, ...] = ()
    checked: bool = True
    error: str = ""
    system_error: bool = False


class ReviewAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    OVERRIDE = "override"


class DefinitionStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    RETIRED = "retired"


class DefinitionStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: DefinitionStatus


class ReviewDecisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: ReviewAction
    value: Any | None = None
    reviewer: str = Field(default="owner", min_length=1, max_length=100)
    reason: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def override_has_value(self) -> ReviewDecisionCreate:
        if self.action is ReviewAction.OVERRIDE and self.value is None:
            raise ValueError("override decisions require a value")
        if self.action is not ReviewAction.OVERRIDE and self.value is not None:
            raise ValueError("only override decisions may supply a value")
        return self


class OrganizationMergeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target_organization_id: str = Field(pattern=r"^org_[a-f0-9]{24}$")
    reviewer: str = Field(default="owner", min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)


class OrganizationMergeReverseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reviewer: str = Field(default="owner", min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)


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
    OutputField("contact_page_url", "url"),
    OutputField("contact_emails", "json"),
    OutputField("contact_phones", "json"),
    OutputField("whatsapp_url", "url"),
    OutputField("verified_phone_secondary"),
    OutputField("google_place_id"),
    OutputField("google_maps_url", "url"),
    OutputField("google_maps_cid_url", "url"),
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
    OutputField("entity_match_score", "decimal"),
    OutputField("data_quality_score", "decimal"),
    OutputField("freshness_status"),
    OutputField("google_attribution"),
    OutputField("manual_review_status"),
    OutputField("providers_checked", "json"),
    OutputField("evidence_urls", "json"),
    OutputField("first_enriched_at", "datetime"),
    OutputField("last_enriched_at", "datetime"),
)
