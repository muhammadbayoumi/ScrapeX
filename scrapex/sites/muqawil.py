"""muqawil.org — the Saudi Contractors Authority's public contractor directory.

Step 3 of docs/GENERIC-FETCH-SEAM.md, and the first concrete `PageSource` this
project has. Everything here is about THIS SITE'S LAYOUT and nothing else: no
fetching, no pacing, no request counting, no database. All of that belongs to
`scrapex/pagewalk.py`, and it belongs there so that every site behaves the same
way about the things that are not about the site.

WHAT WAS MEASURED, 2026-08-16, and why each measurement is load-bearing. The
full record is `docs/CONTRACTOR-SOURCE.md`; these four decide the code:

  * The listing is `?page=1..865`, TWENTY rows a page, and **no page-size
    parameter is honoured** — `per_page`, `perPage`, `limit`, `size`,
    `page_size` and `take` were each tried at 60 and each answered twenty. So
    the page count is the crawl's whole bound and cannot be traded down.

  * A profile is `/{lang}/contractors/{id}/{143}`. The trailing segment plays NO
    part in identity — `/881/1` and `/881/999` return the same contractor — but
    `143` is what makes the self-build price section render at all. Diffing the
    two, the only difference was `العقود سعر البناء (برنامج البناء الذاتي)`
    appearing under `143` and vanishing under `999`. A crawl that treated the
    segment as noise would ship three of the owner's columns permanently empty
    and nothing would say so. It is a literal here, deliberately.

  * A contractor card is `div.section-card`, and there are TWENTY-ONE of them on
    a listing page. The twenty-first is not a contractor. Cards are therefore
    selected by holding a profile link, never by counting.

  * Cloudflare fronts the site and does NOT block: a plain HTTP fetch with
    ScrapeX's own user agent answers 200 with the full body and no interstitial.
    No browser is needed, which is an order of magnitude off the crawl's cost.
"""
from __future__ import annotations

import re
from collections.abc import Iterable

from bs4 import BeautifulSoup

from ..pagesource import FetchedPage, SliceNotSupported

#: The trailing path segment that makes a profile render its self-build prices.
#: A literal because it is one, and named because `143` in a URL template is the
#: kind of number a later reader deletes as noise. See the module docstring.
SELF_BUILD_SEGMENT = "143"

#: Both locales, because the `[ar]` half of every column comes from the second.
#: The owner's reason: the Data page switches language behind one toggle, so a
#: row that carries only one language cannot be shown in the other.
LOCALES = ("en", "ar")

#: A profile link, in either locale. The id is the identity; the tail is not.
_PROFILE = re.compile(r"/(?:en|ar)/contractors/(\d+)/\d+")

#: The city, keyed by the ICON and never by the label beside it. The Arabic page
#: spells the membership-number label `رقم العضويه` — with `ه`, not `ة` — and a
#: label-matched selector breaks on a spelling difference no reader would ever
#: notice. The icon class is identical in both locales, which makes it the only
#: honest key. `icon-locaion` is THEIR spelling of "location"; it is matched
#: exactly, and the day they fix it this selector is what will say so.
_CITY_ICON = "icon-locaion"


def read_last_page(html: str) -> int:
    """The highest page number the listing's own pagination links to.

    READ, NEVER ASSUMED. 865 was true on 2026-08-16 and a directory grows; a
    constant here would quietly stop crawling the tail the week it changed. The
    caller reads page one, calls this, and only then builds the source — which
    is why `MuqawilPageSource` demands the number instead of defaulting it.
    """
    pages = [int(found) for found in re.findall(r"[?&]page=(\d+)", html)]
    if not pages:
        raise ValueError(
            "no pagination on this listing page, so the crawl's size is "
            "unknown — refusing to guess it. Check the page really is a "
            "contractor listing before treating this as a layout change.")
    return max(pages)


def _cards(page: FetchedPage) -> list:
    """Every contractor card on a listing page, in the order it is published.

    SELECTED BY HOLDING A PROFILE LINK. `div.section-card` matches twenty-one
    elements and only twenty are contractors, so a slice keyed on position would
    be off by one for every row after the impostor.
    """
    soup = BeautifulSoup(page.html, "html.parser")
    return [card for card in soup.select("div.section-card")
            if card.find("a", href=_PROFILE)]


