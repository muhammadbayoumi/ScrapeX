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



def _panel_calls() -> set[str]:
    found: set[str] = set()
    for path in (ROOT / "extension").rglob("*.js"):
        if "tests" in path.parts:
            continue
        for match in CALLS.finditer(path.read_text(encoding="utf-8")):
            found.add("/api/" + match.group(1).rstrip("/"))
    return found


def _engine_serves(tmp_path) -> set[str]:
    """THE ROUTES THE APP ACTUALLY MOUNTS, read off a built app.

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

    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                                pointer_file=tmp_path / "databases.json")
    registry.initialize()
    app = create_app(databases=registry)
    return {p for p in _walk(app.routes) if p.startswith("/api/")}


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


def test_the_health_route_the_panel_polls_is_the_one_the_engine_serves(tmp_path):
    """NAMED ON ITS OWN, because it is the one that broke and because its
    failure is silent: the panel's restart poll simply never succeeds, and the
    owner is told the engine did not come back when it did."""
    assert "/api/engine/health" in _engine_serves(tmp_path), (
        "the engine no longer serves /api/engine/health")

    app_js = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")
    assert "/api/engine/health" in app_js, (
        "the panel does not poll /api/engine/health")
    assert "/api/marketlens/health" not in app_js, (
        "the panel still polls the route M5 removed")


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
