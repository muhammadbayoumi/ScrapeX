"""What a source can be asked to do — ONE declaration, read by the engine and the panel.

`REQ-45`: five of the panel's six source actions answered 404 for muqawil, because
`extension/app.js` carried its own retyped list of what a source can do. A retyped
list goes stale in the safe-looking direction, so the passes, their cost, what they
write and the hover line the user reads are declared here and served by
`GET /api/dry/{source_key}`.

THE HOVER IS COMPOSED, NEVER WRITTEN. `Pass.hover` is built from the same fields the
payload carries, so a hover cannot promise one cost while `network` states another.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .connectors.factory import _BUILDERS, supports_history
from .crawlscope import CrawlScope
from .directories import Directory
from .vocab import RunMode

#: The passes a DIRECTORY source has. `contractors.validate` reads this tuple, so a
#: seventh pass cannot reach the command line without appearing here.
DIRECTORY_PASSES: tuple[str, ...] = (
    "plan", "crawl", "details", "approve", "coverage", "impostors",
    "reapprove_schema")


@dataclass(frozen=True)
class Pass:
    """One thing a source can be asked to do, and what it costs to ask.

    `network` is a count where the code fixes one and `None` where it depends on a
    frontier only a run can size; `network_phrase` is what the user reads either way.
    """

    key: str
    label: str
    #: What it does, one clause, no trailing stop. The first half of the hover.
    does: str
    #: The tables it writes, or empty for a pass that writes nothing.
    writes: tuple[str, ...] = ()
    network: int | None = 0
    network_phrase: str = "zero requests"
    #: Why it cannot run now, in words the user can act on, or None.
    blocked_by: str | None = None

    @property
    def hover(self) -> str:
        wrote = ("writes nothing" if not self.writes
                 else "writes " + ", ".join(self.writes))
        line = f"{self.does} — {self.network_phrase}, {wrote}."
        if self.blocked_by:
            line += f" BLOCKED: {self.blocked_by}"
        return line

    def as_dict(self) -> dict:
        return {"key": self.key, "label": self.label, "writes": list(self.writes),
                "network": self.network, "blocked_by": self.blocked_by,
                "hover": self.hover}


# ---- directory sources ------------------------------------------------------

#: `--approve` also writes the SCHEMA tables — `dataset_definition`,
#: `dataset_schema_version`, `field_definition`, `schema_version_field` — but only
#: when the parse adds a field, which `extract.service._retire_or_refuse` decides.
#: The five below move on every approve.
_APPROVE_WRITES = ("generic_record", "generic_record_revision", "generic_ingestion",
                   "generic_record_node", "classification_node")

_DIRECTORY: dict[str, Pass] = {
    "plan": Pass(
        key="plan", label="Price the crawl",
        does="Sizes every cell of the partition and prices the full crawl against "
             "the live directory",
        # `contractors.run` calls `plan()` and returns BEFORE `open_engine()`, so it
        # cannot write even on error.
        writes=(), network=None,
        network_phrase="sizing requests against the live site"),
    "crawl": Pass(
        key="crawl", label="Crawl the listing",
        does="Fetches every listing page the partition proves it must read, storing "
             "each unparsed",
        writes=("generic_page_snapshot", "dataset_sighting", "fetch_validator",
                "generic_record"),
        network=None,
        network_phrase="one request per listing page — 56 cells, 47 proven on the "
                       "first run"),
    "details": Pass(
        key="details", label="Fetch the profile pages",
        does="Fetches the profile page of every row the registered scope asks for",
        writes=("generic_page_snapshot",), network=None,
        network_phrase="one request per profile page in the frontier — last measured "
                       "34,834 pages at 1.007 s each, 9.75 h"),
    "approve": Pass(
        key="approve", label="Interpret the stored pages",
        does="Interprets the pages already on disk into rows, re-fetching nothing",
        writes=_APPROVE_WRITES, network=0,
        network_phrase="zero requests — last measured 121 rows in 83.9 min"),
    "coverage": Pass(
        key="coverage", label="What we are missing",
        does="Stored against sighted, the frequency sample, sighted-and-never-stored, "
             "and departures measured against the ledger's newest sighting",
        writes=(), network=0,
        network_phrase="zero requests, read from the warehouse"),
    "impostors": Pass(
        key="impostors", label="Rows written from the wrong page",
        does="Lists profile rows whose membership number disagrees with their listing "
             "card; --repair is what retires them",
        writes=(), network=0,
        network_phrase="zero requests, read from the warehouse"),
    "reapprove_schema": Pass(
        key="reapprove_schema", label="Re-approve the contract onto the live shape",
        does="Re-approves the live rows onto the field set they actually carry, when the "
             "approved version was taught by pages that have since been retired; "
             "--repair is what applies it",
        # It writes no VALUE and no revision: only which version a row is bound to, plus
        # the two version rows. `R-53`'s own text says 17,371 revisions and cannot be
        # right -- `generic_record_revision` is UNIQUE on (record, snapshot, hash) and
        # nothing here changes a hash.
        writes=("dataset_schema_version", "schema_version_field", "generic_record"),
        network=0,
        network_phrase="zero requests, read from the warehouse"),
}


def directory_passes(directory: Directory | None, *, scope: CrawlScope | None,
                     crawl_slice: str = "", site_key: str = "",
                     extraction_enabled: bool = True) -> tuple[Pass, ...]:
    """The six, with the cost filled in and every block named.

    Every block below is one of `contractors.validate`'s own refusals, or the early
    return in `contractors.details` — stated here so the panel can grey a control
    instead of the user meeting the refusal after the click.
    """
    if directory is None:
        unknown = (f"no directory builder for site {site_key!r} "
                   "(scrapex/directories.py), so no pass can be run against it")
        return tuple(replace(_DIRECTORY[key], blocked_by=unknown)
                     for key in DIRECTORY_PASSES)

    cells = len(directory.partition().cells())
    built: list[Pass] = []
    for key in DIRECTORY_PASSES:
        one = _DIRECTORY[key]
        if key == "plan":
            # `size_cell` costs 2 requests, or 1 for a cell that is a single page —
            # so this is the ceiling, and it is derived rather than carried.
            one = replace(
                one, network=2 * (cells + 1),
                network_phrase=f"up to {2 * (cells + 1)} requests — 2 per cell over "
                               f"{cells} cells, plus the whole listing")
        elif key == "details":
            if scope is CrawlScope.LISTING_ONLY:
                one = replace(one, blocked_by=(
                    "site_profile.crawl_scope is listing_only, under which this pass "
                    "refuses and asks you to change the scope"))
            elif scope is CrawlScope.LISTING_PLUS_SLICE and not crawl_slice.strip():
                one = replace(one, blocked_by=(
                    "site_profile.crawl_scope is listing_plus_slice and "
                    "crawl_slice names no slice, so there is nothing to select"))
        elif key == "approve" and not extraction_enabled:
            one = replace(one, blocked_by=(
                "generic extraction is disabled in this build "
                "(scrapex/features.py)"))
        elif key == "impostors" and directory.profiles is None:
            one = replace(one, blocked_by=(
                f"{directory.key} declares no profile reader, so it has no profile "
                "rows to check"))
        built.append(one)
    return tuple(built)


# ---- price sources ----------------------------------------------------------

#: Every table `scrapex/ingest.py` writes. Guarded against that file, so a run mode
#: cannot come to write a table this list does not name.
_INGEST_WRITES = ("crawl_run", "currency_rate", "offer_state", "price_observation",
                  "price_period", "source_offer", "source_product",
                  "source_product_attribute", "source_site", "source_variant")

_PRICE: dict[str, Pass] = {
    RunMode.INITIAL_CRAWL.value: Pass(
        key=RunMode.INITIAL_CRAWL.value, label="First full collection",
        does="Walks the whole catalogue for the first time and stores every price it "
             "reads",
        writes=_INGEST_WRITES, network=None),
    RunMode.UPDATE.value: Pass(
        key=RunMode.UPDATE.value, label="Update now",
        does="Re-reads the catalogue and appends an observation only where the price "
             "moved",
        writes=_INGEST_WRITES, network=None),
    RunMode.FULL_REBUILD.value: Pass(
        key=RunMode.FULL_REBUILD.value, label="Rebuild from scratch",
        does="Archives what is held, then collects the catalogue again from the top",
        writes=_INGEST_WRITES, network=None),
    RunMode.HISTORY_BACKFILL.value: Pass(
        key=RunMode.HISTORY_BACKFILL.value, label="Collect the published history",
        does="Collects the history the source publishes itself, as dated rows",
        writes=_INGEST_WRITES, network=None),
}


def price_passes(entry, *, last_requests: int | None = None) -> tuple[Pass, ...]:
    """The run modes `POST /api/jobs` accepts, per source.

    The cost is the source's OWN last run — `crawl_run.requests_count` — because a
    number retyped from another shop's catalogue is not this shop's cost.
    """
    phrase = (f"last run made {last_requests:,} requests"
              if last_requests else
              "no finished run has measured this source's request count yet")
    # EVERY REASON, NOT THE FIRST ONE. ELBUROJ is both switched off and on a family
    # with no published history; naming one of the two sends the owner to fix a
    # setting that will not make the control work.
    common: list[str] = []
    if entry.family not in _BUILDERS:
        common.append(f"family {entry.family.value!r} has no connector in "
                      "scrapex/connectors/factory.py, so nothing can collect it")
    if not entry.active:
        common.append("the source is switched off in sources.yaml")

    built: list[Pass] = []
    for key in (mode.value for mode in RunMode):
        reasons = list(common)
        if key == RunMode.HISTORY_BACKFILL.value and not supports_history(entry.family):
            reasons.append(
                f"family {entry.family.value!r} does not publish its own history")
        built.append(replace(_PRICE[key], network=last_requests,
                             network_phrase=phrase,
                             blocked_by="; ".join(reasons) or None))
    return tuple(built)
