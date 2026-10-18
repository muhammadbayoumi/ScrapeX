"""TVTC's licensed-establishments register, both language views, as one candidate table.

`scrapex/sites/tvtc.py` reads a page; this turns a pair of them into the rows
`generic_record` stores -- muqawil's and Oman's split, for their reason.

OMAN'S THREE LESSONS HOLD HERE UNCHANGED (`extract/oman_tenderboard.py`): the field list is
DECLARED and its order FIXED, `nullable` is always True, and every field is on every row.

WHAT THE TWO VIEWS ADD TO EACH OTHER, MEASURED (`#1716`): the English view changes exactly
two values, `establishment_type.name` and `city.name` -- `region.name` stays Arabic in it --
so those two get an `_en` twin and nothing else does. Everything else bilingual is already
bilingual inside one response (`name`/`name_en`, `violation.description_ar/_en`,
`week_day_ar/_en`) and is read from the Arabic view.

EVERY VALUE IS STORED AS THE SITE SENT IT, AS TEXT: a date stays its `YYYY-MM-DD` string, a
coordinate its decimal string, a boolean `true`/`false`. The census found no Arabic-Indic
digit in any numeric field. THE ONE VALUE READ RATHER THAN COPIED is a working-hours time,
whose date part is the fetch's own (`_clock`); its digits are folded by `normalize`.

EVERY PATH IS READ STRICTLY (`_at`). A key this reader names that the row no longer carries,
or an object that arrives as something else, refuses the page by name -- never a column of
NULLs that reads as "no violation" or "no owner". An absent object is `None` or `[]`, the two
forms the register was measured to publish for one; see `_at`.

THE OWNER AND THE INVESTOR ARE STORED. His ruling on `#1716` Q1: the site's own search
answers to the owner's ID number, and what reaches mbiX is reviewed separately.

WHAT IS DELIBERATELY NOT STORED, each with its reason:

  * `file.url` -- a 30-minute pre-signed S3 URL; stored, it is a dead link by morning.
    `logo_path` keeps the object's stable path.
  * `activity_title_list` -- it repeats `establishment_type`: 3,022 of 3,022 rows agree.
  * `region` inside `city` -- it repeats `region`: 3,139 of 3,139 agree.
  * `violation.penalty.color`, `.type` and the attachment's own metadata beyond its path
    -- presentation and storage bookkeeping, not facts about the establishment.

A KEY THE SITE ADDS IS STILL KEPT, in ONE column, `unknown_keys`, as a JSON object, and named
in the candidate's warnings. One column and not one per key, because a key's own name is
the site's to choose and the catalog's to refuse: `workingHours` already shows camelCase,
which `ApprovalField`'s pattern rejects, a key named like a declared column would collide,
and fourteen of them would pass `MAX_TABLE_COLUMNS`. Each of those refused EVERY page.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from .. import normalize
from ..extract.html_table import InferredField, TableCandidate
from ..sites.tvtc import read_page

DATASET_KEY = "tvtc_training_establishments"
DATASET_NAME = "TVTC licensed training establishments"

#: The site's own id, which is also the licence number printed on the licence PDF.
IDENTITY_FIELD = "establishment_id"


def _text(value: Any) -> str | None:
    """The site's value as text, `None` for absent or blank."""
    if value is None or value == "" or value == [] or value == {}:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


class RowShapeError(ValueError):
    """A row is not the shape this reader was written against: a key it reads is gone, or
    an object arrived as something else. The page is refused and named, never stored as
    empty columns."""


