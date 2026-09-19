"""The Balady census reader: shape, offsets, and every way the shape can break.

No network. `census()` takes a fetcher, so every case here injects one.

The happy-path fixture is five REAL rows from the 2026-09-17 census, each kept for a
measured reason rather than because it was first: a row with coordinates and a grade, a
row with neither, an office whose code contains a slash, the office whose entire code is
`0`, and an office whose latitude is 94.8 -- which is not a latitude, and is stored
exactly as it arrived.
"""
from __future__ import annotations

import dataclasses
import json
import pathlib

import pytest

from scrapex.sites.balady import (
    BASE_URL,
    BOUND_COLUMNS,
    CENSUS_PATH,
    LOGO_PLACEHOLDER,
    PAGE_CAP,
    VOLATILE_ATTRS,
    VOLATILE_FIELDS,
    Office,
    Census,
    CensusShapeError,
    census,
    census_form,
    detail_url,
    read_census_page,
    read_office,
)

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "balady_loaddata_page0.json"


def _live_payload() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _row(**overrides) -> dict:
    """One well-formed row, overridable per case."""
    row = {
        "OfficeId": "5110001955",
        "HashedOfficeId": "bldyPrm9E68C86A49FDFD31",
        "OfficeName": "دار الخليج للاستشارات الهندسية",
        "MobileNo": None,
        "ClassificationGrade": None,
        "ClassificationStatus": None,
        "LogoUrl": "/Eservices/Inquiries/InquiryEngOffices/DownloadFile?url=bldyPrm55C8",
        "X": "46.71116840902193",
        "Y": "24.747132956319863",
    }
    row.update(overrides)
    return row


def _payload(rows, declared=None) -> dict:
    return {"draw": "1",
            "recordsFiltered": len(rows) if declared is None else declared,
            "recordsTotal": len(rows), "data": rows}


class _Resp:
    def __init__(self, payload=None, raw=None):
        self._payload, self._raw = payload, raw

    def json(self):
        if self._payload is None:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")
        return self._payload


