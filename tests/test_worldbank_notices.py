"""A World Bank notice becomes one OCDS release, persons beside it (#1647).

Every notice here is a real `procnotices?fl=*` record from #1647's census
(`tests/fixtures/worldbank/notices.json`), with each contact person replaced and the
notice text removed. A test that edits one does so on a copy and says which field.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scrapex.sites import worldbank as wb

FIXTURE = Path(__file__).parent / "fixtures" / "worldbank" / "notices.json"
NOTICES = {n["id"]: n for n in json.loads(FIXTURE.read_text(encoding="utf-8"))["notices"]}

OPEN_REOI = "OP00473710"     # Request for Expression of Interest, deadline 2026-11-05 14:00
IFB = "OP00158446"           # Invitation for Bids ...
ITS_AWARD = "OP00184991"     # ... and the Contract Award that names it (ctr_orig_notice_id)
GPN_NO_REF = "OP00208979"    # General Procurement Notice, no borrower reference
REVISED_IFB = "OP00033824"   # Invitation for Bids, Revised
DRAFT_AWARD = "OP00012856"   # Contract Award, Draft: no publication date


def notice(notice_id: str) -> dict:
    return copy.deepcopy(NOTICES[notice_id])


# ---- the process key: his ruling, #1647 Q3 ------------------------------------------

def test_an_award_lands_in_the_process_of_the_invitation_it_names():
    """The key is project + borrower reference; the Bank's own link agrees (360 of 360
    in Egypt). If it did not, an award would never meet its tender."""
    award, invitation = notice(ITS_AWARD), notice(IFB)
    assert award["ctr_orig_notice_id"] == IFB
    assert wb.process_key(award) == wb.process_key(invitation)
    assert wb.release_from_notice(award).ocid == wb.release_from_notice(invitation).ocid


def test_the_reference_is_compared_with_its_case_and_spaces_folded():
    one, other = notice(IFB), notice(IFB)
    other["bid_reference_no"] = "  " + " ".join(one["bid_reference_no"].lower())
    assert wb.process_key(one) == wb.process_key(other)
    other["bid_reference_no"] = one["bid_reference_no"].replace("-", "/")
    assert wb.process_key(one) != wb.process_key(other), "punctuation is part of it"


def test_a_notice_with_no_reference_is_a_process_of_its_own():
    gpn = notice(GPN_NO_REF)
    assert not gpn.get("bid_reference_no")
    assert wb.process_key(gpn) == f"notice:{GPN_NO_REF}"


def test_the_same_reference_under_another_project_is_another_process():
    one, other = notice(IFB), notice(IFB)
    other["project_id"] = "P000001"
    assert wb.process_key(one) != wb.process_key(other)


# ---- stage, status, dates -------------------------------------------------------------

@pytest.mark.parametrize(("notice_id", "tag", "status"), [
    (OPEN_REOI, "tender", "active"),
    (IFB, "tender", "active"),
    (ITS_AWARD, "award", "complete"),
    (GPN_NO_REF, "planning", "planned"),
    (REVISED_IFB, "tenderAmendment", "active"),
    (DRAFT_AWARD, "award", None),
])
def test_each_notice_type_is_its_ocds_stage(notice_id, tag, status):
    release = wb.release_from_notice(notice(notice_id))
    assert release.payload["tag"] == [tag]
    assert release.payload["tender"]["status"] == status
    assert release.payload["tender"]["statusDetails"] == NOTICES[notice_id]["notice_status"]


def test_a_published_notice_is_dated_by_its_publication():
    release = wb.release_from_notice(notice(OPEN_REOI))
    assert release.payload["date"] == NOTICES[OPEN_REOI]["submission_date"]
    assert release.source_modified_at == NOTICES[OPEN_REOI]["api_modified_date"]


def test_a_draft_is_dated_by_the_banks_own_change_stamp():
    """A draft has no publication date; OCDS `date` is when the information was first
    recorded, which is the Bank's change stamp."""
    draft = notice(DRAFT_AWARD)
    assert "submission_date" not in draft
    assert wb.release_from_notice(draft).payload["date"] == draft["api_modified_date"]


def test_the_deadline_is_a_date_and_a_local_time_with_no_zone():
    period = wb.release_from_notice(notice(OPEN_REOI)).payload["tender"]["tenderPeriod"]
    assert period == {"endDateLocal": "2026-11-05", "endTimeLocal": "14:00",
                      "endTimeZone": None}
    assert "endDate" not in period, "an instant the source never stated must not be invented"


def test_the_estimate_keeps_its_currency():
    value = wb.release_from_notice(notice(OPEN_REOI)).payload["tender"]["value"]
    assert value == {"amount": float(NOTICES[OPEN_REOI]["bid_estimate_amount"]),
                     "currency": "USD"}


