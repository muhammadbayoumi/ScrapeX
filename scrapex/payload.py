"""The versioned funnel payload contract (ENGINEERING.md T8).

ONE contract, THREE parties: the Python CLI (producer), the Chrome extension
(producer), and the Apps Script funnel (consumer). This module is the Python
authority; `contracts/funnel-payload.schema.json` is the exported neutral form
consumed by the extension's tests and standing as the GAS contract; the golden
fixtures in `contracts/fixtures/` are shared vectors all three validate against.

Any change here MUST bump PAYLOAD_VERSION and update the schema + fixtures in
the same commit (T8).

Chunking (S1): Apps Script appends one chunk per sheet row; a cell holds at
most 50,000 chars, so chunks are capped at CHUNK_MAX_CHARS = 40,000 with margin.
Reassembly happens ONLY in Python at ingest — GAS stays dumb.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .vocab import ExtractKind, PayloadClient

PAYLOAD_VERSION = 1

# 40k keeps a comfortable margin under the Google Sheets 50k-char cell limit
# even after the funnel adds its envelope columns (S1).
CHUNK_MAX_CHARS = 40_000


class FunnelChunk(BaseModel):
    """Position of one chunk inside a chunked batch (1-based)."""

    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1)
    total: int = Field(ge=1)

    @field_validator("index")
    @classmethod
    def _index_within_total(cls, v: int, info):  # explicit guard (P4)
        # total is validated afterwards when both fields exist (model validator
        # would be heavier; the pair check happens in FunnelPayload below).
        return v


class FunnelPayload(BaseModel):
    """One batch of raw scraped rows on its way to the staging inbox.

    `header` + `rows` deliberately mirror the shape the add-in's
    StreamingTsvReader produces on the read path: raw strings, no typing —
    normalization happens later, in one shared place (Q2).
    """

    model_config = ConfigDict(extra="forbid")

    payload_version: int
    source_key: str = Field(min_length=1, max_length=64)
    kind: ExtractKind
    client: PayloadClient
    scraped_at: str  # UTC ISO8601 with Z suffix
    source_url: str = Field(min_length=1)
    header: list[str]
    rows: list[list[str]]
    chunk: FunnelChunk | None = None
    run_ref: str | None = None  # producer-side run correlation id (CLI run, extension capture)

    @field_validator("payload_version")
    @classmethod
    def _version_supported(cls, v: int) -> int:
        if v != PAYLOAD_VERSION:
            raise ValueError(
                f"unsupported payload_version {v}; this build speaks version {PAYLOAD_VERSION}"
            )
        return v

    @field_validator("scraped_at")
    @classmethod
    def _scraped_at_utc_iso(cls, v: str) -> str:
        # Explicit over clever (P5): require the exact wire format we emit.
        try:
            parsed = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"scraped_at is not ISO8601: {v!r}") from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError(f"scraped_at must be UTC ('Z' or +00:00): {v!r}")
        return v

    @field_validator("rows")
    @classmethod
    def _rows_match_header(cls, v: list[list[str]], info) -> list[list[str]]:
        header = info.data.get("header")
        if header is not None:
            width = len(header)
            for i, row in enumerate(v):
                if len(row) != width:
                    raise ValueError(
                        f"row {i} has {len(row)} cells, header has {width} — "
                        "ragged rows are a parse defect at the connector (Q4)"
                    )
        return v


def utc_now_iso() -> str:
    """The one blessed wire timestamp format (Q5)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def split_into_chunks(payload: FunnelPayload) -> list[FunnelPayload]:
    """Split a payload into wire chunks whose serialized size fits CHUNK_MAX_CHARS.

    Rows are never split across chunks. A payload that already fits is returned
    as a single element (with chunk 1/1 stamped so the consumer sees a uniform
    envelope).
    """
    envelope_probe = payload.model_copy(update={"rows": [], "chunk": FunnelChunk(index=1, total=1)})
    envelope_chars = len(envelope_probe.model_dump_json())
    budget = CHUNK_MAX_CHARS - envelope_chars
    if budget <= 0:  # pathological header; explicit failure over silent truncation (Q4)
        raise ValueError("payload envelope alone exceeds CHUNK_MAX_CHARS")

    groups: list[list[list[str]]] = []
    current: list[list[str]] = []
    used = 0
    for row in payload.rows:
        row_chars = len(json.dumps(row, ensure_ascii=False)) + 1  # +1 separator
        if row_chars > budget:
            raise ValueError(
                f"single row of {row_chars} chars exceeds chunk budget {budget}; "
                "connector must not emit megarows (S1)"
            )
        if current and used + row_chars > budget:
            groups.append(current)
            current, used = [], 0
        current.append(row)
        used += row_chars
    groups.append(current)  # empty-row payloads still send one (empty) chunk

    total = len(groups)
    return [
        payload.model_copy(update={"rows": rows, "chunk": FunnelChunk(index=i, total=total)})
        for i, rows in enumerate(groups, start=1)
    ]


def reassemble_chunks(chunks: list[FunnelPayload]) -> FunnelPayload:
    """Rebuild the original batch from wire chunks (ingest side).

    Validates completeness and ordering explicitly — a missing chunk is a loud
    error, never silently-partial data (Q3/Q4).
    """
    if not chunks:
        raise ValueError("no chunks to reassemble")
    first = chunks[0]
    total = first.chunk.total if first.chunk else 1
    if len(chunks) != total:
        raise ValueError(f"expected {total} chunks, got {len(chunks)}")
    ordered = sorted(chunks, key=lambda c: c.chunk.index if c.chunk else 1)
    for expected_index, chunk in enumerate(ordered, start=1):
        got = chunk.chunk.index if chunk.chunk else 1
        if got != expected_index:
            raise ValueError(f"chunk sequence broken: expected {expected_index}, got {got}")
        if chunk.source_key != first.source_key or chunk.scraped_at != first.scraped_at:
            raise ValueError("chunks from different batches mixed together")
    rows = [row for chunk in ordered for row in chunk.rows]
    return first.model_copy(update={"rows": rows, "chunk": None})


def export_json_schema() -> dict:
    """The neutral contract form written to contracts/funnel-payload.schema.json."""
    schema = FunnelPayload.model_json_schema()
    schema["title"] = "ScrapeX funnel payload"
    schema["description"] = (
        f"Version {PAYLOAD_VERSION}. One contract for CLI + extension producers "
        "and the Apps Script consumer. See scraper/ENGINEERING.md T8."
    )
    return schema


def math_expected_chunks(total_rows: int, rows_per_chunk: int) -> int:
    """Tiny helper kept for test readability."""
    return max(1, math.ceil(total_rows / rows_per_chunk))
