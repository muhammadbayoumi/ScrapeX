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

from .changes import (
    ALIAS_FIELDS, classify_availability, classify_price, product_field_diffs,
    record_alias, record_change,
)
from .config import SourceEntry
from . import pricekey, tax
from .normalize import parse_money, record_hash
from .payload import FunnelPayload
from .rowspec import PRODUCT_PRICES, RowView, spec_for
from .vocab import Availability, ChangeType, CurationStatus, ExtractKind, RunStatus


@dataclass
class IngestResult:
    source_key: str
    run_id: int
    products: int = 0            # newly-seen products this run
    variants: int = 0            # newly-seen variants this run
    observations: int = 0        # rows actually appended (new content)
    duplicates: int = 0          # idempotent no-ops (already had this content)
    attributes: int = 0          # enrichment values landed or refreshed
    confirmed: int = 0           # unchanged prices re-confirmed, NOT appended
    # offer_id -> the latest values seen this run. The spec allows a run to hold
    # its seen set in memory while finalizing; these become confirmations only
    # if the run completes successfully, because a failed or partial run has not
    # established that anything is still true.
    seen: dict = field(default_factory=dict)
    # product_id -> the external variant ids THIS run published, for the
    # stand-in retirement sweep. Run bookkeeping, not result contract.
    _seen_variant_ids: dict = field(default_factory=dict, repr=False)
    skipped_ignored: int = 0     # rows under an owner-ignored product
    rejected_out_of_scope: int = 0
    # Two kinds of trouble, kept apart because they mean different things:
    #   errors    — row/payload-level failures: some of the DATA did not land,
    #               so the run genuinely is partial (or failed).
    #   contained — side-effect failures that were isolated by design (e.g. tax
    #               evidence not recorded). Every price landed; degrading the
    #               run for one of these used to gate the whole derived price
    #               layer off — 18 live offers ended up with observations but
    #               no offer_state and no price_period over a contained note.
    errors: list[str] = field(default_factory=list)
    contained: list[str] = field(default_factory=list)

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


# ---- F6 volume canary: did this crawl silently break? ------------------------

def canary_breach(entry: SourceEntry, rows: int, previous_rows: int | None = None) -> str | None:
    """Return a breach message, or None when the volume looks healthy.

    A connector whose selectors rot usually fails QUIETLY — it returns zero (or a
    handful of) rows and every downstream step reports success. The manifest
    declares the expected floor per source; this is where that declaration is
    finally enforced.
    """
    if rows == 0:
        return f"{entry.source_key}: zero rows returned (volume canary)"
    if entry.min_expected_rows is not None and rows < entry.min_expected_rows:
        return (f"{entry.source_key}: {rows} rows is below the declared minimum "
                f"{entry.min_expected_rows} (volume canary)")
    if entry.max_drop_pct is not None and previous_rows:
        drop_pct = (previous_rows - rows) / previous_rows * 100
        if drop_pct > entry.max_drop_pct:
            return (f"{entry.source_key}: {rows} rows is a {drop_pct:.0f}% drop from "
                    f"{previous_rows} (max {entry.max_drop_pct}%) (volume canary)")
    return None


def previous_rows_seen(conn: sqlite3.Connection, source_key: str) -> int | None:
    """rows_seen of the last run for this source that actually saw rows."""
    row = conn.execute(
        "SELECT r.rows_seen FROM crawl_run r JOIN source_site s ON s.source_id = r.source_id "
        "WHERE s.source_key = ? AND r.rows_seen > 0 ORDER BY r.run_id DESC LIMIT 1",
        (source_key,),
    ).fetchone()
    return int(row[0]) if row is not None else None


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


