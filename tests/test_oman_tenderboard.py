"""The Oman ESNAD register reader: the commented identifier, the paginator, the join.

No network. Every happy-path assertion runs against markup trimmed from the real
2026-09-18 captures, and each fixture row was chosen for a measured reason: a
single-category firm, a firm holding several categories concatenated with no separator,
a firm with **no CR number** (so it cannot be paired between languages), and a firm with
no expiry date.

The Arabic fixture holds the counterparts of the page-1 firms only. That is deliberate:
the blank-CR firm has no counterpart by construction, which is what `join_languages` is
supposed to refuse to paper over.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from scrapex.sites.oman_tenderboard import (
    BASE_URL,
    DIRECTIONS,
    LTR,
    ROWS_PER_PAGE,
    RTL,
    CategorySplit,
    RegisterShapeError,
    codes_for,
    decompose_categories,
    join_languages,
    read_categories,
    read_company_types,
    read_last_page,
    read_rows,
    read_subcategories,
    register_url,
    subcategory_url,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _en() -> str:
    return (FIXTURES / "oman_register_en.html").read_text(encoding="utf-8")


def _ar() -> str:
    return (FIXTURES / "oman_register_ar.html").read_text(encoding="utf-8")


def _xml() -> str:
    return (FIXTURES / "oman_subcategory_z1.xml").read_text(encoding="utf-8")


def _row(short="00001234", name="A FIRM LLC", cr="00011111-1111111", addr="مسقط",
         tel="99000000", fax="", cat="Services", exp="01-01-2027", vtype="Local",
         echo=None, comment=True):
    """One synthetic data row in the register's own markup."""
    key = short if echo is None else echo
    hidden = f"<!-- <td>{short}</td> -->" if comment else f"<td>{short}</td>"
    return (
        "<tr class='odd gradeA'>"
        '<td align="center">1</td>'
        f"{hidden}"
        f"<td>{name}</td><td align=\"center\">{cr}</td><td align=\"center\">{addr}</td>"
        f"<td>{tel}</td><td align=\"center\">{fax}</td><td>{cat}</td><td>{exp}</td>"
        f"<td>{vtype}</td>"
        '<td align="center"><a href="#banner"><img id="procAct" '
        f"onClick=\"getProcActivities('{key}')\"></a></td>"
        "</tr>")


def _page(rows, pages=3):
    nav = ("<tr class=\"rownohover\"><td colspan=\"12\">"
           "<table cellpadding='1' class='Pagination_table'><tbody>"
           "<tr><td class='Pagination_td'>&nbsp;Page&nbsp;</td>"
           f"<td class='Pagination_td'>&nbsp;of {pages}&nbsp;</td>"
           f"<input type='hidden' name='hidMax' value='{pages}'>"
           f"<td><A href='#banner' onclick=\"ShowPage({pages})\">Last&raquo;</A></td>"
           "</tr></tbody></table></td></tr>")
    return ("<html><body>"
            '<select name="category"><option value="-1">--Select--</option>'
            '<option value="Z6">Services</option>'
            '<option value="Z8">Supply</option>'
            '<option value="I1">Supply and Services (Old)</option></select>'
            '<select name="vendType"><option value="-1">--Select--</option>'
            '<option value="0">Local</option></select>'
            '<table class="display"><tbody>'
            + "".join(rows) + nav + "</tbody></table></body></html>")


# --- the live fixture ----------------------------------------------------------------

def test_the_real_page_yields_its_four_firms_and_not_the_paginator():
    """51 rows pass a cell-count filter on a real page and 50 are firms; the paginator
    renders nine cells of its own."""
    firms = read_rows(_en())
    assert len(firms) == 4, [f.short_name for f in firms]


def test_the_commented_out_identifier_is_recovered():
    """`<!-- <td>0000</td> -->` — an HTML parser that strips comments loses the key."""
    assert "0000" in [f.short_name for f in read_rows(_en())]


def test_the_short_name_is_a_name_and_not_always_a_number():
    """Measured in the fixture: `ZYPHARSPH` beside `0000` and `00064048`. Nothing here
    may parse it as an integer or strip its leading zeros."""
    names = [f.short_name for f in read_rows(_en())]
    assert "ZYPHARSPH" in names
    assert "0000" in names, "and a zero-padded one must survive intact too"


def test_a_missing_cr_number_reads_as_absent_not_as_empty_text():
    firm = next(f for f in read_rows(_en()) if f.short_name == "ZYPHARSPH")
    assert firm.cr_number is None


