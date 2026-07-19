"""Spec 22: presentation changes are never destructive schema changes."""
from __future__ import annotations

import sqlite3

import pytest

from scrapex import db as dbmod
from scrapex.fields import (
    CURRENT_VIEW, ORIGINAL_SCHEMA, apply_schema, delete_view, ensure_fields, list_fields,
    list_views, reorder, reset_view, save_view, set_display_name, set_visibility,
    visible_columns,
)

COLUMNS = ["product", "sku", "price", "currency"]


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    ensure_fields(c, "SHOP", COLUMNS)
    yield c
    c.close()


# ---- registration ------------------------------------------------------------

def test_fields_register_in_discovery_order(conn):
    assert [f["field_key"] for f in list_fields(conn, "SHOP")] == COLUMNS
    assert all(f["display_name"] is None and not f["is_hidden"] for f in list_fields(conn, "SHOP"))


def test_ensure_fields_is_additive_and_leaves_existing_alone(conn):
    set_display_name(conn, "SHOP", "price", "Unit price")
    set_visibility(conn, "SHOP", "sku", True)

    ensure_fields(conn, "SHOP", COLUMNS + ["stock"])   # a connector grew a column
    fields = {f["field_key"]: f for f in list_fields(conn, "SHOP")}
    assert fields["price"]["display_name"] == "Unit price"   # untouched
    assert fields["sku"]["is_hidden"] is True                # untouched
    assert fields["stock"]["display_order"] == 4             # appended at the end


# ---- renaming never touches identity ----------------------------------------

def test_rename_changes_only_the_label(conn):
    assert set_display_name(conn, "SHOP", "product", "Product name") is True
    field = next(f for f in list_fields(conn, "SHOP") if f["field_key"] == "product")
    assert field["field_key"] == "product"          # immutable identity
    assert field["original_name"] == "product"      # preserved forever
    assert field["label"] == "Product name"


def test_rename_can_be_cleared_back_to_original(conn):
    set_display_name(conn, "SHOP", "product", "Product name")
    set_display_name(conn, "SHOP", "product", "")
    field = next(f for f in list_fields(conn, "SHOP") if f["field_key"] == "product")
    assert field["display_name"] is None and field["label"] == "product"


def test_renaming_an_unknown_field_reports_failure(conn):
    assert set_display_name(conn, "SHOP", "ghost", "X") is False


# ---- hiding is NOT deleting --------------------------------------------------

def test_hiding_removes_from_view_but_keeps_the_field(conn):
    set_visibility(conn, "SHOP", "sku", True)
    assert "sku" not in visible_columns(conn, "SHOP")
    # still present in the manage surface, with all its metadata
    assert "sku" in [f["field_key"] for f in list_fields(conn, "SHOP")]


def test_hidden_field_keeps_receiving_data_and_can_come_back(conn):
    set_visibility(conn, "SHOP", "sku", True)
    header = COLUMNS
    rows = [["Lamp", "SKU-1", 100, "EGP"]]
    # exporting the CURRENT VIEW drops the column...
    view_header, view_rows = apply_schema(conn, "SHOP", header, rows, CURRENT_VIEW)
    assert "sku" not in view_header and view_rows == [["Lamp", 100, "EGP"]]
    # ...but the ORIGINAL SCHEMA still has every value: nothing was lost
    orig_header, orig_rows = apply_schema(conn, "SHOP", header, rows, ORIGINAL_SCHEMA)
    assert orig_header == COLUMNS and orig_rows == rows

    set_visibility(conn, "SHOP", "sku", False)      # un-hide
    back_header, back_rows = apply_schema(conn, "SHOP", header, rows, CURRENT_VIEW)
    assert "sku" in back_header and back_rows == rows


def test_there_is_no_way_to_delete_a_field():
    import scrapex.fields as fields_module
    assert not [n for n in dir(fields_module) if "delete_field" in n]


# ---- ordering ----------------------------------------------------------------

def test_reorder_accepts_a_partial_list(conn):
    reorder(conn, "SHOP", ["price", "product"])
    assert [f["field_key"] for f in list_fields(conn, "SHOP")] == \
        ["price", "product", "sku", "currency"]


