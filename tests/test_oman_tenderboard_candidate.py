"""The Oman candidate: the declared schema, R-12's shape, and what is deliberately absent.

No network. The fixtures are the same real 2026-09-18 captures the reader's tests use, so
the row that has no CR number is present in the English fixture and absent from the Arabic
one — which is why the candidate is built from the pairable rows and the reader's own
refusal is tested next door.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from scrapex.extract.oman_tenderboard import (
    DATASET_KEY,
    FIELDS,
    IDENTITY_FIELD,
    NO_ARABIC_TWIN,
    bilingual_listing_candidate,
)
from scrapex.sites.oman_tenderboard import RegisterShapeError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
EN = (FIXTURES / "oman_register_en.html").read_text(encoding="utf-8")
AR = (FIXTURES / "oman_register_ar.html").read_text(encoding="utf-8")


def _pairable_en() -> str:
    """The English fixture without the firm that has no CR number.

    That firm cannot be paired by construction and the reader raises on it; this file is
    about the candidate, so it is removed here rather than the refusal being weakened.
    """
    return re.sub(r"<tr[^>]*>(?:(?!</tr>).)*ZYPHARSPH(?:(?!</tr>).)*</tr>",
                  "", EN, flags=re.S)


def _candidate():
    return bilingual_listing_candidate(_pairable_en(), AR)


# --- the declared schema -------------------------------------------------------------

def test_the_field_list_is_declared_and_in_its_declared_order():
    """Derived from the page, the schema becomes a property of which firms that page
    showed — which refused 823 of 897 muqawil pages."""
    fields = [f.field_key for f in _candidate().fields]
    assert fields[:len(FIELDS)] == list(FIELDS)


def test_every_field_is_nullable_and_text_whatever_this_page_happens_to_hold():
    """Measured per page, `nullable` flips and the schema hash with it."""
    for field in _candidate().fields:
        assert field.nullable is True, field.field_key
        assert field.data_type == "text", field.field_key


def test_the_identity_is_the_short_name_and_only_it():
    candidate = _candidate()
    identities = [f.field_key for f in candidate.fields if f.identity_candidate]
    assert identities == [IDENTITY_FIELD] == ["short_name"]


def test_the_same_schema_comes_back_for_a_page_with_different_firms():
    """The order and the set must not depend on the rows; that is the whole lesson."""
    one = [f.field_key for f in _candidate().fields]
    single = re.sub(
        r"<tr[^>]*>(?:(?!</tr>).)*00169963(?:(?!</tr>).)*</tr>", "",
        _pairable_en(), flags=re.S)
    two = [f.field_key for f in bilingual_listing_candidate(single, AR).fields]
    assert one == two


def test_every_row_carries_every_field_even_when_absent():
    """`_validated_rows` walks the field list; a row simply lacking a key raises."""
    candidate = _candidate()
    names = {f.field_key for f in candidate.fields}
    for row in candidate.rows:
        assert set(row) == names


def test_the_dataset_is_named_once_and_not_guessed_per_call():
    assert DATASET_KEY == "oman_registered_vendors"
    assert _candidate().name == "Oman registered vendors"


# --- R-12's bilingual shape ----------------------------------------------------------

def test_the_english_view_fills_the_base_column_and_the_arabic_fills_its_twin():
    row = next(r for r in _candidate().rows if r["short_name"] == "0000")
    assert row["firm_name"] == "AL REEF LINE UNITED TRADE CO LLC"
    assert re.search(r"[؀-ۿ]", row["firm_name_ar"])
    assert row["registered_category"] == "Services"
    assert row["registered_category_ar"] == "الخدمات"


def test_the_address_base_column_stays_null_because_the_english_view_is_arabic():
    """A rule here, not an exception — measured on every row of page 1."""
    for row in _candidate().rows:
        assert row["address"] is None
    located = [r for r in _candidate().rows if r["address_ar"]]
    assert located and re.search(r"[؀-ۿ]", located[0]["address_ar"])


def test_an_identifier_gets_no_arabic_twin():
    declared = set(FIELDS)
    for name in NO_ARABIC_TWIN:
        assert name in declared
        assert f"{name}_ar" not in declared


def test_exactly_four_fields_carry_an_arabic_twin():
    """The four the site translates. `address`'s base column is NULL by measurement
    rather than absent, so the pair still exists."""
    twins = {f[:-3] for f in FIELDS if f.endswith("_ar")}
    assert twins == {"firm_name", "address", "registered_category", "company_type"}
    for name in twins:
        assert name in FIELDS, f"a twin with no base column: {name}"


# --- the category cell ---------------------------------------------------------------

def test_the_raw_category_cell_is_stored_whole():
    row = next(r for r in _candidate().rows if r["short_name"] == "00169963")
    assert row["registered_category"].startswith("Information Technology Services")
    assert len(row["registered_category"]) > 60, "several names, no separator"


def test_the_decomposed_list_is_deliberately_not_stored():
    """A delimited column is what `docs/GULF-EGYPT-SOURCES.md:353` refuses and what R-19
    measured the penalty for. The raw cell plus the vocabulary reproduces it."""
    names = {f.field_key for f in _candidate().fields}
    assert "registered_category_codes" not in names
    assert "registered_categories" not in names


def test_the_count_of_decomposed_categories_is_stored_flat():
    rows = {r["short_name"]: r for r in _candidate().rows}
    assert rows["0000"]["registered_category_count"] == "1"
    assert int(rows["00169963"]["registered_category_count"]) > 1


def test_what_the_vocabulary_could_not_explain_is_empty_on_every_measured_row():
    """The health signal: 102 of 102 decomposed with nothing left over."""
    assert all(r["registered_category_undecoded"] is None for r in _candidate().rows)


def test_a_cell_the_vocabulary_cannot_explain_lands_in_the_warehouse_visibly():
    broken = _pairable_en().replace(
        "<td>Services</td>", "<td>Services Something Unpublished</td>", 1)
    rows = bilingual_listing_candidate(broken, AR).rows
    leftover = [r["registered_category_undecoded"] for r in rows
                if r["registered_category_undecoded"]]
    assert leftover == ["Something Unpublished"]


# --- the rest of the row -------------------------------------------------------------

def test_a_blank_cell_reads_as_absent_and_not_as_empty_text():
    row = next(r for r in _candidate().rows if r["short_name"] == "00004174")
    assert row["reg_expiry"] is None
    assert row["address_ar"] is None or row["address_ar"]


def test_the_expiry_is_kept_as_the_site_printed_it():
    row = next(r for r in _candidate().rows if r["short_name"] == "0000")
    assert row["reg_expiry"] == "07-05-2026", "dd-MM-yyyy, not reformatted"


def test_the_short_name_keeps_its_leading_zeros():
    assert "0000" in {r["short_name"] for r in _candidate().rows}


def test_the_candidate_is_approvable_only_when_it_has_rows():
    assert _candidate().approvable is True
    empty = re.sub(r"<tr[^>]*>(?:(?!</tr>).)*getProcActivities(?:(?!</tr>).)*</tr>",
                   "", _pairable_en(), flags=re.S)
    assert bilingual_listing_candidate(empty, AR).approvable is False


def test_an_unpairable_firm_reaches_the_candidate_as_a_refusal_not_a_gap():
    """The full English fixture still holds the firm with no CR number."""
    with pytest.raises(RegisterShapeError, match="no counterpart"):
        bilingual_listing_candidate(EN, AR)