class _StubFetcher:
    """Answers each POST with the next queued response, recording what was sent."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.posts: list[dict] = []

    def post(self, url, **kwargs):
        self.posts.append({"url": url, **kwargs})
        if not self._responses:
            raise AssertionError(f"unexpected extra request to {url}")
        return self._responses.pop(0)


# --- the live fixture ---------------------------------------------------------------

def test_the_real_census_page_parses_and_declares_its_total():
    declared, offices = read_census_page(_live_payload())
    assert declared == 5468
    assert len(offices) == 5


def test_a_code_containing_a_slash_survives_as_text():
    _, offices = read_census_page(_live_payload())
    codes = [o.office_id for o in offices]
    assert "12/4205" in codes, codes


def test_the_office_whose_code_is_zero_is_not_lost_to_falsiness():
    """`0` is a real `OfficeId` in the register, and `if not code` would drop it."""
    _, offices = read_census_page(_live_payload())
    assert "0" in [o.office_id for o in offices]


def test_an_impossible_latitude_is_stored_exactly_as_it_arrived():
    """94.8 is not a latitude. The connector is not where that gets corrected."""
    _, offices = read_census_page(_live_payload())
    out_of_range = [o for o in offices if o.y and abs(float(o.y)) > 90]
    assert out_of_range, "the fixture is meant to carry one"
    assert out_of_range[0].y == "94.80877727564585"
    assert out_of_range[0].x == "44.688281978913814"


def test_both_coordinates_keep_every_digit_the_site_published():
    """Not only the impossible one. Either half rounded is a number we did not read."""
    _, offices = read_census_page(_live_payload())
    located = [o for o in offices if o.has_coordinates]
    assert [(o.x, o.y) for o in located] == [
        ("46.76989065429919", "24.730443701999206"),
        ("44.688281978913814", "94.80877727564585"),
    ]


def test_every_office_in_the_fixture_has_both_identifiers():
    _, offices = read_census_page(_live_payload())
    assert all(o.office_id and o.hashed_office_id for o in offices)


# --- the derived properties ---------------------------------------------------------

def test_the_placeholder_logo_is_not_a_logo():
    office = read_office(_row(LogoUrl=LOGO_PLACEHOLDER))
    assert office.has_logo is False


def test_a_real_logo_is_a_logo():
    assert read_office(_row()).has_logo is True


def test_coordinates_need_both_halves():
    assert read_office(_row()).has_coordinates is True
    assert read_office(_row(X=None, Y=None)).has_coordinates is False
    assert read_office(_row(Y=None)).has_coordinates is False
    assert read_office(_row(X=None)).has_coordinates is False


def test_blank_strings_read_as_absent_not_as_values():
    office = read_office(_row(MobileNo="   ", ClassificationGrade="", X="", Y=""))
    assert office.mobile_no is None and office.classification_grade is None
    assert office.has_coordinates is False


# --- the form ------------------------------------------------------------------------

def test_the_form_sends_the_six_columns_the_site_binds():
    form = census_form(start=0, length=20)
    for index, column in enumerate(BOUND_COLUMNS):
        assert form[f"columns[{index}][data]"] == column
    assert f"columns[{len(BOUND_COLUMNS)}][data]" not in form


def test_the_form_asks_for_everything_by_default():
    form = census_form(start=40, length=2000)
    assert form["regionId"] == "-1" and form["cityId"] == "-1"
    assert form["textSearch"] == "" and form["activity"] == ""
    assert form["start"] == "40" and form["length"] == "2000"


def test_the_form_refuses_a_negative_offset():
    with pytest.raises(ValueError, match="must not be negative"):
        census_form(start=-1, length=20)


def test_the_form_refuses_an_empty_page():
    with pytest.raises(ValueError, match="at least 1"):
        census_form(start=0, length=0)


# --- the sweep -----------------------------------------------------------------------

def test_the_sweep_pages_at_the_cap_and_stops_when_the_register_is_read():
    first = [_row(OfficeId=str(n), HashedOfficeId=f"h{n}") for n in range(2000)]
    second = [_row(OfficeId=str(n), HashedOfficeId=f"h{n}")
              for n in range(2000, 3000)]
    fetcher = _StubFetcher([_Resp(_payload(first, declared=3000)),
                            _Resp(_payload(second, declared=3000))])
    result = census(fetcher, page_cap=2000)
    assert isinstance(result, Census)
    assert len(result.offices) == 3000
    assert result.requests == 2
    assert [p["data"]["start"] for p in fetcher.posts] == ["0", "2000"]


def test_the_sweep_spends_no_request_asking_for_the_total():
    """The first page's own `recordsFiltered` is the total."""
    fetcher = _StubFetcher([_Resp(_payload([_row()], declared=1))])
    result = census(fetcher, page_cap=2000)
    assert result.requests == 1 and result.declared_first == 1


def test_a_register_that_grows_during_the_sweep_records_both_totals():
    """Measured: 5,468 offices on 2026-09-17 and 5,470 the next day."""
    first = [_row(OfficeId=str(n), HashedOfficeId=f"h{n}") for n in range(2)]
    second = [_row(OfficeId="2", HashedOfficeId="h2"),
              _row(OfficeId="3", HashedOfficeId="h3")]
    fetcher = _StubFetcher([_Resp(_payload(first, declared=3)),
                            _Resp(_payload(second, declared=4))])
    result = census(fetcher, page_cap=2)
    assert result.declared_first == 3 and result.declared_last == 4
    assert result.grew_during_sweep == 1
    assert len(result.offices) == 4


def test_a_row_repeated_across_pages_is_counted_not_hidden():
    """THE REPEATED ROW CARRIES A DIFFERENT HASH, which is what the site does.

    This test used to give the repeat an identical `HashedOfficeId`, contradicting the
    measurement in the module it guards -- "identical in 0 of 20. It is a fresh
    ciphertext of the same office each time". With the hashes equal, keying the dedup on
    the hash instead of `office_id` passed, so the module's headline claim that
    `office_id` is the identity was guarded by nothing.

    `declared=3` and not 4: the sweep reads three distinct offices, so it is complete
    against what the register declared. The old total was chosen so that only crediting
    the duplicate could clear it.
    """
    first = [_row(OfficeId="1", HashedOfficeId="h1"),
             _row(OfficeId="2", HashedOfficeId="h2")]
    second = [_row(OfficeId="2", HashedOfficeId="A-FRESH-CIPHERTEXT-OF-OFFICE-2"),
              _row(OfficeId="3", HashedOfficeId="h3")]
    fetcher = _StubFetcher([_Resp(_payload(first, declared=3)),
                            _Resp(_payload(second, declared=3))])
    result = census(fetcher, page_cap=2)
    assert result.duplicates_dropped == 1
    assert [o.office_id for o in result.offices] == ["1", "2", "3"]


