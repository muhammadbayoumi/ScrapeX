"""worldbank-pink-sheet: the World Bank's monthly commodity prices (#1912).

The workbook fixture is the real file of 2026-10-02 with the sheets the connector does not
read removed, so the census below is the real census. The page is a window of the live one.
"""
from __future__ import annotations

import io
import sqlite3
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

import openpyxl
import pytest

from scrapex import db as dbmod
from scrapex.config import MANIFEST_FILE, ExtractSpec, SourceEntry, load_manifest
from scrapex.connectors.base import ScrapedTable
from scrapex.connectors.factory import _BUILDERS, supports_history
from scrapex.connectors.pinksheet import (
    _SERIES,
    HIDDEN_SOURCE,
    PinkSheetConnector,
    change_points,
    find_workbook_url,
    series_name,
)
from scrapex.ingest import ingest_payloads
from scrapex.rowspec import COMMODITY_PRICE, ENRICHMENT, RowBuilder, RowView
from scrapex.tax import resolve
from scrapex.vocab import ConnectorFamily, ExtractKind, ExtractScope, VatMode

FX = Path(__file__).parent / "fixtures"
WORKBOOK = (FX / "pinksheet_monthly_2026-10-02.xlsx").read_bytes()
PAGE = (FX / "pinksheet_page.html").read_text(encoding="utf-8")
LINK = ("https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/"
        "related/CMO-Historical-Data-Monthly.xlsx")
_SHORT: bytes | None = None


class _Resp:
    def __init__(self, text="", content=b""):
        self.text, self.content = text, content


class _Stub:
    """The two requests a check costs, and nothing else."""

    def __init__(self, page=PAGE, workbook=WORKBOOK):
        self.page, self.workbook, self.urls = page, workbook, []

    def get(self, url, **kwargs):
        self.urls.append(url)
        if url.endswith("/en/research/commodity-markets"):
            return _Resp(text=self.page)
        assert url == LINK, f"the connector went somewhere else: {url}"
        return _Resp(content=self.workbook)


def make_entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="WORLDBANK_PINK_SHEET", source_name="World Bank Pink Sheet",
        base_url="https://www.worldbank.org", family="worldbank-pink-sheet",
        cadence="weekly", authority="official", currency="USD", vat_mode="excl",
        extract=[ExtractSpec(kind=ExtractKind.COMMODITY_PRICE, scope=ExtractScope.TARGETED),
                 ExtractSpec(kind=ExtractKind.ENRICHMENT, scope=ExtractScope.TARGETED)],
    ))


def tables(*, history=False, stub=None):
    connector = PinkSheetConnector(stub or _Stub(), history=history)
    return list(connector.fetch(make_entry()))


def prices(table) -> list[dict]:
    view = RowView(COMMODITY_PRICE, table.header)
    return [view.as_dict(r) for r in table.rows]


def details(table) -> list[dict]:
    view = RowView(ENRICHMENT, table.header)
    return [view.as_dict(r) for r in table.rows]


def _shorter() -> openpyxl.Workbook:
    """The real workbook less 1960M04 to 2023M12: every shape, a thirtieth of the wait."""
    book = openpyxl.load_workbook(io.BytesIO(WORKBOOK))
    sheet = book["Monthly Prices"]
    first, last = row_of(sheet, "1960M04"), row_of(sheet, "2023M12")
    sheet.delete_rows(first, last - first + 1)
    return book


def edited(change) -> bytes:
    """The real workbook with one thing changed, as a later edition might change it."""
    global _SHORT
    if _SHORT is None:
        out = io.BytesIO()
        _shorter().save(out)
        _SHORT = out.getvalue()
    book = openpyxl.load_workbook(io.BytesIO(_SHORT))
    change(book)
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def column_of(sheet, name: str) -> int:
    for cell in sheet[5]:
        if cell.value is not None and series_name(str(cell.value)) == name:
            return cell.column
    raise AssertionError(name)


def row_of(sheet, period: str) -> int:
    for cell in sheet["A"]:
        if cell.value == period:
            return cell.row
    raise AssertionError(period)


@pytest.fixture(scope="module")
def weekly():
    return tables()


@pytest.fixture(scope="module")
def full():
    return tables(history=True)


# ---- the landing page --------------------------------------------------------

def test_the_workbook_address_is_read_from_the_page():
    assert find_workbook_url(PAGE) == LINK


def test_a_page_that_stopped_linking_it_is_loud():
    with pytest.raises(ValueError, match="links 0"):
        find_workbook_url("<a href='x'>Monthly prices</a>")


def test_two_different_workbooks_on_the_page_are_loud_not_a_guess():
    other = LINK.replace("74e8be41", "aaaaaaaa")
    with pytest.raises(ValueError, match="links 2"):
        find_workbook_url(f'<a href="{LINK}"></a><a href="{other}"></a>')


def test_the_same_link_twice_is_one_workbook():
    assert find_workbook_url(f'<a href="{LINK}"></a><a href="{LINK}"></a>') == LINK


def test_a_link_to_another_host_is_never_followed():
    with pytest.raises(ValueError, match="links 0"):
        find_workbook_url('<a href="https://evil.example/en/CMO-Historical-Data-Monthly.xlsx"></a>')


def test_a_check_costs_two_requests():
    stub = _Stub()
    list(PinkSheetConnector(stub).fetch(make_entry()))
    assert len(stub.urls) == 2


# ---- the census, against the study's own counts --------------------------------

def test_every_priced_series_comes_through_and_the_index_does_not(full):
    rows = prices(full[0])
    assert {r["material_key"] for r in rows} == {v[0] for v in _SERIES.values()}
    assert len(_SERIES) == 70
    assert "NATURAL_GAS_INDEX" not in {r["material_key"] for r in rows}
    assert not any(r["unit"].startswith("2010") for r in rows)
    assert not any("Natural gas index" in w for w in full[0].warnings),         "the index is left out on purpose, so it is not a new series to review"


