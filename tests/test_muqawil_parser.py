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
