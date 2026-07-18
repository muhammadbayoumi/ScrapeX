"""T8: the funnel payload contract — validation, chunking, golden fixtures."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scrapex.payload import (
    CHUNK_MAX_CHARS,
    PAYLOAD_VERSION,
    FunnelPayload,
    export_json_schema,
    reassemble_chunks,
    split_into_chunks,
    utc_now_iso,
)

FIXTURES = Path(__file__).resolve().parent.parent / "contracts" / "fixtures"


def make_payload(rows: list[list[str]] | None = None) -> FunnelPayload:
    return FunnelPayload(
        payload_version=PAYLOAD_VERSION,
        source_key="MADAR",
        kind="product_prices",
        client="cli",
        scraped_at="2026-07-16T10:00:00Z",
        source_url="https://www.madar.com/graphql",
        header=["external_product_id", "external_variant_id", "sku", "name", "price"],
        rows=rows if rows is not None else [
            ["4672", "4670", "120151248", "Fire Retardant Plywood - 12mm", "112.50"],
            ["4672", "4671", "120151848", "Fire Retardant Plywood - 18mm", "168.78"],
        ],
    )


# ---- golden fixtures: the cross-language contract vectors (T8) --------------

def test_golden_valid_fixture_parses():
    payload = FunnelPayload.model_validate_json(
        (FIXTURES / "payload_valid.json").read_text(encoding="utf-8")
    )
    assert payload.source_key == "MADAR"
    assert payload.rows[1][4] == "168.78"  # exact-value assertion (T2)


def test_golden_invalid_fixtures_rejected():
    for fixture in sorted(FIXTURES.glob("payload_invalid_*.json")):
        with pytest.raises(ValidationError):
            FunnelPayload.model_validate_json(fixture.read_text(encoding="utf-8"))


def test_exported_schema_is_current():
    """The committed schema file must match the model — same-commit rule (T8)."""
    committed = json.loads(
        (FIXTURES.parent / "funnel-payload.schema.json").read_text(encoding="utf-8")
    )
    assert committed == export_json_schema(), (
        "contracts/funnel-payload.schema.json is stale — run: scrapex export-contract"
    )


# ---- validation edges (T3/P4) ------------------------------------------------

def test_wrong_version_rejected():
    with pytest.raises(ValidationError, match="payload_version"):
        FunnelPayload.model_validate(
            {**json.loads(make_payload().model_dump_json()), "payload_version": 99}
        )


def test_ragged_rows_rejected():
    with pytest.raises(ValidationError, match="ragged|cells"):
        make_payload(rows=[["only-one-cell"]])


def test_non_utc_timestamp_rejected():
    data = json.loads(make_payload().model_dump_json())
    data["scraped_at"] = "2026-07-16T10:00:00+03:00"
    with pytest.raises(ValidationError, match="UTC"):
        FunnelPayload.model_validate(data)


def test_unknown_fields_rejected():
    data = json.loads(make_payload().model_dump_json())
    data["surprise"] = "field"
    with pytest.raises(ValidationError):
        FunnelPayload.model_validate(data)


def test_utc_now_iso_shape():
    stamp = utc_now_iso()
    assert stamp.endswith("Z") and len(stamp) == 20  # 2026-07-16T10:00:00Z


# ---- chunking (S1) -----------------------------------------------------------

def test_small_payload_is_single_stamped_chunk():
    chunks = split_into_chunks(make_payload())
    assert len(chunks) == 1
    assert chunks[0].chunk.index == 1 and chunks[0].chunk.total == 1


def test_large_payload_chunks_under_limit_and_roundtrips():
    wide_row = ["cell-" + "x" * 200] * 5
    payload = make_payload(rows=[list(wide_row) for _ in range(200)])
    chunks = split_into_chunks(payload)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.model_dump_json()) <= CHUNK_MAX_CHARS
    rebuilt = reassemble_chunks(chunks)
    assert rebuilt.rows == payload.rows
    assert rebuilt.chunk is None


def test_empty_rows_still_sends_one_chunk():
    chunks = split_into_chunks(make_payload(rows=[]))
    assert len(chunks) == 1 and chunks[0].rows == []


def test_megarow_fails_loud():
    huge = [["x" * (CHUNK_MAX_CHARS + 1)] * 5]
    payload = make_payload(rows=huge)
    with pytest.raises(ValueError, match="megarow|exceeds"):
        split_into_chunks(payload)


def test_reassemble_missing_chunk_fails_loud():
    payload = make_payload(rows=[["r", "r", "r", "r", str(i)] for i in range(200)])
    wide = make_payload(rows=[["cell-" + "x" * 200] * 5 for _ in range(200)])
    chunks = split_into_chunks(wide)
    assert len(chunks) >= 2
    with pytest.raises(ValueError, match="expected"):
        reassemble_chunks(chunks[:-1])


def test_reassemble_mixed_batches_fails_loud():
    a = split_into_chunks(make_payload())[0]
    other = make_payload()
    b = other.model_copy(update={"source_key": "ALSWEED"})
    b = split_into_chunks(b)[0]
    with pytest.raises(ValueError):
        reassemble_chunks([a, b.model_copy(update={"chunk": a.chunk.model_copy(update={"index": 2, "total": 2})})])
