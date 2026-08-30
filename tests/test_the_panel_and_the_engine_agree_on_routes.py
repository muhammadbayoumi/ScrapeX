"""Every engine route the panel calls must be a route the engine serves.

THE BREAK THIS EXISTS FOR HAPPENED DURING M5. Collapsing two databases into one
collapsed `/api/general/health` and `/api/marketlens/health` into
`/api/engine/health`. The panel went on calling the old one, and nothing failed:
the engine suite passed (it never reads extension/), the extension suite passed
(it stubs fetch and never asks a real engine), and the only symptom would have
been the "engine is back" poll after a restart never succeeding — on a machine
where the engine was, in fact, back.

That is the shape of every extension/engine contract break: both halves correct,
both suites green, and the seam untested because no test crosses it. So this
file crosses it, by reading the routes out of BOTH sides and comparing them.

It reads extension/ sources, so it is part of the extension gate.
"""

from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.extension

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Written by the engine into the panel's own storage and fetched from there,
#: not typed into a URL. Anything matching this in extension JavaScript is a
#: promise about a route.
CALLS = re.compile(r'["`]/api/([a-z0-9/_-]+)')



def _caller_files() -> list[pathlib.Path]:
    """Every file in the product that names an engine route.

    THIS USED TO BE `extension/**/*.js` AND NOTHING ELSE, and the omission was
    not theoretical: `scrapex/webui/templates/settings.html` polled
    `/api/marketlens/health` for the eleven days after M5 deleted it. The engine
    page's Restart button therefore asked a 404 sixty times and then reported
    "The engine has not come back" about an engine that had come back at once.

    **The guard for that exact break already existed, and it read one half of
    the product.** `test_the_health_route_the_panel_polls_is_the_one_the_engine
    _serves` asserts the dead route is absent from `app.js` — and `app.js` was
    the half that had been corrected. The engine's own pages call engine routes
    too, and a rename breaks them in precisely the same way.

    MEASURED BEFORE WIDENING, because a check that cries wolf gets switched off
    and this file has been bitten by that three times already: the templates
    make 34 distinct `/api/` calls and exactly ONE of them is unserved. The
    widening costs no noise.
    """
    js = [path for path in (ROOT / "extension").rglob("*.js")
          if "tests" not in path.parts]
    return js + sorted((ROOT / "scrapex" / "webui" / "templates").glob("*.html"))


def _panel_calls() -> set[str]:
    found: set[str] = set()
    for path in _caller_files():
        for match in CALLS.finditer(path.read_text(encoding="utf-8")):
            found.add("/api/" + match.group(1).rstrip("/"))
    return found


def _engine_serves(tmp_path, *, registry: bool = True) -> set[str]:
    """THE ROUTES THE APP ACTUALLY MOUNTS, read off a built app.

    `registry=False` BUILDS THE OTHER SHAPE THE ENGINE SHIPS IN, and it is not
    hypothetical: `cli.py`'s `--db` branch leaves `registry = None`, and
    `create_app` then skips `create_database_router` and
    `create_domain_health_router` entirely. Those two conditional includes are
    the whole difference, and `/api/engine/health` is inside the second one.

    Scraping decorators out of the source was tried first and was WRONG: routers
    are mounted with `prefix=`, so `@router.post("/upgrade")` under
    `APIRouter(prefix="/api/databases")` never matched, and the test reported
    two real routes as missing. A check that cries wolf gets switched off, so it
    asks the app instead of guessing at it.
    """
    pytest.importorskip("fastapi")
    from scrapex.databases import EngineDatabase
    from scrapex.databases.registry import DatabaseRegistry
    from scrapex.webui.app import create_app

    reg = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                           pointer_file=tmp_path / "databases.json")
    reg.initialize()
    app = create_app(databases=reg) if registry else create_app(reg.engine.path)
    return {p for p in _walk(app.routes) if p.startswith("/api/")}


def _engine_serves_however_it_started(tmp_path) -> set[str]:
    """The routes served on EVERY start -- the intersection of both shapes.

    THIS IS THE FIX FOR `OP-119`, AND THE OLD HELPER WAS THE DEFECT.
    `_engine_serves` had already been widened once, from scraping decorators to
    asking a built app, which made it right about ROUTES. It stayed wrong about
    CONFIGURATIONS: it built the app one way, with a registry, so
    `/api/engine/health` was always in its answer and `assert "/api/engine/health"
    in _engine_serves(...)` could not fail. **The guard was written for the
    restart poll, by the fix for the restart poll, and still could not see the
    start on which that poll is guaranteed to 404.**

    A liveness probe is the one call that must answer whenever the engine is up
    at all, so probes are checked against this set rather than either shape
    alone. Routes that are legitimately conditional -- the database pages exist
    only when there is a database -- are not held to it; those are pinned by
    `test_the_conditional_routes_are_declared_not_discovered`.
    """
    return (_engine_serves(tmp_path, registry=True)
            & _engine_serves(tmp_path, registry=False))


def _walk(routes):
    """Every path, including the ones behind an included router.

    THIS FUNCTION IS THE WHOLE REASON THIS TEST IS TRUSTWORTHY. FastAPI 0.139
    does not flatten `include_router` into `app.routes` — it stores an
    `_IncludedRouter` wrapper that has NO `.path` and NO `.routes`. Reading
    `app.routes` directly therefore misses every mounted router, which here is
    the database routes, the health routes and both catalog mounts.

    That produced three confident false failures in a row, each naming a route
    that was being served perfectly well. A test that reports working code as
    broken is worse than no test: it gets switched off, and takes the real
    failures with it.
    """
    for route in routes:
        path = getattr(route, "path", None)
        if path:
            yield path
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _walk(inner.routes)


