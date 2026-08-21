"""The slice scope was built, tested, never used — and wrong.

WHAT WAS WRONG, MEASURED ON A STORED PAGE BEFORE ANYTHING WAS CHANGED.
`belongs_to_slice` indexes ROWS of a listing. `detail_urls` yields URLs. Every caller
paired them with `enumerate(detail_urls(page))`, which is correct exactly when a page
yields one URL per row — and muqawil yields **one per locale**:

    cards       17
    detail URLs 34
    url index 1 → card 1, but url 1 is contractor 0's ARABIC page
    17 of the 34 indices pointed past the last card

So under `LISTING_PLUS_SLICE` the crawl would have asked the wrong card about every URL
but the first, and silently dropped the seventeen that overshot. **The result is neither
the slice nor its complement**, and it reads as a smaller city rather than as a defect.

Nothing caught it because nothing used it: muqawil is registered `listing_only`, and the
fakes in the walker's own tests yield one URL per row, which is the case the assumption
happens to fit.

THE FIX IS IN TWO HALVES, AND THE SECOND IS WHY THIS CANNOT COME BACK.

  * `detail_rows` — the source pairs each URL with the row it came from, and
    `slice_rows` asks for it. Optional, because most sources publish one URL per row
    and `test_a_fake_site_satisfies_the_protocol` is right that a Protocol nothing can
    implement is a design rather than a seam.
  * `belongs_to_slice` REFUSES a row index past its last row, where it used to answer
    `False`. That is the only place the row count is known, so it is the only place the
    guard can live — and it turns any future re-guess into a loud failure instead of a
    quiet half-crawl.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from scrapex.pagesource import FetchedPage, PageKind, SliceNotSupported, slice_rows
from scrapex.sites.muqawil import MuqawilPageSource, _cards, read_ids

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "muqawil"


def _page(name: str = "listing-en.html") -> FetchedPage:
    """The committed listing, which is a real trimmed page from the site."""
    return FetchedPage(url="https://muqawil.org/en/contractors?page=1",
                       html=(FIXTURES / name).read_text(encoding="utf-8"),
                       kind=PageKind.LISTING)


def _id_in(url: str) -> str:
    return url.rsplit("/contractors/", 1)[1].split("/")[0]


# ---- the pairing ---------------------------------------------------------------

def test_the_page_really_does_yield_more_urls_than_rows():
    """THE PREMISE, asserted so the tests below cannot pass on a single-locale page.

    Without this, a fixture that happened to carry one locale would make every
    assertion here vacuously true — which is exactly how the defect survived in the
    walker's own tests.
    """
    page = _page()
    source = MuqawilPageSource(last_page=871)

    cards = _cards(page.html)
    urls = list(source.detail_urls(page))

    assert len(cards) >= 2
    assert len(urls) == len(cards) * 2, "one URL per locale is the whole difficulty"


def test_every_url_is_paired_with_its_own_row():
    page = _page()
    source = MuqawilPageSource(last_page=871)
    ids = read_ids(page.html)

    rows = slice_rows(source, page)

    assert len(rows) == len(list(source.detail_urls(page)))
    wrong = [(index, url) for index, url in rows if ids[index] != _id_in(url)]
    assert wrong == [], "a URL paired with a different contractor's row"


def test_no_row_index_points_past_the_last_row():
    """The half that was being dropped. Seventeen of thirty-four, on a real page."""
    page = _page()
    source = MuqawilPageSource(last_page=871)

    highest = max(index for index, _ in slice_rows(source, page))

    assert highest < len(_cards(page.html))


def test_the_old_assumption_is_the_one_that_fails():
    """PINS THE REASON, not just the fix. `enumerate(detail_urls(page))` is what every
    caller used to write, and this is the assertion that it cannot be gone back to."""
    page = _page()
    source = MuqawilPageSource(last_page=871)
    ids = read_ids(page.html)

    guessed = list(enumerate(source.detail_urls(page)))

    mismatched = [i for i, url in guessed
                  if i >= len(ids) or ids[i] != _id_in(url)]
    assert len(mismatched) > len(guessed) // 2, (
        "the old pairing was wrong for more than half the URLs; if this now passes, "
        "the page has changed shape and these tests need re-measuring")


# ---- and the guard that makes a re-guess loud ---------------------------------

def test_a_row_that_does_not_exist_is_refused_and_not_answered_false():
    """IT USED TO RETURN `False`. That is what made the overshoot invisible: seventeen
    contractors dropped out of the slice and the answer looked like a small city."""
    page = _page()
    source = MuqawilPageSource(last_page=871)
    past_the_end = len(_cards(page.html)) + 5

    with pytest.raises(SliceNotSupported) as raised:
        source.belongs_to_slice(page, past_the_end, "RIYADH")

    said = str(raised.value)
    assert "does not exist" in said
    assert "detail_rows" in said, "the message must name the fix"


def test_a_real_row_still_answers_the_slice_question():
    """The guard must not have turned every question into a refusal."""
    page = _page()
    source = MuqawilPageSource(last_page=871)

    answers = [source.belongs_to_slice(page, index, "RIYADH")
               for index in range(len(_cards(page.html)))]

    assert all(isinstance(one, bool) for one in answers)
    assert any(answers), "the committed listing has at least one Riyadh contractor"


# ---- the default, for the sources that never needed this ----------------------

class _OneUrlPerRow:
    """The shape every other source has: one detail page per listing row."""

    site_key = "one_per_row"

    def detail_urls(self, page):
        return ["https://e.test/a", "https://e.test/b", "https://e.test/c"]


def test_a_source_with_one_url_per_row_needs_no_pairing_method():
    """`detail_rows` IS OPTIONAL ON PURPOSE. Requiring it would make the Protocol
    demand a method whose only possible implementation is `enumerate`, and
    `test_a_fake_site_satisfies_the_protocol` already says why that is wrong."""
    assert slice_rows(_OneUrlPerRow(), _page()) == [
        (0, "https://e.test/a"), (1, "https://e.test/b"), (2, "https://e.test/c")]


def test_the_resume_wrapper_forwards_the_pairing():
    """FORGETTING THIS WOULD HAVE BEEN SILENT AND PRODUCTION-ONLY. The wrapper hides
    already-stored listing URLs from a resume and delegates everything else; a
    `detail_rows` it did not forward would send `slice_rows` to its `enumerate` default
    for the wrapped source — which is the only source production ever slices.
    """
    from scrapex.partitioncrawl import _Unstored

    page = _page()
    inner = MuqawilPageSource(last_page=871)

    wrapped = _Unstored(inner, frozenset())

    assert slice_rows(wrapped, page) == slice_rows(inner, page)
