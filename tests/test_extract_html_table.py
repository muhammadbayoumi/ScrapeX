"""Bounded, non-product HTML-table discovery and inference tests."""
from __future__ import annotations

from scrapex.extract.html_table import detect_html_tables


REPORT_HTML = """
<!doctype html>
<html><body>
  <table id="city-report">
    <caption>City report</caption>
    <thead><tr>
      <th>City</th><th>Population</th><th>Coastal</th><th>Recorded</th>
    </tr></thead>
    <tbody>
      <tr><td>الرياض</td><td>7000000</td><td>No</td><td>2026-07-19</td></tr>
      <tr><td>Jeddah</td><td>4700000</td><td>Yes</td><td>2026-07-20</td></tr>
    </tbody>
  </table>
</body></html>
"""


def test_detects_a_non_product_table_and_infers_dynamic_schema():
    candidates = detect_html_tables(REPORT_HTML)

    assert len(candidates) == 1
    candidate = candidates[0].public()
    assert candidate["name"] == "City report"
    assert candidate["source_type"] == "html_table"
    assert candidate["source_locator"] == "table#city-report"
    assert candidate["estimated_row_count"] == 2
    assert [field["data_type"] for field in candidate["fields"]] == [
        "text", "integer", "boolean", "date",
    ]
    assert candidate["sample_records"][0]["city"] == "الرياض"
    assert candidate["candidate_identity_fields"] == ["city"]
    assert candidate["approvable"] is True


def test_discovery_returns_candidates_without_interpreting_nested_tables_twice():
    html = """
    <table><tr><th>Name</th></tr><tr><td>
      Outer<table><tr><th>Nested</th></tr><tr><td>Ignored</td></tr></table>
    </td></tr></table>
    """

    candidates = detect_html_tables(html)

    assert len(candidates) == 1
    assert candidates[0].public()["estimated_row_count"] == 1


def test_empty_and_headerless_tables_have_honest_actionable_results():
    candidates = detect_html_tables(
        "<table></table><table><tr><td>A</td><td>1</td></tr></table>"
    )

    assert candidates[0].approvable is False
    assert "No data rows were found" in candidates[0].warnings[-1]
    assert candidates[1].approvable is True
    assert "No semantic header row" in candidates[1].warnings[0]
    assert [field.source_name for field in candidates[1].fields] == [
        "Column 1", "Column 2",
    ]


def test_merged_cells_are_previewed_but_refused_before_ingestion():
    candidate = detect_html_tables(
        "<table><tr><th colspan='2'>Heading</th></tr>"
        "<tr><td>A</td><td>B</td></tr></table>"
    )[0]

    assert candidate.approvable is False
    assert any("Merged cells" in warning for warning in candidate.warnings)


def test_untrusted_markup_is_reduced_to_text_data():
    candidate = detect_html_tables(
        "<table><tr><th>Payload</th></tr>"
        "<tr><td>&lt;img src=x onerror=alert(1)&gt;</td></tr></table>"
    )[0]

    assert candidate.rows[0]["payload"] == "<img src=x onerror=alert(1)>"
