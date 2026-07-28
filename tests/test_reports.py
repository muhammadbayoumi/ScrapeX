"""Reports: the two-layer summary + bounded sample."""
from __future__ import annotations

import sqlite3

import pytest

from scrapex import db as dbmod
from scrapex.reports import (BILINGUAL_COLUMNS, CATEGORY_LEVELS,
                            _category_leaf, fold_variant_rows,
                            recent_observations, source_summary,
                            table_payload)
from tests.test_ingest import make_entry, make_payload, one_row
from scrapex.ingest import ingest_payloads


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


def test_summary_none_for_unknown_source(conn):
    assert source_summary(conn, "NOPE") is None


def test_summary_reports_source_local_layer(conn):
    ingest_payloads(conn, make_entry(), [make_payload([
        one_row(external_product_id="1", external_variant_id="v1"),
        one_row(external_product_id="2", external_variant_id="v2", price="50.00"),
    ])])
    s = source_summary(conn, "ELSEWEDYSHOP")
    assert s.products == 2 and s.variants == 2 and s.observations == 2
    assert s.curation == {"inventoried": 2}
    # Unified layer is empty until curation — this is the point of the report.
    assert s.matched_variants == 0 and s.published_rows == 0
    assert s.last_status == "success"


def test_recent_observations_is_bounded_and_shaped(conn):
    rows = [one_row(external_product_id=str(i), external_variant_id=f"v{i}",
                    price=f"{i+1}.00") for i in range(5)]
    ingest_payloads(conn, make_entry(), [make_payload(rows)])
    sample = recent_observations(conn, "ELSEWEDYSHOP", limit=3)
    assert len(sample) == 3
    assert set(sample[0]) == {"product_name_ar", "price", "currency",
                              "availability", "tax_included",
                              "business_date", "country_code_alpha2", "country", "unit"}
    assert sample[0]["currency"] == "EGP"


def test_summary_curation_breakdown_reflects_ignore(conn):
    ingest_payloads(conn, make_entry(), [make_payload([one_row()])])
    conn.execute("UPDATE source_product SET curation = 'ignored'")
    s = source_summary(conn, "ELSEWEDYSHOP")
    assert s.curation == {"ignored": 1}


# ---- region / country surfacing (the owner-reported defect) -----------------

def _commodity_rows(conn, regions=("EG", "SA"), price="0.404"):
    """Ingest one commodity row per country, the GPP shape."""
    from scrapex.config import ExtractSpec, SourceEntry
    from scrapex.payload import PAYLOAD_VERSION, FunnelPayload
    from scrapex.rowspec import COMMODITY_PRICE, RowBuilder
    from scrapex.vocab import ExtractKind, ExtractScope

    entry = SourceEntry.model_validate(dict(
        source_key="GPP_ENERGY", source_name="Global energy prices",
        base_url="https://www.globalpetrolprices.com", family="static-html-table",
        currency="USD", authority="aggregator", cadence="weekly",
        extract=[ExtractSpec(kind=ExtractKind.COMMODITY_PRICE, scope=ExtractScope.LATEST_ONLY,
                             materials=["DIESEL"], regions=["*"])]))
    rows = [RowBuilder(COMMODITY_PRICE).row(
        material_key="DIESEL", country_code_alpha2=r, currency="USD", unit="USD/liter",
        tax_included="1", price=price, observed_label="") for r in regions]
    ingest_payloads(conn, entry, [FunnelPayload(
        payload_version=PAYLOAD_VERSION, source_key="GPP_ENERGY",
        kind=ExtractKind.COMMODITY_PRICE, client="cli", scraped_at="2026-07-19T10:00:00Z",
        source_url="https://www.globalpetrolprices.com",
        header=list(COMMODITY_PRICE.columns), rows=rows)])
    return entry


def test_iso_code_resolves_to_a_country_name():
    from scrapex.reports import region_name
    assert region_name("EG") == "Egypt" and region_name("SA") == "Saudi Arabia"
    assert region_name("ZZ") == "ZZ"          # unknown code passes through
    assert region_name("*") == "" and region_name(None) == ""   # no geography = blank