def _at(row: dict[str, Any], *path: str) -> Any:
    """The value at `path`, read strictly.

    AN ABSENT OBJECT IS `None` OR `[]`, AND NOTHING ELSE -- both measured over the census of
    3,141 rows in both views: `violation`, `file`, `city` and `establishment_type` arrive
    as `null` when absent, and `region` on its one region-less row as `[]`, an empty PHP
    array. A NON-EMPTY list where an object is read is refused: that is a one-to-one
    relation turned one-to-many, the day an establishment gets its second violation.
    """
    value: Any = row
    walked: list[str] = []
    for key in path:
        if value is None or value == []:
            return None
        if not isinstance(value, dict):
            raise RowShapeError(
                f"{'.'.join(walked)} is a {type(value).__name__}, not an object")
        if key not in value:
            raise RowShapeError(f"{'.'.join([*walked, key])} is missing from the row")
        value = value[key]
        walked.append(key)
    return value


Getter = Callable[[dict[str, Any], dict[str, Any]], Any]


def _ar(*path: str) -> Getter:
    return lambda arabic, english: _at(arabic, *path)


def _en(*path: str) -> Getter:
    return lambda arabic, english: _at(english, *path)


def _activity_code(arabic: dict[str, Any], english: dict[str, Any]) -> Any:
    """The activity code(s), comma-joined. One code on 3,130 of 3,141 census rows and two
    on none -- joined rather than JSON-wrapped so the one value reads as itself."""
    codes = _at(arabic, "activity_list")
    if codes is None:
        return None
    if not isinstance(codes, list) or not all(
            isinstance(code, int) and not isinstance(code, bool) for code in codes):
        raise RowShapeError(f"activity_list reads {codes!r}, not a list of integer codes")
    return ",".join(str(code) for code in codes) or None


#: `2026-10-17T08:00:00.000000Z`: the date part is THE DAY THE PAGE WAS FETCHED, not a
#: fact -- every time on a page carried that day's date -- so it is dropped, and only the
#: clock is kept. The `Z` is not believed either: 08:00-22:00 reads as local opening
#: hours, and the site states no zone it can be checked against. Kept as written: `HH:MM`,
#: and `HH:MM:SS` when the seconds are not zero, so nothing the site said is dropped.
#: `[0-9]` and not `\d`, which in Python also matches Arabic-Indic digits: those are folded
#: by `normalize.fold_digits` first, so the stored clock is always ASCII.
_CLOCK = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T([0-9]{2}:[0-9]{2}):([0-9]{2})(?:\.[0-9]+)?Z")


class WorkingHoursShapeError(ValueError):
    """A working-hours entry is not the shape this reader was written against."""


def _clock(value: Any) -> str:
    match = (_CLOCK.fullmatch(normalize.fold_digits(value))
             if isinstance(value, str) else None)
    if match is None:
        raise WorkingHoursShapeError(f"a working-hours time reads {value!r}")
    clock, seconds = match.groups()
    return clock if seconds == "00" else f"{clock}:{seconds}"


def _working_hours(arabic: dict[str, Any], english: dict[str, Any]) -> Any:
    """The week as a JSON list of `{day_ar, day_en, start, end}`, without the fetch date.

    WHY THE DATE MUST GO: stored whole, every one of the 781 establishments that publish
    hours would read as CHANGED on every crawl, because the date is the crawl's own.
    """
    # `None` IS THE ONLY ABSENCE, tested before the type: `or []` let `false`, `""`, `0` and
    # `{}` pass as "no hours", and an establishment that publishes hours lost them silently.
    days = _at(arabic, "workingHours")
    if days is None:
        days = []
    if not isinstance(days, list):
        raise WorkingHoursShapeError(f"workingHours is a {type(days).__name__}")
    week = []
    for day in days:
        if not isinstance(day, dict):
            raise WorkingHoursShapeError(f"a workingHours entry is a {type(day).__name__}")
        try:
            week.append({"day_ar": day["week_day_ar"], "day_en": day["week_day_en"],
                         "start": _clock(day["start_time"]),
                         "end": _clock(day["end_time"])})
        except KeyError as missing:
            raise WorkingHoursShapeError(f"a workingHours entry has no {missing}") from None
    return week


