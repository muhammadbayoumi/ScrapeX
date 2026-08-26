"""The two pages of one contractor do not always publish the same boxes.

WHY THIS FILE EXISTS, AND WHAT IT COST TO FIND. `merge_locales` refused any pair whose
box counts differed. That was right — and it held **129 contractors** out of the
warehouse, every one of them with both pages already on disk, so no crawl could ever
have recovered them. Measured 2026-08-24 over the whole stored corpus (`OP-66`).

THE SITE PUBLISHES THE SAME ELEVEN BOXES IN THE SAME ORDER IN BOTH LANGUAGES, and a
page may omit one — but the two languages do not always omit the SAME one. On 121 of
the 129 the Arabic page carries a `عنوان` box the English page does not print at all.

TWO SHAPES, AND THE SECOND IS WHY A TAIL-DROP WOULD HAVE BEEN A DISASTER:

    97 pages   English omits Address AND Activity; Arabic has one of them. Both sit
               past every English box, so nothing shifts — but WHICH one Arabic
               carries cannot be told without reading an Arabic label, so its value
               is dropped rather than filed under a guess.
    24 pages   English omits Address only. Arabic's extra sits at index 9, BETWEEN
               `Region` and `Activity`. Zipping to the shorter list would have
               written an Arabic ADDRESS into `activity_ar`.

AND THE INSTRUMENT MATTERED MORE THAN THE MEASUREMENT. The first study of this
compared `Reading.fields` — a dict whose insertion order is NOT the page's, because
`read_profile` adds `organization_email` and `commercial_registration` after the
info-box loop. It reported a gap of +2 on every pair and "121 of 121 MISALIGNED", and
concluded no repair was possible. `merge_locales` reads `labels` and `values`. Against
those the gap is **±1 on all 129, never ±2**, and nothing is misaligned before the
divergence. `LESSONS` §9 is about exactly this class of error; this is an instance.

WHY NO ARABIC LABEL IS READ, STILL. `PROFILE_FIELDS` is ordered, so an English label's
position in it IS its box's canonical position — which means the gap can be LOCATED
from the English side alone. That property is worth more than the 129: the site spells
`المنطقه` with `ه` where `ة` belongs, so a hand-written Arabic vocabulary would have to
carry the site's own typo and would break the day they fix it.

THE FIXTURES ARE REAL PAGES, cut down to the block the parser reads — the info-box
block IS the defect, so a synthetic fixture with the right counts could prove a counter
fired and never reach it. What is guaranteed is what matters and it is stated exactly:
`read_profile` returns the SAME labels and the SAME values from the fixture as from the
untrimmed snapshot, which was asserted while the fixtures were written. An earlier draft
of this paragraph claimed "not one byte edited"; an adversarial review measured that the
block was re-indented out of its 48-space nesting, so the fixture is not a substring of
the page. The claim was too strong and is now the one that can be checked. One
parser-visible field IS lost — `commercial_registration`, which lives in the
contract-request form the trim removes — so no assertion here reads it.
"""
from __future__ import annotations

import pathlib

import pytest

from scrapex.extract.muqawil import (
    NOT_BILINGUAL,
    PROFILE_FIELDS,
    Reading,
    align_locales,
    merge_locales,
    read_profile,
)

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "muqawil"
CANON = list(PROFILE_FIELDS)

#: The contractor each fixture pair is really about, so `read_profile`'s layer-1
#: check is exercised on the same path production takes.
WHOSE = {"omits-one-box": "20060253", "omits-two-boxes": "20059311"}


def _pair(name: str) -> tuple[Reading, Reading]:
    cid = WHOSE[name]
    return (read_profile((FIXTURES / f"profile-en-{name}.html").read_text(encoding="utf-8"),
                         contractor_id=cid),
            read_profile((FIXTURES / f"profile-ar-{name}.html").read_text(encoding="utf-8"),
                         contractor_id=cid))


# ---- the real documents ------------------------------------------------------

def test_the_fixture_still_has_the_shape_this_file_is_about():
    """A GUARD ON THE FIXTURE ITSELF. Every assertion below is meaningless if the
    trimmed pages stop exhibiting the mismatch, and a fixture that quietly lost its
    defect is a suite that quietly stops testing."""
    english, arabic = _pair("omits-one-box")
    assert (len(english.labels), len(arabic.labels)) == (10, 11), (
        f"the one-box fixture no longer differs by one: "
        f"{len(english.labels)} vs {len(arabic.labels)}")
    assert "Address" not in english.labels, "the English fixture regained its address box"
    assert english.labels[-1] == "Activity", (
        "the divergence is no longer INTERIOR, which is the whole point of this pair")

    english, arabic = _pair("omits-two-boxes")
    assert (len(english.labels), len(arabic.labels)) == (9, 10)
    assert english.labels[-1] == "Region", "the two-box fixture stopped being trailing"


