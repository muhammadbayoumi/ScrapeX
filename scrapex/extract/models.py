"""Typed HTTP and service boundaries for the first generic extraction slice."""
from __future__ import annotations

from typing import Annotated

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
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
    #: Which crawl run fetched this page, so an interrupted one can resume
    #: without re-fetching what it already has. SET AT INSERT AND NEVER
    #: UPDATED -- `trg_generic_page_snapshot_immutable_update` forbids the
    #: alternative, and rightly: who fetched a page is a fact fixed at the
    #: moment of capture. None for a crawl that does not name itself, and for
    #: the 1,728 snapshots stored before runs had names.
    crawl_run_ref: str | None = None
    #: WHICH RUN, PROVABLY -- the typed companion to the label above, added by `0016`
    #: for `R-54`'s second half. `crawl_run_ref` is what an operator typed and it is
    #: what `--run-ref` resumes on; this is a foreign key into `crawl_run`, and it is
    #: what the State column compares against. Measured before the two were separated:
    #: the label has 141 distinct values across 55,313 snapshots, one per PARTITION
    #: CELL for a listing crawl and one per CRAWL for a profile crawl, and one stored
    #: value is literally `R`. None for every snapshot taken before `0016`, and his
    #: ruling for those rows is `unsighted`.
    run_id: int | None = None
    #: Which compression dictionary this page belongs with -- `host/kind`, from
    #: `snapshotbody.label_for`. None means STORE IT AS IT ARRIVED, and that is
    #: the default on purpose: the engine's save-a-page endpoint saves one page
    #: by hand, which has no class to share a dictionary with and nothing to
    #: gain. A crawl of 36,548 pages has both. See docs/STORAGE.md.
    body_class: str | None = None


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
    def has_identity_field(self) -> CandidateApproval:
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
