"""TVTC's training plans: the second listing, its 77 declared columns, and a real approval.

No network. The fixtures are page 1 of `plans?limit=20` captured 2026-10-18 in both
languages (`#1716`), with every person's name, ID, mobile and e-mail inside the nested
establishment, and the establishment's phone, fax and e-mail, replaced by same-shape fakes.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from scrapex.extract.tvtc import LanguagesDisagree, RowShapeError
from scrapex.extract.tvtc_plans import (
    DATASET_KEY,
    FIELDS,
    IDENTITY_FIELD,
    KNOWN_KEYS,
    KNOWN_PLAN_KEYS,
    bilingual_listing_candidate,
)
from scrapex.pagesource import WHOLE, PageSource
from scrapex.sites.tvtc import (
    BASE_URL,
    LIST_PATH,
    PLANS_PATH,
    PLANS_SITE_KEY,
    TvtcPartition,
    TvtcPlansPartition,
    listing_url,
    locale_in_query,
    read_ids,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _raw(locale: str) -> str:
    return (FIXTURES / f"tvtc_training_plans_p1_{locale}.json").read_text(encoding="utf-8")


def _doc(locale: str) -> dict:
    return json.loads(_raw(locale))


def _candidate():
    return bilingual_listing_candidate(_raw("en"), _raw("ar"))


def _by_id(candidate) -> dict[str, dict]:
    return {row["establishment_plan_id"]: row for row in candidate.rows}


# --- the listing ------------------------------------------------------------------------

def test_the_plans_listing_is_the_measured_path_on_the_same_host():
    assert PLANS_PATH == "/api/v1/public-inquiries/licensed-establishments/plans"
    assert PLANS_SITE_KEY == "tvtc_training_plans"
    assert listing_url(locale="ar", page=2, path=PLANS_PATH) == (
        f"{BASE_URL}{PLANS_PATH}?locale=ar&limit=1000&page=2")


def test_a_path_that_is_neither_listing_is_refused():
    with pytest.raises(ValueError, match="two listings"):
        listing_url(page=1, path="/api/v1/somewhere-else")


def test_the_plans_partition_reads_its_own_path_under_its_own_key():
    part = TvtcPlansPartition()
    assert part.site_key == PLANS_SITE_KEY and part.cells() == (WHOLE,)
    assert part.listing_url(BASE_URL, locale="en", page=3).startswith(f"{BASE_URL}{PLANS_PATH}?")
    source = part.in_cell(WHOLE, last_page=2)
    assert isinstance(source, PageSource) and source.site_key == PLANS_SITE_KEY
    urls = list(source.listing_urls(BASE_URL))
    assert len(urls) == 4 and all(PLANS_PATH + "?" in url for url in urls)
    assert [locale_in_query(url)[1] for url in urls] == ["en", "ar", "en", "ar"]


def test_the_establishments_partition_still_reads_the_establishments_path():
    """The plans path is a parameter now; the first listing must not have moved."""
    part = TvtcPartition()
    assert part.site_key == "tvtc_establishments"
    urls = list(part.in_cell(WHOLE, last_page=1).listing_urls(BASE_URL))
    assert all(f"{LIST_PATH}?" in url for url in urls)
    assert part.in_cell(WHOLE, last_page=1).site_key == "tvtc_establishments"


def test_both_languages_hold_the_same_row_ids_in_the_same_order():
    assert read_ids(_raw("en")) == read_ids(_raw("ar"))
    assert len(set(read_ids(_raw("ar")))) == 20


# --- the registry ---------------------------------------------------------------------

def test_the_entry_carries_its_facts_and_ships_off():
    from scrapex import directories
    entry = directories.get(PLANS_SITE_KEY)
    assert entry.base_url == BASE_URL
    assert entry.dataset_key == DATASET_KEY == "tvtc_training_plans"
    assert entry.identity_field == IDENTITY_FIELD == "establishment_plan_id"
    assert entry.candidate is bilingual_listing_candidate
    assert entry.locale_pairing is locale_in_query
    assert isinstance(entry.partition(), TvtcPlansPartition)
    assert entry.profiles is None and entry.registration_field is None
    assert entry.active is False


# --- the declared schema ---------------------------------------------------------------

def test_the_columns_are_the_declared_list_in_its_declared_order():
    candidate = _candidate()
    assert [f.field_key for f in candidate.fields] == list(FIELDS)
    assert len(FIELDS) == 77 == len(set(FIELDS))
    assert FIELDS[:3] == ("establishment_plan_id", "establishment_id", "plan_id")
    assert FIELDS[-1] == "unknown_keys"


def test_every_field_is_nullable_text_and_only_the_row_id_is_the_identity():
    fields = _candidate().fields
    assert all(f.data_type == "text" and f.nullable for f in fields)
    assert [f.field_key for f in fields if f.identity_candidate] == [IDENTITY_FIELD]


def test_a_page_of_twenty_is_twenty_approvable_rows_carrying_every_field():
    candidate = _candidate()
    assert candidate.approvable and len(candidate.rows) == 20 and candidate.warnings == ()
    assert all(list(row) == list(FIELDS) for row in candidate.rows)


def test_the_approval_limit_holds():
    from scrapex.extract.models import MAX_TABLE_COLUMNS
    assert len(FIELDS) <= MAX_TABLE_COLUMNS


def test_every_key_the_fixture_publishes_is_known():
    for locale in ("en", "ar"):
        for row in _doc(locale)["data"]:
            assert set(row) <= KNOWN_KEYS, sorted(set(row) - KNOWN_KEYS)
            assert set(row["training_plan"]) <= KNOWN_PLAN_KEYS, \
                sorted(set(row["training_plan"]) - KNOWN_PLAN_KEYS)


# --- every column reads its own key from its own view ----------------------------------

TP = ("training_plan",)
PROGRAM = TP + ("training_program",)
#: WRITTEN FROM THE STUDY'S PLAN TABLE (`#1716`, the column-plan comment), NOT FROM
#: `COLUMNS`: (view, path). A table derived from `COLUMNS` would make the test vacuous.
PATHS: dict[str, tuple[str, tuple[str, ...]]] = {
    "establishment_id": ("ar", ("establishment", "id")),
    "plan_id": ("ar", TP + ("id",)), "plan_name": ("ar", TP + ("name",)),
    "status": ("ar", ("status", "value")),
    "status_label_ar": ("ar", ("status", "label")),
    "status_label_en": ("en", ("status", "label")),
    "classification_status_ar": ("ar", TP + ("classification_status",)),
    "classification_status_en": ("en", TP + ("classification_status",)),
    "target_group_id": ("ar", TP + ("training_plan_target_group_id",)),
    "program_id": ("ar", PROGRAM + ("id",)), "program_ar": ("ar", PROGRAM + ("name",)),
    "program_en": ("ar", PROGRAM + ("name_en",)),
    "program_type_id": ("ar", PROGRAM + ("program_type", "id")),
    "program_type_ar": ("ar", PROGRAM + ("program_type", "name_ar")),
    "program_type_en": ("ar", PROGRAM + ("program_type", "name_en")),
    "program_is_short": ("ar", PROGRAM + ("program_type", "is_short")),
    "program_is_development": ("ar", PROGRAM + ("program_type", "is_development")),
    "domain_id": ("ar", PROGRAM + ("domain", "id")),
    "domain_number": ("ar", PROGRAM + ("domain", "domain_number")),
    "domain_ar": ("ar", PROGRAM + ("domain", "name_ar")),
    "domain_en": ("ar", PROGRAM + ("domain", "name_en")),
    "specialization_id": ("ar", PROGRAM + ("specialization", "id")),
    "specialization_ar": ("ar", PROGRAM + ("specialization", "name_ar")),
    "specialization_en": ("ar", PROGRAM + ("specialization", "name_en")),
    "modality_id": ("ar", TP + ("modality", "id")),
    "modality_ar": ("ar", TP + ("modality", "name_ar")),
    "modality_en": ("en", TP + ("modality", "name")),
    "hours_per_day": ("ar", TP + ("number_of_trainingHours_day",)),
    "hours_online_sync": ("ar", TP + ("hours_online_synchronize",)),
    "hours_online_async": ("ar", TP + ("hours_online_non_synchronize",)),
    "cooperative_call_hours": ("ar", TP + ("cooperative_hours", "number_call_hours")),
    "cooperative_weeks": ("ar", TP + ("cooperative_hours", "number_weeks")),
    "product_id": ("ar", TP + ("product", "id")),
    "product_name": ("ar", TP + ("product", "name")),
    "product_price": ("ar", TP + ("product", "price")),
    "is_active_online": ("ar", TP + ("establishment_training_plan", "is_active_online")),
    "is_active_in_class": ("ar", TP + ("establishment_training_plan", "is_active_in_class")),
    "is_active_hybrid": ("ar", TP + ("establishment_training_plan", "is_active_hybrid")),
    "establishment_plan_status": ("ar", TP + ("establishment_training_plan", "status")),
    "frozen_at": ("ar", TP + ("establishment_training_plan", "frozen_at")),
    "plan_updated_at": ("ar", TP + ("establishment_training_plan", "updated_at")),
    **{name: ("ar", TP + (name,)) for name in (
        "enabled", "is_draft", "accreditation_status", "version_code",
        "training_plan_code", "request_id", "language", "parent_id",
        "specialization_number", "exam_number", "assessor_modality_id",
        "remote_training_enabled", "qualification_level", "qualification_title",
        "is_professional_certificate", "program_description", "program_main_objective",
        "total_hours", "total_credits", "total_days", "days", "months", "semesters",
        "hours_in_class", "total_lecture_hours", "total_practical_hours",
        "total_contact_hours", "calendar_type", "cooperative_semester_exists",
        "trainee_age", "number_of_trainers", "number_of_supervisors", "capacity",
        "accessibility_certificate_no")},
}


def _put(row: dict, path: tuple[str, ...], value) -> None:
    for key in path[:-1]:
        if not isinstance(row.get(key), dict):
            row[key] = {}
        row = row[key]
    row[path[-1]] = value


def test_the_path_table_covers_every_plain_column():
    assert set(PATHS) == set(FIELDS) - {"establishment_plan_id", "unknown_keys"}


def test_every_column_reads_its_own_key_from_its_own_view():
    english, arabic = _doc("en"), _doc("ar")
    for view, doc in (("ar", arabic), ("en", english)):
        for _, path in PATHS.values():
            _put(doc["data"][0], path, f"{view}:{'.'.join(path)}")
    # The language check reads `status.label` and `modality.name`: keep the views apart.
    arabic["data"][1]["status"]["label"] = "نشط"
    row = bilingual_listing_candidate(json.dumps(english), json.dumps(arabic)).rows[0]
    wrong = {column: row[column] for column, (view, path) in PATHS.items()
             if row[column] != f"{view}:{'.'.join(path)}"}
    assert wrong == {}


def test_the_row_id_is_the_identity_column():
    row = _candidate().rows[0]
    assert row["establishment_plan_id"] == str(_doc("ar")["data"][0]["id"])


# --- what each language view gives -----------------------------------------------------

def test_the_three_labels_get_their_english_from_the_english_view():
    row = _candidate().rows[0]
    english, arabic = _doc("en")["data"][0], _doc("ar")["data"][0]
    assert row["status_label_en"] == english["status"]["label"] == "Active"
    assert row["status_label_ar"] == arabic["status"]["label"]
    assert row["modality_en"] == english["training_plan"]["modality"]["name"]
    assert row["modality_ar"] == arabic["training_plan"]["modality"]["name_ar"]
    assert row["classification_status_en"] == \
        english["training_plan"]["classification_status"]


def test_the_untranslated_english_classification_is_stored_as_the_site_sent_it():
    """The site's own i18n key, measured; storing it is storing what the site says."""
    assert _candidate().rows[0]["classification_status_en"] == \
        "training_plans.program_classification.not_classified"