def _get_product(conn, source_id: int, r: dict, run_id: int | None = None,
                 job_id: int | None = None) -> tuple[int, str, bool]:
    """(source_product_id, curation_status, created). Upserts by the owner's
    UNIQUE(source_id, external_product_id).

    Also RECORDS and APPLIES changes to the tracked descriptive fields: before
    this, a product renamed at the source kept its first-seen name forever —
    the change was neither stored as history nor reflected in current state.
    """
    row = conn.execute(
        "SELECT source_product_id, curation_status, source_name, product_url, brand_raw, "
        "       external_sku, status, category_path, category_external_id, "
        "       source_name_en, name_lang, category_path_en "
        "FROM source_product WHERE source_id = ? AND external_product_id = ?",
        (source_id, r["external_product_id"]),
    ).fetchone()
    if row is not None:
        pid = int(row["source_product_id"])
        _touch_last_seen(conn, "source_product", "source_product_id", pid)
        if row["status"] != "active":
            # Seen again after vanishing (or after a rebuild archived it).
            conn.execute("UPDATE source_product SET status = 'active' WHERE source_product_id = ?",
                         (pid,))
            record_change(conn, ChangeType.RETURNED, "status", previous_value=row["status"],
                          new_value="active", source_product_id=pid, run_id=run_id, job_id=job_id)
        for column, old, new in product_field_diffs(dict(row), r):
            record_change(conn, ChangeType.FIELD_UPDATED, column, previous_value=old,
                          new_value=new, source_product_id=pid, run_id=run_id, job_id=job_id)
            if column in ALIAS_FIELDS and old:
                # Keep the superseded identity findable (spec 14).
                record_alias(conn, pid, ALIAS_FIELDS[column], old)
            # `column` comes from the fixed TRACKED_PRODUCT_FIELDS tuple, never input.
            conn.execute(f"UPDATE source_product SET {column} = ? WHERE source_product_id = ?",
                         (new, pid))
        return pid, row["curation_status"], False
    pid = _insert(conn, "source_product", {
        "source_id": source_id,
        "external_product_id": r["external_product_id"],
        "external_sku": r["external_sku"] or None,
        "source_name": r["product_name"] or None,
        "product_url": r["product_url"] or None,
        "brand_raw": r["brand_raw"] or None,
        # .get: the commodity spec has no classification columns, and old
        # payloads predate the contract widening that added them.
        "category_path": r.get("category_path") or "",
        "category_path_en": r.get("category_path_en") or "",
        "category_external_id": r.get("category_external_id") or "",
        "source_name_en": r.get("product_name_en") or "",
        "name_lang": r.get("lang") or "",
        "has_variants": 1 if r["external_variant_id"] or r["option_fingerprint"] else 0,
        "curation_status": CurationStatus.INVENTORIED.value,
    })
    record_change(conn, ChangeType.NEW, "source_product", source_product_id=pid,
                  new_value=r["product_name"] or r["external_product_id"],
                  run_id=run_id, job_id=job_id)
    return pid, CurationStatus.INVENTORIED.value, True


def _get_variant(conn, product_id: int, r: dict, run_id: int | None = None,
                 job_id: int | None = None) -> tuple[int, bool]:
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
        if r["option_label"]:
            # The label is the site's CURRENT wording for which variant this
            # is — when a connector learns to say it better (axis names came
            # 2026-07-23), the next crawl rewrites it. Identity never moves:
            # the fingerprint and external id stay untouched.
            conn.execute(
                "UPDATE source_variant SET option_label = ? "
                "WHERE source_variant_id = ? AND COALESCE(option_label,'') != ?",
                (r["option_label"], found, r["option_label"]))
        status = conn.execute(
            "SELECT status FROM source_variant WHERE source_variant_id = ?",
            (found,)).fetchone()[0]
        if status != "active":
            # The source publishes this variant again (the woo fallback path
            # re-emits the stand-in when every variation fetch fails) — it
            # returns to the table, and the return is an event, not a secret.
            conn.execute("UPDATE source_variant SET status = 'active' "
                         "WHERE source_variant_id = ?", (found,))
            record_change(conn, ChangeType.RETURNED, "variant_status",
                          previous_value=status, new_value="active",
                          source_product_id=product_id, source_variant_id=found,
                          run_id=run_id, job_id=job_id)
        return found, False
    return _insert(conn, "source_variant", {
        "source_product_id": product_id,
        "external_variant_id": ext,
        "external_sku": r["external_sku"] or None,
        "option_fingerprint": fp,
        "option_label": r["option_label"] or None,
    }), True