def test_history_is_change_points_then_every_month_of_the_window(full):
    rows = prices(full[0])
    published = [r for r in rows if r["provenance"] == "reported"
                 and r["official_source_name"] != HIDDEN_SOURCE]
    hidden = [r for r in rows if r["official_source_name"] == HIDDEN_SOURCE]
    # #1912 counted 40,787 change points with Rice Thai 25%'s run of zeros as one point; it
    # is refused here, so 40,786. His answer on #1919 adds the 38 months of the window that
    # equal the month before, and 2 of the hidden sheet's.
    assert len(published) == 40_786 + 38
    assert len(hidden) == 138 + 2


def test_before_the_window_history_keeps_only_change_points(full):
    """His rule where no edition revises a value: no two kept months in a row are equal."""
    series: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for r in prices(full[0]):
        if r["provenance"] == "reported" and r["as_of_date"] < "2025-10-01":
            series.setdefault((r["material_key"], r["official_source_name"]), []).append(
                (r["as_of_date"], r["price"]))
    assert len(series) == 70 + 2
    for key, points in series.items():
        points.sort()
        assert all(a[1] != b[1] for a, b in pairwise(points)), key


def test_a_normal_run_reads_a_year_and_not_the_whole_history(weekly, full):
    reported = [r for r in prices(weekly[0]) if r["provenance"] == "reported"]
    assert reported and min(r["as_of_date"] for r in reported) == "2025-10-01"
    assert len(reported) < 1_000 < len(prices(full[0]))


def test_a_normal_run_sends_every_month_of_the_window_the_flat_ones_too(weekly):
    """Phosphate rock held 152.5 from October 2025: each month is a row, not only the first."""
    reported = [r for r in prices(weekly[0]) if r["provenance"] == "reported"
                and r["official_source_name"] != HIDDEN_SOURCE]
    assert len(reported) == 802
    phosphate = {r["as_of_date"] for r in reported if r["material_key"] == "PHOSPHATE_ROCK"}
    assert {"2025-11-01", "2025-12-01", "2026-01-01"} <= phosphate
    # Barley's and Sorghum's whole window is the hidden sheet's, and 2 of its months are flat:
    # as change points this would be 18.
    hidden = [r for r in prices(weekly[0]) if r["official_source_name"] == HIDDEN_SOURCE]
    assert len(hidden) == 20


def test_the_newest_month_is_the_observed_price(weekly):
    rows = {r["material_key"]: r for r in prices(weekly[0]) if r["provenance"] == "observed"}
    assert rows["COPPER"]["price"] == "14474"
    assert rows["COPPER"]["source_date"] == "2026-09-01"
    assert rows["COPPER"]["as_of_date"] == ""


def test_a_late_series_is_still_current_and_a_dead_one_is_not(weekly):
    rows = {r["material_key"]: r for r in prices(weekly[0]) if r["provenance"] == "observed"}
    assert rows["TOBACCO_US"]["source_date"] == "2026-07-01"
    for dead in ("BARLEY", "SORGHUM", "SHRIMP"):
        assert dead not in rows, f"{dead} last published long ago and is not a current price"
    assert len(rows) == 67
    said = " ".join(weekly[0].warnings)
    assert "Barley: no current price, last published 2020M08" in said
    assert "Shrimps, Mexican: no current price, last published 2023M10" in said


# ---- what a number is ------------------------------------------------------------

def test_a_row_says_what_the_study_found(weekly):
    row = next(r for r in prices(weekly[0]) if r["material_key"] == "COPPER")
    assert row["currency"] == "USD" and row["unit"] == "tonne"
    assert row["country_code_alpha2"] == "*"
    assert row["consumer_segment"] == "wholesale"
    assert row["tax_included"] == "0"
    assert row["price_basis"] == "original" and row["original_price"] == ""
    assert row["official_source_link"] == LINK
    assert "Bloomberg" in row["official_source_name"]


def test_plywood_is_stated_in_dollars_with_the_cents_beside_it(weekly):
    row = next(r for r in prices(weekly[0])
               if r["material_key"] == "PLYWOOD" and r["provenance"] == "observed")
    assert row["price"] == "3.491" and row["original_price"] == "349.1"
    assert row["currency"] == "USD" and row["unit"] == "sheet"
    assert row["price_basis"] == "converted"


def test_iron_ore_is_per_dry_ton_and_the_workbook_word_survives(weekly):
    row = next(r for r in prices(weekly[0]) if r["material_key"] == "IRON_ORE")
    assert row["unit"] == "dmt"
    word = next(d for d in details(weekly[1])
                if d["external_product_id"] == "IRON_ORE" and d["attribute_code"] == "unit_as_published")
    assert word["raw_value"] == "($/dmtu)"


@pytest.mark.parametrize("key, unit", [
    ("CRUDE_OIL_BRENT", "bbl"), ("NATURAL_GAS_US", "mmbtu"), ("LOGS_CAMEROON", "m3"),
    ("GOLD", "troy oz"), ("COCOA", "kg"), ("ALUMINUM", "tonne"),
])
def test_every_kind_of_unit(weekly, key, unit):
    assert next(r for r in prices(weekly[0]) if r["material_key"] == key)["unit"] == unit


def test_a_flag_on_the_header_is_not_part_of_the_series():
    assert series_name("Coal, South African **") == "Coal, South African"
    assert series_name("Copper") == "Copper"


# ---- holes in the sheet ------------------------------------------------------------

