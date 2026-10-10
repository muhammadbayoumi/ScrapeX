"""Q2/T2: the ONE shared parser — exact-value assertions, error paths included."""
from __future__ import annotations

from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest

from scrapex.normalize import (
    fold_digits,
    option_fingerprint,
    parse_clock,
    parse_date,
    parse_instant,
    parse_money,
    parse_money_with_currency,
    record_hash,
    selling_unit_from,
)


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
        # BOTH SIDES OF THE 1-2 BOUNDARY, because the comment above used to claim
        # "1-2" while only the 1 was here. Mutation proved the cost: `<= 2` -> `< 2`
        # publishes 12,50 as 1250 with all 4022 tests green (#967). The two-digit
        # tail is the commonest Arabic and European price shape, so it is the row
        # whose absence was most expensive.
        ("12,5", Decimal("12.5")),             # single comma, 1 trailing -> decimal
        ("12,50", Decimal("12.50")),           # 2 trailing -> decimal, the boundary
        ("1,50", Decimal("1.50")),             # 2 trailing, one digit before it
        ("0,75", Decimal("0.75")),             # 2 trailing, leading zero
        ("1,2345", Decimal("12345")),          # 4 trailing -> thousands, the far side
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


def test_text_beside_the_number_is_dropped_not_fatal():
    """Decimal() strips surrounding whitespace itself, so '129.38 SAR' above
    stays green with the numeric-keep sieve gone — these rows do not. Without
    it any leftover letter or inner space reaches Decimal and the price raises
    instead of parsing: a source stops publishing prices while every other
    source keeps working (#970)."""
    assert parse_money("Price: 100") == Decimal("100")
    assert parse_money("1 234.56") == Decimal("1234.56")
    assert parse_money("100 SAR/ton") == Decimal("100")


# ---- option_fingerprint --------------------------------------------------------

def test_fingerprint_is_sorted_lowercased_folded():
    fp = option_fingerprint({"Thickness_MM": "١٨", "Width_MM": "1220"})
    assert fp == "thickness_mm=18|width_mm=1220"


def test_fingerprint_deterministic_across_dict_order():
    a = option_fingerprint({"a": "1", "b": "2"})
    b = option_fingerprint({"b": "2", "a": "1"})
    assert a == b


def test_a_padded_axis_name_folds_to_the_same_axis():
    """The VALUE strip is pinned by the frozen contract vector; the KEY strip
    was pinned by nothing. Two spellings of one axis then fingerprint
    differently, and in an append-only warehouse that forks a variant into two
    rows that never merge again (#970)."""
    assert option_fingerprint({" Color ": "red"}) == "color=red"
    assert option_fingerprint({"Size\t": "L"}) == "size=l"
    assert option_fingerprint({" Color ": "red"}) == option_fingerprint({"Color": "red"})


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


def test_the_agreement_is_exact_not_within_a_kilogram():
    """Every disagreement case above differs by 15-19 kg, so only the
    EXISTENCE of the clamp is pinned, never its SIZE. A tolerance invents a
    basis the shop never stated, and basis quantity sits in the offer's unique
    key and its price key — a wrong one splits the offer's identity and
    restarts its price history (#970).

    The 20-vs-19.5 rows leave every tolerance under half a kilogram alive:
    `> 1e-6` -> `> 0.05` keeps all 47 green. The last row closes that band. A
    hundredth of a kilogram is below any pack size a site publishes and far
    above the float noise the clamp exists to absorb, so it stays true of any
    correct rewrite of the comparison."""
    assert selling_unit_from("Sika Grout 200 ® 20 KG", 19.5) == ("", "")
    assert selling_unit_from("Sika Grout 200 ® 20 KG", 20.9) == ("", "")
    assert selling_unit_from("Sika Something 2.5 kg", 2.51) == ("", "")


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


# ---- dates, instants, clock times and coded amounts (#1647 §6.1) --------------
# Every input below is a value the World Bank wrote, taken from the study's saved
# responses; the comment names the field it came from.

