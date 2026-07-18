"""Q2/T2: the ONE shared parser — exact-value assertions, error paths included."""
from __future__ import annotations

from decimal import Decimal

import pytest

from scrapex.normalize import fold_digits, option_fingerprint, parse_money, record_hash


# ---- fold_digits -------------------------------------------------------------

def test_arabic_indic_digits_fold():
    assert fold_digits("١٢٣٤٫٥٦") == "1234.56"


def test_eastern_arabic_digits_fold():
    assert fold_digits("۴۲") == "42"


def test_ascii_passes_through():
    assert fold_digits("129.38 SAR") == "129.38 SAR"


# ---- parse_money: every documented case pinned exactly (T2) -------------------

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1,234.56", Decimal("1234.56")),      # comma thousands, dot decimal
        ("1.234,56", Decimal("1234.56")),      # EU style
        ("١٢٣٤٫٥٦", Decimal("1234.56")),       # Arabic digits + Arabic decimal
        ("129.38 SAR", Decimal("129.38")),     # currency token stripped
        ("SAR 168.78", Decimal("168.78")),
        ("ر.س 112.50", Decimal("112.50")),
        ("1,234", Decimal("1234")),            # single comma, 3 trailing -> thousands
        ("12,5", Decimal("12.5")),             # single comma, 1-2 trailing -> decimal
        ("1,234,567", Decimal("1234567")),     # multi comma -> thousands
        ("820", Decimal("820")),
        ("0.004", Decimal("0.004")),           # globalpetrolprices Venezuela case
        ("-15.5", Decimal("-15.5")),
    ],
)
def test_parse_money_exact(raw: str, expected: Decimal):
    assert parse_money(raw) == expected


def test_none_and_empty_return_none():
    assert parse_money(None) is None
    assert parse_money("") is None
    assert parse_money("   ") is None


def test_garbage_fails_loud_not_silent():
    """Q3: None-on-garbage would hide connector defects — must raise."""
    with pytest.raises(ValueError, match="no numeric content"):
        parse_money("Call for price")


def test_currency_only_fails_loud():
    with pytest.raises(ValueError, match="no numeric content"):
        parse_money("SAR")


# ---- option_fingerprint --------------------------------------------------------

def test_fingerprint_is_sorted_lowercased_folded():
    fp = option_fingerprint({"Thickness_MM": "١٨", "Width_MM": "1220"})
    assert fp == "thickness_mm=18|width_mm=1220"


def test_fingerprint_deterministic_across_dict_order():
    a = option_fingerprint({"a": "1", "b": "2"})
    b = option_fingerprint({"b": "2", "a": "1"})
    assert a == b


# ---- record_hash ----------------------------------------------------------------

def test_record_hash_deterministic_and_order_insensitive():
    h1 = record_hash({"price": "168.78", "availability": "in_stock"})
    h2 = record_hash({"availability": "in_stock", "price": "168.78"})
    assert h1 == h2 and len(h1) == 64


def test_record_hash_changes_with_content():
    assert record_hash({"price": "168.78"}) != record_hash({"price": "170.00"})
