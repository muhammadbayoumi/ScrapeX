"""TVTC's training plans, both language views, as one candidate table.

The second listing of the register `extract/tvtc.py` reads: one row per (establishment,
licensed training plan), 41,694 rows on 2026-10-18. Its reading rules are that module's,
imported rather than restated -- every path read strictly (`_at`), every value stored as
the site sent it (`_text`), the two views joined on `id` in published order and refused
unless they are two languages (`_pairs`) -- because they are one register's one shape and
would change together.

WHAT THE TWO VIEWS ADD TO EACH OTHER, MEASURED over the census of 41,694 rows (#1749's
review): the English view changes `status.label`, `training_plan.classification_status` and
`training_plan.modality.name`, so those three get an `_en` twin. It also changes
`program_type.name` (read instead from `name_ar`/`name_en`, which both views carry) and two
`status_value` labels this module does not store. The English `classification_status` is
the site's own untranslated key -- `training_plans.program_classification.not_classified`.

THE `_en` NAME FIELDS ARE STORED AS THE SITE SENDS THEM, AND THE SITE OFTEN SENDS ARABIC IN
THEM: `training_program.name_en` carries Arabic script on 28,318 of 41,689 filled rows and
equals `name` on 29,764; `domain.name_en` on 3,809 and `specialization.name_en` on 603.
`program_en` is therefore not an English name on most rows -- it is what the site put in
its English field. `training_program` has no `name_ar`; `program_ar` is its `name`.

THE OBJECTS EVERY ROW CARRIES ARE REQUIRED (`REQUIRED_OBJECTS`). `_at` reads `None` and `[]`
as an absent object, which is right for `domain` (null on 56 rows), the activation
(`establishment_training_plan`, null on 36,622) and `cooperative_hours` (`[]` on 39,819) --
but `establishment`, `status`, `training_plan` and five more are objects on 41,694 of 41,694
rows, and one arriving empty would be a mostly-NULL row whose join key is gone. So it
refuses the page by name instead.

THE ACTIVATION CAN BELONG TO ANOTHER ESTABLISHMENT, AND THAT IS STORED, NOT HIDDEN (his
ruling on #1749): on 59 of the 5,072 rows that carry one, its `establishment_id` is not the
row's. `establishment_training_plan_id` and `activation_establishment_id` are kept beside
the activation columns, so the mismatch is visible as a comparison of two columns.

WHAT IS DELIBERATELY NOT STORED:

  * The establishment nested in every row, ~110 keys repeated per plan: only its `id` is
    kept, the join to `tvtc_training_establishments`, which holds the rest.
  * `establishment.license` -- it belongs to the establishment, not to the plan (24 of 24
    establishments on a 1,000-row page carried one licence however many plans), and
    `#1716` step 3 moves it to the establishments table.
  * `training_program.description/objective/enrollment_requirements/minimum_trainee_age`,
    `domain.saudi_major_codes`, `show_export_pdf`, `can_edit_professional_certificate`,
    `class_type`, `accessibility_certificate_end_date` -- null on 41,694 of 41,694 rows, or
    UI switches. The seven the census found filled (`audience`, `semester_duration`,
    `total_exercise_hours`, the parent plan, `number_approved_units`, the activation's
    `created_at` and `program_classification`) are columns, by his ruling on #1749.

`product.price` IS STORED AS THE SITE STATES IT and is not rendered on the site; what it
is the price of is unproved (`#1716` §6), so it is a number named what the site names it.

A KEY THE SITE ADDS, at the top level of a row or of its `training_plan`, is kept in
`unknown_keys` and named in the warnings -- `extract/tvtc.py`'s rule, for its reason.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..extract.html_table import InferredField, TableCandidate
from .tvtc import RowShapeError, _ar, _at, _en, _pairs, _text, _uniqueness

DATASET_KEY = "tvtc_training_plans"
DATASET_NAME = "TVTC licensed training plans"

#: The row's own id: one (establishment, plan) licensing. 1,000 of 1,000 distinct.
IDENTITY_FIELD = "establishment_plan_id"

#: The names whose script tells the two views apart, for a plans row: `نشط`/`Active`,
#: `حضوري`/`In class`, measured on 20 of 20 rows.
LANGUAGE_PATHS: tuple[tuple[str, ...], ...] = (
    ("status", "label"), ("training_plan", "modality", "name"))

Getter = Callable[[dict[str, Any], dict[str, Any]], Any]
TP = "training_plan"
PROGRAM = (TP, "training_program")
ACTIVATION = (TP, "establishment_training_plan")

#: Objects on 41,694 of 41,694 census rows in both views; see the module docstring.
REQUIRED_OBJECTS: tuple[tuple[str, ...], ...] = (
    ("establishment",), ("status",), (TP,), PROGRAM, (*PROGRAM, "program_type"),
    (*PROGRAM, "specialization"), (TP, "modality"), (TP, "product"))


def _assert_required_objects(row: dict[str, Any]) -> None:
    for path in REQUIRED_OBJECTS:
        value = _at(row, *path)
        if not isinstance(value, dict) or not value:
            raise RowShapeError(
                f"{'.'.join(path)} is {value!r}, but every plan row carries it as an object")


#: DECLARED AND ORDERED: the plan `#1716` approved, with the three measured `_en` twins.
COLUMNS: tuple[tuple[str, Getter], ...] = (
    ("establishment_plan_id", _ar("id")),
    ("establishment_id", _ar("establishment", "id")),
    ("plan_id", _ar(TP, "id")),
    ("plan_name", _ar(TP, "name")),
    ("status", _ar("status", "value")),
    ("status_label_ar", _ar("status", "label")),
    ("status_label_en", _en("status", "label")),
    ("enabled", _ar(TP, "enabled")),
    ("is_draft", _ar(TP, "is_draft")),
    ("accreditation_status", _ar(TP, "accreditation_status")),
    ("classification_status_ar", _ar(TP, "classification_status")),
    ("classification_status_en", _en(TP, "classification_status")),
    ("version_code", _ar(TP, "version_code")),
    ("training_plan_code", _ar(TP, "training_plan_code")),
    ("request_id", _ar(TP, "request_id")),
    ("language", _ar(TP, "language")),
    ("parent_id", _ar(TP, "parent_id")),
    ("parent_plan_id", _ar(TP, "id_training_plan_parent")),
    # An object on 6 of 41,694 rows, as JSON text: what the site says the parent is.
    ("parent_plan", _ar(TP, "trainingPlanParent")),
    ("target_group_id", _ar(TP, "training_plan_target_group_id")),
    ("program_id", _ar(*PROGRAM, "id")),
    ("program_ar", _ar(*PROGRAM, "name")),
    ("program_en", _ar(*PROGRAM, "name_en")),
    ("program_type_id", _ar(*PROGRAM, "program_type", "id")),
    ("program_type_ar", _ar(*PROGRAM, "program_type", "name_ar")),
    ("program_type_en", _ar(*PROGRAM, "program_type", "name_en")),
    ("program_is_short", _ar(*PROGRAM, "program_type", "is_short")),
    ("program_is_development", _ar(*PROGRAM, "program_type", "is_development")),
    ("domain_id", _ar(*PROGRAM, "domain", "id")),
    ("domain_number", _ar(*PROGRAM, "domain", "domain_number")),
    ("domain_ar", _ar(*PROGRAM, "domain", "name_ar")),
    ("domain_en", _ar(*PROGRAM, "domain", "name_en")),
    ("specialization_id", _ar(*PROGRAM, "specialization", "id")),
    ("specialization_ar", _ar(*PROGRAM, "specialization", "name_ar")),
    ("specialization_en", _ar(*PROGRAM, "specialization", "name_en")),
    ("specialization_number", _ar(TP, "specialization_number")),
    ("exam_number", _ar(TP, "exam_number")),
    ("modality_id", _ar(TP, "modality", "id")),
    ("modality_ar", _ar(TP, "modality", "name_ar")),
    ("modality_en", _en(TP, "modality", "name")),
    ("assessor_modality_id", _ar(TP, "assessor_modality_id")),
    ("remote_training_enabled", _ar(TP, "remote_training_enabled")),
    ("qualification_level", _ar(TP, "qualification_level")),
    ("qualification_title", _ar(TP, "qualification_title")),
    ("is_professional_certificate", _ar(TP, "is_professional_certificate")),
    ("program_description", _ar(TP, "program_description")),
    ("program_main_objective", _ar(TP, "program_main_objective")),
    ("program_audience", _ar(*PROGRAM, "audience")),
    ("total_hours", _ar(TP, "total_hours")),
    ("total_credits", _ar(TP, "total_credits")),
    ("total_days", _ar(TP, "total_days")),
    ("days", _ar(TP, "days")),
    ("months", _ar(TP, "months")),
    ("semesters", _ar(TP, "semesters")),
    ("semester_duration", _ar(TP, "semester_duration")),
    ("hours_per_day", _ar(TP, "number_of_trainingHours_day")),
    ("hours_in_class", _ar(TP, "hours_in_class")),
    ("hours_online_sync", _ar(TP, "hours_online_synchronize")),
    ("hours_online_async", _ar(TP, "hours_online_non_synchronize")),
    ("total_lecture_hours", _ar(TP, "total_lecture_hours")),
    ("total_practical_hours", _ar(TP, "total_practical_hours")),
    ("total_exercise_hours", _ar(TP, "total_exercise_hours")),
    ("total_contact_hours", _ar(TP, "total_contact_hours")),
    ("calendar_type", _ar(TP, "calendar_type")),
    ("cooperative_semester_exists", _ar(TP, "cooperative_semester_exists")),
    # `cooperative_hours` is `[]` on 89 of 100 measured rows and an object on 11; `_at`
    # reads the `[]` as an absent object.
    ("cooperative_call_hours", _ar(TP, "cooperative_hours", "number_call_hours")),
    ("cooperative_weeks", _ar(TP, "cooperative_hours", "number_weeks")),
    ("cooperative_approved_units", _ar(TP, "cooperative_hours", "number_approved_units")),
    ("trainee_age", _ar(TP, "trainee_age")),
    ("number_of_trainers", _ar(TP, "number_of_trainers")),
    ("number_of_supervisors", _ar(TP, "number_of_supervisors")),
    ("capacity", _ar(TP, "capacity")),
    ("product_id", _ar(TP, "product", "id")),
    ("product_name", _ar(TP, "product", "name")),
    ("product_price", _ar(TP, "product", "price")),
    # WHOSE ACTIVATION THIS IS: its own id and establishment, beside the row's -- they
    # differ on 59 rows (see the module docstring).
    ("establishment_training_plan_id", _ar(*ACTIVATION, "id")),
    ("activation_establishment_id", _ar(*ACTIVATION, "establishment_id")),
    ("is_active_online", _ar(TP, "establishment_training_plan", "is_active_online")),
    ("is_active_in_class", _ar(TP, "establishment_training_plan", "is_active_in_class")),
    ("is_active_hybrid", _ar(TP, "establishment_training_plan", "is_active_hybrid")),
    ("establishment_plan_status", _ar(TP, "establishment_training_plan", "status")),
    ("frozen_at", _ar(TP, "establishment_training_plan", "frozen_at")),
    ("plan_updated_at", _ar(TP, "establishment_training_plan", "updated_at")),
    ("activation_created_at", _ar(*ACTIVATION, "created_at")),
    ("activation_program_classification", _ar(*ACTIVATION, "program_classification")),
    ("accessibility_certificate_no", _ar(TP, "accessibility_certificate_no")),
    # LAST, so a key the register adds never moves a declared column.
    ("unknown_keys", lambda arabic, english: None),
)
FIELDS: tuple[str, ...] = tuple(name for name, _ in COLUMNS)

#: The keys a row published when this was written, at its top level and in its
#: `training_plan` -- the two levels a new key is looked for at.
KNOWN_KEYS = frozenset({"establishment", "id", "status", "training_plan"})
KNOWN_PLAN_KEYS = frozenset({
    "accessibility_certificate_end_date", "accessibility_certificate_no",
    "accreditation_status", "assessor_modality_id", "calendar_type",
    "can_edit_professional_certificate", "capacity", "class_type", "classification_status",
    "cooperative_hours", "cooperative_semester_exists", "days", "enabled",
    "establishment_training_plan", "exam_number", "hours_in_class",
    "hours_online_non_synchronize", "hours_online_synchronize", "id",
    "id_training_plan_parent", "is_draft", "is_professional_certificate", "language",
    "modality", "months", "name", "number_of_supervisors", "number_of_trainers",
    "number_of_trainingHours_day", "parent_id", "product", "program_description",
    "program_main_objective", "qualification_level", "qualification_title",
    "remote_training_enabled", "request_id", "semester_duration", "semesters",
    "show_export_pdf", "specialization_number", "total_contact_hours", "total_credits",
    "total_days", "total_exercise_hours", "total_hours", "total_lecture_hours",
    "total_practical_hours", "trainee_age", "trainingPlanParent", "training_plan_code",
    "training_plan_target_group_id", "training_program", "version_code",
})


def _unknown(arabic: dict[str, Any], english: dict[str, Any]) -> dict[str, Any]:
    """Either view's new keys, the Arabic value first; plan-level ones as `training_plan.x`."""
    found = {key: arabic[key] if key in arabic else english[key]
             for key in (set(arabic) | set(english)) - KNOWN_KEYS}
    plan_ar = _at(arabic, TP) or {}
    plan_en = _at(english, TP) or {}
    found.update({f"{TP}.{key}": plan_ar[key] if key in plan_ar else plan_en[key]
                  for key in (set(plan_ar) | set(plan_en)) - KNOWN_PLAN_KEYS})
    return dict(sorted(found.items()))