def test_a_missing_expiry_reads_as_absent():
    firm = next(f for f in read_rows(_en()) if f.short_name == "00004174")
    assert firm.expiry_raw is None


def test_the_address_is_arabic_in_the_english_view():
    """So R-12's base column stays NULL for it and the `_ar` column carries the value."""
    firm = next(f for f in read_rows(_en()) if f.short_name == "0000")
    assert firm.address and re.search(r"[؀-ۿ]", firm.address)


def test_the_category_cell_is_kept_exactly_as_printed():
    firm = next(f for f in read_rows(_en()) if f.short_name == "00169963")
    assert firm.category_raw.startswith("Information Technology Services")


def test_the_paginator_publishes_the_register_total():
    assert read_last_page(_en()) == 471


def test_the_page_size_is_the_measured_fifty():
    assert ROWS_PER_PAGE == 50


# --- the published vocabularies ------------------------------------------------------

def test_the_category_vocabulary_is_read_from_the_page():
    cats = read_categories(_en())
    assert len(cats) == 12, sorted(cats)
    assert cats["Z1"] == "Construction and Maintenance"
    assert cats["Z4"] == (
        "Electromechanical and Telecommunications Contracting and Maintenance"), (
        "the select truncates in a narrow render; the full string is what the cell "
        "must be matched against")
    assert "-1" not in cats, "the --Select-- placeholder is not a category"


def test_the_legacy_scheme_is_in_the_vocabulary_and_marked_by_the_site():
    cats = read_categories(_en())
    old = [name for name in cats.values() if name.endswith("(Old)")]
    assert len(old) == 4, old


def test_the_arabic_view_publishes_the_same_codes():
    assert set(read_categories(_en())) == set(read_categories(_ar()))


def test_the_company_type_codes_have_holes_and_nothing_may_assume_otherwise():
    types = read_company_types(_en())
    assert types["0"] == "Local" and types["7"] == "Freelancer"
    assert "4" not in types and "5" not in types


def test_the_subcategory_xml_pairs_by_position():
    pairs = read_subcategories(_xml())
    assert len(pairs) == 5
    assert pairs[0] == ("101", "Building Construction")
    assert any("INACTIVATED" in name for _, name in pairs), (
        "the site marks a retired subcategory in the name itself")


def test_a_subcategory_response_whose_halves_differ_in_length_raises():
    bad = ("<subCategory><subCategoryValue>1</subCategoryValue>"
           "<subCategoryValue>2</subCategoryValue>"
           "<subCategoryName>One</subCategoryName></subCategory>")
    with pytest.raises(RegisterShapeError, match="paired by position"):
        read_subcategories(bad)


# --- decomposing the category cell ---------------------------------------------------

def test_a_single_category_cell_decomposes_to_one_name():
    vocab = read_categories(_en())
    split = decompose_categories("Services", vocab)
    assert split == CategorySplit(names=("Services",), remainder="")


def test_the_multi_category_cell_in_the_fixture_decomposes_with_no_remainder():
    vocab = read_categories(_en())
    firm = next(f for f in read_rows(_en()) if f.short_name == "00169963")
    split = decompose_categories(firm.category_raw, vocab)
    assert split.remainder == ""
    assert len(split.names) > 1, split


def test_every_category_cell_in_the_fixture_decomposes_with_no_remainder():
    """The measured property: 102 of 102 on the sample, zero remainder."""
    vocab = read_categories(_en())
    leftovers = {f.short_name: decompose_categories(f.category_raw, vocab).remainder
                 for f in read_rows(_en())}
    assert not any(leftovers.values()), leftovers


def test_longest_first_matters_because_one_name_is_a_prefix_of_another():
    """`Supply` is a prefix of `Supply and Services (Old)`. Shortest-first would eat the
    short one out of the long one and report a remainder that is only a greedy bug."""
    vocab = {"Z8": "Supply", "I1": "Supply and Services (Old)"}
    assert decompose_categories("Supply and Services (Old)", vocab).names == (
        "Supply and Services (Old)",)
    assert decompose_categories("Supply", vocab).names == ("Supply",)


def test_two_concatenated_names_with_no_separator_are_both_found():
    vocab = {"Z6": "Services", "Z8": "Supply"}
    split = decompose_categories("Services Supply", vocab)
    assert split.names == ("Services", "Supply") and split.remainder == ""


def test_a_name_the_vocabulary_does_not_have_is_reported_not_dropped():
    vocab = {"Z6": "Services"}
    split = decompose_categories("Services Something Else Entirely", vocab)
    assert split.names == ("Services",)
    assert split.remainder == "Something Else Entirely"


