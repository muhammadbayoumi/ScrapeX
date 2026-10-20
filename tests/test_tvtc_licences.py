"""TVTC's licences: one row per establishment, derived from the plans pages -- ES-5.

No network. The fixtures are `tests/test_tvtc_plans.py`'s two 20-row plans pages, whose
nested establishments carry their licences (personal data replaced by fakes).
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

from scrapex.extract.tvtc import RowShapeError
from scrapex.extract.tvtc_plans import (
    KNOWN_LICENCE_KEYS,
    LICENCE_DATASET_KEY,
    LICENCE_FIELDS,
    LICENCE_IDENTITY_FIELD,
    licence_candidate,
)
from scrapex.sites.tvtc import PLANS_PATH, PLANS_SITE_KEY, listing_url

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def _raw(locale: str) -> str:
    return (FIXTURES / f"tvtc_training_plans_p1_{locale}.json").read_text(encoding="utf-8")


def _doc(locale: str) -> dict:
    return json.loads(_raw(locale))


def _candidate(english: dict | None = None, arabic: dict | None = None):
    return licence_candidate(json.dumps(english or _doc("en")),
                             json.dumps(arabic or _doc("ar")))


def _establishments(doc: dict) -> dict[str, dict]:
    """Each establishment of a page with the licence its first plan carries."""
    found: dict[str, dict] = {}
    for row in doc["data"]:
        found.setdefault(str(row["establishment"]["id"]), row["establishment"]["license"])
    return found


# --- the registry ---------------------------------------------------------------------

def test_the_plans_directory_derives_the_licence_dataset():
    from scrapex import directories
    (reader,) = directories.get(PLANS_SITE_KEY).derived
    assert reader.candidate is licence_candidate
    assert reader.dataset_key == LICENCE_DATASET_KEY == "tvtc_establishment_licences"
    assert reader.identity_field == LICENCE_IDENTITY_FIELD == "establishment_id"


@pytest.mark.parametrize("key", ["muqawil_org", "oman_tenderboard", "tvtc_establishments"])
def test_no_other_directory_derives_anything(key):
    from scrapex import directories
    assert directories.get(key).derived == ()


def test_a_derived_approval_is_keyed_and_named_by_its_reader():
    from scrapex import directories
    from scrapex.contractors import _approval
    directory = directories.get(PLANS_SITE_KEY)
    (reader,) = directory.derived
    approval = _approval(directory, _candidate(), derived=reader)
    assert approval.dataset_key == LICENCE_DATASET_KEY
    assert approval.dataset_name == reader.dataset_name
    assert [f.field_key for f in approval.fields if f.identity] == ["establishment_id"]
    from scrapex.extract.tvtc_plans import bilingual_listing_candidate
    plain = _approval(directory, bilingual_listing_candidate(_raw("en"), _raw("ar")))
    assert plain.dataset_key == "tvtc_training_plans"
    assert [f.field_key for f in plain.fields if f.identity] == ["establishment_plan_id"]


# --- one row per establishment ----------------------------------------------------------

def test_a_page_gives_one_licence_per_establishment_it_holds():
    candidate = _candidate()
    expected = _establishments(_doc("ar"))
    assert len(expected) < 20, "the fixture page repeats an establishment across plans"
    assert [row["establishment_id"] for row in candidate.rows] == list(expected)
    assert candidate.approvable and candidate.warnings == ()


def test_the_columns_are_declared_and_only_the_establishment_is_the_identity():
    candidate = _candidate()
    assert [f.field_key for f in candidate.fields] == list(LICENCE_FIELDS)
    assert len(LICENCE_FIELDS) == 17 and LICENCE_FIELDS[0] == "establishment_id"
    assert [f.field_key for f in candidate.fields if f.identity_candidate] == [
        "establishment_id"]


def test_every_licence_value_is_the_one_the_site_sent():
    arabic, english = _establishments(_doc("ar")), _establishments(_doc("en"))
    for row in _candidate().rows:
        lic = arabic[row["establishment_id"]]
        assert row["license_id"] == str(lic["id"])
        assert row["license_id_encrypt"] == str(lic["id_encrypt"])
        assert row["ref_license"] == lic["ref_license"]
        assert (row["start_date"], row["end_date"]) == (lic["start_date"], lic["end_date"])
        assert (row["start_date_hijri"], row["end_date_hijri"]) == (
            lic["start_date_hijri"], lic["end_date_hijri"])
        assert (row["date_gregorian"], row["date_hijri"]) == (
            lic["date_gregorian"], lic["date_hijri"])
        assert row["license_status"] == lic["license_status"]
        assert row["license_status_label_ar"] == lic["license_status_label"]
        assert row["license_status_label_en"] == \
            english[row["establishment_id"]]["license_status_label"]
        assert row["is_license_expired"] == ("true" if lic["is_license_expired"] else "false")
        assert row["link_pdf_license"] == lic["link_pdf_license"]


def test_the_status_label_takes_its_english_from_the_english_view():
    row = _candidate().rows[0]
    assert row["license_status_label_en"] != row["license_status_label_ar"]


def test_every_licence_key_the_fixture_publishes_is_known():
    for locale in ("ar", "en"):
        for lic in _establishments(_doc(locale)).values():
            assert set(lic) <= KNOWN_LICENCE_KEYS, sorted(set(lic) - KNOWN_LICENCE_KEYS)


# --- refused, never guessed ----------------------------------------------------------

def _first_establishment_rows(doc: dict) -> list[dict]:
    first = doc["data"][0]["establishment"]["id"]
    return [row for row in doc["data"] if row["establishment"]["id"] == first]


def test_an_establishment_with_two_different_licences_on_one_page_is_refused():
    english, arabic = _doc("en"), _doc("ar")
    rows = _first_establishment_rows(arabic)
    assert len(rows) > 1, "the fixture's first establishment has several plans"
    rows[-1]["establishment"]["license"]["end_date"] = "2099-01-01"
    with pytest.raises(RowShapeError, match=re.escape("two different licences")):
        _candidate(english, arabic)


@pytest.mark.parametrize("empty", [None, [], {}])
@pytest.mark.parametrize("view", ["ar", "en"])
def test_a_licence_that_arrives_empty_is_refused(empty, view):
    english, arabic = _doc("en"), _doc("ar")
    (arabic if view == "ar" else english)["data"][0]["establishment"]["license"] = empty
    with pytest.raises(RowShapeError, match="establishment.license"):
        _candidate(english, arabic)


def test_a_licence_missing_a_key_it_reads_is_refused():
    english, arabic = _doc("en"), _doc("ar")
    arabic["data"][0]["establishment"]["license"].pop("end_date")
    with pytest.raises(RowShapeError, match=re.escape("establishment.license.end_date")):
        _candidate(english, arabic)


def test_a_licence_key_the_site_adds_is_kept_and_named():
    english, arabic = _doc("en"), _doc("ar")
    for doc, value in ((arabic, "ar"), (english, "en")):
        for row in doc["data"]:
            row["establishment"]["license"]["renewal_count"] = value
    candidate = _candidate(english, arabic)
    assert json.loads(candidate.rows[0]["unknown_keys"]) == {"license.renewal_count": "ar"}
    assert candidate.warnings == (
        "the register added a licence key this reader does not know: license.renewal_count",)


def test_its_locator_is_not_the_plans_one():
    """`generic_ingestion` is unique on (snapshot, locator): the same snapshot's second
    ingestion needs its own."""
    from scrapex.extract.tvtc_plans import bilingual_listing_candidate
    plans = bilingual_listing_candidate(_raw("en"), _raw("ar"))
    assert _candidate().locator != plans.locator


# --- through the real approval ---------------------------------------------------------

def _approve_pages(tmp_path, monkeypatch, pages, *, rounds: int = 1):
    """The real `contractors.approve` over stored plans page pairs `[(english, arabic,
    captured_at), ...]`, read in order; the log and both datasets' rows.

    THE ROWS ARE READ ON A SECOND CONNECTION, so a derived write that was never committed
    cannot pass for one that was (#1758's tests review, mutation m07).
    """
    import io
    from contextlib import closing, redirect_stdout

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

        def stored(url: str, body: str, captured_at: str) -> int:
            blob, codec, dict_id = encode(conn, body, label=None)
            cursor = conn.execute(
                "INSERT INTO generic_page_snapshot (source_url, html_content, "
                " content_hash, crawl_run_ref, html_codec, html_dict_id, captured_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (url, blob, url + captured_at, "run-1", codec, dict_id, captured_at))
            conn.commit()
            return int(cursor.lastrowid)

        pairs = {}
        for number, (english, arabic, captured_at) in enumerate(pages, start=1):
            pairs[f"page-{number}"] = {
                "en": (stored(listing_url(locale="en", page=number, path=PLANS_PATH),
                              english, captured_at), english),
                "ar": (stored(listing_url(locale="ar", page=number, path=PLANS_PATH),
                              arabic, captured_at), arabic)}
        monkeypatch.setattr(contractors, "_pairs",
                            lambda c, d, run_ref, *, ids=(): pairs)
        monkeypatch.setattr(contractors, "coverage", lambda c, key: "")
        monkeypatch.setattr(contractors, "LOG", tmp_path / "listing.log")
        said = io.StringIO()
        for _ in range(rounds):
            said = io.StringIO()
            with redirect_stdout(said):
                contractors.approve(conn, directory, "run-1")
    finally:
        conn.close()
    with closing(EngineDatabase(tmp_path / "scrapex-engine.db").connect()) as fresh:
        def rows(key: str) -> list[dict]:
            return [json.loads(blob) for (blob,) in fresh.execute(
                "SELECT r.data_json FROM generic_record AS r JOIN dataset_definition AS d "
                "ON d.dataset_definition_id = r.dataset_definition_id "
                "WHERE d.dataset_key = ?", (key,))]
        return said.getvalue(), rows("tvtc_training_plans"), rows(LICENCE_DATASET_KEY)


def _approve(tmp_path, monkeypatch, english: str, arabic: str):
    return _approve_pages(tmp_path, monkeypatch, [(english, arabic, "2026-10-19T10:00:00Z")])


def test_one_approval_stores_the_plans_and_their_licences(tmp_path, monkeypatch):
    log, plans, licences = _approve(tmp_path, monkeypatch, _raw("en"), _raw("ar"))
    assert "approved 1 page(s)" in log, log
    assert f"{LICENCE_DATASET_KEY}: approved 1 page(s) from the same pages (ES-5)" in log
    assert len(plans) == 20
    assert sorted(r["establishment_id"] for r in licences) == sorted(
        _establishments(_doc("ar")))
    assert {r["establishment_id"] for r in plans} == {r["establishment_id"] for r in licences}


def test_a_licence_refusal_keeps_the_plans_and_names_its_dataset(tmp_path, monkeypatch):
    """Refused on its own: the plans of the page are still stored, and the log says which
    dataset refused and why."""
    english, arabic = _doc("en"), _doc("ar")
    _first_establishment_rows(arabic)[-1]["establishment"]["license"]["end_date"] = "2099-01-01"
    log, plans, licences = _approve(tmp_path, monkeypatch, json.dumps(english),
                                    json.dumps(arabic))
    assert len(plans) == 20
    assert licences == []
    assert f"{LICENCE_DATASET_KEY}: RowShapeError" in log and "two different licences" in log
    # A refused page is not counted as approved (#1758's tests review, m01).
    assert "from the same pages (ES-5)" not in log


def test_a_refused_plans_page_derives_nothing(tmp_path, monkeypatch):
    log, plans, licences = _approve(tmp_path, monkeypatch, _raw("en"), _raw("en"))
    assert "LanguagesDisagree" in log
    assert plans == [] and licences == []


#: WRITTEN FROM THE CENSUS'S LICENCE KEYS, NOT FROM `LICENCE_COLUMNS`: column -> (view, key).
LICENCE_PATHS = {
    "license_id": ("ar", "id"), "license_id_encrypt": ("ar", "id_encrypt"),
    "ref_license": ("ar", "ref_license"), "start_date": ("ar", "start_date"),
    "end_date": ("ar", "end_date"), "start_date_hijri": ("ar", "start_date_hijri"),
    "end_date_hijri": ("ar", "end_date_hijri"), "date_gregorian": ("ar", "date_gregorian"),
    "date_hijri": ("ar", "date_hijri"), "license_status": ("ar", "license_status"),
    "license_status_label_ar": ("ar", "license_status_label"),
    "license_status_label_en": ("en", "license_status_label"),
    "is_license_expired": ("ar", "is_license_expired"),
    "request_status": ("ar", "request_status"),
    "link_pdf_license": ("ar", "link_pdf_license"),
}


def test_the_licence_path_table_covers_every_plain_column():
    assert set(LICENCE_PATHS) == set(LICENCE_FIELDS) - {"establishment_id", "unknown_keys"}


def test_every_licence_column_reads_its_own_key_from_its_own_view():
    """`id` and `id_encrypt` are equal on every census licence, so only a sentinel tells
    the two columns apart."""
    english, arabic = _doc("en"), _doc("ar")
    for view, doc in (("ar", arabic), ("en", english)):
        for row in doc["data"]:
            for _, key in LICENCE_PATHS.values():
                row["establishment"]["license"][key] = f"{view}:{key}"
    row = _candidate(english, arabic).rows[0]
    wrong = {column: row[column] for column, (view, key) in LICENCE_PATHS.items()
             if row[column] != f"{view}:{key}"}
    assert wrong == {}


def test_the_plans_reader_names_its_dataset_as_the_licences():
    """Not circular: the name is pinned, not read back from the reader (m20)."""
    from scrapex import directories
    from scrapex.extract.tvtc_plans import LICENCE_DATASET_NAME
    (reader,) = directories.get(PLANS_SITE_KEY).derived
    assert reader.dataset_name == LICENCE_DATASET_NAME == "TVTC establishment licences"


def test_a_licence_key_only_the_english_view_adds_is_kept():
    english, arabic = _doc("en"), _doc("ar")
    for row in english["data"]:
        row["establishment"]["license"]["renewal_count"] = "en"
    assert json.loads(_candidate(english, arabic).rows[0]["unknown_keys"]) == {
        "license.renewal_count": "en"}


def test_a_derived_warning_reaches_the_log_under_its_dataset(tmp_path, monkeypatch):
    english, arabic = _doc("en"), _doc("ar")
    for doc in (english, arabic):
        for row in doc["data"]:
            row["establishment"]["license"]["renewal_count"] = "x"
    log, _, licences = _approve(tmp_path, monkeypatch, json.dumps(english), json.dumps(arabic))
    assert licences
    assert (f"{LICENCE_DATASET_KEY}: the register added a licence key this reader does not "
            "know: license.renewal_count") in log


def test_a_derived_write_that_fails_after_writing_is_rolled_back(tmp_path, monkeypatch):
    """m06: page 1's derived approval wrote, then failed; page 2's committed after it. Had
    page 1 not been rolled back, its write would have committed with page 2's -- a second
    licence ingestion where there must be one."""
    from contextlib import closing

    from scrapex.databases import EngineDatabase
    from scrapex.extract import service
    real = service.approve_candidate
    calls = {"licence": 0}

    def failing_once(conn, snapshot_id, approval, **kwargs):
        result = real(conn, snapshot_id, approval, **kwargs)
        if approval.dataset_key == LICENCE_DATASET_KEY:
            calls["licence"] += 1
            if calls["licence"] == 1:
                raise RuntimeError("disk full")
        return result
    monkeypatch.setattr(service, "approve_candidate", failing_once)
    log, plans, licences = _approve_pages(tmp_path, monkeypatch, [
        (_raw("en"), _raw("ar"), "2026-10-19T10:00:00Z"),
        (_raw("en"), _raw("ar"), "2026-10-19T11:00:00Z")])
    assert f"{LICENCE_DATASET_KEY}: RuntimeError: disk full" in log
    assert len(plans) == 20 and licences
    with closing(EngineDatabase(tmp_path / "scrapex-engine.db").connect()) as fresh:
        (ingestions,) = fresh.execute(
            "SELECT COUNT(*) FROM generic_ingestion WHERE source_locator = ?",
            ("licensed-establishments/plans#licence",)).fetchone()
    assert ingestions == 1


def _renewed(end_date: str) -> tuple[str, str]:
    """The fixture page with its first establishment's licence ending on `end_date`."""
    english, arabic = _doc("en"), _doc("ar")
    for doc in (english, arabic):
        for row in _first_establishment_rows(doc):
            row["establishment"]["license"]["end_date"] = end_date
    return json.dumps(english), json.dumps(arabic)


def test_a_licence_read_differently_on_two_pages_of_one_run_is_said(tmp_path, monkeypatch):
    """The case ES-5 says would re-open it: said by name, the later reading stored."""
    target = next(iter(_establishments(_doc("ar"))))
    early, late = _renewed("2030-01-01"), _renewed("2031-01-01")
    log, _, licences = _approve_pages(tmp_path, monkeypatch, [
        (*early, "2026-10-19T10:00:00Z"), (*late, "2026-10-19T11:00:00Z")])
    assert "1 key(s) read with two different values on two pages of this run" in log, log
    assert target in log
    assert {r["establishment_id"]: r for r in licences}[target]["end_date"] == "2031-01-01"


def test_an_older_page_read_later_says_the_licence_kept_its_newer(tmp_path, monkeypatch):
    """The listing's own rule, now said for the derived dataset too (#1758, S1)."""
    newer, older = _renewed("2031-01-01"), _renewed("2030-01-01")
    log, _, licences = _approve_pages(tmp_path, monkeypatch, [
        (*newer, "2026-10-19T11:00:00Z"), (*older, "2026-10-19T10:00:00Z")])
    lines = log.splitlines()
    at = next(i for i, line in enumerate(lines) if "from the same pages (ES-5)" in line)
    assert lines[at + 1].startswith("    ") and "row(s) kept their newer evidence: this pass " \
        "read an older page of the same record" in lines[at + 1], lines[at:at + 2]
    target = next(iter(_establishments(_doc("ar"))))
    assert {r["establishment_id"]: r for r in licences}[target]["end_date"] == "2031-01-01"


def test_a_first_reading_counts_no_page_as_unchanged(tmp_path, monkeypatch):
    log, _, _ = _approve(tmp_path, monkeypatch, _raw("en"), _raw("ar"))
    assert (f"{LICENCE_DATASET_KEY}: approved 1 page(s) from the same pages (ES-5): "
            "0 unchanged and confirmed") in log


def test_a_second_reading_of_the_same_pages_counts_them_unchanged(tmp_path, monkeypatch):
    log, _, licences = _approve_pages(tmp_path, monkeypatch, [
        (_raw("en"), _raw("ar"), "2026-10-19T10:00:00Z")], rounds=2)
    assert licences
    assert (f"{LICENCE_DATASET_KEY}: approved 1 page(s) from the same pages (ES-5): "
            "1 unchanged and confirmed") in log, log