def bilingual_listing_candidate(english_body: str, arabic_body: str, *,
                                table_index: int = 0,
                                locator: str = "licensed-establishments/plans",
                                ) -> TableCandidate:
    """One page of the plans listing, both languages, as a candidate table."""
    rows = []
    extra: set[str] = set()
    for arabic, english in _pairs(english_body, arabic_body, language_paths=LANGUAGE_PATHS):
        _assert_required_objects(arabic)
        _assert_required_objects(english)
        row = {name: _text(read(arabic, english)) for name, read in COLUMNS}
        unknown = _unknown(arabic, english)
        row["unknown_keys"] = _text(unknown)
        extra.update(unknown)
        rows.append(row)
    rows_out = tuple({name: row.get(name) for name in FIELDS} for row in rows)
    fields = tuple(
        InferredField(
            field_key=name, source_name=name, data_type="text",
            nullable=True, position=position, confidence=1.0,
            uniqueness=_uniqueness(rows_out, name),
            null_fraction=(sum(1 for row in rows_out if not row.get(name)) / len(rows_out)
                           if rows_out else 1.0),
            identity_candidate=(name == IDENTITY_FIELD),
        )
        for position, name in enumerate(FIELDS)
    )
    return TableCandidate(
        table_index=table_index, name=DATASET_NAME, locator=locator, fields=fields,
        rows=rows_out, confidence=1.0,
        warnings=tuple(f"the register added a key this reader does not know: {key}"
                       for key in sorted(extra)),
        approvable=bool(rows_out), truncated=False,
    )