def _retire_product_level_stand_ins(conn, result: "IngestResult",
                                    run_id: int | None,
                                    job_id: int | None) -> None:
    """A product now publishing REAL variants retires its old stand-in.

    The stand-in is the row whose variant id IS the product id — the shape a
    connector emits when it cannot see variations, priced at whatever the
    listing showed (for WooCommerce: the price RANGE's low end). When a run
    publishes differently-identified variants for the product and no longer
    publishes the stand-in, the stand-in is superseded — otherwise the low
    end poses as a current offer forever beside the real prices.

    Scoped hard on purpose: only products THIS run touched, only the exact
    stand-in id, and never when the run still publishes it (the fallback
    path) — a partial crawl retires nothing it did not positively replace.
    """
    for product_id, seen in result._seen_variant_ids.items():
        ext = conn.execute(
            "SELECT external_product_id FROM source_product "
            "WHERE source_product_id = ?", (product_id,)).fetchone()[0]
        if ext in seen or not any(v and v != ext for v in seen):
            continue
        stale = conn.execute(
            "SELECT source_variant_id FROM source_variant "
            "WHERE source_product_id = ? AND external_variant_id = ? "
            "AND status = 'active'", (product_id, ext)).fetchone()
        if stale is None:
            continue
        conn.execute("UPDATE source_variant SET status = 'superseded' "
                     "WHERE source_variant_id = ?", (stale[0],))
        record_change(conn, ChangeType.REMOVED, "variant_status",
                      previous_value="product-level stand-in (range low end)",
                      new_value="superseded by per-variation prices",
                      source_product_id=product_id, source_variant_id=stale[0],
                      run_id=run_id, job_id=job_id)


def canonical_unit(raw: str, currency: str = "") -> str:
    """The unit a price is per, as a stable code — or "" when none was supplied.

    Two jobs, both narrow on purpose:

    1. Drop a currency prefix. globalpetrolprices reports 'USD/liter', but the
       currency already has its own column, so storing it inside the unit too
       would make 'USD/liter' and 'EGP/liter' two different units for the same
       physical litre.
    2. Fold the obvious spellings of the same unit together, so 'meters', 'Metre'
       and 'm' do not become three units and split one price series in three.

    Anything unrecognised is kept, lowercased and trimmed. Guessing further
    would silently merge units that a site means differently, and a wrong merge
    is far worse than an extra row in a lookup table.
    """
    text = (raw or "").strip()
    if not text:
        return ""
    if "/" in text:
        head, _, tail = text.partition("/")
        # Only strip the head when it really is the currency, so a genuine
        # compound unit like 'kg/m2' survives untouched.
        if head.strip().upper() == (currency or "").strip().upper() or head.strip().isupper():
            text = tail
    key = text.strip().lower().rstrip(".")
    return _UNIT_ALIASES.get(key, key)


_UNIT_ALIASES = {
    "meter": "m", "meters": "m", "metre": "m", "metres": "m", "mtr": "m",
    "kilogram": "kg", "kilograms": "kg", "kilo": "kg", "kgs": "kg",
    "litre": "liter", "litres": "liter", "liters": "liter", "l": "liter",
    "ton": "tonne", "tons": "tonne", "tonnes": "tonne", "metric ton": "tonne",
    "square meter": "m2", "square metre": "m2", "sqm": "m2", "m²": "m2",
    "cubic meter": "m3", "cubic metre": "m3", "cbm": "m3", "m³": "m3",
    "pieces": "piece", "pcs": "piece", "pc": "piece", "each": "piece",
    "kwh": "kWh", "kw/h": "kWh",
    # Arabic spellings, from live sources. samehgabriel sells cable by the roll
    # and states the basis as an Arabic attribute — "100 متر" — which is the
    # unit information, not a product detail (owner's correction).
    "متر": "m", "امتار": "m", "أمتار": "m",
    "كيلوجرام": "kg", "كجم": "kg", "كيلو": "kg",
    "لتر": "liter", "قطعة": "piece", "حبة": "piece",
}


def _get_unit_id(conn: sqlite3.Connection, unit_code: str) -> int | None:
    """Resolve-or-create. Units arrive from sites, so they cannot all be seeded."""
    if not unit_code:
        return None
    found = _find_id(conn, "SELECT selling_unit_id FROM selling_unit WHERE unit_code = ?",
                     (unit_code,))
    if found is not None:
        return found
    return _insert(conn, "selling_unit", {"unit_code": unit_code})


def _unit_with_basis(r: dict) -> str:
    """'m' for a per-metre price, '100 m' for a 100-metre roll.

    The quantity belongs with the unit in the price key: a 100 m roll at 500 and
    a 1 m offcut at 500 are not the same price, and comparing them as if they
    were is the failure this whole field exists to prevent.
    """
    unit = canonical_unit(r.get("unit", ""), r.get("currency", ""))
    if not unit:
        return ""
    basis = _basis_quantity(r.get("basis_quantity", ""))
    if basis == 1.0:
        return unit
    quantity = int(basis) if float(basis).is_integer() else basis
    return f"{quantity} {unit}"


def _basis_quantity(raw: str) -> float:
    """How many units one offer buys. Anything unusable stays 1 — the default
    the schema already assumes, never a guess at what the site meant."""
    try:
        value = float(str(raw).strip())
    except (TypeError, ValueError):
        return 1.0
    return value if value > 0 else 1.0


