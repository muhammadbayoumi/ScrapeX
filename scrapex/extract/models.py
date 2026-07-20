"""Typed HTTP and service boundaries for the first generic extraction slice."""
from __future__ import annotations

from typing import Annotated

from pydantic import (
    AnyHttpUrl, BaseModel, ConfigDict, Field, field_validator, model_validator,
)

from ..catalog_models import CatalogKey, FieldType

MAX_HTML_BYTES = 2_000_000
MAX_TABLES = 20
MAX_TABLE_ROWS = 5_000
MAX_TABLE_COLUMNS = 100
MAX_PREVIEW_ROWS = 10
MAX_RECORD_PAGE_SIZE = 100
DEFAULT_RECORD_PAGE_SIZE = 50


class SnapshotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_url: AnyHttpUrl
    html_content: str = Field(min_length=1, max_length=MAX_HTML_BYTES)


class ApprovalField(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    field_key: CatalogKey
    display_name: str = Field(min_length=1, max_length=500)
    data_type: FieldType
    identity: bool = False


class CandidateApproval(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    table_index: int = Field(ge=0, lt=MAX_TABLES)
    site_key: CatalogKey
    site_display_name: str = Field(min_length=1, max_length=200)
    dataset_key: CatalogKey
    dataset_name: str = Field(min_length=1, max_length=500)
    fields: list[ApprovalField] = Field(min_length=1, max_length=MAX_TABLE_COLUMNS)

    @field_validator("fields")
    @classmethod
    def field_keys_are_unique(cls, fields: list[ApprovalField]) -> list[ApprovalField]:
        keys = [field.field_key for field in fields]
        if len(keys) != len(set(keys)):
            raise ValueError("fields must not contain duplicate field_key values")
        return fields

    @model_validator(mode="after")
    def has_identity_field(self) -> "CandidateApproval":
        if not any(field.identity for field in self.fields):
            raise ValueError(
                "select at least one identity field before approving the dataset"
            )
        return self


SnapshotIdPath = Annotated[int, Field(gt=0)]


class ExtractionError(ValueError):
    """A safe, actionable generic-extraction refusal."""


class ExtractionNotFound(ExtractionError):
    pass


class ExtractionConflict(ExtractionError):
    pass


class CandidateNotApprovable(ExtractionError):
    pass