def test_browse_exposes_the_country_for_commodity_rows(conn):
    """Regression: prices arrived but the country was invisible — ~180 rows
    rendered byte-identical except for the price."""
    from scrapex.reports import browse_observations
    _commodity_rows(conn)
    rows = browse_observations(conn, "GPP_ENERGY").rows
    assert {r["country_code_alpha2"] for r in rows} == {"EG", "SA"}
    assert {r["country"] for r in rows} == {"Egypt", "Saudi Arabia"}
    assert rows[0] != rows[1]                 # the rows are now distinguishable


def test_browse_can_search_by_country(conn):
    """Search matched product name only, so "EG" found nothing on a commodity source."""
    from scrapex.reports import browse_observations
    _commodity_rows(conn)
    assert browse_observations(conn, "GPP_ENERGY", search="EG").total == 1
    assert browse_observations(conn, "GPP_ENERGY", search="DIESEL").total == 2


def test_browse_order_is_stable_for_identical_rows(conn):
    from scrapex.reports import browse_observations
    _commodity_rows(conn, regions=("EG", "SA", "US", "AE"))
    first = [r["country_code_alpha2"] for r in browse_observations(conn, "GPP_ENERGY").rows]
    second = [r["country_code_alpha2"] for r in browse_observations(conn, "GPP_ENERGY").rows]
    assert first == second == sorted(first)


def test_export_carries_region_and_country(conn):
    from scrapex.reports import EXPORT_HEADER, export_source_table
    _commodity_rows(conn)
    header, table = export_source_table(conn, "GPP_ENERGY")
    assert header == EXPORT_HEADER
    # This said "asserted by NAME, not by index" and then read row[1] and
    # row[2] — the positions the geography held BEFORE product_name_en entered
    # the header. That is precisely the shift the owner found in a real export
    # (the region code published under product_name_en, the country name under
    # region, country empty, the English name in country), and these two lines
    # were defending it. Reading through the header cannot drift.
    rows = [dict(zip(header, row)) for row in table]
    assert {row["country_code_alpha2"] for row in rows} == {"EG", "SA"}
    assert {row["country"] for row in rows} == {"Egypt", "Saudi Arabia"}


def test_every_exported_column_holds_its_own_field(conn):
    """The owner opened a real export and found the country code filed under
    product_name_en, the country name under region, country empty, and the
    English product name in country. The header was one list and the row was
    another, and a column added to the first without the second shifted
    everything between them. One row, every column read by NAME: a value that
    lands under someone else's heading fails here and nowhere else, because a
    spreadsheet has no way to notice."""
    from scrapex.reports import export_source_table
    ingest_payloads(conn, make_entry(), [make_payload([one_row(
        product_name_ar="سلك نحاس", product_name="Copper wire", country_code_alpha2="EG",
        brand="Elsewedy", brand_ar="السويدي", category_path_ar="أسلاك", category_path="Wires",
        external_product_id="9797", external_sku="76ec8c8572f0-1",
        price_before="1209.54", price_sale="1124.87", price="1124.87")])])
    header, table = export_source_table(conn, "ELSEWEDYSHOP")
    row = dict(zip(header, table[0]))
    assert row["product_name"] == "Copper wire"
    assert row["product_name_ar"] == "سلك نحاس"
    assert row["country_code_alpha2"] == "EG"
    assert row["country"] == "Egypt"
    assert row["brand"] == "Elsewedy"
    assert row["category"] == "Wires" and row["category_ar"] == "أسلاك"
    # The six variations of one cable differ only in the SKU suffix; the id
    # they share is what lets a spreadsheet group them without parsing text.
    assert row["product_id"] == "9797" and row["sku"] == "76ec8c8572f0-1"
    assert row["discount"] == -84.67 and row["discount_pct"] == -7.0


def test_product_sources_show_no_country_rather_than_a_star(conn):
    """A shop has no per-row geography; '*' must read as blank, not an asterisk."""
    from scrapex.reports import export_source_table
    ingest_payloads(conn, make_entry(default_region="*"), [make_payload([one_row(country_code_alpha2="*")])])
    header, table = export_source_table(conn, "ELSEWEDYSHOP")
    row = dict(zip(header, table[0]))
    assert row["country_code_alpha2"] == "" and row["country"] == ""