def _get_offer_id(conn, variant_id: int, r: dict) -> int:
    vat = 1 if r["vat_included"] == "1" else 0
    unit_id = _get_unit_id(conn, canonical_unit(r.get("unit", ""), r.get("currency", "")))
    basis = _basis_quantity(r.get("basis_quantity", ""))
    # The unit is part of what an offer IS: 15 per litre and 15 per gallon are
    # different offers, not one offer that changed price. The lookup used to pin
    # selling_unit_id IS NULL, which made every offer unit-less by construction
    # and made those two indistinguishable in the warehouse.
    found = _find_id(
        conn,
        "SELECT offer_id FROM source_offer WHERE source_variant_id = ? AND branch_id IS NULL "
        "AND region = ? AND customer_segment = 'retail' "
        "AND COALESCE(selling_unit_id,0) = ? AND basis_quantity = ?",
        (variant_id, r["region"], unit_id or 0, basis),
    )
    if found is not None:
        return found
    return _insert(conn, "source_offer", {
        "source_variant_id": variant_id,
        "region": r["region"],
        "currency": r["currency"],
        "vat_included": vat,
        "selling_unit_id": unit_id,
        "basis_quantity": basis,
    })


# ---- price parsing (via the ONE shared parser, Q2) ---------------------------

def _to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _canon_amount(value: Decimal | None) -> str:
    """Scale-invariant canonical string for hashing.

    A source that renders '0.620' one week and '0.62' the next is quoting the SAME
    price; str(Decimal) preserves the scale, so hashing it would mint a second
    record_hash and defeat ux_price_obs_dedupe — appending a phantom 'price change'
    to an append-only table. normalize() strips the trailing zeros first.

    Deliberately returns a STRING: the cross-engine contract rule is that
    record_hash only ever receives canonical strings, never language-native floats
    (Python repr 15.0 vs JS 15 was the original parity landmine).
    """
    if value is None:
        return ""
    return format(value.normalize(), "f")


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
    stock_dec = parse_money(stock_raw) if stock_raw else None
    stock = _to_float(stock_dec)
    # record_hash keeps its original composition — it is the dedupe key on
    # ux_price_obs_dedupe and part of the frozen cross-engine contract, so
    # changing it would silently re-key every existing warehouse.
    content_hash = record_hash({
        "effective": _canon_amount(effective), "regular": _canon_amount(regular),
        "sale": _canon_amount(sale), "currency": r["currency"], "vat": vat,
        "availability": availability, "stock": _canon_amount(stock_dec),
    })
    # price_hash answers a different question: is this the SAME PRICE? It leaves
    # availability and stock out — the owner wants the latest stock state, not
    # its history, and a stock movement must never read as a price change.
    price_key = pricekey.build(
        effective=_canon_amount(effective), regular=_canon_amount(regular),
        sale=_canon_amount(sale), currency=r["currency"], vat=vat,
        region=r.get("region", ""),
        # The real unit, canonicalised the same way the offer identity does it,
        # so the two can never disagree about what a price is per. This slot
        # used to hold option_label, which is the selling unit for commodity
        # rows but a variant TITLE ("Red / Large") for products — so the
        # promise that 15/litre and 15/gallon are different series held for
        # fuel and quietly did not hold for anything else.
        unit=_unit_with_basis(r),
        brand=r.get("brand_raw", ""),
        # Not collected by any connector yet. Named here so a connector that
        # starts supplying them needs no schema change, and so their arrival is
        # a field-set widening rather than a warehouse-wide price change.
        origin=r.get("country_of_origin", ""),
        spec=r.get("spec_summary", ""),
    )
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
        "price_hash": price_key.digest,
        "price_fields": price_key.field_list,
    }


# ---- the pipeline ------------------------------------------------------------