def test_an_interior_extra_box_shifts_everything_after_it():
    english, arabic = _pair("omits-one-box")
    lined = align_locales(english, arabic)
    assert lined is not None, "a real, alignable pair was refused"
    assert lined.extra_label == "Address"
    # Index 9 is English's `Activity`; Arabic's index 9 is the address, so it must
    # map to 10. Every index below 9 is untouched.
    assert lined.arabic_of == {0: 0, 1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6, 7: 7, 8: 8, 9: 10}


def test_the_arabic_address_does_not_land_in_activity_ar():
    """THE CORRUPTION A TAIL-DROP WOULD HAVE CAUSED, on a real page, asserted
    directly rather than argued for in a comment."""
    merged = merge_locales(*_pair("omits-one-box"))
    assert merged["address"], "the Arabic-only address was not recovered"
    assert merged.get("activity_ar") != merged["address"], (
        "the address was written into activity_ar — this is the exact failure "
        "merge_locales refuses to risk")
    assert merged.get("region_ar"), "region_ar came from the wrong box, or from none"


def test_the_bilingual_pairs_are_the_same_fact_in_two_languages():
    """Alignment is only correct if what it pairs actually corresponds. `Member Since`
    is identical in both locales and the two numbers are digits — so these are
    checkable across the language boundary without translating anything."""
    english, arabic = _pair("omits-one-box")
    lined = align_locales(english, arabic)
    checked = 0
    for index, label in enumerate(english.labels):
        if label in ("Member Since", "Membership Number", "Organization Mobile Number"):
            assert english.values[index] == arabic.values[lined.arabic_of[index]], (
                f"{label} does not match across the pair, so the alignment is wrong")
            checked += 1
    assert checked == 3, (
        f"only {checked} of the three language-independent boxes were found, so this "
        "test proved less than it claims")


def test_a_trailing_extra_is_aligned_and_its_value_is_dropped_not_guessed():
    """The 97-page shape. English omits Address AND Activity; Arabic has one of them
    and nothing here can say which, so the row is complete for every box English
    published and the extra is DROPPED. Filing it under either name would be a coin
    toss written into a column."""
    english, arabic = _pair("omits-two-boxes")
    lined = align_locales(english, arabic)
    assert lined is not None
    assert lined.extra_label is None, (
        "the extra box was named, but English omits two so it cannot be")
    assert lined.arabic_of == {index: index for index in range(9)}, (
        "a trailing extra shifted an index it sits after")
    merged = merge_locales(english, arabic)
    assert not merged.get("address"), "an unnameable box was filed as the address"
    assert not merged.get("activity"), "an unnameable box was filed as the activity"


def test_the_ordinary_pair_is_untouched():
    """The repair must not cost the 17,264 that already worked."""
    english = read_profile((FIXTURES / "profile-en.html").read_text(encoding="utf-8"))
    arabic = read_profile((FIXTURES / "profile-ar.html").read_text(encoding="utf-8"))
    lined = align_locales(english, arabic)
    assert lined.extra_label is None
    assert lined.arabic_of == {index: index for index in range(len(english.labels))}
    assert merge_locales(english, arabic)["membership_number"]


# ---- what must still be refused ---------------------------------------------

def _reading(labels: tuple[str, ...]) -> Reading:
    return Reading(fields={}, labels=labels,
                   values=tuple(f"v{index}" for index in range(len(labels))))


def test_arabic_being_the_shorter_side_is_refused():
    """EIGHT REAL PAGES. Which box ARABIC dropped is precisely what reading no Arabic
    label leaves unknowable, and guessing would put a value one column out."""
    english = _reading(tuple(CANON[:10]))
    arabic = _reading(tuple(f"ar{index}" for index in range(9)))
    assert align_locales(english, arabic) is None
    with pytest.raises(ValueError, match="cannot be lined up"):
        merge_locales(english, arabic)


