"""The World Bank's procurement notices, read as OCDS releases.

Studied live in `#1647` before a line of this was written; every constant below is a
measurement from that study, and the section it came from is named beside it.

ONE NOTICE IN, ONE RELEASE OUT, AND NO NETWORK. This module reads one record of
`search.worldbank.org/api/v2/procnotices?fl=*` and returns a `tenderstore.Release`.
Fetching, paging and storing belong to the collector and to `scrapex/tenderstore.py`.

EVERY READ ASSERTS ITS SHAPE (`CLAUDE.md`). A notice without an id, a project, a known
type or a known status raises `NoticeShapeError` rather than becoming a half-true release;
the collector records it and goes on with the next notice.

THE PROCESS KEY IS HIS RULING (#1647 Q3): one contracting process per project and
borrower reference, the reference compared with its case and whitespace folded. On
Egypt's 1,448 notices that makes 944 processes, and it agrees with the Bank's own
`ctr_orig_notice_id` link on 360 of 360 awards. A notice that states no reference
(16 of 1,448) is a process of its own.

PERSONS STAY OUT OF THE PAYLOAD (#1647 Q4 and its follow-up): the notice's contact
person goes to `Release.contacts`, and `notice_text`, whose award blocks name bidders'
owners, stays in the stored response alone. Part 4 parses that text from there.
"""
from __future__ import annotations

import re
from typing import Any

from scrapex.normalize import parse_clock, parse_date, parse_instant, parse_money
from scrapex.tenderstore import Release


class NoticeShapeError(ValueError):
    """A notice that is not the shape #1647 measured."""


#: The seven notice types the facet lists (#1647 §4), and the OCDS release tag each is.
#: A Specific Procurement Notice is filed as one of the three tender types (§6.1).
_TAGS = {
    "General Procurement Notice": "planning",
    "Invitation for Bids": "tender",
    "Request for Expression of Interest": "tender",
    "Invitation for Prequalification": "tender",
    "Contract Award": "award",
    "Goods and Works Award": "award",
    "Small Contracts Award": "award",
}

#: OCDS tenderStatus for each stage. A draft states no status the Bank has published,
#: so it compiles to none and keeps its word in `statusDetails` (#1647 §6.1).
_STATUS = {"planning": "planned", "tender": "active", "award": "complete"}
_NOTICE_STATUSES = frozenset({"Published", "Revised", "Draft"})
#: A `Revised` notice restates its stage: OCDS's update tag for each.
_REVISED_TAG = {"planning": "planningUpdate", "tender": "tenderAmendment",
                "award": "awardUpdate"}

#: `procurement_group` -> OCDS mainProcurementCategory. Consulting and non-consulting
#: services are both `services`; the Bank's word stays in the release.
_CATEGORY = {"GO": "goods", "CW": "works", "CS": "services", "NC": "services"}

#: `market_approach_code` -> OCDS procurementMethod (#1647 §5.1).
_METHOD = {"O": "open", "L": "limited", "D": "direct"}

#: ISO 3166-1 alpha-2, the 249 officially assigned codes.
_ISO_3166_ALPHA2 = frozenset((
    "AD", "AE", "AF", "AG", "AI", "AL", "AM", "AO", "AQ", "AR", "AS", "AT", "AU", "AW", "AX",
    "AZ", "BA", "BB", "BD", "BE", "BF", "BG", "BH", "BI", "BJ", "BL", "BM", "BN", "BO", "BQ",
    "BR", "BS", "BT", "BV", "BW", "BY", "BZ", "CA", "CC", "CD", "CF", "CG", "CH", "CI", "CK",
    "CL", "CM", "CN", "CO", "CR", "CU", "CV", "CW", "CX", "CY", "CZ", "DE", "DJ", "DK", "DM",
    "DO", "DZ", "EC", "EE", "EG", "EH", "ER", "ES", "ET", "FI", "FJ", "FK", "FM", "FO", "FR",
    "GA", "GB", "GD", "GE", "GF", "GG", "GH", "GI", "GL", "GM", "GN", "GP", "GQ", "GR", "GS",
    "GT", "GU", "GW", "GY", "HK", "HM", "HN", "HR", "HT", "HU", "ID", "IE", "IL", "IM", "IN",
    "IO", "IQ", "IR", "IS", "IT", "JE", "JM", "JO", "JP", "KE", "KG", "KH", "KI", "KM", "KN",
    "KP", "KR", "KW", "KY", "KZ", "LA", "LB", "LC", "LI", "LK", "LR", "LS", "LT", "LU", "LV",
    "LY", "MA", "MC", "MD", "ME", "MF", "MG", "MH", "MK", "ML", "MM", "MN", "MO", "MP", "MQ",
    "MR", "MS", "MT", "MU", "MV", "MW", "MX", "MY", "MZ", "NA", "NC", "NE", "NF", "NG", "NI",
    "NL", "NO", "NP", "NR", "NU", "NZ", "OM", "PA", "PE", "PF", "PG", "PH", "PK", "PL", "PM",
    "PN", "PR", "PS", "PT", "PW", "PY", "QA", "RE", "RO", "RS", "RU", "RW", "SA", "SB", "SC",
    "SD", "SE", "SG", "SH", "SI", "SJ", "SK", "SL", "SM", "SN", "SO", "SR", "SS", "ST", "SV",
    "SX", "SY", "SZ", "TC", "TD", "TF", "TG", "TH", "TJ", "TK", "TL", "TM", "TN", "TO", "TR",
    "TT", "TV", "TW", "TZ", "UA", "UG", "UM", "US", "UY", "UZ", "VA", "VC", "VE", "VG", "VI",
    "VN", "VU", "WF", "WS", "YE", "YT", "ZA", "ZM", "ZW",
))