def ingest_payloads(conn: sqlite3.Connection, entry: SourceEntry,
                    payloads: list[FunnelPayload], job_id: int | None = None) -> IngestResult:
    """Ingest one source's payloads into harvest.db in a single transaction.

    All-or-nothing at the DB level (F1): the crawl_run and every row commit
    together, or nothing does. Per-row *data* problems are isolated into
    result.errors and do not abort the batch (Q3)."""
    from .contract import assert_writable
    assert_writable(conn)  # two-engine guardrail: never write across contract versions
    source_id = _get_source_id(conn, entry, _first_currency(payloads))
    # The manifest's tax evidence is recorded before any price is written, so a
    # price can never be stored under a tax position the warehouse cannot state.
    # Failing to record evidence must not lose a crawl, so it is contained: the
    # prices are the irreplaceable part, and an unrecorded rule reads as
    # unverified, which is honest.
    try:
        tax.upsert_rules(conn, entry)
    except sqlite3.DatabaseError as exc:
        result_note = f"tax evidence not recorded: {exc}"
    else:
        result_note = ""
    run_id = _insert(conn, "crawl_run", {
        "source_id": source_id,
        "status": RunStatus.RUNNING.value,
        "extractor_version": "phase1",
        "job_id": job_id,
    })
    result = IngestResult(source_key=entry.source_key, run_id=run_id)
    if result_note:
        result.contained.append(result_note)

    # Prices before enrichment, whatever order the payloads ARRIVE in: a detail
    # can only attach to a product the run has registered, and the local inbox
    # reads files in filename order — which put the enrichment payload first
    # and sent all 270 of samehgabriel's details out-of-scope on a fresh
    # warehouse. The dependency is the ingester's to enforce, not the caller's
    # to remember.
    payloads = sorted(payloads,
                      key=lambda pl: 1 if pl.kind == ExtractKind.ENRICHMENT else 0)
    for payload in payloads:
        if payload.source_key != entry.source_key:
            result.errors.append(f"payload source_key {payload.source_key} != {entry.source_key}")
            continue
        if payload.kind not in (ExtractKind.PRODUCT_PRICES, ExtractKind.COMMODITY_PRICE,
                                ExtractKind.ENRICHMENT):
            result.errors.append(f"kind {payload.kind} not ingestable")
            continue
        if payload.kind == ExtractKind.ENRICHMENT and not any(
                spec.kind == ExtractKind.ENRICHMENT for spec in entry.extract):
            # The scope guard, same rule as everything else: nothing lands that
            # the manifest did not declare (owner principle: له أساس).
            result.errors.append(
                f"{entry.source_key} does not declare enrichment; payload refused")
            continue
        try:
            view = RowView(spec_for(payload.kind), payload.header)
        except ValueError as exc:  # header drift — whole payload unusable (Q4)
            result.errors.append(f"header drift: {exc}")
            continue
        row_fn = (_ingest_commodity_row if payload.kind == ExtractKind.COMMODITY_PRICE
                  else _ingest_enrichment_row if payload.kind == ExtractKind.ENRICHMENT
                  else _ingest_product_row)
        for i, raw in enumerate(payload.rows):
            try:
                row_fn(conn, entry, source_id, run_id,
                       view.as_dict(raw), payload.scraped_at, result, job_id)
            except Exception as exc:  # noqa: BLE001 — isolate one bad row (Q3)
                result.errors.append(f"row {i}: {exc}")

    # Stand-ins are retired before the derive: a run that just published a
    # product's real variants must not leave the range low end posing as a
    # current offer beside them.
    _retire_product_level_stand_ins(conn, result, run_id, job_id)
    # The derived layers are rebuilt for EVERY offer the run touched, whatever
    # the run's status ends up being: the observations are already appended, and
    # leaving them underived strands them where timeline() cannot see them.
    _derive_seen(conn, result)
    # Only a run that completed may claim it confirmed anything.
    if result.status is RunStatus.SUCCESS:
        _confirm_seen(conn, result)

    conn.execute(
        "UPDATE crawl_run SET finished_at = strftime('%Y-%m-%dT%H:%M:%SZ','now'), "
        "status = ?, products_discovered = ?, variants_discovered = ?, errors_count = ?, "
        "rows_seen = ? WHERE run_id = ?",
        (result.status.value, result.products, result.variants,
         len(result.errors) + len(result.contained),
         sum(len(p.rows) for p in payloads), run_id),
    )
    return result