class MuqawilPageSource:
    """What muqawil.org knows about its own pages."""

    site_key = "muqawil.org"

    def __init__(self, *, last_page: int, locales: Iterable[str] = LOCALES) -> None:
        """`last_page` is REQUIRED, and that is the point.

        A default would let a caller crawl page one, get twenty contractors out
        of seventeen thousand, and have nothing tell them the other 864 pages
        were never asked for. `read_last_page` is how the number is obtained.
        """
        if last_page < 1:
            raise ValueError(f"last_page must be at least 1, got {last_page}")
        self._last_page = last_page
        self._locales = tuple(locales)

    def listing_urls(self, base_url: str) -> Iterable[str]:
        """Every listing page, in both locales, page by page rather than locale
        by locale.

        THE ORDER IS DELIBERATE: `en?page=1`, `ar?page=1`, `en?page=2`, … so a
        crawl stopped half way holds BOTH languages for the pages it reached,
        rather than every English page and no Arabic one. The owner's columns
        come in pairs; half a pair is not half a row, it is an unusable one.
        """
        base = base_url.rstrip("/")
        for page in range(1, self._last_page + 1):
            for locale in self._locales:
                yield f"{base}/{locale}/contractors?page={page}"

    def detail_urls(self, page: FetchedPage) -> Iterable[str]:
        """The profile of every contractor this listing page names, in both
        locales, deduplicated by contractor id.

        The id is taken from the href and the tail is REBUILT as
        `SELF_BUILD_SEGMENT` rather than carried over — the site's own links use
        it today, and rebuilding means a page that ever links some other value
        still gets crawled at the one that renders every section.
        """
        base = _origin(page.url)
        seen: list[str] = []
        for card in _cards(page):
            link = card.find("a", href=_PROFILE)
            found = _PROFILE.search(link["href"])
            if found is None or found.group(1) in seen:
                continue
            seen.append(found.group(1))
        for contractor_id in seen:
            for locale in self._locales:
                yield (f"{base}/{locale}/contractors/"
                       f"{contractor_id}/{SELF_BUILD_SEGMENT}")

    def belongs_to_slice(self, page: FetchedPage, row_index: int,
                         slice_of: str) -> bool:
        """Whether one row of this listing is in the named city.

        ANSWERED FROM THE LISTING, which is what makes the slice scope worth
        having: muqawil publishes the city on the card, so one city's profiles
        can be crawled without fetching the other sixteen thousand.

        The slice must be named in the SAME LANGUAGE as the page — `RIYADH` for
        an English listing, `الرياض` for an Arabic one. Translating here would
        mean shipping a city gazetteer and getting it wrong for the first city
        nobody thought of.
        """
        if not slice_of.strip():
            raise SliceNotSupported(
                "a slice of muqawil is a city and no city was named")

        cards = _cards(page)
        if row_index >= len(cards):
            return False

        icon = cards[row_index].select_one(f".info-icon span.{_CITY_ICON}")
        if icon is None:
            # The card carries no city. NOT an answer of False, which would
            # quietly drop a contractor from every slice and read as a smaller
            # city rather than as a layout that moved.
            raise SliceNotSupported(
                f"no {_CITY_ICON} on card {row_index} of {page.url} — the "
                "listing's city marker has moved, and a slice cannot be "
                "chosen from a page that no longer publishes one")

        box = icon.find_parent(class_="info-box")
        value = box.select_one(".info-value") if box else None
        return _city_of(value) == slice_of.strip().casefold()


def _city_of(value) -> str:
    """The city out of the card's location cell, folded for comparison.

    ONE CELL HOLDS TWO FACTS. The card publishes city and region together,
    separated by a dash and a great deal of whitespace:

        RIYADH
                                    - Riyadh

    and in Arabic `الرياض - الرياض`, where the two happen to be the same word.
    So the cell is not the city — the head of it is. Whitespace is collapsed
    first, because the separator is only recognisable once it is.

    The split is on the FIRST dash, which assumes no Saudi city name carries
    one. That held for every city seen (RIYADH, JEDDAH, DAMMAM, AL KHOBAR); if
    one ever does, this is the line that will be wrong, and it is written here
    rather than left as an accident of a regex.
    """
    if value is None:
        return ""
    text = " ".join(value.get_text(" ", strip=True).split())
    return text.split("-", 1)[0].strip().casefold()


def _origin(url: str) -> str:
    """`https://host` from any URL on it, without importing urllib for one job."""
    parts = url.split("/", 3)
    return "/".join(parts[:3]) if len(parts) >= 3 else url.rstrip("/")
