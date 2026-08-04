"""One column order, read by every surface.

The owner drags a column in Choose Columns. The panel says it saved. The page
reloads. The table is byte-for-byte what it was.

That was not a rendering bug. The grid took its order from the literal
BROWSE_COLUMNS list and had never read dataset_field at all — `display_order`
occurred zero times in reports.py and zero times in grid.js — while the
Choose-Columns panel and the Current-View export both ordered BY display_order.
So the same warehouse answered "what order are my columns in" three ways, and
they disagreed at position 0: MADAR opened product_name on the grid and
product_name_ar in the panel, with price 18th against 13th.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from scrapex import db as dbmod, fields, reports
from scrapex.vocab import BLOCK_ORDER, Block


@pytest.fixture()
def conn():
    path = pathlib.Path(tempfile.mkdtemp()) / "order.db"
    connection = dbmod.connect(path)
    dbmod.migrate(connection)
    return connection


def test_the_agreed_order_puts_the_offer_straight_after_the_identity():
    """«الهوية ثم العرض ثم التصنيف». Before this, the main table opened with
    twenty-seven filing columns and reached price at index 32."""
    order = [key for key, _ in reports.browse_columns()]

    assert order.index("price") < order.index("category"), (
        "the price is still filed behind the classification")
    assert order.index("price") <= 8, (
        f"price sits at index {order.index('price')}; the agreement puts the "
        "offer directly after the identity")
    # And identity really is first — the name, not a category.
    assert order[0] == "product_name"


def test_every_column_has_a_block_and_the_blocks_run_in_the_agreed_order():
    """A column with no block would sort by accident. The membership is
    asserted rather than assumed, because the mapping is by rule and a rule
    that misses a key fails silently."""
    keys = [key for key, _ in reports.BROWSE_COLUMNS]

    assert set(reports.COLUMN_BLOCK) == set(keys), (
        "some column has no block: "
        f"{sorted(set(keys) - set(reports.COLUMN_BLOCK))}")

    blocks = [reports.COLUMN_BLOCK[key] for key, _ in reports.browse_columns()]
    positions = [BLOCK_ORDER.index(block) for block in blocks]
    assert positions == sorted(positions), (
        "the blocks are interleaved; browse_columns is not sorting by block")


def test_the_category_levels_still_come_from_the_generator():
    """PR #63 was sent back for re-typing twenty tuples by hand and orphaning
    _level_columns(). reports.py promises that raising the ceiling is one line,
    and this asserts the promise is true rather than written."""
    before = [key for key, _ in reports.browse_columns() if key.startswith("category_l")]

    original = reports.CATEGORY_LEVELS
    try:
        reports.CATEGORY_LEVELS = original + 2
        rebuilt = reports._level_columns()
    finally:
        reports.CATEGORY_LEVELS = original

    assert len(rebuilt) == (original + 2) * 2, (
        "raising CATEGORY_LEVELS did not produce more levels — the generator "
        "is no longer what builds them")
    assert len(before) == original * 2 + 2      # +2 for category_leaf and its _ar


def test_an_unarranged_source_shows_the_agreed_order(conn):
    """The default is ours to improve. Nobody has touched this source, so the
    agreement decides."""
    keys = ["category_l1", "price", "product_name", "brand", "sku"]

    assert not fields.arranged(conn, "NEW")
    assert fields.column_order(conn, "NEW", keys) == [
        "product_name", "sku", "price", "brand", "category_l1"]


def test_an_arrangement_the_owner_made_wins_and_is_not_blended(conn):
    """His arrangement is his. A default we may replace and an arrangement we
    may not are different things, and the code must be able to tell them
    apart — which is the entire reason 0059 exists."""
    keys = ["category_l1", "price", "product_name", "brand", "sku"]
    fields.ensure_fields(conn, "MINE", keys)
    fields.reorder(conn, "MINE", ["brand", "price"])

    assert fields.arranged(conn, "MINE"), (
        "dragging a column did not stamp the source, so no surface can tell "
        "his order from ours")
    shown = fields.column_order(conn, "MINE", keys)
    assert shown[:2] == ["brand", "price"], (
        "the agreed order overrode what he arranged")


def test_resetting_the_view_hands_the_order_back(conn):
    """Reset means reset. If arranged_at survived it, the source would keep
    claiming an arrangement that no longer exists and never see an improved
    default again."""
    keys = ["category_l1", "price", "product_name"]
    fields.ensure_fields(conn, "MINE", keys)
    fields.reorder(conn, "MINE", ["category_l1"])
    assert fields.arranged(conn, "MINE")

    fields.reset_view(conn, "MINE")

    assert not fields.arranged(conn, "MINE")
    assert fields.column_order(conn, "MINE", keys)[0] == "product_name"


def test_a_column_the_agreement_has_never_heard_of_is_not_dropped(conn):
    """A source-named extra, or a column added tomorrow. Ranking is not
    membership: an unranked key keeps its given position and follows the ranked
    ones, because losing a column to fix an order would be the worse bug."""
    keys = ["price", "something_new", "product_name", "another_new"]

    shown = fields.column_order(conn, "X", keys)

    assert set(shown) == set(keys), "a column was lost to the ordering"
    assert shown.index("something_new") < shown.index("another_new"), (
        "the unranked columns lost their relative order")
    assert shown.index("price") < shown.index("something_new")


def test_the_grid_and_the_chooser_read_the_same_function(conn):
    """The bug in one sentence: they did not. This asserts the shared reader is
    what reports.table_payload calls, so the two cannot drift again without
    someone deleting this line."""
    source = pathlib.Path(reports.__file__).read_text(encoding="utf-8")
    body = source[source.index('"columns": ['):source.index('"rows": shaped')]

    assert "fields.column_order(" in body, (
        "table_payload is ordering columns itself again; the chooser writes an "
        "order the grid will ignore, which is exactly what the owner reported")
    assert "for key, label in BROWSE_COLUMNS" not in body, (
        "the literal list is back in charge of the grid's order")
