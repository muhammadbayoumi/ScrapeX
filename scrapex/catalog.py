"""Persistent definitions for generic sites, datasets, fields and relations.

This module is catalogue-only: it describes arbitrary structures without
pretending that generic extraction or row storage has shipped. Price tables are
never reused, inferred relations remain suggestions, and repeat discovery is
idempotent unless a stable identity changes meaning.
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from .catalog_models import (
    DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, CatalogConflict, CatalogNotFound,
    DatasetCreate, FieldCreate, SiteCreate,
)


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _page_limit(limit: int) -> int:
    if limit < 1 or limit > MAX_PAGE_SIZE:
        raise ValueError(f"limit must be between 1 and {MAX_PAGE_SIZE}")
    return limit


def _site_row(conn: sqlite3.Connection, site_key: str) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM site_profile WHERE site_key = ? AND valid_to IS NULL",
        (site_key,),
    ).fetchone()
    if row is None:
        raise CatalogNotFound(f"unknown active site profile {site_key!r}")
    return row


def _dataset_row(conn: sqlite3.Connection, dataset_id: int) -> sqlite3.Row:
    row = conn.execute(
        "SELECT * FROM dataset_definition "
        "WHERE dataset_definition_id = ? AND valid_to IS NULL",
        (dataset_id,),
    ).fetchone()
    if row is None:
        raise CatalogNotFound(f"unknown active dataset {dataset_id}")
    return row


def _site_public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "site_profile_id": row["site_profile_id"],
        "site_key": row["site_key"],
        "display_name": row["display_name"],
        "base_url": row["base_url"],
        "price_source_id": row["price_source_id"],
        "lifecycle": row["lifecycle"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _dataset_public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "dataset_definition_id": row["dataset_definition_id"],
        "site_profile_id": row["site_profile_id"],
        "dataset_key": row["dataset_key"],
        "original_name": row["original_name"],
        "display_name": row["display_name"],
        "label": row["display_name"] or row["original_name"],
        "dataset_kind": row["dataset_kind"],
        "discovery_method": row["discovery_method"],
        "locator": json.loads(row["locator_json"]),
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
    }


def _field_public(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "field_definition_id": row["field_definition_id"],
        "dataset_definition_id": row["dataset_definition_id"],
        "field_key": row["field_key"],
        "original_name": row["original_name"],
        "display_name": row["display_name"],
        "label": row["display_name"] or row["original_name"],
        "data_type": row["data_type"],
        "is_nullable": bool(row["is_nullable"]),
        "identity_role": row["identity_role"],
        "display_order": row["display_order"],
        "first_seen_at": row["first_seen_at"],
        "last_seen_at": row["last_seen_at"],
    }


def register_site(conn: sqlite3.Connection, request: SiteCreate) -> dict[str, Any]:
    """Register a site idempotently without overwriting its stable identity."""
    base_url = str(request.base_url)
    existing = conn.execute(
        "SELECT * FROM site_profile WHERE site_key = ?", (request.site_key,)
    ).fetchone()
    if existing is not None:
        if existing["valid_to"] is not None:
            raise CatalogConflict(
                f"site_key {request.site_key!r} is retired; reactivate it explicitly"
            )
        if existing["base_url"] != base_url:
            raise CatalogConflict(
                f"site_key {request.site_key!r} already belongs to "
                f"{existing['base_url']!r}"
            )
        return _site_public(existing)
    cursor = conn.execute(
        "INSERT INTO site_profile "
        "(site_key, display_name, base_url, price_source_id, lifecycle) "
        "VALUES (?,?,?,?,?)",
        (
            request.site_key,
            request.display_name,
            base_url,
            request.price_source_id,
            request.lifecycle.value,
        ),
    )
    return _site_public(conn.execute(
        "SELECT * FROM site_profile WHERE site_profile_id = ?", (cursor.lastrowid,)
    ).fetchone())


def list_sites(
    conn: sqlite3.Connection, *, after_id: int = 0, limit: int = DEFAULT_PAGE_SIZE
) -> dict[str, Any]:
    limit = _page_limit(limit)
    rows = conn.execute(
        "SELECT * FROM site_profile WHERE valid_to IS NULL AND site_profile_id > ? "
        "ORDER BY site_profile_id LIMIT ?",
        (max(0, after_id), limit + 1),
    ).fetchall()
    has_more = len(rows) > limit
    page = rows[:limit]
    return {
        "sites": [_site_public(row) for row in page],
        "next_after_id": page[-1]["site_profile_id"] if has_more else None,
    }


def register_dataset(
    conn: sqlite3.Connection, site_key: str, request: DatasetCreate
) -> dict[str, Any]:
    site = _site_row(conn, site_key)
    locator_json = _json(request.locator)
    existing = conn.execute(
        "SELECT * FROM dataset_definition "
        "WHERE site_profile_id = ? AND dataset_key = ?",
        (site["site_profile_id"], request.dataset_key),
    ).fetchone()
    if existing is not None:
        if existing["valid_to"] is not None:
            raise CatalogConflict(
                f"dataset_key {request.dataset_key!r} is retired; "
                "reactivate it explicitly"
            )
        identity = (
            existing["original_name"], existing["dataset_kind"],
            existing["discovery_method"], existing["locator_json"],
        )
        proposed = (
            request.original_name, request.dataset_kind.value,
            request.discovery_method.value, locator_json,
        )
        if identity != proposed:
            raise CatalogConflict(
                f"dataset_key {request.dataset_key!r} already has another definition"
            )
        conn.execute(
            "UPDATE dataset_definition SET last_seen_at = "
            "strftime('%Y-%m-%dT%H:%M:%SZ','now') "
            "WHERE dataset_definition_id = ?",
            (existing["dataset_definition_id"],),
        )
        return _dataset_public(_dataset_row(conn, existing["dataset_definition_id"]))
    cursor = conn.execute(
        "INSERT INTO dataset_definition "
        "(site_profile_id, dataset_key, original_name, dataset_kind, "
        "discovery_method, locator_json) VALUES (?,?,?,?,?,?)",
        (
            site["site_profile_id"], request.dataset_key, request.original_name,
            request.dataset_kind.value, request.discovery_method.value, locator_json,
        ),
    )
    return _dataset_public(_dataset_row(conn, int(cursor.lastrowid)))


def list_datasets(
    conn: sqlite3.Connection, site_key: str, *, after_id: int = 0,
    limit: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    limit = _page_limit(limit)
    site = _site_row(conn, site_key)
    rows = conn.execute(
        "SELECT * FROM dataset_definition WHERE site_profile_id = ? "
        "AND valid_to IS NULL AND dataset_definition_id > ? "
        "ORDER BY dataset_definition_id LIMIT ?",
        (site["site_profile_id"], max(0, after_id), limit + 1),
    ).fetchall()
    has_more = len(rows) > limit
    page = rows[:limit]
    return {
        "datasets": [_dataset_public(row) for row in page],
        "next_after_id": page[-1]["dataset_definition_id"] if has_more else None,
    }


def register_field(
    conn: sqlite3.Connection, dataset_id: int, request: FieldCreate
) -> dict[str, Any]:
    dataset = _dataset_row(conn, dataset_id)
    existing = conn.execute(
        "SELECT * FROM field_definition "
        "WHERE dataset_definition_id = ? AND field_key = ?",
        (dataset["dataset_definition_id"], request.field_key),
    ).fetchone()
    if existing is not None:
        if existing["valid_to"] is not None:
            raise CatalogConflict(
                f"field_key {request.field_key!r} is retired; reactivate it explicitly"
            )
        identity = (
            existing["original_name"], existing["data_type"],
            bool(existing["is_nullable"]), existing["identity_role"],
        )
        proposed = (
            request.original_name, request.data_type.value,
            request.is_nullable, request.identity_role.value,
        )
        if identity != proposed:
            raise CatalogConflict(
                f"field_key {request.field_key!r} already has another definition"
            )
        conn.execute(
            "UPDATE field_definition SET last_seen_at = "
            "strftime('%Y-%m-%dT%H:%M:%SZ','now') "
            "WHERE field_definition_id = ?",
            (existing["field_definition_id"],),
        )
        row = conn.execute(
            "SELECT * FROM field_definition WHERE field_definition_id = ?",
            (existing["field_definition_id"],),
        ).fetchone()
        return _field_public(row)
    cursor = conn.execute(
        "INSERT INTO field_definition "
        "(dataset_definition_id, field_key, original_name, data_type, "
        "is_nullable, identity_role, display_order) VALUES (?,?,?,?,?,?,?)",
        (
            dataset["dataset_definition_id"], request.field_key,
            request.original_name, request.data_type.value,
            int(request.is_nullable), request.identity_role.value,
            request.display_order,
        ),
    )
    row = conn.execute(
        "SELECT * FROM field_definition WHERE field_definition_id = ?",
        (cursor.lastrowid,),
    ).fetchone()
    return _field_public(row)


def list_fields(
    conn: sqlite3.Connection, dataset_id: int, *, after_id: int = 0,
    limit: int = DEFAULT_PAGE_SIZE,
) -> dict[str, Any]:
    limit = _page_limit(limit)
    dataset = _dataset_row(conn, dataset_id)
    rows = conn.execute(
        "SELECT * FROM field_definition WHERE dataset_definition_id = ? "
        "AND valid_to IS NULL AND field_definition_id > ? "
        "ORDER BY field_definition_id LIMIT ?",
        (dataset["dataset_definition_id"], max(0, after_id), limit + 1),
    ).fetchall()
    has_more = len(rows) > limit
    page = rows[:limit]
    return {
        "fields": [_field_public(row) for row in page],
        "next_after_id": page[-1]["field_definition_id"] if has_more else None,
    }