_WRITTEN_DATES = [
    ("07-Oct-2026", "DD-Mon-YYYY", date(2026, 10, 7)),             # procnotices noticedate
    ("19-May-2022", "DD-Mon-YYYY", date(2022, 5, 19)),             # Finances One API
    ("22-Sep-2026", "DD-Mon-YYYY", date(2026, 9, 22)),             # contractdata no-objection
    ("2026-11-05T00:00:00Z", "YYYY-MM-DDT00:00:00Z", date(2026, 11, 5)),  # the deadline
    ("10/08/2026", "MM/DD/YYYY", date(2026, 10, 8)),               # the bulk CSV: 8 October
    ("12/1/2025 12:00:00 AM", "M/D/YYYY 12:00:00 AM", date(2025, 12, 1)),  # closingdate
    ("2024-06-24 00:00:00.0", "YYYY-MM-DD 00:00:00.0", date(2024, 6, 24)),  # p2a_updated_date
    ("2024/07/01", "YYYY/MM/DD", date(2024, 7, 1)),                # an award text
]


@pytest.mark.parametrize(("raw", "layout", "expected"), _WRITTEN_DATES)
def test_each_layout_reads_the_date_the_source_wrote(raw, layout, expected):
    assert parse_date(raw, layout) == expected


@pytest.mark.parametrize("layout", sorted({layout for _, layout, _ in _WRITTEN_DATES}))
def test_every_layout_refuses_the_shapes_of_the_others(layout):
    """A layout is an assertion, not a hint: text in any other shape raises."""
    for raw, other, _ in _WRITTEN_DATES:
        if other != layout:
            with pytest.raises(ValueError, match="is not in the layout"):
                parse_date(raw, layout)


def test_the_same_digits_are_read_the_way_the_layout_says_never_guessed():
    """'10/08/2026' is 8 October in the Bank's CSV and 10 August under DD/MM. The
    layout decides; a day above 12 in the month's place raises instead of being
    quietly swapped into a date the source never wrote."""
    assert parse_date("10/08/2026", "MM/DD/YYYY") == date(2026, 10, 8)
    with pytest.raises(ValueError, match="no real day"):
        parse_date("13/08/2026", "MM/DD/YYYY")


def test_a_date_layout_refuses_an_instant_rather_than_truncating_it():
    """The search APIs carry a DATE as midnight UTC. Any other time of day would
    be an instant, and dropping its time would store a day the source never
    meant."""
    with pytest.raises(ValueError, match="is not in the layout"):
        parse_date("2026-10-07T13:45:00Z", "YYYY-MM-DDT00:00:00Z")
    with pytest.raises(ValueError, match="is not in the layout"):
        parse_date("12/1/2025 3:00:00 PM", "M/D/YYYY 12:00:00 AM")


def test_trailing_text_is_a_different_shape_not_a_date():
    with pytest.raises(ValueError, match="is not in the layout"):
        parse_date("07-Oct-2026 10:00", "DD-Mon-YYYY")


@pytest.mark.parametrize(("raw", "layout"), [
    ("31-Feb-2026", "DD-Mon-YYYY"),
    ("2026-02-30T00:00:00Z", "YYYY-MM-DDT00:00:00Z"),
    ("00/10/2026", "MM/DD/YYYY"),
])
def test_a_day_that_does_not_exist_fails_loud(raw, layout):
    with pytest.raises(ValueError, match="no real day"):
        parse_date(raw, layout)


def test_an_unknown_month_name_fails_loud():
    with pytest.raises(ValueError, match="names no month"):
        parse_date("07-Okt-2026", "DD-Mon-YYYY")


def test_a_month_name_is_read_in_any_case():
    assert parse_date("07-OCT-2026", "DD-Mon-YYYY") == date(2026, 10, 7)