def test_a_zero_and_an_excel_error_are_holes_and_are_said_out_loud(full):
    rice = {r["as_of_date"]: r["price"] for r in prices(full[0])
            if r["material_key"] == "RICE_THAI_25" and r["provenance"] == "reported"}
    for month in ("2008-03-01", "2008-04-01", "2008-05-01", "2008-06-01", "2008-02-01", "1988-08-01"):
        assert month not in rice
    assert all(Decimal(p) > 0 for p in rice.values())
    assert any("Rice, Thai 25%: 4 cell(s) of 0 and 4 Excel error(s)" in w for w in full[0].warnings)


def test_an_absent_cell_is_silent_because_it_is_ordinary(full):
    assert not any("DAP" in w for w in full[0].warnings), "DAP's '...' before 1967 is not news"
    dap = [r["as_of_date"] for r in prices(full[0])
           if r["material_key"] == "DAP" and r["provenance"] == "reported"]
    assert min(dap) == "1967-01-01"


def test_change_points_keep_the_first_and_each_move():
    values = {"a": Decimal(1), "b": Decimal(1), "c": Decimal(2), "e": Decimal(2), "f": Decimal(1)}
    assert list(change_points(values, ["a", "b", "c", "d", "e", "f"])) == [
        ("a", Decimal(1)), ("c", Decimal(2)), ("f", Decimal(1))]


def test_change_points_of_nothing_is_nothing():
    assert list(change_points({}, ["a"])) == []


# ---- the hidden sheet: his word, «تتبع اسعار طالما مذكورة» --------------------------

def test_the_hidden_grains_are_taken_and_marked(full):
    rows = [r for r in prices(full[0]) if r["official_source_name"] == HIDDEN_SOURCE]
    assert {r["material_key"] for r in rows} == {"BARLEY", "SORGHUM"}
    assert all(r["provenance"] == "reported" for r in rows)
    newest = max((r for r in rows if r["material_key"] == "BARLEY"), key=lambda r: r["as_of_date"])
    assert newest["as_of_date"] == "2026-07-01" and newest["price"] == "162.8"
    public = [r for r in prices(full[0]) if r["material_key"] == "BARLEY"
              and r["official_source_name"] != HIDDEN_SOURCE]
    assert max(r["as_of_date"] for r in public) < "2020-09-01"


def test_a_hidden_value_is_not_the_older_edition_of_a_published_one(full):
    """The sheet's `Value mismatch` rows hold what July was before it was revised."""
    lng = {r["as_of_date"]: r for r in prices(full[0]) if r["material_key"] == "LNG_JAPAN"}
    assert lng["2026-07-01"]["price"] == "13.85"
    assert lng["2026-07-01"]["official_source_name"] != HIDDEN_SOURCE


def test_the_older_edition_rows_are_not_even_considered(full):
    assert not any("hidden value(s) ignored" in w for w in full[0].warnings), \
        "only `Blank vs number` rows are candidates, and on the real file none has a public cell"


def test_the_real_sheet_holds_no_kind_the_reader_does_not_know(full):
    assert not any("does not know" in w or "holds no" in w for w in full[0].warnings)


def test_a_renamed_kind_in_the_hidden_sheet_is_said_not_silent():
    """It ended the hidden prices with the warnings identical to a normal run's (#1919)."""
    def rename(book):
        for row in book["Mismatch Details"].iter_rows(min_row=5):
            if row[6].value == "Blank vs number":
                row[6].value = "Blank vs Number"
    table = tables(history=True, stub=_Stub(workbook=edited(rename)))[0]
    assert not any(r["official_source_name"] == HIDDEN_SOURCE for r in prices(table))
    assert any("142 hidden row(s) of a kind this reader does not know ('Blank vs Number' x142)"
               in w for w in table.warnings)
    assert "the hidden sheet holds no 'Blank vs number' row: no hidden price this run" \
        in table.warnings


def test_a_hidden_sheet_with_only_older_editions_left_says_its_prices_stopped():
    def passed_over(book):
        for row in book["Mismatch Details"].iter_rows(min_row=5):
            if row[6].value == "Blank vs number":
                row[6].value = "Value mismatch"
    table = tables(history=True, stub=_Stub(workbook=edited(passed_over)))[0]
    assert "the hidden sheet holds no 'Blank vs number' row: no hidden price this run" \
        in table.warnings
    assert not any("does not know" in w for w in table.warnings)


def test_a_published_cell_beats_the_hidden_value_for_the_same_month():
    def publish_barley(book):
        sheet = book["Monthly Prices"]
        sheet.cell(row_of(sheet, "2026M07"), column_of(sheet, "Barley"), 999.5)
    table = tables(history=True, stub=_Stub(workbook=edited(publish_barley)))[0]
    july = [r for r in prices(table) if r["material_key"] == "BARLEY"
            and r["as_of_date"] == "2026-07-01"]
    assert [r["price"] for r in july] == ["999.5"]
    assert july[0]["official_source_name"] != HIDDEN_SOURCE
    assert any("hidden value(s) ignored" in w for w in table.warnings)


def test_when_the_hidden_sheet_goes_the_run_says_so_and_carries_on():
    def remove(book):
        del book["Mismatch Details"]
    table = tables(history=True, stub=_Stub(workbook=edited(remove)))[0]
    assert any("hidden sheet" in w and "gone" in w for w in table.warnings)
    assert not table.defects, "a QA sheet going away does not degrade the published prices"
    assert not any(r["official_source_name"] == HIDDEN_SOURCE for r in prices(table))
    assert "COPPER" in {r["material_key"] for r in prices(table)}


def test_a_hidden_sheet_with_other_columns_is_read_as_nothing_and_said():
    def rename(book):
        book["Mismatch Details"]["F4"] = "Something else"
    table = tables(history=True, stub=_Stub(workbook=edited(rename)))[0]
    assert any("changed its columns" in w for w in table.warnings)
    assert not any(r["official_source_name"] == HIDDEN_SOURCE for r in prices(table))


