"""Read-only reports over harvest.db (ENGINEERING.md A8: bounded reads only).

The `peek` summary makes the two-layer warehouse legible: what landed in the
SOURCE-LOCAL layer (raw, as scraped) vs the UNIFIED layer (fills only after the
owner curates). This directly answers "did anything actually land?".
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from . import fields, tax


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
    # LEFT: an offer whose state has not been derived yet still has a price.
    "LEFT JOIN offer_state ost ON ost.offer_id = po.offer_id "
    # LEFT: a source that publishes no unit still has a price. A missing unit
    # must read as "not stated" and must never suppress the row.
    "LEFT JOIN selling_unit su ON su.selling_unit_id = so.selling_unit_id "
    "WHERE ss.source_key = ? "
    "AND po.price_observation_id = ("
    "  SELECT po2.price_observation_id FROM price_observation po2 "
    # The offer's face is what WE saw, newest first. Ordering by observed_at
    # alone made the current price a lottery: one crawl stamps every row with
    # the same timestamp — today's observed price AND the source's backfilled
    # year-ago anchors — and the id tiebreak then crowned the LAST INSERT,
    # which for GPP was the oldest anchor. Diesel showed 15.5 EGP dated
    # 2025 while the source said 20.5 today. Reported rows are the source's
    # dated claims about the PAST; they may only speak for an offer that has
    # no observation at all, and then the newest-dated claim speaks.
    "  WHERE po2.offer_id = po.offer_id "
    "  ORDER BY (po2.provenance = 'observed') DESC, po2.business_date DESC, "
    "           po2.price_observation_id DESC LIMIT 1)"
)


def price_unit(unit_code: str | None, basis_quantity: float | None = 1) -> str:
    """What one price buys, as text: 'liter', '100 m', or "" when unstated.

    Returned as ONE string so a screen cannot render the quantity and forget the
    unit — the pair only means anything together. Empty when the source
    published no unit; the caller shows that as "not stated" rather than
    inventing 'each', which would be an assertion nobody made.
    """
    if not unit_code:
        return ""
    try:
        basis = float(basis_quantity if basis_quantity is not None else 1)
    except (TypeError, ValueError):
        basis = 1.0
    if basis == 1.0:
        return unit_code
    quantity = int(basis) if basis.is_integer() else basis
    return f"{quantity} {unit_code}"


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


def _browse_filters(search: str | None, availability: str | None,
                    column_filters: dict[str, tuple[str, str]] | None = None
                    ) -> tuple[str, list]:
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
    # Per-column filters. Built by iterating FILTERABLE, never the caller's dict,
    # so an unknown key cannot reach SQL even if one slipped past parse_filters.
    for key, (operator, value) in (column_filters or {}).items():
        entry = FILTERABLE.get(key)
        if entry is None or entry[1] == "derived":
            continue
        template = _OPERATORS.get(operator)
        if template is None:
            continue
        clause += " AND " + template.format(col=entry[0])
        if operator == "has":
            params.append(f"%{value}%")
        elif key == "region" and operator == "is":
            # The screen shows the country NAME (region_name), so that is what a
            # person types. The column stores the ISO code. Without this,
            # filtering by the only string on screen matches nothing.
            params.append(region_code(value) or value)
        else:
            params.append(value)
    return clause, params


# Every column a query may touch, as an ALLOW-LIST of key -> (SQL expression,
# kind). A key never reaches the query as text, so neither a sort nor a filter
# can become SQL injection — the expression is looked UP, never interpolated.
#
# ONE table, so sorting and filtering cannot drift apart. They were separate,
# and SORTABLE quietly omitted last_confirmed and curation_status: two columns
# the page rendered with no way to order by them, and nothing said so.
#
# kind decides what control the header offers:
#   text    free text, matched with LIKE
#   exact   a bounded domain (a CHECK constraint or ISO codes) -> a <select>
#   number  a numeric comparison
#   date    a date comparison
#   derived computed in PYTHON after the query, so SQL cannot filter it at all
FILTERABLE: dict[str, tuple[str, str]] = {
    "product_name": ("sp.source_name", "text"),
    "region": ("so.region", "exact"),
    "option_label": ("sv.option_label", "text"),
    "sku": ("sv.external_sku", "text"),
    "effective_price": ("po.effective_price", "number"),
    "availability": ("po.availability", "exact"),
    "price_changed_on": ("po.business_date", "date"),
    "last_confirmed_on": ("ost.last_confirmed_at", "date"),
    "curation_status": ("sp.curation_status", "exact"),
    # Computed in Python — price_unit() and tax.resolve(), the latter with a
    # region->wildcard fallback and valid_to temporality. Reimplementing that in
    # SQL and keeping the two in agreement across 169 regions is a correctness
    # trap, so these are honestly marked unfilterable rather than half-supported.
    "unit": ("", "derived"),
    "tax_label": ("", "derived"),
}

# Derived from the same table, so the two can never disagree about a column.
SORTABLE = {key: expr for key, (expr, kind) in FILTERABLE.items() if kind != "derived"}
DEFAULT_SORT = "product_name"

# What a filter may ASK. The operator picks a SQL template; the value is always
# a bound parameter, never text spliced into the statement.
_OPERATORS: dict[str, str] = {
    "has": "{col} LIKE ?",
    "is": "{col} = ?",
    "gte": "{col} >= ?",
    "lte": "{col} <= ?",
    "after": "{col} > ?",
    "before": "{col} < ?",
}


def parse_filters(params: dict[str, str]) -> tuple[dict[str, tuple[str, str]], list[str]]:
    """Read `f.<key>=<op>:<value>` pairs. Returns (accepted, ignored keys).

    Anything unknown is REPORTED, not silently dropped: a filter that vanishes
    without a word makes the answer bigger than the question, and the reader has
    no way to tell. A crafted key is refused here and never reaches SQL.
    """
    accepted: dict[str, tuple[str, str]] = {}
    ignored: list[str] = []
    for raw_key, raw_value in params.items():
        if not raw_key.startswith("f."):
            continue
        key = raw_key[2:]
        operator, _, value = str(raw_value).partition(":")
        if not value or key not in FILTERABLE or operator not in _OPERATORS:
            ignored.append(raw_key)
            continue
        if FILTERABLE[key][1] == "derived":
            ignored.append(raw_key)      # computed in Python; SQL cannot filter it
            continue
        accepted[key] = (operator, value)
    return accepted, ignored


def _order_by(sort: str | None, direction: str | None) -> str:
    column = SORTABLE.get(sort or DEFAULT_SORT, SORTABLE[DEFAULT_SORT])
    way = "DESC" if (direction or "asc").lower() == "desc" else "ASC"
    # so.region is always the final tiebreak: commodity rows share a source_name,
    # and without it their order is not stable between identical queries.
    return f"ORDER BY {column} {way}, sp.source_name, so.region"


def browse_observations(conn: sqlite3.Connection, source_key: str, *, search: str | None = None,
                        availability: str | None = None, sort: str | None = None,
                        direction: str | None = None,
                        column_filters: dict[str, tuple[str, str]] | None = None,
                        offset: int = 0, limit: int = 50) -> BrowsePage:
    """Paginated current-price browse for one source (A8: always LIMIT+OFFSET).

    Filters and the base join are shared between the page query and the count
    query so the two can never diverge (DRY)."""
    limit = max(1, min(limit, 200))  # hard cap (A8) — never an unbounded read
    filt, fparams = _browse_filters(search, availability, column_filters)
    base_params = [source_key, *fparams]

    total = int(conn.execute(f"SELECT COUNT(*) {_LATEST_PER_OFFER}{filt}", base_params).fetchone()[0])
    rows = conn.execute(
        "SELECT sp.source_name, sv.option_label, sv.external_sku, po.effective_price, "
        "       po.regular_price, po.sale_price, po.currency, po.availability, po.vat_included, "
        "       po.business_date, sp.product_url, sp.curation_status, so.region, "
        "       ost.last_confirmed_at, su.unit_code, so.basis_quantity, so.offer_id "
        f"{_LATEST_PER_OFFER}{filt} {_order_by(sort, direction)} LIMIT ? OFFSET ?",
        [*base_params, limit, offset],
    ).fetchall()
    tax_rules = tax.load_rules(conn, source_key)
    shaped = [
        {"name": r[0], "option_label": r[1], "sku": r[2], "effective_price": r[3],
         "regular_price": r[4], "sale_price": r[5], "currency": r[6], "availability": r[7],
         "vat_included": bool(r[8]), "business_date": r[9], "product_url": r[10],
         "curation_status": r[11], "region": r[12] or "", "region_name": region_name(r[12]),
         # When the price was last CONFIRMED, which is not when it last changed.
         "last_confirmed": (r[13] or "")[:10],
         # A price without its unit is not a comparable number: 325 per tonne and
         # 325 per bag are different facts that look identical on screen.
         "unit": price_unit(r[14], r[15]),
         # Resolved per ROW because one source can hold a different tax position
         # per country. Rules are loaded once above, never queried per row.
         **tax.resolve(tax_rules, r[12]).as_dict(),
         # The row's own identity. Its absence is why no screen has ever been
         # able to ask "what did THIS price do over time" — pricehistory.timeline
         # has been callable since migration 0016 and had no way to be reached,
         # because the row on the page carried nothing to ask about.
         "offer_id": r[16]}
        for r in rows
    ]
    return BrowsePage(rows=shaped, total=total, offset=offset, limit=limit)


def history_counts(conn: sqlite3.Connection, offer_ids: list[int]) -> dict[int, int]:
    """How many distinct prices each offer has had. One query for the page.

    Answers "which of these 721 rows actually moved?" by scanning the column,
    instead of opening rows one at a time to find out. Bounded by the page size
    (A8), so it costs one GROUP BY over at most 200 offers, never a query per row.
    """
    if not offer_ids:
        return {}
    marks = ",".join("?" for _ in offer_ids)
    try:
        rows = conn.execute(
            f"SELECT offer_id, COUNT(*) FROM price_period WHERE offer_id IN ({marks}) "
            "GROUP BY offer_id", offer_ids).fetchall()
    except sqlite3.DatabaseError:
        # price_period arrives with migration 0016 and is DERIVED — a warehouse
        # that has not rebuilt it yet is not broken, it just has nothing to say.
        return {}
    return {int(r[0]): int(r[1]) for r in rows}


# The columns the DATA TABLE can show, as (key, label) in default order. One
# definition, so "manage columns" manages exactly what the table renders — until
# now the panel managed a constant 14-key export header while the table itself
# had ten literal <th> cells, and the two had no relationship at all.
# The KEYS are the export vocabulary, deliberately. They were invented fresh
# when this list was written — "name" beside EXPORT_HEADER's "product_name",
# "business_date" beside "price_changed_on" — and dataset_field then held two
# names for the same fact, so the manage list showed each column twice and
# hiding one did not hide the other. One vocabulary, one list, one meaning.
BROWSE_COLUMNS: list[tuple[str, str]] = [
    ("product_name", "Record"),
    ("region", "Country"),
    ("option_label", "Variant"),
    ("sku", "SKU"),
    ("effective_price", "Price"),
    ("unit", "Unit"),
    ("availability", "Status"),
    ("tax_label", "Tax"),
    ("price_changed_on", "Price changed"),
    ("last_confirmed_on", "Last confirmed"),
    ("curation_status", "Curation"),
]

# Never hidden by the emptiness sweep: without them a row cannot be identified
# or is not a price at all.
ESSENTIAL_COLUMNS = frozenset({"product_name", "effective_price"})


def column_presence(conn: sqlite3.Connection, source_key: str) -> set[str]:
    """Which browse columns this source actually populates.

    Answers the review's key question — "when a source supplies no brand or SKU,
    does the table still show those columns?" — with data rather than a guess.
    ONE aggregate over the latest-per-offer set, not a query per column.

    A source that publishes no variants, no SKU and no unit should not be given
    three columns of em-dashes to read past.
    """
    row = conn.execute(
        "SELECT COUNT(NULLIF(TRIM(COALESCE(sv.option_label,'')),'')), "
        "       COUNT(NULLIF(TRIM(COALESCE(sv.external_sku,'')),'')), "
        "       COUNT(NULLIF(TRIM(COALESCE(so.region,'')),'')), "
        "       COUNT(so.selling_unit_id), "
        # 'unknown' is a non-empty string that states nothing. Counting it as
        # present gave GPP a Status column reading "Unknown" on all 721 rows —
        # a column of noise. No information is not information.
        "       COUNT(NULLIF(NULLIF(TRIM(COALESCE(po.availability,'')),''),'unknown')) "
        f"{_LATEST_PER_OFFER}", (source_key,)).fetchone()
    present = {key for key, _ in BROWSE_COLUMNS}
    for column, count in (("option_label", row[0]), ("sku", row[1]),
                          ("region", row[2]), ("unit", row[3]),
                          ("availability", row[4])):
        if not count:
            present.discard(column)
    return present


EXPORT_HEADER = [
    # region/country sit right after the name: for a commodity source they are
    # what distinguishes one row from the next.
    "product_name", "region", "country", "option_label", "sku", "effective_price",
    # The unit sits beside the price it qualifies. A column of bare numbers where
    # some are per tonne and some per bag is not a price list, it is a trap.
    "unit", "regular_price", "sale_price", "currency", "availability",
    # vat_included alone was a claim with no source. The three columns beside it
    # say how well we actually know it, and where the owner can go and read it.
    "vat_included", "tax_evidence", "tax_rate_pct", "tax_statement_url",
    # price_changed_on is when the price last MOVED; last_confirmed_on is when a
    # completed run last saw it still true. They are different questions, and
    # publishing only the first made a confirmed price look stale.
    "price_changed_on", "last_confirmed_on", "product_url",
]


def export_source_table(conn: sqlite3.Connection, source_key: str,
                        limit: int = 40_000) -> tuple[list[str], list[list]]:
    """Flat current-price table for one source (header + rows), ready to write to
    a Google Sheet tab. Reuses the shared latest-per-offer join (DRY) and is
    always bounded (A8). Numbers stay numeric so Sheets sorts/filters them."""
    rows = conn.execute(
        "SELECT sp.source_name, sv.option_label, sv.external_sku, po.effective_price, "
        "       po.regular_price, po.sale_price, po.currency, po.availability, "
        "       po.vat_included, po.business_date, sp.product_url, so.region, "
        "       ost.last_confirmed_at, su.unit_code, so.basis_quantity "
        f"{_LATEST_PER_OFFER} ORDER BY sp.source_name, so.region LIMIT ?",
        (source_key, limit),
    ).fetchall()
    tax_rules = tax.load_rules(conn, source_key)
    table = []
    for r in rows:
        state = tax.resolve(tax_rules, r[11])
        table.append(
            [r[0] or "", (r[11] or "") if r[11] != "*" else "", region_name(r[11]),
             r[1] or "", r[2] or "",
             r[3] if r[3] is not None else "", price_unit(r[13], r[14]),
             r[4] if r[4] is not None else "",
             r[5] if r[5] is not None else "", r[6] or "", r[7] or "",
             "yes" if r[8] else "no",
             state.evidence,
             state.rate_pct if state.rate_pct is not None else "",
             state.statement_url,
             r[9] or "", (r[12] or "")[:10], r[10] or ""])
    return list(EXPORT_HEADER), table


def recent_observations(conn: sqlite3.Connection, source_key: str, limit: int = 10) -> list[dict]:
    """A bounded sample of the source-local prices (A8: always LIMIT-ed)."""
    rows = conn.execute(
        "SELECT sp.source_name, po.effective_price, po.currency, po.availability, "
        "       po.vat_included, po.business_date, so.region, su.unit_code, so.basis_quantity "
        "FROM price_observation po "
        "JOIN source_offer so ON so.offer_id = po.offer_id "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
        "JOIN source_site ss ON ss.source_id = sp.source_id "
        "LEFT JOIN selling_unit su ON su.selling_unit_id = so.selling_unit_id "
        "WHERE ss.source_key = ? ORDER BY po.observed_at DESC, po.price_observation_id DESC LIMIT ?",
        (source_key, limit),
    ).fetchall()
    return [
        {"name": r[0], "price": r[1], "currency": r[2], "availability": r[3],
         "vat_included": bool(r[4]), "business_date": r[5],
         "region": r[6] or "", "region_name": region_name(r[6]),
         "unit": price_unit(r[7], r[8])}
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


def offer_identity(conn: sqlite3.Connection, source_key: str,
                   offer_id: int) -> dict | None:
    """What this offer IS, and None when it does not belong to this source.

    The ownership check is the security boundary, not a nicety: without it the
    URL /source/A/offer/<id> would happily render an offer belonging to source B
    to anyone who could count. The join through source_site is what makes the
    check impossible to forget — the row simply does not come back.
    """
    row = conn.execute(
        "SELECT sp.source_name, sv.option_label, sv.external_sku, so.region, "
        "       so.currency, su.unit_code, so.basis_quantity, sp.product_url, "
        "       ss.source_key "
        "FROM source_offer so "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
        "JOIN source_site ss ON ss.source_id = sp.source_id "
        "LEFT JOIN selling_unit su ON su.selling_unit_id = so.selling_unit_id "
        "WHERE so.offer_id = ? AND ss.source_key = ?",
        (offer_id, source_key)).fetchone()
    if row is None:
        return None
    return {"name": row[0], "option_label": row[1] or "", "sku": row[2] or "",
            "region": row[3] or "", "region_name": region_name(row[3]),
            "currency": row[4], "unit": price_unit(row[5], row[6]),
            "product_url": row[7] or "", "source_key": row[8],
            "offer_id": offer_id}


def offer_observations(conn: sqlite3.Connection, offer_id: int,
                       limit: int = 200) -> list[dict]:
    """The raw append-only observations behind the timeline, newest first.

    The timeline shows CHANGES; this shows what was actually recorded, including
    which rows we observed ourselves and which the source reported for an earlier
    date. Keeping them distinguishable on screen is the whole point of storing
    the distinction (migration 0019).
    """
    columns = {r[1] for r in conn.execute("PRAGMA table_info(price_observation)")}
    provenance = "provenance" if "provenance" in columns else "'observed'"
    rows = conn.execute(
        f"SELECT business_date, effective_price, regular_price, sale_price, currency, "
        f"       observed_at, {provenance} "
        "FROM price_observation WHERE offer_id = ? "
        "ORDER BY business_date DESC, price_observation_id DESC LIMIT ?",
        (offer_id, max(1, min(limit, 500)))).fetchall()
    return [{"business_date": r[0], "effective_price": r[1], "regular_price": r[2],
             "sale_price": r[3], "currency": r[4], "observed_at": r[5],
             "provenance": r[6]} for r in rows]


def facet_options(conn: sqlite3.Connection, source_key: str, key: str,
                  limit: int = 200) -> list[str]:
    """The distinct values of one BOUNDED column, for a <select>.

    Only for columns whose domain the schema already limits — a CHECK
    constraint or ISO codes. Excel offers this list for every column; at 40,000
    rows a product-name column has ~40,000 distinct values, and building that
    list is exactly the unbounded read A8 forbids. So free-text columns get a
    text box, and this is never called for them.
    """
    entry = FILTERABLE.get(key)
    if entry is None or entry[1] != "exact":
        return []
    rows = conn.execute(
        f"SELECT DISTINCT {entry[0]} {_LATEST_PER_OFFER} "
        f"AND {entry[0]} IS NOT NULL AND TRIM({entry[0]}) <> '' "
        f"ORDER BY 1 LIMIT ?", (source_key, max(1, min(limit, 500)))).fetchall()
    return [str(r[0]) for r in rows]


def watch(conn: sqlite3.Connection, source_key: str, moved_within_days: int = 7) -> dict:
    """What needs the owner, counted once — the watch strip above the table.

    Three queries, not five: the offer-scoped counts share one pass over the
    latest-per-offer join, and the period tables are asked once each. Five
    separate COUNT(*)s over that correlated subquery would be five full scans to
    render one strip.

    Every count is DERIVED from the same rows the table shows, so a tile and the
    page it links to can never disagree. A tile whose number does not match the
    list it opens teaches the owner to distrust both.
    """
    from datetime import date, timedelta

    cutoff = (date.today() - timedelta(days=max(1, moved_within_days))).isoformat()
    result = {"total": 0, "state_not_derived": 0, "needs_curation": 0,
              "moved": 0, "missing": 0, "history_built": True}

    row = conn.execute(
        "SELECT COUNT(*), "
        # A NULL offer_state is NOT "confirmed" — _LATEST_PER_OFFER joins it
        # LEFT precisely because an offer whose state has not been derived still
        # has a price. Folding those into "confirmed" would under-report exactly
        # the staleness this strip exists to surface.
        "       SUM(CASE WHEN ost.last_confirmed_at IS NULL THEN 1 ELSE 0 END), "
        "       SUM(CASE WHEN sp.curation_status = 'inventoried' THEN 1 ELSE 0 END) "
        f"{_LATEST_PER_OFFER}", (source_key,)).fetchone()
    if row:
        result["total"] = int(row[0] or 0)
        result["state_not_derived"] = int(row[1] or 0)
        result["needs_curation"] = int(row[2] or 0)

    try:
        built = conn.execute(
            "SELECT COUNT(*) FROM price_period pp "
            "JOIN source_offer so ON so.offer_id = pp.offer_id "
            "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
            "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
            "JOIN source_site ss ON ss.source_id = sp.source_id "
            "WHERE ss.source_key = ?", (source_key,)).fetchone()[0]
        # price_period is DERIVED and only filled by a rebuild. Empty means
        # "not built yet", which is a different answer from "nothing moved" —
        # reporting a bare 0 for both would be a lie of omission.
        result["history_built"] = bool(built)
        result["moved"] = int(conn.execute(
            "SELECT COUNT(DISTINCT pp.offer_id) FROM price_period pp "
            "JOIN source_offer so ON so.offer_id = pp.offer_id "
            "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
            "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
            "JOIN source_site ss ON ss.source_id = sp.source_id "
            "WHERE ss.source_key = ? AND pp.first_detected_at >= ? "
            "AND pp.opened_because = 'price_change'", (source_key, cutoff)).fetchone()[0])
        result["missing"] = int(conn.execute(
            "SELECT COUNT(*) FROM absence_period ap "
            "JOIN source_offer so ON so.offer_id = ap.offer_id "
            "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
            "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
            "JOIN source_site ss ON ss.source_id = sp.source_id "
            "WHERE ss.source_key = ? AND ap.returned_at IS NULL",
            (source_key,)).fetchone()[0])
    except sqlite3.DatabaseError:
        # A warehouse older than migration 0016 has neither table. Saying so is
        # correct; pretending the counts are zero is not.
        result["history_built"] = False
    return result


# The whole table, for a browser that filters and groups it in place. Bounded —
# large, but a number, not "everything" (A8). A source past this cap says so
# rather than quietly showing a prefix and letting the reader believe it is all.
TABLE_ROW_CAP = 20_000


def table_payload(conn: sqlite3.Connection, source_key: str,
                  limit: int = TABLE_ROW_CAP) -> dict:
    """Every row of one source, shaped for a client-side grid.

    Deliberately LEANER than browse_observations' shape. The tax verdict, its
    sentence and its source URL are identical for every row sharing a region —
    sending them per row cost about a third of the payload for nothing. They
    travel once, keyed by region, and the grid joins them.

    The tree grouping is decided HERE rather than in the template, because it
    depends on what the source actually publishes: a commodity source has one
    row per (material, country) and reads naturally as material -> countries,
    while a shop has products and variants.
    """
    limit = max(1, min(limit, TABLE_ROW_CAP))
    total = int(conn.execute(f"SELECT COUNT(*) {_LATEST_PER_OFFER}", (source_key,)).fetchone()[0])
    rows = conn.execute(
        "SELECT sp.source_name, sv.option_label, sv.external_sku, po.effective_price, "
        "       po.regular_price, po.sale_price, po.currency, po.availability, "
        "       po.business_date, sp.product_url, sp.curation_status, so.region, "
        "       ost.last_confirmed_at, su.unit_code, so.basis_quantity, so.offer_id "
        f"{_LATEST_PER_OFFER} ORDER BY sp.source_name, so.region LIMIT ?",
        (source_key, limit)).fetchall()

    tax_rules = tax.load_rules(conn, source_key)
    regions = {r[11] or "" for r in rows}
    tax_by_region = {region: tax.resolve(tax_rules, region).as_dict() for region in regions}

    shaped = [{"product_name": r[0], "option_label": r[1] or "", "sku": r[2] or "",
               "effective_price": r[3], "regular_price": r[4], "sale_price": r[5],
               "currency": r[6], "availability": r[7],
               "price_changed_on": r[8], "product_url": r[9] or "",
               "curation_status": r[10], "region": r[11] or "",
               "region_name": region_name(r[11]),
               "last_confirmed_on": (r[12] or "")[:10],
               "unit": price_unit(r[13], r[14]), "offer_id": r[15]}
              for r in rows]

    present = column_presence(conn, source_key)
    # Two independent questions, and both must be asked. `present` answers "does
    # this source publish anything here at all"; the saved view answers "does the
    # owner want to see it". Asking only the first is why Hide this column did
    # nothing: the choice was written to dataset_field and this payload — the only
    # thing the grid reads — never consulted it.
    wanted = set(fields.visible_columns(conn, source_key, fallback=list(present)))
    return {
        "source_key": source_key,
        "columns": [{"key": key, "label": label} for key, label in BROWSE_COLUMNS
                    if key in present and key in wanted],
        "rows": shaped,
        "tax_by_region": tax_by_region,
        "total": total,
        "returned": len(shaped),
        # A prefix presented as the whole is the failure this flag exists to
        # prevent; the page states it rather than looking complete.
        "truncated": total > len(shaped),
        "tree": _tree_shape(shaped),
    }


def _tree_shape(rows: list[dict]) -> dict:
    """How this source's rows nest, decided from what they actually contain.

    A commodity source carries one row per (material, country), so it reads as
    material -> countries: five rows that open into 169 instead of 721 flat
    ones. A source whose rows share no region has nothing to nest and says so,
    rather than being given a tree with one child each.
    """
    if not rows:
        return {"by": "", "child": ""}
    regions = {r["region"] for r in rows if r["region"] and r["region"] != "*"}
    names = {r["product_name"] for r in rows}
    # The region has to VARY for nesting by it to mean anything. A shop whose
    # every row is 'SA' would otherwise get a tree whose branch has one child
    # reading "Saudi Arabia" — more clicks to see the same list.
    if len(regions) > 1 and len(names) < len(rows):
        return {"by": "product_name", "child": "region_name"}
    return {"by": "", "child": ""}
