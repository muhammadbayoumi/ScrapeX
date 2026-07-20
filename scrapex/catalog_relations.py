"""Suggested relationships between generic datasets and their field pairs."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from .catalog import _dataset_row, _json, _page_limit, _site_row
from .catalog_models import (
    DEFAULT_PAGE_SIZE, CatalogConflict, RelationshipCreate, RelationshipReviewStatus,
)


def _relationship_pairs(
    conn: sqlite3.Connection, relationship_ids: list[int]
) -> dict[int, list[dict[str, Any]]]:
    pairs = {relationship_id: [] for relationship_id in relationship_ids}
    if not relationship_ids:
        return pairs
    # Placeholder count is derived from bounded database IDs; all values remain
    # parameterized, and the second query avoids one query per relationship.
    placeholders = ",".join("?" for _ in relationship_ids)
    rows = conn.execute(
        "SELECT rfp.dataset_relationship_id, rfp.parent_field_id, "
        "rfp.child_field_id, rfp.pair_order, pf.field_key AS parent_field_key, "
        "cf.field_key AS child_field_key "
        "FROM relationship_field_pair rfp "
        "JOIN field_definition pf ON pf.field_definition_id = rfp.parent_field_id "
        "JOIN field_definition cf ON cf.field_definition_id = rfp.child_field_id "
        f"WHERE rfp.dataset_relationship_id IN ({placeholders}) "
        "ORDER BY rfp.dataset_relationship_id, rfp.pair_order",
        relationship_ids,
    ).fetchall()
    for row in rows:
        pairs[row["dataset_relationship_id"]].append({
            "parent_field_id": row["parent_field_id"],
            "parent_field_key": row["parent_field_key"],
            "child_field_id": row["child_field_id"],
            "child_field_key": row["child_field_key"],
            "pair_order": row["pair_order"],
        })
    return pairs


def _relationship_public(
    row: sqlite3.Row, pairs: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "dataset_relationship_id": row["dataset_relationship_id"],
        "site_profile_id": row["site_profile_id"],
        "relationship_key": row["relationship_key"],
        "parent_dataset_id": row["parent_dataset_id"],
        "child_dataset_id": row["child_dataset_id"],
        "cardinality": row["cardinality"],
        "review_status": row["review_status"],
        "confidence": row["confidence"],
        "evidence": json.loads(row["evidence_json"]),
        "field_pairs": pairs,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def propose_relationship(
    conn: sqlite3.Connection, site_key: str, request: RelationshipCreate
) -> dict[str, Any]:
    """Persist an inference as ``suggested``; this path can never confirm it."""
    site = _site_row(conn, site_key)
    parent = _dataset_row(conn, request.parent_dataset_id)
    child = _dataset_row(conn, request.child_dataset_id)
    if request.parent_dataset_id == request.child_dataset_id:
        raise CatalogConflict("a relationship must connect two different datasets")
    if parent["site_profile_id"] != site["site_profile_id"] or \
            child["site_profile_id"] != site["site_profile_id"]:
        raise CatalogConflict("relationship datasets must belong to the requested site")

    pair_keys = [
        (pair.parent_field_id, pair.child_field_id) for pair in request.field_pairs
    ]
    field_ids = {field_id for pair in pair_keys for field_id in pair}
    placeholders = ",".join("?" for _ in field_ids)
    rows = conn.execute(
        "SELECT field_definition_id, dataset_definition_id FROM field_definition "
        f"WHERE valid_to IS NULL AND field_definition_id IN ({placeholders})",
        sorted(field_ids),
    ).fetchall()
    owners = {row["field_definition_id"]: row["dataset_definition_id"] for row in rows}
    for parent_field_id, child_field_id in pair_keys:
        if owners.get(parent_field_id) != request.parent_dataset_id or \
                owners.get(child_field_id) != request.child_dataset_id:
            raise CatalogConflict(
                "relationship fields must belong to their mapped datasets"
            )

    evidence_json = _json(request.evidence)
    existing = conn.execute(
        "SELECT * FROM dataset_relationship "
        "WHERE site_profile_id = ? AND relationship_key = ?",
        (site["site_profile_id"], request.relationship_key),
    ).fetchone()
    if existing is not None:
        if existing["valid_to"] is not None:
            raise CatalogConflict(
                f"relationship_key {request.relationship_key!r} is retired; "
                "reactivate it explicitly"
            )
        existing_pairs = _relationship_pairs(
            conn, [existing["dataset_relationship_id"]]
        )[existing["dataset_relationship_id"]]
        existing_keys = [
            (pair["parent_field_id"], pair["child_field_id"])
            for pair in existing_pairs
        ]
        identity = (
            existing["parent_dataset_id"], existing["child_dataset_id"],
            existing["cardinality"], existing["confidence"],
            existing["evidence_json"], existing_keys,
        )
        proposed = (
            request.parent_dataset_id, request.child_dataset_id,
            request.cardinality.value, request.confidence, evidence_json, pair_keys,
        )
        if identity != proposed:
            raise CatalogConflict(
                f"relationship_key {request.relationship_key!r} already has "
                "another definition"
            )
        return _relationship_public(existing, existing_pairs)

    cursor = conn.execute(
        "INSERT INTO dataset_relationship "
        "(site_profile_id, relationship_key, parent_dataset_id, child_dataset_id, "
        "cardinality, review_status, confidence, evidence_json) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            site["site_profile_id"], request.relationship_key,
            request.parent_dataset_id, request.child_dataset_id,
            request.cardinality.value, RelationshipReviewStatus.SUGGESTED.value,
            request.confidence, evidence_json,
        ),
    )
    relationship_id = int(cursor.lastrowid)
    conn.executemany(
        "INSERT INTO relationship_field_pair "
        "(dataset_relationship_id, parent_field_id, child_field_id, pair_order) "
        "VALUES (?,?,?,?)",
        [
            (relationship_id, parent_field_id, child_field_id, order)
            for order, (parent_field_id, child_field_id) in enumerate(pair_keys)
        ],
    )
    row = conn.execute(
        "SELECT * FROM dataset_relationship WHERE dataset_relationship_id = ?",
        (relationship_id,),
    ).fetchone()
    return _relationship_public(
        row, _relationship_pairs(conn, [relationship_id])[relationship_id]
    )


def list_relationships(
    conn: sqlite3.Connection, site_key: str, *, after_id: int = 0,
    limit: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    limit = _page_limit(limit)
    site = _site_row(conn, site_key)
    rows = conn.execute(
        "SELECT * FROM dataset_relationship WHERE site_profile_id = ? "
        "AND valid_to IS NULL AND dataset_relationship_id > ? "
        "ORDER BY dataset_relationship_id LIMIT ?",
        (site["site_profile_id"], max(0, after_id), limit + 1),
    ).fetchall()
    has_more = len(rows) > limit
    page = rows[:limit]
    ids = [row["dataset_relationship_id"] for row in page]
    pairs = _relationship_pairs(conn, ids)
    return {
        "relationships": [
            _relationship_public(row, pairs[row["dataset_relationship_id"]])
            for row in page
        ],
        "next_after_id": page[-1]["dataset_relationship_id"] if has_more else None,
    }