def test_search_accepts_the_country_NAME_not_only_the_code(conn):
    """The region is stored as a code but a person searches by name — typing
    "Egypt" must find the Egyptian row, not zero rows."""
    from scrapex.reports import browse_observations, region_code
    _commodity_rows(conn, regions=("EG", "SA", "US"))
    assert region_code("Egypt") == "EG" and region_code("Saudi Arabia") == "SA"
    assert region_code("EG") == "" and region_code("nonsense") == ""

    assert browse_observations(conn, "GPP_ENERGY", search="Egypt").total == 1
    assert browse_observations(conn, "GPP_ENERGY", search="EG").total == 1
    assert browse_observations(conn, "GPP_ENERGY", search="Saudi Arabia").total == 1


# ---- USD est. is per-source column state, never a global switch --------------
#
# The owner's report (2026-07-22): one GPP crawl landing one implied rate made
# "USD est." appear on EVERY source, its values computed through a fuel site's
# arithmetic. Column state belongs to each source — the engine is shared, the
# gates are not (see the INVARIANT on column_presence).

def _rate(conn, currency="EGP", per_usd=51.25):
    conn.execute(
        "INSERT INTO currency_rate (currency, per_usd, as_of, source_key) "
        "VALUES (?,?,?,?)", (currency, per_usd, "2026-07-13", "GPP_ENERGY"))


def test_usd_est_never_leaks_onto_a_single_currency_source(conn):
    from scrapex.reports import column_presence, table_payload

    _rate(conn)
    ingest_payloads(conn, make_entry(), [make_payload([one_row()])])   # EGP only

    assert "price_usd" not in column_presence(conn, "ELSEWEDYSHOP")
    grid = table_payload(conn, "ELSEWEDYSHOP")
    assert "price_usd" not in {c["key"] for c in grid["columns"]}, \
        "a one-currency shop got a USD twin of its own Price column"


def test_a_multi_currency_source_with_a_relevant_rate_keeps_usd_est(conn):
    from scrapex.reports import column_presence

    _rate(conn)
    ingest_payloads(conn, make_entry(), [make_payload([
        one_row(),
        one_row(external_product_id="1002", external_variant_id="5002",
                external_sku="SKU2", currency="USD"),
    ])])

    assert "price_usd" in column_presence(conn, "ELSEWEDYSHOP"), \
        "ranking across currencies is exactly what the column exists for"


def test_multi_currency_without_any_relevant_rate_stays_without_usd_est(conn):
    from scrapex.reports import column_presence

    _rate(conn, currency="KWD")            # a rate exists — but for nobody here
    ingest_payloads(conn, make_entry(), [make_payload([
        one_row(),
        one_row(external_product_id="1002", external_variant_id="5002",
                external_sku="SKU2", currency="USD"),
    ])])

    assert "price_usd" not in column_presence(conn, "ELSEWEDYSHOP"), \
        "a column that can only render empty cells was still offered"


def test_each_variation_axis_becomes_its_own_export_column(conn):
    """The owner exported a variable product and read "Color: أحمر" in ONE cell.

    A spreadsheet cannot filter, group or pivot on that, which is the only
    reason the column exists — and he asked for the fix at the root, not for
    the string to be cut at the far end. So the axes travel from the connector
    as structure and arrive as columns named the way the SITE names them.
    """
    from scrapex.reports import export_source_table
    ingest_payloads(conn, make_entry(), [make_payload([
        one_row(external_variant_id="v1", variant_ar="Color: أحمر",
                variant_axes_ar='{"Color":"أحمر"}'),
        one_row(external_variant_id="v2", variant_ar="Color: أخضر",
                variant_axes_ar='{"Color":"أخضر"}', price="99.00"),
    ])])
    header, table = export_source_table(conn, "ELSEWEDYSHOP")

    assert "Color" in header, "the axis never became a column"
    # Beside the variation it was welded into, not at the far end. The exported
    # variation is now a PAIR — variant (English) and variant_ar — so the axes
    # follow the Arabic side, which is the last of the two.
    assert header.index("Color") == header.index("variant_ar") + 1, \
        "the axis belongs beside the variation, not at the far end"
    rows = sorted(dict(zip(header, row))["Color"] for row in table)
    assert rows == ["أحمر", "أخضر"]


def test_a_source_without_variations_gains_no_empty_axis_columns(conn):
    from scrapex.reports import EXPORT_HEADER, export_source_table
    ingest_payloads(conn, make_entry(), [make_payload([one_row()])])
    header, _table = export_source_table(conn, "ELSEWEDYSHOP")
    assert header == EXPORT_HEADER