# ---- every parse asserts its shape ---------------------------------------------------

@pytest.mark.parametrize("sheet", ["Monthly Prices", "Description"])
def test_a_renamed_sheet_is_loud(sheet):
    def rename(book):
        book[sheet].title = "Something else"
    with pytest.raises(ValueError, match=sheet):
        tables(stub=_Stub(workbook=edited(rename)))


def test_a_sheet_that_stopped_saying_nominal_dollars_is_loud():
    def rewrite(book):
        book["Monthly Prices"]["A2"] = "monthly prices in real 2010 US dollars"
    with pytest.raises(ValueError, match="nominal US dollars"):
        tables(stub=_Stub(workbook=edited(rewrite)))


def test_a_first_column_with_no_months_is_loud():
    def rewrite(book):
        for cell in book["Monthly Prices"]["A"]:
            if cell.row > 6:
                cell.value = "2026-09"
    with pytest.raises(ValueError, match="YYYYMmm"):
        tables(stub=_Stub(workbook=edited(rewrite)))


def test_a_word_where_a_month_belongs_is_loud():
    def rewrite(book):
        sheet = book["Monthly Prices"]
        sheet.cell(row_of(sheet, "2025M01"), 1, "Notes")
    with pytest.raises(ValueError, match="where a month belongs"):
        tables(stub=_Stub(workbook=edited(rewrite)))


def test_months_out_of_order_are_loud():
    def rewrite(book):
        sheet = book["Monthly Prices"]
        sheet.cell(row_of(sheet, "2025M02"), 1, "1999M01")
    with pytest.raises(ValueError, match="out of order"):
        tables(stub=_Stub(workbook=edited(rewrite)))


def test_a_word_in_a_price_cell_is_loud_not_a_missing_month():
    def rewrite(book):
        sheet = book["Monthly Prices"]
        sheet.cell(row_of(sheet, "2025M01"), column_of(sheet, "Copper"), "discontinued")
    with pytest.raises(ValueError, match="no numeric content"):
        tables(stub=_Stub(workbook=edited(rewrite)))


def test_an_unknown_unit_is_loud():
    def rewrite(book):
        sheet = book["Monthly Prices"]
        sheet.cell(6, column_of(sheet, "Copper"), "(EUR/mt)")
    with pytest.raises(ValueError, match="price unit"):
        tables(stub=_Stub(workbook=edited(rewrite)))


def test_a_new_series_is_reported_and_not_guessed():
    def add(book):
        sheet = book["Monthly Prices"]
        sheet.cell(5, sheet.max_column + 1, "Cement, world")
    table = tables(stub=_Stub(workbook=edited(add)))[0]
    assert any("Cement, world" in w for w in table.warnings)
    assert not table.defects


def test_a_renamed_series_is_a_defect_on_the_run():
    def rename(book):
        sheet = book["Monthly Prices"]
        sheet.cell(5, column_of(sheet, "Copper"), "Copper, LME")
    table = tables(stub=_Stub(workbook=edited(rename)))[0]
    assert any("Copper" in d for d in table.defects)
    assert any("Copper, LME" in w for w in table.warnings)
    assert "COPPER" not in {r["material_key"] for r in prices(table)}


def test_a_series_twice_is_loud():
    def double(book):
        sheet = book["Monthly Prices"]
        sheet.cell(5, column_of(sheet, "Silver"), "Copper")
    with pytest.raises(ValueError, match="twice"):
        tables(stub=_Stub(workbook=edited(double)))


def test_a_workbook_that_lost_most_of_its_series_is_loud():
    def thin(book):
        sheet = book["Monthly Prices"]
        for cell in list(sheet[5])[1:]:
            if cell.column > 20:
                cell.value = None
    with pytest.raises(ValueError, match="known series"):
        tables(stub=_Stub(workbook=edited(thin)))


def test_a_body_far_past_the_usual_size_is_refused_before_it_is_opened():
    with pytest.raises(ValueError, match="bytes"):
        tables(stub=_Stub(workbook=b"x" * 25_000_001))


def test_a_body_that_is_not_a_workbook_is_loud():
    with pytest.raises(Exception, match="(?i)zip"):
        tables(stub=_Stub(workbook=b"<html>a login page</html>"))


def test_a_description_row_gone_is_said_and_the_prices_stay():
    def remove(book):
        sheet = book["Description"]
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str) and cell.value.startswith("Copper (LME)"):
                    cell.value = None
    table, facts = tables(stub=_Stub(workbook=edited(remove)))
    assert any("no Description row for 'Copper'" in w for w in table.warnings)
    assert "COPPER" in {r["material_key"] for r in prices(table)}
    assert "market_terms" not in {d["attribute_code"] for d in details_of(facts, "COPPER")}


def details_of(table, key: str) -> list[dict]:
    return [d for d in details(table) if d["external_product_id"] == key]


# ---- the attributes his answers ask for ------------------------------------------------

def test_every_series_says_it_is_a_monthly_average_and_where_it_trades(full):
    keys = {v[0] for v in _SERIES.values()}
    for code in ("price_period", "market_terms", "commodity_group", "unit_as_published"):
        have = {d["external_product_id"] for d in details(full[1]) if d["attribute_code"] == code}
        assert have == keys, f"{code} missing on {sorted(keys - have)}"
    copper = {d["attribute_code"]: d["raw_value"] for d in details_of(full[1], "COPPER")}
    assert copper["price_period"].startswith("Monthly average")
    assert copper["market_terms"].startswith("Copper (LME)")
    assert copper["commodity_group"] == "Metals and minerals"


def test_each_description_row_went_to_its_own_series(full):
    """Rows are found by how they begin, so two series must not share one."""
    terms = [d["raw_value"] for d in details(full[1]) if d["attribute_code"] == "market_terms"]
    assert len(terms) == len(set(terms)) == 70