@pytest.mark.parametrize("english, arabic, said", [
    ("en", "en", "the Arabic copy carries no Arabic script"),
    ("ar", "ar", "the English copy carries Arabic script"),
    ("ar", "en", "the Arabic copy carries no Arabic script"),
])
def test_two_copies_that_are_not_two_languages_are_refused(english, arabic, said):
    with pytest.raises(LanguagesDisagree, match=re.escape(said)):
        bilingual_listing_candidate(_raw(english), _raw(arabic))


# --- what is not stored ----------------------------------------------------------------

def test_the_nested_establishment_is_reduced_to_its_id():
    """Its ~110 keys live in `tvtc_training_establishments`; owner data is not repeated
    here once per plan."""
    candidate = _candidate()
    owner_ids = {str(r["establishment"]["owner"]["owner_id_number"])
                 for r in _doc("ar")["data"] if r["establishment"]["owner"]["owner_id_number"]}
    assert owner_ids
    assert not any(value in owner_ids for row in candidate.rows for value in row.values())
    assert not any(name.startswith(("owner", "investor", "license")) for name in FIELDS)


def test_the_licence_is_not_a_plan_column():
    """It belongs to the establishment (`#1716` step 3)."""
    links = {r["establishment"]["license"]["link_pdf_license"] for r in _doc("ar")["data"]}
    assert not any(value in links for row in _candidate().rows for value in row.values())