# --- the licence, kept once per establishment -- ES-5 ------------------------------------

LICENCE_DATASET_KEY = "tvtc_establishment_licences"
LICENCE_DATASET_NAME = "TVTC establishment licences"
#: The licence depends on the establishment alone: across the census, 0 of the 2,145
#: establishments the plans listing carries showed two different licences over their plans.
LICENCE_IDENTITY_FIELD = "establishment_id"

LICENCE = ("establishment", "license")

#: DECLARED AND ORDERED: every key the census's 2,145 licences carry, as the site sends it.
#: `date_gregorian`/`date_hijri` are the site's own "start / end" strings, stored as stated
#: beside the dates they combine; nothing is derived here.
LICENCE_COLUMNS: tuple[tuple[str, Getter], ...] = (
    ("establishment_id", _ar("establishment", "id")),
    ("license_id", _ar(*LICENCE, "id")),
    ("license_id_encrypt", _ar(*LICENCE, "id_encrypt")),
    ("ref_license", _ar(*LICENCE, "ref_license")),
    ("start_date", _ar(*LICENCE, "start_date")),
    ("end_date", _ar(*LICENCE, "end_date")),
    ("start_date_hijri", _ar(*LICENCE, "start_date_hijri")),
    ("end_date_hijri", _ar(*LICENCE, "end_date_hijri")),
    ("date_gregorian", _ar(*LICENCE, "date_gregorian")),
    ("date_hijri", _ar(*LICENCE, "date_hijri")),
    ("license_status", _ar(*LICENCE, "license_status")),
    ("license_status_label_ar", _ar(*LICENCE, "license_status_label")),
    # The one licence value the English view changes, measured on the plans census.
    ("license_status_label_en", _en(*LICENCE, "license_status_label")),
    ("is_license_expired", _ar(*LICENCE, "is_license_expired")),
    ("request_status", _ar(*LICENCE, "request_status")),
    ("link_pdf_license", _ar(*LICENCE, "link_pdf_license")),
    ("unknown_keys", lambda arabic, english: None),
)
LICENCE_FIELDS: tuple[str, ...] = tuple(name for name, _ in LICENCE_COLUMNS)
KNOWN_LICENCE_KEYS = frozenset({
    "id", "id_encrypt", "ref_license", "start_date", "end_date", "start_date_hijri",
    "end_date_hijri", "date_gregorian", "date_hijri", "license_status",
    "license_status_label", "is_license_expired", "request_status", "link_pdf_license",
})


