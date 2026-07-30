"""Ingest: funnel payloads -> harvest.db (ENGINEERING.md A5, A7, Q3, F1, F2).

Runs ONLY on the owner's machine (A10). Reads reassembled payloads, applies the
manifest scope guard (gate 2 of 5), upserts the source-local rows, and APPENDS
price observations idempotently. Per-row failures are isolated and counted, never
silent (Q3); a whole source never dies on one bad row.
"""
from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from functools import partial
from dataclasses import dataclass, field
from decimal import Decimal

from .changes import (
    ALIAS_FIELDS, TRACKED_PRODUCT_FIELDS, classify_availability, classify_price,
    product_field_diffs, record_alias, record_change,
)
from .config import SourceEntry
from . import db as _dbmod, pricekey, tax
from .normalize import brand_pair, joined_brand, parse_money, record_hash
from .payload import FunnelPayload, utc_now_iso
from .rowspec import PRODUCT_PRICES, RowView, spec_for
from .vocab import (Availability, ChangeType, CurationStatus, DetailGroup,
                    ExtractKind, RunStatus)


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
    #   notices   — a NORMAL outcome worth saying out loud. Nothing failed and
    #               nothing was contained: the run did something routine that
    #               the owner should be able to see. These degrade nothing.
    #
    # The third channel exists because the retirement sweep had nowhere else to
    # speak. Its message went into `errors`, and `status` reads `errors`, so a
    # healthy crawl that tidied one stale detail value was reported PARTIAL —
    # or FAILED, on the normal refresh where no price moved and so nothing was
    # appended. _confirm_seen only runs for a SUCCESS, so that run also
    # confirmed no prices at all: on 2026-07-28 run 38 crawled 15,848 madar
    # rows, was shown as failed, and left last_confirmed_at stuck 1h45m behind.
    errors: list[str] = field(default_factory=list)
    contained: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)

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


def last_successful_run(conn: sqlite3.Connection, source_key: str) -> dict | None:
    """The last run of this source that SUCCEEDED, and what it measured.

    Two very different screens need exactly this row and neither may grow its
    own copy of the query: the Activity panel takes `requests_count` as the
    denominator its progress bar states, and the Data page shows when the data
    on screen was last actually gathered. One reader, so the two can never
    disagree about which run was the last good one.

    'Succeeded' means status='success' — never 'partial', because a run that
    lost half a catalogue is not a measurement of the catalogue, and using it
    as an expectation would quietly halve the bar's denominator.

    None means it has never succeeded (or never ran). That is a real answer and
    both callers must say so rather than substituting a zero: a bar against 0 is
    the 0% the owner has been staring at, and "last crawled: never" is the fact
    the Data page is missing.
    """
    row = conn.execute(
        "SELECT r.started_at, r.finished_at, r.rows_seen, r.requests_count, "
        "       r.products_discovered, r.errors_count "
        "FROM crawl_run r JOIN source_site s ON s.source_id = r.source_id "
        "WHERE s.source_key = ? AND r.status = 'success' "
        "ORDER BY r.run_id DESC LIMIT 1",
        (source_key,),
    ).fetchone()
    if row is None:
        return None
    return {"started_at": row[0], "finished_at": row[1], "rows_seen": int(row[2] or 0),
            # 0 means "this run predates requests_count ever being written"
            # (see ingest_payloads) — an absence, not a measurement of zero.
            "requests_count": int(row[3] or 0),
            "products_discovered": int(row[4] or 0), "errors_count": int(row[5] or 0)}


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


def _product_sku(r) -> str:
    """The PRODUCT's own sku: the parent's where there is one, else the row's.

    A variable product's row carries the VARIATION's sku (76ec8c8572f0-1), so
    writing that onto the product left it wearing whichever variation landed
    last. A product with no variations has no parent_sku and its own sku IS the
    row's — so this is a fallback, not a replacement.
    """
    return str(r.get("parent_sku") or r.get("external_sku") or "")


# The one tracked field whose value is DERIVED here rather than carried by a
# row: `product_sku` is the parent's sku or the row's own (_product_sku above).
_DERIVED_DIFF_KEYS = frozenset({"product_sku"})

# Every OTHER row key product_field_diffs reads, taken FROM the tracked list
# instead of hand-listed beside it.
#
# This narrowed dict is the diff's only input, so a key absent here is a field
# that is tracked and can never change — silently, because nothing raises and
# the column simply stays as it was. That is exactly how 0056 shipped:
# display_method was added to TRACKED_PRODUCT_FIELDS *specifically* so the 763
# MADAR products that already existed could learn it (only the INSERT path
# writes it, and they were inserted days earlier), and the hand-written tuple
# here was not extended with it — so three successful `update` crawls diffed a
# dict that had no display_method key, produced no diff, and wrote nothing.
# Deriving the keys means the two lists cannot drift apart again: adding a pair
# to TRACKED_PRODUCT_FIELDS is now the whole change.
_DIFF_ROW_KEYS = tuple(row_key for _, row_key in TRACKED_PRODUCT_FIELDS
                       if row_key not in _DERIVED_DIFF_KEYS)


