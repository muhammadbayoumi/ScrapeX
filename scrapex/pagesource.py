"""What one site knows about its own pages, and nothing else.

Step 1 of docs/GENERIC-FETCH-SEAM.md. No network, no database, no parsing —
this file is the shape of the agreement, and the walker and the site both have
to fit it before either is written.

WHY NOT `SiteConnector`. That protocol is the price pipeline: it returns
`ScrapedTable`, which becomes a `FunnelPayload` of priced offers. A generic
source has no offers. What a page MEANS is decided later, by the schema the
owner approved against a stored snapshot — so what a generic source hands over
is a page, not an interpretation of one. A muqawil connector written against
`SiteConnector` would compile, pass, and put nothing in the generic tables.

WHAT A `PageSource` MAY NOT DO, and the boundary matters more than the methods:
it may not fetch, pace itself, count requests, decide how deep to go, or touch
the database. All of that is the walker's, and it is the walker's precisely so
that every site behaves the same way about the things that are not about the
site. A `PageSource` that reaches past this line is the reason two sources will
one day differ for no reason anybody can name.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable, Protocol, runtime_checkable


class PageKind(StrEnum):
    """Which of a site's two kinds of page this is.

    A string would have done, and would have let `"listings"` or `"Detail"`
    through to be compared against `"listing"` and quietly never match — the
    walker gates the two kinds differently, so a typo there is a crawl that
    silently fetches nothing.
    """

    #: Paginated, and the only kind that is. Carries the rows.
    LISTING = "listing"

    #: One entity. Reached from a listing, never paginated.
    DETAIL = "detail"


@dataclass(frozen=True)
class FetchedPage:
    """One page as it arrived, before anyone has decided what it means.

    FROZEN, AND HOLDING THE HTML UNPARSED. The whole seam rests on this: the
    walker stores exactly this, and interpretation happens later against the
    stored copy. A parse that turns out wrong is re-run without re-fetching —
    which on a source measured at thirty-four hours is the product, not an
    optimisation.
    """

    url: str
    html: str
    kind: PageKind

    def __post_init__(self) -> None:
        if not self.url:
            raise ValueError("a fetched page with no url cannot be stored: "
                             "save_snapshot needs it to say where this came from")


class SliceNotSupported(NotImplementedError):
    """This site cannot decide slice membership from its listing pages.

    Raised rather than answered False, and the difference is the point. False
    means "this row is not in the slice"; a site that cannot tell would then
    return False for every row and produce an EMPTY crawl that looks like a
    successful one. Refusing says the scope is not available here, which the
    owner can act on.
    """


@runtime_checkable
class PageSource(Protocol):
    """One site's knowledge of its own layout."""

    #: Matches `site_profile.site_key`, which is how a crawl finds its scope.
    site_key: str

    def listing_urls(self, base_url: str) -> Iterable[str]:
        """The listing pages, in order.

        muqawil: `?page=1` through `?page=860`. Yielded rather than returned as
        a list where a site can manage it, so a listing whose length is only
        discoverable by reading page one does not have to lie about its size
        before it has looked.
        """

    def detail_urls(self, page: FetchedPage) -> Iterable[str]:
        """The detail links this listing page points at."""

    def belongs_to_slice(self, page: FetchedPage, row_index: int,
                         slice_of: str) -> bool:
        """Whether one row of this listing page is in the named slice.

        ANSWERED FROM THE LISTING, which is the whole reason the slice scope is
        affordable: muqawil publishes city and grade on the listing page, so a
        slice is chosen without fetching a single detail page. A site that
        cannot answer must raise SliceNotSupported.
        """


def supports_slices(source: PageSource, *, base_url: str = "") -> bool:
    """Whether LISTING_PLUS_SLICE can be offered for this site at all.

    Asked with an EMPTY page rather than by inspecting the class, because a
    site can implement the method and still not be able to answer — the
    inability lives in the site's HTML, not its type. The walker uses this to
    refuse the scope up front instead of half-way through a crawl.
    """
    try:
        source.belongs_to_slice(
            FetchedPage(url=base_url or "about:blank", html="",
                        kind=PageKind.LISTING),
            0, "")
    except SliceNotSupported:
        return False
    except Exception:                      # noqa: BLE001
        # Any other failure on an empty page says nothing about whether the
        # site can slice a real one. Only an explicit refusal counts.
        return True
    return True