def licence_candidate(english_body: str, arabic_body: str, *, table_index: int = 0,
                      locator: str = "licensed-establishments/plans#licence",
                      ) -> TableCandidate:
    """One page of the plans listing, read as the licences of its establishments -- ES-5.

    ONE ROW PER ESTABLISHMENT ON THE PAGE, however many of its plans the page holds. Its
    plans' copies must agree; two different licences for one establishment refuse the
    page by name, because the whole reason this table exists is that they never differ
    (0 of 2,145 in the census). The page's other establishments' licences arrive on the
    pages that carry them, and the same row read from two pages is one record.

    ITS OWN `locator`, so this is a second ingestion of the same snapshot rather than a
    collision with the plans' (`generic_ingestion` is unique on snapshot and locator).
    """
    by_establishment: dict[str, dict[str, str | None]] = {}
    extra: set[str] = set()
    for arabic, english in _pairs(english_body, arabic_body, language_paths=LANGUAGE_PATHS):
        _assert_required_objects(arabic)
        _assert_required_objects(english)
        for view in (arabic, english):
            licence = _at(view, *LICENCE)
            if not isinstance(licence, dict) or not licence:
                raise RowShapeError(f"establishment.license is {licence!r}, but every plan "
                                    "row of the census carries it as an object")
        row = {name: _text(read(arabic, english)) for name, read in LICENCE_COLUMNS}
        lic_ar, lic_en = _at(arabic, *LICENCE), _at(english, *LICENCE)
        unknown = {f"license.{key}": lic_ar[key] if key in lic_ar else lic_en[key]
                   for key in sorted((set(lic_ar) | set(lic_en)) - KNOWN_LICENCE_KEYS)}
        row["unknown_keys"] = _text(dict(sorted(unknown.items())))
        extra.update(unknown)
        key = row["establishment_id"]
        if key in by_establishment and by_establishment[key] != row:
            differing = sorted(name for name in LICENCE_FIELDS
                               if by_establishment[key][name] != row[name])
            raise RowShapeError(f"establishment {key} carries two different licences on "
                                f"one page (they differ in {differing})")
        by_establishment[key] = row
    rows_out = tuple(by_establishment.values())
    fields = tuple(
        InferredField(
            field_key=name, source_name=name, data_type="text",
            nullable=True, position=position, confidence=1.0,
            uniqueness=_uniqueness(rows_out, name),
            null_fraction=(sum(1 for row in rows_out if not row.get(name)) / len(rows_out)
                           if rows_out else 1.0),
            identity_candidate=(name == LICENCE_IDENTITY_FIELD),
        )
        for position, name in enumerate(LICENCE_FIELDS)
    )
    return TableCandidate(
        table_index=table_index, name=LICENCE_DATASET_NAME, locator=locator, fields=fields,
        rows=rows_out, confidence=1.0,
        warnings=tuple(f"the register added a licence key this reader does not know: {key}"
                       for key in sorted(extra)),
        approvable=bool(rows_out), truncated=False,
    )
