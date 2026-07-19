"""Typed vocabulary and boundary DTOs for the generic dataset catalogue."""
from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator

MAX_PAGE_SIZE = 200
DEFAULT_PAGE_SIZE = 50
KEY_PATTERN = r"^[a-z][a-z0-9_]{1,63}$"
CatalogKey = Annotated[str, Field(pattern=KEY_PATTERN)]


class SiteLifecycle(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"


class DatasetKind(StrEnum):
    TABLE = "table"
    LIST = "list"
    DETAIL = "detail"
    TREE = "tree"
    STREAM = "stream"
    UNKNOWN = "unknown"


class DiscoveryMethod(StrEnum):
    MANUAL = "manual"
    HTML_TABLE = "html_table"
    REPEATING_DOM = "repeating_dom"
    JSON = "json"
    API = "api"
    INFERRED = "inferred"


class FieldType(StrEnum):
    TEXT = "text"
    INTEGER = "integer"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    URL = "url"
    JSON = "json"
    UNKNOWN = "unknown"


class IdentityRole(StrEnum):
    NONE = "none"
    CANDIDATE = "candidate"
    KEY_PART = "key_part"


class Cardinality(StrEnum):
    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    MANY_TO_MANY = "many_to_many"
    UNKNOWN = "unknown"


class RelationshipReviewStatus(StrEnum):
    SUGGESTED = "suggested"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class SiteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    site_key: CatalogKey
    display_name: str = Field(min_length=1, max_length=200)
    base_url: AnyHttpUrl
    lifecycle: SiteLifecycle = SiteLifecycle.DRAFT
    price_source_id: int | None = Field(default=None, gt=0)


class DatasetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    dataset_key: CatalogKey
    original_name: str = Field(min_length=1, max_length=500)
    dataset_kind: DatasetKind = DatasetKind.UNKNOWN
    discovery_method: DiscoveryMethod
    locator: dict[str, Any] = Field(default_factory=dict)


class FieldCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    field_key: CatalogKey
    original_name: str = Field(min_length=1, max_length=500)
    data_type: FieldType = FieldType.UNKNOWN
    is_nullable: bool = True
    identity_role: IdentityRole = IdentityRole.NONE
    display_order: int = Field(default=0, ge=0)


class RelationshipFieldPairCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parent_field_id: int = Field(gt=0)
    child_field_id: int = Field(gt=0)


class RelationshipCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    relationship_key: CatalogKey
    parent_dataset_id: int = Field(gt=0)
    child_dataset_id: int = Field(gt=0)
    cardinality: Cardinality = Cardinality.UNKNOWN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: dict[str, Any] = Field(default_factory=dict)
    field_pairs: list[RelationshipFieldPairCreate] = Field(min_length=1, max_length=32)

    @field_validator("field_pairs")
    @classmethod
    def _pairs_are_unique(
        cls, pairs: list[RelationshipFieldPairCreate]
    ) -> list[RelationshipFieldPairCreate]:
        keys = {(pair.parent_field_id, pair.child_field_id) for pair in pairs}
        if len(keys) != len(pairs):
            raise ValueError("field_pairs must not contain duplicates")
        return pairs


class SiteView(BaseModel):
    site_profile_id: int
    site_key: str
    display_name: str
    base_url: AnyHttpUrl
    price_source_id: int | None
    lifecycle: SiteLifecycle
    created_at: str
    updated_at: str


class DatasetView(BaseModel):
    dataset_definition_id: int
    site_profile_id: int
    dataset_key: str
    original_name: str
    display_name: str | None
    label: str
    dataset_kind: DatasetKind
    discovery_method: DiscoveryMethod
    locator: dict[str, Any]
    first_seen_at: str
    last_seen_at: str


class FieldView(BaseModel):
    field_definition_id: int
    dataset_definition_id: int
    field_key: str
    original_name: str
    display_name: str | None
    label: str
    data_type: FieldType
    is_nullable: bool
    identity_role: IdentityRole
    display_order: int
    first_seen_at: str
    last_seen_at: str


class RelationshipFieldPairView(BaseModel):
    parent_field_id: int
    parent_field_key: str
    child_field_id: int
    child_field_key: str
    pair_order: int


class RelationshipView(BaseModel):
    dataset_relationship_id: int
    site_profile_id: int
    relationship_key: str
    parent_dataset_id: int
    child_dataset_id: int
    cardinality: Cardinality
    review_status: RelationshipReviewStatus
    confidence: float
    evidence: dict[str, Any]
    field_pairs: list[RelationshipFieldPairView]
    created_at: str
    updated_at: str


class SitePage(BaseModel):
    sites: list[SiteView]
    next_after_id: int | None


class DatasetPage(BaseModel):
    datasets: list[DatasetView]
    next_after_id: int | None


class FieldPage(BaseModel):
    fields: list[FieldView]
    next_after_id: int | None


class RelationshipPage(BaseModel):
    relationships: list[RelationshipView]
    next_after_id: int | None


class CatalogError(ValueError):
    """A safe, user-facing catalogue refusal."""


class CatalogNotFound(CatalogError):
    pass


class CatalogConflict(CatalogError):
    pass