# ---- into the warehouse ------------------------------------------------------------------

@pytest.fixture
def conn():
    connection: sqlite3.Connection = dbmod.connect(":memory:")
    dbmod.migrate(connection)
    yield connection
    connection.close()


def ingest(conn, found):
    return ingest_payloads(conn, make_entry(), [t.to_payload() for t in found])


def test_a_weekly_run_lands_with_no_errors(conn, weekly):
    result = ingest(conn, weekly)
    assert not result.errors, result.errors[:3]
    assert result.rejected_out_of_scope == 0, "a detail with no product of its own was refused"
    offers = conn.execute("SELECT COUNT(*) FROM source_offer").fetchone()[0]
    # Shrimp stopped in 2023 and nothing in the last year names it, hidden sheet included.
    assert offers == 69


def test_a_series_with_nothing_this_run_sends_no_details_to_be_refused(weekly):
    assert details_of(weekly[1], "SHRIMP") == []
    assert "SHRIMP" not in {r["material_key"] for r in prices(weekly[0])}


def test_every_offer_is_wholesale_and_worldwide(conn, weekly):
    ingest(conn, weekly)
    assert [tuple(r) for r in conn.execute(
        "SELECT DISTINCT customer_segment, country_code_alpha2, currency, tax_included "
        "FROM source_offer")] == [("wholesale", "*", "USD", 0)]


def test_a_full_history_lands_with_no_errors(conn, full):
    result = ingest(conn, full)
    assert not result.errors, result.errors[:3]
    assert result.rejected_out_of_scope == 0
    assert conn.execute("SELECT COUNT(*) FROM source_offer").fetchone()[0] == 70
    reported = conn.execute(
        "SELECT COUNT(*) FROM price_observation WHERE provenance = 'reported'").fetchone()[0]
    assert reported == 40_824 + 140


def test_a_second_run_of_the_same_edition_adds_nothing_reported(conn, weekly):
    ingest(conn, weekly)
    before = conn.execute(
        "SELECT COUNT(*) FROM price_observation WHERE provenance = 'reported'").fetchone()[0]
    ingest(conn, weekly)
    assert conn.execute(
        "SELECT COUNT(*) FROM price_observation WHERE provenance = 'reported'").fetchone()[0] == before


def test_a_revised_month_lands_beside_the_old_value_and_overwrites_nothing(conn, weekly):
    ingest(conn, weekly)

    def revise(book):
        sheet = book["Monthly Prices"]
        sheet.cell(row_of(sheet, "2026M07"), column_of(sheet, "Copper"), 13000)
    ingest(conn, tables(stub=_Stub(workbook=edited(revise))))
    assert copper_reported(conn, "2026-07-01") == [13543.0, 13000.0]


def test_a_month_revised_to_equal_the_one_before_it_lands_too(conn, weekly):
    """His answer on #1919: as a change point, July equal to June would never be sent, and
    the warehouse would keep July's old value with nothing said."""
    ingest(conn, weekly)
    june: list[float] = []

    def revise(book):
        sheet = book["Monthly Prices"]
        col = column_of(sheet, "Copper")
        june.append(sheet.cell(row_of(sheet, "2026M06"), col).value)
        sheet.cell(row_of(sheet, "2026M07"), col).value = june[0]
    ingest(conn, tables(stub=_Stub(workbook=edited(revise))))
    assert copper_reported(conn, "2026-07-01") == [13543.0, float(june[0])]


def copper_reported(conn, business_date: str) -> list[float]:
    """Copper's reported rows for one month, oldest first: every reader takes the last."""
    return [r[0] for r in conn.execute(
        "SELECT po.price FROM price_observation po "
        "JOIN source_offer so ON so.offer_id = po.offer_id "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
        "WHERE sp.external_product_id = 'COPPER' AND po.provenance = 'reported' "
        "AND po.business_date = ? ORDER BY po.price_observation_id", (business_date,))]


def with_months(book, *stamps: str) -> None:
    """A later edition: the sheet reaches further, each new month copying the last one."""
    sheet = book["Monthly Prices"]
    last = sheet.max_row
    for stamp in stamps:
        row = sheet.max_row + 1
        for col in range(2, sheet.max_column + 1):
            sheet.cell(row, col).value = sheet.cell(last, col).value
        sheet.cell(row, 1).value = stamp


def test_only_the_window_carries_the_edition(weekly, full):
    """The newest month the sheet reaches, on every reported row of the window and on no
    other row: older months are never revised, and the observed row is our own."""
    for table in (weekly[0], full[0]):
        for r in prices(table):
            inside = r["provenance"] == "reported" and r["as_of_date"] >= "2025-10-01"
            assert r["edition"] == ("2026M09" if inside else ""), r


def test_a_month_revised_and_revised_back_reads_the_newest_edition(conn):
    """#1993 on the real workbook, his answer «اختم بالإصدار»: July 13543, then 13000 in the
    next edition, then 13543 again. The third edition's July is stored, so the newest row,
    which every reader shows, is the bank's word."""
    def second(book):
        sheet = book["Monthly Prices"]
        sheet.cell(row_of(sheet, "2026M07"), column_of(sheet, "Copper")).value = 13000
        with_months(book, "2026M10")

    def third(book):
        with_months(book, "2026M10", "2026M11")
    for change in (lambda book: None, second, third):
        ingest(conn, tables(stub=_Stub(workbook=edited(change))))
    assert copper_reported(conn, "2026-07-01") == [13543.0, 13000.0, 13543.0]