def test_a_gap_of_two_is_refused():
    """Nothing measured has one, and an untested inference is not a feature. Two
    missing boxes give two independent positions to place, and the shift stops being
    determined by the English side alone."""
    assert align_locales(_reading(tuple(CANON[:8])),
                         _reading(tuple(f"ar{index}" for index in range(10)))) is None


def test_an_absent_position_that_straddles_an_english_box_is_refused():
    """THE AMBIGUITY THIS TURNS ON. English here publishes box 0 and box 8 only, so
    the extra could be anywhere between — and the shift for box 8 is 0 or 1 depending
    on which. Measured: zero real pages, and it is refused rather than resolved
    because the answer is genuinely unknown, not merely unlikely."""
    assert align_locales(_reading((CANON[0], CANON[8])), _reading(("a", "b", "c"))) is None


def test_a_label_the_map_does_not_know_is_refused():
    """A new box the site adds has no canonical position, so the gap cannot be
    located. `read_profile` keeps it under a slug of its own, which is right for one
    page and not enough to align two."""
    assert align_locales(_reading((CANON[0], "Something New")),
                         _reading(("a", "b", "c"))) is None


def test_labels_out_of_canonical_order_are_refused():
    """Every inference here rests on one printed order. A page that breaks it has
    broken the premise, and the honest answer is to stop rather than to sort.

    THE PAIR IS ADJACENT AND SWAPPED ON PURPOSE. The first version of this test used
    `(CANON[8], CANON[0])`, and a mutation proved it worthless: with the order check
    deleted those two positions straddle the absent ones, so the AMBIGUITY check
    returned None and the test passed for the wrong reason. Swapping boxes 1 and 0
    leaves every absent position above both, so the ambiguity check is satisfied and
    only the order check stands between this page and a map that pairs English's
    second box with Arabic's first."""
    assert align_locales(_reading((CANON[1], CANON[0])), _reading(("a", "b", "c"))) is None


def test_a_repeated_label_is_refused():
    """`len(set(seen)) != len(seen)`, which the order comparison alone lets through:
    `[0, 0]` is sorted. Two boxes claiming one canonical position means one of them
    is not what it says, and every index after it is a guess."""
    assert align_locales(_reading((CANON[0], CANON[0])), _reading(("a", "b", "c"))) is None


# ---- where the extra goes ----------------------------------------------------

def test_a_single_valued_extra_goes_to_the_field_and_not_to_its_ar_twin():
    """`address` is in `NOT_BILINGUAL` because the site publishes ONE address, in
    Arabic, whichever page you ask. So the Arabic page is not a second-best source
    for it — it is the only one — and `address_ar` would be a column that never
    means anything."""
    assert "address" in NOT_BILINGUAL
    merged = merge_locales(*_pair("omits-one-box"))
    assert merged.get("address")
    assert "address_ar" not in merged


def test_a_bilingual_extra_goes_to_the_ar_half_and_leaves_the_base_empty():
    """The other branch, which no real page exercises today. A bilingual column whose
    English half was never published must not pretend the Arabic value is both — that
    is how an Arabic city name ends up in the column an English report reads."""
    # ENGLISH OMITS EXACTLY ONE BOX, `City`, and publishes the other ten. Omitting
    # `City` alone is what makes the extra NAMEABLE — the first draft of this test
    # dropped City and kept only seven boxes, leaving three absent positions that
    # straddle box 8, so `align_locales` correctly returned None and the test failed
    # on its own fixture rather than on the code.
    english = _reading(tuple(CANON[:7]) + tuple(CANON[8:]))
    arabic = Reading(fields={}, labels=tuple(f"ar{index}" for index in range(11)),
                     values=tuple(f"v{index}" for index in range(7)) + ("مدينة",)
                            + tuple(f"v{index}" for index in range(8, 11)))
    lined = align_locales(english, arabic)
    assert lined is not None and lined.extra_label == "City"
    merged = merge_locales(english, arabic)
    assert merged.get("city_ar") == "مدينة"
    assert not merged.get("city"), "the Arabic value was written into the English column"


