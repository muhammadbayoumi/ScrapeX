"""The Oman ESNAD register's two language views, turned into one candidate table.

`scrapex/sites/oman_tenderboard.py` knows how to read a page; this turns a pair of them
into the rows `generic_record` stores. The split is muqawil's — `sites/` for the listing's
own knowledge, `extract/` for the candidate — and it is kept because the two answer
different questions.

THREE LESSONS ARE COPIED FROM `extract/muqawil.py` RATHER THAN RE-LEARNED, and each one
cost that source a run:

  * **The field list is DECLARED and its order FIXED.** Deriving it from the page made the
    schema depend on which twenty contractors that page happened to show, and 823 of 897
    pages were refused with `ExtractionConflict`.
  * **`nullable` is always True, never measured.** Computed per page it read False where
    the page happened to be complete, and 50 pages in 60 were refused as "a different
    schema" with identical fields in identical order.
  * **Every field appears on every row**, absent ones as `None`, because `_validated_rows`
    walks the field list and a row simply lacking a key raises rather than recording an
    empty cell.

`R-12`'S SHAPE IS FILLABLE HERE, and this is the first candidate source where it is. The
English view supplies English names, categories and company types; the Arabic view supplies
theirs; the two are joined on the CR number. Balady had no English at all (`#998` §3).

THE ADDRESS IS THE EXCEPTION, and it is a rule rather than an accident: the address is
Arabic in the English view for every row measured, so `address` stays NULL and
`address_ar` carries it — which is what `docs/GULF-EGYPT-SOURCES.md:340` asks for.

WHAT IS DELIBERATELY *NOT* STORED: the decomposed category list. A firm holds several
categories (22 of 102 measured) and the honest home for them is a child table, which
`R-38` has not yet been asked how to shape (`#1003`). Flattening them into one delimited
column is the very thing `docs/GULF-EGYPT-SOURCES.md:353` refuses, and `R-19` measured the
penalty. So the raw cell is stored whole — it is reproducible input — and two flat,
honest derivations sit beside it: how many categories decomposed, and whatever the
vocabulary could not explain. The second is the health signal: it is empty on every row
measured, and a non-empty one says the vocabulary drifted.
"""
from __future__ import annotations

from ..extract.html_table import InferredField, TableCandidate
from ..sites.oman_tenderboard import (
    Firm,
    decompose_categories,
    join_languages,
    read_categories,
    read_rows,
)

#: The dataset these rows land in.
DATASET_KEY = "oman_registered_vendors"
DATASET_NAME = "Oman registered vendors"

#: The identity, and `#1004` measured why it is this and not the CR number: the short name
#: was unique and present on 102 of 102 rows, the CR number blank on 1 of 102.
IDENTITY_FIELD = "short_name"

#: DECLARED AND ORDERED. See the module docstring: a derived list makes the schema a
#: property of one page. A field the site ADDS is still kept -- appended after these, by
#: `_candidate`, because a new column is news and dropping it silently is how it stays
#: news for a year.
FIELDS: tuple[str, ...] = (
    "short_name",
    "firm_name",
    "firm_name_ar",
    "cr_number",
    # Base English stays NULL by measurement, not by oversight -- the English view's
    # address cell is Arabic.
    "address",
    "address_ar",
    "telephone",
    "fax",
    "registered_category",
    "registered_category_ar",
    # Derived, flat and honest: the count and the leftovers, never a delimited list of
    # the categories themselves.
    "registered_category_count",
    "registered_category_undecoded",
    "reg_expiry",
    "company_type",
    "company_type_ar",
)

#: `R-12`: identifiers, numbers, dates and codes get no `_ar` twin. Named rather than
#: implied, so a later field is placed deliberately.
NO_ARABIC_TWIN = frozenset({
    "short_name", "cr_number", "telephone", "fax", "reg_expiry",
    "registered_category_count", "registered_category_undecoded",
})


def _uniqueness(rows: tuple[dict[str, str | None], ...], name: str) -> float:
    values = [row.get(name) for row in rows]
    present = [value for value in values if value]
    if not present:
        return 0.0
    return len(set(present)) / len(present)


def _row(english: Firm, arabic: Firm, vocabulary: dict[str, str]) -> dict[str, str | None]:
    split = decompose_categories(english.category_raw, vocabulary)
    return {
        "short_name": english.short_name,
        "firm_name": english.name,
        "firm_name_ar": arabic.name,
        "cr_number": english.cr_number,
        "address": None,
        "address_ar": arabic.address or english.address,
        "telephone": english.telephone,
        "fax": english.fax,
        "registered_category": english.category_raw or None,
        "registered_category_ar": arabic.category_raw or None,
        "registered_category_count": str(len(split.names)),
        # EMPTY IS THE MEASURED STATE, and the column exists so a non-empty one is
        # visible in the warehouse rather than only in a log. `#1004` step 1: 102 of 102
        # cells decomposed with nothing left over.
        "registered_category_undecoded": split.remainder or None,
        "reg_expiry": english.expiry_raw,
        "company_type": english.company_type,
        "company_type_ar": arabic.company_type,
    }


def bilingual_listing_candidate(english_html: str, arabic_html: str, *,
                                table_index: int = 0,
                                locator: str = "RegVendorPublic") -> TableCandidate:
    """One page of the register, both languages, as a candidate table.

    THE VOCABULARY COMES FROM THE ENGLISH PAGE ITSELF, not from a constant here, so a
    category the site adds is data. It is needed because the category cell concatenates
    several names with no separator (`#1004` §4).
    """
    vocabulary = read_categories(english_html)
    pairs = join_languages(read_rows(english_html), read_rows(arabic_html))
    rows = tuple(_row(english, arabic, vocabulary) for english, arabic in pairs)

    present = {key for row in rows for key in row}
    names = list(FIELDS) + sorted(present - set(FIELDS))
    fields = tuple(
        InferredField(
            field_key=name,
            source_name=name,
            data_type="text",
            # Always True, never measured -- see the module docstring.
            nullable=True,
            position=position,
            confidence=1.0,
            uniqueness=_uniqueness(rows, name),
            null_fraction=(sum(1 for row in rows if not row.get(name)) / len(rows)
                           if rows else 1.0),
            identity_candidate=(name == IDENTITY_FIELD),
        )
        for position, name in enumerate(names)
    )
    return TableCandidate(
        table_index=table_index,
        name=DATASET_NAME,
        locator=locator,
        fields=fields,
        # Every field on every row, absent ones as None rather than missing.
        rows=tuple({name: row.get(name) for name in names} for row in rows),
        confidence=1.0,
        warnings=(),
        approvable=bool(rows),
        truncated=False,
    )