# --- shapes ----------------------------------------------------------------------------

def test_cooperative_hours_as_an_empty_list_is_an_absent_object():
    rows = _candidate().rows
    raw = {str(r["id"]): r["training_plan"]["cooperative_hours"] for r in _doc("ar")["data"]}
    assert [] in raw.values()
    for row in rows:
        if raw[row["establishment_plan_id"]] == []:
            assert row["cooperative_call_hours"] is None and row["cooperative_weeks"] is None


def test_cooperative_hours_as_an_object_is_read():
    english, arabic = _doc("en"), _doc("ar")
    for doc in (english, arabic):
        doc["data"][0]["training_plan"]["cooperative_hours"] = {
            "id": 1, "number_call_hours": 360, "number_approved_units": 0, "number_weeks": 12}
    row = bilingual_listing_candidate(json.dumps(english), json.dumps(arabic)).rows[0]
    assert (row["cooperative_call_hours"], row["cooperative_weeks"]) == ("360", "12")


@pytest.mark.parametrize("change, said", [
    (lambda r: r["training_plan"].pop("total_credits"), "training_plan.total_credits is missing"),
    (lambda r: r["training_plan"].update(training_program=[{"id": 1}]),
     "training_plan.training_program is a list"),
    (lambda r: r.update(establishment=[{"id": 1}, {"id": 2}]), "establishment is a list"),
    (lambda r: r.pop("status"), "status is missing"),
])
def test_a_row_whose_shape_changed_refuses_the_page_by_name(change, said):
    english, arabic = _doc("en"), _doc("ar")
    change(arabic["data"][0])
    with pytest.raises(RowShapeError, match=re.escape(said)):
        bilingual_listing_candidate(json.dumps(english), json.dumps(arabic))