def test_reorder_is_stable_when_repeated(conn):
    reorder(conn, "SHOP", ["price", "product"])
    reorder(conn, "SHOP", ["price", "product"])
    assert [f["field_key"] for f in list_fields(conn, "SHOP")] == \
        ["price", "product", "sku", "currency"]


def test_reorder_ignores_unknown_keys(conn):
    reorder(conn, "SHOP", ["ghost", "price"])
    assert [f["field_key"] for f in list_fields(conn, "SHOP")][0] == "price"


# ---- reset -------------------------------------------------------------------

def test_reset_restores_names_visibility_and_order(conn):
    set_display_name(conn, "SHOP", "price", "Unit price")
    set_visibility(conn, "SHOP", "sku", True)
    reorder(conn, "SHOP", ["currency", "price"])

    reset_view(conn, "SHOP")
    fields = list_fields(conn, "SHOP")
    assert [f["field_key"] for f in fields] == COLUMNS
    assert all(f["display_name"] is None and not f["is_hidden"] for f in fields)


# ---- saved views -------------------------------------------------------------

def test_saved_views_round_trip_and_overwrite(conn):
    save_view(conn, "SHOP", "Prices only", {"columns": ["product", "price"]})
    save_view(conn, "SHOP", "Prices only", {"columns": ["product", "price", "currency"]})
    views = list_views(conn, "SHOP")
    assert len(views) == 1                      # same name overwrites, never duplicates
    assert views[0]["config"]["columns"] == ["product", "price", "currency"]


def test_views_are_deletable_because_they_hold_no_data(conn):
    view_id = save_view(conn, "SHOP", "Temp", {"columns": ["product"]})
    assert delete_view(conn, view_id) is True
    assert delete_view(conn, view_id) is False
    assert list_views(conn, "SHOP") == []


def test_views_are_scoped_per_source(conn):
    save_view(conn, "SHOP", "V", {"columns": ["product"]})
    ensure_fields(conn, "OTHER", COLUMNS)
    save_view(conn, "OTHER", "V", {"columns": ["price"]})
    assert len(list_views(conn, "SHOP")) == 1 and len(list_views(conn, "OTHER")) == 1


# ---- export projection -------------------------------------------------------

def test_current_view_uses_display_names(conn):
    set_display_name(conn, "SHOP", "product", "Product name")
    header, _ = apply_schema(conn, "SHOP", COLUMNS, [["a", "b", 1, "EGP"]], CURRENT_VIEW)
    assert header[0] == "Product name"


def test_original_schema_ignores_all_cosmetics(conn):
    set_display_name(conn, "SHOP", "product", "Product name")
    set_visibility(conn, "SHOP", "sku", True)
    reorder(conn, "SHOP", ["currency"])
    header, rows = apply_schema(conn, "SHOP", COLUMNS, [["a", "b", 1, "EGP"]], ORIGINAL_SCHEMA)
    assert header == COLUMNS and rows == [["a", "b", 1, "EGP"]]


def test_apply_schema_registers_unseen_columns(conn):
    apply_schema(conn, "FRESH", ["x", "y"], [[1, 2]], CURRENT_VIEW)
    assert [f["field_key"] for f in list_fields(conn, "FRESH")] == ["x", "y"]


def test_hiding_every_column_yields_an_empty_view_not_all_of_them(conn):
    """Regression (MEDIUM): the fallback keyed off "none visible" instead of
    "none registered", so hiding everything published the ENTIRE table."""
    for column in COLUMNS:
        set_visibility(conn, "SHOP", column, True)
    assert visible_columns(conn, "SHOP", fallback=COLUMNS) == []
    header, rows = apply_schema(conn, "SHOP", COLUMNS, [["a", "b", 1, "EGP"]], CURRENT_VIEW)
    assert header == [] and rows == [[]]


def test_unregistered_source_still_falls_back(conn):
    assert visible_columns(conn, "NEVER_SEEN", fallback=COLUMNS) == COLUMNS