def test_a_variation_is_linked_to_its_own_page_not_the_products(conn):
    """Every variation of one product used to carry the SAME url — the product's
    — because the variation's own address had nowhere to live. Live on
    samehgabriel that meant 108 variants sharing one link, so five of every six
    opened the wrong colour."""
    from scrapex.reports import export_source_table, table_payload
    ingest_payloads(conn, make_entry(), [make_payload([
        one_row(external_variant_id="v1", variant_ar="Color: أحمر",
                product_link="https://shop.example/wire/",
                variant_url="https://shop.example/wire/?attribute_pa_color=black"),
    ])])

    header, table = export_source_table(conn, "ELSEWEDYSHOP")
    row = dict(zip(header, table[0]))
    assert row["product_link"].endswith("attribute_pa_color=black")
    assert table_payload(conn, "ELSEWEDYSHOP")["rows"][0]["product_link"].endswith(
        "attribute_pa_color=black")


def test_a_product_without_variations_keeps_its_own_link(conn):
    """The fallback matters as much: a source with no variations publishes no
    variant_url, and the row must still link somewhere."""
    from scrapex.reports import export_source_table
    ingest_payloads(conn, make_entry(), [make_payload([
        one_row(product_link="https://shop.example/floodlight/")])])
    header, table = export_source_table(conn, "ELSEWEDYSHOP")
    assert dict(zip(header, table[0]))["product_link"] == "https://shop.example/floodlight/"


def test_every_read_path_names_a_fact_the_same_way(conn):
    """The owner's question, turned into a guard: is a column called the same
    thing on EVERY path it appears on?

    It was not. The declared lists agreed perfectly — table, export, filters,
    bilingual pairs, details and history headers — while four read paths kept a
    private vocabulary underneath them: browse_observations said `name` and
    `option_label` and `last_confirmed` for what table_payload calls
    product_name_ar, variant_ar and last_confirmed_on; offer_identity said
    `name`/`name_ar`; recent_observations said `name`/`price`; and
    recent_changes aliased the ARABIC name to `product_name` — a key asserting
    English over a column holding Arabic, which is the exact defect the whole
    vocabulary exists to delete, reappearing one layer down.

    Comparing the declared lists to each other could never have caught that,
    because they were consistent. This compares what the code actually RETURNS.
    """
    from scrapex.changes import recent_changes
    from scrapex.reports import (browse_observations, offer_identity,
                                 recent_observations, table_payload)

    ingest_payloads(conn, make_entry(), [make_payload([one_row(
        product_name="Copper wire", product_name_ar="سلك نحاس")])])

    payload = table_payload(conn, "ELSEWEDYSHOP", limit=1)
    offer_id = payload["rows"][0]["offer_id"]
    shapes = {
        "table_payload": payload["rows"][0],
        "browse_observations": browse_observations(conn, "ELSEWEDYSHOP", limit=1).rows[0],
        "offer_identity": offer_identity(conn, "ELSEWEDYSHOP", offer_id),
        "recent_observations": recent_observations(conn, "ELSEWEDYSHOP", 1)[0],
        "recent_changes": recent_changes(conn, "ELSEWEDYSHOP", limit=1)[0],
    }

    # Words that were private names for a fact the vocabulary already names.
    retired = {"name": "product_name / product_name_ar",
               "name_ar": "product_name_ar",
               "option_label": "variant_ar",
               "option_axes": "variant_axes_ar",
               "last_confirmed": "last_confirmed_on",
               # `business_date` is NOT retired: on a history row it is the
               # date that price applied, which HISTORY_HEADER names, and
               # that is a different question from "when did it last move".
               # It was only wrong on browse_observations, where it stood
               # for price_changed_on.
               "region": "country_code_alpha2",
               "region_name": "country",
               "product_name_en": "product_name",
               "category_en": "category"}
    for path, row in shapes.items():
        for key in retired:
            assert key not in row, (
                f"{path} still calls it {key!r}; the rest of the product calls "
                f"it {retired[key]!r}")