def test_a_new_edition_stores_its_window_again_and_rereading_it_stores_nothing(conn):
    """The cost he accepted on #1993: one row per month of the window per edition."""
    def reported_rows() -> int:
        return conn.execute("SELECT COUNT(*) FROM price_observation "
                            "WHERE provenance = 'reported'").fetchone()[0]
    ingest(conn, tables(stub=_Stub(workbook=edited(lambda book: None))))
    later = tables(stub=_Stub(workbook=edited(lambda book: with_months(book, "2026M10"))))
    window = [r for r in prices(later[0]) if r["provenance"] == "reported"]
    assert {r["edition"] for r in window} == {"2026M10"}
    before = reported_rows()
    assert ingest(conn, later).duplicates == 0
    # 819: November 2025 to October 2026, the window of the edition reaching 2026M10.
    assert reported_rows() - before == len(window) == 819
    assert ingest(conn, later).duplicates == len(window)
    assert reported_rows() - before == len(window)


def test_the_units_have_names_in_both_languages(conn, weekly):
    ingest(conn, weekly)
    rows = conn.execute("SELECT unit_code, name, name_ar FROM selling_unit").fetchall()
    assert {r[0] for r in rows} == {"tonne", "kg", "bbl", "mmbtu", "m3", "troy oz", "dmt", "sheet"}
    assert all(r[1] and r[2] for r in rows), rows


def test_a_retail_row_still_lands_retail(conn):
    """The widening reaches only a row that states a segment."""
    entry = SourceEntry.model_validate(dict(
        source_key="ARAMCO_FUEL_SA", source_name="Saudi Aramco", base_url="https://www.aramco.com",
        family="aramco-fuel-page", cadence="monthly", authority="official", currency="SAR",
        default_region="SA", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.COMMODITY_PRICE, scope=ExtractScope.LATEST_ONLY,
                             materials=["DIESEL"], regions=["SA"])],
    ))
    builder = RowBuilder(COMMODITY_PRICE)
    row = builder.row(material_key="DIESEL", country_code_alpha2="SA", currency="SAR", unit="liter",
                      tax_included="1", price="1.79", provenance="observed")
    table = ScrapedTable(entry.source_key, COMMODITY_PRICE.kind, "u", builder.header, [row])
    ingest_payloads(conn, entry, [table.to_payload()])
    assert [r[0] for r in conn.execute("SELECT customer_segment FROM source_offer")] == ["retail"]


def test_a_segment_the_warehouse_does_not_know_is_refused_out_loud(conn):
    entry = make_entry()
    builder = RowBuilder(COMMODITY_PRICE)
    row = builder.row(material_key="COPPER", country_code_alpha2="*", currency="USD", unit="kg",
                      tax_included="0", price="1", provenance="observed", consumer_segment="household")
    table = ScrapedTable(entry.source_key, COMMODITY_PRICE.kind, "u", builder.header, [row])
    result = ingest_payloads(conn, entry, [table.to_payload()])
    assert result.errors and "CHECK" in result.errors[0]
    assert conn.execute("SELECT COUNT(*) FROM source_offer").fetchone()[0] == 0


# ---- a segment is its own series, in the two rules #1905 wrote for retail ---------------

def commodity_table(*rows: dict) -> ScrapedTable:
    builder = RowBuilder(COMMODITY_PRICE)
    built = [builder.row(**{"material_key": "COPPER", "country_code_alpha2": "*", "currency": "USD",
                            "tax_included": "0", "price": "1", "provenance": "observed", **row})
             for row in rows]
    return ScrapedTable("WORLDBANK_PINK_SHEET", COMMODITY_PRICE.kind, "u", builder.header, built)


def land(conn, *rows: dict):
    return ingest_payloads(conn, make_entry(), [commodity_table(*rows).to_payload()])


def offers_of(conn) -> list[tuple]:
    return [tuple(r) for r in conn.execute(
        "SELECT so.customer_segment, COALESCE(su.unit_code, ''), so.country_code_alpha2, so.status "
        "FROM source_offer so LEFT JOIN selling_unit su ON su.selling_unit_id = so.selling_unit_id "
        "ORDER BY so.offer_id")]


def test_a_wholesale_offer_that_loses_its_unit_stays_one_offer(conn):
    """#1874's rule, for a segment it was not written for: the series is the same."""
    land(conn, {"unit": "kg", "consumer_segment": "wholesale"})
    land(conn, {"unit": "", "consumer_segment": "wholesale"})
    assert offers_of(conn) == [("wholesale", "", "*", "active")]


def test_a_wholesale_row_does_not_take_a_retail_offers_unit_away(conn):
    land(conn, {"unit": "kg"})
    land(conn, {"unit": "", "consumer_segment": "wholesale"})
    assert offers_of(conn) == [("retail", "kg", "*", "active"), ("wholesale", "", "*", "active")]


def test_a_retail_row_does_not_take_a_wholesale_offers_unit_away(conn):
    land(conn, {"unit": "kg", "consumer_segment": "wholesale"})
    land(conn, {"unit": ""})
    assert offers_of(conn) == [("wholesale", "kg", "*", "active"), ("retail", "", "*", "active")]


def test_a_wholesale_offer_learning_its_unit_is_not_a_second_offer(conn):
    land(conn, {"unit": "", "consumer_segment": "wholesale"})
    land(conn, {"unit": "kg", "consumer_segment": "wholesale"})
    assert offers_of(conn) == [("wholesale", "kg", "*", "active")]


def test_a_wholesale_series_whose_unit_changes_retires_the_old_offer(conn):
    land(conn, {"unit": "kg", "consumer_segment": "wholesale"})
    result = land(conn, {"unit": "tonne", "consumer_segment": "wholesale"})
    assert offers_of(conn) == [("wholesale", "kg", "*", "superseded"),
                               ("wholesale", "tonne", "*", "active")]
    assert any("retired 1 offer" in n for n in result.notices)