#: The Bank's own codes for five countries ISO codes differently (#1647 §6.2 C3). Every
#: other Bank code is either ISO's or names no ISO country (a region such as `3W`, `XK`,
#: which ISO leaves to user assignment) and maps to none.
_BANK_TO_ISO = {"ZR": "CD", "GZ": "PS", "YF": "RS", "TP": "TL", "RY": "YE"}

_NOTICE_ID = re.compile(r"OP\d{8}")
_PROJECT_ID = re.compile(r"P\d{6}")


def iso_country(bank_code: str | None) -> str | None:
    """The ISO 3166-1 code for a Bank country code, or None when it names no ISO country."""
    if not bank_code:
        return None
    code = _BANK_TO_ISO.get(bank_code, bank_code)
    return code if code in _ISO_3166_ALPHA2 else None


def process_key(notice: dict[str, Any]) -> str:
    """His rule (#1647 Q3): the project and the borrower's reference, else the notice."""
    reference = re.sub(r"\s+", "", (notice.get("bid_reference_no") or "").upper())
    if not reference:
        return f"notice:{notice['id']}"
    return f"{notice['project_id']}:{reference}"


def _required(notice: dict[str, Any], key: str) -> str:
    value = notice.get(key)
    if not isinstance(value, str) or not value.strip():
        raise NoticeShapeError(f"notice {notice.get('id')!r} has no {key!r}")
    return value.strip()