def _ingest_enrichment_row(conn, entry, source_id, run_id, r, observed_at,
                           result: IngestResult, job_id=None) -> None:
    """Land one detail exactly as the shop printed it (source-local layer).

    The connector has emitted these since 2026-07-20 and this function's
    absence made ingest refuse every one — "not yet ingestable (Phase 1)" —
    so colours, lengths and warranties that arrived free in the price
    response were thrown away, and (since completed_with_errors landed)
    degraded a healthy job while doing it.

    UPSERT on (product, code, value): a re-crawl refreshes last_seen_at, a
    value the shop removed simply stops being refreshed. Nothing is deleted.
    """
    row = conn.execute(
        "SELECT source_product_id FROM source_product "
        "WHERE source_id = ? AND external_product_id = ?",
        (source_id, r["external_product_id"])).fetchone()
    if row is None:
        # A detail for a product this run never registered says nothing that
        # can be attached to anything; refuse it rather than minting a ghost.
        result.rejected_out_of_scope += 1
        return
    conn.execute(
        "INSERT INTO source_product_attribute "
        "(source_product_id, attribute_code, attribute_label, raw_value, "
        " numeric_value, unit_raw, value_url, attribute_group, lang) "
        "VALUES (?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(source_product_id, attribute_code, raw_value) DO UPDATE SET "
        "  attribute_label = excluded.attribute_label, "
        "  numeric_value = excluded.numeric_value, "
        "  unit_raw = excluded.unit_raw, "
        "  value_url = excluded.value_url, "
        "  attribute_group = excluded.attribute_group, "
        "  last_seen_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')",
        (row[0], r["attribute_code"], r.get("attribute_label", ""),
         r["raw_value"], r.get("numeric_value", ""), r.get("unit_raw", ""),
         r.get("value_url", ""), r.get("attribute_group", ""), r.get("lang", "")))
    result.attributes += 1


def _ingest_product_row(conn, entry, source_id, run_id, r, observed_at,
                        result: IngestResult, job_id: int | None = None) -> None:
    reason = scope_reason(entry, ExtractKind.PRODUCT_PRICES, r["region"])
    if reason is not None:
        result.rejected_out_of_scope += 1
        result.errors.append(f"out of scope: {reason}")
        return
    _persist_row(conn, source_id, run_id, r, observed_at, result, job_id)


def _ingest_commodity_row(conn, entry, source_id, run_id, c, observed_at,
                          result: IngestResult, job_id: int | None = None) -> None:
    """A commodity is a degenerate product (the material is the product, one
    implicit NULL/NULL variant, region on the offer): scope-check on material+region,
    then reuse the exact same persistence chain via the row-shape adapter."""
    reason = scope_reason(entry, ExtractKind.COMMODITY_PRICE, c["region"], c["material_key"])
    if reason is not None:
        result.rejected_out_of_scope += 1
        result.errors.append(f"out of scope: {reason}")
        return
    _record_implied_rate(conn, entry, c)
    _persist_row(conn, source_id, run_id, _commodity_to_product_row(c), observed_at,
                 result, job_id)


def _record_implied_rate(conn, entry, c: dict) -> None:
    """The exchange rate the PUBLISHER used, read off the row's own pair.

    A row carrying the local price and the site's printed USD conversion
    implies the rate between them — Egypt's 20.50 EGP beside 0.40 USD says
    1 USD = 51.25 EGP, in the site's own arithmetic. Recorded per (currency,
    day, source) so the Data page can rank 128 currencies in one USD column;
    never asserted where the pair is absent, and never for a USD row (a rate
    of 1 is noise). Isolated: a malformed pair must not cost the price row.
    """
    try:
        currency = (c.get("currency") or "").upper()
        local = float(c.get("original_price") or 0)
        usd = float(c.get("converted_usd_price") or 0)
        if not currency or currency == "USD" or local <= 0 or usd <= 0:
            return
        from datetime import date as _date
        as_of = (c.get("source_date") or "").strip() or _date.today().isoformat()
        conn.execute(
            "INSERT INTO currency_rate (currency, per_usd, as_of, source_key) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(currency, as_of, source_key) DO UPDATE SET "
            "  per_usd = excluded.per_usd",
            (currency, local / usd, as_of, entry.source_key))
    except (ValueError, TypeError, sqlite3.DatabaseError):
        pass


def _commodity_to_product_row(c: dict) -> dict:
    """Adapt a COMMODITY_PRICE row into the product-row shape _persist_row expects.

    `unit` ('USD/liter') goes to the row's `unit` column and nowhere else. It
    used to be stuffed into option_label because that was the only field the
    warehouse stored; now that ingest resolves selling_unit_id, option_label is
    free to mean what it says — a variant title — and a unit is no longer
    indistinguishable from "Red / Large".

    `observed_label` is deliberately DROPPED: it has no schema column and must
    never drive business_date/record_hash (owner rule: the history is OUR own
    weekly observations, stamped with our crawl date, not the publisher's dating).

    Built from the spec's own column list, so a widened contract cannot leave
    the adapter silently behind it.
    """
    row = {col: "" for col in PRODUCT_PRICES.columns}
    row.update({
        "external_product_id": c["material_key"],
        "product_name": c["material_key"],
        "region": c["region"],
        "currency": c["currency"],
        "vat_included": c.get("vat_included", ""),
        "effective_price": c["effective_price"],
        "unit": c.get("unit", ""),
        # A row the SOURCE dates versus a row WE date. These used to be dropped
        # here, which stamped every reported history anchor with the crawl date:
        # three "months ago" prices all landing as today, colliding with the
        # current price and with each other. They travel so _persist_row can put
        # reported rows on their own path.
        "provenance": c.get("provenance", ""),
        "as_of_date": c.get("as_of_date", ""),
        # Who states this figure, per the page it came from. Optional — a page
        # that names no source stays empty rather than being invented.
        "official_source_name": c.get("official_source_name", ""),
        "official_source_url": c.get("official_source_url", ""),
    })
    return row