def test_an_award_says_its_usd_value_is_the_banks_conversion():
    award = notice(ITS_AWARD)
    payload = wb.release_from_notice(award).payload
    assert payload["awards"] == [{
        "id": award["contract_id"], "status": "active",
        "value": {"amount": float(award["contract_usd_value"]), "currency": "USD",
                  "isConverted": True}}]
    assert payload["contracts"][0]["dateSigned"] == award["contr_sgn_date"][:10]


# ---- persons stay out of the history ---------------------------------------------------

def test_the_contact_person_is_beside_the_payload_never_in_it():
    reoi = notice(OPEN_REOI)
    release = wb.release_from_notice(reoi)
    text = json.dumps(release.payload, ensure_ascii=False)
    for person_field in ("contact_name", "contact_email", "contact_phone_no",
                         "contact_job_title"):
        assert reoi[person_field] not in text, person_field
    (contact,) = release.contacts.values()
    assert contact["name"] == reoi["contact_name"]
    assert contact["email"] == reoi["contact_email"]


def test_the_notice_text_is_not_copied_into_the_payload():
    """It names bidders' owners; it stays in the stored response for part 4 to read."""
    with_text = notice(ITS_AWARD)
    with_text["notice_text"] = "<p>Beneficial Ownership Details</p>"
    assert "Beneficial" not in json.dumps(wb.release_from_notice(with_text).payload)


# ---- classifications, items, countries --------------------------------------------------

def test_unspsc_entries_become_items_once_each():
    reoi = notice(OPEN_REOI)
    reoi["unspsc_classification"] = reoi["unspsc_classification"] * 2
    items = wb.release_from_notice(reoi).payload["tender"]["items"]
    codes = [entry["proc_voc_id"] for entry in NOTICES[OPEN_REOI]["unspsc_classification"]]
    assert [item["id"] for item in items] == list(dict.fromkeys(codes))
    assert {item["classification"]["scheme"] for item in items} == {"UNSPSC"}


def test_the_sectors_are_the_banks_own_vocabulary():
    payload = wb.release_from_notice(notice(OPEN_REOI)).payload
    assert {c["scheme"] for c in payload["classifications"]} <= {
        "worldbank-sector", "worldbank-major-sector"}
    assert {c["id"] for c in payload["classifications"]} >= {
        s["sector_code"] for s in NOTICES[OPEN_REOI]["sector"]}


@pytest.mark.parametrize(("bank", "iso"), [
    ("EG", "EG"), ("ZR", "CD"), ("GZ", "PS"), ("YF", "RS"), ("TP", "TL"), ("RY", "YE"),
    ("3W", None), ("XK", None), ("1W", None), ("AN", None), ("null", None), ("", None),
    (None, None),
])
def test_a_bank_country_code_maps_to_iso_or_to_none(bank, iso):
    assert wb.iso_country(bank) == iso


def test_a_region_keeps_the_banks_code_when_it_has_no_iso_one():
    regional = notice(IFB)
    regional["project_ctry_code"], regional["project_ctry_name"] = "3W", "Western and Central Africa"
    (place,) = wb.release_from_notice(regional).payload["locations"]
    assert place == {"sourceCountryCode": "3W", "sourceCountryName": "Western and Central Africa",
                     "countryCode": None}


# ---- every read asserts its shape --------------------------------------------------------

@pytest.mark.parametrize(("field", "value", "message"), [
    ("id", None, "has no 'id'"),
    ("id", "OP123", "is not OP followed by eight digits"),
    ("project_id", "172548", "is not P######"),
    ("notice_type", "Tender", "unknown notice type"),
    ("notice_status", "Archived", "unknown notice status"),
    ("api_modified_date", None, "has no 'api_modified_date'"),
    ("project_ctry_code", "", "has no 'project_ctry_code'"),
])
def test_a_notice_in_another_shape_is_refused(field, value, message):
    changed = notice(OPEN_REOI)
    changed[field] = value
    with pytest.raises(wb.NoticeShapeError, match=message):
        wb.release_from_notice(changed)


def test_a_publication_date_in_another_shape_is_refused():
    changed = notice(OPEN_REOI)
    changed["submission_date"] = "07-Oct-2026"
    with pytest.raises(ValueError, match="is not in the layout"):
        wb.release_from_notice(changed)


def test_a_unspsc_entry_without_its_code_is_refused():
    changed = notice(OPEN_REOI)
    changed["unspsc_classification"] = [{"proc_voc_title": "Medical waste disposal"}]
    with pytest.raises(wb.NoticeShapeError, match="no proc_voc_id"):
        wb.release_from_notice(changed)