def test_the_table_catalogue_covers_every_table_the_schema_creates(conn):
    """TABLE_GROUPS is a hand-written second copy of the DDL inventory, and it
    had already drifted. `source_attribute_promotion` shipped in migration 0044,
    is written by fields.py and read by reports.py itself — and was missing from
    the catalogue, so /data-model showed a live, actively-written table under
    "Other tables" with a blank purpose. Nothing failed; the page just quietly
    degraded, and the append-to-Other bucket was the only feedback there was.
    """
    from scrapex.reports import TABLE_GROUPS

    live = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' "
        "AND name NOT LIKE 'sqlite_%'")}
    catalogued = {name for *_head, rows in TABLE_GROUPS for name, _purpose in rows}

    missing = sorted(live - catalogued)
    assert not missing, (
        "these tables exist in the warehouse and are not described in "
        f"TABLE_GROUPS, so /data-model files them under Other with no purpose: {missing}")


def test_every_browsable_column_says_what_it_means():
    """The same decay as the table catalogue above, one level down.

    Adding a column means touching several hand-written lists, and COLUMN_NOTES
    is the one with no consequence for forgetting it: /schema simply prints the
    column with an empty meaning cell. `brand_ar` shipped that way, and this
    guard found `price_trade` sitting in the same state — which is the argument
    for the guard rather than for fixing the two by hand.
    """
    from scrapex.reports import BROWSE_COLUMNS, COLUMN_NOTES

    # The derived family: category_l1/_l2/... are explained by a rule in
    # schema_page rather than one entry each, so they are covered, not missing.
    def described(key: str) -> bool:
        return key in COLUMN_NOTES or (key.startswith("category_") and "_l" in key)

    silent = sorted(key for key, _label in BROWSE_COLUMNS if not described(key))
    assert not silent, (
        "these columns appear in the table and say nothing about themselves on "
        f"/schema, so the page shows a blank meaning cell: {silent}")


# ---- folding a product's same-priced variations (owner ruling 2026-07-28) ----
# samehgabriel sells 18 products in 6 colours each, so the table showed 108 rows
# that differed only by colour. The fold is a DISPLAY rule, per source: the
# warehouse still stores every row the site published.

def _variant_row(**over):
    row = {"source_product_id": 7, "product_name_ar": "سلك نحاس", "variant_ar": "أحمر",
           "variant": "Red", "sku": "abc-1", "price": 100.0, "currency": "EGP",
           "availability": "in_stock", "price_min": 100.0, "price_max": 120.0,
           "observations": 4, "offer_id": 1, "stock_quantity": 5}
    row.update(over)
    return row


def test_same_priced_variations_become_one_row_listing_them():
    rows = [_variant_row(),
            _variant_row(variant_ar="أزرق", variant="Blue", sku="abc-2", offer_id=2),
            _variant_row(variant_ar="أخضر", variant="Green", sku="abc-3", offer_id=3)]
    folded = fold_variant_rows(rows)
    assert len(folded) == 1
    assert folded[0]["variant_ar"] == "أحمر، أزرق، أخضر"
    assert folded[0]["variant"] == "Red, Blue, Green"
    assert folded[0]["sku"] == "abc-1, abc-2, abc-3"
    assert folded[0]["variants"] == 3
    assert folded[0]["offer_ids"] == [1, 2, 3]
    assert folded[0]["offer_id"] == 1, "the record panel must still open"


def test_a_product_priced_differently_per_variation_stays_separate_rows():
    """17 of samehgabriel's 18 products charge one price for every colour. One
    charges two, and folding it into a single row would state a price the site
    does not charge for half of them."""
    rows = [_variant_row(), _variant_row(variant_ar="أزرق", sku="abc-2", offer_id=2),
            _variant_row(variant_ar="أصفر", sku="abc-3", offer_id=3, price=150.0)]
    folded = fold_variant_rows(rows)
    assert len(folded) == 2
    assert [r["price"] for r in folded] == [100.0, 150.0]
    assert folded[0]["variants"] == 2
    assert "variants" not in folded[1], "a row that folded nothing is untouched"


def test_a_fact_that_differs_is_blanked_rather_than_guessed():
    """A stock level that belonged to one colour must not be printed against
    three. The record panel still holds each variation's own."""
    rows = [_variant_row(stock_quantity=5),
            _variant_row(variant_ar="أزرق", sku="abc-2", offer_id=2, stock_quantity=0)]
    folded = fold_variant_rows(rows)
    assert folded[0]["stock_quantity"] == ""
    assert folded[0]["availability"] == "in_stock", "identical facts survive"