#: DECLARED AND ORDERED: (column, how it is read). The order is the plan `#1716` approved.
COLUMNS: tuple[tuple[str, Getter], ...] = (
    ("establishment_id", _ar("id")),
    ("name_ar", _ar("name")),
    ("name_en", _ar("name_en")),
    ("charity_name", _ar("charity_name")),
    ("establishment_type_id", _ar("establishment_type", "id")),
    ("establishment_type_ar", _ar("establishment_type", "name")),
    ("establishment_type_en", _en("establishment_type", "name")),
    ("activity_code", _activity_code),
    ("gender", _ar("gender")),
    ("region_id", _ar("region", "id")),
    ("region_code", _ar("region", "code")),
    ("region_ar", _ar("region", "name")),
    ("city_id", _ar("city", "id")),
    ("city_code", _ar("city", "code")),
    ("city_ar", _ar("city", "name")),
    ("city_en", _en("city", "name")),
    ("parent_city_id", _ar("city", "parent_city_id")),
    ("district", _ar("district")),
    ("street_name", _ar("street_name")),
    ("address", _ar("address")),
    ("building_number", _ar("building_number")),
    ("alternative_building_number", _ar("alternative_building_number")),
    ("zip_code", _ar("zip_code")),
    ("postal_office_box_number", _ar("postal_office_box_number")),
    ("latitude", _ar("latitude")),
    ("longitude", _ar("longitude")),
    ("phone", _ar("phone")),
    ("mobile", _ar("mobile")),
    ("fax", _ar("fax")),
    ("email", _ar("email")),
    ("website", _ar("website")),
    # TWO IDENTIFIERS, NOT ONE STATED TWICE: they differ on 1,002 of 2,945 rows, where
    # `cr_number` is an old city CR and the other the 7-prefixed unified number.
    ("cr_number", _ar("cr_number")),
    ("commercial_record_number", _ar("commercial_record_number")),
    ("commercial_record_national_number", _ar("commercial_record_national_number")),
    ("commercial_record_main_number", _ar("commercial_record_main_number")),
    ("commercial_record_date", _ar("commercial_record_date")),
    ("commercial_record_expiry_date", _ar("commercial_record_expiry_date")),
    ("commercial_record_issue_place", _ar("commercial_record_issue_place")),
    ("municipal_certificate_number", _ar("municipal_certificate_number")),
    ("municipal_certificate_date", _ar("municipal_certificate_date")),
    ("municipal_certificate_expiry_date", _ar("municipal_certificate_expiry_date")),
    ("postal_certificate_date", _ar("postal_certificate_date")),
    ("postal_certificate_expiry_date", _ar("postal_certificate_expiry_date")),
    ("defense_certificate", _ar("defense_certificate")),
    ("defense_certificate_expiry_date", _ar("defense_certificate_expiry_date")),
    ("charity_record_number", _ar("charity_record_number")),
    ("charity_record_expiry_date", _ar("charity_record_expiry_date")),
    ("charity_registration_place", _ar("charity_registration_place")),
    ("trainees_capacity", _ar("trainees_capacity")),
    # The site states no unit.
    ("area_size", _ar("area_size")),
    # A code the site does not explain: 1, H, 2, S, 3.
    ("calendar_type", _ar("calendar_type")),
    ("is_currently_suspended", _ar("is_currently_suspended")),
    ("can_add_trainee", _ar("can_add_trainee")),
    ("suspension_message", _ar("suspension_message")),
    ("violation_id", _ar("violation", "id")),
    ("violation_number", _ar("violation", "number")),
    ("violation_ar", _ar("violation", "description_ar")),
    ("violation_en", _ar("violation", "description_en")),
    ("violation_penalty_code", _ar("violation", "penalty", "code")),
    ("violation_penalty_ar", _ar("violation", "penalty", "description_ar")),
    ("violation_penalty_en", _ar("violation", "penalty", "description_en")),
    ("violation_penalty_grade", _ar("violation", "penalty", "grade")),
    ("violation_attachment_path", _ar("violation", "attachment", "path")),
    ("violation_is_stopped", _ar("violation", "is_stopped")),
    ("violation_status", _ar("violation", "status")),
    ("violation_end_reason", _ar("violation", "end_reason")),
    ("violation_note", _ar("violation", "note")),
    ("skip_momra", _ar("skip_momra")),
    ("skip_momra_reason", _ar("skip_momra_reason")),
    ("skip_momra_at", _ar("skip_momra_at")),
    ("notes", _ar("notes")),
    ("working_hours", _working_hours),
    ("logo_path", _ar("file", "path")),
    ("logo_filename", _ar("file", "filename")),
    ("logo_file_type", _ar("file", "type")),
    ("attachment", _ar("attachment")),
    # This system's record date, not the licence date (range 2026-02-09 .. 2026-10-16).
    ("created_at", _ar("created_at")),
    ("owner_full_name", _ar("owner", "owner_full_name")),
    ("owner_id_number", _ar("owner", "owner_id_number")),
    ("owner_mobile", _ar("owner", "owner_mobile_no")),
    ("owner_nationality", _ar("owner", "owner_national_name")),
    ("investor_name", _ar("investor", "investor_name")),
    ("investor_id_number", _ar("investor", "investor_identification_number")),
    ("investor_mobile", _ar("investor", "investor_mobile_number")),
    ("investor_email", _ar("investor", "investor_email")),
    ("investor_nationality", _ar("investor", "investor_nationality_name")),
    ("investor_position", _ar("investor", "investor_position_user")),
    # LAST, so a key the register adds never moves a declared column; filled by
    # `bilingual_listing_candidate`. See the module docstring.
    ("unknown_keys", lambda arabic, english: None),
)
FIELDS: tuple[str, ...] = tuple(name for name, _ in COLUMNS)

