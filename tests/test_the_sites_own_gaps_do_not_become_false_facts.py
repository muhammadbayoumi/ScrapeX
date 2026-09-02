"""Two things the site publishes that must not be stored as if they were true.

BOTH CAME OUT OF ONE QUESTION HE ASKED — whether six named columns were among the 48 —
and neither was the defect the question looked like. Measuring 712 real Dammam profiles
retired three suspicions and produced these two instead:

| suspected | measured |
|---|---|
| `activity` stores the string `"None"` | it is `None`, the value. The field is genuinely absent on 669 of 712. **Not a defect** |
| `merge_locales` wrongly refuses 8 pairs | the two locales really do publish 9 labels against 10, and the refusal was correct **as written**. **SUPERSEDED 2026-08-24 by `R-51`** for the 121 Arabic-longer pairs, then **superseded again 2026-09-01** for the opposite eight: their Arabic labels are all known, ordered, and equal the English sequence minus `Address`, so the omission is proved rather than guessed. Unknown or reordered Arabic labels remain refused |
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
    DEFAULT_MAP_PIN,
    PROFILE_FIELDS,
    _is_placeholder_logo,
    _slug,
    merge_locales,
    read_coordinates,
    read_listing,
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


def test_a_known_shorter_arabic_page_keeps_the_english_fact():
    """The opposite eight are no longer discarded whole. This simulates Arabic
    omitting the final Activity box: the strict known-label subsequence identifies
    that omission, preserves English Activity, and simply leaves `activity_ar`
    unavailable. The unknown-label refusal is tested beside `align_locales`."""
    english = read_profile(_html("en"))
    shorter = read_profile(_html("ar"))
    object.__setattr__(shorter, "labels", tuple(shorter.labels[:-1]))
    object.__setattr__(shorter, "values", tuple(shorter.values[:-1]))

    merged = merge_locales(english, shorter)

    assert merged.get("membership_number") == english.fields["membership_number"]
    assert merged.get("activity") == english.fields["activity"]
    assert "activity_ar" not in merged


def test_the_declared_english_labels_still_map_where_they_did():
    """PROFILE_FIELDS is the declared map from label to key, and `_slug` is only the
    fallback for a label it does not name. Changing the fallback must not have moved a
    declared one."""
    assert PROFILE_FIELDS["Membership Number"] == "membership_number"
    assert PROFILE_FIELDS["Organization Email"] == "organization_email"
    assert PROFILE_FIELDS["Member Since"] == "member_since"
    assert PROFILE_FIELDS["Address"] == "address"


# ---- R-55 · the two placeholders that are not values --------------------------

LAT, LNG = DEFAULT_MAP_PIN
BARE_DIRECTORY = "https://muqawil.org/public/contractor/companyLogo/"


def _pinned(lat: float, lng: float) -> str:
    return f"<html><script>var latlang = {{ lat: {lat!r}, lng: {lng!r} }};</script></html>"


def test_the_site_wide_default_pin_is_not_promoted_to_a_coordinate_column():
    """MEASURED ON HIS WAREHOUSE 2026-08-29: **14,621 of the 17,352 profiles that carry a
    coordinate at all -- 84.3% -- publish this one pair.** It is the centre of Riyadh, so
    the column places every contractor in Jizan and Tabuk on a point about 1,000 km from
    where they are. A value the site emits identically for six contractors in seven says
    nothing about any of them."""
    english = read_profile(_pinned(LAT, LNG))

    merged = merge_locales(english, english)

    assert "latitude" not in merged
    assert "longitude" not in merged


def test_the_reader_still_reports_the_default_pin_faithfully():
    """`R-45` IS NOT OVERRIDDEN, and this is where that is proved rather than asserted.
    The page says this pair and `read_coordinates` still says it back. What changes is
    only whether we promote it to a column -- refusing to claim knowledge is not editing
    what the site published."""
    assert read_coordinates(_pinned(LAT, LNG)) == (LAT, LNG)


def test_a_pair_that_merely_resembles_the_default_pin_is_still_stored():
    """THE CONSTANT IS EXACT, NOT FUZZY, and the next pair down in the data is why: 30
    rows share `(24.7135517, 46.6753)`, which is a perfectly ordinary thing for several
    contractors in one district to do. `R-55` draws the boundary itself -- a value that
    DIFFERS between records is data, however strange it looks -- so a radius or a
    frequency threshold would eventually eat a real address."""
    english = read_profile(_pinned(LAT + 0.0000001, LNG))

    merged = merge_locales(english, english)

    assert merged["latitude"].startswith("24.449351")
    assert merged["longitude"] == str(LNG)


def test_half_the_default_pin_is_not_the_default_pin():
    """A contractor genuinely on the default LATITUDE with their own longitude keeps
    both. Only the pair is the placeholder."""
    english = read_profile(_pinned(LAT, 39.1434676))

    merged = merge_locales(english, english)

    assert merged["longitude"] == "39.1434676"


def test_a_logo_url_that_names_no_file_is_not_a_logo():
    """THE DOCUMENTED STRING IS NOT IN THE DATA. `CONTRACTOR-SOURCE.md` asks for
    `default.jpg` to be stored as NULL; measured across all 17,304 stored listing rows on
    2026-08-29, `default.jpg` appears **zero** times, while the bare directory appears on
    **13,042 (75.4%)**. A guard written against the documented string would never once
    fire -- `LESSONS` \u00a77."""
    assert _is_placeholder_logo(BARE_DIRECTORY) is True
    assert _is_placeholder_logo("") is True
    assert _is_placeholder_logo("   ") is True
    # kept because the page's own `onerror` still names it, not because it was measured
    assert _is_placeholder_logo(
        "https://muqawil.org/public_assets/img/companies/default.jpg") is True
    assert _is_placeholder_logo(BARE_DIRECTORY + "CompanyLogo-1710325829_x.jpg") is False


def test_the_bare_directory_is_emptied_through_the_real_card_shape():
    """BUILT FROM A REAL CARD, with only the `src` substituted. The fixture's four cards
    all carry genuine filenames, so the placeholder has to be introduced -- and doing it
    by editing one attribute of real HTML is the difference between testing the parser
    and testing a hand-written string that no longer resembles the page."""
    html = (FIXTURES / "listing-en.html").read_text(encoding="utf-8")
    real = read_listing(html)[0]["logo_url"]
    assert real.startswith(BARE_DIRECTORY) and real != BARE_DIRECTORY

    swapped = html.replace(f'src="{real}"', f'src="{BARE_DIRECTORY}"', 1)

    assert read_listing(swapped)[0]["logo_url"] == ""


def test_the_fix_does_not_delete_the_logos_that_exist():
    """Or it would be a feature that empties a column. All four fixture cards publish a
    real filename and all four must survive -- the 4,262 distinct real values on his
    warehouse are what this is protecting."""
    rows = read_listing((FIXTURES / "listing-en.html").read_text(encoding="utf-8"))

    assert len(rows) == 4
    assert all(r["logo_url"].startswith(BARE_DIRECTORY) for r in rows)
    assert all(r["logo_url"] != BARE_DIRECTORY for r in rows)
