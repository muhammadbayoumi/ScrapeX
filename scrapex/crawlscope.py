"""How much of a site a crawl is allowed to fetch, chosen per source.

THIS IS AN OWNER DECISION, NOT A PROJECT ONE (2026-08-05), and the numbers are
why. Measured on muqawil.org, the first entity source:

    the listing            860 pages     14 minutes at the shipped 1s pace
    every detail page    121,157 requests    34 hours at 1s, 17 at 0.5s

Fourteen minutes and thirty-four hours are not two settings of one product; they
are two products. And change-tracking means repeating whichever was chosen, so
the difference is not paid once. Which of them a user wants is theirs to say.

NOT `ExtractScope`, WHICH ALREADY EXISTS AND MEANS SOMETHING ELSE.
`vocab.ExtractScope` is CONTRACT WIDTH for a price payload — TARGETED, CENSUS,
LATEST_ONLY — and it answers "how many fields may this payload carry". This
answers "how many pages may this crawl fetch". Two unrelated questions, and
giving them one name would make every later reader work out which was meant.

MUQAWIL IS THE EXAMPLE, NOT THE RULE. It happens to publish grade, status,
rating and city on the listing page itself, so LISTING_ONLY may be its whole
answer — a fact about one site, discovered when it is added, never a default the
schema assumes on another site's behalf.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class CrawlScope(StrEnum):
    """How deep a crawl of one source goes."""

    #: The fields the listing pages already show, and nothing else. On a site
    #: that publishes what matters in its listing, this is the whole product.
    LISTING_ONLY = "listing_only"

    #: The listing, plus detail pages for a slice the user names — a city, a
    #: grade. The slice is what makes this affordable; without one it is the
    #: same thirty-four hours under a gentler word.
    LISTING_PLUS_SLICE = "listing_plus_slice"

    #: One founding crawl of everything, then the listing catches the changes.
    #: The expensive pass happens ONCE and deliberately, rather than on every
    #: run — which is the only way "everything" is affordable to track.
    FULL_THEN_LISTING = "full_then_listing"


#: What a source gets if nobody chose. The cheapest of the three ON PURPOSE: a
#: default that costs thirty-four hours is a default that runs before anyone has
#: understood what they asked for.
DEFAULT = CrawlScope.LISTING_ONLY


@dataclass(frozen=True)
class Plan:
    """What a scope means for one crawl, in numbers the caller can act on."""

    scope: CrawlScope
    listing_pages: int
    detail_pages: int
    #: The slice the user named, when the scope needs one.
    slice_of: str = ""

    @property
    def requests(self) -> int:
        return self.listing_pages + self.detail_pages

    def seconds_at(self, pace_s: float) -> float:
        return self.requests * pace_s

    def hours_at(self, pace_s: float) -> float:
        return self.seconds_at(pace_s) / 3600


class SliceRequired(ValueError):
    """LISTING_PLUS_SLICE was chosen without naming the slice.

    Refused rather than defaulted, because the obvious default — every detail
    page — is exactly the thirty-four hours the scope exists to avoid, and it
    would arrive labelled as the cheap option.
    """


def plan(scope: CrawlScope, *, listing_pages: int, detail_pages: int,
         slice_pages: int = 0, slice_of: str = "") -> Plan:
    """Turn a scope and a site's measured size into what a crawl will cost.

    The caller supplies the measurements because only the caller has them:
    860 pages is a fact about muqawil, discovered by looking, and this module
    must never carry one site's numbers as if they were every site's.
    """
    if scope is CrawlScope.LISTING_ONLY:
        return Plan(scope, listing_pages, 0)

    if scope is CrawlScope.LISTING_PLUS_SLICE:
        if not slice_of:
            raise SliceRequired(
                "listing_plus_slice needs the slice named — a city, a grade. "
                "Without one the only honest reading is 'every detail page', "
                "which is the whole crawl under a cheaper-sounding name.")
        return Plan(scope, listing_pages, slice_pages, slice_of)

    return Plan(scope, listing_pages, detail_pages)


def is_expensive(plan: Plan, *, pace_s: float, over_hours: float = 1.0) -> bool:
    """Whether this crawl is long enough that a user should be told first.

    Not a refusal — the owner may genuinely want the thirty-four hours, and
    FULL_THEN_LISTING exists precisely so they can have it. It is the difference
    between a choice and a surprise.
    """
    return plan.hours_at(pace_s) > over_hours
