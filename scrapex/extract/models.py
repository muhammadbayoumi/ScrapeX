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

#: THE LARGEST BODY A SNAPSHOT HOLDS, whatever stored it. A directory read from a JSON API
#: stores a page of rows: TVTC's training plans measured up to 10.96 MB a 1,000-row page over
#: the full 84-page crawl (`#1716` step 2), so 16 MB left a 1.46x margin, and a page past the
#: cap is not stored while its ids still count as read. 32 MB is that page with a 2.9x
#: margin (his choice over a smaller page size). The body is zstd-compressed at rest
#: (`snapshotbody.py`, 31x over the 84 plans pages), so the cost is transfer, not warehouse. A body
#: over it is refused by name, never truncated (`service.save_snapshot`).
MAX_STORED_BODY_BYTES = 32_000_000

#: THE LARGEST PAGE HE MAY SAVE BY HAND (`POST /api/general/extract/snapshots`), A SECOND
#: LIMIT BECAUSE IT GUARDS A SECOND COST. That page's tables are found by BeautifulSoup inside
#: the warehouse write (`service.approve_candidate` -> `detect_html_tables`), measured at
#: 4.3 s and 245 MB for 1.99 MB and 29.9 s and 1.27 GB for 15.9 MB (#1739). It changes with
#: parse cost; `MAX_STORED_BODY_BYTES` changes with page size. One number for both is what
#: let a crawl's need raise the parse's exposure.
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
    html_content: str = Field(min_length=1, max_length=MAX_STORED_BODY_BYTES)
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


class SavedPageCreate(SnapshotCreate):
    """A page he saves by hand, whose tables are then parsed: `MAX_HTML_BYTES`, not the
    crawl's `MAX_STORED_BODY_BYTES`. The body model of the save-a-page route only."""

    html_content: str = Field(min_length=1, max_length=MAX_HTML_BYTES)

    @field_validator("html_content")
    @classmethod
    def _within_the_byte_limit(cls, value: str) -> str:
        """BYTES, NOT CHARACTERS. `max_length` counts code points, so a 2M-character Arabic
        page -- about 4 MB as UTF-8 -- passed it (#1749's review, through the real route)."""
        size = len(value.encode("utf-8"))
        if size > MAX_HTML_BYTES:
            raise ValueError(
                f"the saved page is {size:,} bytes; a page saved by hand may be at most "
                f"{MAX_HTML_BYTES:,}")
        return value


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