def _template(route: str) -> re.Pattern:
    """A route with `{id}` placeholders, as a pattern the panel's literal
    prefix can be matched against."""
    return re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]*", re.escape(route))
                      .replace(r"\{", "{") + "$")


def test_no_restart_poll_anywhere_asks_for_the_route_m5_removed(tmp_path):
    """NAMED ON ITS OWN, because it is the one that broke and because its
    failure is silent: a restart poll simply never succeeds, and the owner is
    told the engine did not come back when it did.

    IT USED TO ASK ONLY `app.js`, AND THAT IS WHY IT WENT ON PASSING. The panel
    had been corrected at M5; `scrapex/webui/templates/settings.html` had not,
    and kept polling `/api/marketlens/health` for eleven days. A guard that
    names one caller of a route protects that caller, not the route.
    """
    always = _engine_serves_however_it_started(tmp_path)

    # THIS ASSERTION USED TO REQUIRE THE DEFECT. It read
    #     assert any(path.name == "app.js" for path in polls)
    # where `polls` was every caller naming `/api/engine/health` -- so it
    # obliged the panel to poll a route the engine does not serve when it is
    # started with `--db`, and correcting the panel would have turned this test
    # RED. A guard can do worse than miss a defect; it can mandate one.
    # (`OP-119`.)
    probes = {
        "extension/app.js": "the panel's restart poll",
        "scrapex/webui/templates/settings.html": "the engine page's restart poll",
    }
    for rel, what in probes.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        asked = sorted({"/api/" + m for m in CALLS.findall(text)}
                       & (_engine_serves(tmp_path, registry=True)
                          | _engine_serves(tmp_path, registry=False))
                       & {"/api/health", "/api/engine/health"})
        assert asked, f"{what} ({rel}) polls no health route at all"
        outside = [route for route in asked if route not in always]
        assert not outside, (
            f"{what} ({rel}) polls {outside}, which the engine serves only when "
            "it was started with a registry. Started with an explicit database "
            "path it serves no such route, so the poll 404s its whole budget and "
            "reports a failure that did not happen -- which is the defect this "
            "test is named for, arrived at from the other direction.")

    dead = [str(path.relative_to(ROOT)) for path in _caller_files()
            if "/api/marketlens/health" in path.read_text(encoding="utf-8")]
    assert not dead, (
        f"{dead} still ask for the route M5 removed. Whatever polls it will "
        "wait out its whole budget and then report a failure that did not "
        "happen.")


#: THE ROUTES THAT EXIST ON ONE START AND NOT THE OTHER, declared rather than
#: discovered. Every one is behind `if databases is not None:` in
#: `webui/app.py`, which is legitimate -- a database page cannot work without a
#: database. What is NOT legitimate is a liveness probe in here, and that is the
#: whole point of writing the set down: `OP-119` happened because this axis was
#: invisible, so nobody could notice that the restart poll had crossed it.
CONDITIONAL_ON_A_REGISTRY = {
    # `create_domain_health_router` -- and the one a restart poll reached for.
    "/api/engine/health",
    # `create_database_router`. Legitimately conditional: both act ON a registry,
    # so neither has anything to answer without one.
    "/api/databases/health",
    "/api/databases/upgrade",
}


def test_the_conditional_routes_are_declared_not_discovered(tmp_path):
    """The set above must be exactly what the two start shapes differ by.

    MUTATION-CHECKED: mounting `create_domain_health_router` unconditionally
    empties the difference and turns this red; adding a new conditional router
    without declaring it here turns it red naming the new route. Either way the
    axis stops being invisible, which is the only durable half of `OP-119` --
    repointing the two polls fixed the instance and would not have stopped the
    third.
    """
    with_registry = _engine_serves(tmp_path, registry=True)
    without = _engine_serves(tmp_path, registry=False)

    assert without, "the engine serves nothing when started with a database path"
    assert without < with_registry, (
        "starting without a registry should serve strictly fewer routes")

    difference = with_registry - without
    undeclared = sorted(difference - CONDITIONAL_ON_A_REGISTRY)
    assert not undeclared, (
        f"{undeclared} exist only when the engine was started with a registry "
        "and are not declared in CONDITIONAL_ON_A_REGISTRY. A caller polling one "
        "of these gets a 404 on the other start.")

    gone = sorted(CONDITIONAL_ON_A_REGISTRY - difference)
    assert not gone, (
        f"{gone} are declared conditional but are now served on every start. "
        "Delete them from CONDITIONAL_ON_A_REGISTRY -- a stale entry here is a "
        "route nobody is allowed to poll for no reason.")


def test_no_page_calls_an_engine_route_that_does_not_exist(tmp_path):
    """The general case. A route renamed on one side of the seam is invisible
    to both suites — the engine's never reads extension/, and the panel's stubs
    fetch — so it is caught here or at the moment a user presses the button."""
    serves = _engine_serves(tmp_path)
    patterns = [_template(route) for route in serves]

    missing = sorted(
        call for call in _panel_calls()
        if call not in serves and not any(p.match(call) for p in patterns)
        # The panel builds some paths by concatenation (`/api/jobs/` + id).
        # A literal prefix of a real route is a call this cannot judge, and
        # guessing would make the check noisy enough to be switched off.
        and not any(route.startswith(call) for route in serves))

    assert not missing, (
        f"the panel calls {missing}, which the engine does not serve")