def _still_the_same_price(conn: sqlite3.Connection, offer_id: int, v: dict) -> bool:
    """Does the open period already hold this exact price key?

    Only an OPEN period counts: a closed one describes a price that has already
    been superseded, and matching it would resurrect history rather than confirm
    the present. Two keys built from different field sets are never the same
    price — the source is publishing more (or less), which is a new period with
    its own reason, not a confirmation.
    """
    if not v.get("price_hash"):
        return False                    # no key, no claim
    open_period = conn.execute(
        "SELECT price_hash, price_fields FROM price_period "
        "WHERE offer_id = ? AND closed_at IS NULL LIMIT 1", (offer_id,)).fetchone()
    if open_period is None or not open_period["price_hash"]:
        return False
    if open_period["price_hash"] != v["price_hash"]:
        return False
    return pricekey.comparable(pricekey.parse_fields(open_period["price_fields"]),
                               pricekey.parse_fields(v["price_fields"]))


def _derive_seen(conn: sqlite3.Connection, result: IngestResult) -> None:
    """Rebuild the derived price layers for every offer this run touched.

    UNCONDITIONAL — this runs whatever the run's status is. The derivation is
    pure and idempotent (see rebuild_offer): it only reads observations that are
    already appended, so a partial run derives exactly what it managed to land.
    Gating it on SUCCESS was the incident: one contained error left every offer
    of a run with an appended observation but no offer_state and no
    price_period — and because ux_price_obs_dedupe blocks a same-day re-append,
    re-running the crawl appended nothing and never repaired it.
    """
    from . import pricehistory

    for offer_id in result.seen:
        pricehistory.rebuild_offer(conn, offer_id)


def _confirm_seen(conn: sqlite3.Connection, result: IngestResult) -> None:
    """Advance what a SUCCESSFUL run proved, and nothing more.

    The spec is explicit that a failed, partial or cancelled run must not advance
    last_confirmed_at: not seeing something proves nothing when the run did not
    finish. So confirmations are held in memory during the run and applied only
    here, once the run's own status says they are earned. The periods themselves
    are already rebuilt by _derive_seen — this only stamps the confirmations.
    """
    for offer_id, v in result.seen.items():
        conn.execute(
            "UPDATE price_period SET last_confirmed_at = ? "
            "WHERE offer_id = ? AND closed_at IS NULL", (v["observed_at"], offer_id))
        # Availability and stock are current state only — the owner asked for the
        # latest situation, never its history — so they land here and nowhere else.
        conn.execute(
            "UPDATE offer_state SET availability = ?, stock_quantity = ?, "
            " last_confirmed_at = ?, last_seen_at = ?, "
            " updated_at = strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE offer_id = ?",
            (v["availability"], v["stock_quantity"], v["observed_at"],
             v["observed_at"], offer_id))