def test_an_omitted_email_box_is_not_filled_from_the_boxs_obfuscated_text():
    """FAILURE #1 OF THIS MODULE'S DOCSTRING, nearly reintroduced by the extra-box
    branch. Cloudflare obfuscates the address, so the info-box reads the literal
    `[email protected]` on every page in both locales — the real value comes from
    `data-cfemail` through `read_email`, which `read_profile` has already put in
    `fields`. An adversarial review reproduced the regression on contractor 3574.

    No page in the corpus omits this box today; all 24 single-omission cases are
    `Address`. That is a fact about the site, not a property of the code.
    """
    english = _reading(tuple(CANON[:6]) + tuple(CANON[7:]))       # omits `Organization Email`
    arabic = Reading(
        fields={"organization_email": "real.person@example.test"},
        labels=tuple(f"ar{index}" for index in range(11)),
        values=tuple(f"v{index}" for index in range(6))
                + ("[email protected]",)
                + tuple(f"v{index}" for index in range(7, 11)))
    lined = align_locales(english, arabic)
    assert lined is not None and lined.extra_label == "Organization Email"

    merged = merge_locales(english, arabic)
    assert merged["organization_email"] == "real.person@example.test", (
        "the address came from the info-box instead of from data-cfemail: "
        + repr(merged.get("organization_email")))
    assert "[email protected]" not in merged.values(), (
        "Cloudflare's placeholder was stored as if it were an address, which is the "
        "silent failure this module was built to prevent")


# ---- three gaps a later review's mutation run found -------------------------
#
# Eleven mutants were tested when this file was written and all were caught. A
# subsequent adversarial review ran twenty-one and found three genuine survivors,
# all of them shapes the SITE does not currently print — so the tests pinned the
# arithmetic only for today's data. The three below close them. Thirteen mutants now
# run and twelve are caught.
#
# THE THIRTEENTH IS AN EQUIVALENT MUTANT AND IS RECORDED, NOT CHASED. Pivoting the
# shift on `last` instead of `first` survives, and it must: the ambiguity check two
# lines above guarantees `(first < position) == (last < position)` for every position
# in `seen`, so the two pivots cannot disagree on any input that reaches them. A test
# written to kill it would have to assert on an unreachable state, which is a test
# that lies about what the code does. Five more of the twenty-one were equivalent for
# the same kind of reason (`<=` for `<`, `absent[-1]` for `absent[0]`, `spare[-1]` for
# `spare[0]`, and two on the `spare` length check, which is provably always 1).

def test_a_leading_gap_shifts_every_index():
    """MUTANT: `arabic_of = {index: position}` — using the canonical position as the
    Arabic index. Indistinguishable from the real thing whenever the absent block is
    TRAILING, which is every page in the corpus (`(Address, Activity)` or `(Address,)`).

    With a LEADING gap the two answers diverge on the very first box, so this is the
    test that pins the arithmetic rather than the data."""
    english = _reading(tuple(CANON[2:]))                    # omits boxes 0 and 1
    arabic = _reading(tuple(f"ar{index}" for index in range(10)))
    lined = align_locales(english, arabic)
    assert lined is not None
    # Arabic holds nine of English's boxes plus ONE of the two absent ones, so English's
    # first box sits at Arabic index 1 — not at its canonical position 2.
    assert lined.arabic_of[0] == 1, (
        f"a leading gap was mis-shifted: {lined.arabic_of}")
    assert lined.arabic_of == {index: index + 1 for index in range(9)}


def test_english_publishing_every_box_while_arabic_has_more_is_refused():
    """MUTANT: deleting `if not absent: return None`. With all eleven English boxes
    present there is no absent position for the extra to occupy, `min([])` raises, and
    a clean refusal becomes `ValueError: min() arg is an empty sequence` — a different
    exception, from a different place, saying nothing about the page."""
    english = _reading(tuple(CANON))
    arabic = _reading(tuple(f"ar{index}" for index in range(12)))
    assert align_locales(english, arabic) is None
    with pytest.raises(ValueError, match="cannot be lined up"):
        merge_locales(english, arabic)


def test_an_extra_box_with_no_value_leaves_the_column_absent():
    """MUTANT: dropping the `and value` guard. An empty box would then write `''`,
    and an empty string is not the same fact as a missing column — one says the site
    published nothing there, the other says it published emptiness. `R-45` is that
    the site is the only source of truth, and it did not say this."""
    english = _reading(tuple(CANON[:9]) + (CANON[10],))       # omits `Address`
    arabic = Reading(fields={}, labels=tuple(f"ar{index}" for index in range(11)),
                     values=tuple(f"v{index}" for index in range(9)) + ("", "v10"))
    lined = align_locales(english, arabic)
    assert lined is not None and lined.extra_label == "Address"
    assert "address" not in merge_locales(english, arabic), (
        "an empty box was stored as an empty address")
