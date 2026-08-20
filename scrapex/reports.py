"""Read-only reports over harvest.db (ENGINEERING.md A8: bounded reads only).

The `peek` summary makes the two-layer warehouse legible: what landed in the
SOURCE-LOCAL layer (raw, as scraped) vs the UNIFIED layer (fills only after the
owner curates). This directly answers "did anything actually land?".
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from . import fields, tax
from .settings import business_day, get as _setting
from .normalize import option_axes_from
from .vocab import DETAIL_GROUP_ORDER


@dataclass
class SourceSummary:
    source_key: str
    # English, and required — the unmarked name is the primary one.
    source_name: str
    # The same name in Arabic when the site has one (0035). Carried here so a
    # listing or a heading shows both without a second query — empty for a
    # source that answers in one language, which the templates read as "nothing
    # to add" rather than an empty line.
    source_name_ar: str = ""
    # Display identity uses the source's host as its primary label. The full
    # URL remains available for links while templates strip it to the domain.
    base_url: str = ""
    # source-local layer (raw)
    products: int = 0
    variants: int = 0
    observations: int = 0
    curation: dict[str, int] = field(default_factory=dict)
    last_run: str | None = None
    last_status: str | None = None
    # The last run that actually SUCCEEDED, and what it measured — the freshness
    # of the data on screen, which is the first thing anyone asks and the one
    # fact the source cards were missing. None means it has never succeeded, a
    # real answer the card must state rather than paper over. Shape is
    # ingest.last_successful_run's dict.
    last_success: dict | None = None
    # unified layer (post-curation)
    matched_variants: int = 0
    published_rows: int = 0


def source_summary(conn: sqlite3.Connection, source_key: str) -> SourceSummary | None:
    row = conn.execute(
        "SELECT source_id, source_name_ar, source_name, base_url "
        "FROM source_site WHERE source_key = ?",
        (source_key,)
    ).fetchone()
    if row is None:
        return None
    source_id = row[0]
    s = SourceSummary(source_key=source_key, source_name=row[2] or "",
                      source_name_ar=row[1] or "", base_url=row[3] or "")

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
            "SELECT curation, COUNT(*) FROM source_product WHERE source_id = ? "
            "GROUP BY curation", (source_id,))
    }
    run = conn.execute(
        "SELECT started_at, status FROM crawl_run WHERE source_id = ? "
        "ORDER BY started_at DESC LIMIT 1", (source_id,)).fetchone()
    if run is not None:
        s.last_run, s.last_status = run[0], run[1]
    # The last SUCCESS, which is a different question from the last run: a source
    # whose most recent crawl failed still has data, and its freshness is the
    # date of the last good one. The ONE reader both this page and the panel use.
    from .ingest import last_successful_run
    s.last_success = last_successful_run(conn, source_key)

    s.matched_variants = _scalar(conn,
        "SELECT COUNT(*) FROM source_variant_match svm "
        "JOIN source_variant sv ON sv.source_variant_id = svm.source_variant_id "
        "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
        "WHERE sp.source_id = ? AND svm.review_status = 'approved' AND svm.valid_to IS NULL",
        (source_id,))
    s.published_rows = _scalar(conn,
        # The view publishes the ENGLISH name under the unmarked alias (0038).
        "SELECT COUNT(*) FROM v_material_price_tracking WHERE source_name = ?",
        (s.source_name,))
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
    # A superseded variant is history, not a current offer: the product-level
    # stand-in a per-variation upgrade replaced must leave the current-prices
    # table, the export, and every count derived from this join.
    "AND sv.status = 'active' "
    # The offer's face is what WE saw, newest first; a reported claim speaks
    # only for an offer with no observation at all. TWO indexed probes rather
    # than one expression-ordered subquery: ORDER BY (provenance='observed')
    # DESC is un-indexable, and the ten-year backfill made that lethal — 136k
    # observations x a ~500-row sort each froze every page for seconds
    # (measured live: 6.3s -> 0.06s for the identical result set). Each probe
    # is a seek on ix_price_obs_provenance (offer_id, provenance,
    # business_date DESC).
    "AND po.price_observation_id = COALESCE("
    "  (SELECT p2.price_observation_id FROM price_observation p2 "
    "   WHERE p2.offer_id = po.offer_id AND p2.provenance = 'observed' "
    "   ORDER BY p2.business_date DESC, p2.price_observation_id DESC LIMIT 1), "
    "  (SELECT p3.price_observation_id FROM price_observation p3 "
    "   WHERE p3.offer_id = po.offer_id AND p3.provenance = 'reported' "
    "   ORDER BY p3.business_date DESC, p3.price_observation_id DESC LIMIT 1))"
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


def price_basis(unit_code: str | None, weight, weight_unit: str | None,
                quantity_is_decimal) -> str:
    """'1,000 kg' — the WEIGHT a price is quoted against, when the source
    quotes it that way and names no unit. "" in every other case.

    THE PROBLEM THIS SOLVES, in the source's own numbers. madar's Ø8mm rebar
    member costs 4,830 and its Ø32mm member costs 4,045. Per piece that is
    impossible: a 12 m Ø8 bar is 4.7 kg of steel and a 12 m Ø32 bar is 75.8 kg,
    so those two figures would be 1,020 and 53 riyals a kilogram, on the same
    shelf. The shop states weight = 1000 on both — on all 96 members, whatever
    the diameter — and against that they are 4.83 and 4.05 a kilogram, thin
    dearer than thick, exactly as rolling mills price rebar. The number is only
    readable beside the weight, and until now nothing on the page carried it.

    WHAT THIS FUNCTION WILL NOT DO IS NAME THE UNIT. madar DECLARES none: its
    GraphQL schema has no `unit`, `uom` or `measure` field at all, and not one
    of the rebar member's 22 published attributes says what its price is quoted
    in. Its MARKETING PROSE is a different matter and must be recorded as such
    — measured on the crawl of 2026-07-30, seven of the nineteen products
    behind these offers print «سعر طن الحديد» in a meta field. That corroborates
    the reading and is still not a declaration: it is a search keyword on a
    parent product, it names no SKU and no figure, the other twelve say nothing,
    and promoting it would make the same 109 offers disagree with each other
    about a fact none of them states.

    So the Unit column beside this one stays EMPTY, because empty is the honest
    answer to "what unit did the shop state?", and what a reader sees here is
    two facts the shop did publish, side by side: its weight and its own word
    for the unit that weight is in. Nobody's inference is on screen.

    THREE CONDITIONS, and all three are the SOURCE's:

    1. The source states no selling unit. If it does, that IS the answer and
       price_unit() already gives it — riyadh cement says «50كجم» in the name
       AND weight 50, so it reads "50 kg" through the ordinary path and never
       reaches here. A stated unit always wins over an inferred basis.
    2. The source says the quantity is decimal. This is the load-bearing gate.
       All 3,418 madar leaves publish a weight (measured live 2026-07-30) and
       for 3,309 of them it is the mass of one piece — a steel angle's 4.986 kg
       — so weight alone would print "per 4.986 kg" across the whole shop,
       which is precisely the guess normalize.selling_unit_from was written to
       refuse. is_qty_decimal narrows it to 109.
    3. The source publishes a weight AND the unit of its weights. Both or
       neither: a number whose unit we failed to read is not shown as a bare
       number (ingest._quantity_facts stores the pair or nothing).

    Kept apart from price_unit() rather than folded into it because the two
    answer different questions and one of them has to be allowed to answer
    "nothing". Merging them would fill the Unit column with a word the shop
    never said, which is the whole defect.
    """
    if unit_code:
        return ""
    if not quantity_is_decimal:
        return ""
    if not weight_unit:
        return ""
    try:
        heavy = float(weight)
    except (TypeError, ValueError):
        return ""
    if heavy <= 0:
        return ""
    # Grouped so 1000 reads as a thousand at a glance — the whole point is that
    # this number is large, and "1000" beside a price is easy to read past.
    shown = f"{int(heavy):,}" if float(heavy).is_integer() else f"{heavy:,}"
    return f"{shown} {weight_unit}"


def _discounted(regular, effective) -> bool:
    try:
        return regular is not None and effective is not None and             float(regular) > float(effective)
    except (TypeError, ValueError):
        return False


def _discount_text(regular, effective) -> str:
    """"-104.83 (-7.0%)" — the discount the price already includes.

    The table shows the correct post-discount price; without this column
    nothing said a discount existed at all, which is the information the owner
    actually wanted. Absolute and percent together, same rule as the change
    feed. Empty when there is no discount — a zero would imply "checked, none",
    per row, in ink."""
    if not _discounted(regular, effective):
        return ""
    saved = float(effective) - float(regular)
    return f"{saved:+.2f} ({saved / float(regular) * 100:+.1f}%)"


# The same discount as two NUMBERS. The screen shows one chip because a chip is
# read, not calculated; a spreadsheet column is calculated, and "-84.67 (-7.0%)"
# in one cell can be neither summed nor sorted (owner's report). Same rule as
# the text form: empty, not zero, when there is no discount.
def _discount_amount(regular, effective):
    if not _discounted(regular, effective):
        return ""
    return round(float(effective) - float(regular), 2)


def _discount_pct(regular, effective):
    if not _discounted(regular, effective):
        return ""
    return round((float(effective) - float(regular)) / float(regular) * 100, 1)


def _change_text(previous, current) -> str:
    """The move from the PREVIOUS price to the current one: "+5.00 (+32.3%)".

    Previous means the last value that DIFFERED — with change-only history the
    point immediately before the current price took hold. Empty when the offer
    has never moved: a zero would claim "checked, no move" in ink on every
    static row."""
    try:
        before, now = float(previous), float(current)
    except (TypeError, ValueError):
        return ""
    if not before:
        return ""
    return f"{now - before:+.2f} ({(now - before) / before * 100:+.1f}%)"


def _usd_value(amount, currency, per_usd) -> str:
    """The price in dollars via the publisher's own implied rate, or "".

    Approximate by construction (the rate is the source's arithmetic, sampled
    at crawl time) and exists to make 128 currencies RANKABLE in one column.
    A USD row passes through unchanged; an unknown currency stays empty rather
    than pretending."""
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return ""
    if (currency or "").upper() == "USD":
        return f"{value:.2f}"
    try:
        rate = float(per_usd)
    except (TypeError, ValueError):
        return ""
    if rate <= 0:
        return ""
    return f"{value / rate:.2f}"


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
        clause += (" AND (sp.product_name_ar LIKE ? OR sp.product_name LIKE ? "
                   "OR so.country_code_alpha2 LIKE ?")
        params += [f"%{search}%", f"%{search}%", f"%{search}%"]
        code = region_code(search)
        if code:
            clause += " OR so.country_code_alpha2 = ?"
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
        elif key == "country_code_alpha2" and operator == "is":
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
# and SORTABLE quietly omitted last_confirmed and curation: two columns
# the page rendered with no way to order by them, and nothing said so.
#
# kind decides what control the header offers:
#   text    free text, matched with LIKE
#   exact   a bounded domain (a CHECK constraint or ISO codes) -> a <select>
#   number  a numeric comparison
#   date    a date comparison
#   derived computed in PYTHON after the query, so SQL cannot filter it at all
FILTERABLE: dict[str, tuple[str, str]] = {
    "product_name": ("sp.product_name", "text"),
    "product_name_ar": ("sp.product_name_ar", "text"),
    "country_code_alpha2": ("so.country_code_alpha2", "exact"),
    "variant_ar": ("sv.variant_ar", "text"),
    "variant": ("sv.variant", "text"),
    "sku": ("sv.external_sku", "text"),
    "price": ("po.price", "number"),
    "availability": ("po.availability", "exact"),
    "price_changed_on": ("po.business_date", "date"),
    "last_confirmed_on": ("ost.last_confirmed_at", "date"),
    "curation": ("sp.curation", "exact"),
    # Computed in Python — price_unit() and tax.resolve(), the latter with a
    # region->wildcard fallback and valid_to temporality. Reimplementing that in
    # SQL and keeping the two in agreement across 169 regions is a correctness
    # trap, so these are honestly marked unfilterable rather than half-supported.
    "unit": ("", "derived"),
    "tax": ("", "derived"),
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
    # so.country_code_alpha2 is always the final tiebreak: commodity rows share a source_name,
    # and without it their order is not stable between identical queries.
    return f"ORDER BY {column} {way}, sp.product_name_ar, so.country_code_alpha2"


def business_zone(conn: sqlite3.Connection) -> str:
    """The declared business-day zone, read once per report.

    Every server-side date in this module goes through business_day() with this
    value. Read here rather than at each call site so a report cannot answer
    with one boundary in a column and another in the row beside it.
    """
    return _setting(conn, "business_day_zone")


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
        "SELECT sp.product_name_ar, sv.variant_ar, sv.external_sku, po.price, "
        "       po.price_before, po.price_sale, po.currency, po.availability, po.tax_included, "
        "       po.business_date, sp.product_link, sp.curation, so.country_code_alpha2, "
        "       ost.last_confirmed_at, su.unit_code, so.basis_quantity, so.offer_id, "
        # Appended LAST: every index above is positional. The tax rules are
        # keyed on the name the SOURCE publishes, whichever language that is.
        "       COALESCE(NULLIF(sp.product_name,''), sp.product_name_ar), "
        # Appended LAST again (0052), for the same reason.
        "       po.price_trade, "
        # Appended LAST again (0057). The weight a price is quoted against and
        # the shop's own word for its unit, plus the flag that says the shop
        # sells this by a divisible quantity — three facts that only mean
        # something together, so they travel together.
        "       so.quantity_is_decimal, so.weight, so.weight_unit "
        f"{_LATEST_PER_OFFER}{filt} {_order_by(sort, direction)} LIMIT ? OFFSET ?",
        [*base_params, limit, offset],
    ).fetchall()
    tax_rules = tax.load_rules(conn, source_key)
    _zone = business_zone(conn)
    shaped = [
        {"product_name_ar": r[0], "variant_ar": r[1], "sku": r[2], "price": r[3],
         "price_before": r[4], "price_sale": r[5], "currency": r[6], "availability": r[7],
         "price_trade": r[18],
         "tax_included": bool(r[8]), "price_changed_on": r[9], "product_link": r[10],
         "curation": r[11], "country_code_alpha2": r[12] or "", "country": region_name(r[12]),
         # When the price was last CONFIRMED, which is not when it last changed.
         "last_confirmed_on": business_day(r[13], _zone),
         # A price without its unit is not a comparable number: 325 per tonne and
         # 325 per bag are different facts that look identical on screen.
         "unit": price_unit(r[14], r[15]),
         # ...and where the source states NO unit but does state a weight it
         # prices by, what that weight is. The two never both fill: a stated
         # unit is the answer, and this is what stands in when there is none.
         "price_basis": price_basis(r[14], r[20], r[21], r[19]),
         # Resolved per ROW because one source can hold a different tax position
         # per country. Rules are loaded once above, never queried per row.
         # for_row() then reads that evidence for THIS figure: the rule owns the
         # rate and the statement, the row owns incl/excl. Without it a madar
         # table labelled its 328 tax-EXCLUSIVE configurable prices "Incl. 15%"
         # alongside its 399 inclusive simple ones.
         **tax.resolve(tax_rules, r[12], material=r[17]).for_row(bool(r[8])).as_dict(),
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
# Logical order (owner's ruling): identity -> classification -> the price
# block -> its history -> operational meta. The history block answers, left to
# right, "what is it now, what would that be in dollars, what was it before,
# how did it move, and what range has it lived in".
# HOW DEEP a classification may be split into its own columns. Not dynamic and
# never was: the levels used to be four names typed by hand, so a source filing
# products six deep had its fifth and sixth levels shown only inside the
# full-path Category column. Nothing was lost, but nothing could sort or group
# by them either. This is the one number that decides it, and the presence gate
# still hides every level a source does not actually reach — MADAR reaches 3
# today and SIKAEGSHOP 1, so raising the ceiling adds no empty columns to
# either. Raising it further is one line.
CATEGORY_LEVELS = 10


def _level_columns() -> list[tuple[str, str]]:
    """The classification levels as columns, English then Arabic, level by
    level, so a pair sits together instead of in two distant blocks."""
    columns: list[tuple[str, str]] = []
    for level in range(1, CATEGORY_LEVELS + 1):
        columns.append((f"category_l{level}", f"Category L{level}"))
        columns.append((f"category_l{level}_ar", f"Category L{level} (AR)"))
    return columns


BROWSE_COLUMNS: list[tuple[str, str]] = [
    # The two languages of one field sit TOGETHER, English first. They used to
    # be filed in separate blocks — every English column, then Country, then
    # every Arabic one — so a bilingual shop showed Record (AR), Record,
    # Category, Country, Category (AR): the same fact twice with an unrelated
    # column wedged between. The label for each pair is written once, by
    # BILINGUAL_COLUMNS below. The "(AR)" is AUTHORED into the label, not
    # appended at runtime: the mark is a property of the column, not of the
    # pair, so an Arabic-only source is still told which language it is
    # reading. (It also makes /api/fields and the grid agree by construction
    # rather than by both remembering to run the same loop.)
    ("product_name", "Product name"),
    ("product_name_ar", "Product name (AR)"),
    ("country_code_alpha2", "Country code"),
    ("brand", "Brand"),
    ("brand_ar", "Brand (AR)"),
    # Classification (owner ruling 2026-07-22): part of the MAIN table, with
    # every level the source publishes. "category" carries the source's full
    # path ("Cables > Low voltage") or, for a source that only files products
    # under flat labels, the labels themselves. The per-level columns split
    # the path so the table can sort and group by any layer; presence gating
    # keeps each level to the sources that actually reach that depth.
    ("category", "Category"),
    ("category_ar", "Category (AR)"),
    # The DEEPEST level this row actually reaches, in one column. The owner's
    # ask (2026-07-28): «عاوز عمود يكون مجمع اخر تصنيف لكل صف» — sources like
    # MADAR and ADVANCEDCASTLE classify to different depths row by row, so no
    # single Category L-column holds "the most specific thing this is". Reading
    # it off the row means never asking which level to look in.
    ("category_leaf", "Category leaf"),
    ("category_leaf_ar", "Category leaf (AR)"),
    *_level_columns(),
    ("variant", "Variant"),
    ("variant_ar", "Variant (AR)"),
    ("sku", "SKU"),
    ("price", "Price"),
    # Derived from currency_rate (the publisher's own implied rates) so 128
    # currencies can be RANKED in one column. Approximate by nature and
    # labelled so.
    ("price_trade", "Trade price"),
    ("price_usd", "Price (USD est.)"),
    # The price that held immediately before the current one, and the move
    # between them. Different questions from the DISCOUNT (which is within
    # one listing, was -> sale) — this is across TIME.
    ("price_previous", "Previous price"),
    ("price_change", "Price change"),
    ("price_min", "Lowest price"),
    ("price_max", "Highest price"),
    ("observations", "Observations"),
    # The pre-discount price rides INSIDE the price cell, struck through beside
    # the current one (the owner's asked-for shape) — a separate Was column
    # would state the same number twice. The discount itself is TWO columns,
    # matching the export: one cell reading "-84.67 (-7.0%)" can be neither
    # sorted by size nor by severity, and the owner asked for the split in both
    # places rather than in one.
    ("discount", "Discount"),
    ("discount_pct", "Discount %"),
    ("unit", "Unit"),
    ("availability", "Availability"),
    ("tax", "Tax"),
    ("price_changed_on", "Price changed on"),
    ("last_confirmed_on", "Last confirmed on"),
    # The official body the source names for its figure. Only sources that
    # actually attribute (GPP country pages) populate it; the presence sweep
    # hides it everywhere else.
    ("official_source", "Official source"),
    ("curation", "Curation"),
    # Last, and narrow: the arrow that opens the record on the site itself.
    # It replaced a Details column — the details now open UNDER the table
    # when a row is selected, so a column for them was a second door to a
    # room the row already opens (owner's ruling).
    #
    # Named `product_link` since 0051, the same key the export uses: the arrow
    # and the export's URL column were one fact (the link to the record on the
    # site) arriving down two seeding paths that never reconciled, and
    # dataset_field allows one row per (source, key). The label stays blank —
    # the cell is an icon, and the schema page reads the label from the export
    # list where it is written out in full.
    ("product_link", ""),
]

# The bilingual pairs, declared ONCE (owner's standing rule: a site that
# publishes both languages is captured in both). Everything downstream reads
# this map — the presence gates, the payload keys and the grid's AR|EN
# toggle — so adding a bilingual field is one line, not five edits.
# Orientation is {arabic: english} and must stay that way — grid.js
# destructures `for (const [arabic, english] of pairs)`.
BILINGUAL_COLUMNS: dict[str, str] = {
    "product_name_ar": "product_name",
    # ALSWEED publishes «لوكسيفاي» beside "LUXIFY" and madar «هيونداي»
    # beside "Hyundai Power Products" — one brand, two languages, so the
    # one switch that governs the page governs this too (0047).
    "brand_ar": "brand",
    # The variation reads «العرض (ملم): 610» in Arabic and "Width (mm): 610" in
    # English, and madar publishes both — so the switch flips it too.
    "variant_ar": "variant",
    "category_ar": "category",
    "category_leaf_ar": "category_leaf",
    **{f"category_l{level}_ar": f"category_l{level}"
       for level in range(1, CATEGORY_LEVELS + 1)},
}


# Never hidden by the emptiness sweep: without it the table is not a price
# list at all.
ESSENTIAL_COLUMNS = frozenset({"price"})

# ONE of these always survives too — a row that cannot be identified is not a
# shorter table, it is not a table. WHICH one survives is the source's choice
# of language, which is exactly what the marked names now make visible.
NAME_COLUMNS = frozenset({"product_name", "product_name_ar"})


def column_presence(conn: sqlite3.Connection, source_key: str) -> set[str]:
    """Which browse columns this source actually populates.

    Answers the review's key question — "when a source supplies no brand or SKU,
    does the table still show those columns?" — with data rather than a guess.
    ONE aggregate over the latest-per-offer set, not a query per column.

    A source that publishes no variants, no SKU and no unit should not be given
    three columns of em-dashes to read past.

    INVARIANT (owner ruling 2026-07-22): every gate here asks THIS source's own
    rows — never a global table. The engine is shared; the column state is per
    source. The one global gate this function ever had (price_usd checked
    whether currency_rate had ANY rows) put a fuel-implied USD estimate on
    every shop's table the moment GPP landed its first rate.
    """
    row = conn.execute(
        "SELECT COUNT(NULLIF(TRIM(COALESCE(sv.variant_ar,'')),'')), "
        "       COUNT(NULLIF(TRIM(COALESCE(sv.external_sku,'')),'')), "
        "       COUNT(NULLIF(TRIM(COALESCE(so.country_code_alpha2,'')),'')), "
        "       COUNT(so.selling_unit_id), "
        # 'unknown' is a non-empty string that states nothing. Counting it as
        # present gave GPP a Status column reading "Unknown" on all 721 rows —
        # a column of noise. No information is not information.
        "       COUNT(NULLIF(NULLIF(TRIM(COALESCE(po.availability,'')),''),'unknown')), "
        "       COUNT(NULLIF(TRIM(COALESCE(po.official_source_name,'')),'')), "
        "       COUNT(NULLIF(TRIM(COALESCE(sp.brand,'')),'')), "
        "       SUM(CASE WHEN po.price_before > po.price THEN 1 ELSE 0 END), "
        "       COUNT(DISTINCT po.currency), "
        "       COUNT(NULLIF(TRIM(COALESCE(sp.product_name,'')),'')), "
        # Appended LAST, like every count before it: this list is read by
        # position, and a column inserted mid-list shifts every index under it.
        "       COUNT(NULLIF(TRIM(COALESCE(sv.variant,'')),'')), "
        # Appended LAST again: the ENGLISH name is empty on an Arabic-only
        # source, which it never was while this column held Arabic.
        "       COUNT(NULLIF(TRIM(COALESCE(sp.product_name_ar,'')),'')), "
        # Appended LAST, as every count before it: the Arabic brand is
        # empty on MASDAR and full on SAMEHGABRIEL, so the two halves are
        # gated apart or one source shows a column of nothing.
        "       COUNT(NULLIF(TRIM(COALESCE(sp.brand_ar,'')),'')) "
        f"{_LATEST_PER_OFFER}", (source_key,)).fetchone()
    present = {key for key, _ in BROWSE_COLUMNS}
    for column, count in (("variant_ar", row[0]), ("sku", row[1]),
                          ("country_code_alpha2", row[2]), ("unit", row[3]),
                          ("availability", row[4]), ("official_source", row[5]),
                          ("brand", row[6]), ("discount", row[7]),
                          ("discount_pct", row[7]),
                          ("product_name", row[9]), ("variant", row[10]),
                          ("product_name_ar", row[11]), ("brand_ar", row[12])):
        if not count:
            present.discard(column)
    # USD est. exists to make many currencies RANKABLE in one column. A source
    # whose prices are all in ONE currency is already rankable by its own Price
    # column — showing it a converted twin (through rates implied by a fuel
    # site's arithmetic, no less) is exactly the cross-source leak the owner
    # reported. Multi-currency alone is not enough either: without a single
    # relevant rate the column would render empty on every non-USD row.
    if (row[8] or 0) < 2:
        present.discard("price_usd")
    else:
        relevant_rates = conn.execute(
            "SELECT COUNT(*) FROM currency_rate WHERE currency IN ("
            "  SELECT DISTINCT po.currency " + _LATEST_PER_OFFER + ")",
            (source_key,)).fetchone()[0]
        if not relevant_rates:
            present.discard("price_usd")
    if not conn.execute(
            "SELECT COUNT(NULLIF(TRIM(COALESCE(sp.product_link,'')),'')) "
            f"{_LATEST_PER_OFFER}", (source_key,)).fetchone()[0]:
        present.discard("product_link")
    details = conn.execute(
        "SELECT COUNT(*), "
        # The language mark (0050) rides the code, so the match has to allow
        # it: a shop that files in Arabic stores 'category_ar'. Matching the
        # bare literal silently gated the flat-category column off the one
        # source that has it.
        "SUM(CASE WHEN spa.attribute_code IN ('category','category_ar') "
        "         THEN 1 ELSE 0 END) "
        "FROM source_product_attribute spa "
        "JOIN source_product sp ON sp.source_product_id = spa.source_product_id "
        "JOIN source_site ss ON ss.source_id = sp.source_id "
        "WHERE ss.source_key = ?", (source_key,)).fetchone()

    # Classification depth is per source, from its own products (the same
    # invariant as price_usd): a source whose deepest path is two levels gets
    # exactly L1 and L2, a flat-label shop gets the single Category column, a
    # source that classifies nothing gets none of them.
    def _depth_of(column: str) -> int:
        return conn.execute(
            f"SELECT MAX(LENGTH({column}) - LENGTH(REPLACE({column}, '>', '')) + 1) "
            "FROM source_product sp JOIN source_site ss ON ss.source_id = sp.source_id "
            f"WHERE ss.source_key = ? AND TRIM(COALESCE({column},'')) <> ''",
            (source_key,)).fetchone()[0] or 0

    depth_ar = _depth_of("category_path_ar")
    depth = _depth_of("category_path")
    if not depth:
        present.discard("category")
    for level in range(1, CATEGORY_LEVELS + 1):
        if depth < level or (level == 1 and depth < 2):
            # L1 alone would duplicate Category exactly; the split only earns
            # its columns once there is more than one level to split.
            present.discard(f"category_l{level}")
    # The Arabic branch keeps its own escape hatch — details[1] counts the
    # source_product_attribute rows coded 'category', which is how a shop
    # with flat labels and no path still gets a Category column. The two
    # branches are NOT symmetric on purpose: moving the hatch to the English
    # side would cost SAMEHGABRIEL the only classification column it has.
    if not details[1] and not depth_ar:
        present.discard("category_ar")
    for level in range(1, CATEGORY_LEVELS + 1):
        if depth_ar < level or (level == 1 and depth_ar < 2):
            present.discard(f"category_l{level}_ar")
    history = conn.execute(
        "SELECT MAX(n), MAX(distinct_prices) FROM ("
        "  SELECT COUNT(*) AS n, COUNT(DISTINCT po.price) AS distinct_prices "
        "  FROM price_observation po "
        "  JOIN source_offer so ON so.offer_id = po.offer_id "
        "  JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "  JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
        "  JOIN source_site ss ON ss.source_id = sp.source_id "
        "  WHERE ss.source_key = ? GROUP BY po.offer_id)", (source_key,)).fetchone()
    if not history[0] or history[0] < 2:
        # One observation per offer: nothing to call Min/Max/Previous.
        for column in ("price_previous", "price_change", "price_min",
                       "price_max", "observations"):
            present.discard(column)
    elif not history[1] or history[1] < 2:
        # Rows exist but every price identical — a range of one number.
        present.discard("price_previous")
        present.discard("price_change")
    if not conn.execute(
            "SELECT COUNT(po.price_trade) "
            f"{_LATEST_PER_OFFER}", (source_key,)).fetchone()[0]:
        # Eight shops in nine quote no trade tier, and a column of blanks is
        # not information. Asked of THIS source, never globally — the USD
        # est. leak was a global gate lighting a column up everywhere
        # because one source had the data.
        present.discard("price_trade")
    rate_known = conn.execute(
        "SELECT COUNT(*) FROM currency_rate").fetchone()[0]
    if not rate_known:
        present.discard("price_usd")
    return present


# WHICH publisher's rate the USD column uses when several priced one currency.
#
# A MARKET rate always wins. 0054 split provider from shop precisely because "a
# shop's rate is evidence about that shop, and must never be mistaken for a
# market rate" — and ordering by recency alone hands the whole USD column to
# whichever storefront happened to be crawled last. advancedcastle publishes a
# SAR/EGP ratio of 13.46 while pricing its own Egyptian pages at 11.768; a
# number like that must never convert some other source's prices.
#
# Recency alone was survivable only by accident: publisher-implied rates carry
# a DATE ("2026-07-29") and Google Finance a full timestamp, and text sorting
# puts the timestamp last, so the provider won without anyone arranging it. A
# shop rate stamped with a full read time ends that luck.
#
# A shop's rate is still USED where no rate service published one — that
# fallback is what ranks the 128 currencies GPP prices in — and the row carries
# the rate's source and date beside the number, so a reader can always see
# which kind they got (the owner's standing rule, 2026-07-26).
#
# No has_column branch here, unlike the WRITERS in ingest.py and rates.py: this
# is a read, a missing column fails loudly and at once instead of silently
# mis-ranking, and source_kind has been NOT NULL since 0054.
_RATE_BY_AUTHORITY = ("ORDER BY (cr.source_kind = 'provider') DESC, "
                      "cr.as_of DESC LIMIT 1")

# alias -> SQL expression. The SELECT list and the accessors below are built
# from ONE mapping, so a column can be added without counting tuple positions.
_EXPORT_SELECT: dict[str, str] = {
    "name": "sp.product_name_ar",
    "name_en": "sp.product_name",
    "option_label": "sv.variant_ar",
    "sku": "sv.external_sku",
    "external_product_id": "sp.external_product_id",
    # The VARIATION's own page (0037). A variable product's rows are one per
    # variation, so linking them all to the product's page sent five of every
    # six clicks to the wrong colour.
    "variant_url": "sv.variant_url",
    "price": "po.price",
    "price_before": "po.price_before",
    "price_sale": "po.price_sale",
    "price_trade": "po.price_trade",
    "currency": "po.currency",
    "availability": "po.availability",
    "tax_included": "po.tax_included",
    "business_date": "po.business_date",
    "product_link": "sp.product_link",
    "country_code_alpha2": "so.country_code_alpha2",
    "last_confirmed_at": "ost.last_confirmed_at",
    "unit_code": "su.unit_code",
    "basis_quantity": "so.basis_quantity",
    # The weight a price is quoted against, the shop's own word for its unit,
    # and the flag that says the shop sells this by a divisible quantity. Read
    # together by price_basis() and meaningless apart (0057).
    "quantity_is_decimal": "so.quantity_is_decimal",
    "weight": "so.weight",
    "weight_unit": "so.weight_unit",
    "brand": "sp.brand",
    "brand_ar": "sp.brand_ar",
    "category_path": "sp.category_path_ar",
    "category_flat": (
        "(SELECT GROUP_CONCAT(spa.raw_value, ', ') FROM source_product_attribute spa "
        " WHERE spa.source_product_id = sp.source_product_id "
        " AND spa.attribute_code IN ('category','category_ar'))"),
    "official_source": "po.official_source_name",
    "official_source_link": "po.official_source_link",
    "category_path_en": "sp.category_path",
    "option_axes": "sv.variant_axes_ar",
    "variant_en": "sv.variant",
    "option_axes_en": "sv.variant_axes",
    "curation": "sp.curation",
    # The history statistics the TABLE has always shown and the export
    # never carried. Scoped to the current observation's currency, exactly
    # as table_payload scopes them: after a currency flip, 0.40 USD in the
    # same Min column as 20.50 EGP is the corruption the flip guard exists
    # to prevent, and the guard has to hold in the spreadsheet too.
    "observations": ("(SELECT COUNT(*) FROM price_observation ph "
                     " WHERE ph.offer_id = so.offer_id AND ph.currency = po.currency)"),
    "price_min": ("(SELECT MIN(ph2.price) FROM price_observation ph2 "
                   " WHERE ph2.offer_id = so.offer_id AND ph2.currency = po.currency)"),
    "price_max": ("(SELECT MAX(ph3.price) FROM price_observation ph3 "
                   " WHERE ph3.offer_id = so.offer_id AND ph3.currency = po.currency)"),
    "price_previous": ("(SELECT ph4.price FROM price_observation ph4 "
                        " WHERE ph4.offer_id = so.offer_id "
                        " AND ph4.currency = po.currency "
                        " AND ph4.price != po.price "
                        " ORDER BY ph4.business_date DESC, "
                        "          ph4.price_observation_id DESC LIMIT 1)"),
    "per_usd": ("(SELECT cr.per_usd FROM currency_rate cr "
                 " WHERE cr.currency = po.currency "
                 f" {_RATE_BY_AUTHORITY})"),
    # Not an exported column: the key the site's own filter values are joined on.
    "source_product_id": "sp.source_product_id",
}

# The exported COLUMN NAME and the value that fills it, declared side by side.
#
# This used to be two parallel lists — a header constant and a list of tuple
# indexes built somewhere else — and they drifted. `product_name_en` was added
# to the header without a matching value, so every export since shifted by one:
# the region code was published under `product_name_en`, the country name under
# `region`, `country` came out empty, and the English product name landed in
# `country`. The spreadsheet cannot notice that; the owner did, from a row of
# copper cable. Pairing the name with its producer makes that class of defect
# impossible rather than merely fixed once.
EXPORT_COLUMNS: list[tuple[str, "Callable[[dict, object], object]"]] = [
    # Identity. region/country sit right after the name: for a commodity source
    # they are what distinguishes one row from the next.
    ("product_name", lambda r, s: r["name_en"] or ""),
    # No fallback, deliberately: a source that publishes no English name
    # leaves this blank. Filling it from the Arabic would put Arabic under
    # an English heading and undo the whole point of marking the columns.
    ("product_name_ar", lambda r, s: r["name"] or ""),
    ("country_code_alpha2", lambda r, s: (r["country_code_alpha2"] or "") if r["country_code_alpha2"] != "*" else ""),
    ("country", lambda r, s: region_name(r["country_code_alpha2"])),
    ("brand", lambda r, s: r["brand"] or ""),
    ("brand_ar", lambda r, s: r["brand_ar"] or ""),
    # path-or-flat-labels is NOT a language fallback — both are the same
    # language, and a shop with flat labels and no path has only the labels.
    ("category", lambda r, s: r["category_path_en"] or ""),
    ("category_ar", lambda r, s: r["category_path"] or r["category_flat"] or ""),
    # The product this row's variant belongs to. Six variations of one cable
    # arrive as six rows whose SKUs differ only in the suffix (…-1 … …-6); this
    # is the id they share, so a spreadsheet can group them without parsing.
    ("product_id", lambda r, s: r["external_product_id"] or ""),
    # English first, the Arabic beside it — the same pair convention the table
    # uses, and the same fallback: a source that publishes one language fills
    # one column instead of leaving the reader a blank.
    # No language fallback here either. 269 variants (MADAR 161,
    # SAMEHGABRIEL 108) have an Arabic variation and no English one; the old
    # `variant_en or option_label` published their Arabic under the English
    # heading. Blank is the truthful answer.
    ("variant", lambda r, s: r["variant_en"] or ""),
    ("variant_ar", lambda r, s: r["option_label"] or ""),
    ("sku", lambda r, s: r["sku"] or ""),
    ("price", lambda r, s: _or_blank(r["price"])),
    # The unit sits beside the price it qualifies. A column of bare numbers
    # where some are per tonne and some per bag is not a price list, it is a
    # trap.
    ("unit", lambda r, s: price_unit(r["unit_code"], r["basis_quantity"])),
    # ...and the column that fills in where the source states no unit but does
    # price by a weight. The pair is deliberately TWO columns that never both
    # fill: "what unit did the shop state?" and "what weight is this price
    # quoted against?" are different questions, and the first one is allowed to
    # answer nothing. Folding them into one cell would put the word "kg" under
    # a heading that means "the shop said this", for a shop that did not.
    #
    # It has to be in the FILE and not only on screen for the reason the Unit
    # column exists at all: a spreadsheet of bare numbers where 4,830 is per
    # 1,000 kg and 30.19 is per sheet is not a price list, it is a trap — and
    # the export is the record leaving the building.
    ("price_basis", lambda r, s: price_basis(r["unit_code"], r["weight"],
                                             r["weight_unit"],
                                             r["quantity_is_decimal"])),
    ("price_before", lambda r, s: _or_blank(r["price_before"])),
    ("price_sale", lambda r, s: _or_blank(r["price_sale"])),
    ("price_trade", lambda r, s: _or_blank(r.get("price_trade"))),
    # The discount as TWO numbers, not one sentence. "-84.67 (-7.0%)" in a
    # single cell cannot be summed, sorted or filtered by a spreadsheet, which
    # is the only reason the column exists (owner's report). Both stay empty
    # when there is no discount — a zero would claim "checked, none" in ink.
    ("discount", lambda r, s: _discount_amount(r["price_before"], r["price"])),
    ("discount_pct", lambda r, s: _discount_pct(r["price_before"], r["price"])),
    ("currency", lambda r, s: r["currency"] or ""),
    ("availability", lambda r, s: r["availability"] or ""),
    # tax_included alone was a claim with no source. The three columns beside
    # it say how well we actually know it, and where the owner can go and read
    # it. tax_included is per ROW: one source can publish both states.
    ("tax_included", lambda r, s: "yes" if r["tax_included"] else "no"),
    ("tax_evidence", lambda r, s: s.evidence),
    ("tax_rate_pct", lambda r, s: s.rate_pct if s.rate_pct is not None else ""),
    ("tax_statement", lambda r, s: s.statement_url),
    # price_changed_on is when the price last MOVED; last_confirmed_on is when
    # a completed run last saw it still true. They are different questions, and
    # publishing only the first made a confirmed price look stale.
    ("price_changed_on", lambda r, s: r["business_date"] or ""),
    # Derived onto the row by export_source_table, which is where the
    # connection — and therefore the declared zone — actually is.
    ("last_confirmed_on", lambda r, s: r["last_confirmed_on"]),
    # The official body the source names for its figure, when it names one.
    ("official_source", lambda r, s: r["official_source"] or ""),
    ("official_source_link", lambda r, s: r["official_source_link"] or ""),
    # The most specific address this row has: the variation's own page when the
    # source publishes one, the product's page otherwise. Storing the right link
    # and then exporting the wrong one would be the defect with extra steps.
    ("product_link", lambda r, s: r["variant_url"] or r["product_link"] or ""),
    # ---- everything the TABLE shows and the export used to drop -------
    # Owner ruling 2026-07-26: the exported main table carries EVERY
    # column, including the ones that are empty for this source. On screen
    # an empty column is noise to read past; in a spreadsheet an ABSENT
    # column is a formula that breaks and a header that moves between
    # sources. A stable full header costs a blank cell and buys a file the
    # owner can build on.
    ("tax", lambda r, s: s.label()),
    ("curation", lambda r, s: r["curation"] or ""),
    ("price_previous", lambda r, s: _or_blank(r["price_previous"])),
    ("price_change", lambda r, s: _change_text(r["price_previous"],
                                               r["price"])),
    ("price_min", lambda r, s: _or_blank(r["price_min"])),
    ("price_max", lambda r, s: _or_blank(r["price_max"])),
    ("observations", lambda r, s: r["observations"] or 0),
    ("price_usd", lambda r, s: _usd_value(r["price"], r["currency"],
                                          r["per_usd"])),
    # The row's own deepest level, in one column, because the levels below
    # answer "what is at L3" and this answers "what is this, most
    # specifically" — a different question wherever a source classifies to
    # different depths row by row.
    ("category_leaf", lambda r, s: _category_leaf(r["category_path_en"])),
    ("category_leaf_ar", lambda r, s: _category_leaf(r["category_path"])),
    # The classification split into its levels, exactly as the table
    # splits it, so a spreadsheet can pivot on a layer without parsing the
    # path. English then Arabic, level by level.
    *[(name, (lambda level, suffix, path_key: (
          lambda r, s: _category_levels(r[path_key]).get(f"category_l{level}", "")))(
              lvl, sfx, key))
      for lvl in range(1, CATEGORY_LEVELS + 1)
      for name, sfx, key in ((f"category_l{lvl}", "", "category_path_en"),
                             (f"category_l{lvl}_ar", "_ar", "category_path"))],
]

EXPORT_HEADER = [name for name, _ in EXPORT_COLUMNS]


def _or_blank(value):
    """Numbers stay numeric so Sheets sorts them; absence stays empty."""
    return value if value is not None else ""


def export_source_table(conn: sqlite3.Connection, source_key: str,
                        limit: int = 40_000) -> tuple[list[str], list[list]]:
    """Flat current-price table for one source (header + rows), ready to write to
    a Google Sheet tab. Reuses the shared latest-per-offer join (DRY) and is
    always bounded (A8). Numbers stay numeric so Sheets sorts/filters them."""
    aliases = list(_EXPORT_SELECT)
    select = ", ".join(f"{_EXPORT_SELECT[alias]} AS {alias}" for alias in aliases)
    rows = conn.execute(
        f"SELECT {select} {_LATEST_PER_OFFER} "
        # TRIM here decides the ORDER, never the content: the cells below are
        # written verbatim. Sorting on the raw column put MADAR's space-padded
        # names at the top of the file, ahead of everything, which is a fact
        # about their padding rather than about the products.
        "ORDER BY TRIM(sp.product_name_ar), so.country_code_alpha2 LIMIT ?",
        (source_key, limit),
    ).fetchall()
    tax_rules = tax.load_rules(conn, source_key)
    filters = _filter_values(conn, source_key)
    table = []
    parsed = []
    _zone = business_zone(conn)
    for raw in rows:
        row = dict(zip(aliases, raw))
        # The day this confirmation falls on, in the zone the owner declared —
        # the same value the screen and the filter use, so the sheet cannot
        # disagree with the page it was exported from.
        row["last_confirmed_on"] = business_day(row["last_confirmed_at"], _zone)
        # ...and read for THIS row's figure, so tax_evidence never contradicts
        # the tax_included cell two columns to its left.
        state = (tax.resolve(tax_rules, row["country_code_alpha2"],
                             material=row["name_en"] or row["name"])
                 .for_row(bool(row["tax_included"])))
        # Verbatim. The file says what the site published — a name with its
        # padding, a brand the shop published as a single space — because the
        # export is the record leaving the building, and a spreadsheet that
        # quietly tidies its source is a spreadsheet nobody can reconcile.
        table.append([produce(row, state) for _name, produce in EXPORT_COLUMNS])
        # The product's filterable attributes first, then this VARIANT's own
        # axes over them. Where a shop both filters by «السماكة (مم)» and varies
        # by it, the variant's value is the specific one — the product-level
        # attribute describes the family, and letting it win would print the
        # family's thickness on every one of its variants.
        merged = dict(filters.get(row["source_product_id"], {}))
        # The axes in the language the export is written in — English is the
        # primary display language, so the English axis NAMES head the columns
        # when the source publishes them, and the Arabic ones when it does not.
        merged.update(option_axes_from(row["option_axes_en"])
                      or option_axes_from(row["option_axes"]))
        parsed.append(merged)
    return _with_axis_columns(list(EXPORT_HEADER), table, parsed,
                              _filter_groups(conn, source_key))


def _filter_values(conn: sqlite3.Connection, source_key: str) -> dict[int, dict[str, str]]:
    """source_product_id -> {the site's filter label: this product's value}.

    The owner: the site offers filters on its listing pages and he wants columns
    for them, so he can slice the table the way the shop lets him slice its own.
    The connector asks the site which attributes those are (Magento answers
    `aggregations` with exactly its facet list) and files their values under the
    flags is_site_filter; here they become columns, named as the SHOP names them.

    OR the owner promoted it. Which detail deserved a column used to be
    decided entirely by the SHOP: madar gets 64 columns because Magento
    publishes its facet list, and sika got none of its 18 attribute codes
    because its shop publishes no facets at all. The mechanism was never
    the obstacle — the owner simply had no say in it (0044).

    Nothing is inferred: a source with neither flagged nor promoted
    attributes gets no such columns, and a product missing one of them gets
    an empty cell rather than a guess.
    """
    rows = conn.execute(
        "SELECT spa.source_product_id, "
        "       COALESCE(NULLIF(spa.attribute_label,''), spa.attribute_code), spa.raw_value "
        "FROM source_product_attribute spa "
        "JOIN source_product sp ON sp.source_product_id = spa.source_product_id "
        "JOIN source_site ss ON ss.source_id = sp.source_id "
        "WHERE ss.source_key = ? AND (spa.is_site_filter = 1 OR spa.attribute_code IN "
        "     (SELECT attribute_code FROM source_attribute_promotion "
        "       WHERE source_key = ?)) "
        "ORDER BY spa.source_product_id",
        (source_key, source_key)).fetchall()
    found: dict[int, dict[str, str]] = {}
    for product_id, label, value in rows:
        if label and value:
            found.setdefault(product_id, {})[str(label)] = str(value)
    return found


def _filter_groups(conn: sqlite3.Connection, source_key: str) -> dict[str, str]:
    """Map each site-named table column to its stored detail group."""
    rows = conn.execute(
        "SELECT DISTINCT "
        "       COALESCE(NULLIF(spa.attribute_label,''), spa.attribute_code), "
        "       COALESCE(spa.attribute_group, '') "
        "FROM source_product_attribute spa "
        "JOIN source_product sp ON sp.source_product_id = spa.source_product_id "
        "JOIN source_site ss ON ss.source_id = sp.source_id "
        "WHERE ss.source_key = ? AND (spa.is_site_filter = 1 OR spa.attribute_code IN "
        "     (SELECT attribute_code FROM source_attribute_promotion "
        "       WHERE source_key = ?))",
        (source_key, source_key)).fetchall()

    rank = {name: position for position, name in enumerate(DETAIL_GROUP_ORDER)}
    best: dict[str, str] = {}
    for label, group in rows:
        label = str(label or "")
        group = str(group or "")
        if not label:
            continue
        current = best.get(label)
        if current is None or rank.get(group, len(rank)) < rank.get(current, len(rank)):
            best[label] = group
    return best


def _group_sorted(labels: list[str], groups: dict[str, str]) -> list[str]:
    """Order detail columns by the UI group order, then by their site label."""
    rank = {name: position for position, name in enumerate(DETAIL_GROUP_ORDER)}
    return sorted(labels,
                  key=lambda label: (rank.get(groups.get(label, ""), len(rank)),
                                     label))


def _with_axis_columns(header: list[str], table: list[list],
                       parsed: list[dict], groups: dict[str, str] | None = None,
                       ) -> tuple[list[str], list[list]]:
    """The per-source columns: one per variation AXIS, one per site FILTER.

    Two owner reports with one answer. He exported a variable product and found
    `Color: أحمر` welded into one cell — a spreadsheet cannot filter, group or
    pivot on that, which is the only reason a column exists, and splitting the
    STRING at the far end was the fix he explicitly refused. And he found the
    site offering filters its own listing pages use, and wanted to slice the
    table the same ways.

    Both arrive here as dictionaries per row and leave as columns named the way
    the SITE names them ("Color", «السماكة (مم)», «التيار المقنّن (بالأمبير)»).

    The columns are per SOURCE, in first-seen order, because the facts are: a
    cable shop varies by colour, a steel shop by thickness and width, and each
    shop filters by what it sells. A source with neither gets no extra columns
    at all, so nothing gains an empty column for a shape it does not have.
    """
    names: list[str] = []
    for axes in parsed:
        for name in axes:
            if name not in names:
                names.append(name)
    if not names:
        return header, table
    if groups:
        axis_names = [name for name in names if name not in groups]
        filter_names = [name for name in names if name in groups]
        names = axis_names + _group_sorted(filter_names, groups)
    at = header.index("variant_ar") + 1
    widened = header[:at] + names + header[at:]
    rows = [row[:at] + [axes.get(name, "") for name in names] + row[at:]
            for row, axes in zip(table, parsed)]
    return widened, rows


# Both tabs carry BOTH name columns, like the price tab: they are enumerated
# on no page, so nothing else would ever tell you they had only one.
DETAILS_HEADER = ["product_name", "product_name_ar", "country_code_alpha2", "sku", "group",
                  "attribute", "value", "value_url", "last_seen_on"]
HISTORY_HEADER = ["product_name", "product_name_ar", "country_code_alpha2", "sku",
                  "business_date", "price", "currency", "provenance"]


def export_details_table(conn: sqlite3.Connection, source_key: str,
                         limit: int = 40_000) -> tuple[list[str], list[list]]:
    """Every detail this source published, one row per stated fact.

    The owner's report: an export carried the price table and NOTHING of the
    details or the history, so the spreadsheet held a third of what the page
    showed. Same bounded rule as every other read (A8)."""
    rows = conn.execute(
        "SELECT sp.product_name, sp.product_name_ar, so.country_code_alpha2, sv.external_sku, "
        "       spa.attribute_group, COALESCE(spa.attribute_label, spa.attribute_code), "
        "       spa.raw_value, spa.value_url, spa.last_seen_at "
        "FROM source_product_attribute spa "
        "JOIN source_product sp ON sp.source_product_id = spa.source_product_id "
        "JOIN source_site ss ON ss.source_id = sp.source_id "
        "JOIN source_variant sv ON sv.source_product_id = sp.source_product_id "
        "JOIN source_offer so ON so.source_variant_id = sv.source_variant_id "
        "WHERE ss.source_key = ? AND sv.status = 'active' "
        "GROUP BY spa.source_product_attribute_id "
        "ORDER BY sp.product_name, sp.product_name_ar, spa.attribute_group, "
        "         spa.attribute_label LIMIT ?",
        (source_key, limit)).fetchall()
    return list(DETAILS_HEADER), [
        [r[0] or "", r[1] or "", (r[2] or "") if r[2] != "*" else "", r[3] or "",
         r[4] or "Details", r[5] or "", r[6] or "", r[7] or "",
         business_day(r[8], business_zone(conn))]
        for r in rows]


def export_history_table(conn: sqlite3.Connection, source_key: str,
                         limit: int = 40_000) -> tuple[list[str], list[list]]:
    """Every price this source has published, oldest first per record."""
    rows = conn.execute(
        "SELECT sp.product_name, sp.product_name_ar, so.country_code_alpha2, sv.external_sku, "
        "       po.business_date, po.price, po.currency, po.provenance "
        "FROM price_observation po "
        "JOIN source_offer so ON so.offer_id = po.offer_id "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
        "JOIN source_site ss ON ss.source_id = sp.source_id "
        "WHERE ss.source_key = ? AND sv.status = 'active' "
        "ORDER BY sp.product_name, sp.product_name_ar, so.country_code_alpha2, "
        "         po.business_date LIMIT ?",
        (source_key, limit)).fetchall()
    return list(HISTORY_HEADER), [
        [r[0] or "", r[1] or "", (r[2] or "") if r[2] != "*" else "", r[3] or "",
         r[4] or "", r[5] if r[5] is not None else "", r[6] or "", r[7] or "observed"]
        for r in rows]


def recent_observations(conn: sqlite3.Connection, source_key: str, limit: int = 10) -> list[dict]:
    """A bounded sample of the source-local prices (A8: always LIMIT-ed)."""
    rows = conn.execute(
        "SELECT sp.product_name_ar, po.price, po.currency, po.availability, "
        "       po.tax_included, po.business_date, so.country_code_alpha2, su.unit_code, so.basis_quantity "
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
        {"product_name_ar": r[0], "price": r[1], "currency": r[2], "availability": r[3],
         "tax_included": bool(r[4]), "business_date": r[5],
         "country_code_alpha2": r[6] or "", "country": region_name(r[6]),
         "unit": price_unit(r[7], r[8])}
        for r in rows
    ]


def crawl_history(conn: sqlite3.Connection, source_key: str | None = None,
                  limit: int = 50) -> list[dict]:
    """Per-run history (spec 21 "Crawl History"). crawl_run has recorded this all
    along — status, counts, request budget, rows_seen — and nothing ever showed it."""
    sql = ("SELECT r.run_id, r.job_id, ss.source_key, ss.source_name_ar, "
           "       ss.source_name, ss.base_url, r.started_at, "
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
    # The same lesson the Data page learned, applied to both ends of the range:
    # one crawl stamps today's observed price AND the backfilled anchors with
    # one observed_at, so ordering by it made "first" the first INSERT (today's
    # price) and "current" the last INSERT (the oldest anchor). Egypt diesel
    # read First 20.5 -> Current 15.5, change -24.4%, when the source itself
    # states +32.3% over the year — every row's change inverted.
    #   first   = the earliest KNOWN price by the date it was FOR, anchors
    #             included: a First column that ignored the source's dated
    #             claims would call this week "the beginning of history".
    #   current = what we last SAW: observed outranks reported, then newest
    #             business_date — identical to the Data page's rule.
    # The current CURRENCY, by the same observed-first probes as the current
    # price. Every statistic below is scoped to it: after a currency flip,
    # first/min/max mixing USD and EGP amounts — or a Change computed across
    # them — is the corruption the flip guard exists to prevent, and it has
    # to hold on this page too, not only in the feed.
    current_currency = (
        "COALESCE("
        " (SELECT cc1.currency FROM price_observation cc1 "
        "  WHERE cc1.offer_id = so.offer_id AND cc1.provenance = 'observed' "
        "  ORDER BY cc1.business_date DESC, cc1.price_observation_id DESC LIMIT 1), "
        " (SELECT cc2.currency FROM price_observation cc2 "
        "  WHERE cc2.offer_id = so.offer_id AND cc2.provenance = 'reported' "
        "  ORDER BY cc2.business_date DESC, cc2.price_observation_id DESC LIMIT 1))")
    rows = conn.execute(
        "SELECT sp.product_name_ar, so.country_code_alpha2, po.currency, so.offer_id, "
        "       MIN(po.price) AS price_min, MAX(po.price) AS price_max, "
        "       COUNT(*) AS observations, "
        "       (SELECT p2.price FROM price_observation p2 WHERE p2.offer_id = so.offer_id "
        f"        AND p2.currency = {current_currency} "
        "        ORDER BY p2.business_date, p2.price_observation_id LIMIT 1) AS first_price, "
        "       COALESCE("
        "        (SELECT p3.price FROM price_observation p3 "
        "         WHERE p3.offer_id = so.offer_id AND p3.provenance = 'observed' "
        "         ORDER BY p3.business_date DESC, p3.price_observation_id DESC LIMIT 1), "
        "        (SELECT p4.price FROM price_observation p4 "
        "         WHERE p4.offer_id = so.offer_id AND p4.provenance = 'reported' "
        "         ORDER BY p4.business_date DESC, p4.price_observation_id DESC LIMIT 1)"
        "       ) AS current_price "
        "FROM price_observation po "
        "JOIN source_offer so ON so.offer_id = po.offer_id "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
        "JOIN source_site ss ON ss.source_id = sp.source_id "
        "WHERE ss.source_key = ? AND sv.status = 'active' "
        f"AND po.currency = {current_currency} "
        "GROUP BY so.offer_id "
        "ORDER BY sp.product_name_ar, so.country_code_alpha2 LIMIT ?",
        (source_key, max(1, min(limit, 2000))),
    ).fetchall()
    previous_by_offer = {
        r2[0]: r2[1] for r2 in conn.execute(
            "SELECT so.offer_id, "
            "  (SELECT ph.price FROM price_observation ph "
            f"   WHERE ph.offer_id = so.offer_id AND ph.currency = {current_currency} "
            "   AND ph.price != ("
            "     SELECT COALESCE("
            "      (SELECT c1.price FROM price_observation c1 "
            "       WHERE c1.offer_id = so.offer_id AND c1.provenance = 'observed' "
            "       ORDER BY c1.business_date DESC, c1.price_observation_id DESC LIMIT 1), "
            "      (SELECT c2.price FROM price_observation c2 "
            "       WHERE c2.offer_id = so.offer_id AND c2.provenance = 'reported' "
            "       ORDER BY c2.business_date DESC, c2.price_observation_id DESC LIMIT 1))) "
            "   ORDER BY ph.business_date DESC, ph.price_observation_id DESC LIMIT 1) "
            "FROM source_offer so "
            "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
            "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
            "JOIN source_site ss ON ss.source_id = sp.source_id "
            "WHERE ss.source_key = ? AND sv.status = 'active'", (source_key,))}
    out = []
    for r in rows:
        item = dict(r)
        item["country"] = region_name(item["country_code_alpha2"])
        first, current = item["first_price"], item["current_price"]
        # The Change column now answers the owner's question — the move from
        # the PREVIOUS price to the current one, not from the dawn of history.
        # First stays as context; with change-only storage, previous is the
        # point immediately before the current price took hold.
        previous = previous_by_offer.get(item.get("offer_id"))
        item["price_previous"] = previous
        item["change_abs"] = (None if previous is None
                              else round(current - previous, 6))
        item["change_pct"] = (None if not previous
                              else round((current - previous) / previous * 100, 2))
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
        "SELECT sp.product_name_ar, sv.variant_ar, sv.external_sku, so.country_code_alpha2, "
        "       so.currency, su.unit_code, so.basis_quantity, sp.product_link, "
        "       ss.source_key, sp.product_name, sv.variant, "
        # Appended LAST: the inspector prints the price too, so it needs the
        # same basis the table cell shows or the panel and the row disagree.
        "       so.quantity_is_decimal, so.weight, so.weight_unit "
        "FROM source_offer so "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
        "JOIN source_site ss ON ss.source_id = sp.source_id "
        "LEFT JOIN selling_unit su ON su.selling_unit_id = so.selling_unit_id "
        "WHERE so.offer_id = ? AND ss.source_key = ?",
        (offer_id, source_key)).fetchone()
    if row is None:
        return None
    return {"product_name": row[9] or "", "product_name_ar": row[0] or "",
            "variant": row[10] or "", "variant_ar": row[1] or "",
            "sku": row[2] or "",
            "country_code_alpha2": row[3] or "", "country": region_name(row[3]),
            "currency": row[4], "unit": price_unit(row[5], row[6]),
            "price_basis": price_basis(row[5], row[12], row[13], row[11]),
            "product_link": row[7] or "", "source_key": row[8],
            "offer_id": offer_id}


def product_attributes(conn: sqlite3.Connection, offer_id: int,
                       limit: int = 300) -> list[dict]:
    """The details the source printed for this offer's product, grouped as the
    page grouped them (A8 bounded). Source-local layer: exactly what the shop
    said, before any curation."""
    rows = conn.execute(
        "SELECT spa.attribute_group, spa.attribute_label, spa.attribute_code, "
        "       spa.raw_value, spa.value_url, spa.last_seen_at, spa.lang, "
        "       spa.numeric_value, spa.unit_raw "
        "FROM source_product_attribute spa "
        "JOIN source_variant sv ON sv.source_product_id = spa.source_product_id "
        "JOIN source_offer so ON so.source_variant_id = sv.source_variant_id "
        "WHERE so.offer_id = ? "
        "ORDER BY spa.attribute_group, spa.attribute_label, spa.raw_value LIMIT ?",
        (offer_id, max(1, min(limit, 1000)))).fetchall()
    _zone = business_zone(conn)
    # `code` and `lang` travel with every row so the panel can PAIR the two
    # languages of one fact (description + description_en) into ONE entry
    # instead of printing the same attribute twice. Connectors already keep the
    # languages in separate rows under distinct codes; that declaration is the
    # pairing key, so the browser never has to guess which rows are a pair.
    # `numeric`/`unit` come along for values that carry a measured quantity —
    # a datasheet's byte size, a weight — which the panel formats rather than
    # printing raw.
    return [{"group": r[0] or "Details", "label": r[1] or r[2], "value": r[3],
             "url": r[4] or "", "last_seen_at": business_day(r[5], _zone),
             "code": r[2] or "", "lang": r[6] or "",
             "numeric": r[7] or "", "unit": r[8] or ""} for r in rows]


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
        f"SELECT business_date, price, price_before, price_sale, currency, "
        f"       observed_at, {provenance} "
        "FROM price_observation WHERE offer_id = ? "
        "ORDER BY business_date DESC, price_observation_id DESC LIMIT ?",
        (offer_id, max(1, min(limit, 500)))).fetchall()
    return [{"business_date": r[0], "price": r[1], "price_before": r[2],
             "price_sale": r[3], "currency": r[4], "observed_at": r[5],
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
        "       SUM(CASE WHEN sp.curation = 'inventoried' THEN 1 ELSE 0 END) "
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


def _category_leaf(path: str | None) -> str:
    """The DEEPEST segment of a classification path — the row's own last level.

    MADAR classifies some rows to three levels and others to one; ADVANCEDCASTLE
    reaches six. So no single Category L-column answers "what is the most
    specific thing this row is": the answer sits in a different column for
    different rows, and a filter on L3 silently drops everything shallower.

    Read off the row rather than stored, because it is not a new fact — it is
    the last segment of a path the warehouse already holds. Nothing is invented
    and nothing needs a re-crawl. It also survives the CATEGORY_LEVELS ceiling:
    a path deeper than ten levels still reports its true last segment.
    """
    segments = [s.strip() for s in (path or "").split(">") if s.strip()]
    return segments[-1] if segments else ""


def _category_levels(path: str | None, prefix: str = "category_l",
                     suffix: str = "") -> dict[str, str]:
    """Split "Cables > Low voltage > Copper" into category_l1..lN.

    Always ALL the keys, so every row has the same shape (a grid that meets a
    ragged row invents undefineds). CATEGORY_LEVELS decides how many; the
    presence gate then hides every level a source never reaches, so a shop with
    one level shows one column and not ten empty ones. Anything deeper than the
    ceiling stays visible in the full-path Category column rather than being
    lost."""
    segments = [s.strip() for s in (path or "").split(">") if s.strip()]
    return {f"{prefix}{level}{suffix}": (segments[level - 1] if level <= len(segments) else "")
            for level in range(1, CATEGORY_LEVELS + 1)}


# The whole table, for a browser that filters and groups it in place. Bounded —
# large, but a number, not "everything" (A8). A source past this cap says so
# rather than quietly showing a prefix and letting the reader believe it is all.
TABLE_ROW_CAP = 20_000

# The variant identity: which of a product's variations this row is. These are
# the ONLY fields a fold is allowed to join, because joining them states exactly
# what the site published — "the site sells this at this price in red, blue and
# green" is true, where a joined price or stock would not be.
_FOLD_JOINED = ("variant_ar", "variant", "sku")
# History belongs to ONE offer. Across a folded group these are aggregates of
# different timelines, so they are recomputed for the group rather than carried
# from whichever row happened to come first.
_FOLD_MIN = "price_min"
_FOLD_MAX = "price_max"
# Kept from the first variant rather than blanked: the grid opens the record
# panel by offer_id, and a folded row with no offer_id would open nothing. The
# full list travels beside it as offer_ids.
_FOLD_KEPT = ("offer_id",)


def _shared_axis_once(values: list[str]) -> list[str]:
    """Say the axis name once when every value in the list carries it.

    A variant is stored the way the site labels it — "Color: أحمر". Joining six
    of those gives "Color: أحمر، Color: أخضر، Color: أرضي…", which repeats the
    word Color six times to say one thing. When EVERY value shares one label,
    the list reads "Color: أحمر، أخضر، أرضي" instead.

    Nothing is dropped and nothing is rewritten: the label is still printed, and
    the moment two values disagree about it — a product varying by colour AND by
    size — every value keeps its own, because then the label is information.
    """
    if len(values) < 2:
        return values
    split = [value.split(": ", 1) for value in values]
    if any(len(part) != 2 for part in split):
        return values
    labels = {part[0] for part in split}
    if len(labels) != 1:
        return values
    first = split[0]
    return [f"{first[0]}: {first[1]}"] + [part[1] for part in split[1:]]


def fold_variant_rows(rows: list[dict]) -> list[dict]:
    """Fold a product's same-priced variations into one row.

    The owner's case: samehgabriel publishes 18 products in 6 colours each, so
    the table showed 108 rows that differed only by colour. He asked for the
    variants to be listed together in one row instead — enabled per source,
    because MADAR's variations are a different kind of thing.

    WHAT THIS IS NOT. It does not change a single stored row: the warehouse
    keeps all 108, because what the site published is the record. This is the
    rule the owner set for exactly this situation — a rule decides where a fact
    is SHOWN, never what it says.

    THE GROUPING IS BY PRICE, NOT BY PRODUCT, and that matters: 17 of those 18
    products charge one price for every colour, but one charges two, and it
    correctly stays two rows. Nothing has to know in advance which colours are
    priced alike.

    A group folds only when the rows agree on everything else they display. Any
    field that differs and is not part of the variant's identity is left BLANK
    rather than guessed - a stock level or a discount that belonged to one
    colour must not be printed against six.

    The row keeps `offer_id` from its first variant so the record panel still
    opens, and gains `offer_ids` (all of them) and `variants` (how many were
    folded), so the surface can say what it is showing rather than imply that
    six colours are one offer.
    """
    groups: dict[tuple, list[dict]] = {}
    order: list[tuple] = []
    for row in rows:
        # THE COUNTRY IS PART OF THE KEY, and it has to be. GPP hangs many
        # countries off ONE source_product, so without it two countries that
        # happened to charge the same amount folded into a single row and the
        # country - the whole point of that table - came out blank. Measured on
        # the live data: 58 rows of GPP_ENERGY merged that way.
        key = (row.get("source_product_id"), row.get("price"),
               row.get("currency"), row.get("country_code_alpha2"))
        # A row with no product identity cannot be grouped with anything: give
        # it a key of its own rather than pooling every such row together.
        if key[0] is None:
            key = ("row", id(row))
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(row)

    folded: list[dict] = []
    for key in order:
        members = groups[key]
        if len(members) == 1:
            folded.append(members[0])
            continue
        merged = dict(members[0])
        for field in members[0]:
            if field in _FOLD_JOINED:
                seen: list[str] = []
                for member in members:
                    value = str(member.get(field) or "").strip()
                    if value and value not in seen:
                        seen.append(value)
                # An Arabic list reads with an Arabic comma; the rest with a
                # plain one. Same rule the columns already follow.
                separator = "، " if field.endswith("_ar") else ", "
                merged[field] = separator.join(_shared_axis_once(seen))
                continue
            if field in _FOLD_KEPT:
                continue
            values = [member.get(field) for member in members]
            if all(value == values[0] for value in values):
                continue
            if field in (_FOLD_MIN, _FOLD_MAX):
                numbers = [v for v in values if isinstance(v, (int, float))]
                if numbers:
                    merged[field] = min(numbers) if field == _FOLD_MIN else max(numbers)
                    continue
            merged[field] = ""
        merged["variants"] = len(members)
        merged["offer_ids"] = [m.get("offer_id") for m in members]
        folded.append(merged)
    return folded


def table_payload(conn: sqlite3.Connection, source_key: str,
                  limit: int = TABLE_ROW_CAP, fold_variants: bool = False) -> dict:
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
        "SELECT sp.product_name_ar, sv.variant_ar, sv.external_sku, po.price, "
        "       po.price_before, po.price_sale, po.currency, po.availability, "
        "       po.business_date, sp.product_link, sp.curation, so.country_code_alpha2, "
        "       ost.last_confirmed_at, su.unit_code, so.basis_quantity, so.offer_id, "
        "       po.official_source_name, po.official_source_link, sp.brand, "
        # Every history statistic is scoped to the CURRENT observation's
        # currency (po IS the latest row, so po.currency IS the current one):
        # after a currency flip, 0.40 USD in the same Min column as 20.50 EGP
        # — or a +5025% Change — is the corruption the flip guard exists to
        # prevent, and the guard has to hold HERE too, not only in the feed.
        "       (SELECT COUNT(*) FROM price_observation ph "
        "        WHERE ph.offer_id = so.offer_id "
        "        AND ph.currency = po.currency) AS observations, "
        "       (SELECT MIN(ph2.price) FROM price_observation ph2 "
        "        WHERE ph2.offer_id = so.offer_id "
        "        AND ph2.currency = po.currency) AS price_min, "
        "       (SELECT MAX(ph3.price) FROM price_observation ph3 "
        "        WHERE ph3.offer_id = so.offer_id "
        "        AND ph3.currency = po.currency) AS price_max, "
        "       (SELECT ph4.price FROM price_observation ph4 "
        "        WHERE ph4.offer_id = so.offer_id "
        "        AND ph4.currency = po.currency "
        "        AND ph4.price != po.price "
        "        ORDER BY ph4.business_date DESC, ph4.price_observation_id DESC "
        "        LIMIT 1) AS price_previous, "
        "       (SELECT cr.per_usd FROM currency_rate cr "
        "        WHERE cr.currency = po.currency "
        f"       {_RATE_BY_AUTHORITY}) AS per_usd, "
        "       (SELECT GROUP_CONCAT(spa.raw_value, ', ') FROM source_product_attribute spa "
        "        WHERE spa.source_product_id = sp.source_product_id "
        "        AND spa.attribute_code IN ('category','category_ar')) AS category, "
        "       EXISTS(SELECT 1 FROM source_product_attribute spa2 "
        "        WHERE spa2.source_product_id = sp.source_product_id) AS has_details, "
        "       sp.category_path_ar, sp.product_name, sp.category_path, "
        # Appended LAST on purpose: every index above is positional and a column
        # inserted mid-list silently shifts the lot.
        "       po.tax_included, sv.variant, sv.variant_url, "
        "       COALESCE(NULLIF(sp.product_name,''), sp.product_name_ar), "
        "       sp.source_product_id, "
        # Appended LAST, obeying the rule the comment above states: adding it
        # beside sp.brand shifted observations/min/max/previous by one.
        "       sp.brand_ar, po.price_trade, "
        # The rate's DATE and source, appended last. The owner's standing
        # rule (2026-07-26) is that a converted number is never shown
        # without the rate used AND the date of that rate — so the number
        # cannot travel to the grid alone.
        "       (SELECT cr.as_of FROM currency_rate cr "
        "        WHERE cr.currency = po.currency "
        f"       {_RATE_BY_AUTHORITY}) AS usd_rate_as_of, "
        "       (SELECT cr.source_key FROM currency_rate cr "
        "        WHERE cr.currency = po.currency "
        f"       {_RATE_BY_AUTHORITY}) AS usd_rate_source, "
        # Appended LAST, obeying the rule stated twice above: the three facts
        # that let the price cell say what one unit of the price buys where the
        # shop quotes by weight and names no unit (0057).
        "       so.quantity_is_decimal, so.weight, so.weight_unit "
        f"{_LATEST_PER_OFFER} ORDER BY sp.product_name_ar, so.country_code_alpha2 LIMIT ?",
        (source_key, limit)).fetchall()

    tax_rules = tax.load_rules(conn, source_key)
    # One resolved state per DISTINCT (region, material, tax_included) triple,
    # sent once and referenced by index from each row. Keyed by region alone,
    # gasoline and natural-gas rows wore the diesel page's link — the owner's
    # exact report. Keyed without tax_included, madar's 328 tax-EXCLUSIVE
    # configurable rows shared one state with its 399 inclusive simple ones and
    # every Tax cell in the table read "Incl. 15%": still one state per distinct
    # ANSWER, but the row's own figure is part of what makes an answer distinct.
    tax_states: list[dict] = []
    tax_index: dict[tuple[str, str, bool], int] = {}

    def tax_ref(region: str, material: str, tax_included: bool) -> int:
        key = (region, material, tax_included)
        if key not in tax_index:
            tax_index[key] = len(tax_states)
            tax_states.append(tax.resolve(tax_rules, region, material=material)
                              .for_row(tax_included).as_dict())
        return tax_index[key]

    _zone = business_zone(conn)
    shaped = [{"product_name_ar": r[0], "variant_ar": r[1] or "", "variant": r[30] or "",
               # The variation's own page where there is one; the row's arrow
               # and the record panel both open the most specific address.
               "product_link": r[31] or r[9] or "",
               "sku": r[2] or "",
               "price": r[3], "price_before": r[4], "price_sale": r[5],
               "currency": r[6], "availability": r[7],
               "price_changed_on": r[8],
               "curation": r[10], "country_code_alpha2": r[11] or "",
               "country": region_name(r[11]),
               "last_confirmed_on": business_day(r[12], _zone),
               "unit": price_unit(r[13], r[14]), "offer_id": r[15],
               # The price cell renders this when the Unit column is empty. It
               # is NOT a unit and must never fill that column: it is the
               # weight the shop publishes for the thing it is pricing, shown
               # because the shop also says the quantity is divisible.
               "price_basis": price_basis(r[13], r[39], r[40], r[38]),
               "official_source": r[16] or "",
               "official_source_link": r[17] or "",
               "brand": r[18] or "",
               # Explicit index, not r[-1]: a column appended after it would
               # silently steal the position, which 0052 nearly did.
               "brand_ar": r[34] or "",
               "price_trade": r[35],
               # The full stated path when the source classifies in levels;
               # the flat labels otherwise. The per-level keys split the path
               # so any layer can be sorted or grouped on its own.
               "category_ar": r[26] or r[24] or "",
               "category_leaf_ar": _category_leaf(r[26] or r[24]),
               **_category_levels(r[26], prefix="category_l", suffix="_ar"),
               "category": r[28] or "",
               "category_leaf": _category_leaf(r[28]),
               **_category_levels(r[28]),
               "product_name": r[27] or "",
               "has_details": bool(r[25]),
               "observations": r[19],
               "price_min": r[20],
               "price_max": r[21],
               "price_previous": r[22] if r[22] is not None else "",
               "price_change": _change_text(r[22], r[3]),
               "price_usd": _usd_value(r[3], r[6], r[23]),
               # Never the number on its own: the rate and its date ride
               # with it so the cell can say what it was converted at.
               "usd_rate": r[23],
               "usd_rate_as_of": (r[36] or "")[:10],
               "usd_rate_source": r[37] or "",
               "was_price": r[4] if _discounted(r[4], r[3]) else "",
               "discount": _discount_amount(r[4], r[3]),
               "discount_pct": _discount_pct(r[4], r[3]),
               "tax_ref": tax_ref(r[11] or "", r[32] or r[0] or "", bool(r[29])),
               # Carried only as far as the attribute join below, then popped.
               "source_product_id": r[33]}
              for r in rows]

    # How many rows the query actually returned, kept before any folding: the
    # truncation flag answers "did the cap cut this off", and a fold that turned
    # 108 rows into 18 would otherwise answer it wrongly.
    fetched = len(shaped)
    # Folded here, while source_product_id is still on the row and before the
    # per-site facet columns are joined: those are per PRODUCT, so they land on
    # the folded row identically either way.
    #
    # Computed even when the fold is OFF, because the page needs to know whether
    # offering the switch would mean anything: a source with nothing to fold
    # gets no control rather than a control that does nothing.
    could_fold = fold_variant_rows(shaped)
    foldable = len(could_fold) < fetched
    if fold_variants:
        shaped = could_fold

    present = column_presence(conn, source_key)
    # Two independent questions, and both must be asked. `present` answers "does
    # this source publish anything here at all"; the saved view answers "did the
    # owner HIDE it". Hidden is the explicit act — a column that was never
    # registered was never hidden and defaults to shown. (Deriving this from
    # the registered-VISIBLE list instead silently suppressed every column
    # added after a source's view was first seeded.)
    hidden = fields.hidden_columns(conn, source_key)
    # OWNER'S CONVENTION (2026-07-25): where a source publishes both
    # languages, the UNMARKED column is the English one — «العمود record يعرض
    # اللغة الانجليزية اما record ar يعرض العربية» — and the Arabic one wears
    # the (AR) marker. Applied from the pair table, so it holds for the name,
    # the category and every level at once, and a monolingual source keeps its
    # plain heading (calling its only Record column "(AR)" would be a claim
    # about a language nobody stated).
    labels = dict(BROWSE_COLUMNS)

    # The per-source columns the EXPORT has always carried, now on the page
    # too: one per site facet, one per detail the owner promoted (0044).
    # The owner asked for the main table to hold everything, and a column
    # that exists in the file and not on the screen is the same split he
    # keeps having to work around.
    pivoted = _filter_values(conn, source_key)
    extra: list[str] = []
    for row in shaped:
        for label in pivoted.get(row.get("source_product_id") or -1, {}):
            if label not in extra and label not in labels:
                extra.append(label)
    extra = _group_sorted(extra, _filter_groups(conn, source_key))
    for row in shaped:
        values = pivoted.get(row.pop("source_product_id", None) or -1, {})
        for label in extra:
            row[label] = values.get(label, "")

    # NOTHING is normalised on the way out. This payload carries what the site
    # published, padding included, because the record is the record.
    #
    # An earlier version collapsed whitespace here so MADAR's space-padded
    # names would stop sorting ahead of everything else. It bought the right
    # ORDER by editing the VALUE, which is the one thing a report may not do —
    # and it reached the xlsx and Sheets export as well, so a brand the shop
    # published as a single space left as an empty cell. An order is not a
    # value: the grid compares a normalised form when it sorts and when it
    # lists filter values, and shows and exports exactly what was captured.

    return {
        "source_key": source_key,
        "columns": [{"key": key, "label": labels[key]} for key, label in BROWSE_COLUMNS
                    if key in present and key not in hidden]
                   # Named the way the SITE names them, like the export.
                   + [{"key": label, "label": label} for label in extra
                      if label not in hidden],
        "rows": shaped,
        "tax_states": tax_states,
        "total": total,
        "returned": len(shaped),
        # Stated separately so a folded table can say what it did: `total` is
        # what the source published, `returned` is how many rows are on screen,
        # and these two differ for a reason that is not truncation.
        "folded": fold_variants and len(shaped) < fetched,
        # Is the fold ON, and would it change anything — two questions the page
        # asks separately: the first sets the switch, the second decides whether
        # to offer it at all.
        "fold_variants": bool(fold_variants),
        "foldable": foldable,
        # A prefix presented as the whole is the failure this flag exists to
        # prevent; the page states it rather than looking complete. Measured
        # against what the QUERY returned, never against the folded count.
        "truncated": total > fetched,
        "tree": _tree_shape(shaped),
        # The pairs actually on offer for THIS source: the grid's AR|EN
        # toggle flips exactly these, so it never hardcodes a field list.
        "bilingual": {ar: en for ar, en in BILINGUAL_COLUMNS.items()
                      if ar in present and en in present},
        # Columns this source HAS but the owner moved out of the table. They
        # are not lost: the record panel lists them under Details, so hiding a
        # column is "move it to the details" and showing it is "move it back"
        # — the owner's ask, using the mechanism that already exists.
        "moved_to_details": [{"key": key, "label": label}
                             for key, label in BROWSE_COLUMNS
                             # The link is an icon, not a fact that can live
                             # in the details panel, so "move it to details" was
                             # never a real offer for it.
                             if key in present and key in hidden
                             and key != "product_link"],
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
    regions = {r["country_code_alpha2"] for r in rows if r["country_code_alpha2"] and r["country_code_alpha2"] != "*"}
    # Whichever name column this source actually fills: an Arabic-only shop
    # leaves the English one blank, and grouping on a blank column collapses
    # every row into one branch with an empty heading.
    by = "product_name" if any(r.get("product_name") for r in rows) else "product_name_ar"
    names = {r[by] for r in rows}
    # The region has to VARY for nesting by it to mean anything. A shop whose
    # every row is 'SA' would otherwise get a tree whose branch has one child
    # reading "Saudi Arabia" — more clicks to see the same list.
    if len(regions) > 1 and len(names) < len(rows):
        return {"by": by, "child": "country"}
    return {"by": "", "child": ""}


# ---- the schema page: what every column IS, read from the code itself --------
#
# The owner asked for a page he can read and review with me. Written as a static
# document it would be wrong within a week, so it is DERIVED: the column list
# comes from BROWSE_COLUMNS and EXPORT_HEADER, which is the same list the table
# and the export are built from, and "who fills it" is counted from the live
# warehouse. A column that stops existing disappears from the page by itself.
#
# The one thing that cannot be derived is what a column MEANS. That sentence is
# authored here, once, beside the name it describes.
#
# IT DESCRIBES TODAY, NOT THE PLAN. The first version of this map wrote the
# APPROVED vocabulary's meaning onto the columns that still hold the old one —
# product_name was described as "the product's name, in English" while it holds
# Arabic on every bilingual source. The owner read that off the page and asked
# why the agreement had been reversed. It had not: the inversion has not
# happened yet, and a page whose whole claim is that it cannot drift from the
# product must describe the product AS IT IS. Columns whose name is due to
# change say so, in RENAMING_TO below, instead of pretending it already did.
COLUMN_NOTES: dict[str, str] = {
    "product_name": "The product's name in English, where the source publishes one.",
    "product_name_ar": "The same name in Arabic, where the source publishes one.",
    "country_code_alpha2": "The country the price applies to, as an ISO 3166-1 alpha-2 code.",
    "country": "The same country, spelled out.",
    "brand": "The brand, as the source publishes it — never inferred from the name.",
    "brand_ar": "The same brand in Arabic, where the source publishes one.",
    "category": "The full classification path the source files this product "
                "under, in English where it publishes one.",
    "category_ar": "The same path in Arabic, where the source publishes one.",
    "variant": "Which variation this row is, in English.",
    "variant_ar": "The same variation in the site's own Arabic words.",
    "sku": "The source's own code for this item.",
    "product_id": "The id its variations share, so six rows of one cable group.",
    "price": "What a visitor actually pays today.",
    "price_before": "The price before any discount inside this listing.",
    "price_sale": "The discounted price, when the listing has one.",
    "price_trade": "The price for trade or wholesale buyers, where the source "
                   "publishes a second one beside the retail price.",
    "discount": "How much the listing takes off, as an amount.",
    "discount_pct": "The same discount as a percentage.",
    "currency": "The currency the source quotes in — never converted.",
    "price_usd": "An approximate US-dollar figure, so many currencies can be "
                 "ranked in one column. UNDER REVIEW — the owner has flagged "
                 "this column for a decision: the rate it uses is implied by "
                 "a fuel site's own arithmetic, not quoted by any source, so "
                 "what it is FOR has to be settled before it is trusted. "
                 "Shown only where a source spans more than one currency.",
    "price_previous": "The price that held immediately before the current one.",
    "price_change": "The move from that previous price to this one.",
    "price_min": "The lowest price ever recorded for this record.",
    "price_max": "The highest price ever recorded for this record.",
    "observations": "How many times this price has been recorded.",
    "unit": "What one price BUYS: a litre, a 50 kg bag, a 100 m roll. "
            "Empty when the source states no unit — never guessed.",
    "price_basis": "The WEIGHT a price is quoted against, where the source "
                   "prices by weight and names no unit: madar's rebar is "
                   "4,830 per 1,000 kg, and per bar it would be nonsense. "
                   "Both numbers are the shop's — its published weight and "
                   "its own word for the unit of that weight. Empty wherever "
                   "the Unit column is filled, and wherever the source does "
                   "not say its quantity is divisible.",
    "availability": "In stock or out, as the source states it.",
    "tax": "Whether THIS figure includes tax, and at what rate.",
    "tax_included": "The same fact as yes/no, for a spreadsheet.",
    "tax_evidence": "How well the tax position is known: stated, implied, unknown.",
    "tax_rate_pct": "The rate, when the source states one.",
    "tax_statement": "Where the source says it, so the claim can be read.",
    "price_changed_on": "When the price last MOVED.",
    "last_confirmed_on": "When a completed run last saw it still true.",
    "official_source": "The body the source attributes its figure to.",
    "official_source_link": "Where that body publishes it.",
    "curation": "Your own review state for this product.",
    # One column since 0051, so one note: the same link is the arrow in the
    # table and the full URL in the export.
    "product_link": "The product's page on the site — the arrow opens it, "
                    "and the export carries the full address.",
}


# The approved vocabulary (docs/column-vocabulary.md), and the columns still
# waiting for it. Two rules produce every target name: the key and the label are
# the same word, and the name states the LANGUAGE of the content — English
# unmarked, Arabic marked `_ar`. While a rename is pending the schema page shows
# both names side by side, rather than letting the owner read a plan as a fact.
#
# EMPTY: both halves have landed. The language half across 0038-0050, and the
# non-language half — the price family, the tax family, curation, and the
# product_link merge — in 0051. A row left here after its rename lands is worse
# than no row at all: the page would go on announcing a change already made.
#
# `region` stays `region` and is NOT a pending rename: it SCOPES a row rather
# than describing it (0042), and the same is true of the manifest's
# default_region and pricekey's own field name.
RENAMING_TO: dict[str, str] = {}


def renaming_to(key: str) -> str:
    """The name this column takes when the vocabulary sweep lands, or ""."""
    # No level loop any more: it lived OUTSIDE the dict, so emptying the
    # dict alone would have left pending_renames stuck at 20 and the page
    # still announcing a rename that had already landed.
    if key in RENAMING_TO and RENAMING_TO[key] != key:
        return RENAMING_TO[key]
    return ""


def schema_report(conn: sqlite3.Connection) -> dict:
    """Every column, what it means, and which sources actually fill it.

    Derived, never authored: the names come from the same lists the table and
    the export are built from, and the counts from the warehouse as it is right
    now. The page cannot drift from the product because it IS the product's own
    declaration, read back.
    """
    sources = [row[0] for row in conn.execute(
        "SELECT DISTINCT ss.source_key FROM source_site ss "
        "JOIN source_product sp ON sp.source_id = ss.source_id ORDER BY ss.source_key")]
    presence = {key: column_presence(conn, key) for key in sources}

    def note(key: str) -> str:
        if key in COLUMN_NOTES:
            return COLUMN_NOTES[key]
        if key.startswith("category_") and "_l" in key:
            # rsplit on the RAW key returned "1_ar" and printed "Level 1_ar".
            level = key.removesuffix("_ar").rsplit("_l", 1)[-1]
            return f"Level {level} of the classification path, split out so it can be sorted and grouped."
        return ""

    table_columns = []
    for key, label in BROWSE_COLUMNS:
        arabic = key in BILINGUAL_COLUMNS
        english_twin = BILINGUAL_COLUMNS.get(key)
        table_columns.append({
            "key": key, "label": label, "note": note(key),
            "renaming_to": renaming_to(key), "origin": column_origin(key),
            "language": "Arabic" if arabic else ("English" if key in BILINGUAL_COLUMNS.values() else ""),
            "pairs_with": english_twin or "",
            "sources": [s for s in sources if key in presence[s]],
        })
    export_only = [{"key": key, "note": note(key), "renaming_to": renaming_to(key),
                    "origin": column_origin(key)}
                   for key in EXPORT_HEADER if key not in {k for k, _ in BROWSE_COLUMNS}]

    # The per-source columns the SITE names, not us: variation axes and the
    # facets a source filters by. Counted, not listed, because madar alone
    # publishes sixty.
    per_source = []
    for key in sources:
        axes = conn.execute(
            "SELECT COUNT(*) FROM source_variant sv "
            "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
            "JOIN source_site ss ON ss.source_id = sp.source_id "
            "WHERE ss.source_key = ? AND COALESCE(sv.variant_axes_ar,'') != ''",
            (key,)).fetchone()[0]
        facets = conn.execute(
            "SELECT COUNT(DISTINCT spa.attribute_label) FROM source_product_attribute spa "
            "JOIN source_product sp ON sp.source_product_id = spa.source_product_id "
            "JOIN source_site ss ON ss.source_id = sp.source_id "
            "WHERE ss.source_key = ? AND spa.is_site_filter = 1",
            (key,)).fetchone()[0]
        groups = [row[0] for row in conn.execute(
            "SELECT DISTINCT spa.attribute_group FROM source_product_attribute spa "
            "JOIN source_product sp ON sp.source_product_id = spa.source_product_id "
            "JOIN source_site ss ON ss.source_id = sp.source_id "
            "WHERE ss.source_key = ? AND COALESCE(spa.attribute_group,'') != '' "
            "ORDER BY spa.attribute_group", (key,))]
        per_source.append({"source_key": key, "columns": len(presence[key]),
                           "variants_with_axes": axes, "filters": facets,
                           "detail_groups": groups})
    return {"sources": sources, "table": table_columns, "export_only": export_only,
            "per_source": per_source, "category_levels": CATEGORY_LEVELS,
            "pending_renames": sum(1 for c in table_columns if c["renaming_to"]),
            "warehouse": warehouse_tables(conn)}


# ---- the warehouse itself: every table, and why it exists --------------------
#
# The owner opened the schema page to REVIEW the data model and found one table
# on it — the Data page's columns. What he asked for is the warehouse: every
# table, what it holds, and what it is FOR. So the page lists them all, grouped
# by the layer they belong to, with the row counts read live.
#
# The grouping is the model's own story, in the order the data moves through it:
# a site publishes a product, we record what it charges, the charges become a
# history, the owner curates a unified layer on top, and the operational tables
# say what ran.
TABLE_GROUPS: list[tuple[str, str, list[tuple[str, str]]]] = [
    ("What the source said", "The source-local layer: exactly what each site "
     "published, before any interpretation. Nothing here is merged or renamed.", [
         ("source_site", "One row per source: its key, both names, base URL and platform."),
         ("source_product", "One row per product a source publishes, with its name, "
                            "classification, URL and your curation state."),
         ("source_variant", "One row per buyable variation — a colour, a thickness — "
                            "with the site's own label and axes."),
         ("source_product_attribute", "Every stated fact about a product: descriptions, "
                                      "specifications, images, datasheets, the site's filters."),
         ("identity_alias", "Names and codes a product has been seen under, so a rename "
                            "on the site does not create a second product here."),
         ("raw_snapshot", "The untouched page or response behind a row, when kept."),
     ]),
    ("General extraction", "The flexible branch for non-price data. It discovers a "
     "dataset and its fields first, then stores versioned records without forcing "
     "them into the price model.", [
         ("site_profile", "One profile per general website, including its lifecycle "
                          "and optional link to a MarketLens source."),
         ("dataset_definition", "A table, list, detail, tree or stream discovered on "
                                "that website."),
         ("field_definition", "The fields that belong to a discovered dataset, with "
                              "their types, order and identity role."),
         ("dataset_relationship", "A reviewed relationship between two discovered "
                                  "datasets, including its cardinality."),
         ("relationship_field_pair", "The parent and child fields that make a dataset "
                                     "relationship work."),
         ("generic_page_snapshot", "The captured page or response from which general "
                                   "records were extracted."),
         ("dataset_schema_version", "A frozen version of a dataset's shape, so later "
                                    "field changes never rewrite old records."),
         ("schema_version_field", "Which field definitions belonged to one frozen "
                                  "schema version."),
         ("generic_record", "The current identity and latest state of one general "
                            "record."),
         ("generic_record_revision", "Every previous version of a general record, "
                                     "preserved as history."),
         ("generic_ingestion", "One extraction event: dataset, schema, snapshot and "
                               "record counts."),
     ]),
    ("What it costs", "An offer is a thing you can buy at a price. Observations are "
     "append-only: a price is never edited, only observed again.", [
         ("source_offer", "One row per (variant, region, currency, unit) — what is on sale."),
         ("price_observation", "Every price ever recorded, with its date, currency, tax "
                               "state and whether we observed it or the source reported it."),
         ("price_period", "The change-only timeline: one row per price that HELD, from "
                          "when it appeared until it moved."),
         ("offer_state", "The current answer per offer: latest price, last confirmation, "
                         "whether it is still on the site."),
         ("absence_period", "When an offer disappeared from the source, and when it returned."),
         ("change_event", "The feed behind the Changes page: what changed, from what, to "
                          "what, and when it was detected."),
         ("selling_unit", "The units prices are quoted in — litre, kg, metre, piece."),
         ("currency_rate", "Rates the sources themselves imply, used only to RANK many "
                           "currencies in one column, never to convert a stored price."),
         ("tax_rule", "What each source says about tax: the rate, the sentence it was read "
                      "from, and the link to it."),
     ]),
    ("Your unified layer", "Where your own catalogue lives. It fills only as you curate: "
     "until then these tables are empty by design, and the source-local layer above is "
     "the whole truth.", [
         ("material", "One material in YOUR catalogue — the thing several sources each sell."),
         ("material_variant", "One buyable form of your material."),
         ("material_attribute_value", "Your own attribute values for it."),
         ("material_classification", "Where your material sits in your own classification."),
         ("source_product_match", "Which source product you decided IS which material."),
         ("source_variant_match", "The same decision at variation level."),
         ("brand", "Brands, deduplicated across sources."),
         ("attribute_definition", "The attributes you track, and their types."),
         ("classification_scheme", "A classification you keep — yours, or a standard's."),
         ("classification_node", "One node in that classification."),
         ("classification_mapping", "How a source's own category maps onto your node."),
         ("variant_attribute_value", "Attribute values at variation level."),
         ("feed_assignment", "Which materials a published feed carries."),
     ]),
    ("What ran, and what you asked for", "Operations: every run leaves a record, and "
     "every preference you set is stored rather than remembered.", [
         ("crawl_run", "One row per ingest: rows seen, status, and what failed."),
         ("crawl_job", "One row per job you started, with its controls and outcome."),
         ("job_log_entry", "The log lines behind a job."),
         ("schedule", "When a source should run by itself."),
         ("retention_policy", "How long raw material is kept."),
         ("retention_run", "What a retention pass actually removed."),
         ("retention_pin", "What you pinned so retention never touches it."),
         ("dataset_field", "Every column a source has, and whether you hide it."),
         ("source_attribute_promotion", "Details you promoted into columns of their own."),
         ("saved_view", "A filter and column arrangement you saved."),
         ("database_migration", "Every schema change this database has applied."),
         ("scrapex_meta", "The database's own identity and version."),
     ]),
]


def warehouse_tables(conn: sqlite3.Connection) -> list[dict]:
    """Every table, grouped by layer, with its live row count.

    The counts are read; the purposes are authored (a table cannot say what it
    is FOR). A table present in the database but missing from the groups above
    is listed at the end rather than hidden — a schema page that quietly omits
    part of the schema is the one thing it must never be.
    """
    known = {name for _title, _note, tables in TABLE_GROUPS for name, _purpose in tables}
    live = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}

    def described(name: str) -> dict:
        rows = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] if name in live else None
        columns = len(list(conn.execute(f'PRAGMA table_info("{name}")'))) if name in live else 0
        return {"name": name, "rows": rows, "columns": columns, "present": name in live}

    groups = [{"title": title, "note": note,
               "tables": [dict(described(name), purpose=purpose) for name, purpose in tables]}
              for title, note, tables in TABLE_GROUPS]
    stray = sorted(live - known)
    if stray:
        groups.append({"title": "Not yet described",
                       "note": "Present in the database and missing from the list above — "
                               "shown so the page can never omit part of the schema.",
                       "tables": [dict(described(name), purpose="") for name in stray]})
    return groups


# ---- where a column COMES FROM ----------------------------------------------
#
# The owner, reviewing the schema page: "put the table name beside each column
# so I know which table it came from". Half of that is already declared —
# FILTERABLE and _EXPORT_SELECT carry the real SQL expression per column, so the
# table is READ from the same string the query uses, and a column that moves
# tables cannot keep a stale note here.
#
# The other half is computed at read time (a discount is not stored; it is the
# difference between two prices) or assembled from a bag (the classification
# levels split one path). Those are authored, and they say COMPUTED rather than
# naming a table they do not live in.
_TABLE_BY_ALIAS = {
    "sp": "source_product", "sv": "source_variant", "so": "source_offer",
    "po": "price_observation", "ost": "offer_state", "su": "selling_unit",
    "ss": "source_site", "spa": "source_product_attribute",
}

_COMPUTED_FROM: dict[str, str] = {
    "category": "source_product.category_path",
    "category_ar": "source_product.category_path_ar",
    "variant": "source_variant.variant",
    "unit": "selling_unit + source_offer.basis_quantity",
    "price_basis": ("source_offer.weight + weight_unit, shown only where "
                    "quantity_is_decimal and no selling_unit"),
    "discount": "computed: price_observation.price_before − price",
    "discount_pct": "computed: the same two prices, as a percentage",
    "price_usd": "computed: price_observation × currency_rate",
    "price_previous": "computed: price_observation, the last differing price",
    "price_change": "computed: this price against the previous one",
    "price_min": "computed: price_observation, lowest for this offer",
    "price_max": "computed: price_observation, highest for this offer",
    "observations": "computed: price_observation, counted",
    "tax": "tax_rule + this row's price_observation.tax_included",
    "open": "source_product.product_link",
}


def column_origin(key: str) -> str:
    """"source_product.brand_raw" — where this column's value comes from.

    Read from the query's own SQL where there is one, so it cannot go stale.
    """
    expression = (FILTERABLE.get(key, ("", ""))[0] or _EXPORT_SELECT.get(key, "")).strip()
    if expression and "." in expression and expression.count(" ") == 0:
        alias, _, column = expression.partition(".")
        if alias in _TABLE_BY_ALIAS:
            return f"{_TABLE_BY_ALIAS[alias]}.{column}"
    if key in _COMPUTED_FROM:
        return _COMPUTED_FROM[key]
    for level in range(1, CATEGORY_LEVELS + 1):
        if key in (f"category_l{level}", f"category_l{level}_ar"):
            path = "category_path_ar" if key.endswith("_ar") else "category_path"
            return f"split from source_product.{path}"
    return ""


_MODEL_GROUP_KEYS = {
    "What the source said": "source",
    "General extraction": "general",
    "What it costs": "pricing",
    "Your unified layer": "unified",
    "What ran, and what you asked for": "operations",
    "Not yet described": "other",
}


def data_model_report(conn: sqlite3.Connection, *, database_key: str,
                      database_label: str) -> dict:
    """The live relational model for one database.

    Table names, columns, primary keys and relationships are read from SQLite,
    not copied into a diagram. Purposes and layers reuse ``TABLE_GROUPS`` â€” the
    same authored explanations shown on the Schema page. This makes the visual
    model a view of the database that is running, not a drawing that can drift
    away from it.
    """
    described_groups = warehouse_tables(conn)
    descriptions = {
        table["name"]: {
            "group": group["title"],
            "group_key": _MODEL_GROUP_KEYS.get(group["title"], "other"),
            "purpose": table["purpose"],
        }
        for group in described_groups
        for table in group["tables"]
    }
    live = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]

    tables: list[dict] = []
    relationships: list[dict] = []
    for table_name in live:
        quoted = table_name.replace('"', '""')
        column_rows = list(conn.execute(f'PRAGMA table_info("{quoted}")'))
        fk_rows = list(conn.execute(f'PRAGMA foreign_key_list("{quoted}")'))
        foreign_by_column: dict[str, list[dict]] = {}
        for fk in fk_rows:
            relation = {
                "id": f"{database_key}:{table_name}:{fk[0]}:{fk[1]}",
                "database": database_key,
                "from_table": table_name,
                "from_column": fk[3],
                "to_table": fk[2],
                "to_column": fk[4] or "rowid",
                "on_update": fk[5],
                "on_delete": fk[6],
            }
            relationships.append(relation)
            foreign_by_column.setdefault(fk[3], []).append(relation)

        fields = [{
            "name": column[1],
            "type": column[2] or "",
            "required": bool(column[3]),
            "default": column[4],
            "primary_key": bool(column[5]),
            "foreign_keys": foreign_by_column.get(column[1], []),
        } for column in column_rows]
        preview = sorted(
            fields,
            key=lambda field: (
                not field["primary_key"],
                not bool(field["foreign_keys"]),
                fields.index(field),
            ),
        )[:7]
        described = descriptions.get(
            table_name,
            {"group": "Not yet described", "group_key": "other", "purpose": ""},
        )
        row_count = conn.execute(
            f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0]
        tables.append({
            "id": f"{database_key}:{table_name}",
            "database": database_key,
            "name": table_name,
            "group": described["group"],
            "group_key": described["group_key"],
            "purpose": described["purpose"],
            "rows": row_count,
            "column_count": len(fields),
            "fields": fields,
            "preview_fields": preview,
        })

    present_group_keys = {table["group_key"] for table in tables}
    groups = []
    for title, note, _tables in TABLE_GROUPS:
        key = _MODEL_GROUP_KEYS.get(title, "other")
        if key in present_group_keys and not any(group["key"] == key for group in groups):
            groups.append({"key": key, "title": title, "note": note})
    if "other" in present_group_keys:
        groups.append({
            "key": "other",
            "title": "Other tables",
            "note": "Live tables that have not been assigned to a model layer yet.",
        })

    return {
        "key": database_key,
        "label": database_label,
        "schema_version": int(conn.execute("PRAGMA user_version").fetchone()[0]),
        "tables": tables,
        "relationships": relationships,
        "groups": groups,
        "row_count": sum(table["rows"] for table in tables),
    }