def test_a_sweep_that_reads_part_of_the_register_raises():
    """A page that empties early while the register declares more is not a smaller
    register."""
    fetcher = _StubFetcher([_Resp(_payload([_row()], declared=900)),
                            _Resp(_payload([], declared=900))])
    with pytest.raises(CensusShapeError, match="partly-read"):
        census(fetcher, page_cap=1)


def test_an_empty_register_is_not_an_error():
    fetcher = _StubFetcher([_Resp(_payload([], declared=0))])
    result = census(fetcher, page_cap=2000)
    assert result.offices == () and result.declared_first == 0


def test_a_response_that_is_not_json_names_the_offset():
    fetcher = _StubFetcher([_Resp(payload=None)])
    with pytest.raises(CensusShapeError, match="start=0"):
        census(fetcher)


def test_the_sweep_refuses_a_page_cap_below_one():
    """MATCHED ON `page_cap`, because `census_form` raises the same words.

    `census_form(length=0)` is evaluated before `post` is reached, so with the guard in
    `census` deleted a ValueError still arrived -- from the form -- and "at least 1"
    matched it. The test passed for the wrong reason.
    """
    with pytest.raises(ValueError, match="page_cap must be at least 1"):
        census(_StubFetcher([]), page_cap=0)


def test_the_default_page_cap_is_the_measured_server_cap():
    assert PAGE_CAP == 2000


# --- the response envelope -----------------------------------------------------------

def test_a_response_that_is_not_an_object_raises():
    with pytest.raises(CensusShapeError, match="must be an object"):
        read_census_page([_row()])


def test_a_response_without_records_filtered_raises_and_lists_what_it_had():
    with pytest.raises(CensusShapeError, match="recordsFiltered"):
        read_census_page({"draw": "1", "data": []})


@pytest.mark.parametrize("bad", ["5468", 5468.0, -1, None, True])
def test_records_filtered_must_be_a_non_negative_integer(bad):
    with pytest.raises(CensusShapeError, match="non-negative integer"):
        read_census_page({"recordsFiltered": bad, "data": []})


def test_records_total_is_not_read_as_the_register():
    """It echoes the page length: 20 for `length=20`, 2000 for `length=6000`."""
    declared, _ = read_census_page(
        {"recordsFiltered": 5468, "recordsTotal": 20, "data": []})
    assert declared == 5468


@pytest.mark.parametrize("bad", [None, {}, "rows", 7])
def test_data_must_be_a_list(bad):
    with pytest.raises(CensusShapeError, match="must be a list"):
        read_census_page({"recordsFiltered": 1, "data": bad})


# --- one row's shape -----------------------------------------------------------------

def test_a_row_that_is_not_an_object_raises():
    with pytest.raises(CensusShapeError, match="must be an object"):
        read_office(["OfficeId", "1"])


def test_a_new_field_stops_the_parse_and_names_it():
    """A key the site added is a field nobody has studied."""
    row = _row()
    row["LicenseExpiry"] = "2027-01-01"
    with pytest.raises(CensusShapeError, match="LicenseExpiry"):
        read_office(row)


def test_a_dropped_field_stops_the_parse_and_names_it():
    row = _row()
    del row["X"]
    with pytest.raises(CensusShapeError, match="missing.*'X'"):
        read_office(row)


@pytest.mark.parametrize("key", ["OfficeId", "HashedOfficeId", "OfficeName", "LogoUrl"])
def test_the_four_fields_measured_never_empty_raise_when_empty(key):
    with pytest.raises(CensusShapeError, match=f"{key} is empty"):
        read_office(_row(**{key: ""}))


@pytest.mark.parametrize("key", ["OfficeId", "HashedOfficeId", "OfficeName", "LogoUrl"])
def test_those_four_also_raise_when_they_are_only_whitespace(key):
    with pytest.raises(CensusShapeError, match=f"{key} is empty"):
        read_office(_row(**{key: "   "}))


