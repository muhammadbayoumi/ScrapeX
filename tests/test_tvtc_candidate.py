"""The TVTC candidate: 87 declared columns, the two-language join, and a real approval.

The fixtures are `tests/test_tvtc.py`'s: four real pages with every person's data replaced
by same-shape fakes, so the owner and investor assertions below are about the fakes.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from scrapex.extract.tvtc import (
    DATASET_KEY,
    FIELDS,
    IDENTITY_FIELD,
    KNOWN_KEYS,
    LanguagesDisagree,
    WorkingHoursShapeError,
    bilingual_listing_candidate,
)
from scrapex.sites.tvtc import RegisterShapeError, listing_url

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _raw(page: int, locale: str) -> str:
    return (FIXTURES / f"tvtc_establishments_p{page}_{locale}.json").read_text(
        encoding="utf-8")


def _doc(page: int, locale: str) -> dict:
    return json.loads(_raw(page, locale))


def _candidate(page: int = 1):
    return bilingual_listing_candidate(_raw(page, "en"), _raw(page, "ar"))


def _by_id(candidate) -> dict[str, dict]:
    return {row["establishment_id"]: row for row in candidate.rows}


# --- the declared schema ---------------------------------------------------------------

def test_the_columns_are_the_declared_list_in_its_declared_order():
    candidate = _candidate()
    assert [field.field_key for field in candidate.fields] == list(FIELDS)
    assert len(FIELDS) == 87 == len(set(FIELDS))
    assert FIELDS[:3] == ("establishment_id", "name_ar", "name_en")
    assert FIELDS[-10:] == (
        "owner_full_name", "owner_id_number", "owner_mobile", "owner_nationality",
        "investor_name", "investor_id_number", "investor_mobile", "investor_email",
        "investor_nationality", "investor_position")


def test_two_pages_give_the_same_schema_so_the_second_is_not_refused():
    """A schema derived per page would differ between pages and refuse the second."""
    one, two = _candidate(1), _candidate(38)
    assert [(f.field_key, f.data_type, f.nullable) for f in one.fields] == [
        (f.field_key, f.data_type, f.nullable) for f in two.fields]


def test_every_field_is_nullable_text_and_only_the_id_is_the_identity():
    fields = _candidate().fields
    assert all(f.data_type == "text" and f.nullable for f in fields)
    assert [f.field_key for f in fields if f.identity_candidate] == [IDENTITY_FIELD]


def test_every_row_carries_every_field():
    for page in (1, 38):
        assert all(list(row) == list(FIELDS) for row in _candidate(page).rows)


def test_a_page_of_ten_is_ten_approvable_rows_with_unique_ids():
    candidate = _candidate()
    assert candidate.approvable and len(candidate.rows) == 10
    assert len(_by_id(candidate)) == 10
    assert candidate.warnings == ()


def test_the_approval_limit_still_has_room_for_the_licence():
    """`ApprovalField` accepts 100 columns; the licence's 11 are still to come."""
    from scrapex.extract.models import MAX_TABLE_COLUMNS
    assert len(FIELDS) + 11 <= MAX_TABLE_COLUMNS


# --- what comes from which language -----------------------------------------------------

def test_the_type_and_city_get_their_english_from_the_english_page():
    row = _by_id(_candidate())["859310"]
    english = next(r for r in _doc(1, "en")["data"] if r["id"] == 859310)
    arabic = next(r for r in _doc(1, "ar")["data"] if r["id"] == 859310)
    assert row["establishment_type_en"] == english["establishment_type"]["name"]
    assert row["establishment_type_ar"] == arabic["establishment_type"]["name"]
    assert row["city_en"] == english["city"]["name"] == "Buraidah"
    assert row["city_ar"] == arabic["city"]["name"]
    assert row["city_en"] != row["city_ar"]


def test_the_region_has_no_english_twin_because_the_site_publishes_none():
    """Measured: `region.name` is Arabic in the English view too."""
    assert "region_en" not in FIELDS
    english = _doc(1, "en")["data"][0]["region"]["name"]
    assert english == _doc(1, "ar")["data"][0]["region"]["name"]


def test_the_establishment_with_no_region_is_a_row_with_empty_region_columns():
    rows = [row for row in _candidate(38).rows if row["region_id"] is None]
    assert len(rows) == 1
    assert rows[0]["region_ar"] is None and rows[0]["region_code"] is None


# --- how values are written -----------------------------------------------------------

def test_values_are_text_as_the_site_sent_them():
    row = _by_id(_candidate())["859310"]
    arabic = next(r for r in _doc(1, "ar")["data"] if r["id"] == 859310)
    assert row["trainees_capacity"] == str(arabic["trainees_capacity"])
    assert row["latitude"] == arabic["latitude"]
    assert row["commercial_record_national_number"] == \
        arabic["commercial_record_national_number"]
    assert row["is_currently_suspended"] == "false"
    assert row["skip_momra"] == "false"


