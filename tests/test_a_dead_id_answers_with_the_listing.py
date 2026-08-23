"""muqawil answers a profile id that no longer resolves with the LISTING page.

WHY THIS FILE EXISTS. The site returns HTTP 200 and ~373 KB — where a profile averages
118 KB — carrying the contractors listing. `read_profile` then matches THREE of the
eleven `PROFILE_FIELDS` labels that a listing card happens to share (Membership Number,
Company Size, Training credit hours), and `fields[key] = value` is LAST-WINS over every
`div.info-box` pair on the page, so the values come from the LAST card on that listing.

Counted rather than sampled: **39 contractor ids** were served the listing across 78
snapshots, both locales for each. 14 produced a row; 25 produced none. Each of the 14
carries FIVE declared columns belonging to a stranger — `membership_number`,
`company_size`, `company_size_ar`, `training_credit_hours`, `training_credit_hours_ar` —
and twelve of the fourteen took the same stranger's. `address`, `organization_email` and
the coordinates are null. Nothing downstream could tell: 18.0 populated fields against
18.2 on a healthy row. Recorded as `OP-64`.

WHAT THIS FILE GUARDS, AND WHAT IT DOES NOT. It guards layer 1 — `read_profile` refusing
the wrong document. Layers 2 and 3 (the approval cross-check, and `--impostors`) are
guarded in `tests/test_the_two_pages_must_agree.py`.

THE FIRST VERSION OF THIS GUARD COUNTED `section-card` AND BOTH ITS NUMBERS WERE WRONG.
It thresholded at 15, justified by "7-9 on a profile, 22 on the listing, nothing
between". An adversarial review found 160 real listing pages carrying FEWER than 15 cards
— the last page of every filtered slice — so the gap did not exist on the side being
guarded against. And the 7-9 census had been taken with a REGEX while the parser uses
BeautifulSoup, which does not expose the `section-card` inside a `<script>` template:
through `select` a real profile has SIX. Measured with the wrong instrument, defended
with a gap that was not there.

WHAT REPLACED IT NEEDS NO THRESHOLD. A profile page links to exactly ONE contractor —
itself. Measured through `soup.select`, the path the parser takes:

    800 real profile pages (400 EN + 400 AR)    distinct contractor links: min 1, max 1
    400 listing pages                           distinct contractor links: min 3, max 20

And when the caller passes the id — which every production caller does, because the crawl
built the URL from it — the test is exact rather than statistical: a page linking to
anyone ELSE is not that contractor's page, whatever its shape or card count.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from scrapex.extract.muqawil import (
    ONE_CONTRACTOR,
    PageIsNotAProfile,
    read_profile,
)

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "muqawil"
PROFILE_EN = (FIXTURES / "profile-en.html").read_text(encoding="utf-8")
LISTING_EN = (FIXTURES / "listing-en.html").read_text(encoding="utf-8")


def _only_id(html: str) -> str:
    """The contractor a committed profile fixture is about."""
    found = re.search(r"/(?:en|ar)/contractors/(\d+)/", html)
    assert found, "the profile fixture no longer names a contractor"
    return found.group(1)


# ---- the real documents, from the committed fixtures -------------------------

def test_the_real_listing_fixture_is_refused_when_a_profile_was_asked_for():
    """A REAL listing page, not a synthetic one with the right card count.

    The previous version built `_cards(22)` — twenty-two bare divs each holding one
    link. It could prove the counter fired and could not reach the defect: the wrong
    data was written by last-wins over 160 `div.info-box` pairs, which a fixture of
    bare divs does not have."""
    with pytest.raises(PageIsNotAProfile) as refused:
        read_profile(LISTING_EN, contractor_id="20008518")

    message = str(refused.value)
    assert "other than 20008518" in message, (
        "the refusal must name the id that was asked for, or a reader cannot check it")
    assert "no longer resolves" in message, (
        "the refusal must say WHY the site does this, since a 200 looks like success")


def test_the_real_profile_fixture_still_parses():
    """The guard must not cost the 99.8%."""
    reading = read_profile(PROFILE_EN, contractor_id=_only_id(PROFILE_EN))
    assert reading.fields, "a real profile stopped parsing"


def test_a_profile_is_refused_for_the_wrong_contractor():
    """THE CASE A CARD COUNT CANNOT REACH, and the reason the id is threaded down.

    This page is a perfectly ordinary profile — the right shape, the right size, six
    cards. It is simply somebody else's. A count says nothing about it; the id says
    everything. The filtered listing whose last page holds one card is the same
    problem wearing the other hat."""
    with pytest.raises(PageIsNotAProfile):
        read_profile(PROFILE_EN, contractor_id="99999999")


def test_without_an_id_the_check_is_weaker_and_still_holds():
    """`contractor_id` is optional for tests and ad-hoc reads. The fallback asks how
    many contractors the page is about, which still separates the two documents —
    1 against 3-to-20 — but cannot catch a profile belonging to the wrong one."""
    assert read_profile(PROFILE_EN).fields, "the fallback refused a real profile"
    with pytest.raises(PageIsNotAProfile) as refused:
        read_profile(LISTING_EN)
    assert "contractors, and a profile is about" in str(refused.value)


def test_the_fallback_boundary_is_one_and_not_a_measured_gap():
    """A profile is about ONE contractor. This is the definition, not a percentile —
    which is the difference between this guard and the one it replaced."""
    assert ONE_CONTRACTOR == 1


def test_the_refusal_is_not_a_missing_field():
    """`PageIsNotAProfile` must not read as ordinary absence.

    `contractors.approve` wraps candidate building in `except Exception` and files the
    page under `refused`, which is correct. A caller that treated a parse failure as
    "this contractor has no data" would write the empty row this exception prevents."""
    assert issubclass(PageIsNotAProfile, ValueError)
    assert not issubclass(PageIsNotAProfile, LookupError), (
        "a LookupError reads as 'not found on the page', which is the wrong story: "
        "the page itself is the wrong document")