def test_arabic_indic_digits_in_a_date_fold_first():
    assert parse_date("٠٧-Oct-٢٠٢٦", "DD-Mon-YYYY") == date(2026, 10, 7)


def test_an_unknown_layout_fails_loud_even_when_no_date_was_written():
    """A misspelt layout is the caller's defect; it must not hide behind a field
    that happens to be empty on the first rows read."""
    with pytest.raises(ValueError, match="unknown date layout"):
        parse_date(None, "auto")


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_no_date_written_is_none(raw):
    assert parse_date(raw, "DD-Mon-YYYY") is None


def test_an_instant_is_utc_and_keeps_its_time():
    """`api_modified_date`: the Bank's own change stamp, which an incremental pass
    compares."""
    assert parse_instant("2026-10-09T16:07:56Z") == datetime(2026, 10, 9, 16, 7, 56, tzinfo=UTC)


@pytest.mark.parametrize("raw", [
    "2026-10-09T16:07:56",        # no zone: a local time, not an instant
    "2026-10-09 16:07:56Z",       # a space where the T goes
    "2026-10-09T16:07Z",          # no seconds
    "09-Oct-2026",                # a date
])
def test_an_instant_in_another_shape_fails_loud(raw):
    with pytest.raises(ValueError, match="not an instant"):
        parse_instant(raw)


def test_an_instant_that_does_not_exist_fails_loud():
    with pytest.raises(ValueError, match="no real moment"):
        parse_instant("2026-10-09T24:00:00Z")


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_no_instant_written_is_none(raw):
    assert parse_instant(raw) is None


@pytest.mark.parametrize(("raw", "expected"), [
    ("14:00", time(14, 0)),       # submission_deadline_time
    ("9:05", time(9, 5)),
    ("00:00", time(0, 0)),
    ("23:45", time(23, 45)),
])
def test_a_clock_time_is_read_as_written(raw, expected):
    assert parse_clock(raw) == expected


def test_a_clock_time_carries_no_zone_because_the_source_states_none():
    """The deadline's zone is unknown (#1647 §8 Q6). This module must not assume
    one; the caller records it as unknown."""
    assert parse_clock("14:00").tzinfo is None


@pytest.mark.parametrize("raw", ["24:00", "12:60", "2 PM", "14:00:00", "14h00"])
def test_a_clock_time_in_another_shape_fails_loud(raw):
    with pytest.raises(ValueError, match="clock time"):
        parse_clock(raw)


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_no_clock_time_written_is_none(raw):
    assert parse_clock(raw) is None


@pytest.mark.parametrize(("raw", "expected"), [
    ("EGP 292182.000", (Decimal("292182.000"), "EGP")),   # a signed contract price
    ("USD 799673.00", (Decimal("799673.00"), "USD")),
    ("EUR 1,234.50", (Decimal("1234.50"), "EUR")),
    ("  DJF 178024  ", (Decimal("178024"), "DJF")),
])
def test_an_amount_keeps_the_currency_written_before_it(raw, expected):
    assert parse_money_with_currency(raw) == expected


def test_the_number_beside_the_code_is_the_one_parse_money_reads():
    """One parser for the number: the coded form must never disagree with it."""
    for raw in ("EGP 292182.000", "EUR 1,234.50", "USD 1.234,56"):
        assert parse_money_with_currency(raw)[0] == parse_money(raw.split(maxsplit=1)[1])


@pytest.mark.parametrize("raw", [
    "292182.000",         # no currency: parse_money's job, not this one's
    "EGP",                # a currency with no amount
    "egp 5",              # not a currency code's shape
    "EGP 5 USD",          # two currencies
    "Egyptian Pounds 5",  # a currency's name, not its code
])
def test_an_amount_without_one_coded_currency_fails_loud(raw):
    with pytest.raises(ValueError, match="currency code and an amount"):
        parse_money_with_currency(raw)


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_no_amount_written_is_none(raw):
    assert parse_money_with_currency(raw) is None