@pytest.mark.parametrize("key,value", [("ClassificationGrade", 2), ("X", 46.7),
                                       ("MobileNo", ["0500000000"]),
                                       ("OfficeId", 5110001955)])
def test_a_field_that_is_not_a_string_raises(key, value):
    with pytest.raises(CensusShapeError, match=f"{key} is "):
        read_office(_row(**{key: value}))


@pytest.mark.parametrize("key,value", [("ClassificationGrade", 0), ("X", 0.0),
                                       ("MobileNo", []), ("ClassificationStatus", {})])
def test_a_field_that_is_falsy_and_not_a_string_is_refused_not_read_as_absent(key, value):
    """`0` is not `null`. A truthiness test here would file the site's `0` under
    "never said", which is the one reading the study says is wrong: blank, `0` and junk
    are three different things at this source."""
    with pytest.raises(CensusShapeError, match=f"{key} is "):
        read_office(_row(**{key: value}))


def test_the_grade_is_kept_as_text_not_coerced():
    assert read_office(_row(ClassificationGrade="6")).classification_grade == "6"


# --- the detail url ------------------------------------------------------------------

def test_the_detail_url_uses_the_hash_and_not_the_code():
    """The code's own URL form answers 302 to the SSO login."""
    office = read_office(_row(OfficeId="1010251919", HashedOfficeId="bldyPrmABC"))
    url = detail_url(office)
    assert url.endswith("/Details?OfficeId=bldyPrmABC")
    assert "1010251919" not in url


def test_the_detail_url_honours_a_different_base():
    office = read_office(_row())
    assert detail_url(office, base_url="https://staging.example.sa").startswith(
        "https://staging.example.sa/Eservices/")


def test_an_office_with_no_hash_has_no_reachable_detail_page():
    office = read_office(_row())
    hashless = type(office)(**{**office.__dict__, "hashed_office_id": ""})
    with pytest.raises(ValueError, match="reaches only the login page"):
        detail_url(hashless)


# --- what may decide that an office changed --------------------------------------

def test_the_two_volatile_census_fields_are_named():
    """Measured across two responses seconds apart: the hash matched in 0 of 20
    offices and the logo URL in 7, and those seven were the static placeholder."""
    assert VOLATILE_FIELDS == {"HashedOfficeId", "LogoUrl"}


def test_a_fresh_hash_for_the_same_office_is_not_a_change():
    """The endpoint re-encrypts the id on every response. Including it in change
    detection would report all 5,470 offices as edited on every run."""
    first = read_office(_row(HashedOfficeId="bldyPrmAAAA"))
    second = read_office(_row(HashedOfficeId="bldyPrmBBBB"))
    assert first.hashed_office_id != second.hashed_office_id
    assert first.content_fields() == second.content_fields()


def test_a_re_encrypted_logo_url_is_not_a_change():
    """Every real logo URL carries the same per-request ciphertext."""
    base = "/Eservices/Inquiries/InquiryEngOffices/DownloadFile?url=bldyPrm"
    first = read_office(_row(LogoUrl=base + "EE7D0C14"))
    second = read_office(_row(LogoUrl=base + "DBA0E296"))
    assert first.content_fields() == second.content_fields()


def test_losing_the_logo_altogether_IS_a_change():
    """Whether the office uploaded one is the stable half, and it is kept."""
    with_logo = read_office(_row())
    without = read_office(_row(LogoUrl=LOGO_PLACEHOLDER))
    assert with_logo.content_fields() != without.content_fields()
    assert with_logo.content_fields()["has_logo"] == "1"
    assert without.content_fields()["has_logo"] == "0"


@pytest.mark.parametrize("key,value", [
    ("OfficeName", "اسم آخر"), ("ClassificationGrade", "5"),
    ("MobileNo", "0500000000"), ("ClassificationStatus", "غير مصنف"),
    ("X", "46.0"), ("Y", "24.0")])
def test_every_field_the_site_can_really_edit_is_a_change(key, value):
    assert read_office(_row()).content_fields() != read_office(
        _row(**{key: value})).content_fields()


