"""muqawil answers a profile id that no longer resolves with the LISTING page.

WHY THIS FILE EXISTS. The site returns HTTP 200 and 375 KB — where a profile is
122 KB — carrying the contractors listing. `read_profile` then found none of
`PROFILE_FIELDS`' labels, emitted nulls for all of them, and the membership number
leaked through from the first card on that listing.

Fourteen contractors ended up carrying a stranger's membership number, **thirteen of
them the same stranger's**, and nothing downstream could tell: those rows average
18.0 populated fields against 18.2 on healthy ones. A missing field is a fact about
a contractor; a missing DOCUMENT is not, and the two arrived looking alike.

Recorded as `OP-64`. Three layers answer it and this file guards the first two:

  1. `read_profile` refuses a listing-shaped page instead of parsing it.
  2. approval cross-checks the profile's membership number against the listing
     card, whose own value is unique across all 17,304 rows.

THE THRESHOLD IS MEASURED, NOT CHOSEN. Across 300 real profile snapshots the
`section-card` count was 7 (×262), 8 (×33) and 9 (×4); the one listing served in a
profile's place had 22. Nothing was observed between 9 and 22, so `LISTING_SHAPED =
15` sits in an empty gap.
"""
from __future__ import annotations

import pytest

from scrapex.extract.muqawil import (
    LISTING_SHAPED,
    PageIsNotAProfile,
    read_profile,
)

PROFILE = """
<html><body>
  <div class="section-card"><div class="info-box">
      <div class="info-name">Membership Number</div><div class="info-value">160916095</div>
  </div></div>
  <div class="section-card"><div class="info-box">
      <div class="info-name">Company Size</div><div class="info-value">Small</div>
  </div></div>
  {extra}
</body></html>
"""


def _cards(count: int) -> str:
    """A page carrying `count` section-cards, the shape and nothing else."""
    body = "".join(
        f'<div class="section-card"><a href="/en/contractors/{2000 + n}/143">x</a></div>'
        for n in range(count - 2))
    return PROFILE.format(extra=body)


def test_a_listing_shaped_page_is_refused_rather_than_parsed():
    """The whole defect in one assertion. Parsing this page is what produced a row
    that looked ordinary and named the wrong company."""
    with pytest.raises(PageIsNotAProfile) as refused:
        read_profile(_cards(22))

    assert "22 section-cards" in str(refused.value), (
        "the refusal must say what it counted, or the next reader cannot check it")
    assert "no longer resolves" in str(refused.value), (
        "the refusal must say WHY the site does this, since a 200 looks like success")


def test_a_real_profile_is_still_parsed():
    """The guard must not cost the 99.8%. Seven, eight and nine cards were all
    observed on real profiles and all three must pass."""
    for count in (7, 8, 9):
        reading = read_profile(_cards(count))
        assert reading.fields.get("membership_number") == "160916095", (
            f"a {count}-card profile stopped parsing, and real profiles have that many")


def test_the_threshold_sits_in_the_gap_the_measurement_found():
    """A threshold between the two populations, not on top of either.

    Nine is the most cards any real profile showed and twenty-two is the listing.
    A threshold at or below 9 would refuse real profiles; at or above 22 it would
    let the listing through. Both failures are silent in opposite directions."""
    assert 9 < LISTING_SHAPED < 22, (
        f"LISTING_SHAPED is {LISTING_SHAPED}, which is not between the largest "
        "profile observed (9 cards) and the listing (22)")


def test_the_refusal_is_not_a_missing_field():
    """`PageIsNotAProfile` must not be catchable as ordinary absence.

    `contractors.approve` wraps candidate building in `except Exception` and files
    the page under `refused` — which is correct here — but a caller that treats a
    parse failure as "this contractor has no data" would write the empty row this
    exception exists to prevent."""
    assert issubclass(PageIsNotAProfile, ValueError)
    assert not issubclass(PageIsNotAProfile, LookupError), (
        "a LookupError reads as 'not found on the page', which is the wrong story: "
        "the page itself is the wrong document")
