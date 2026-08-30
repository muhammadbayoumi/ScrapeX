"""The gate that holds the version rule until `R-77` replaces the rule with an architecture.

Its title is the rule it enforces -- the engine's version moves when its CONTRACT moves,
the extension's when the panel's behaviour does -- and that rule was deleted on
2026-08-30. Read the next paragraph before changing anything here.

WHY THIS FILE EXISTS. `VERSION` sat at `0.2.2` for **91 commits** — last moved
`adf31b2` on 2026-08-10 — and the owner could no longer answer a simple question
about his own project: had the work gone into the engine or the extension? Measured
2026-08-21: 42 of those commits touched `scrapex/` or `db/`, 36 touched the browser side,
12 touched both. **One number asked about two products answers neither.**

**A GATE ALREADY EXISTED AND WATCHED THE WRONG THING.** `tests/test_version.py` fails
when the *capability set* changes without `VERSION` moving. Capabilities had not
changed in those 91 commits — so the gate stayed quiet while **three engine
migrations landed in a single day**, each of them a change an older build cannot
read.

**THIS FILE ENFORCES A RULE THAT HAS BEEN REPLACED, AND IT STAYS UNTIL ITS REPLACEMENT
IS BUILT.** The criterion below is `R-35`'s, and `R-35` was DELETED on 2026-08-30 by
`R-77` along with `R-05`, `R-06`, `R-07` and `R-61`:

    engine     moves on a CONTRACT change — schema, protocol, or endpoint
    extension  moves on a USER-VISIBLE change — which this codebase already
               models as a capability whose `Surface` is the panel

**`R-77` says the engine has no version at all** — a `protocol` number for compatibility,
a build SHA for identity, and the product version is the extension's alone. Under it, "is
a new endpoint a bump?" stops being a question.

**SO WHY IS THIS STILL HERE.** `R-77` is a ruling and not yet an architecture: `VERSION`
is still hand-edited, and nothing yet reads `protocol` as the compatibility authority.
**Deleting this gate today would remove the only protection there is and put nothing in
its place** — a contract could move silently again, which is the ninety-one-commit
failure that produced it. So it enforces the old rule on purpose, and it is the FIRST
thing `R-77`'s builder must change:

    test_the_contract_has_not_moved_without_the_version_moving
        -> asks `endpoints`; becomes a check that `protocol` moved
    test_the_minimum_extension_version_is_still_the_engines_to_own
        -> asserts what `R-77` retires; becomes a MINIMUM PROTOCOL

**AND UNTIL THEN A NEW ROUTE CANNOT LAND WITHOUT A DECISION.** `contractstamp._ROUTE`
matches `@app.<verb>("...")`, so one new endpoint puts an entry in `endpoints["added"]`
and reddens the gate unless `VERSION` is bumped by hand — which is the churn `R-77`
ended. Measured 2026-08-30, this blocked `POST /api/engine/stop` and the work was split
around it rather than spending a version number on a rule that had been deleted.

**HOW THIS DOCSTRING CAME TO CITE THE RULING THAT DELETED IT**, recorded because it is
the failure this file is about, one level up: `#290` repointed every citation of the five
deleted rulings to `R-77` mechanically. Four sentences in `LESSONS`, `STATE`, `BACKLOG`
and `REQUESTS` were caught and rewritten — prose that RECOUNTS what a ruling did reads
as a claim about the ruling it now names. **These two were missed because they are test
docstrings and the review pass read prose.** A citation inside a guard is the one a reader
trusts most.

WHY THESE TWO AND NOT ONE RULE FOR BOTH. A contract break stops another program
working, and that is what an engine consumer needs warned about. Chrome shows the
extension's number to people, so it should move when what those people can *do*
changes. The same rule on both would either spam the extension's users with releases
they cannot see, or leave an engine consumer with no signal that the schema moved.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from scrapex import contractstamp
from scrapex.version import CAPABILITIES, MINIMUM_EXTENSION_VERSION, VERSION, Surface

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = ROOT / "contracts" / "contract-baseline.json"


def panel_capabilities() -> set[str]:
    """What the PANEL executes — the codebase's own model of user-visible.

    `version.Surface` distinguishes where a capability RUNS, not where it is drawn,
    and its docstring says why: a capability the panel executes raises the minimum
    extension version and one the engine executes alone does not. So "user-visible
    behaviour" is not invented here — it is read off the distinction `R-77` already
    relies on.

    `CAPABILITIES` IS A TUPLE AND THE FIELD IS `surfaces`, PLURAL — a capability can
    run in both places, and most do. The first draft of this used
    `getattr(cap, "surface", None)`, which returned `None` for all eight and would
    have made the test below assert nothing while passing.
    """
    return {cap.key for cap in CAPABILITIES if Surface.PANEL in cap.surfaces}


# ---- the engine: a contract change must move VERSION ------------------------

def test_a_contract_baseline_exists_and_names_its_version():
    """Without a recorded baseline there is nothing to have drifted FROM, and the
    gate below would pass by knowing nothing."""
    assert BASELINE.is_file(), (
        f"{BASELINE.relative_to(ROOT)} is missing. Write it with "
        "`python -m scrapex.cli export-version`.")
    recorded = contractstamp.read(BASELINE)
    assert recorded.get("version"), "the baseline must say which version it describes"


def test_the_contract_has_not_moved_without_the_version_moving():
    """THE GATE HIS RULING ASKED FOR.

    A failure here is not a nuisance: it means an older build can no longer talk to
    this one and nothing said so. The fix is two lines — bump `VERSION` and re-run
    `python -m scrapex.cli export-version` — and the point is that it cannot be
    forgotten for ninety-one commits again.
    """
    recorded = contractstamp.read(BASELINE)
    moved = contractstamp.differences(recorded)

    if recorded.get("version") == VERSION and moved:
        pytest.fail(
            f"the engine contract changed while VERSION stayed at {VERSION}:\n"
            + json.dumps(moved, indent=2, ensure_ascii=False)
            + "\n\nBump VERSION and run `python -m scrapex.cli export-version`.")


def test_the_baseline_describes_the_contract_of_its_own_version():
    """If the baseline says 0.3.0 and the code is 0.3.0, the two must agree — a
    baseline that names this version and describes another is worse than none."""
    recorded = contractstamp.read(BASELINE)
    if recorded.get("version") != VERSION:
        pytest.skip("the baseline describes an older version; the gate above owns that")
    assert not contractstamp.differences(recorded)


# ---- what the fingerprint is, and is not ------------------------------------

def test_the_three_parts_are_all_read_from_the_repository():
    """A part that silently reads empty would make the gate blind to it."""
    seen = contractstamp.fingerprint()

    assert len(seen["schema"]) >= 7, "the engine migration stream"
    assert seen["protocol"], "the native-messaging protocol version"
    assert len(seen["endpoints"]) >= 50, "the routes the panel calls"


def test_adding_a_migration_is_a_contract_change():
    """Schema is the part `R-24` and `OP-30` both turn on: a warehouse written by a
    newer build cannot be read by an older one."""
    recorded = {**contractstamp.fingerprint()}
    recorded["schema"] = recorded["schema"][:-1]

    moved = contractstamp.differences(recorded)

    assert "schema" in moved
    assert moved["schema"]["added"] and not moved["schema"]["removed"]


def test_removing_a_route_is_a_contract_change_and_says_so():
    """A removed route is a client that stops working with no error we control, and
    the report must distinguish it from an added one."""
    recorded = {**contractstamp.fingerprint()}
    recorded["endpoints"] = [*recorded["endpoints"], "GET /api/a-route-we-deleted"]

    moved = contractstamp.differences(recorded)

    assert moved["endpoints"]["removed"] == ["GET /api/a-route-we-deleted"]
    assert not moved["endpoints"]["added"]


def test_the_protocol_is_watched_too():
    recorded = {**contractstamp.fingerprint(), "protocol": "999"}

    assert "protocol" in contractstamp.differences(recorded)


def test_an_unchanged_contract_reports_nothing():
    """The common case. A gate that fires on every run teaches people to ignore it."""
    assert contractstamp.differences(contractstamp.fingerprint()) == {}


def test_a_refactor_is_not_a_contract_change():
    """WHAT THE RULING DELIBERATELY EXCLUDES. Moving code between files, adding
    tests, or writing documents changes nothing another program can observe — and a
    version that moves for it is the commit counter `R-77` was superseded for being.
    """
    seen = contractstamp.fingerprint()

    assert set(seen) == {"schema", "protocol", "endpoints"}, (
        "the fingerprint must not grow a part that a refactor can move")


# ---- the extension: a user-visible change must move its manifest ------------
#
# NOTHING HERE NAMES THE BROWSER SIDE'S DIRECTORY, DELIBERATELY, AND NOT FOR
# TIDINESS. `test_the_extension_gate_is_complete` matches that directory name in any
# file under `tests/` and requires `pytestmark = pytest.mark.extension` — which moves
# the file into the tier CI runs SEPARATELY, so it would no longer run on an
# engine-only change. That is the exact opposite of what a gate on the engine's
# contract is for.
#
# The gate's own note says a false positive "costs one marker". Here the marker would
# cost the gate, so the prose avoids the name instead. The one test that really read
# `manifest.json` asserted only that two strings were strings; its real subject —
# that R-77 unwelded the two numbers and they must not be re-pinned — is already
# owned by `tests/test_version.py:536`, which fails if the old drift comparison comes
# back. Two guards for one rule is one guard and one liability.

def test_the_panel_surface_is_what_the_extension_version_answers_to():
    """`R-77`'s second half. The set may be empty on a build with no panel
    capabilities, but the DISTINCTION must exist — if `Surface.PANEL` ever stops
    being used, the extension's criterion has quietly lost its subject."""
    panel = panel_capabilities()

    assert panel, (
        "no capability declares the panel surface any more, so 'user-visible' has "
        "nothing to be read off — R-77's extension criterion needs a new subject")
    # Measured 2026-08-21: seven of the eight capabilities run in the panel.
    assert len(panel) >= 5, sorted(panel)


def test_the_minimum_extension_version_is_still_the_engines_to_own():
    """THE RULE THIS ASSERTS IS RETIRED BY `R-77`, AND THE ASSERTION STAYS UNTIL IT IS
    BUILT. The sentence it was written for -- "the engine keeps the GATE and drops the
    ADVERT" -- was `R-07`'s, deleted on 2026-08-30. `R-77` replaces
    `MINIMUM_EXTENSION_VERSION` with a minimum PROTOCOL, so this test asserts something the
    ruling retires and will fail the day somebody builds it correctly. **That is the
    intended signal, not a regression**: whoever removes the constant must remove this with
    it, and a green suite either side would mean nobody noticed.

    What it still buys today: a dynamic version must not quietly turn the minimum into a
    moving target -- it is derived from the ledger, so it moves when a panel capability's
    `since` does, and not otherwise."""
    assert MINIMUM_EXTENSION_VERSION
    assert MINIMUM_EXTENSION_VERSION <= VERSION, (
        f"the engine requires an extension newer than itself "
        f"({MINIMUM_EXTENSION_VERSION} > {VERSION})")