def test_no_volatile_field_leaks_into_the_content():
    content = read_office(_row()).content_fields()
    assert "hashed_office_id" not in content
    assert "logo_url" not in content
    assert set(content) == {"office_id", "office_name", "mobile_no",
                            "classification_grade", "classification_status",
                            "has_logo", "x", "y"}


def test_a_duplicate_does_not_pay_for_an_office_the_sweep_never_read():
    """The completeness guard used to credit duplicates, and that cancels the one
    failure `duplicates_dropped` exists for.

    A register shifting under the offsets returns rows already seen AND misses an equal
    number never seen, so `collected + duplicates` clears a total the sweep never
    reached. Measured against a server that ignores `start` and re-serves the first
    page -- the silent capping this endpoint is documented to do at `balady.py:74-78`
    -- 2,000 offices and 4,000 duplicates passed a declared 5,468: 36.6% of the
    register, returned as a complete sweep.
    """
    page = [_row(OfficeId="1", HashedOfficeId="h1"),
            _row(OfficeId="2", HashedOfficeId="h2")]
    fetcher = _StubFetcher([
        _Resp(_payload(page, declared=4)),
        _Resp(_payload([_row(OfficeId="1", HashedOfficeId="A-FRESH-CIPHERTEXT"),
                        _row(OfficeId="2", HashedOfficeId="ANOTHER-FRESH-ONE")],
                       declared=4)),
    ])
    with pytest.raises(CensusShapeError, match="partly-read"):
        census(fetcher, page_cap=2)


def test_a_register_that_sheds_one_office_mid_sweep_is_still_complete():
    """His ruling: complete against the LAST total the site declared, not the first.

    A register that sheds an office between the first page and the last is not a
    partly-read register, and failing a correct sweep over one deregistration is a
    false alarm that would repeat -- the register moves, which is why `Census` carries
    both totals in the first place.
    """
    fetcher = _StubFetcher([
        _Resp(_payload([_row(OfficeId="1", HashedOfficeId="h1"),
                        _row(OfficeId="2", HashedOfficeId="h2")], declared=3)),
        _Resp(_payload([_row(OfficeId="3", HashedOfficeId="h3")], declared=2)),
    ])
    result = census(fetcher, page_cap=2)

    assert len(result.offices) == 3, result.offices
    assert result.declared_first == 3 and result.declared_last == 2


def test_the_next_offset_follows_the_rows_that_came_back():
    """`start += len(page)`, never `+= page_cap`, and nothing drove the difference.

    The site is documented to cap a page and say nothing about having done so, so a
    server answering 3 rows to a request for 5 must be followed at offset 3. Advancing
    by the ASK instead would skip every row between -- and the completeness guard would
    not see it, because the rows were never read to be counted.
    """
    fetcher = _StubFetcher([
        _Resp(_payload([_row(OfficeId=str(i), HashedOfficeId=f"h{i}") for i in range(3)],
                       declared=10)),
        _Resp(_payload([_row(OfficeId=str(i), HashedOfficeId=f"h{i}") for i in range(3, 10)],
                       declared=10)),
    ])
    result = census(fetcher, page_cap=5)

    assert [post["data"]["start"] for post in fetcher.posts] == ["0", "3"], (
        "the sweep advanced by what it ASKED for rather than by what came back, so the "
        "rows the short page did not carry are never fetched"
    )
    assert len(result.offices) == 10


def test_the_sweep_asks_the_measured_endpoint_at_the_measured_page_size():
    """Nothing asserted what actually went on the wire.

    `BASE_URL`, `CENSUS_PATH`, the default `page_cap` and the `length` the form carries
    could each be changed to something else and the whole suite stayed green -- and a
    smaller default page size is a 274-request sweep where 3 were measured, against
    the politeness budget.
    """
    fetcher = _StubFetcher([_Resp(_payload([_row()], declared=1))])
    census(fetcher)

    # THE LITERAL, NOT THE CONSTANTS. `posts[0]["url"] == BASE_URL + CENSUS_PATH`
    # compares the constants with themselves -- changing either moved both sides and the
    # assertion stayed true, which is how a wrong endpoint survived a suite of 77.
    assert fetcher.posts[0]["url"] == (
        "https://apps.balady.gov.sa/Eservices/Inquiries/InquiryEngOffices/LoadData"
    ), fetcher.posts[0]["url"]
    assert fetcher.posts[0]["data"]["length"] == str(PAGE_CAP), (
        f"the sweep asked for a page of {fetcher.posts[0]['data']['length']} against the "
        f"measured cap of {PAGE_CAP}"
    )


