"""Read-only reports over harvest.db (ENGINEERING.md A8: bounded reads only).

The `peek` summary makes the two-layer warehouse legible: what landed in the
SOURCE-LOCAL layer (raw, as scraped) vs the UNIFIED layer (fills only after the
owner curates). This directly answers "did anything actually land?".
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field


@dataclass
class SourceSummary:
    source_key: str
    source_name: str
    # source-local layer (raw)
    products: int = 0
    variants: int = 0
    observations: int = 0
    curation: dict[str, int] = field(default_factory=dict)
    last_run: str | None = None
    last_status: str | None = None
    # unified layer (post-curation)
    matched_variants: int = 0
    published_rows: int = 0


def source_summary(conn: sqlite3.Connection, source_key: str) -> SourceSummary | None:
    row = conn.execute(
        "SELECT source_id, source_name FROM source_site WHERE source_key = ?", (source_key,)
    ).fetchone()
    if row is None:
        return None
    source_id, source_name = row[0], row[1]
    s = SourceSummary(source_key=source_key, source_name=source_name)

    s.products = _scalar(conn, "SELECT COUNT(*) FROM source_product WHERE source_id = ?", (source_id,))
    s.variants = _scalar(conn,
        "SELECT COUNT(*) FROM source_variant sv JOIN source_product sp "
        "ON sp.source_product_id = sv.source_product_id WHERE sp.source_id = ?", (source_id,))
    s.observations = _scalar(conn,
        "SELECT COUNT(*) FROM price_observation po "
        "JOIN source_offer so ON so.offer_id = po.offer_id "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
        "WHERE sp.source_id = ?", (source_id,))
    s.curation = {
        r[0]: r[1] for r in conn.execute(
            "SELECT curation_status, COUNT(*) FROM source_product WHERE source_id = ? "
            "GROUP BY curation_status", (source_id,))
    }
    run = conn.execute(
        "SELECT started_at, status FROM crawl_run WHERE source_id = ? "
        "ORDER BY started_at DESC LIMIT 1", (source_id,)).fetchone()
    if run is not None:
        s.last_run, s.last_status = run[0], run[1]

    s.matched_variants = _scalar(conn,
        "SELECT COUNT(*) FROM source_variant_match svm "
        "JOIN source_variant sv ON sv.source_variant_id = svm.source_variant_id "
        "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
        "WHERE sp.source_id = ? AND svm.review_status = 'approved' AND svm.valid_to IS NULL",
        (source_id,))
    s.published_rows = _scalar(conn,
        "SELECT COUNT(*) FROM v_material_price_tracking WHERE source_name = ?", (source_name,))
    return s


def list_sources(conn: sqlite3.Connection) -> list[SourceSummary]:
    """Every registered source with its summary — the web overview (A8 bounded:
    source count is tiny by definition)."""
    keys = [r[0] for r in conn.execute("SELECT source_key FROM source_site ORDER BY source_key")]
    return [s for s in (source_summary(conn, k) for k in keys) if s is not None]


@dataclass
class BrowsePage:
    rows: list[dict]
    total: int
    offset: int
    limit: int

    @property
    def has_prev(self) -> bool:
        return self.offset > 0

    @property
    def has_next(self) -> bool:
        return self.offset + self.limit < self.total


# One row per offer = its LATEST observation (current price), reused by browse+count.
_LATEST_PER_OFFER = (
    "FROM price_observation po "
    "JOIN source_offer so ON so.offer_id = po.offer_id "
    "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
    "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
    "JOIN source_site ss ON ss.source_id = sp.source_id "
    "WHERE ss.source_key = ? "
    "AND po.price_observation_id = ("
    "  SELECT po2.price_observation_id FROM price_observation po2 "
    # price_observation_id breaks observed_at ties toward the NEWEST row. Ties are
    # structural, not rare: one crawl stamps every chunk with the same scraped_at,
    # so a same-day price change would otherwise publish the superseded price.
    "  WHERE po2.offer_id = po.offer_id "
    "  ORDER BY po2.observed_at DESC, po2.price_observation_id DESC LIMIT 1)"
)


def region_name(region: str | None) -> str:
    """ISO alpha-2 -> English country name, for display only.

    Commodity rows are one-per-country, so the region IS the row's identity —
    without it ~180 rows render byte-identical except for the price. A product
    source uses region '*' (no per-row geography), which must read as blank
    rather than a literal asterisk.
    """
    code = (region or "").strip()
    if not code or code == "*":
        return ""
    try:
        import pycountry
    except ImportError:                     # display nicety, never a hard dependency
        return code
    try:
        found = pycountry.countries.get(alpha_2=code.upper())
    except (LookupError, KeyError):
        return code
    return getattr(found, "common_name", None) or getattr(found, "name", None) or code


def region_code(text: str | None) -> str:
    """Country NAME -> ISO alpha-2, the inverse of region_name.

    Needed because the region is stored as a code while a person searches by
    name: without this, typing "Egypt" matches nothing on a commodity source.
    Returns "" when the text is not a country.
    """
    name = (text or "").strip()
    if len(name) < 3:                       # "EG" is already a code, not a name
        return ""
    try:
        import pycountry
    except ImportError:
        return ""
    try:
        return pycountry.countries.lookup(name).alpha_2
    except LookupError:
        return ""


def _browse_filters(search: str | None, availability: str | None) -> tuple[str, list]:
    clause, params = "", []
    if search:
        # Match the region too: for a commodity source the country IS the row.
        # Both spellings work — the stored code ("EG") and the human name
        # ("Egypt"), which is resolved to its code before the query runs.
        clause += " AND (sp.source_name LIKE ? OR so.region LIKE ?"
        params += [f"%{search}%", f"%{search}%"]
        code = region_code(search)
        if code:
            clause += " OR so.region = ?"
            params.append(code)
        clause += ")"
    if availability:
        clause += " AND po.availability = ?"
        params.append(availability)
    return clause, params


# Sortable columns, as an ALLOW-LIST of key -> SQL expression. A sort key never
# reaches the query as text, so no ordering choice can become SQL injection.
SORTABLE = {
    "name": "sp.source_name",
    "region": "so.region",
    "sku": "sv.external_sku",
    "effective_price": "po.effective_price",
    "availability": "po.availability",
    "business_date": "po.business_date",
}
DEFAULT_SORT = "name"


def _order_by(sort: str | None, direction: str | None) -> str:
    column = SORTABLE.get(sort or DEFAULT_SORT, SORTABLE[DEFAULT_SORT])
    way = "DESC" if (direction or "asc").lower() == "desc" else "ASC"
    # so.region is always the final tiebreak: commodity rows share a source_name,
    # and without it their order is not stable between identical queries.
    return f"ORDER BY {column} {way}, sp.source_name, so.region"


def browse_observations(conn: sqlite3.Connection, source_key: str, *, search: str | None = None,
                        availability: str | None = None, sort: str | None = None,
                        direction: str | None = None,
                        offset: int = 0, limit: int = 50) -> BrowsePage:
    """Paginated current-price browse for one source (A8: always LIMIT+OFFSET).

    Filters and the base join are shared between the page query and the count
    query so the two can never diverge (DRY)."""
    limit = max(1, min(limit, 200))  # hard cap (A8) — never an unbounded read
    filt, fparams = _browse_filters(search, availability)
    base_params = [source_key, *fparams]

    total = int(conn.execute(f"SELECT COUNT(*) {_LATEST_PER_OFFER}{filt}", base_params).fetchone()[0])
    rows = conn.execute(
        "SELECT sp.source_name, sv.option_label, sv.external_sku, po.effective_price, "
        "       po.regular_price, po.sale_price, po.currency, po.availability, po.vat_included, "
        "       po.business_date, sp.product_url, sp.curation_status, so.region "
        f"{_LATEST_PER_OFFER}{filt} {_order_by(sort, direction)} LIMIT ? OFFSET ?",
        [*base_params, limit, offset],
    ).fetchall()
    shaped = [
        {"name": r[0], "option_label": r[1], "sku": r[2], "effective_price": r[3],
         "regular_price": r[4], "sale_price": r[5], "currency": r[6], "availability": r[7],
         "vat_included": bool(r[8]), "business_date": r[9], "product_url": r[10],
         "curation_status": r[11], "region": r[12] or "", "region_name": region_name(r[12])}
        for r in rows
    ]
    return BrowsePage(rows=shaped, total=total, offset=offset, limit=limit)


EXPORT_HEADER = [
    # region/country sit right after the name: for a commodity source they are
    # what distinguishes one row from the next.
    "product_name", "region", "country", "option_label", "sku", "effective_price",
    "regular_price", "sale_price", "currency", "availability", "vat_included",
    "business_date", "product_url",
]


def export_source_table(conn: sqlite3.Connection, source_key: str,
                        limit: int = 40_000) -> tuple[list[str], list[list]]:
    """Flat current-price table for one source (header + rows), ready to write to
    a Google Sheet tab. Reuses the shared latest-per-offer join (DRY) and is
    always bounded (A8). Numbers stay numeric so Sheets sorts/filters them."""
    rows = conn.execute(
        "SELECT sp.source_name, sv.option_label, sv.external_sku, po.effective_price, "
        "       po.regular_price, po.sale_price, po.currency, po.availability, "
        "       po.vat_included, po.business_date, sp.product_url, so.region "
        f"{_LATEST_PER_OFFER} ORDER BY sp.source_name, so.region LIMIT ?",
        (source_key, limit),
    ).fetchall()
    table = [
        [r[0] or "", (r[11] or "") if r[11] != "*" else "", region_name(r[11]),
         r[1] or "", r[2] or "",
         r[3] if r[3] is not None else "", r[4] if r[4] is not None else "",
         r[5] if r[5] is not None else "", r[6] or "", r[7] or "",
         "yes" if r[8] else "no", r[9] or "", r[10] or ""]
        for r in rows
    ]
    return list(EXPORT_HEADER), table


def recent_observations(conn: sqlite3.Connection, source_key: str, limit: int = 10) -> list[dict]:
    """A bounded sample of the source-local prices (A8: always LIMIT-ed)."""
    rows = conn.execute(
        "SELECT sp.source_name, po.effective_price, po.currency, po.availability, "
        "       po.vat_included, po.business_date, so.region "
        "FROM price_observation po "
        "JOIN source_offer so ON so.offer_id = po.offer_id "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
        "JOIN source_site ss ON ss.source_id = sp.source_id "
        "WHERE ss.source_key = ? ORDER BY po.observed_at DESC, po.price_observation_id DESC LIMIT ?",
        (source_key, limit),
    ).fetchall()
    return [
        {"name": r[0], "price": r[1], "currency": r[2], "availability": r[3],
         "vat_included": bool(r[4]), "business_date": r[5],
         "region": r[6] or "", "region_name": region_name(r[6])}
        for r in rows
    ]


def crawl_history(conn: sqlite3.Connection, source_key: str | None = None,
                  limit: int = 50) -> list[dict]:
    """Per-run history (spec 21 "Crawl History"). crawl_run has recorded this all
    along — status, counts, request budget, rows_seen — and nothing ever showed it."""
    sql = ("SELECT r.run_id, r.job_id, ss.source_key, ss.source_name, r.started_at, "
           "       r.finished_at, r.status, r.products_discovered, r.variants_discovered, "
           "       r.errors_count, r.rows_seen "
           "FROM crawl_run r JOIN source_site ss ON ss.source_id = r.source_id ")
    params: list = []
    if source_key:
        sql += "WHERE ss.source_key = ? "
        params.append(source_key)
    sql += "ORDER BY r.run_id DESC LIMIT ?"
    params.append(max(1, min(limit, 500)))
    return [dict(r) for r in conn.execute(sql, params)]


def price_extremes(conn: sqlite3.Connection, source_key: str, limit: int = 50) -> list[dict]:
    """First / current / min / max price per offer (spec 15).

    The append-only history has always contained this; it just had no reader.
    Bounded like every other read (A8).
    """
    rows = conn.execute(
        "SELECT sp.source_name, so.region, po.currency, "
        "       MIN(po.effective_price) AS min_price, MAX(po.effective_price) AS max_price, "
        "       COUNT(*) AS observations, "
        "       (SELECT p2.effective_price FROM price_observation p2 WHERE p2.offer_id = so.offer_id "
        "        ORDER BY p2.observed_at, p2.price_observation_id LIMIT 1) AS first_price, "
        "       (SELECT p3.effective_price FROM price_observation p3 WHERE p3.offer_id = so.offer_id "
        "        ORDER BY p3.observed_at DESC, p3.price_observation_id DESC LIMIT 1) AS current_price "
        "FROM price_observation po "
        "JOIN source_offer so ON so.offer_id = po.offer_id "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
        "JOIN source_site ss ON ss.source_id = sp.source_id "
        "WHERE ss.source_key = ? GROUP BY so.offer_id "
        "ORDER BY sp.source_name, so.region LIMIT ?",
        (source_key, max(1, min(limit, 500))),
    ).fetchall()
    out = []
    for r in rows:
        item = dict(r)
        item["region_name"] = region_name(item["region"])
        first, current = item["first_price"], item["current_price"]
        item["change_abs"] = None if first is None else round(current - first, 6)
        item["change_pct"] = (None if not first else round((current - first) / first * 100, 2))
        out.append(item)
    return out


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple) -> int:
    return int(conn.execute(sql, params).fetchone()[0])
