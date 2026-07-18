"""Ingest: funnel payloads -> harvest.db (ENGINEERING.md A5, A7, Q3, F1, F2).

Runs ONLY on the owner's machine (A10). Reads reassembled payloads, applies the
manifest scope guard (gate 2 of 5), upserts the source-local rows, and APPENDS
price observations idempotently. Per-row failures are isolated and counted, never
silent (Q3); a whole source never dies on one bad row.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from decimal import Decimal

from .config import SourceEntry
from .normalize import parse_money, record_hash
from .payload import FunnelPayload
from .rowspec import RowView, spec_for
from .vocab import Availability, CurationStatus, ExtractKind, RunStatus


@dataclass
class IngestResult:
    source_key: str
    run_id: int
    products: int = 0            # newly-seen products this run
    variants: int = 0            # newly-seen variants this run
    observations: int = 0        # rows actually appended (new content)
    duplicates: int = 0          # idempotent no-ops (already had this content)
    skipped_ignored: int = 0     # rows under an owner-ignored product
    rejected_out_of_scope: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def status(self) -> RunStatus:
        if self.errors and self.observations == 0:
            return RunStatus.FAILED
        return RunStatus.PARTIAL if self.errors else RunStatus.SUCCESS


# ---- scope guard (gate 2): what a source is CONTRACTED to write --------------

def scope_reason(entry: SourceEntry, kind: ExtractKind, region: str,
                 material_key: str | None = None) -> str | None:
    """Return a rejection reason if this row is outside the source's contract,
    else None. `census` scope accepts the source's whole catalog."""
    specs = [s for s in entry.extract if s.kind == kind]
    if not specs:
        return f"kind {kind} is not contracted for {entry.source_key}"
    for spec in specs:
        if spec.scope.value == "census":
            return None
        region_ok = "*" in spec.regions or region in spec.regions
        material_ok = not spec.materials or (material_key in spec.materials)
        if region_ok and material_ok:
            return None
    return (f"row (region={region}, material={material_key}) is outside "
            f"{entry.source_key}'s contract")


# ---- tiny DRY upsert helpers -------------------------------------------------

def _find_id(conn: sqlite3.Connection, sql: str, params: tuple) -> int | None:
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row else None


def _insert(conn: sqlite3.Connection, table: str, values: dict) -> int:
    cols = ", ".join(values)
    marks = ", ".join("?" for _ in values)
    cur = conn.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(values.values()))
    return int(cur.lastrowid)


def _touch_last_seen(conn: sqlite3.Connection, table: str, id_col: str, row_id: int) -> None:
    conn.execute(
        f"UPDATE {table} SET last_seen_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE {id_col} = ?",
        (row_id,),
    )


# ---- entity resolution (get-or-create; each returns an explicit `created`) ---

def _get_source_id(conn, entry: SourceEntry, currency: str) -> int:
    found = _find_id(conn, "SELECT source_id FROM source_site WHERE source_key = ?", (entry.source_key,))
    if found is not None:
        return found
    return _insert(conn, "source_site", {
        "source_key": entry.source_key,
        "source_name": entry.source_name,
        "base_url": entry.base_url,
        "platform": entry.family.value,
        "currency": currency,
        "authority": entry.authority.value,
    })


def _get_product(conn, source_id: int, r: dict) -> tuple[int, str, bool]:
    """(source_product_id, curation_status, created). Upserts by the owner's
    UNIQUE(source_id, external_product_id)."""
    row = conn.execute(
        "SELECT source_product_id, curation_status FROM source_product "
        "WHERE source_id = ? AND external_product_id = ?",
        (source_id, r["external_product_id"]),
    ).fetchone()
    if row is not None:
        _touch_last_seen(conn, "source_product", "source_product_id", int(row[0]))
        return int(row[0]), row[1], False
    pid = _insert(conn, "source_product", {
        "source_id": source_id,
        "external_product_id": r["external_product_id"],
        "external_sku": r["external_sku"] or None,
        "source_name": r["product_name"] or None,
        "product_url": r["product_url"] or None,
        "brand_raw": r["brand_raw"] or None,
        "has_variants": 1 if r["external_variant_id"] or r["option_fingerprint"] else 0,
        "curation_status": CurationStatus.INVENTORIED.value,
    })
    return pid, CurationStatus.INVENTORIED.value, True


def _get_variant(conn, product_id: int, r: dict) -> tuple[int, bool]:
    """(source_variant_id, created). Keyed by external_variant_id when present,
    else by option_fingerprint (the owner's rule — never SKU alone)."""
    ext = r["external_variant_id"] or None
    fp = r["option_fingerprint"] or None
    if ext is not None:
        found = _find_id(
            conn,
            "SELECT source_variant_id FROM source_variant "
            "WHERE source_product_id = ? AND external_variant_id = ?",
            (product_id, ext),
        )
    else:
        found = _find_id(
            conn,
            "SELECT source_variant_id FROM source_variant "
            "WHERE source_product_id = ? AND external_variant_id IS NULL AND option_fingerprint IS ?",
            (product_id, fp),
        )
    if found is not None:
        _touch_last_seen(conn, "source_variant", "source_variant_id", found)
        return found, False
    return _insert(conn, "source_variant", {
        "source_product_id": product_id,
        "external_variant_id": ext,
        "external_sku": r["external_sku"] or None,
        "option_fingerprint": fp,
        "option_label": r["option_label"] or None,
    }), True