def test_a_pink_sheet_series_whose_unit_changes_shows_one_current_offer(conn):
    """The same rule through the real connector: his table must not keep both."""
    ingest(conn, tables(stub=_Stub(workbook=edited(lambda book: None))))

    def to_kilos(book):
        sheet = book["Monthly Prices"]
        sheet.cell(6, column_of(sheet, "Copper"), "($/kg)")
    ingest(conn, tables(stub=_Stub(workbook=edited(to_kilos))))
    copper = [tuple(r) for r in conn.execute(
        "SELECT su.unit_code, so.status FROM source_offer so "
        "JOIN selling_unit su ON su.selling_unit_id = so.selling_unit_id "
        "JOIN source_variant sv ON sv.source_variant_id = so.source_variant_id "
        "JOIN source_product sp ON sp.source_product_id = sv.source_product_id "
        "WHERE sp.external_product_id = 'COPPER' ORDER BY so.offer_id")]
    assert copper == [("tonne", "superseded"), ("kg", "active")]


def test_restating_wholesale_leaves_a_retail_sibling_alone(conn):
    land(conn, {"unit": "kg"}, {"unit": "kg", "consumer_segment": "wholesale"})
    land(conn, {"unit": "kg", "consumer_segment": "wholesale"})
    assert offers_of(conn) == [("retail", "kg", "*", "active"), ("wholesale", "kg", "*", "active")]


def test_restating_retail_leaves_a_wholesale_sibling_alone(conn):
    land(conn, {"unit": "kg"}, {"unit": "kg", "consumer_segment": "wholesale"})
    land(conn, {"unit": "kg"})
    assert offers_of(conn) == [("retail", "kg", "*", "active"), ("wholesale", "kg", "*", "active")]


def test_a_wholesale_row_naming_a_country_answers_only_for_its_own_segment(conn):
    """'*' means the country was not known, and a row naming it answers for it, inside a segment."""
    land(conn, {"unit": "kg"}, {"unit": "kg", "consumer_segment": "wholesale"})
    land(conn, {"unit": "kg", "consumer_segment": "wholesale", "country_code_alpha2": "EG"})
    assert offers_of(conn) == [("retail", "kg", "*", "active"), ("wholesale", "kg", "*", "superseded"),
                               ("wholesale", "kg", "EG", "active")]


def test_two_segments_alone_on_a_variant_are_not_siblings(conn):
    """Only a sibling in the same segment can make an offer stale, even with nothing restated."""
    land(conn, {"unit": "kg"}, {"unit": "tonne", "consumer_segment": "wholesale"})
    land(conn, {"unit": "tonne", "consumer_segment": "wholesale"})
    assert offers_of(conn) == [("retail", "kg", "*", "active"), ("wholesale", "tonne", "*", "active")]


# ---- the merge gate's findings, each pinned (#1919) ----------------------------------------

def hidden_row(sheet, period: str, commodity: str) -> int:
    for row in sheet.iter_rows(min_row=5):
        if row[0].value == period and row[1].value == commodity and row[6].value == "Blank vs number":
            return row[0].row
    raise AssertionError((period, commodity))


def test_an_impossible_month_is_loud_on_a_weekly_run_too():
    """One definition of a month stamp: a weekly run used to take 2026M13 silently."""
    def add(book):
        sheet = book["Monthly Prices"]
        sheet.cell(sheet.max_row + 1, 1, "2026M13")
    with pytest.raises(ValueError, match="where a month belongs"):
        tables(stub=_Stub(workbook=edited(add)))


def test_a_known_series_with_no_value_is_a_defect():
    def blank(book):
        sheet = book["Monthly Prices"]
        col = column_of(sheet, "Copper")
        for row in range(7, sheet.max_row + 1):
            # openpyxl's cell(row, col, None) writes nothing; the attribute does.
            sheet.cell(row, col).value = None
    table = tables(stub=_Stub(workbook=edited(blank)))[0]
    assert any("'Copper' holds no value" in d for d in table.defects)
    assert "COPPER" not in {r["material_key"] for r in prices(table)}


def test_a_sheet_whose_values_are_all_gone_is_loud_whatever_its_headers_say():
    """What a formula with no cached value reads as: every header, no number."""
    def blank(book):
        sheet = book["Monthly Prices"]
        for row in sheet.iter_rows(min_row=7, min_col=2):
            for cell in row:
                cell.value = None
    with pytest.raises(ValueError, match="known series with a value"):
        tables(stub=_Stub(workbook=edited(blank)))


def test_a_word_in_the_hidden_sheet_is_a_warning_not_a_dead_run():
    def word(book):
        sheet = book["Mismatch Details"]
        sheet.cell(hidden_row(sheet, "2026M07", "Sorghum"), 6, "n/a")
    table = tables(history=True, stub=_Stub(workbook=edited(word)))[0]
    assert any("no price above 0" in w for w in table.warnings)
    assert "COPPER" in {r["material_key"] for r in prices(table)}
    assert not any(r["material_key"] == "SORGHUM" and r["as_of_date"] == "2026-07-01"
                   for r in prices(table))


def test_a_zero_in_the_hidden_sheet_is_not_a_price():
    def zero(book):
        sheet = book["Mismatch Details"]
        sheet.cell(hidden_row(sheet, "2026M07", "Barley"), 6, 0)
    table = tables(history=True, stub=_Stub(workbook=edited(zero)))[0]
    assert not any(r["material_key"] == "BARLEY" and r["as_of_date"] == "2026-07-01"
                   for r in prices(table))
    assert any("no price above 0" in w for w in table.warnings)


OUTSIDE = "hidden row(s) skipped: a series or a month the published sheet does not have"


def skipped_outside(table) -> int:
    said = [w for w in table.warnings if w.endswith(OUTSIDE)]
    return int(said[0].split(" ")[0]) if said else 0