def test_history_is_recomputed_for_the_group_not_carried_from_the_first_row():
    """price_min/price_max belong to ONE offer's timeline. Across a fold they
    are aggregates of several, so they are recomputed - carrying the first
    row's would understate the range the group actually saw."""
    rows = [_variant_row(price_min=100.0, price_max=110.0),
            _variant_row(variant_ar="أزرق", sku="abc-2", offer_id=2,
                         price_min=90.0, price_max=130.0)]
    folded = fold_variant_rows(rows)
    assert folded[0]["price_min"] == 90.0
    assert folded[0]["price_max"] == 130.0


def test_two_products_at_the_same_price_do_not_merge():
    rows = [_variant_row(source_product_id=7), _variant_row(source_product_id=8)]
    assert len(fold_variant_rows(rows)) == 2


def test_rows_with_no_product_identity_are_never_pooled_together():
    """A commodity row carries no source_product_id. Grouping them all under
    one None key would collapse unrelated rows into one."""
    rows = [_variant_row(source_product_id=None), _variant_row(source_product_id=None)]
    assert len(fold_variant_rows(rows)) == 2


def test_folding_is_off_unless_the_source_asks_for_it(conn):
    ingest_payloads(conn, make_entry(), [make_payload([
        one_row(external_product_id="1", external_variant_id="v1", variant="Red"),
        one_row(external_product_id="1", external_variant_id="v2", variant="Blue"),
    ])])
    assert len(table_payload(conn, "ELSEWEDYSHOP")["rows"]) == 2
    payload = table_payload(conn, "ELSEWEDYSHOP", fold_variants=True)
    assert len(payload["rows"]) == 1
    assert payload["folded"] is True
    assert payload["total"] == 2, "what the site published is still reported"
    assert payload["truncated"] is False, "a fold is not a truncation"


def test_a_shared_axis_name_is_printed_once_not_per_value():
    """A variant is stored as the site labels it - "Color: أحمر". Six of those
    joined said the word Color six times to state one axis."""
    rows = [_variant_row(variant_ar="Color: أحمر"),
            _variant_row(variant_ar="Color: أخضر", sku="abc-2", offer_id=2),
            _variant_row(variant_ar="Color: أزرق", sku="abc-3", offer_id=3)]
    folded = fold_variant_rows(rows)
    assert folded[0]["variant_ar"] == "Color: أحمر، أخضر، أزرق"


def test_two_different_axes_each_keep_their_own_name():
    """The moment the values disagree about the axis, the axis IS information
    and every value keeps it."""
    rows = [_variant_row(variant_ar="Color: أحمر"),
            _variant_row(variant_ar="Size: كبير", sku="abc-2", offer_id=2)]
    folded = fold_variant_rows(rows)
    assert folded[0]["variant_ar"] == "Color: أحمر، Size: كبير"


def test_values_with_no_axis_name_are_joined_untouched():
    rows = [_variant_row(variant_ar="أحمر"),
            _variant_row(variant_ar="أخضر", sku="abc-2", offer_id=2)]
    assert fold_variant_rows(rows)[0]["variant_ar"] == "أحمر، أخضر"


# ---- the row's own deepest classification (owner ask 2026-07-28) -------------

def test_the_leaf_is_the_last_level_the_row_actually_reaches():
    """MADAR classifies some rows to three levels and others to one, so no
    single Category L-column holds "the most specific thing this row is"."""
    assert _category_leaf("Cables > Low voltage > Copper") == "Copper"
    assert _category_leaf("Cables") == "Cables"
    assert _category_leaf("") == ""
    assert _category_leaf(None) == ""


def test_the_leaf_ignores_empty_segments_and_stray_spacing():
    assert _category_leaf("Cables >  > Copper ") == "Copper"
    assert _category_leaf("Cables > > ") == "Cables"


def test_the_leaf_survives_a_path_deeper_than_the_level_ceiling():
    """The L-columns stop at CATEGORY_LEVELS. The leaf must still be true for a
    path deeper than that, or the one column that claims to hold the last level
    would hold the tenth."""
    deep = " > ".join(f"L{n}" for n in range(1, CATEGORY_LEVELS + 4))
    assert _category_leaf(deep) == f"L{CATEGORY_LEVELS + 3}"


def test_both_languages_get_their_own_leaf_and_the_switch_flips_them():
    assert BILINGUAL_COLUMNS["category_leaf_ar"] == "category_leaf"