def test_a_blank_cell_decomposes_to_nothing_without_raising():
    assert decompose_categories("", {"Z6": "Services"}) == CategorySplit((), "")


def test_the_codes_are_what_a_stored_row_joins_on_not_the_names():
    """The name is whatever language was requested; the code is the same in both."""
    vocab = read_categories(_en())
    split = decompose_categories("Services Supply", vocab)
    assert codes_for(split, vocab) == ("Z6", "Z8")


def test_the_codes_keep_the_order_the_cell_printed():
    vocab = {"Z6": "Services", "Z8": "Supply"}
    split = decompose_categories("Supply Services", vocab)
    assert codes_for(split, vocab) == ("Z8", "Z6")


# --- the bilingual join --------------------------------------------------------------

def test_the_two_views_pair_on_the_cr_number():
    english = tuple(f for f in read_rows(_en()) if f.cr_number)
    arabic = read_rows(_ar())
    pairs = join_languages(english, arabic)
    assert len(pairs) == len(arabic) == 3


def test_the_pair_carries_english_on_one_side_and_arabic_on_the_other():
    english = tuple(f for f in read_rows(_en()) if f.cr_number)
    pairs = join_languages(english, read_rows(_ar()))
    en, ar = next(p for p in pairs if p[0].short_name == "0000")
    assert en.cr_number == ar.cr_number
    assert en.name == "AL REEF LINE UNITED TRADE CO LLC"
    assert re.search(r"[؀-ۿ]", ar.name)
    assert en.category_raw == "Services" and ar.category_raw == "الخدمات"


def test_the_join_is_on_the_number_and_not_on_position():
    """The real orders agree, so the fixture alone cannot catch a positional join. The
    Arabic side is reversed here on purpose: `docs/GULF-EGYPT-SOURCES.md:338` says never
    to pair by row position, and an order that happens to agree is not a contract."""
    english = tuple(f for f in read_rows(_en()) if f.cr_number)
    arabic = tuple(reversed(read_rows(_ar())))
    pairs = join_languages(english, arabic)
    for en, ar in pairs:
        assert en.cr_number == ar.cr_number
    assert [en.short_name for en, _ in pairs] == [f.short_name for f in english]


def test_a_firm_with_no_cr_number_cannot_be_paired_and_says_so():
    """It is 1 of 102 measured, and it is news rather than a row to skip."""
    with pytest.raises(RegisterShapeError, match="no counterpart"):
        join_languages(read_rows(_en()), read_rows(_ar()))


def test_the_unpairable_firm_is_named_in_the_refusal():
    with pytest.raises(RegisterShapeError, match="ZYPHARSPH"):
        join_languages(read_rows(_en()), read_rows(_ar()))


# --- the urls ------------------------------------------------------------------------

def test_the_register_url_pages_by_a_get_parameter():
    url = register_url(2)
    assert url.startswith(BASE_URL) and "pageNo=2" in url
    assert "CTRL_STRDIRECTION=LTR" in url and "eventFlag=RegVendorPublic" in url


def test_the_register_url_switches_language_by_the_same_parameter_the_site_uses():
    assert "CTRL_STRDIRECTION=RTL" in register_url(1, direction=RTL)


@pytest.mark.parametrize("page", [0, -1])
def test_the_register_url_refuses_a_page_below_one(page):
    with pytest.raises(ValueError, match="at least 1"):
        register_url(page)


def test_the_register_url_refuses_an_unknown_direction():
    with pytest.raises(ValueError, match="must be one of"):
        register_url(1, direction="RTL2")


def test_only_the_two_directions_the_site_has_are_allowed():
    assert DIRECTIONS == ("LTR", "RTL")


def test_the_subcategory_url_names_the_category_and_the_language():
    url = subcategory_url("Z1", direction=RTL)
    assert "category=Z1" in url and "eventFlag=getSubCategory" in url
    assert "CTRL_STRDIRECTION=RTL" in url


def test_the_subcategory_url_refuses_an_empty_code():
    with pytest.raises(ValueError, match="must not be empty"):
        subcategory_url("")


# --- every way the page's shape can break -------------------------------------------

def test_a_row_with_no_comment_raises_because_the_key_lives_in_one():
    with pytest.raises(RegisterShapeError, match="0 comment"):
        read_rows(_page([_row(comment=False)]))


def test_a_row_with_two_comments_raises():
    row = _row().replace("<td>A FIRM LLC</td>", "<!-- noise --><td>A FIRM LLC</td>")
    with pytest.raises(RegisterShapeError, match="2 comment"):
        read_rows(_page([row]))


