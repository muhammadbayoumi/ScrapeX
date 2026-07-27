"""Q2/T2: the ONE shared parser — exact-value assertions, error paths included."""
from __future__ import annotations

from decimal import Decimal

import pytest

from scrapex.normalize import (
    fold_digits, option_fingerprint, parse_money, record_hash, selling_unit_from)


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


# ---- selling_unit_from -----------------------------------------------------------
#
# Moved here from the magento connector 2026-07-25: two families read a pack
# size off a name now (madar in Arabic, sikaegshop in English) and connectors
# never import each other (A1). Every case below is a real live product.

@pytest.mark.parametrize(
    ("name", "weight", "expected"),
    [
        ("اسمنت الرياض 50كجم", 50, ("50", "kg")),        # madar, Arabic spelling
        ('Sika Zinc Rich® -1 "5 KG"', 5, ("5", "kg")),   # sika, English, quoted
        ("Sika Viscocrete 3425 ®-5 kg", 5, ("5", "kg")),
        ("Sika Grout 200 ® 25 KG", 25, ("25", "kg")),
        # the site must state it TWICE and agree with itself:
        ("Sika Latex®- 20 kg", 5, ("", "")),             # live product 218
        ("Sika Creat 114 ® 20 KG", 1, ("", "")),         # live product 261
        # a weight alone is the PIECE's mass, not what one price buys:
        ("زاوية حديد 40x40x4", 4.986, ("", "")),
        ("Sika Backing ® Rod 1 CM", 1, ("", "")),        # a diameter, not a basis
        # nothing to read at all
        ("Sika Swell S2 ®  600ml", 1, ("", "")),
        ("Sika Fume® 5 KG", None, ("", "")),
        ("Sika Fume® 5 KG", 0, ("", "")),
        ("Sika Fume® 5 KG", "not a number", ("", "")),
        ("", 50, ("", "")),
    ],
)
def test_selling_unit_only_when_the_site_states_it_twice(name, weight, expected):
    assert selling_unit_from(name, weight) == expected


def test_a_fractional_pack_size_keeps_its_fraction():
    assert selling_unit_from("Sika Something 2.5 kg", 2.5) == ("2.5", "kg")
    assert selling_unit_from("Sika Something 2,5 kg", 2.5) == ("2.5", "kg")


# ---- record_hash ----------------------------------------------------------------

def test_record_hash_deterministic_and_order_insensitive():
    h1 = record_hash({"price": "168.78", "availability": "in_stock"})
    h2 = record_hash({"availability": "in_stock", "price": "168.78"})
    assert h1 == h2 and len(h1) == 64


def test_record_hash_changes_with_content():
    assert record_hash({"price": "168.78"}) != record_hash({"price": "170.00"})


# ---- the CSS the owner read in a product description -------------------------

def test_a_style_block_leaves_with_its_contents_not_just_its_tags():
    """Owner-reported, from madar's record panel: the Description opened with a
    paragraph of CSS before the Arabic text.

        #html-body [data-pb-style=JHMUASU]{justify-content:flex-start;…}

    Magento Page Builder writes a <style> block at the top of every description
    it composes. Stripping tags alone deletes `<style>` and `</style>` and keeps
    EVERYTHING BETWEEN THEM — a rule that removes the wrapper and keeps the
    payload is not a strip, it is a leak.
    """
    from scrapex.normalize import strip_markup

    raw = ("<style>#html-body [data-pb-style=JHMUASU],#html-body "
           "[data-pb-style=LHRGWPE]{justify-content:flex-start;display:flex;"
           "background-size:auto}</style>"
           "<div data-pb-style='JHMUASU'><p>حديد تسليح ابوكسي</p></div>")

    out = strip_markup(raw)

    assert "data-pb-style" not in out and "flex-start" not in out
    assert out == "حديد تسليح ابوكسي"


def test_an_unclosed_style_does_not_let_the_whole_tail_through():
    """The half-fix: removing only `<style>…</style>` pairs leaves an unclosed
    opener publishing the rest of the document as text."""
    from scrapex.normalize import strip_markup

    assert strip_markup("<style>p{color:red}<div>tail") == ""


def test_entities_are_unescaped_before_the_tags_go():
    """madar returns its description already escaped, so stripping first left
    the markup sitting in the value as literal text."""
    from scrapex.normalize import strip_markup

    assert strip_markup("&lt;article lang=&quot;ar&quot;&gt;نص&lt;/article&gt;") == "نص"


def test_every_connector_shares_one_stripper():
    """Three connectors had written this rule three times and one of them was
    wrong — the one that drifted is what put CSS in madar's description. The
    guard is the import, because a fourth copy is how it comes back."""
    from pathlib import Path

    root = Path(__file__).parents[1] / "scrapex" / "connectors"
    for name in ("magento.py", "woocommerce.py", "aramco.py"):
        body = (root / name).read_text(encoding="utf-8")
        assert "strip_markup" in body, f"{name} must use the shared stripper"
        assert 're.sub(r"<[^>]+>"' not in body, (
            f"{name} strips tags on its own again — that is the copy that drifts")
