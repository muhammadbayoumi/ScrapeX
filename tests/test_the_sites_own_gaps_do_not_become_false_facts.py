"""Two things the site publishes that must not be stored as if they were true.

BOTH CAME OUT OF ONE QUESTION HE ASKED — whether six named columns were among the 48 —
and neither was the defect the question looked like. Measuring 712 real Dammam profiles
retired three suspicions and produced these two instead:

| suspected | measured |
|---|---|
| `activity` stores the string `"None"` | it is `None`, the value. The field is genuinely absent on 669 of 712. **Not a defect** |
| `merge_locales` wrongly refuses 8 pairs | the two locales really do publish 9 labels against 10. The refusal is correct and its reasoning is written. **Not a defect** |
| `longitude = 0` is a parse failure | the page itself says `var latlang = { lat: 24.4493518, lng: 0 }`. The parser is right. **The defect is storing it** |

AND THE MEASUREMENT FOUND ONE NOBODY HAD SUSPECTED: `read_profile` on an Arabic page
turned **ten labels into two keys**, because `_slug` kept `[a-z0-9]` only and fell back to
the constant `"unnamed"` — so every Arabic label produced the same key and eight of ten
were lost to a dict collision.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scrapex.extract.muqawil import (
    PROFILE_FIELDS,
    _slug,
    merge_locales,
    read_coordinates,
    read_profile,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "muqawil"


def _html(locale: str) -> str:
    return (FIXTURES / f"profile-{locale}.html").read_text(encoding="utf-8")


# ---- a label with no ASCII must still get its own key -------------------------

def test_two_arabic_labels_do_not_collapse_into_one_key():
    """THE COLLISION, WHICH LOST EIGHT FIELDS OF TEN. Measured on a real profile before
    the fix: `['x_unnamed', 'organization_email']` from ten Arabic labels."""
    labels = ["رقم العضويه", "العضوية", "عضو منذ", "حجم المنشأة", "المدينة"]

    keys = [_slug(one) for one in labels]

    assert len(set(keys)) == len(labels), dict(zip(labels, keys, strict=True))
    assert "unnamed" not in keys


def test_the_key_is_the_same_next_time_the_same_label_appears():
    """A POSITIONAL FALLBACK WOULD HAVE SHIFTED. `unnamed_3` is stable only until the
    site adds a box above it; a digest of the label is stable while the label is."""
    assert _slug("المدينة") == _slug("المدينة")
    assert _slug("المدينة") != _slug("المنطقه")


def test_an_english_label_is_untouched_by_the_fix():
    """THE PART THAT MUST NOT MOVE. Every declared key comes from an English label, and a
    changed slug would silently re-key an approved schema."""
    assert _slug("Membership Number") == "membership_number"
    assert _slug("Training credit hours") == "training_credit_hours"
    assert _slug("Organization Email") == "organization_email"


def test_a_blank_label_is_still_the_one_shared_name():
    """Nothing distinguishes one empty label from another, so they may share a key — and
    the digest must not be computed over whitespace and produce a false distinction."""
    assert _slug("") == _slug("   ") == "unnamed"


def test_the_arabic_profile_now_keys_every_box_it_publishes():
    """END TO END on the committed fixture, and the invariant is NOT equality.

    A reading carries keys that no label produced — the email is decoded from
    `data-cfemail` and has no info-box of its own — so `len(fields) == len(labels)` is the
    wrong test and the first version of this asserted it and failed at 12 against 11. The
    fact that matters is that no label was LOST: every one contributed a key of its own.
    """
    arabic = read_profile(_html("ar"))

    assert len(arabic.fields) >= len(arabic.labels), (
        f"{len(arabic.labels)} labels produced only {len(arabic.fields)} keys, so at "
        "least two collapsed into one")
    assert len({_slug(one) for one in arabic.labels}) == len(arabic.labels)


# ---- a zero coordinate is "no pin", not a place ------------------------------

def test_the_reader_still_reports_the_zero_faithfully():
    """`read_coordinates` IS NOT THE PLACE TO FIX THIS. It reads what the page says, and
    the page says `lng: 0`. Source truth is never edited — `DSN-05` keeps the published
    `"RIYADH - Riyadh"` beside the split for the same reason."""
    page = ("<html><script>var latlang = { lat: 24.4493518, lng: 0 };"
            "</script></html>")

    assert read_coordinates(page) == (24.4493518, 0.0)


def test_a_zero_longitude_is_not_promoted_to_a_coordinate_column():
    """MEASURED ON HIS DATA: two of 712 Dammam profiles publish `lng: 0`, both with the
    SAME latitude — an unset default. Latitude 24.45 with longitude 0 is a point in the
    Atlantic about 4,000 km from Dammam, and a table whose purpose is to be believed
    cannot say that."""
    english = read_profile("<html><script>var latlang = { lat: 24.4493518, lng: 0 };"
                           "</script></html>")

    merged = merge_locales(english, english)

    assert "latitude" not in merged
    assert "longitude" not in merged


def test_a_real_pair_is_still_stored():
    """The common case, or the fix above would be a feature that deletes coordinates."""
    english = read_profile(_html("en"))
    arabic = read_profile(_html("ar"))

    merged = merge_locales(english, arabic)

    # THE FIXTURE'S FULL PRECISION, not the four decimals a report prints. The first
    # version of this asserted `"24.6717"` — a truncation read off a summary line — which
    # is the same class of error as building a fixture from memory.
    assert merged["latitude"].startswith("24.6716")
    assert merged["longitude"].startswith("46.394")
    assert float(merged["latitude"]) and float(merged["longitude"])


def test_a_page_with_no_map_at_all_is_unchanged(monkeypatch):
    """`None` FROM `read_coordinates` ALREADY MEANT "no location", and the new condition
    must not turn that into an exception or a zero."""
    english = read_profile("<html><body>no map here</body></html>")

    merged = merge_locales(english, english)

    assert "latitude" not in merged


# ---- and what the measurement retired ----------------------------------------

def test_an_absent_field_is_none_and_not_the_string_none():
    """SUSPECTED AND RETIRED. 669 of 712 profiles carry no `activity`, and the value is
    `None` rather than the four characters `"None"`. The first measurement applied `str()`
    and could not tell those apart, which is how a non-defect gets reported as one."""
    english = read_profile(_html("en"))

    absent = english.fields.get("a_field_this_page_does_not_have")

    assert absent is None
    assert absent != "None"


def test_a_differing_label_count_is_still_refused():
    """SUSPECTED AND RETIRED. Eight of 712 pairs publish 9 labels against 10, and
    refusing them is correct: pairing by index across a divergence attaches the wrong
    Arabic value to every field after it. 704 of 712 — 98.9% — pair cleanly."""
    english = read_profile(_html("en"))
    shorter = read_profile(_html("ar"))
    object.__setattr__(shorter, "labels", tuple(shorter.labels[:-1]))

    with pytest.raises(ValueError, match="pairing them by position"):
        merge_locales(english, shorter)


def test_the_declared_english_labels_still_map_where_they_did():
    """PROFILE_FIELDS is the declared map from label to key, and `_slug` is only the
    fallback for a label it does not name. Changing the fallback must not have moved a
    declared one."""
    assert PROFILE_FIELDS["Membership Number"] == "membership_number"
    assert PROFILE_FIELDS["Organization Email"] == "organization_email"
    assert PROFILE_FIELDS["Member Since"] == "member_since"
    assert PROFILE_FIELDS["Address"] == "address"
