"""Reading a contractor off muqawil.org's pages, proved against real HTML.

THE TWO FAILURES THIS FILE EXISTS FOR ARE BOTH SILENT.

The email is not in the page — Cloudflare leaves the literal `[email protected]`
and hides the address in `data-cfemail`. A parser that skips the decode stores
that literal for every contractor, and a test asking "is the column populated?"
passes forever. So the assertions here are about the DECODED ADDRESS, never
about presence — and never about the ciphertext either, which rotates per
render: the same address came back as `670e…` and `f990…` minutes apart.

The coordinates are in an inline script. A change there raises nothing; it just
turns two columns NULL for seventeen thousand rows.

Fixtures are `tests/fixtures/muqawil/`, taken 2026-08-16. No network.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from scrapex.extract.muqawil import (
    CoordinatesMoved,
    decode_cfemail,
    merge_locales,
    read_coordinates,
    read_email,
    read_listing,
    read_profile,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "muqawil"


def html(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture()
def english():
    return read_profile(html("profile-en.html"))


@pytest.fixture()
def arabic():
    return read_profile(html("profile-ar.html"))


# ---- the email, which is the guard this file was written for -----------------

def test_the_address_is_decoded_and_not_the_literal_the_page_shows(english):
    assert english.fields["organization_email"] == "it@sca.sa"
    assert "[email" not in english.fields["organization_email"], (
        "the page's own placeholder was stored — every contractor in the "
        "country would carry this string and no emptiness check would fail")


def test_the_ciphertext_rotates_so_only_the_address_may_be_asserted():
    """Two fetches of the same profile minutes apart returned different
    payloads. A test pinned to the hex would break on every fixture refresh and
    teach whoever refreshed it that the parser was wrong."""
    assert decode_cfemail("670e1327140406491406") == "it@sca.sa"
    assert decode_cfemail("f9908db98a9a98d78a98") == "it@sca.sa"


def test_a_page_with_no_protected_address_yields_nothing_rather_than_guessing():
    assert read_email("<html><body>no address here</body></html>") == ""


def test_a_payload_that_is_not_one_is_refused():
    with pytest.raises(ValueError, match="not a data-cfemail"):
        decode_cfemail("abc")


# ---- the coordinates, the second silent one ----------------------------------

def test_the_coordinates_come_off_the_inline_script(english):
    assert english.latitude == pytest.approx(24.671699788528482)
    assert english.longitude == pytest.approx(46.39415764160163)


def test_a_plausible_pair_and_not_merely_a_present_one(english):
    """Riyadh is near 24.7N 46.7E. Asserting "not None" would pass on a parser
    that read the two numbers in the wrong order, or read a zoom level."""
    assert 16 < english.latitude < 33, "outside Saudi Arabia's latitudes"
    assert 34 < english.longitude < 56, "outside Saudi Arabia's longitudes"


def test_a_page_with_no_map_at_all_is_not_an_error():
    assert read_coordinates("<html><body>a page with no map</body></html>") is None


def test_a_map_whose_script_moved_refuses_rather_than_returning_none():
    """None means "this contractor has no location", which is a real state. A
    layout change answering it would lose every coordinate without an error."""
    with pytest.raises(CoordinatesMoved, match="shape has changed"):
        read_coordinates("<script>initMap(); centre = [24.6, 46.4];</script>")


# ---- the profile's own fields ------------------------------------------------

def test_the_english_page_is_read_by_its_labels(english):
    assert english.fields["membership_number"] == "10000861"
    assert english.fields["membership_type"] == "Saudi Contractor"
    assert english.fields["member_since"] == "2018/08/25"
    assert english.fields["city"] == "RIYADH"
    assert english.fields["region"] == "Riyadh"
    assert english.fields["training_credit_hours"] == "308 h"


def test_a_label_nobody_mapped_is_kept_rather_than_dropped(english):
    """A field the site adds is news. A parser that discards what it was not
    told about is how it stays news for a year."""
    kept = read_profile(html("profile-en.html").replace(
        ">Region<", ">Some New Thing<"))

    assert kept.fields.get("x_some_new_thing") == "Riyadh"


# ---- the pairing, which is the whole reason both languages are fetched -------

def test_the_two_languages_pair_by_position_and_never_by_arabic_label(english, arabic):
    """The Arabic membership-number label is spelled `رقم العضويه`, with `ه` and
    not `ة`. Nothing here reads it, which is exactly why that cannot break."""
    merged = merge_locales(english, arabic)

    assert merged["membership_type"] == "Saudi Contractor"
    assert merged["membership_type_ar"] == "مقاول سعودي"
    assert merged["company_size"] == "Small Company Size"
    assert merged["company_size_ar"] == "منشأة صغيرة"
    assert merged["city"] == "RIYADH"
    assert merged["city_ar"] == "الرياض"


def test_a_field_declared_untranslatable_earns_no_second_column(english, arabic):
    """`2018/08/25` reads identically in Arabic, and the membership number is a
    number. Both are named in `NOT_BILINGUAL`, so neither is even offered a
    pair."""
    merged = merge_locales(english, arabic)

    assert merged["member_since"] == "2018/08/25"
    assert "member_since_ar" not in merged
    assert "membership_number_ar" not in merged


def test_a_translatable_field_the_site_has_not_translated_earns_none_either(english):
    """THE SECOND GUARD, AND IT NEEDED ITS OWN TEST. The one above proves the
    `NOT_BILINGUAL` list; it never reaches the equality check, because those
    fields are skipped before it. This does: `city` IS a paired field, so a
    site that publishes `RIYADH` in both languages must still produce one
    column, not two holding the same string in every row of seventeen
    thousand."""
    untranslated = read_profile(html("profile-ar.html").replace(
        '<div class="info-value">الرياض', '<div class="info-value">RIYADH', 1))

    merged = merge_locales(english, untranslated)

    assert merged["city"] == "RIYADH"
    assert "city_ar" not in merged, (
        "the Arabic page repeated the English value and it was stored twice")
    assert merged["region_ar"] == "الرياض", (
        "only the repeated field may be dropped — the rest still pair")


def test_the_address_has_no_english_half_so_it_gets_no_pair(english, arabic):
    """Measured: the ENGLISH page prints the Arabic address. There is no English
    one to pair it with."""
    merged = merge_locales(english, arabic)

    assert "الرياض" in merged["address"]
    assert "address_ar" not in merged


def test_pages_that_disagree_about_their_shape_are_refused(english, arabic):
    """Zipping to the shorter of the two would attach the wrong Arabic value to
    every field after the divergence — and a wrong value is worse than a missing
    one in a table whose whole purpose is to be believed."""
    short = read_profile(html("profile-ar.html").replace(
        '<div class="info-name">المدينة</div>', ""))

    with pytest.raises(ValueError, match="attach the wrong Arabic value"):
        merge_locales(english, short)


def test_being_a_saudi_contractor_is_derived_and_never_read_twice(english, arabic):
    merged = merge_locales(english, arabic)
    assert merged["is_saudi_contractor"] == "true"

    other = read_profile(html("profile-en.html").replace(
        "Saudi Contractor", "Non-Saudi Contractor"))
    assert merge_locales(other, arabic)["is_saudi_contractor"] == "false"


# ---- the listing card --------------------------------------------------------

def test_every_contractor_on_the_listing_is_read(english):
    rows = read_listing(html("listing-en.html"))

    assert len(rows) == 4, "the fixture holds four cards"
    assert rows[0]["contractor_id"] == "20008518"
    assert rows[0]["company_name"] == "Awared General Contracting Company"
    assert rows[0]["membership_level"] == "Platinum Membership"
    assert rows[0]["customer_rating_score"] == "5"
    assert rows[0]["customer_rating_count"] == "1"


def test_a_real_logo_is_kept():
    rows = read_listing(html("listing-en.html"))
    assert rows[0]["logo_url"].startswith(
        "https://muqawil.org/public/contractor/companyLogo/")


def test_the_placeholder_is_not_stored_as_a_logo():
    """The site's own `onerror` names `default.jpg`, and a card already showing
    it has no logo. Storing that URL would make every logo-less contractor look
    like one with a picture — and every such contractor look identical."""
    placeholder = "https://muqawil.org/public_assets/img/companies/default.jpg"
    swapped = re.sub(r'src="https://muqawil\.org/public/contractor/companyLogo/[^"]*"',
                     f'src="{placeholder}"', html("listing-en.html"))

    rows = read_listing(swapped)
    assert rows, "the substitution destroyed the fixture"
    for row in rows:
        assert row["logo_url"] == "", (
            f"the placeholder was stored as a logo: {row['logo_url']!r}")


def test_the_impostor_card_is_not_read_as_a_contractor():
    padded = html("listing-en.html").replace(
        "<div class='container'>",
        "<div class='container'><div class='section-card'>an advert</div>")

    assert len(read_listing(padded)) == len(read_listing(html("listing-en.html")))


# ---- the profile reaches the approval path --------------------------------

def _profile_pair():
    from pathlib import Path
    here = Path(__file__).resolve().parent / "fixtures" / "muqawil"
    return ((here / "profile-en.html").read_text(encoding="utf-8"),
            (here / "profile-ar.html").read_text(encoding="utf-8"))


def test_a_profile_becomes_a_candidate_the_approval_path_accepts():
    """THE ONLY THING THAT WAS MISSING, and the plan said otherwise.

    `read_profile`, `read_email`, `read_coordinates` and `merge_locales` were all
    built and tested; the checklist said *"nothing extracts a profile page today"* and
    that was wrong. What did not exist was the step from a merged reading to a
    `TableCandidate` — which is what puts the profile columns on the approval path at
    all, and therefore into a row.
    """
    from scrapex.extract.muqawil import (
        PROFILE_FIELD_ORDER, bilingual_profile_candidate,
    )

    english, arabic = _profile_pair()
    candidate = bilingual_profile_candidate(english, arabic, contractor_id="881")

    assert candidate.approvable
    assert len(candidate.rows) == 1, "a profile is one contractor, not twenty"
    keys = [f.field_key for f in candidate.fields]
    assert keys[:len(PROFILE_FIELD_ORDER)] == list(PROFILE_FIELD_ORDER)
    assert candidate.name == "contractor_profiles"
    assert candidate.locator == "div.info-box", (
        "the locator has to name somewhere a person could go and look")


def test_a_profile_row_does_not_carry_the_listings_columns():
    """THE DEFECT THAT BLOCKED THIS. `_candidate_from` hardcoded `CARD_FIELDS` as the
    declared lead, so a profile row came out with **17 empty listing columns** —
    measured, 39 fields where the profile has 21. Every page kind has its own declared
    list, and it is now a parameter rather than a constant.

    THE COUNT WENT 21 -> 27 ON 2026-08-22 and the assertion changed shape with it. A
    bare `== 21` said only that nobody had touched the number; comparing against
    `PROFILE_FIELD_ORDER` itself says the two things that matter — the candidate carries
    exactly the declared fields, and **in the declared order**, which is load-bearing
    because `_schema_payload` puts `position` in the hash. An order that drifts is a
    different schema with identical fields, and that refused 105 pages of 120 once.
    """
    from scrapex.extract.muqawil import PROFILE_FIELD_ORDER, bilingual_profile_candidate

    english, arabic = _profile_pair()
    keys = [f.field_key
            for f in bilingual_profile_candidate(
                english, arabic, contractor_id="881").fields]

    leaked = [key for key in keys if key.startswith("card_")]
    assert not leaked, f"listing columns leaked into a profile row: {leaked}"
    assert keys == list(PROFILE_FIELD_ORDER), (
        "the candidate's fields are not the declared list in the declared order; "
        f"declared {len(PROFILE_FIELD_ORDER)}, got {len(keys)}: {keys}")


def test_the_identity_is_passed_in_and_not_parsed_out():
    """A profile is reached BY id — the crawl builds `/{lang}/contractors/{id}/143` —
    so the id is what the caller already knows. A page that failed to repeat it in its
    own body would otherwise produce a row with no identity and be refused at
    approval, and the listing uses the same key, which is what lets the two join.

    THIS USED TO PASS AN ID THE FIXTURE DOES NOT CARRY (`20044482`, where the fixture
    is contractor 881), and `OP-64`'s guard now refuses that — correctly. A page that
    links to a contractor OTHER than the one asked for is not that contractor's page:
    measured, 797 of 797 real profile snapshots link to themselves and nothing else,
    and every exception was the listing served in a profile's place.

    So the id still comes from the CALLER and is not parsed out — the row's value is
    the string handed in, and the guard only requires the page not to contradict it.
    The two rules are compatible and the arbitrary id was hiding that."""
    from scrapex.extract.muqawil import bilingual_profile_candidate

    english, arabic = _profile_pair()
    # AN INT, ON PURPOSE, and this is the property the guard nearly cost.
    #
    # The original passed `"20044482"` — an id the fixture does not carry — and
    # THAT was the proof: a value appearing nowhere on the page can only have been
    # passed in. `OP-64`'s guard refuses that page now, correctly, so the proof had
    # to be rebuilt rather than dropped. An adversarial review caught the first
    # attempt weakening it: with `contractor_id="881"` and the fixture also being
    # 881, scraping the id off the page's first href would pass every assertion.
    #
    # AND THIS PROVES ONE HALF, NOT BOTH — said plainly because the previous
    # version of this comment claimed both and a reviewer disproved it. An int
    # cannot come off a page, so `"881"` in the row proves `str()` ran. It does
    # NOT prove the value came from the caller: after `str()`, an id scraped off
    # the page's first href is the same string, and that mutation still passes.
    #
    # THE ORIGINAL PROOF IS IMPOSSIBLE BY CONSTRUCTION NOW. It worked by passing
    # an id the page does not carry, and `OP-64`'s guard exists to refuse exactly
    # that page. The two properties cannot both be tested through this function
    # any more, and pretending otherwise is worse than losing one: the companion
    # below tests the guard, this tests the conversion, and the "came from the
    # caller" half is now guarded by the guard itself — a page that names a
    # different contractor never reaches the assignment.
    row = bilingual_profile_candidate(english, arabic, contractor_id=881).rows[0]

    assert row["contractor_id"] == "881"
    assert isinstance(row["contractor_id"], str), (
        "the id reached the row without str() — an int identity breaks the join "
        "with the listing, whose contractor_id is text")


def test_a_page_that_names_a_different_contractor_is_refused():
    """The other half of the rule above, and the whole of `OP-64`.

    The id being the caller's does NOT make the page's content irrelevant. Before this
    guard, asking for contractor X and being served contractor Y produced a row labelled
    X carrying five of Y's declared columns — measured on 14 rows, twelve of them
    carrying the same stranger's values."""
    import pytest as _pytest

    from scrapex.extract.muqawil import (
        PageIsNotAProfile,
        bilingual_profile_candidate,
    )

    english, arabic = _profile_pair()
    with _pytest.raises(PageIsNotAProfile):
        bilingual_profile_candidate(english, arabic, contractor_id="20044482")