def test_a_comment_holding_more_than_one_cell_raises():
    row = _row().replace("<!-- <td>00001234</td> -->",
                         "<!-- <td>00001234</td><td>extra</td> -->")
    with pytest.raises(RegisterShapeError, match="exactly one cell"):
        read_rows(_page([row]))


def test_a_row_with_the_wrong_number_of_cells_raises():
    row = _row().replace("<td>99000000</td>", "")
    with pytest.raises(RegisterShapeError, match="not the 11"):
        read_rows(_page([row]))


def test_a_key_that_disagrees_with_the_rows_own_activities_argument_raises():
    """Two independent copies of the record key; a disagreement means one of them has
    stopped being it."""
    with pytest.raises(RegisterShapeError, match="disagree beyond case"):
        read_rows(_page([_row(short="00001234", echo="00009999")]))


def test_the_two_copies_of_the_key_may_differ_in_case_and_that_is_not_a_failure():
    """Measured over 152 real rows: identical on 150, case-only on 2, otherwise never.
    The call lower-cases an alphabetic key -- `ZYPHARSPH` against `zypharsph`."""
    firms = read_rows(_page([_row(short="ZYPHARSPH", echo="zypharsph")]))
    assert firms[0].short_name == "ZYPHARSPH", "the printed form is what is stored"


def test_an_agreeing_key_is_accepted():
    firms = read_rows(_page([_row(short="00001234", echo="00001234")]))
    assert firms[0].short_name == "00001234"


def test_a_row_with_no_short_name_raises():
    with pytest.raises(RegisterShapeError, match="no Company Short Name"):
        read_rows(_page([_row(short="")]))


def test_a_row_with_no_company_name_raises():
    with pytest.raises(RegisterShapeError, match="no company name"):
        read_rows(_page([_row(name="")]))


def test_a_page_with_no_category_select_raises():
    page = _page([_row()]).replace('<select name="category">', "<select name='other'>")
    with pytest.raises(RegisterShapeError, match="no category select"):
        read_categories(page)


def test_a_category_select_holding_only_its_placeholder_raises():
    page = ('<select name="category"><option value="-1">--Select--</option>'
            "</select>")
    with pytest.raises(RegisterShapeError, match="no options besides"):
        read_categories(page)


def test_a_page_with_no_vendtype_select_raises():
    with pytest.raises(RegisterShapeError, match="no vendType select"):
        read_company_types("<html></html>")


def test_a_page_with_no_paginator_raises():
    with pytest.raises(RegisterShapeError, match="no Pagination_table"):
        read_last_page("<html><body>no nav here</body></html>")


def test_a_paginator_publishing_no_total_at_all_raises():
    """All three forms gone. S No. cannot stand in for it."""
    page = _page([_row()])
    page = page.replace("&nbsp;of 3&nbsp;", "&nbsp;&nbsp;")
    page = page.replace("ShowPage(3)", "doNothing()")
    page = page.replace("name='hidMax' value='3'", "name='other' value='3'")
    with pytest.raises(RegisterShapeError, match="no total in any of its three forms"):
        read_last_page(page)


def test_one_missing_form_is_tolerated_when_the_others_agree():
    """Deliberate: the guard is disagreement, not absence."""
    page = _page([_row()]).replace("&nbsp;of 3&nbsp;", "&nbsp;&nbsp;")
    assert read_last_page(page) == 3


def test_the_hidden_hidmax_field_alone_is_enough():
    page = _page([_row()])
    page = page.replace("ShowPage(3)", "doNothing()").replace("&nbsp;of 3&nbsp;", "")
    assert read_last_page(page) == 3


def test_hidmax_disagreeing_with_the_last_link_raises():
    """The site's own validation source against its own navigation."""
    page = _page([_row()]).replace("name='hidMax' value='3'", "name='hidMax' value='9'")
    with pytest.raises(RegisterShapeError, match="disagree"):
        read_last_page(page)


def test_the_real_paginator_agrees_three_ways():
    """hidMax=471, ShowPage(471) and the printed 'of 471' — and the printed one is split
    across two table cells, so it is read from the stripped text and not through tags."""
    assert read_last_page(_en()) == 471


def test_a_paginator_whose_two_readings_disagree_raises():
    """The printed total and the Last link are read independently on purpose."""
    page = _page([_row()]).replace("ShowPage(3)", "ShowPage(9)")
    with pytest.raises(RegisterShapeError, match="must agree"):
        read_last_page(page)


def test_the_two_agreeing_readings_are_accepted():
    assert read_last_page(_page([_row()], pages=7)) == 7
