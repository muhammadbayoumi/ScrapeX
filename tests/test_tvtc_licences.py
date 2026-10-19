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

def _approve(tmp_path, monkeypatch, english: str, arabic: str):
    """The real `contractors.approve` over one stored plans page pair; the log and both
    datasets' rows."""
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
                (url, blob, url, "run-1", codec, dict_id, "2026-10-19T10:00:00Z"))
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

        def rows(key: str) -> list[dict]:
            return [json.loads(blob) for (blob,) in conn.execute(
                "SELECT r.data_json FROM generic_record AS r JOIN dataset_definition AS d "
                "ON d.dataset_definition_id = r.dataset_definition_id "
                "WHERE d.dataset_key = ?", (key,))]
        return said.getvalue(), rows("tvtc_training_plans"), rows(LICENCE_DATASET_KEY)
    finally:
        conn.close()


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


def test_a_refused_plans_page_derives_nothing(tmp_path, monkeypatch):
    log, plans, licences = _approve(tmp_path, monkeypatch, _raw("en"), _raw("en"))
    assert "LanguagesDisagree" in log
    assert plans == [] and licences == []