def test_the_two_silent_profile_fields_survive_the_adapter():
    """THE EMAIL AND THE COORDINATES ARE THE TWO SILENT FAILURES this module's own
    docstring names: Cloudflare XORs the address under a key that rotates per render,
    and the coordinates live in an inline script where a layout change produces no
    error, only two columns quietly going NULL. Both must arrive in the ROW, not
    merely be readable."""
    from scrapex.extract.muqawil import bilingual_profile_candidate

    english, arabic = _profile_pair()
    row = bilingual_profile_candidate(english, arabic, contractor_id="881").rows[0]

    assert "@" in str(row["organization_email"]), (
        f"the email did not survive as a decoded address: {row['organization_email']!r}")
    assert "[email" not in str(row["organization_email"]), (
        "Cloudflare's placeholder was stored instead of the address")
    assert float(row["latitude"]) == pytest.approx(24.6717, abs=0.001)
    assert float(row["longitude"]) == pytest.approx(46.3942, abs=0.001)


def test_a_profile_missing_a_box_keeps_the_same_schema():
    """The reason `PROFILE_FIELD_ORDER` is declared at all: a page that omits a box
    must not produce a different `schema_hash`, or the second profile approved is
    refused and the crawl stops at one — which is exactly what happened to the
    listing, 823 pages of it."""
    from scrapex.extract.muqawil import bilingual_profile_candidate

    english, arabic = _profile_pair()
    full = [f.field_key for f in bilingual_profile_candidate(
        english, arabic, contractor_id="881").fields]
    # Strip the whole City box out, as a contractor with no city publishes it.
    thinner = english.replace("City", "Somewhere Else", 1)
    reduced = [f.field_key for f in bilingual_profile_candidate(
        thinner, arabic, contractor_id="881").fields]

    assert reduced[:len(full)] == full, (
        "a profile with a different set of boxes declared a different schema")