def test_a_blank_value_is_none_not_an_empty_string():
    assert all(value != "" for row in _candidate().rows for value in row.values())


def test_a_violation_is_flattened_into_its_columns():
    rows = [row for row in _candidate().rows if row["violation_id"] is not None]
    assert len(rows) == 2, "page 1 holds two of the census's nine violations"
    arabic = {r["id"]: r for r in _doc(1, "ar")["data"]}
    for row in rows:
        violation = arabic[int(row["establishment_id"])]["violation"]
        assert row["violation_ar"] == violation["description_ar"]
        assert row["violation_en"] == violation["description_en"]
        assert row["violation_penalty_ar"] == violation["penalty"]["description_ar"]
        assert row["violation_penalty_grade"] == str(violation["penalty"]["grade"])
        assert row["violation_attachment_path"] == violation["attachment"]["path"]


def test_working_hours_keep_the_clock_and_drop_the_fetch_date():
    """Stored whole, every establishment with hours would read as changed every day."""
    rows = [row for row in _candidate(38).rows if row["working_hours"]]
    assert rows
    for row in rows:
        days = json.loads(row["working_hours"])
        assert all(set(day) == {"day_ar", "day_en", "start", "end"} for day in days)
        assert all(len(day["start"]) == 5 and day["start"][2] == ":" for day in days)
        assert "2026-" not in row["working_hours"]


def test_the_same_hours_fetched_on_another_day_store_the_same_value():
    english, arabic = _doc(38, "en"), _doc(38, "ar")
    for doc in (english, arabic):
        for row in doc["data"]:
            for day in row.get("workingHours") or []:
                day["start_time"] = day["start_time"].replace("2026-10-17", "2027-01-05")
                day["end_time"] = day["end_time"].replace("2026-10-17", "2027-01-05")
    later = bilingual_listing_candidate(json.dumps(english), json.dumps(arabic))
    assert [r["working_hours"] for r in later.rows] == [
        r["working_hours"] for r in _candidate(38).rows]


def test_a_working_hours_time_of_another_shape_is_refused():
    english, arabic = _doc(38, "en"), _doc(38, "ar")
    target = next(r for r in arabic["data"] if r.get("workingHours"))
    target["workingHours"][0]["start_time"] = "8 am"
    with pytest.raises(WorkingHoursShapeError, match="8 am"):
        bilingual_listing_candidate(json.dumps(english), json.dumps(arabic))


def test_the_signed_logo_url_is_never_stored():
    """A 30-minute pre-signed URL is a dead link by morning; the path is kept."""
    candidate = _candidate()
    assert not any("X-Amz" in (value or "") for row in candidate.rows
                   for value in row.values())
    with_logo = [row for row in candidate.rows if row["logo_path"]]
    assert with_logo and all(row["logo_path"].startswith("logos/") for row in with_logo)


def test_the_owner_and_the_investor_are_stored():
    """His ruling on `#1716` Q1."""
    row = _by_id(_candidate())["859310"]
    arabic = next(r for r in _doc(1, "ar")["data"] if r["id"] == 859310)
    assert row["owner_id_number"] == arabic["owner"]["owner_id_number"]
    assert row["owner_mobile"] == arabic["owner"]["owner_mobile_no"]
    assert row["owner_full_name"] == arabic["owner"]["owner_full_name"]
    assert row["investor_email"] == arabic["investor"]["investor_email"]
    assert row["investor_id_number"] == \
        arabic["investor"]["investor_identification_number"]


def test_every_key_the_fixture_publishes_is_known():
    """So a key outside `KNOWN_KEYS` in a crawl is news, not a key this test forgot."""
    for page in (1, 38):
        for row in _doc(page, "ar")["data"]:
            assert set(row) <= KNOWN_KEYS, sorted(set(row) - KNOWN_KEYS)


def test_a_key_the_register_adds_is_kept_as_a_column_and_named():
    english, arabic = _doc(1, "en"), _doc(1, "ar")
    for doc in (english, arabic):
        for row in doc["data"]:
            row["accreditation_level"] = {"id": 2, "name": "B"}
    candidate = bilingual_listing_candidate(json.dumps(english), json.dumps(arabic))
    assert [f.field_key for f in candidate.fields] == list(FIELDS) + ["accreditation_level"]
    assert candidate.rows[0]["accreditation_level"] == '{"id":2,"name":"B"}'
    assert candidate.warnings == (
        "the register added a key this reader does not know: accreditation_level",)


# --- the join is refused, never guessed ----------------------------------------------