def _persist_row(conn, source_id, run_id, r, observed_at, result: IngestResult,
                 job_id: int | None = None) -> None:
    """Get-or-create the source_product -> variant -> offer chain and append one
    price_observation (idempotent). Shared by product + commodity ingest — the
    caller has already applied the kind-specific scope check."""
    product_id, curation, product_created = _get_product(conn, source_id, r, run_id, job_id)
    if curation == CurationStatus.IGNORED.value:
        result.skipped_ignored += 1
        return
    if product_created:
        result.products += 1

    variant_id, variant_created = _get_variant(conn, product_id, r, run_id, job_id)
    result._seen_variant_ids.setdefault(product_id, set()).add(
        r["external_variant_id"] or "")
    if variant_created:
        result.variants += 1
        record_change(conn, ChangeType.NEW, "source_variant", source_product_id=product_id,
                      source_variant_id=variant_id, new_value=r["option_label"] or None,
                      run_id=run_id, job_id=job_id)

    offer_id = _get_offer_id(conn, variant_id, r)
    v = _observation_values(r, observed_at)

    # A REPORTED row is the source's own statement about an earlier date — not
    # something we watched. It takes a separate, quieter path:
    #   - business_date is the date the source says the price held, which is the
    #     row's whole meaning;
    #   - it is not a confirmation of today's open period, does not mark the
    #     offer as seen (it says nothing about the site today), and NEVER feeds
    #     change detection — a backfilled 2016 price arriving after today's row
    #     would otherwise be read as a price change that happened this morning.
    if r.get("provenance") == "reported":
        if not r.get("as_of_date"):
            # A dated claim with no date is no claim at all.
            result.rejected_out_of_scope += 1
            return
        cur = conn.execute(
            "INSERT OR IGNORE INTO price_observation "
            "(offer_id, observed_at, business_date, regular_price, sale_price, "
            " effective_price, currency, vat_included, availability, stock_quantity, "
            " run_id, record_hash, price_hash, price_fields, provenance, "
            " official_source_name, official_source_url) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'reported',?,?)",
            (offer_id, v["observed_at"], r["as_of_date"], v["regular_price"],
             v["sale_price"], v["effective_price"], v["currency"], v["vat_included"],
             v["availability"], v["stock_quantity"], run_id, v["record_hash"],
             v["price_hash"], v["price_fields"],
             r.get("official_source_name", ""), r.get("official_source_url", "")),
        )
        if cur.rowcount == 1:
            result.observations += 1
        else:
            result.duplicates += 1
        return

    # Every row seen is a candidate confirmation, appended or not.
    result.seen[offer_id] = v

    # The price history is a timeline of real changes, not a daily copy of an
    # unchanged row. If the open period already holds this exact price key, the
    # refresh CONFIRMS it; appending would add a row that says nothing new.
    if _still_the_same_price(conn, offer_id, v):
        result.confirmed += 1
        return

    # Read the prior state BEFORE appending — same tiebreak as the publish path.
    # Observed rows only: the freshest row by insertion order may be a REPORTED
    # backfill whose business_date is years old, and comparing today's price
    # against a 2016 anchor would record a change nobody's price ever made.
    previous = conn.execute(
        "SELECT effective_price, availability, currency FROM price_observation "
        "WHERE offer_id = ? AND provenance = 'observed' "
        "ORDER BY observed_at DESC, price_observation_id DESC LIMIT 1", (offer_id,)
    ).fetchone()
    cur = conn.execute(
        "INSERT OR IGNORE INTO price_observation "
        "(offer_id, observed_at, business_date, regular_price, sale_price, effective_price, "
        " currency, vat_included, availability, stock_quantity, run_id, record_hash, "
        "price_hash, price_fields, provenance, official_source_name, official_source_url) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'observed',?,?)",
        (offer_id, v["observed_at"], v["business_date"], v["regular_price"], v["sale_price"],
         v["effective_price"], v["currency"], v["vat_included"], v["availability"],
         v["stock_quantity"], run_id, v["record_hash"],
         v["price_hash"], v["price_fields"],
         r.get("official_source_name", ""), r.get("official_source_url", "")),
    )
    if cur.rowcount == 1:
        result.observations += 1
        if previous is not None:  # no previous state = the 'new' event already said it
            ids = {"source_product_id": product_id, "source_variant_id": variant_id,
                   "offer_id": offer_id, "run_id": run_id, "job_id": job_id}
            if (previous["currency"] and v["currency"]
                    and previous["currency"] != v["currency"]):
                # A currency flip is NOT a price move: 20.50 EGP after 0.40 USD
                # would go into the change feed as a −98% crash when nobody's
                # price changed. The numbers are incomparable, so the flip
                # itself is the event — recorded with both values, never
                # dressed as a price movement (the guard behind the
                # currency-in-price-key rule).
                record_change(conn, ChangeType.FIELD_UPDATED, "currency",
                              previous_value=previous["currency"],
                              new_value=v["currency"], **ids)
            else:
                moved = classify_price(previous["effective_price"], v["effective_price"])
                if moved is not None:
                    record_change(conn, moved, "effective_price",
                                  previous_value=previous["effective_price"],
                                  new_value=v["effective_price"], **ids)
            stock_moved = classify_availability(previous["availability"], v["availability"])
            if stock_moved is not None:
                record_change(conn, stock_moved, "availability",
                              previous_value=previous["availability"],
                              new_value=v["availability"], **ids)
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
