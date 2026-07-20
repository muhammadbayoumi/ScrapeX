"""What makes two prices comparable (spec: price-history storage semantics).

The rule under test: everything that makes two prices non-comparable belongs in
the key — the money, the denomination it is quoted in, and what is being priced —
and nothing else does.
"""
from __future__ import annotations

import pytest

from scrapex import pricekey


def key(**over) -> pricekey.PriceKey:
    base = dict(effective="100", currency="SAR", vat=1)
    base.update(over)
    return pricekey.build(**base)


# ---- what does NOT belong ----------------------------------------------------

def test_stock_and_availability_are_not_part_of_the_price():
    """The owner wants the latest stock state, never its history. A stock
    movement that leaves the price alone must not read as a new price."""
    assert not any(f in pricekey.ALL_FIELDS for f in ("stock", "availability"))


# ---- the money ---------------------------------------------------------------

def test_a_different_price_is_a_different_key():
    assert key(effective="100").digest != key(effective="101").digest


def test_the_same_amount_in_another_currency_is_not_the_same_price():
    assert key(currency="SAR").digest != key(currency="USD").digest


def test_the_same_number_on_a_different_vat_basis_is_not_the_same_price():
    assert key(vat=1).digest != key(vat=0).digest


def test_currency_case_and_padding_do_not_invent_a_change():
    assert key(currency="sar").digest == key(currency=" SAR ").digest


# ---- the denomination --------------------------------------------------------

def test_the_same_number_per_litre_and_per_gallon_are_different_prices():
    """The failure this prevents: a source switching unit turns 15,000/tonne into
    15/kg, and without the unit that reads as a 99.9% price collapse."""
    assert key(unit="USD/liter").digest != key(unit="USD/gallon").digest


def test_the_same_number_in_two_countries_is_not_one_price_series():
    assert key(region="EG").digest != key(region="SA").digest


def test_a_source_with_no_regional_split_is_treated_as_having_no_region():
    """'*' means this source does not divide by region. Hashing it would make an
    absence look like a place."""
    assert key(region="*").digest == key().digest
    assert "region" not in key(region="*").fields


# ---- what is being priced ----------------------------------------------------

def test_the_same_bag_from_two_factories_is_not_one_price_series():
    """50kg of cement from two manufacturers is two products at two prices."""
    assert key(brand="Lafarge").digest != key(brand="Titan").digest


def test_a_corrected_spelling_does_not_open_a_new_price_period():
    """Normalising is what makes the manufacturer safe to hash: excluding it
    would have been the cheap fix and would also stop Lafarge and Titan being
    told apart."""
    assert key(brand="Lafarge").digest == key(brand=" lafarge ").digest
    assert key(brand="LAFARGE").digest == key(brand="Lafarge").digest


def test_origin_and_specification_separate_prices_when_a_source_supplies_them():
    assert key(origin="Germany").digest != key(origin="China").digest
    assert key(spec="Grade 42.5").digest != key(spec="Grade 52.5").digest


# ---- dynamic fields: stores differ -------------------------------------------

def test_a_field_the_source_does_not_supply_is_absent_not_empty():
    """An empty string is a value like any other. Hashing one would make 'this
    store never says' indistinguishable from 'this store said nothing'."""
    plain = key()
    assert plain.fields == pricekey.MONEY_FIELDS
    assert "brand" not in plain.fields and "origin" not in plain.fields


def test_a_richer_source_records_the_fields_it_actually_had():
    rich = key(region="SA", unit="bag", brand="Lafarge")
    assert set(rich.fields) == set(pricekey.MONEY_FIELDS) | {"region", "unit", "brand"}


def test_two_keys_built_from_different_fields_are_not_comparable():
    """The day a store starts publishing a manufacturer, every one of its offers
    would otherwise appear to change price at once."""
    before = key()
    after = key(brand="Lafarge")
    assert before.digest != after.digest, "the key genuinely changed"
    assert not pricekey.comparable(before.fields, after.fields), \
        "...but the two are not comparable, so it is not a price change"


def test_learning_a_field_is_reported_as_widening_not_as_a_price_change():
    before, after = key(), key(brand="Lafarge")
    assert pricekey.widened(before.fields, after.fields) == ("brand",)
    assert pricekey.narrowed(before.fields, after.fields) == ()


def test_a_source_that_stops_publishing_a_field_is_reported_as_narrowing():
    before, after = key(brand="Lafarge"), key()
    assert pricekey.narrowed(before.fields, after.fields) == ("brand",)


def test_the_same_fields_and_the_same_money_compare_equal():
    a, b = key(brand="Lafarge", region="SA"), key(brand="Lafarge", region="SA")
    assert pricekey.comparable(a.fields, b.fields) and a.digest == b.digest


# ---- the stored form ---------------------------------------------------------

def test_the_field_list_round_trips():
    built = key(brand="Lafarge", unit="bag")
    assert pricekey.parse_fields(built.field_list) == built.fields


def test_a_row_written_before_this_existed_reads_as_unknown_not_as_empty():
    """Migration 0015 adds the columns and never back-fills — back-filling would
    mean UPDATE-ing rows the append-only triggers forbid touching."""
    assert pricekey.parse_fields(None) == ()
    assert pricekey.parse_fields("") == ()


def test_an_unknown_field_name_is_ignored_rather_than_trusted():
    assert pricekey.parse_fields("effective,nonsense,brand") == ("effective", "brand")


# ---- the version guard -------------------------------------------------------

def test_the_key_version_travels_with_the_hash(monkeypatch):
    """Changing what a field MEANS must re-baseline every offer, not report a
    warehouse-wide price change."""
    before = key(brand="Lafarge")
    monkeypatch.setattr(pricekey, "PRICE_KEY_VERSION", pricekey.PRICE_KEY_VERSION + 1)
    assert key(brand="Lafarge").digest != before.digest


# ---- the cross-engine contract ----------------------------------------------

def test_a_trailing_zero_is_not_a_price_change():
    """The frozen contract: money reaches a hash as a canonical string, because
    Python renders 15.0 where the other engine renders 15. A source quoting
    '0.620' one week and '0.62' the next is quoting the SAME price.
    """
    from scrapex.ingest import _canon_amount
    from decimal import Decimal

    assert key(effective=_canon_amount(Decimal("0.620"))).digest == \
        key(effective=_canon_amount(Decimal("0.62"))).digest


def test_what_ingest_stores_is_a_key_over_canonical_money(tmp_path):
    """The guarantee end to end: the digest on the row is the one this module
    builds from canonical strings, not from whatever floats SQLite handed back.
    """
    from scrapex import db as dbmod
    from scrapex.ingest import ingest_payloads
    from tests.test_ingest import make_entry, make_payload, one_row

    conn = dbmod.connect(tmp_path / "h.db")
    dbmod.migrate(conn)
    ingest_payloads(conn, make_entry(), [make_payload(
        [one_row(effective_price="1,200.00", regular_price="1,200.00",
                 sale_price="", region="EG", brand_raw="Elsewedy")])])
    stored = conn.execute(
        "SELECT price_hash, price_fields FROM price_observation").fetchone()
    conn.close()

    expected = pricekey.build(effective="1200", regular="1200", sale="",
                              currency="EGP", vat=1, region="EG", brand="Elsewedy")
    assert stored["price_hash"] == expected.digest
    assert pricekey.parse_fields(stored["price_fields"]) == expected.fields
