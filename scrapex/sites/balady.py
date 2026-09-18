"""apps.balady.gov.sa engineering offices — what this one site knows about itself.

Studied in `#998` before a line of this was written. Every constant below is a
measurement from that study, and the ones that look arbitrary are the ones that were
measured hardest.

WHY THIS IS NOT A `PartitionedListing`. Every directory before it implemented
`partitioncrawl.PartitionedListing`: bilingual pages, a partition of exhaustive cells,
and a total read off the listing's own paginator. Balady fails all three, measured:

  * **One language.** No switcher, no `culture` parameter, no `hreflang`; the page is
    `<html lang="ar" dir="rtl">`. Of 5,468 names, eight contain a latin word and two of
    those are the literal string `asd`.
  * **No exhaustive partition.** The only axis is `regionId`, and the thirteen regions
    summed to 4,625 against a register of 5,468 -- **843 offices answer to no region**.
    Muqawil had the same hole and it had a URL (`region_id=0`, `sites/muqawil.py`);
    here `regionId=0` returns **0 records**, and so do `14` and `99`. There is no
    escape hatch, so a cell-based crawl would carry a permanent deficit of 843.
  * **A paginator that is short by a page.** `GetCardsPagged` renders its own nav whose
    highest link is page index 272. Index 273 exists and holds ten offices, and nothing
    links to it -- the nav floors `total / pageSize` where it should ceil. A
    `read_last_page()` that trusts it loses those ten silently.

So the census is read from the JSON endpoint the page's own table uses, whose
`recordsFiltered` is the only honest total. Three requests cover the register.

WHAT THE ENDPOINT PUBLISHES THAT NO PAGE SHOWS. `X`, `Y` and `ClassificationStatus` are
returned for every row and bound to no column (the table binds six of the nine fields).
`X`/`Y` are the only coordinates the site gives anywhere -- the detail page has none --
and they are present on 55.4% of rows. `ClassificationStatus` is null on 100% of them.

THE COORDINATES ARE NOT VALIDATED HERE, AND THAT IS DELIBERATE. Over the 3,030 rows that
carry them, longitude ran -41.13 to 344.65 and latitude -117.49 to 1268.53. A latitude of
1268 is not a latitude. They are unvalidated user input at the source, and CLAUDE.md is
explicit that a wrong number is diagnosed at the stored row: correcting one here would
put the defect in the connector and hide it from every later reader. They are carried as
the strings they arrived as.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Matches `source_site.source_key`, as `directories.Directory.key` requires.
SITE_KEY = "balady_eng_offices"

BASE_URL = "https://apps.balady.gov.sa"

#: The census. A POST, because the site's own table posts to it -- `HttpFetcher.post`
#: already carries the politeness, the retry policy and the circuit breaker.
CENSUS_PATH = "/Eservices/Inquiries/InquiryEngOffices/LoadData"

#: One office's detail page. Anonymous and 200 **only** when the parameter is the
#: `HashedOfficeId`; the same route with the plain `OfficeId` answers 302 to
#: `ssoapp.balady.gov.sa`. The site's own cards view links by the plain code, so every
#: card on that view sends a visitor to a login screen. `detail_url` uses the hash.
DETAIL_PATH = "/Eservices/Inquiries/InquiryEngOffices/Details"

#: Every key one census row carries. Checked exactly rather than by subset: a key the
#: site adds is a field nobody has studied, and a key it drops is data we stopped
#: collecting. Either way the crawl must stop and say so, which is CLAUDE.md's "every
#: parse asserts its shape".
CENSUS_FIELDS = frozenset({
    "OfficeId", "HashedOfficeId", "OfficeName", "MobileNo",
    "ClassificationGrade", "ClassificationStatus", "LogoUrl", "X", "Y",
})

#: The six of those nine the site's own table binds to a column. Sent in the DataTables
#: form so the request is the one the site expects; the response carries all nine
#: regardless, which is the whole point of `#998`.
BOUND_COLUMNS = ("LogoUrl", "OfficeId", "OfficeName", "MobileNo",
                 "ClassificationGrade", "HashedOfficeId")

#: MEASURED, NOT CHOSEN. `length=20` returns 20, `500` returns 500, and **`6000`
#: returns 2000** -- the server caps a page and says nothing about having done so, since
#: it echoes the cap back in `recordsTotal`. Paging at the cap is three requests for the
#: whole register; trusting a larger number would silently collect 2,000 of 5,470.
PAGE_CAP = 2000

#: `LogoUrl` when the office has uploaded none. 39.5% of the register, and it travels
#: with the coordinates: of 2,161 placeholder rows, 2,158 have no `X`. Both are the
#: site's "this office completed a profile" signal, so the placeholder is worth naming
#: rather than storing as though it were a logo.
LOGO_PLACEHOLDER = "/Eservices/Inquiries/Content/images/em.jpg"


class CensusShapeError(RuntimeError):
    """The census response is not the shape this reader was written against.

    Its own class, and it raises rather than skipping the row, because the alternative
    is a crawl that reports success over a register it only partly read. `#998` measured
    the shape against 5,468 real rows; a departure from it is news.
    """


@dataclass(frozen=True)
class Office:
    """One census row, carried as it arrived.

    `office_id` is the business key -- the site's own `كود المكتب`, and also its
    `رقم ترخيص المكتب`: identical on 14 of 14 sampled detail pages, which is why there
    is one field here and not two. It is **text**, not a number: 48 of 5,468 contain a
    slash (`12/4205`, `323/13/28`), 23 begin with a zero, and one office's entire code
    is `0`.

    `hashed_office_id` is the fetch key, and nothing else in the product can reach the
    detail page without it.
    """

    office_id: str
    hashed_office_id: str
    office_name: str
    #: Null on 100% of the register from this endpoint. The detail page has it for 11 of
    #: 12 sampled offices, so the field is real and this is not where it lives.
    mobile_no: str | None
    #: `1`..`6`, and absent on 62.0% of the register.
    classification_grade: str | None
    #: Null on 100% of the register. The detail page prints `مصنف` for every office
    #: sampled, including offices with no grade, so it reads as a constant rather than a
    #: value; kept because the endpoint returns it and a day it is filled is a day we
    #: want the data, not a schema change.
    classification_status: str | None
    logo_url: str
    #: Longitude and latitude, AS STRINGS. See the module docstring: they are
    #: unvalidated at the source and are not repaired here.
    x: str | None
    y: str | None

    @property
    def has_logo(self) -> bool:
        return self.logo_url != LOGO_PLACEHOLDER

    @property
    def has_coordinates(self) -> bool:
        return bool(self.x) and bool(self.y)


@dataclass(frozen=True)
class Census:
    """The register as one sweep read it, and what that sweep cost.

    `declared_first` AND `declared_last` BOTH, because the register moves: it held 5,468
    offices on 2026-09-17 and 5,470 on 2026-09-18, +2 in about 22 hours. A single
    "total" would have to pick one of them and would then disagree with the row count
    for a reason the caller could not see.
    """

    offices: tuple[Office, ...]
    declared_first: int
    declared_last: int
    requests: int
    #: Rows whose `OfficeId` had already been seen in this sweep. Zero in the 5,468-row
    #: measurement, and reported rather than hidden: the only way it goes non-zero is
    #: the register shifting under the offsets mid-sweep, which the caller should know
    #: about rather than discover as a duplicate-key error downstream.
    duplicates_dropped: int

    @property
    def grew_during_sweep(self) -> int:
        return self.declared_last - self.declared_first


def census_form(*, start: int, length: int, region_id: int = -1, city_id: int = -1,
                text_search: str = "", activity: str = "") -> dict[str, str]:
    """The DataTables form the site's own table posts.

    `-1` IS THE SITE'S "ALL", not a sentinel invented here: the page's selects carry
    `value="-1"` for `اختر المنطقة` and the table's `data` callback posts whatever they
    hold. An empty string behaves the same way -- both return 5,470 -- and `-1` is used
    because it is what the page sends.
    """
    if start < 0:
        raise ValueError(f"start must not be negative, got {start}")
    if length < 1:
        raise ValueError(f"length must be at least 1, got {length}")
    form = {
        "draw": "1",
        "start": str(start),
        "length": str(length),
        "search[value]": "",
        "search[regex]": "false",
        "regionId": str(region_id),
        "cityId": str(city_id),
        "textSearch": text_search,
        "activity": activity,
    }
    for index, column in enumerate(BOUND_COLUMNS):
        form[f"columns[{index}][data]"] = column
        form[f"columns[{index}][name]"] = ""
        form[f"columns[{index}][searchable]"] = "true"
        form[f"columns[{index}][orderable]"] = "true"
        form[f"columns[{index}][search][value]"] = ""
        form[f"columns[{index}][search][regex]"] = "false"
    return form


def _text_or_none(row: dict[str, Any], key: str) -> str | None:
    value = row[key]
    if value is None:
        return None
    if not isinstance(value, str):
        raise CensusShapeError(
            f"{key} is {type(value).__name__}, expected a string or null: {value!r}")
    stripped = value.strip()
    return stripped or None


def _required_text(row: dict[str, Any], key: str) -> str:
    value = _text_or_none(row, key)
    if value is None:
        raise CensusShapeError(
            f"{key} is empty, and the census measured 0 empty in 5,468 rows: {row!r}")
    return value


def read_office(row: Any) -> Office:
    """One row, with its shape asserted before any of it is believed."""
    if not isinstance(row, dict):
        raise CensusShapeError(
            f"a census row must be an object, got {type(row).__name__}: {row!r}")
    keys = frozenset(row)
    if keys != CENSUS_FIELDS:
        added = sorted(keys - CENSUS_FIELDS)
        gone = sorted(CENSUS_FIELDS - keys)
        raise CensusShapeError(
            "the census row's fields are not the nine this reader was written against"
            + (f"; new: {added}" if added else "")
            + (f"; missing: {gone}" if gone else "")
            + ". A new field is a field nobody has studied; a missing one is data we "
              "stopped collecting. Re-study the source (#998) before widening this.")
    return Office(
        office_id=_required_text(row, "OfficeId"),
        hashed_office_id=_required_text(row, "HashedOfficeId"),
        office_name=_required_text(row, "OfficeName"),
        mobile_no=_text_or_none(row, "MobileNo"),
        classification_grade=_text_or_none(row, "ClassificationGrade"),
        classification_status=_text_or_none(row, "ClassificationStatus"),
        logo_url=_required_text(row, "LogoUrl"),
        x=_text_or_none(row, "X"),
        y=_text_or_none(row, "Y"),
    )


def read_census_page(payload: Any) -> tuple[int, tuple[Office, ...]]:
    """`(declared total, the page's offices)` from one `LoadData` response.

    `recordsFiltered` IS THE TOTAL AND `recordsTotal` IS NOT. The names invite the
    opposite reading, and DataTables' own convention is the opposite, but measured
    against this endpoint `recordsTotal` echoes the page length -- 20 for `length=20`,
    2000 for `length=6000` -- while `recordsFiltered` held 5,468 on every one of the
    three census requests. Reading `recordsTotal` as the register would report a
    directory of 20 offices.
    """
    if not isinstance(payload, dict):
        raise CensusShapeError(
            f"the census response must be an object, got {type(payload).__name__}")
    if "recordsFiltered" not in payload:
        raise CensusShapeError(
            "the census response carries no recordsFiltered, which is the only honest "
            f"total this site publishes; keys were {sorted(payload)}")
    declared = payload["recordsFiltered"]
    if isinstance(declared, bool) or not isinstance(declared, int) or declared < 0:
        raise CensusShapeError(
            f"recordsFiltered must be a non-negative integer, got {declared!r}")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise CensusShapeError(
            f"the census response's data must be a list, got {type(rows).__name__}")
    return declared, tuple(read_office(row) for row in rows)


def census(fetcher: Any, *, base_url: str = BASE_URL,
           page_cap: int = PAGE_CAP) -> Census:
    """The whole register, by offset, at the measured page cap.

    NO SEPARATE "HOW MANY ARE THERE" REQUEST. The first page's own `recordsFiltered` is
    the total, so asking first would spend a request to learn what the next one says
    anyway. Three requests cover 5,470 offices at `page_cap=2000`.

    A SHORT PAGE ENDS THE SWEEP, AND A SHORT SWEEP RAISES. The loop stops when a page
    comes back empty or the declared total is reached; if it stops with fewer offices
    than the register declared, that is a crawl which read part of a directory, and
    CLAUDE.md's "no silent failures" makes it an error rather than a smaller number.
    """
    if page_cap < 1:
        raise ValueError(f"page_cap must be at least 1, got {page_cap}")
    url = f"{base_url}{CENSUS_PATH}"
    collected: list[Office] = []
    seen: set[str] = set()
    duplicates = 0
    declared_first: int | None = None
    declared_last = 0
    requests = 0
    start = 0
    while True:
        response = fetcher.post(url, data=census_form(start=start, length=page_cap))
        requests += 1
        try:
            payload = response.json()
        except ValueError as exc:
            raise CensusShapeError(
                f"the census response at start={start} was not JSON: {exc}") from exc
        declared_last, page = read_census_page(payload)
        if declared_first is None:
            declared_first = declared_last
        if not page:
            break
        for office in page:
            if office.office_id in seen:
                duplicates += 1
                continue
            seen.add(office.office_id)
            collected.append(office)
        start += len(page)
        if start >= declared_last:
            break
    if declared_first is None:                    # unreachable: the loop posts once
        raise CensusShapeError("the census made no request")
    if len(collected) + duplicates < declared_first:
        raise CensusShapeError(
            f"the census read {len(collected)} office(s) and dropped {duplicates} "
            f"duplicate(s) against a declared {declared_first}. A partly-read "
            "directory is not a smaller directory.")
    return Census(offices=tuple(collected), declared_first=declared_first,
                  declared_last=declared_last, requests=requests,
                  duplicates_dropped=duplicates)


def detail_url(office: Office, *, base_url: str = BASE_URL) -> str:
    """The office's public detail page.

    BY THE HASH, NEVER BY THE CODE. `Details?OfficeId=<code>` answers 302 to the SSO
    login; `Details?OfficeId=<hash>` answers 200 to an anonymous plain client with no
    cookie. Measured both ways on the same office in `#998`.
    """
    if not office.hashed_office_id:
        raise ValueError(
            f"office {office.office_id!r} carries no HashedOfficeId, and the plain code "
            "reaches only the login page")
    return f"{base_url}{DETAIL_PATH}?OfficeId={office.hashed_office_id}"