@pytest.fixture(scope="module")
def short_history():
    """The shortened workbook unchanged: its hidden rows for the months cut away are outside
    already, so a test counts what its edit adds rather than whether the warning exists."""
    return tables(history=True, stub=_Stub(workbook=edited(lambda book: None)))


def test_the_months_cut_from_the_shortened_workbook_are_outside(short_history):
    assert skipped_outside(short_history[0]) == 80


def test_a_hidden_row_for_a_month_the_sheet_lacks_is_said(short_history):
    def later(book):
        sheet = book["Mismatch Details"]
        sheet.cell(hidden_row(sheet, "2026M07", "Barley"), 1, "2026M11")
    table = tables(history=True, stub=_Stub(workbook=edited(later)))[0]
    assert skipped_outside(table) == skipped_outside(short_history[0]) + 1
    assert not any("no price above 0" in w for w in table.warnings)


def test_a_hidden_row_for_a_series_this_run_does_not_collect_is_a_warning_not_a_dead_run(
        short_history):
    """Every hidden row of the real file is Barley or Sorghum, so nothing else reached it."""
    def stranger(book):
        sheet = book["Mismatch Details"]
        sheet.cell(hidden_row(sheet, "2026M07", "Barley"), 2, "Unobtainium")
    table = tables(history=True, stub=_Stub(workbook=edited(stranger)))[0]
    assert skipped_outside(table) == skipped_outside(short_history[0]) + 1


def test_two_description_rows_for_one_series_give_it_no_sources_rather_than_a_guess():
    def second(book):
        sheet = book["Description"]
        sheet.insert_rows(5)
        sheet.cell(5, 1, "Copper (LME), grade A, three-month forward, NOT spot")
        sheet.cell(5, 2, "Some other publisher")
    table, facts = tables(stub=_Stub(workbook=edited(second)))
    copper = next(r for r in prices(table)
                  if r["material_key"] == "COPPER" and r["provenance"] == "observed")
    assert copper["official_source_name"] == ""
    assert any("2 Description rows begin 'Copper (LME)'" in w for w in table.warnings)
    assert "market_terms" not in {d["attribute_code"] for d in details_of(facts, "COPPER")}


def test_a_description_row_that_grows_a_third_cell_gives_no_sources_rather_than_a_guess():
    """Which of three cells names the sources is a question for a person, not for the code."""
    def third(book):
        for row in book["Description"].iter_rows():
            cells = [c for c in row if c.value is not None and str(c.value).strip()]
            if any(str(c.value).strip().startswith("Copper (LME)") for c in cells):
                book["Description"].cell(cells[-1].row, cells[-1].column + 1).value = "a note"
                return
        raise AssertionError("no Copper row")
    table = tables(stub=_Stub(workbook=edited(third)))[0]
    copper = next(r for r in prices(table)
                  if r["material_key"] == "COPPER" and r["provenance"] == "observed")
    assert copper["official_source_name"] == ""
    assert "no Description row for 'Copper'" in table.warnings


def test_a_change_log_line_that_shares_a_prefix_is_not_a_second_row(full):
    """Coal (South Africa) and Potassium chloride each have a one-cell change-log line."""
    for key in ("COAL_SOUTH_AFRICA", "POTASSIUM_CHLORIDE"):
        assert "market_terms" in {d["attribute_code"] for d in details_of(full[1], key)}


def test_an_iron_ore_unit_the_correction_does_not_know_is_stored_as_written_and_said():
    def retype(book):
        sheet = book["Monthly Prices"]
        sheet.cell(6, column_of(sheet, "Iron ore, cfr spot"), "($/mt)")
    table = tables(stub=_Stub(workbook=edited(retype)))[0]
    iron = next(r for r in prices(table) if r["material_key"] == "IRON_ORE")
    assert iron["unit"] == "tonne"
    assert any("Iron ore, cfr spot: the unit now reads '($/mt)'" in w for w in table.warnings)


def test_every_unit_the_parser_can_answer_has_words():
    from scrapex.normalize import _QUOTED_UNITS
    from scrapex.units import UNIT_NAMES
    assert set(_QUOTED_UNITS.values()) <= set(UNIT_NAMES)


def test_a_wholesale_row_does_not_give_a_retail_blank_offer_its_unit(conn):
    land(conn, {"unit": ""})
    land(conn, {"unit": "kg", "consumer_segment": "wholesale"})
    assert offers_of(conn) == [("retail", "", "*", "active"), ("wholesale", "kg", "*", "active")]


def test_a_retail_row_does_not_give_a_wholesale_blank_offer_its_unit(conn):
    land(conn, {"unit": "", "consumer_segment": "wholesale"})
    land(conn, {"unit": "kg"})
    assert offers_of(conn) == [("wholesale", "", "*", "active"), ("retail", "kg", "*", "active")]


# ---- the manifest and the registry -------------------------------------------------------

def test_the_manifest_entry_ships_off_and_obeying():
    entry = load_manifest(MANIFEST_FILE).get("WORLDBANK_PINK_SHEET")
    assert entry.family == ConnectorFamily.WORLDBANK_PINK_SHEET
    assert entry.active is False, "no source is made active without his word"
    assert str(entry.robots) == "obey"
    assert entry.crawl_pace_s == 2.5
    assert entry.cadence.value == "weekly"
    assert entry.vat_mode == VatMode.EXCLUSIVE
    assert entry.tax == [], "the workbook says nothing about tax, so no rule may claim it"


def test_the_family_is_registered_and_offers_a_history_backfill():
    assert ConnectorFamily.WORLDBANK_PINK_SHEET in _BUILDERS
    assert supports_history(ConnectorFamily.WORLDBANK_PINK_SHEET)


def test_tax_reads_unverified_because_nothing_is_claimed():
    state = resolve({}, "*", "COPPER").for_row(False)
    assert state.evidence == "unknown"
    assert state.short_label() == "Unverified"