#: Every top-level key the register published when this was written. One outside this
#: set, from either view, is kept in the `unknown_keys` column; see the module docstring.
KNOWN_KEYS = frozenset({
    "id", "name", "name_en", "notes", "skip_momra", "skip_momra_reason", "skip_momra_at",
    "charity_name", "phone", "cr_number", "fax", "mobile", "zip_code",
    "postal_office_box_number", "email", "website", "address", "district", "street_name",
    "building_number", "gender", "calendar_type", "commercial_record_number",
    "commercial_record_national_number", "commercial_record_date",
    "commercial_record_issue_place", "charity_registration_place",
    "commercial_record_expiry_date", "defense_certificate_expiry_date",
    "municipal_certificate_expiry_date", "municipal_certificate_number",
    "postal_certificate_expiry_date", "postal_certificate_date", "municipal_certificate_date",
    "commercial_record_main_number", "charity_record_number", "charity_record_expiry_date",
    "defense_certificate", "trainees_capacity", "latitude", "longitude", "area_size", "city",
    "region", "file", "activity_list", "activity_title_list", "establishment_type",
    "workingHours", "violation", "owner", "investor", "can_add_trainee",
    "suspension_message", "alternative_building_number", "is_currently_suspended",
    "attachment", "created_at",
})


class LanguagesDisagree(ValueError):
    """The English and Arabic copies of one page do not hold the same establishments."""


def _pairs(english_body: str, arabic_body: str) -> tuple[tuple[dict, dict], ...]:
    """Each Arabic row with its English twin, joined on `id` IN PUBLISHED ORDER.

    REFUSED WHEN THE TWO VIEWS DIFFER, rather than joined on what they share: the two
    copies of a page are fetched seconds apart, and an establishment added between them
    shifts every row after it. A half-joined page would store rows whose `_en` columns
    came from a neighbour, so the page is refused. NOTHING FETCHES IT AGAIN: the crawl has
    closed by the time approval runs, so that page's rows keep their previous values until
    the next crawl, and the refusal is named in the approval log.
    """
    if not english_body or not arabic_body:
        raise LanguagesDisagree("one language copy of this page is missing")
    arabic, english = read_page(arabic_body).rows, read_page(english_body).rows
    ids_ar = [str(row["id"]) for row in arabic]
    ids_en = [str(row["id"]) for row in english]
    if ids_ar != ids_en:
        only_ar = sorted(set(ids_ar) - set(ids_en))[:5]
        only_en = sorted(set(ids_en) - set(ids_ar))[:5]
        raise LanguagesDisagree(
            f"the two copies hold different establishments (Arabic only: {only_ar}, "
            f"English only: {only_en}, or the same ids in another order)")
    _assert_two_languages(arabic, english)
    return tuple(zip(arabic, english, strict=True))