def _get_offer_id(conn, variant_id: int, r: dict) -> int:
    vat = 1 if r["vat_included"] == "1" else 0
    found = _find_id(
        conn,
        "SELECT offer_id FROM source_offer WHERE source_variant_id = ? AND branch_id IS NULL "
        "AND region = ? AND customer_segment = 'retail' AND selling_unit_id IS NULL AND basis_quantity = 1",
        (variant_id, r["region"]),
    )
    if found is not None:
        return found
    return _insert(conn, "source_offer", {
        "source_variant_id": variant_id,
        "region": r["region"],
        "currency": r["currency"],
        "vat_included": vat,
    })


# ---- price parsing (via the ONE shared parser, Q2) ---------------------------

def _to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _observation_values(r: dict, observed_at: str) -> dict:
    effective = parse_money(r["effective_price"])
    if effective is None:
        raise ValueError("effective_price is empty after parsing")
    regular = parse_money(r["regular_price"]) if r["regular_price"] else None
    sale = parse_money(r["sale_price"]) if r["sale_price"] else None
    vat = 1 if r["vat_included"] == "1" else 0
    availability = r["availability"] or Availability.UNKNOWN.value
    if availability not in {a.value for a in Availability}:
        availability = Availability.UNKNOWN.value
    stock_raw = r["stock_quantity"]
    stock = _to_float(parse_money(stock_raw)) if stock_raw else None
    content_hash = record_hash({
        "effective": str(effective), "regular": str(regular), "sale": str(sale),
        "currency": r["currency"], "vat": vat, "availability": availability, "stock": stock,
    })
    return {
        "observed_at": observed_at,
        "business_date": observed_at[:10],
        "regular_price": _to_float(regular),
        "sale_price": _to_float(sale),
        "effective_price": _to_float(effective),
        "currency": r["currency"],
        "vat_included": vat,
        "availability": availability,
        "stock_quantity": stock,
        "record_hash": content_hash,
    }


# ---- the pipeline ------------------------------------------------------------

def ingest_payloads(conn: sqlite3.Connection, entry: SourceEntry,
                    payloads: list[FunnelPayload]) -> IngestResult:
    """Ingest one source's payloads into harvest.db in a single transaction.

    All-or-nothing at the DB level (F1): the crawl_run and every row commit
    together, or nothing does. Per-row *data* problems are isolated into
    result.errors and do not abort the batch (Q3)."""
    source_id = _get_source_id(conn, entry, _first_currency(payloads))
    run_id = _insert(conn, "crawl_run", {
        "source_id": source_id,
        "status": RunStatus.RUNNING.value,
        "extractor_version": "phase1",
    })
    result = IngestResult(source_key=entry.source_key, run_id=run_id)

    for payload in payloads:
        if payload.source_key != entry.source_key:
            result.errors.append(f"payload source_key {payload.source_key} != {entry.source_key}")
            continue
        if payload.kind != ExtractKind.PRODUCT_PRICES:
            # Phase 1 ingests product_prices only; commodity/enrichment land later.
            result.errors.append(f"kind {payload.kind} not yet ingestable (Phase 1)")
            continue
        try:
            view = RowView(spec_for(payload.kind), payload.header)
        except ValueError as exc:  # header drift — whole payload unusable (Q4)
            result.errors.append(f"header drift: {exc}")
            continue
        for i, raw in enumerate(payload.rows):
            try:
                _ingest_product_row(conn, entry, source_id, run_id,
                                    view.as_dict(raw), payload.scraped_at, result)
            except Exception as exc:  # noqa: BLE001 — isolate one bad row (Q3)
                result.errors.append(f"row {i}: {exc}")

    conn.execute(
        "UPDATE crawl_run SET finished_at = strftime('%Y-%m-%dT%H:%M:%SZ','now'), "
        "status = ?, products_discovered = ?, variants_discovered = ?, errors_count = ? "
        "WHERE run_id = ?",
        (result.status.value, result.products, result.variants, len(result.errors), run_id),
    )
    return result


def _ingest_product_row(conn, entry, source_id, run_id, r, observed_at, result: IngestResult) -> None:
    reason = scope_reason(entry, ExtractKind.PRODUCT_PRICES, r["region"])
    if reason is not None:
        result.rejected_out_of_scope += 1
        result.errors.append(f"out of scope: {reason}")
        return

    product_id, curation, product_created = _get_product(conn, source_id, r)
    if curation == CurationStatus.IGNORED.value:
        result.skipped_ignored += 1
        return
    if product_created:
        result.products += 1

    variant_id, variant_created = _get_variant(conn, product_id, r)
    if variant_created:
        result.variants += 1

    offer_id = _get_offer_id(conn, variant_id, r)
    v = _observation_values(r, observed_at)
    cur = conn.execute(
        "INSERT OR IGNORE INTO price_observation "
        "(offer_id, observed_at, business_date, regular_price, sale_price, effective_price, "
        " currency, vat_included, availability, stock_quantity, run_id, record_hash) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (offer_id, v["observed_at"], v["business_date"], v["regular_price"], v["sale_price"],
         v["effective_price"], v["currency"], v["vat_included"], v["availability"],
         v["stock_quantity"], run_id, v["record_hash"]),
    )
    if cur.rowcount == 1:
        result.observations += 1
    else:
        result.duplicates += 1


def _first_currency(payloads: list[FunnelPayload]) -> str:
    """Best-effort site currency for source_site (offers carry their own)."""
    for payload in payloads:
        if "currency" not in payload.header:
            continue
        idx = payload.header.index("currency")
        for raw in payload.rows:
            if idx < len(raw) and raw[idx]:
                return raw[idx]
    return "UNKNOWN"