def _with_product_sku(r) -> dict:
    """The row plus the derived product sku, for the field-diff comparison."""
    incoming = {key: r.get(key) for key in _DIFF_ROW_KEYS}
    incoming["product_sku"] = _product_sku(r)
    return incoming


# ---- entity resolution (get-or-create; each returns an explicit `created`) ---

def _get_source_id(conn, entry: SourceEntry, currency: str) -> int:
    row = conn.execute(
        "SELECT source_id, source_name FROM source_site WHERE source_key = ?",
        (entry.source_key,)).fetchone()
    if row is not None:
        source_id = int(row[0])
        # A registered source keeps whatever it was first stored with — that is
        # why this row is not re-written wholesale. The English name is the one
        # exception, and it has to be: it arrived with 0035, so every source we
        # already crawl carries '' until the manifest value is copied over, and
        # the listings would stay Arabic-only for exactly the sites with data.
        # Narrow on purpose — only the column the manifest just answered for.
        if (row[1] or "") != entry.source_name:
            conn.execute("UPDATE source_site SET source_name = ? WHERE source_id = ?",
                         (entry.source_name, source_id))
        return source_id
    return _insert(conn, "source_site", {
        "source_key": entry.source_key,
        "source_name_ar": entry.source_name_ar,
        "source_name": entry.source_name,
        "base_url": entry.base_url,
        "platform": entry.family.value,
        "currency": currency,
        "authority": entry.authority.value,
    })


