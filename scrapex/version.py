"""The product version, and the ledger that says which version has what.

THE ENGINE's number, and one mirror: this module is the authority and
`pyproject.toml` carries a copy because the installer cannot import Python.
`tests/test_version.py` reads it back and fails the build the moment it drifts —
the same arrangement `PROTOCOL_VERSION` has across `scrapex/native.py` and
`extension/transport.js`.

THE EXTENSION'S NUMBER IS NOT HERE, and since 2026-08-05 it is not this one
either. It lives in `extension/manifest.json`, which is the only thing Chrome
reads, and the two are allowed to differ — because they ship down separate
paths (PLATFORM-PLAN Decision 21): the extension is reviewed by Google and then
pushed to every user automatically, while the engine is published to GitHub and
installed when the owner accepts. Chrome can therefore move the extension
tonight while a user's engine is last month's, and no equality rule can stop
that — it can only stop the repository from saying so.

WHAT REFUSES AN INCOMPATIBLE PAIR is `PROTOCOL_VERSION` and the ledger below,
never a comparison of the two stamps. `capability_problem` already takes the two
versions separately and names both in every sentence it produces; that was
written before the split and needed no change for it.

TWO NUMBERS, BECAUSE THERE ARE TWO QUESTIONS — the split the funnel payload
contract already made for itself (`scrapex/payload.py`), applied here:

  VERSION                    the RELEASE stamp. Moves whenever a functional,
                             architectural or behavioural change lands. It is
                             reported, displayed and read by humans; on its own
                             it refuses nothing.
  MINIMUM_EXTENSION_VERSION  the GATE. The oldest extension that can still work
                             every capability this engine deploys. DERIVED from
                             the ledger below and never typed, so a capability
                             that forgets to say which version introduced it
                             cannot be constructed at all.

WHY THIS FILE EXISTS. Twice in two days the owner asked for a feature that had
already shipped, because nothing in front of him could say what he was running:

  - the crawl pace (`crawl_honour_delay`, `crawl_min_interval_s`) was built and
    plumbed all the way to the fetcher in `c63ec21`, and rendered only on the
    engine's web page. He asked for it as if it were new.
  - crawling several sites at once landed in the engine at `63dc24b` and reached
    the panel eleven commits later at `76a4b14`. In between, the engine queued
    two jobs at once and he asked why.

Both are the same question — "does the thing in front of me have X?" — and the
version string could answer neither, because it had not moved in 130 commits.
A number that never moves is not a version, it is a decoration.

WHAT `since` MEANS, AND WHAT IT DOES NOT. Every capability below is recorded
`since 0.2.0` and NOTHING is back-dated. 0.1.0 covered the entire history of the
project without ever moving, so it cannot promise that a build carrying it has
anything in particular; 0.2.0 is the first version that can promise anything at
all. The commit that BUILT each capability is recorded beside it as evidence —
read out of `git log`, never invented — so the ledger answers "when was this
written" and "from which version is it guaranteed" separately, and neither
answer is allowed to impersonate the other.

WHAT IS IN THE LEDGER. The capabilities whose absence a person would meet as a
missing or broken feature: something to press that is not there, or a request
the other side does not understand. Not every function in the codebase — a
ledger padded to look complete is a ledger nobody trusts. `tests/test_version.py`
fails the build when a capability declares a panel control the panel does not
have, when a crawl setting the engine accepts belongs to no capability at all,
and when the capability set changes without VERSION moving.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

# The release stamp. Bump it for a functional, architectural or behavioural
# change (issue 32 section 1.1), and regenerate the baseline + CHANGELOG in the
# same commit: python -m scrapex.cli export-version
VERSION = "0.2.2"


class Surface(StrEnum):
    """Where a capability is EXECUTED — never merely where it is displayed.

    The distinction is load-bearing. The extension is the primary application
    (issue 32 section 2.1), so a capability that the panel executes raises the
    minimum extension version and one the engine executes alone does not. The
    web interface is display-only by the owner's standing rule and is therefore
    not a surface at all.
    """

    PANEL = "panel"
    ENGINE = "engine"


@dataclass(frozen=True)
class Capability:
    """One thing the product can do, and the version from which it is guaranteed.

    EVERY field is required, including `since`. That is the whole mechanism: a
    capability appended without declaring its version is a TypeError at import,
    which is the loudest and earliest place to ask the question. It is the same
    trick `GENERATION_OF_VERSION[PAYLOAD_VERSION]` plays on a payload bump that
    forgets to declare its kind.
    """

    key: str
    since: str
    summary: str          # what a person loses when it is missing (issue 32 §1.4)
    surfaces: tuple[Surface, ...]
    panel_control: str    # a string the panel's own source must contain; "" when engine-only
    settings: tuple[str, ...]   # keys in scrapex.settings.SETTINGS this capability owns
    commit: str           # the commit that BUILT it; "" only while it is landing


CAPABILITIES: tuple[Capability, ...] = (
    Capability(
        key="crawl_pace",
        since="0.2.0",
        summary="Choose whether each site's requested crawl delay is honoured, and "
                "set the minimum seconds between requests and the request timeout.",
        surfaces=(Surface.PANEL, Surface.ENGINE),
        panel_control="crawl_min_interval_s",
        settings=("crawl_honour_delay", "crawl_min_interval_s",
                  "crawl_timeout_s", "crawl_user_agent"),
        # Built and plumbed to HttpFetcher here; 2253308 moved the controls off
        # the display-only web page into the panel. This is incident one.
        commit="c63ec21",
    ),
    Capability(
        key="robots_per_source",
        # 0.2.2, not 0.2.1, and the ledger is what taught me: the baseline
        # records what each version DEPLOYS, so adding a capability under a
        # version that already has a baseline changes what 0.2.1 means after the
        # fact. "A functional change gets its own version" is the rule, and it
        # holds whether or not anything has been released yet.
        since="0.2.2",
        summary="Read what a site's robots.txt asks of a crawler, then decide per "
                "source: follow the tool default, obey that site, or write a rule "
                "for it alone.",
        surfaces=(Surface.PANEL, Surface.ENGINE),
        panel_control="source-edit-robots",
        settings=("crawl_obey_disallow",),
        # The setting is only the DEFAULT. The per-source choice lives on the
        # source itself (SourceEntry.robots), which is why the panel control
        # named here is on the source editor and not the Settings page.
        commit="",
    ),
    Capability(
        key="crawl_parallel_sources",
        since="0.2.0",
        summary="Crawl several different sites at the same time. Two sources on the "
                "SAME site still take turns, so no site is asked for more than before.",
        surfaces=(Surface.PANEL, Surface.ENGINE),
        panel_control="crawl_parallel_sources",
        settings=("crawl_parallel_sources",),
        # The engine learned to do it here and the panel had no field for it
        # until 76a4b14, eleven commits and fourteen hours later. This is
        # incident two, and it is the exact gap this ledger is built to expose.
        commit="63dc24b",
    ),
    Capability(
        key="crawl_resume",
        since="0.2.0",
        summary="Continue an interrupted crawl from the pages it already kept, "
                "without fetching any of them again.",
        surfaces=(Surface.PANEL, Surface.ENGINE),
        panel_control="data-resume",
        settings=(),
        commit="56a50d1",
    ),
    Capability(
        key="source_admin",
        since="0.2.0",
        summary="Edit, rename, stop tracking or erase a source from the panel, with a "
                "rename moving the rows in all nine tables in one transaction.",
        surfaces=(Surface.PANEL, Surface.ENGINE),
        panel_control="source-edit-rename",
        settings=(),
        commit="412785b",
    ),
    Capability(
        key="version_visibility",
        since="0.2.0",
        summary="See which version of the extension and which version of the engine "
                "are actually running, each named for the side it belongs to.",
        surfaces=(Surface.PANEL, Surface.ENGINE),
        panel_control="about-extension-version",
        settings=(),
        commit="7ca7a75",  # landing in this release
    ),
    Capability(
        key="compatibility_notice",
        since="0.2.0",
        summary="Be told, rather than left to find out, when the installed extension "
                "is older than the features the engine deploys.",
        surfaces=(Surface.PANEL,),
        panel_control="version-notice",
        settings=(),
        commit="7ca7a75",  # landing in this release
    ),
    Capability(
        key="display_method_and_unit",
        since="0.2.0",
        summary="Record how a site displays a product and what one unit of its price "
                "buys, so a per-metre price is never read as a per-piece one.",
        # ENGINE alone on purpose, and it is the case that proves the split is
        # real: this changes what is stored and what the sheet receives, and the
        # panel needs no new control for it — so it must NOT raise the oldest
        # extension the engine can work with.
        surfaces=(Surface.ENGINE,),
        panel_control="",
        settings=(),
        commit="55ae064",
    ),
)


def parse_version(value: str) -> tuple[int, int, int]:
    """MAJOR.MINOR.PATCH as three integers, or a refusal that names the input.

    Deliberately strict (P5). Chrome would accept one to four dot-separated
    integers in a manifest, and accepting the same range here would mean
    `0.2` and `0.2.0` comparing as different versions of the same build.
    """
    parts = value.split(".") if value else []
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError(
            f"{value!r} is not a ScrapeX version: expected MAJOR.MINOR.PATCH, "
            "three integers separated by dots")
    major, minor, patch = (int(part) for part in parts)
    return major, minor, patch


def is_older(left: str, right: str) -> bool:
    """True when `left` is a version strictly behind `right`."""
    return parse_version(left) < parse_version(right)


def _newest(versions: tuple[str, ...]) -> str:
    return max(versions, key=parse_version)


# The oldest extension that can work everything this engine deploys — DERIVED,
# never typed. Only capabilities the PANEL executes count: an engine-only
# capability costs the extension nothing, which is what keeps an engine-side
# improvement from telling the owner to go and reload a browser for no reason.
# (The same logic as the payload contract's additive changes being free.)
# The first engine that publishes a capability report at all. Before it, an
# engine's silence about its features means "too old to say", never "does not
# have them" — and the remedy is to reach THIS version, not to reach whatever
# number the extension happens to wear. An engine and an extension can sit at
# the same number and both be below this line; telling the owner to update to
# the number already installed is not a remedy, it is a loop.
CAPABILITY_REPORTING_SINCE = "0.2.0"

# THE FLOOR IS THE NEWEST PANEL CAPABILITY, AND A CAPABILITY'S `since` IS A
# FROZEN LITERAL — never `VERSION`.
#
# Every one of the seven capabilities used to record `since=VERSION`, which made
# this line always equal VERSION however it was written. MEASURED: bump the
# engine alone to 0.4.0 and the floor became 0.4.0, so the engine declared the
# extension in the Chrome Web Store — 0.2.0, reviewed by Google, installed on
# every machine — too old to talk to. Every engine release did that, to an
# extension that had not changed.
#
# That is the exact opposite of PLATFORM-PLAN Decision 21 ("neither triggers the
# other"), and no test could see it, because with `since=VERSION` the floor and
# the head move together and every comparison stays true.
#
# The literal is the version the capability WAS INTRODUCED IN, and it never
# moves again. A new capability is written with the number it ships in; the old
# ones keep theirs. Then the floor rises only when the panel genuinely needs a
# newer extension, which is the only thing it was ever meant to say.
MINIMUM_EXTENSION_VERSION = _newest(tuple(
    capability.since for capability in CAPABILITIES
    if Surface.PANEL in capability.surfaces
) or (VERSION,))

# There is no remote update server, and this file will not pretend otherwise.
# The extension is loaded from the same checkout as the engine, so the newest
# extension a machine can have is the one its engine shipped with — that is the
# entire meaning of "latest available" here, and it travels on the wire as
# LATEST_SOURCE so a reader is never left to assume a release feed exists.
LATEST_SOURCE = ("the ScrapeX engine you are connected to — it ships with the "
                 "extension, and there is no remote update server")

UPDATE_INSTRUCTIONS = (
    "Update the engine first (it carries the new extension with it), then open "
    "chrome://extensions, turn on Developer mode and press Reload on ScrapeX. "
    "Close and reopen the side panel afterwards."
)

CAPABILITY_BY_KEY: dict[str, Capability] = {c.key: c for c in CAPABILITIES}

# What this engine deploys, in the shape it travels in. `capability_problem`
# takes this rather than reaching for the ledger directly, so the Python and the
# JavaScript copies take IDENTICAL inputs and can be pinned to identical outputs
# — a function that quietly knows more on one side than the other is a drift
# test that passes while the two disagree.
DEPLOYED: dict[str, dict[str, str]] = {
    capability.key: {"since": capability.since, "summary": capability.summary}
    for capability in CAPABILITIES
}


def _validate_ledger() -> None:
    """Everything the ledger cannot be allowed to say, refused at IMPORT.

    Not in a test: a build whose version ledger contradicts itself must not
    start, because every downstream answer — what is missing, what to update,
    whether a feature may run — is computed from it.
    """
    if len(CAPABILITY_BY_KEY) != len(CAPABILITIES):
        raise ValueError("two capabilities share one key in scrapex.version.CAPABILITIES")
    parse_version(VERSION)
    for capability in CAPABILITIES:
        parse_version(capability.since)
        if is_older(VERSION, capability.since):
            raise ValueError(
                f"capability {capability.key!r} claims to exist since "
                f"{capability.since}, which is newer than this build ({VERSION}). "
                "A capability cannot ship before the release that carries it — "
                "bump VERSION in the same commit")
        if not capability.commit and capability.since != VERSION:
            raise ValueError(
                f"capability {capability.key!r} is dated {capability.since}, older "
                f"than this build ({VERSION}), and cites no commit. History is "
                "read out of git log, never remembered")
        if Surface.PANEL in capability.surfaces and not capability.panel_control:
            raise ValueError(
                f"capability {capability.key!r} says the panel executes it and names "
                "no control. A capability the owner cannot reach from the side panel "
                "is a capability he does not have")


_validate_ledger()


def capability_problem(
    key: str,
    *,
    extension_version: str,
    engine_version: str,
    deployed: Mapping[str, Mapping[str, str]] | None,
    update_instructions: str = UPDATE_INSTRUCTIONS,
) -> str:
    """"" when this pair can work the capability, otherwise the refusal in words.

    `deployed` is what the ENGINE says it deploys, keyed by capability: pass
    `DEPLOYED` to ask this build about itself, whatever the engine published to
    ask a remote one, and None for an engine too old to publish anything at all.
    It is a required argument because those three are genuinely different
    questions and defaulting one of them would answer a question nobody asked.

    THREE refusals, and each names BOTH versions and WHICH side is behind — the
    remedies are opposite and one bare number cannot tell them apart: a stale
    extension is fixed by a reload in chrome://extensions, a stale engine by
    updating the engine, and an engine that cannot say is not the same as an
    engine that said no. The panel carries this function word for word where
    JavaScript allows (extension/version.js: capabilityProblem), and
    contracts/version-vectors.json pins both copies to the same sentences.
    """
    entry = deployed.get(key) if deployed is not None else None
    label = entry["summary"] if entry else key
    if deployed is None:
        # An engine from before this ledger existed. It is not refused for
        # having no answer — it is told apart from an engine that answered NO,
        # because "cannot say" and "does not have it" send you to different
        # places. The same care engine.js already takes with an absent
        # protocol_version: silence is not a mismatch.
        return (
            f"«{label}» cannot be confirmed: the ScrapeX engine reports version "
            f"{engine_version} and is too old to say which features it deploys. "
            f"This extension is {extension_version}. Update the engine to "
            f"{extension_version}."
        )
    if entry is None:
        return (
            f"«{label}» is not deployed by this ScrapeX engine ({engine_version}); "
            f"this extension is {extension_version}. Update the engine to "
            f"{extension_version} or newer."
        )
    if is_older(extension_version, entry["since"]):
        return (
            f"«{label}» needs ScrapeX extension {entry['since']}; this extension "
            f"is {extension_version} and the engine is {engine_version}. "
            + update_instructions
        )
    return ""


# The pairs both languages are pinned to. Written to contracts/version-vectors.json
# by `python -m scrapex.cli export-version`, checked by tests/test_version.py on
# the Python side and extension/tests/version-compat.test.mjs on the JavaScript
# side — the arrangement contract/parity already uses for the normalize vectors,
# because two implementations of one rule drift the moment nothing compares them.
#
# Each case is here because it has a DIFFERENT remedy, and a vector set that
# only covered the happy path would pin the one answer nobody needs to read.
VECTOR_CASES: tuple[dict, ...] = (
    {"name": "in step — the engine deploys it and the extension is new enough",
     "key": "crawl_parallel_sources", "extension_version": VERSION,
     "engine_version": VERSION, "deployed": True},
    {"name": "the extension is behind the engine",
     "key": "crawl_parallel_sources", "extension_version": "0.1.0",
     "engine_version": VERSION, "deployed": True},
    {"name": "the engine is behind and says so",
     "key": "crawl_parallel_sources", "extension_version": VERSION,
     "engine_version": "0.1.0", "deployed": False},
    {"name": "the engine is too old to say anything",
     "key": "crawl_parallel_sources", "extension_version": VERSION,
     "engine_version": "0.1.0", "deployed": None},
    # Never refuse a side for being NEWER. The payload contract learned this the
    # expensive way: an equality gate refused payloads it could read perfectly,
    # and the cure was a hand re-paste. An extension ahead of its engine works.
    {"name": "an extension newer than the requirement is not refused for being newer",
     "key": "crawl_parallel_sources", "extension_version": "9.9.9",
     "engine_version": VERSION, "deployed": True},
)


def export_vectors() -> dict:
    """The neutral form of the compatibility rule, for the JavaScript copy."""
    cases = []
    for case in VECTOR_CASES:
        if case["deployed"] is True:
            deployed = DEPLOYED
        elif case["deployed"] is False:
            deployed = {k: v for k, v in DEPLOYED.items() if k != case["key"]}
        else:
            deployed = None
        cases.append({
            "name": case["name"],
            "key": case["key"],
            "extension_version": case["extension_version"],
            "engine_version": case["engine_version"],
            "deployed": deployed,
            "update_instructions": UPDATE_INSTRUCTIONS,
            "problem": capability_problem(
                case["key"],
                extension_version=case["extension_version"],
                engine_version=case["engine_version"],
                deployed=deployed,
            ),
        })
    return {
        "version": VERSION,
        "minimum_extension_version": MINIMUM_EXTENSION_VERSION,
        "capability_reporting_since": CAPABILITY_REPORTING_SINCE,
        "note": "Both copies of capabilityProblem must reproduce every `problem` "
                "string exactly. Python: scrapex/version.py. JavaScript: "
                "extension/version.js.",
        "cases": cases,
    }


def missing_capabilities(extension_version: str) -> tuple[Capability, ...]:
    """What an extension of that age cannot work, newest requirement first."""
    return tuple(sorted(
        (capability for capability in CAPABILITIES
         if Surface.PANEL in capability.surfaces
         and is_older(extension_version, capability.since)),
        key=lambda capability: parse_version(capability.since), reverse=True))


def version_report(extension_version: str | None = None) -> dict:
    """The five facts issue 32 section 1.4 asks a notification to carry.

    Every number here says whose it is in its own name. `version` on its own was
    the defect: /api/health published one and the panel printed it beside the
    word "Engine" by convention alone, so nothing stopped a second surface from
    printing the same number as the extension's.
    """
    report = {
        "engine_version": VERSION,
        # What the running engine shipped with — see LATEST_SOURCE. Derived from
        # the same constant rather than read off the manifest, because the
        # manifest is a mirror and a mirror is not an authority.
        "latest_extension_version": VERSION,
        "latest_source": LATEST_SOURCE,
        "minimum_extension_version": MINIMUM_EXTENSION_VERSION,
        "capability_reporting_since": CAPABILITY_REPORTING_SINCE,
        "update_instructions": UPDATE_INSTRUCTIONS,
        "capabilities": [
            {"key": capability.key, "since": capability.since,
             "summary": capability.summary,
             "surfaces": [surface.value for surface in capability.surfaces],
             "commit": capability.commit}
            for capability in CAPABILITIES
        ],
        # The caller's own version, echoed back with a verdict, so a client that
        # asked has one answer to show instead of a rule to re-derive.
        "installed_extension_version": extension_version,
        "outdated": False,
        "missing": [],
    }
    if extension_version is None:
        return report
    missing = missing_capabilities(extension_version)
    report["outdated"] = bool(missing) or is_older(extension_version, VERSION)
    report["missing"] = [
        {"key": capability.key, "since": capability.since,
         "summary": capability.summary}
        for capability in missing
    ]
    return report