def test_a_missing_language_copy_is_refused():
    with pytest.raises(LanguagesDisagree, match="missing"):
        bilingual_listing_candidate(_raw(1, "en"), "")
    with pytest.raises(LanguagesDisagree, match="missing"):
        bilingual_listing_candidate("", _raw(1, "ar"))


def test_two_copies_holding_different_establishments_are_refused():
    """An establishment added between the two fetches shifts every row after it."""
    english, arabic = _doc(1, "en"), _doc(1, "ar")
    english["data"][3]["id"] = 999
    with pytest.raises(LanguagesDisagree, match="999"):
        bilingual_listing_candidate(json.dumps(english), json.dumps(arabic))


def test_the_same_ids_in_another_order_are_refused():
    english, arabic = _doc(1, "en"), _doc(1, "ar")
    english["data"][0], english["data"][1] = english["data"][1], english["data"][0]
    with pytest.raises(LanguagesDisagree, match="another order"):
        bilingual_listing_candidate(json.dumps(english), json.dumps(arabic))


def test_a_copy_of_another_shape_is_refused_by_the_reader():
    with pytest.raises(RegisterShapeError):
        bilingual_listing_candidate("<html></html>", _raw(1, "ar"))


def test_a_page_past_the_end_is_not_approvable():
    empty = json.dumps({"data": [], "meta": {"total": 3141, "per_page": 10,
                                             "current_page": 400, "last_page": 315}})
    candidate = bilingual_listing_candidate(empty, empty)
    assert not candidate.approvable and candidate.rows == ()


# --- the real approval ------------------------------------------------------------------

def _approve(tmp_path, monkeypatch, english: str, arabic: str) -> tuple[str, dict]:
    """The real `contractors.approve` over one stored page pair, on the real directory
    and the real schema, after the crawl's own site registration. Returns the log and
    the stored rows by id."""
    import io
    from contextlib import redirect_stdout

    from scrapex import catalog, contractors, directories
    from scrapex.catalog_models import SiteCreate
    from scrapex.databases import DatabaseRegistry, EngineDatabase
    from scrapex.snapshotbody import encode

    directory = directories.get("tvtc_establishments")
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    conn = registry.engine.connect()
    try:
        # WHAT `contractors._run_for` DOES ON THE FIRST CRAWL: register the site from
        # `Directory.base_url`. Approval then registers it again from the stored page's
        # URL, and the two must agree or every page is a catalog conflict.
        catalog.register_site(conn, SiteCreate(
            site_key=directory.key, display_name=directory.display_name,
            base_url=directory.base_url))

        def stored(url: str, body: str) -> int:
            blob, codec, dict_id = encode(conn, body, label=None)
            cursor = conn.execute(
                "INSERT INTO generic_page_snapshot (source_url, html_content, "
                " content_hash, crawl_run_ref, html_codec, html_dict_id, captured_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (url, blob, url, "run-1", codec, dict_id, "2026-10-17T10:00:00Z"))
            conn.commit()
            return int(cursor.lastrowid)

        pair = {"en": (stored(listing_url(locale="en", page=1), english), english),
                "ar": (stored(listing_url(locale="ar", page=1), arabic), arabic)}
        monkeypatch.setattr(contractors, "_pairs",
                            lambda c, d, run_ref, *, ids=(): {"page-1": pair})
        monkeypatch.setattr(contractors, "coverage", lambda c, key: "")
        monkeypatch.setattr(contractors, "LOG", tmp_path / "listing.log")

        said = io.StringIO()
        with redirect_stdout(said):
            contractors.approve(conn, directory, "run-1")
        rows = {}
        for (blob,) in conn.execute(
                "SELECT r.data_json FROM generic_record AS r "
                "  JOIN dataset_definition AS d "
                "    ON d.dataset_definition_id = r.dataset_definition_id "
                " WHERE d.dataset_key = ?", (DATASET_KEY,)):
            row = json.loads(blob)
            rows[row["establishment_id"]] = row
        return said.getvalue(), rows
    finally:
        conn.close()


def test_the_real_approval_stores_every_row_of_the_page(tmp_path, monkeypatch):
    log, rows = _approve(tmp_path, monkeypatch, _raw(1, "en"), _raw(1, "ar"))
    assert "approved 1 page(s)" in log, log
    assert set(rows) == set(_by_id(_candidate()))
    stored = rows["859310"]
    assert stored["city_en"] == "Buraidah"
    assert stored["owner_id_number"] == _by_id(_candidate())["859310"]["owner_id_number"]


def test_a_refused_page_is_named_in_the_log_and_stores_nothing(tmp_path, monkeypatch):
    english, arabic = _doc(1, "en"), _doc(1, "ar")
    english["data"][3]["id"] = 999
    log, rows = _approve(tmp_path, monkeypatch, json.dumps(english), json.dumps(arabic))
    assert "LanguagesDisagree" in log, log
    assert rows == {}