def _get_product(conn, source_id: int, r: dict, run_id: int | None = None,
                 job_id: int | None = None) -> tuple[int, str, bool]:
    """(source_product_id, curation, created). Upserts by the owner's
    UNIQUE(source_id, external_product_id).

    Also RECORDS and APPLIES changes to the tracked descriptive fields: before
    this, a product renamed at the source kept its first-seen name forever —
    the change was neither stored as history nor reflected in current state.
    """
    row = conn.execute(
        "SELECT source_product_id, curation, product_name_ar, product_link, brand, brand_ar, "
        "       external_sku, status, category_path_ar, category_external_id, "
        "       product_name, product_name_lang, category_path, display_method "
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
        for column, old, new in product_field_diffs(dict(row), _with_product_sku(r)):
            record_change(conn, ChangeType.FIELD_UPDATED, column, previous_value=old,
                          new_value=new, source_product_id=pid, run_id=run_id, job_id=job_id)
            if column in ALIAS_FIELDS and old:
                # Keep the superseded identity findable (spec 14).
                record_alias(conn, pid, ALIAS_FIELDS[column], old)
            # `column` comes from the fixed TRACKED_PRODUCT_FIELDS tuple, never input.
            conn.execute(f"UPDATE source_product SET {column} = ? WHERE source_product_id = ?",
                         (new, pid))
        return pid, row["curation"], False
    pid = _insert(conn, "source_product", {
        "source_id": source_id,
        "external_product_id": r["external_product_id"],
        # The PRODUCT's own sku when the source publishes one (0037). This used
        # to take the row's external_sku, which on a variable product is the
        # VARIATION's — so the product ended up wearing whichever variation was
        # written last (76ec8c8572f0-6 instead of 76ec8c8572f0).
        "external_sku": _product_sku(r) or None,
        "parent_sku": r.get("parent_sku") or "",
        "product_name_ar": r.get("product_name_ar") or None,
        "product_link": r["product_link"] or None,
        "brand": r["brand"] or None,
        "brand_ar": r["brand_ar"] or None,
        # .get: the commodity spec has no classification columns, and old
        # payloads predate the contract widening that added them.
        "category_path_ar": r.get("category_path_ar") or "",
        "category_path": r.get("category_path") or "",
        "category_external_id": r.get("category_external_id") or "",
        "product_name": r["product_name"] or "",
        "product_name_lang": r.get("lang") or "",
        # HOW THE SITE PRESENTS IT (0056) — one of vocab.DisplayMethod, or ""
        # from a connector that has not been taught to say. Kept beside
        # parent_sku because it is the same kind of fact: product identity the
        # source states, not an open-ended attribute.
        "display_method": r.get("display_method") or "",
        # "MORE THAN ONE OF IT", which is not the same question as "does this
        # row carry a variant id". The old test was `external_variant_id or
        # option_fingerprint`, and a simple product is emitted as row(uid, uid)
        # by every shop connector here, so external_variant_id was NEVER empty
        # and this column read 1 for 763/763 MADAR products and for every
        # product of sources 1,2,3,4,7,8,9 — one column, one answer, no
        # information. Comparing the two ids is the honest test: a product that
        # IS its own variant has no variations. display_method now answers the
        # richer question; this one goes back to answering its own correctly.
        "has_variants": 1 if (
            (r["external_variant_id"]
             and r["external_variant_id"] != r["external_product_id"])
            or r["option_fingerprint"]) else 0,
        "curation": CurationStatus.INVENTORIED.value,
    })
    record_change(conn, ChangeType.NEW, "source_product", source_product_id=pid,
                  # Either name, whichever the source publishes: an
                  # Arabic-only shop fills only product_name_ar.
                  new_value=(r["product_name"] or r.get("product_name_ar")
                             or r["external_product_id"]),
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
        if r["variant_ar"]:
            # The label is the site's CURRENT wording for which variant this
            # is — when a connector learns to say it better (axis names came
            # 2026-07-23), the next crawl rewrites it. Identity never moves:
            # the fingerprint and external id stay untouched.
            conn.execute(
                "UPDATE source_variant SET variant_ar = ? "
                "WHERE source_variant_id = ? AND COALESCE(variant_ar,'') != ?",
                (r["variant_ar"], found, r["variant_ar"]))
        if r["external_sku"]:
            # Same rule for the SKU, and it was missing: a variant recorded
            # before its connector could read a sku kept a NULL forever, because
            # nothing but the INSERT ever wrote this column. Sika made it
            # visible — 87 products with a real sku each (SK1049 and its
            # siblings) and an export whose SKU column was empty on every row.
            # Identity does not move: variants are keyed on external_variant_id
            # or the option fingerprint, never on the sku (the owner's rule).
            conn.execute(
                "UPDATE source_variant SET external_sku = ? "
                "WHERE source_variant_id = ? AND COALESCE(external_sku,'') != ?",
                (r["external_sku"], found, r["external_sku"]))
        if r.get("variant_axes_ar"):
            conn.execute(
                "UPDATE source_variant SET variant_axes_ar = ? "
                "WHERE source_variant_id = ? AND COALESCE(variant_axes_ar,'') != ?",
                (r["variant_axes_ar"], found, r["variant_axes_ar"]))
        # The same variation in English (0036). Same rule as every other
        # learned fact: written when the source states it, never blanked when
        # it does not, and identity untouched.
        for column, value in (("variant", r.get("variant")),
                              ("variant_axes", r.get("variant_axes")),
                              ("variant_url", r.get("variant_url"))):
            if value:
                conn.execute(
                    f"UPDATE source_variant SET {column} = ? "
                    f"WHERE source_variant_id = ? AND COALESCE({column},'') != ?",
                    (value, found, value))
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
        "variant_ar": r["variant_ar"] or None,
        # The axes as the site states them, as structure. The column has
        # existed since the first schema and was NULL on every row ever
        # written: connectors composed "Color: أحمر" and dropped the parts, so
        # nothing downstream could put the axis and its value in two columns.
        "variant_axes_ar": r.get("variant_axes_ar") or None,
        "variant": r.get("variant") or "",
        "variant_axes": r.get("variant_axes") or "",
        # The variation's OWN page (0037). It used to be written onto the
        # product, where every variation overwrote the one before it.
        "variant_url": r.get("variant_url") or "",
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


def _optional_quantity(raw: str) -> float | None:
    """A quantity the SITE stated, or None when it stated nothing.

    Deliberately not _basis_quantity: that one falls back to 1.0, which is the
    right answer for "how many units does this price buy" (the schema's own
    default) and the WRONG one here. "The shop requires a minimum of 1" and
    "the shop states no minimum" are different facts, and a default of 1 would
    erase the difference on all 3,417 offers that currently say nothing.
    """
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _quantity_facts(r: dict) -> dict:
    """WHAT ONE UNIT OF THE PRICE BUYS, as the site states it (0056).

    ONLY the facts this row actually REPORTED. A connector that has not been
    taught these columns sends "" for all three, and this returns {} — so the
    absent column can never overwrite a value an earlier crawl learned. Same
    rule product_field_diffs already applies to names and brands: an empty
    incoming value is "the connector did not say", never "the source cleared
    it".

    None of these is in ux_source_offer_identity, so learning them never splits
    an offer or mints a second one — an existing offer simply fills in the
    columns it was always missing.
    """
    facts: dict = {}
    for column in ("minimum_quantity", "quantity_increment"):
        value = _optional_quantity(r.get(column, ""))
        if value is not None:
            facts[column] = value
    # This one is a flag, so the site saying "false" is itself an answer — but
    # an ABSENT column is still silence, and "" is what absence looks like.
    stated = str(r.get("quantity_is_decimal", "") or "").strip()
    if stated:
        facts["quantity_is_decimal"] = 1 if stated == "1" else 0
    # THE WEIGHT, AND ONLY WITH ITS UNIT (0057). The two are stored together or
    # not at all: a bare 1000 in a column is not a fact, and the display layer
    # would then be free to supply the missing word itself — which is the one
    # thing this whole change exists to prevent. So a source that publishes a
    # weight and will not say what unit it is in stores neither, exactly as
    # normalize.selling_unit_from says nothing when a name and a weight
    # disagree.
    #
    # canonical_unit folds the spelling the same way the SELLING unit is
    # already folded ("kgs" -> "kg" via _UNIT_ALIASES). That is not editing
    # source truth — it is the shared spelling table this warehouse has always
    # run every unit through, and without it "kgs" and "kg" would be two units
    # for one kilogram.
    weight = _optional_quantity(r.get("weight", ""))
    weight_unit = canonical_unit(str(r.get("weight_unit", "") or ""),
                                 r.get("currency", ""))
    if weight is not None and weight_unit:
        facts["weight"] = weight
        facts["weight_unit"] = weight_unit
    return facts


def _apply_quantity_facts(conn, offer_id: int, facts: dict) -> None:
    """Let an existing offer learn what the site says about its quantity.

    Written on every crawl, not only at INSERT: all 3,417 MADAR offers already
    exist, so an INSERT-only path would have left every one of them blank
    forever — the same trap 0052 fell into with the trade price, where the
    values it promised "on the next crawl" could never arrive because nothing
    asked the warehouse to write them.
    """
    if not facts:
        return
    sets = ", ".join(f"{column} = ?" for column in facts)   # fixed column names
    conn.execute(f"UPDATE source_offer SET {sets} WHERE offer_id = ?",
                 (*facts.values(), offer_id))


def _get_offer_id(conn, variant_id: int, r: dict) -> int:
    vat = 1 if r["tax_included"] == "1" else 0
    unit_id = _get_unit_id(conn, canonical_unit(r.get("unit", ""), r.get("currency", "")))
    basis = _basis_quantity(r.get("basis_quantity", ""))
    quantity = _quantity_facts(r)
    # The unit is part of what an offer IS: 15 per litre and 15 per gallon are
    # different offers, not one offer that changed price. The lookup used to pin
    # selling_unit_id IS NULL, which made every offer unit-less by construction
    # and made those two indistinguishable in the warehouse.
    found = _find_id(
        conn,
        "SELECT offer_id FROM source_offer WHERE source_variant_id = ? AND branch_id IS NULL "
        "AND country_code_alpha2 = ? AND customer_segment = 'retail' "
        "AND COALESCE(selling_unit_id,0) = ? AND basis_quantity = ?",
        (variant_id, r["country_code_alpha2"], unit_id or 0, basis),
    )
    if found is not None:
        _apply_quantity_facts(conn, found, quantity)
        return found
    # AN OFFER LEARNING ITS UNIT IS NOT A SECOND OFFER. The rule above is right
    # about two KNOWN units, and wrong about the step from unknown to known: the
    # day the sika connector learned to read "5 KG" off the name, 56 products
    # each grew a second offer beside their unit-less one, both active, and the
    # current-prices table showed every one of them twice. The offer that never
    # had a unit adopts the one this run states — same offer, better described,
    # and the Unit column fills in where it was blank. Only a move BETWEEN two
    # stated units mints a new offer, which is what "15 per litre and 15 per
    # gallon are different offers" actually means.
    if unit_id:
        unstated = _find_id(
            conn,
            "SELECT offer_id FROM source_offer WHERE source_variant_id = ? AND branch_id IS NULL "
            "AND country_code_alpha2 = ? AND customer_segment = 'retail' AND selling_unit_id IS NULL",
            (variant_id, r["country_code_alpha2"]),
        )
        if unstated is not None:
            conn.execute(
                "UPDATE source_offer SET selling_unit_id = ?, basis_quantity = ? "
                "WHERE offer_id = ?", (unit_id, basis, unstated))
            _apply_quantity_facts(conn, unstated, quantity)
            return unstated
    return _insert(conn, "source_offer", {
        "source_variant_id": variant_id,
        "country_code_alpha2": r["country_code_alpha2"],
        "currency": r["currency"],
        "tax_included": vat,
        "selling_unit_id": unit_id,
        "basis_quantity": basis,
        **quantity,
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
    effective = parse_money(r["price"])
    if effective is None:
        raise ValueError("price is empty after parsing")
    regular = parse_money(r["price_before"]) if r["price_before"] else None
    sale = parse_money(r["price_sale"]) if r["price_sale"] else None
    vat = 1 if r["tax_included"] == "1" else 0
    availability = r["availability"] or Availability.UNKNOWN.value
    if availability not in {a.value for a in Availability}:
        availability = Availability.UNKNOWN.value
    stock_raw = r["stock_quantity"]
    stock_dec = parse_money(stock_raw) if stock_raw else None
    stock = _to_float(stock_dec)
    trade_dec = parse_money(r.get("price_trade", "")) if r.get("price_trade") else None
    # record_hash decides whether this observation is NEW. Its composition is the
    # dedupe key on ux_price_obs_dedupe and part of the frozen cross-engine
    # contract, so a key added unconditionally would re-hash every observation of
    # every source and append a duplicate for all 73,000 of them on the next
    # crawl. `trade` is therefore added ONLY when the shop published one.
    #
    # THE ABSENT FIELD CONTRIBUTES NOTHING — the rule pricekey.py already states
    # and the reason this is safe: a source with no trade price hashes exactly
    # what it hashed yesterday, so nothing moves for it, ever.
    #
    # WHY IT HAD TO GO IN. 0052 moved the trade tier out of the details bag into
    # price_observation.price_trade and left it out of every hash, writing down
    # the cost: "a run where ONLY the trade price moved appends no observation".
    # The real cost was larger. An observation is only ever WRITTEN when the hash
    # differs, so an offer whose retail price had not moved never got a new row
    # at all — and the column stayed NULL on the rows that already existed.
    # Measured on the live warehouse: two successful sikaegshop crawls after
    # 0052, 2,461 rows each, and 0 of 73,084 observations carried a trade price;
    # the newest sikaegshop observation was still dated two days BEFORE the
    # migration. The values 0052 promised would "be re-fetched on the next crawl"
    # could not arrive, because nothing asked the warehouse to write a row.
    #
    # It is NOT added to the price key, and that stays deliberate: this is a
    # different customer's price, so it must not split the retail timeline. It
    # answers "is this row new", not "did the price change".
    content_hash = record_hash({
        "effective": _canon_amount(effective), "regular": _canon_amount(regular),
        "sale": _canon_amount(sale), "currency": r["currency"], "vat": vat,
        "availability": availability, "stock": _canon_amount(stock_dec),
        **({"trade": _canon_amount(trade_dec)} if trade_dec is not None else {}),
    })
    # price_hash answers a different question: is this the SAME PRICE? It leaves
    # availability and stock out — the owner wants the latest stock state, not
    # its history, and a stock movement must never read as a price change.
    price_key = pricekey.build(
        effective=_canon_amount(effective), regular=_canon_amount(regular),
        sale=_canon_amount(sale), currency=r["currency"], vat=vat,
        region=r.get("country_code_alpha2", ""),
        # The real unit, canonicalised the same way the offer identity does it,
        # so the two can never disagree about what a price is per. This slot
        # used to hold option_label, which is the selling unit for commodity
        # rows but a variant TITLE ("Red / Large") for products — so the
        # promise that 15/litre and 15/gallon are different series held for
        # fuel and quietly did not hold for anything else.
        unit=_unit_with_basis(r),
        # The pair rejoined into the string the site published, Arabic
        # first. Splitting the column must not move any offer's identity: the
        # hash sees exactly the text it always saw, so not one of the 1,125
        # branded offers reports a price change that did not happen. Feeding
        # the English half alone would change every ALSWEED digest, and drop
        # brand out of the key entirely for an Arabic-only brand.
        brand=joined_brand(r.get("brand_ar", ""), r.get("brand", "")),
        # Not collected by any connector yet. Named here so a connector that
        # starts supplying them needs no schema change, and so their arrival is
        # a field-set widening rather than a warehouse-wide price change.
        origin=r.get("country_of_origin", ""),
        spec=r.get("spec_summary", ""),
    )
    return {
        "observed_at": observed_at,
        "business_date": observed_at[:10],
        "price_before": _to_float(regular),
        "price_sale": _to_float(sale),
        "price": _to_float(effective),
        # In record_hash when the shop publishes one (see above), never in the
        # PRICE key: it is a different customer's price, so it must not split
        # the retail timeline this warehouse exists to track.
        "price_trade": _to_float(trade_dec),
        "currency": r["currency"],
        "tax_included": vat,
        "availability": availability,
        "stock_quantity": stock,
        "record_hash": content_hash,
        "price_hash": price_key.digest,
        "price_fields": price_key.field_list,
    }


# ---- the pipeline ------------------------------------------------------------

def ingest_payloads(conn: sqlite3.Connection, entry: SourceEntry,
                    payloads: list[FunnelPayload], job_id: int | None = None,
                    fetch_defects: Sequence[str] = (),
                    requests_count: int = 0) -> IngestResult:
    """Ingest one source's payloads into harvest.db in a single transaction.

    All-or-nothing at the DB level (F1): the crawl_run and every row commit
    together, or nothing does. Per-row *data* problems are isolated into
    result.errors and do not abort the batch (Q3).

    `requests_count` is how many HTTP requests the fetch spent. crawl_run has
    carried a column for it since the schema was written, annotated "F5
    politeness accounting" (schema.sql:381) — and NOTHING has ever written it,
    so every run in the warehouse reads 0. A caller that does not know the
    number (the local-inbox path ingests files, having made no requests) leaves
    it alone and gets the same 0 as before. The job path does know, and once it
    records it, the next crawl of that source has a measured expectation to
    show a progress bar against instead of a percentage of nothing."""
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
    # Defects the FETCH already knows about, seeded before any row is read: the
    # connector is the only layer that can tell "this data is degraded" from
    # "this data is fine", and errors_count is written at the end of this
    # function — so a defect appended after the call would never reach the run.
    result.errors.extend(fetch_defects)

    # Prices before enrichment, whatever order the payloads ARRIVE in: a detail
    # can only attach to a product the run has registered, and the local inbox
    # reads files in filename order — which put the enrichment payload first
    # and sent all 270 of samehgabriel's details out-of-scope on a fresh
    # warehouse. The dependency is the ingester's to enforce, not the caller's
    # to remember.
    payloads = sorted(payloads,
                      key=lambda pl: 1 if pl.kind == ExtractKind.ENRICHMENT else 0)
    # Exactly which (product, code) facts this run restated, and with what
    # values — the record that makes retiring a superseded value safe
    # rather than a guess about what a partial crawl did not fetch.
    stated_details: dict = {}
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
                  else partial(_ingest_enrichment_row, stated=stated_details)
                  if payload.kind == ExtractKind.ENRICHMENT
                  else _ingest_product_row)
        for i, raw in enumerate(payload.rows):
            try:
                row_fn(conn, entry, source_id, run_id,
                       view.as_dict(raw), payload.scraped_at, result, job_id)
            except Exception as exc:  # noqa: BLE001 — isolate one bad row (Q3)
                result.errors.append(f"row {i}: {exc}")

    # A detail whose VALUE changed arrived beside its old copy rather than
    # over it, so the superseded one goes now that the run has restated
    # everything the product publishes.
    _retire_superseded_attributes(conn, stated_details, result)
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
        "rows_seen = ?, requests_count = ? WHERE run_id = ?",
        (result.status.value, result.products, result.variants,
         len(result.errors) + len(result.contained),
         sum(len(p.rows) for p in payloads), int(requests_count), run_id),
    )
    return result


def _retire_superseded_attributes(conn, stated: dict, result: "IngestResult") -> None:
    """Drop the values a product no longer states, for the exact facts this run
    restated.

    Keyed on what the run SAID, never on a clock. The first attempt compared
    last_seen_at against the run's start, and last_seen_at has second
    granularity — a fast run stamps the replacement in the same second the
    comparison uses, so the stale row survived by a rounding error. What the
    payload stated is exact and needs no tie-break.

    Scoped hard: only (product, code) pairs this run actually rewrote. A source
    that publishes no enrichment, a product this payload never mentioned, and a
    code the run did not restate are all untouched — so a partial crawl can
    never quietly delete what it simply did not fetch. Silent data loss is the
    one outcome worse than a stale value.
    """
    removed = 0
    for (product_id, code), values in stated.items():
        marks = ",".join("?" * len(values))
        removed += conn.execute(
            f"DELETE FROM source_product_attribute "
            f"WHERE source_product_id = ? AND attribute_code = ? "
            f"AND raw_value NOT IN ({marks})",
            (product_id, code, *values)).rowcount
    if removed:
        # A NOTICE, not an error: this is housekeeping that succeeded. It sat in
        # `errors` until 2026-07-28, where it silently degraded the run.
        result.notices.append(
            f"retired {removed} superseded detail value(s) the source no longer "
            "publishes")


def _ingest_enrichment_row(conn, entry, source_id, run_id, r, observed_at,
                           result: IngestResult, job_id=None, *,
                           stated: dict | None = None) -> None:
    """Land one detail exactly as the shop printed it (source-local layer).

    The connector has emitted these since 2026-07-20 and this function's
    absence made ingest refuse every one — "not yet ingestable (Phase 1)" —
    so colours, lengths and warranties that arrived free in the price
    response were thrown away, and (since completed_with_errors landed)
    degraded a healthy job while doing it.

    UPSERT on (product, code, value): a re-crawl refreshes last_seen_at, a
    value the shop removed simply stops being refreshed.

    That is right for a value the shop DROPPED and wrong for one it
    CHANGED, and the difference was invisible until the owner read CSS in
    a madar description. The conflict key includes raw_value, so a changed
    value INSERTS a new row and the old one is orphaned rather than
    replaced — 125 descriptions ended up stored twice, the stale copy still
    carrying the Page Builder stylesheet the parser now strips. Both showed
    in the panel. _retire_superseded_attributes closes that after the run.
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
        " numeric_value, unit_raw, value_url, attribute_group, lang, is_site_filter) "
        "VALUES (?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(source_product_id, attribute_code, raw_value) DO UPDATE SET "
        "  attribute_label = excluded.attribute_label, "
        "  numeric_value = excluded.numeric_value, "
        "  unit_raw = excluded.unit_raw, "
        "  value_url = excluded.value_url, "
        "  attribute_group = excluded.attribute_group, "
        # A connector that LEARNS a row's language must be able to say so
        # on the stored row — the madar lang-fill rides exactly this.
        "  lang = excluded.lang, "
        "  is_site_filter = excluded.is_site_filter, "
        "  last_seen_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')",
        (row[0], r["attribute_code"], r.get("attribute_label", ""),
         r["raw_value"], r.get("numeric_value", ""), r.get("unit_raw", ""),
         r.get("value_url", ""),
         r.get("attribute_group", "") or DetailGroup.MORE_INFORMATION.value,
         r.get("lang", ""),
         1 if str(r.get("is_site_filter", "")).strip() in {"1", "true", "True"} else 0))
    result.attributes += 1
    if stated is not None:
        stated.setdefault((row[0], r["attribute_code"]), set()).add(r["raw_value"])


def _ingest_product_row(conn, entry, source_id, run_id, r, observed_at,
                        result: IngestResult, job_id: int | None = None) -> None:
    reason = scope_reason(entry, ExtractKind.PRODUCT_PRICES, r["country_code_alpha2"])
    if reason is not None:
        result.rejected_out_of_scope += 1
        result.errors.append(f"out of scope: {reason}")
        return
    # A single-brand shop states its brand once, in the manifest, because
    # its pages never repeat what is not information there. It fills the GAP
    # and never the answer: a shop that publishes a brand per product keeps
    # it, so this can never overwrite a real value with a standing one.
    if entry.brand and not (r.get("brand") or "").strip()             and not (r.get("brand_ar") or "").strip():
        r = {**r, **brand_pair(entry.brand)}
    _persist_row(conn, source_id, run_id, r, observed_at, result, job_id)


def _ingest_commodity_row(conn, entry, source_id, run_id, c, observed_at,
                          result: IngestResult, job_id: int | None = None) -> None:
    """A commodity is a degenerate product (the material is the product, one
    implicit NULL/NULL variant, region on the offer): scope-check on material+region,
    then reuse the exact same persistence chain via the row-shape adapter."""
    reason = scope_reason(entry, ExtractKind.COMMODITY_PRICE, c["country_code_alpha2"], c["material_key"])
    if reason is not None:
        result.rejected_out_of_scope += 1
        result.errors.append(f"out of scope: {reason}")
        return
    _record_implied_rate(conn, entry, c, result)
    _persist_row(conn, source_id, run_id, _commodity_to_product_row(c), observed_at,
                 result, job_id)


def _record_implied_rate(conn, entry, c: dict, result: "IngestResult") -> None:
    """The exchange rate the PUBLISHER used, read off the row's own pair.

    A row carrying the local price and the site's printed USD conversion
    implies the rate between them — Egypt's 20.50 EGP beside 0.40 USD says
    1 USD = 51.25 EGP, in the site's own arithmetic. Recorded per (currency,
    day, source) so the Data page can rank 128 currencies in one USD column;
    never asserted where the pair is absent, and never for a USD row (a rate
    of 1 is noise). Isolated: a malformed pair must not cost the price row.

    ISOLATED IS NOT SILENT. This swallowed sqlite3.DatabaseError alongside the
    two value errors and recorded nothing, so a missing currency_rate table
    after a partial migration — or a locked database — read exactly like a
    number that would not parse. Every rate in a run could fail, the run closed
    with errors_count 0, and the Data page went on ranking currencies at last
    week's rate with nothing anywhere saying why (Q3, and the add-in's
    BulkInsert lesson the rules name).
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
            # 'shop': this rate is implied by a storefront's own printed prices,
            # so it is evidence about that shop and must never be mistaken for a
            # market rate (0054). entry.source_key names a row in source_site by
            # construction. Asked rather than assumed — the code reaches the
            # machine before the migration does; see db.has_column.
            "INSERT INTO currency_rate "
            "  (currency, per_usd, as_of, source_key, source_kind) "
            "VALUES (?,?,?,?,'shop') "
            "ON CONFLICT(currency, as_of, source_key) DO UPDATE SET "
            "  per_usd = excluded.per_usd"
            if _dbmod.has_column(conn, "currency_rate", "source_kind") else
            "INSERT INTO currency_rate (currency, per_usd, as_of, source_key) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(currency, as_of, source_key) DO UPDATE SET "
            "  per_usd = excluded.per_usd",
            (currency, local / usd, as_of, entry.source_key))
    except (ValueError, TypeError) as exc:
        # A NOTICE, not an error: the row said something it could not mean, the
        # price still landed, and nothing about the run is partial. Putting this
        # in `errors` would turn every week GPP publishes one malformed pair
        # among 128 currencies into a PARTIAL run — the exact miscount that had
        # run 38 reported as failed after crawling 15,848 rows correctly.
        result.notices.append(
            f"implied rate for {c.get('currency') or '?'} not recorded — the "
            f"row's own pair does not parse: {exc}")
    except sqlite3.DatabaseError as exc:
        # Not a data problem at all: the store could not take the write. Said
        # separately because the repair is a different one entirely.
        result.errors.append(
            f"implied rate for {c.get('currency') or '?'} not recorded — the "
            f"warehouse refused the write: {exc}")


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
        # The site's own word for the material when it published one; the key
        # otherwise. A machine identity is not a name (owner's report on
        # ARAMCO: the Arabic page was read and only English keys were kept).
        "product_name": c.get("material_label") or c["material_key"],
        "product_name_ar": c.get("material_label_ar", ""),
        "country_code_alpha2": c["country_code_alpha2"],
        "currency": c["currency"],
        "tax_included": c.get("tax_included", ""),
        "price": c["price"],
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
        "official_source_link": c.get("official_source_link", ""),
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
    if not pricekey.comparable(pricekey.parse_fields(open_period["price_fields"]),
                               pricekey.parse_fields(v["price_fields"])):
        return False

    # SAME PRICE PERIOD, BUT IS THERE ANYTHING NEW TO RECORD? Two questions were
    # collapsed into one here, and the second was never asked.
    #
    # The retail price key deliberately excludes the trade tier (0052: it is a
    # different customer's price and must not split this product's timeline).
    # But this function is also the gate on whether an observation is APPENDED
    # AT ALL — so a shop that moved only its trade price was confirmed, nothing
    # was written, and the column stayed NULL forever. Measured on the live
    # warehouse: two sikaegshop crawls after 0052, 0 of 73,084 observations
    # carrying a trade price, and the newest sikaegshop row still dated two days
    # BEFORE the migration that introduced the column.
    #
    # So the period stays keyed on the price — a trade move opens no new period —
    # while a trade move that is genuinely new still lands as an observation
    # INSIDE that period. The retail timeline is unchanged; the fact is recorded.
    if v.get("price_trade") is not None:
        latest = conn.execute(
            "SELECT price_trade FROM price_observation "
            "WHERE offer_id = ? AND provenance = 'observed' "
            "ORDER BY observed_at DESC, price_observation_id DESC LIMIT 1",
            (offer_id,)).fetchone()
        if latest is None or latest["price_trade"] != v["price_trade"]:
            return False
    return True


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
                      source_variant_id=variant_id, new_value=r["variant_ar"] or None,
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
            "(offer_id, observed_at, business_date, price_before, price_sale, "
            " price, currency, tax_included, availability, stock_quantity, "
            " run_id, record_hash, price_hash, price_fields, provenance, "
            " official_source_name, official_source_link) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'reported',?,?)",
            (offer_id, v["observed_at"], r["as_of_date"], v["price_before"],
             v["price_sale"], v["price"], v["currency"], v["tax_included"],
             v["availability"], v["stock_quantity"], run_id, v["record_hash"],
             v["price_hash"], v["price_fields"],
             r.get("official_source_name", ""), r.get("official_source_link", "")),
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
        "SELECT price, availability, currency FROM price_observation "
        "WHERE offer_id = ? AND provenance = 'observed' "
        "ORDER BY observed_at DESC, price_observation_id DESC LIMIT 1", (offer_id,)
    ).fetchone()
    cur = conn.execute(
        "INSERT OR IGNORE INTO price_observation "
        "(offer_id, observed_at, business_date, price_before, price_sale, price, "
        " price_trade, currency, tax_included, availability, stock_quantity, run_id, "
        "record_hash, price_hash, price_fields, provenance, official_source_name, "
        "official_source_link) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'observed',?,?)",
        (offer_id, v["observed_at"], v["business_date"], v["price_before"], v["price_sale"],
         v["price"], v["price_trade"], v["currency"], v["tax_included"], v["availability"],
         v["stock_quantity"], run_id, v["record_hash"],
         v["price_hash"], v["price_fields"],
         r.get("official_source_name", ""), r.get("official_source_link", "")),
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
                moved = classify_price(previous["price"], v["price"])
                if moved is not None:
                    record_change(conn, moved, "price",
                                  previous_value=previous["price"],
                                  new_value=v["price"], **ids)
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
