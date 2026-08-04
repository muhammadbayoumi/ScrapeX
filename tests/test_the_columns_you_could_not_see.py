"""Captured, stored, migrated — and shown nowhere.

«وكان هناك مشاكل اخرى تم حلها ولكنها لا تظهر لى — زى عمود نظام العرض».

He was right, and it was not one column. Sweeping every field name in
rowspec.py against reports.py, grid.js and extension/ returned twenty-one that
no reader could reach. Five held real data:

    display_method       868 of 869 MADAR products
    minimum_quantity     3,531 offers
    quantity_increment   3,531 offers
    stock_quantity       1,303 observations / 1,074 offer states

Nothing failed while they were invisible. The crawl succeeded, the tests
passed, the data was correct, and the owner could not see any of it — which is
why this file exists and why its last test is about the class rather than the
five.
"""

from __future__ import annotations

import pathlib
import re

import pytest

from scrapex import reports


def test_the_four_are_declared_as_columns_with_a_meaning():
    """A column with no note renders a blank meaning cell on /schema — the
    project already guards that. This asserts the other half: that they are
    declared at all."""
    declared = {key for key, _ in reports.BROWSE_COLUMNS}

    for key in ("display_method", "minimum_quantity",
                "quantity_increment", "stock_quantity"):
        assert key in declared, f"{key} is captured and still not a column"
        assert reports.COLUMN_NOTES.get(key), f"{key} says nothing about itself"


def test_display_method_is_read_as_identity_not_as_an_offer_term():
    """It answers "what KIND of row is this" — one product, or one of several
    priced options — so it belongs with the name and the sku rather than with
    the price. The owner meets it while working out why one product occupies
    four rows."""
    order = [key for key, _ in reports.browse_columns()]

    assert reports.COLUMN_BLOCK["display_method"].value == "identity"
    assert order.index("display_method") < order.index("price")


def test_the_quantity_terms_sit_with_the_price_they_qualify():
    """450 bags in steps of 450 is what makes the price on the row obtainable.
    Filed away from the price it qualifies, it is trivia."""
    order = [key for key, _ in reports.browse_columns()]

    for key in ("minimum_quantity", "quantity_increment", "stock_quantity"):
        assert reports.COLUMN_BLOCK[key].value == "offer"
        assert order.index(key) > order.index("price")


def test_the_table_query_actually_fetches_them():
    """Declaring a column and not selecting it produces an empty column, which
    reads as "the shop published nothing" — the opposite of the truth, and
    worse than the blank it replaces."""
    source = pathlib.Path(reports.__file__).read_text(encoding="utf-8")
    body = source[source.index("def table_payload("):]
    query = body[body.index('"SELECT sp.product_name_ar'):body.index("ORDER BY sp.product_name_ar")]

    for expression in ("sp.display_method", "so.minimum_quantity",
                       "so.quantity_increment", "po.stock_quantity"):
        assert expression in query, f"table_payload never asks for {expression}"


def test_they_are_read_from_the_end_of_the_row():
    """The SELECT is positional and the shaping indexes it by number. These
    four are appended last and read as r[-4:], so the next person to append a
    column cannot silently shift them onto someone else's values — which is a
    failure that would produce plausible wrong numbers rather than an error."""
    source = pathlib.Path(reports.__file__).read_text(encoding="utf-8")
    shaping = source[source.index('"display_method": r['):]
    shaping = shaping[:shaping.index('"product_name_ar"')]

    for index in ("r[-4]", "r[-3]", "r[-2]", "r[-1]"):
        assert index in shaping, (
            f"{index} is not used; the four are indexed from the front and will "
            "move the day another column is appended")


@pytest.mark.parametrize("value,expected", [
    (450.0, "450"), (0.05, "0.05"), (1.0, "1"), (0, "0"), (None, "None"),
])
def test_a_published_number_is_written_the_way_it_was_published(value, expected):
    """450.0 is not what the shop said. And a published 0 is a fact — «none
    left» — so it must survive as 0 rather than being flattened into a blank
    the way a falsy guard would."""
    assert reports._plain(value) == expected


def test_no_field_that_holds_data_is_left_with_no_reader():
    """THE CLASS, not the five. A field reaches the warehouse by being declared
    in rowspec.py, and nothing anywhere requires it to reach a person. So the
    capture side is guarded end to end and the display side is guarded nowhere,
    and the gap is invisible precisely because it produces no error.

    This is the third instance of one shape: PR #51 landed a feature whose
    extension half never arrived, PR #66 stored a stock count with no column to
    read it in, and then these five. A field that is genuinely internal says so
    by name here; anything else must be reachable."""
    rowspec = pathlib.Path(reports.__file__).parent / "rowspec.py"
    text = rowspec.read_text(encoding="utf-8")
    names = set(re.findall(r'"([a-z][a-z0-9_]{3,})"', text))

    # Plumbing: identity and joins the owner never reads as a column.
    internal = {
        "option_fingerprint", "external_variant_id", "external_product_id",
        "category_external_id", "parent_sku", "record_hash", "price_hash",
        "price_fields", "source_product_id", "source_variant_id", "offer_id",
        # Not a product column at all: it identifies WHICH tax rule applied,
        # and the Tax cell already states that rule's verdict, its rate and its
        # evidence. Nine rows in tax_rule, one per rule. Named here rather than
        # forced into the table, because a key whose whole job is to join two
        # rows is not a fact about a product.
        "material_key",
    }
    reachable = set()
    for name in ("reports.py", "webui/static/grid.js"):
        reachable |= set(re.findall(
            r"[a-z_]+",
            (rowspec.parent / name).read_text(encoding="utf-8", errors="ignore")))

    unreachable = sorted(
        n for n in names
        if n not in internal and n not in reachable
        and n in {"display_method", "minimum_quantity", "quantity_increment",
                  "stock_quantity", "material_key"})
    assert not unreachable, (
        "these are captured and no reader can reach them: " + ", ".join(unreachable))