def test_the_census_refuses_to_run_past_its_ceiling():
    """The loop's real bound is the site's own `recordsFiltered`, a remote integer.

    A corrupt or hostile total turns a three-request census into a sustained hammer at
    one request per second, and nothing upstream bounds it -- `connectors/base.py`
    records that the declared request count "is not a budget and nothing here enforces
    it". The ceiling raises rather than returning a short register, because a partial
    read reported as complete is the failure this module exists to refuse.
    """
    fetcher = _StubFetcher([
        _Resp(_payload([_row(OfficeId=str(i), HashedOfficeId=f"h{i}")], declared=10**9))
        for i in range(10)
    ])
    with pytest.raises(CensusShapeError, match="ceiling"):
        census(fetcher, page_cap=1, max_requests=3)

    assert len(fetcher.posts) == 3, (
        f"the ceiling let {len(fetcher.posts)} request(s) through against a limit of 3"
    )


def test_a_hash_the_site_re_mints_cannot_carry_a_query_parameter():
    """The one field in this module that reaches the network comes from the site.

    Raw, an `&` in it appends a second query parameter to a request ScrapeX will make,
    and a `#` truncates the query -- so a DIFFERENT office's page is fetched and
    attributed to this one. The host cannot be escaped, since the base is a literal
    prefix and the value lands after `?`, so this is parameter injection and not an
    open redirect; it is still a request the site chose rather than this product.
    """
    def office(hashed: str) -> Office:
        return read_office(_row(HashedOfficeId=hashed))

    assert "&" not in detail_url(office("x&admin=1")).split("?", 1)[1]
    assert "#" not in detail_url(office("x#frag")).split("?", 1)[1]
    assert " " not in detail_url(office("a b")).split("?", 1)[1]
    assert detail_url(office("bldyPrm0A1B")) == (
        "https://apps.balady.gov.sa/Eservices/Inquiries/InquiryEngOffices/Details"
        "?OfficeId=bldyPrm0A1B"
    ), detail_url(office("bldyPrm0A1B"))


def test_the_two_volatile_sets_name_the_same_two_fields():
    """`VOLATILE_FIELDS` is the wire's names and `VOLATILE_ATTRS` is the model's, and
    `read_office` maps between them by keyword with no mapping to reuse.

    So they are re-typed, the way `datasetjob.COLLECTING_KINDS` is, and pinned here:
    a field that becomes volatile on the wire and not in the model would be hashed into
    change detection and report every office as edited on every run.
    """
    assert len(VOLATILE_ATTRS) == len(VOLATILE_FIELDS), (
        f"the wire names {sorted(VOLATILE_FIELDS)} and the model names "
        f"{sorted(VOLATILE_ATTRS)} are different sizes"
    )
    model_fields = {field.name for field in dataclasses.fields(Office)}
    assert VOLATILE_ATTRS <= model_fields, (
        f"{sorted(VOLATILE_ATTRS - model_fields)} is excluded from change detection and "
        f"is not a field of Office"
    )
    assert not (VOLATILE_ATTRS & set(read_office(_row()).content_fields())), (
        "a volatile field reached change detection"
    )


def test_a_field_added_to_the_model_joins_change_detection():
    """`content_fields()` hand-listed its eight keys, so a new field escaped change
    detection in silence -- and the test that looked like a guard asserted a literal
    set, which stays true when a field is added.

    Derived from the dataclass now, so this asserts the RULE rather than the list.
    """
    office = read_office(_row())
    content = office.content_fields()
    expected = {field.name for field in dataclasses.fields(Office)
                if field.name not in VOLATILE_ATTRS} | {"has_logo"}

    assert set(content) == expected, (
        f"change detection and the model disagree about which fields count: "
        f"only in content {sorted(set(content) - expected)}, "
        f"only in the model {sorted(expected - set(content))}"
    )
    assert content["office_id"] == office.office_id, (
        "content_fields reported a constant rather than the office's own value"
    )