# --- added keys ---------------------------------------------------------------------

def test_a_key_added_at_either_level_and_in_either_view_is_kept_and_named():
    english, arabic = _doc("en"), _doc("ar")
    for view, doc in (("ar", arabic), ("en", english)):
        for row in doc["data"]:
            row["newTopLevel"] = view
            row["training_plan"]["new_plan_key"] = 0
            if view == "en":
                row["training_plan"]["english_only"] = "en"
    candidate = bilingual_listing_candidate(json.dumps(english), json.dumps(arabic))
    assert [f.field_key for f in candidate.fields] == list(FIELDS)
    assert json.loads(candidate.rows[0]["unknown_keys"]) == {
        "newTopLevel": "ar", "training_plan.english_only": "en", "training_plan.new_plan_key": 0}
    assert candidate.warnings == tuple(
        f"the register added a key this reader does not know: {key}"
        for key in ("newTopLevel", "training_plan.english_only", "training_plan.new_plan_key"))


def test_a_page_with_no_new_key_has_an_empty_unknown_keys_column():
    assert all(row["unknown_keys"] is None for row in _candidate().rows)


# --- end to end ---------------------------------------------------------------------

def _approve(tmp_path, monkeypatch, english: str, arabic: str) -> tuple[str, dict]:
    """The real `contractors.approve` over one stored page pair of the plans listing, after
    the crawl's own `register_site`, on the real schema."""
    import io
    from contextlib import redirect_stdout

    from scrapex import catalog, contractors, directories
    from scrapex.catalog_models import SiteCreate
    from scrapex.databases import DatabaseRegistry, EngineDatabase
    from scrapex.snapshotbody import encode

    directory = directories.get(PLANS_SITE_KEY)
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    conn = registry.engine.connect()
    try:
        catalog.register_site(conn, SiteCreate(
            site_key=directory.key, display_name=directory.display_name,
            base_url=directory.base_url))

        def stored(url: str, body: str) -> int:
            blob, codec, dict_id = encode(conn, body, label=None)
            cursor = conn.execute(
                "INSERT INTO generic_page_snapshot (source_url, html_content, "
                " content_hash, crawl_run_ref, html_codec, html_dict_id, captured_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (url, blob, url, "run-1", codec, dict_id, "2026-10-18T10:00:00Z"))
            conn.commit()
            return int(cursor.lastrowid)

        pair = {"en": (stored(listing_url(locale="en", page=1, path=PLANS_PATH), english),
                       english),
                "ar": (stored(listing_url(locale="ar", page=1, path=PLANS_PATH), arabic),
                       arabic)}
        monkeypatch.setattr(contractors, "_pairs",
                            lambda c, d, run_ref, *, ids=(): {"page-1": pair})
        monkeypatch.setattr(contractors, "coverage", lambda c, key: "")
        monkeypatch.setattr(contractors, "LOG", tmp_path / "listing.log")
        said = io.StringIO()
        with redirect_stdout(said):
            contractors.approve(conn, directory, "run-1")
        rows = {}
        for (blob,) in conn.execute(
                "SELECT r.data_json FROM generic_record AS r JOIN dataset_definition AS d "
                "ON d.dataset_definition_id = r.dataset_definition_id "
                "WHERE d.dataset_key = ?", (DATASET_KEY,)):
            row = json.loads(blob)
            rows[row["establishment_plan_id"]] = row
        return said.getvalue(), rows
    finally:
        conn.close()


def test_the_real_approval_stores_every_plan_of_the_page(tmp_path, monkeypatch):
    log, rows = _approve(tmp_path, monkeypatch, _raw("en"), _raw("ar"))
    assert "approved 1 page(s)" in log, log
    assert set(rows) == set(_by_id(_candidate()))
    assert rows["135"]["modality_en"] == "In class"


def test_a_refused_page_is_named_in_the_log_and_stores_nothing(tmp_path, monkeypatch):
    log, rows = _approve(tmp_path, monkeypatch, _raw("en"), _raw("en"))
    assert "LanguagesDisagree" in log, log
    assert rows == {}


def test_the_plans_listing_is_proven_complete_through_the_real_crawl(tmp_path):
    from scrapex.databases import DatabaseRegistry, EngineDatabase
    from scrapex.partitioncrawl import crawl_partition

    def page(ids, current, total=5, per_page=2):
        return json.dumps({"data": [{"id": key} for key in ids], "links": {},
                           "meta": {"total": total, "per_page": per_page,
                                    "current_page": current,
                                    "last_page": -(-total // per_page)}})
    pages = {1: (1, 2), 2: (3, 4), 3: (5,)}
    asked: list[str] = []

    def fetch(url: str) -> str:
        asked.append(url)
        number = int(re.search(r"[?&]page=(\d+)", url).group(1))
        return page(pages.get(number, ()), number)

    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    conn = registry.engine.connect()
    try:
        conn.execute("INSERT INTO source_site (source_key, source_name, base_url, "
                     "crawl_scope) VALUES (?, 'TVTC plans', ?, 'listing_only')",
                     (PLANS_SITE_KEY, BASE_URL))
        conn.commit()
        outcome = crawl_partition(conn, TvtcPlansPartition(), BASE_URL, fetch=fetch,
                                  run_ref="run-1", dataset_key=DATASET_KEY,
                                  resize_at_end=False)
    finally:
        conn.close()
    assert outcome.cells[0].provably_complete and outcome.deficit == 0
    assert set(outcome.ids) == {"1", "2", "3", "4", "5"}
    assert asked and all(f"{PLANS_PATH}?" in url for url in asked)