_ARABIC_SCRIPT = re.compile(r"[؀-ۿ]")


def _assert_two_languages(arabic: tuple[dict, ...], english: tuple[dict, ...]) -> None:
    """Refuse a pair whose two copies are not the Arabic and the English view.

    THE LANGUAGE TRAVELS IN `locale=` ALONE, and `lang=` was measured to be ignored
    silently (`sites/tvtc.py`). Were `locale=ar` ignored too, the "Arabic" copy would come
    back English, and `establishment_type_ar` and `city_ar` would store English on every
    row of a page that approves. Measured over the census: every Arabic type name carries
    Arabic script, and on 0 of 3,141 rows are the two views' type and city equal. So the
    Arabic copy must carry Arabic script in its type or city names, and the English copy
    must not carry it in all of them. A swapped pair fails both.
    """
    def names(rows: tuple[dict, ...]) -> list[str]:
        found = []
        for row in rows:
            for path in (("establishment_type", "name"), ("city", "name")):
                value = _at(row, *path)
                if isinstance(value, str) and value.strip():
                    found.append(value)
        return found

    in_arabic, in_english = names(arabic), names(english)
    if in_arabic and not any(_ARABIC_SCRIPT.search(name) for name in in_arabic):
        raise LanguagesDisagree(
            "the Arabic copy carries no Arabic script in any type or city name, so the "
            "site answered `locale=ar` in another language")
    if in_english and all(_ARABIC_SCRIPT.search(name) for name in in_english):
        raise LanguagesDisagree(
            "the English copy carries Arabic script in every type and city name, so the "
            "site answered `locale=en` in Arabic")


def _uniqueness(rows: tuple[dict[str, str | None], ...], name: str) -> float:
    present = [row.get(name) for row in rows if row.get(name)]
    return len(set(present)) / len(present) if present else 0.0


def bilingual_listing_candidate(english_body: str, arabic_body: str, *,
                                table_index: int = 0,
                                locator: str = "licensed-establishments") -> TableCandidate:
    """One page of the register, both languages, as a candidate table."""
    rows = []
    extra: set[str] = set()
    for arabic, english in _pairs(english_body, arabic_body):
        row = {name: _text(read(arabic, english)) for name, read in COLUMNS}
        # EITHER VIEW'S NEW KEYS, the Arabic value first: a key only the English view
        # carries is still news.
        unknown = {key: arabic[key] if key in arabic else english[key]
                   for key in sorted((set(arabic) | set(english)) - KNOWN_KEYS)}
        row["unknown_keys"] = _text(unknown)
        extra.update(unknown)
        rows.append(row)
    names = list(FIELDS)
    rows_out = tuple({name: row.get(name) for name in names} for row in rows)
    fields = tuple(
        InferredField(
            field_key=name, source_name=name, data_type="text",
            # Always True, never measured -- see the module docstring.
            nullable=True, position=position, confidence=1.0,
            uniqueness=_uniqueness(rows_out, name),
            null_fraction=(sum(1 for row in rows_out if not row.get(name)) / len(rows_out)
                           if rows_out else 1.0),
            identity_candidate=(name == IDENTITY_FIELD),
        )
        for position, name in enumerate(names)
    )
    return TableCandidate(
        table_index=table_index, name=DATASET_NAME, locator=locator, fields=fields,
        rows=rows_out, confidence=1.0,
        warnings=tuple(f"the register added a key this reader does not know: {key}"
                       for key in sorted(extra)),
        approvable=bool(rows_out), truncated=False,
    )
