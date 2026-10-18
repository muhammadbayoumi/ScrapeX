"""The TVTC candidate: 88 declared columns, the two-language join, and a real approval.

The fixtures are `tests/test_tvtc.py`'s: four real pages with every person's data replaced
by same-shape fakes, so the owner and investor assertions below are about the fakes.
"""
from __future__ import annotations

import json
import re
import pathlib

import pytest

from scrapex.extract.tvtc import (
    DATASET_KEY,
    FIELDS,
    IDENTITY_FIELD,
    KNOWN_KEYS,
    LanguagesDisagree,
    RowShapeError,
    WorkingHoursShapeError,
    _clock,
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
    assert len(FIELDS) == 88 == len(set(FIELDS))
    assert FIELDS[:3] == ("establishment_id", "name_ar", "name_en")
    assert FIELDS[-11:] == (
        "owner_full_name", "owner_id_number", "owner_mobile", "owner_nationality",
        "investor_name", "investor_id_number", "investor_mobile", "investor_email",
        "investor_nationality", "investor_position", "unknown_keys")


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
    """Its `region` is `[]`, an empty PHP array, not `null` -- the one such row in the
    census, and the reason `_at` reads `[]` as an absent object."""
    assert [r["region"] for r in _doc(38, "ar")["data"] if not r["region"]] == [[]]
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


def _with_keys(added: dict, *, views=("en", "ar"), page: int = 1) -> tuple[str, str]:
    english, arabic = _doc(page, "en"), _doc(page, "ar")
    for view, doc in (("en", english), ("ar", arabic)):
        if view in views:
            for row in doc["data"]:
                row.update(added)
    return json.dumps(english), json.dumps(arabic)


def test_a_key_the_register_adds_is_kept_in_unknown_keys_and_named():
    candidate = bilingual_listing_candidate(
        *_with_keys({"accreditation_level": {"id": 2, "name": "B"}}))
    assert [f.field_key for f in candidate.fields] == list(FIELDS)
    assert json.loads(candidate.rows[0]["unknown_keys"]) == {
        "accreditation_level": {"id": 2, "name": "B"}}
    assert candidate.warnings == (
        "the register added a key this reader does not know: accreditation_level",)


def test_a_page_with_no_new_key_has_an_empty_unknown_keys_column():
    assert all(row["unknown_keys"] is None for row in _candidate().rows)


@pytest.mark.parametrize("added", [
    {"accreditationLevel": 1},                       # camelCase, as `workingHours` is
    {"x": 1},                                        # one letter
    {"city_en": "NEW"},                              # named like a declared column
    {"establishment_id": "NEW"},                     # named like the identity
    {f"k{n}": n for n in range(14)},                 # past MAX_TABLE_COLUMNS as columns
])
def test_any_added_key_leaves_the_schema_and_every_declared_value_alone(added):
    """Each of these refused EVERY page while added keys became columns of their own."""
    candidate = bilingual_listing_candidate(*_with_keys(added))
    assert [f.field_key for f in candidate.fields] == list(FIELDS)
    before = _by_id(_candidate())
    for row in candidate.rows:
        assert json.loads(row["unknown_keys"]) == dict(sorted(added.items()))
        assert {k: v for k, v in row.items() if k != "unknown_keys"} == {
            k: v for k, v in before[row["establishment_id"]].items() if k != "unknown_keys"}


def test_added_keys_are_sorted_so_every_page_stores_the_same_text():
    keys = ["zeta", "alpha", "mu", "kappa", "beta", "omega", "delta", "eta"]
    row = bilingual_listing_candidate(*_with_keys({k: 1 for k in keys})).rows[0]
    assert list(json.loads(row["unknown_keys"])) == sorted(keys)


def test_an_added_key_is_read_from_the_arabic_view_and_one_only_english_has_is_kept():
    english, arabic = _doc(1, "en"), _doc(1, "ar")
    for view, doc in (("ar", arabic), ("en", english)):
        for row in doc["data"]:
            row["both_views"] = view
    for row in english["data"]:
        row["english_only"] = "en"
    candidate = bilingual_listing_candidate(json.dumps(english), json.dumps(arabic))
    assert {row["unknown_keys"] for row in candidate.rows} == {
        '{"both_views":"ar","english_only":"en"}'}


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


def test_a_camel_case_key_the_register_adds_still_stores_every_row(tmp_path, monkeypatch):
    """Through the real approval: this was 0 rows stored and a job reading `completed`."""
    log, rows = _approve(tmp_path, monkeypatch, *_with_keys({"accreditationLevel": 2}))
    assert "approved 1 page(s)" in log, log
    assert len(rows) == 10
    assert all(json.loads(row["unknown_keys"]) == {"accreditationLevel": 2}
               for row in rows.values())


def test_a_page_whose_shape_changed_is_refused_by_name_and_stores_nothing(
        tmp_path, monkeypatch):
    english, arabic = _doc(1, "en"), _doc(1, "ar")
    arabic["data"][0]["violation"] = [{"id": 1}, {"id": 2}]
    log, rows = _approve(tmp_path, monkeypatch, json.dumps(english), json.dumps(arabic))
    assert "RowShapeError" in log and "violation is a list" in log, log
    assert rows == {}


# --- every column reads its own key from its own view -----------------------------------

#: WRITTEN FROM THE STUDY'S FIELD LIST (`#1716` §4a), NOT FROM `COLUMNS`: (view, path).
#: A getter pointing at a neighbouring key, or at the other language, reads somebody
#: else's sentinel below. 16 columns are null on every fixture row, so only a sentinel
#: reaches them.
PATHS: dict[str, tuple[str, tuple[str, ...]]] = {
    "name_ar": ("ar", ("name",)), "name_en": ("ar", ("name_en",)),
    "charity_name": ("ar", ("charity_name",)),
    "establishment_type_id": ("ar", ("establishment_type", "id")),
    "establishment_type_ar": ("ar", ("establishment_type", "name")),
    "establishment_type_en": ("en", ("establishment_type", "name")),
    "gender": ("ar", ("gender",)),
    "region_id": ("ar", ("region", "id")), "region_code": ("ar", ("region", "code")),
    "region_ar": ("ar", ("region", "name")),
    "city_id": ("ar", ("city", "id")), "city_code": ("ar", ("city", "code")),
    "city_ar": ("ar", ("city", "name")), "city_en": ("en", ("city", "name")),
    "parent_city_id": ("ar", ("city", "parent_city_id")),
    **{name: ("ar", (name,)) for name in (
        "district", "street_name", "address", "building_number",
        "alternative_building_number", "zip_code", "postal_office_box_number",
        "latitude", "longitude", "phone", "mobile", "fax", "email", "website",
        "cr_number", "commercial_record_number", "commercial_record_national_number",
        "commercial_record_main_number", "commercial_record_date",
        "commercial_record_expiry_date", "commercial_record_issue_place",
        "municipal_certificate_number", "municipal_certificate_date",
        "municipal_certificate_expiry_date", "postal_certificate_date",
        "postal_certificate_expiry_date", "defense_certificate",
        "defense_certificate_expiry_date", "charity_record_number",
        "charity_record_expiry_date", "charity_registration_place", "trainees_capacity",
        "area_size", "calendar_type", "is_currently_suspended", "can_add_trainee",
        "suspension_message", "skip_momra", "skip_momra_reason", "skip_momra_at",
        "notes", "attachment", "created_at")},
    "violation_id": ("ar", ("violation", "id")),
    "violation_number": ("ar", ("violation", "number")),
    "violation_ar": ("ar", ("violation", "description_ar")),
    "violation_en": ("ar", ("violation", "description_en")),
    "violation_penalty_code": ("ar", ("violation", "penalty", "code")),
    "violation_penalty_ar": ("ar", ("violation", "penalty", "description_ar")),
    "violation_penalty_en": ("ar", ("violation", "penalty", "description_en")),
    "violation_penalty_grade": ("ar", ("violation", "penalty", "grade")),
    "violation_attachment_path": ("ar", ("violation", "attachment", "path")),
    "violation_is_stopped": ("ar", ("violation", "is_stopped")),
    "violation_status": ("ar", ("violation", "status")),
    "violation_end_reason": ("ar", ("violation", "end_reason")),
    "violation_note": ("ar", ("violation", "note")),
    "logo_path": ("ar", ("file", "path")), "logo_filename": ("ar", ("file", "filename")),
    "logo_file_type": ("ar", ("file", "type")),
    "owner_full_name": ("ar", ("owner", "owner_full_name")),
    "owner_id_number": ("ar", ("owner", "owner_id_number")),
    "owner_mobile": ("ar", ("owner", "owner_mobile_no")),
    "owner_nationality": ("ar", ("owner", "owner_national_name")),
    "investor_name": ("ar", ("investor", "investor_name")),
    "investor_id_number": ("ar", ("investor", "investor_identification_number")),
    "investor_mobile": ("ar", ("investor", "investor_mobile_number")),
    "investor_email": ("ar", ("investor", "investor_email")),
    "investor_nationality": ("ar", ("investor", "investor_nationality_name")),
    "investor_position": ("ar", ("investor", "investor_position_user")),
}


def _put(row: dict, path: tuple[str, ...], value) -> None:
    for key in path[:-1]:
        if not isinstance(row.get(key), dict):
            row[key] = {}
        row = row[key]
    row[path[-1]] = value


def test_the_path_table_covers_every_plain_column():
    assert set(PATHS) == set(FIELDS) - {
        "establishment_id", "activity_code", "working_hours", "unknown_keys"}


def test_every_column_reads_its_own_key_from_its_own_view():
    english, arabic = _doc(1, "en"), _doc(1, "ar")
    for view, doc in (("ar", arabic), ("en", english)):
        for _, path in PATHS.values():
            _put(doc["data"][0], path, f"{view}:{'.'.join(path)}")
    row = bilingual_listing_candidate(json.dumps(english), json.dumps(arabic)).rows[0]
    wrong = {column: row[column] for column, (view, path) in PATHS.items()
             if row[column] != f"{view}:{'.'.join(path)}"}
    assert wrong == {}


# --- working hours, value by value ------------------------------------------------------

def test_working_hours_store_each_day_as_the_site_published_it():
    row = next(r for r in _candidate(38).rows if r["working_hours"])
    raw = next(r for r in _doc(38, "ar")["data"]
               if str(r["id"]) == row["establishment_id"])["workingHours"]
    assert json.loads(row["working_hours"]) == [
        {"day_ar": day["week_day_ar"], "day_en": day["week_day_en"],
         "start": day["start_time"][11:16], "end": day["end_time"][11:16]}
        for day in raw]
    # Arabic stored as itself, not as \\u escapes.
    assert raw[0]["week_day_ar"] in row["working_hours"]


@pytest.mark.parametrize("value, kept", [
    ("2026-10-17T08:00:00.000000Z", "08:00"),
    ("2026-10-17T22:30:00Z", "22:30"),
    ("2026-10-17T07:05:59.5Z", "07:05:59"),             # seconds the site said are kept
    ("2026-10-17T08:00:05Z", "08:00:05"),               # ...including ones under ten
    ("٢٠٢٦-١٠-١٧T٠٨:٣٠:٠٠.000000Z", "08:30"),        # folded by normalize, stored ASCII
])
def test_a_working_hours_time_keeps_its_clock(value, kept):
    assert _clock(value) == kept


@pytest.mark.parametrize("value", [
    "2026-10-17T08:00:00.000000", "2026-10-17T08:00:00.000000+03:00",
    "2026-10-17T08:00:00.000000Zjunk", "2026-10-17T08:00:00Z\n", "2026-10-17T08:00Z",
    "08:00", None, 800,
])
def test_a_working_hours_time_of_another_shape_is_refused(value):
    with pytest.raises(WorkingHoursShapeError):
        _clock(value)


@pytest.mark.parametrize("bad, said", [
    # Falsy values that are not absence: each passed as "no hours" through `or []`.
    (False, "workingHours is a bool"),
    ("", "workingHours is a str"),
    (0, "workingHours is a int"),
    ({}, "workingHours is a dict"),
    ({"start_time": "x"}, "workingHours is a dict"),
    ("08:00-22:00", "workingHours is a str"),
    (["Sunday 08:00-22:00"], "entry is a str"),
    ([{"week_day_ar": "الأحد", "start_time": "2026-10-17T08:00:00Z",
       "end_time": "2026-10-17T22:00:00Z"}], "has no 'week_day_en'"),
])
def test_working_hours_of_another_shape_are_refused_by_name(bad, said):
    english, arabic = _doc(38, "en"), _doc(38, "ar")
    arabic["data"][0]["workingHours"] = bad
    with pytest.raises(WorkingHoursShapeError, match=re.escape(said)):
        bilingual_listing_candidate(json.dumps(english), json.dumps(arabic))


# --- the activity code, and zero --------------------------------------------------------

def test_the_activity_code_is_the_published_code_and_two_codes_are_both_kept():
    row = _by_id(_candidate())["859310"]
    raw = next(r for r in _doc(1, "ar")["data"] if r["id"] == 859310)
    assert row["activity_code"] == str(raw["activity_list"][0])
    english, arabic = _doc(1, "en"), _doc(1, "ar")
    arabic["data"][0]["activity_list"] = [853040, 853041]
    later = bilingual_listing_candidate(json.dumps(english), json.dumps(arabic))
    assert later.rows[0]["activity_code"] == "853040,853041"


@pytest.mark.parametrize("codes", ["853040", 853040, [{"id": 1}], [True], [853040.0],
                                   [853040, "853041"], "", 0, {}])
def test_an_activity_list_of_another_shape_is_refused(codes):
    english, arabic = _doc(1, "en"), _doc(1, "ar")
    arabic["data"][0]["activity_list"] = codes
    with pytest.raises(RowShapeError, match="activity_list reads"):
        bilingual_listing_candidate(json.dumps(english), json.dumps(arabic))


@pytest.mark.parametrize("zero", [0, "0"])
def test_a_zero_is_stored_as_zero_not_as_blank(zero):
    english, arabic = _doc(1, "en"), _doc(1, "ar")
    arabic["data"][0]["trainees_capacity"] = zero
    row = bilingual_listing_candidate(json.dumps(english), json.dumps(arabic)).rows[0]
    assert row["trainees_capacity"] == "0"


# --- a changed shape is refused, never stored as NULLs ---------------------------------

def _changed(change, *, view: str = "ar") -> tuple[str, str]:
    english, arabic = _doc(1, "en"), _doc(1, "ar")
    change((arabic if view == "ar" else english)["data"][0])
    return json.dumps(english), json.dumps(arabic)


@pytest.mark.parametrize("change, said", [
    (lambda r: r.update(violation=[{"id": 1}, {"id": 2}]), "violation is a list"),
    (lambda r: r.update(owner=[r["owner"]]), "owner is a list"),
    (lambda r: r.update(region="Riyadh"), "region is a str"),
    (lambda r: r["owner"].update(id_number=r["owner"].pop("owner_id_number")),
     "owner.owner_id_number is missing"),
    (lambda r: r.pop("latitude"), "latitude is missing"),
])
def test_a_row_whose_shape_changed_refuses_the_page_by_name(change, said):
    with pytest.raises(RowShapeError, match=re.escape(said)):
        bilingual_listing_candidate(*_changed(change))


def test_a_shape_change_in_the_english_view_alone_is_refused_too():
    with pytest.raises(RowShapeError, match="city is a str"):
        bilingual_listing_candidate(*_changed(lambda r: r.update(city="Buraidah"),
                                              view="en"))


def test_an_absent_object_is_null_or_an_empty_list_and_reads_as_empty_columns():
    for absent in (None, []):
        row = bilingual_listing_candidate(
            *_changed(lambda r, a=absent: r.update(violation=a, file=a))).rows[0]
        assert row["violation_id"] is None and row["logo_path"] is None


def test_a_nested_empty_list_is_an_absent_object_too():
    """`_at`'s rule holds at every depth: `violation.penalty` as `[]` is no penalty."""
    row = bilingual_listing_candidate(*_changed(lambda r: r.update(violation={
        "id": 1, "number": "22", "description_ar": "x", "description_en": "x",
        "penalty": [], "attachment": [], "is_stopped": True, "status": None,
        "end_reason": None, "note": None}))).rows[0]
    assert row["violation_id"] == "1"
    assert row["violation_penalty_code"] is None and row["violation_attachment_path"] is None


@pytest.mark.parametrize("change, said", [
    (lambda r: r.update(violation={}), "violation.id is missing"),
    (lambda r: r.update(owner=""), "owner is a str"),
    (lambda r: r.update(region=0), "region is a int"),
])
def test_an_object_that_arrives_empty_or_falsy_is_refused_not_absent(change, said):
    """Only `None` and `[]` were measured as absence; `{}`, `""` and `0` are not it."""
    with pytest.raises(RowShapeError, match=re.escape(said)):
        bilingual_listing_candidate(*_changed(change))


@pytest.mark.parametrize("key", ["activity_list", "workingHours"])
def test_a_key_read_by_its_own_function_is_still_read_strictly(key):
    """The two readers that are not a `_ar`/`_en` getter go through `_at` as well."""
    with pytest.raises(RowShapeError, match=re.escape(f"{key} is missing")):
        bilingual_listing_candidate(*_changed(lambda r: r.pop(key)))


@pytest.mark.parametrize("absent", [None, []])
def test_an_absent_activity_list_is_an_empty_code(absent):
    row = bilingual_listing_candidate(
        *_changed(lambda r: r.update(activity_list=absent))).rows[0]
    assert row["activity_code"] is None


@pytest.mark.parametrize("dropped", ["week_day_ar", "week_day_en", "start_time", "end_time"])
def test_each_key_of_a_working_hours_entry_is_required(dropped):
    entry = {"week_day_ar": "الأحد", "week_day_en": "Sunday",
             "start_time": "2026-10-17T08:00:00Z", "end_time": "2026-10-17T22:00:00Z"}
    entry.pop(dropped)
    english, arabic = _doc(38, "en"), _doc(38, "ar")
    arabic["data"][0]["workingHours"] = [entry]
    with pytest.raises(WorkingHoursShapeError, match=re.escape(f"has no '{dropped}'")):
        bilingual_listing_candidate(json.dumps(english), json.dumps(arabic))


def test_every_added_key_from_either_view_is_named_once_in_sorted_order():
    """Eight keys, so a warning list left in set order is out of order on almost every
    hash seed; one with a falsy value and one only the English view carries."""
    added = {"zeta": 1, "alpha": 0, "mu": None, "kappa": 1, "beta": 1, "omega": 1,
             "delta": 1, "eta": 1}
    english, arabic = _doc(1, "en"), _doc(1, "ar")
    for view, doc in (("ar", arabic), ("en", english)):
        for row in doc["data"]:
            row.update(added)
            if view == "en":
                row["english_only"] = "en"
    candidate = bilingual_listing_candidate(json.dumps(english), json.dumps(arabic))
    assert candidate.warnings == tuple(
        f"the register added a key this reader does not know: {key}"
        for key in sorted([*added, "english_only"]))
