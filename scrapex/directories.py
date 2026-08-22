"""Directory sources, declared — so the second one needs no new module.

WHY THIS EXISTS. `REQ-27`, in his words: «علشان لما اديك مصدر لمقاولين تانى فى
المستقبل منخترعش الذرة نكمل على الى موجود بالمثل كالمنتجات اعتقد انها مستقرة الى حد
ما». And the wheel in question was one shipped the same morning: `contractors.py`
hardcoded muqawil in four places —

    BASE = "https://muqawil.org"     DATASET = "contractors"
    SITE_NAME = "Saudi Contractors Authority"     partition = MuqawilPartition()

— so a second contractor directory would have needed a copy of the file. That is
said plainly because it is a defect introduced hours earlier: `REQ-24` closed a real
gap (no user could run any crawl) and closed it by hardcoding the one site we had.

HE IS RIGHT THAT PRODUCTS ARE THE SHAPE TO COPY. A products source is a contract
entry naming a `family`, and `build_connector(entry)` returns its collector, so a
second Shopify shop needs no new module. This is the same split for the
`contractors` category:

    products     entry -> family -> build_connector    (scrapex/connectors/factory.py)
    contractors  key   -> Directory -> its partition   (this module)

WHAT IS **NOT** DUPLICATED HERE, and it is most of the work: the crawl itself. The
engine is already protocol-shaped — `partitioncrawl.PartitionedListing` is a
`Protocol`, and `pagesource`, `sightings`, `snapshotcrawl` and `extract/service` key
on a dataset rather than a site. Their muqawil mentions are docstrings citing where a
number was measured, not code. So a second directory supplies four facts and a
partition, and inherits the provable crawl, the sightings ledger, the resume and the
approval-from-disk unchanged.

WHY A DICT AND NOT A PLUGIN SYSTEM. There is one directory today and a second is
hypothetical. A registry that can be read at a glance is worth more than an entry
point mechanism nobody has needed yet; when a directory arrives that this shape
cannot express, THAT is the evidence for changing the shape. `A3` — no abstraction
until a second case proves it — cuts both ways, and this is the smallest thing that
removes the copy-the-file failure.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Directory:
    """One directory source: the four facts a crawl needs, plus its partition.

    FROZEN, AND `partition` IS BUILT PER ACCESS rather than stored. A
    `PartitionedListing` is cheap to construct and holding one on a module-level
    constant would share it across runs — which is fine today and is exactly the kind
    of accidental sharing that becomes a bug the first time one carries state.
    """

    #: Matches `site_profile.site_key`, which is how a crawl finds its scope, and is
    #: what `--source` names on the command line.
    key: str
    display_name: str
    base_url: str
    #: The dataset the rows land in. Separate from `key` because one site can publish
    #: more than one dataset — muqawil publishes contractors AND their profiles.
    dataset_key: str
    #: Which field the owner's approval marks as the identity. Named per directory
    #: because it is the site's own id column, not a convention.
    identity_field: str
    #: `(english_html, arabic_html) -> TableCandidate`.
    candidate: Callable[..., Any]
    #: `() -> PartitionedListing`.
    partition_factory: Callable[[], Any] = field(repr=False)
    #: How this directory's DETAIL pages are read, or `None` for a directory whose
    #: detail pages nothing interprets yet. Separate from `candidate` because a listing
    #: card and a profile page are two different documents with two different declared
    #: field sets — `CARD_FIELDS` against `PROFILE_FIELD_ORDER` — and one callable
    #: taking both would have to guess which it was handed.
    profiles: ProfileReader | None = None

    def partition(self) -> Any:
        return self.partition_factory()


@dataclass(frozen=True)
class ProfileReader:
    """Everything needed to turn one directory's DETAIL pages into rows and memberships.

    THREE CALLABLES AND A NAME, and they are grouped because they are useless apart: the
    candidate produces the flat row, the groups say what repeats, and the locator finds
    each group on the page. `R-41` put the declaration in the site's own module, so this
    carries references to it rather than copies of it.

    THE SCHEME NAME IS HERE AND NOT IN `taxonomy.py` because it is the SITE's vocabulary
    — `classification_scheme.scheme_type='source'` says so — and the module that stores
    trees has no business naming one site's.
    """

    #: `(english_html, arabic_html, *, contractor_id) -> TableCandidate`.
    candidate: Callable[..., Any]
    #: The declared multi-valued groups, from `R-41`'s map.
    groups: tuple[Any, ...]
    #: `(html, group_key) -> element | None`.
    locate: Callable[..., Any]
    #: What the site calls its own vocabulary, in both languages.
    scheme_name: str
    scheme_name_ar: str
    #: ITS OWN DATASET, AND THIS IS NOT A DETAIL. A profile publishes 21 declared fields
    #: and a listing card 28, so putting both under one `dataset_key` makes every profile
    #: look like a SUBSET of the approved listing schema — which `R-31` correctly refuses,
    #: or worse would retire the listing's live version and drop columns the site still
    #: publishes. `Directory.dataset_key`'s own comment already said a site can publish
    #: more than one dataset; this is that sentence being true.
    dataset_key: str = "contractor_profiles"
    dataset_name: str = "Contractor profiles"


def _muqawil() -> Directory:
    # Imported inside the function so a `directories` import does not drag the whole
    # muqawil parser in. It matters for the CLI: `cli.py` builds its parser on every
    # invocation, and `scrapex status` should not pay for a parser it never uses.
    from .extract.muqawil import (
        MULTI_VALUED_GROUPS,
        bilingual_listing_candidate,
        bilingual_profile_candidate,
        locate_group,
    )
    from .sites.muqawil import MuqawilPartition

    return Directory(
        key=MuqawilPartition.site_key,
        display_name="Saudi Contractors Authority",
        base_url="https://muqawil.org",
        dataset_key="contractors",
        identity_field="contractor_id",
        candidate=bilingual_listing_candidate,
        partition_factory=MuqawilPartition,
        profiles=ProfileReader(
            candidate=bilingual_profile_candidate,
            groups=MULTI_VALUED_GROUPS,
            locate=locate_group,
            # THE SITE'S OWN WORDS. `Interests` in English and `الأنشطة` in Arabic,
            # which `R-41` measured are not translations of each other — so both are
            # recorded rather than one being derived from the other.
            scheme_name="Interests",
            scheme_name_ar="الأنشطة",
            dataset_key="contractor_profiles",
            dataset_name="Contractor profiles"),
    )


#: Every directory this build can crawl. Keyed by `site_key`, because that is what
#: the warehouse joins on and what the crawl's scope lookup uses.
BUILDERS: dict[str, Callable[[], Directory]] = {
    "muqawil_org": _muqawil,
}

#: The one there is. A default keeps every command line that predates `--source`
#: working, including a crawl running right now.
DEFAULT_KEY = "muqawil_org"


def keys() -> tuple[str, ...]:
    return tuple(sorted(BUILDERS))


def get(key: str | None = None) -> Directory:
    """The directory named, or the only one there is.

    REFUSED BY NAME rather than falling back to the default, because a mistyped
    `--source` that silently crawled muqawil would spend hours collecting the wrong
    site and report success — the same reasoning `--only` refuses an unknown cell
    label instead of ignoring it.
    """
    wanted = key or DEFAULT_KEY
    build = BUILDERS.get(wanted)
    if build is None:
        raise KeyError(
            f"{wanted!r} is not a directory this build can crawl. Known: "
            f"{', '.join(keys())}. A new directory is a `Directory` in "
            "scrapex/directories.py — four facts and a partition; the crawl itself "
            "is inherited.")
    return build()