def release_from_notice(notice: dict[str, Any]) -> Release:
    """One `procnotices` record -> one OCDS release, its persons kept beside it."""
    notice_id = _required(notice, "id")
    if not _NOTICE_ID.fullmatch(notice_id):
        raise NoticeShapeError(f"notice id {notice_id!r} is not OP followed by eight digits")
    project_id = _required(notice, "project_id")
    if not _PROJECT_ID.fullmatch(project_id):
        raise NoticeShapeError(f"notice {notice_id}: project id {project_id!r} is not P######")
    notice_type = _required(notice, "notice_type")
    if notice_type not in _TAGS:
        raise NoticeShapeError(f"notice {notice_id}: unknown notice type {notice_type!r}")
    notice_status = _required(notice, "notice_status")
    if notice_status not in _NOTICE_STATUSES:
        raise NoticeShapeError(f"notice {notice_id}: unknown notice status {notice_status!r}")
    modified = parse_instant(_required(notice, "api_modified_date"))

    # A draft has no publication date (6 of Egypt's 1,448); the Bank's own change stamp is
    # then the date the information was first recorded, which is what OCDS `date` means.
    published = notice.get("submission_date")
    parse_date(published, "YYYY-MM-DDT00:00:00Z")
    stage = _TAGS[notice_type]
    tag = _REVISED_TAG[stage] if notice_status == "Revised" else stage
    key = process_key(notice)
    ocid = f"scrapex-worldbank:{key}"

    agency = (notice.get("agency_name") or notice.get("contact_organization") or "").strip()
    parties: list[dict[str, Any]] = [
        {"id": "worldbank", "name": "World Bank", "roles": ["funder"]}]
    contacts: dict[str, dict[str, str]] = {}
    if agency:
        party_ref = f"agency:{agency}"
        address = {k: v for k, v in (
            ("streetAddress", notice.get("contact_address")),
            ("locality", notice.get("contact_city")),
            ("region", notice.get("contact_region")),
            ("countryName", notice.get("contact_ctry_name")),
            ("countryCode", iso_country(notice.get("contact_ctry_code")))) if v}
        party: dict[str, Any] = {"id": party_ref, "name": agency, "roles": ["procuringEntity"]}
        if address:
            party["address"] = address
        parties.append(party)
        contacts[party_ref] = {
            "name": notice.get("contact_name"), "job_title": notice.get("contact_job_title"),
            "email": notice.get("contact_email"), "telephone": notice.get("contact_phone_no"),
            "fax_number": notice.get("contact_fax_no"), "url": notice.get("contact_web_url")}

    tender: dict[str, Any] = {"status": None if notice_status == "Draft" else _STATUS[stage],
                              "statusDetails": notice_status}
    if notice.get("bid_reference_no"):
        tender["id"] = notice["bid_reference_no"].strip()
    if notice.get("bid_description"):
        tender["title"] = notice["bid_description"].strip()
    if notice.get("market_approach_code") in _METHOD:
        tender["procurementMethod"] = _METHOD[notice["market_approach_code"]]
    if notice.get("procurement_method_name"):
        tender["procurementMethodDetails"] = notice["procurement_method_name"]
    if notice.get("procurement_group") in _CATEGORY:
        tender["mainProcurementCategory"] = _CATEGORY[notice["procurement_group"]]
    estimate = parse_money(notice.get("bid_estimate_amount"))
    if estimate is not None:
        tender["value"] = {"amount": float(estimate),
                           "currency": _required(notice, "bid_currency_code")}
    deadline = parse_date(notice.get("submission_deadline_date"), "YYYY-MM-DDT00:00:00Z")
    if deadline is not None:
        # A date and a local time with no zone (#1647 §6.1, Q6). OCDS `endDate` is one
        # RFC 3339 instant, which the source does not state, so it is not invented here.
        clock = parse_clock(notice.get("submission_deadline_time"))
        tender["tenderPeriod"] = {"endDateLocal": deadline.isoformat(),
                                  "endTimeLocal": clock.strftime("%H:%M") if clock else None,
                                  "endTimeZone": None}
    items = []
    for entry in notice.get("unspsc_classification") or []:
        code = (entry.get("proc_voc_id") or "").strip()
        if not code:
            raise NoticeShapeError(f"notice {notice_id}: a UNSPSC entry has no proc_voc_id")
        if code not in {item["id"] for item in items}:
            items.append({"id": code, "description": entry.get("proc_voc_title"),
                          "classification": {"scheme": "UNSPSC", "id": code,
                                             "description": entry.get("proc_voc_title")}})
    if items:
        tender["items"] = items

    payload: dict[str, Any] = {
        "ocid": ocid, "id": notice_id, "date": published or modified.strftime(
            "%Y-%m-%dT%H:%M:%SZ"),
        "tag": [tag], "initiationType": "tender",
        "language": notice.get("notice_lang_code", "").lower() or None,
        "parties": parties,
        "planning": {"budget": {"projectID": project_id,
                                "project": notice.get("project_name")}},
        "tender": tender,
        "classifications": [
            {"scheme": "worldbank-sector", "id": s["sector_code"],
             "description": s.get("sector_description")}
            for s in notice.get("sector") or [] if s.get("sector_code")] + (
            [{"scheme": "worldbank-major-sector", "id": notice["procurement_major_sector_code"],
              "description": notice.get("procurement_major_sector_name")}]
            if notice.get("procurement_major_sector_code") else []),
        "locations": [{"sourceCountryCode": _required(notice, "project_ctry_code"),
                       "sourceCountryName": notice.get("project_ctry_name"),
                       "countryCode": iso_country(notice["project_ctry_code"])}],
        "worldbank": {k: notice[k] for k in (
            "notice_type", "notice_status", "notice_version_no", "prodline", "regionname",
            "procurement_method_code", "market_approach_region_name", "bid_currency_code",
            "contract_id", "contract_usd_value", "contr_sgn_date", "ctr_orig_notice_id",
            "api_modified_date") if notice.get(k) not in (None, "")},
    }
    if notice.get("credit"):
        payload["worldbank"]["financing_ids"] = [c["financing_id"] for c in notice["credit"]]
    if stage == "award" and notice.get("contract_id") not in (None, "", "0"):
        # What the structured fields say. The award's suppliers and its signed price in
        # its own currency are in the notice text, which part 4 reads.
        award: dict[str, Any] = {"id": notice["contract_id"], "status": "active"}
        usd = parse_money(notice.get("contract_usd_value"))
        if usd:
            award["value"] = {"amount": float(usd), "currency": "USD", "isConverted": True}
        payload["awards"] = [award]
        signed = parse_date(notice.get("contr_sgn_date"), "YYYY-MM-DDT00:00:00Z")
        if signed is not None:
            payload["contracts"] = [{"id": notice["contract_id"],
                                     "awardID": notice["contract_id"],
                                     "dateSigned": signed.isoformat()}]
    return Release(process_key=key, ocid=ocid, payload=payload, project_ref=project_id,
                   source_modified_at=modified.strftime("%Y-%m-%dT%H:%M:%SZ"),
                   contacts=contacts)
