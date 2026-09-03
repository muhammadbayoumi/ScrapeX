"""Every request to the engine goes through `backend.js`, which owns the guarantees.

`extension/backend.js` gives a request three things: the status is checked and turned
into an error carrying the detail, the deadline comes from `startup.js`'s table, and
the page's abort signal is attached. **Two calls had none of them**, and they were the
two that moved the most bytes in the product.

MEASURED ON HIS MACHINE, 2026-09-03:

    the engine built  scrapex-bundle-20260903-131501.zip   541,531,989 bytes
    on disk, complete, no .part beside it
    the panel read    0

`extension/app.js` fetched the archive and the panel-pack with a bare
`fetch(...).blob()` — because `api()` ends in `res.json()` and a zip is not JSON. So
a 404, a timeout and a browser refusing to hold half a gigabyte all arrived as the
same thing: an empty blob. The 2026-08-30 guard refused the upload correctly, and
the message it could print said only *"this panel read 0"*, because **the line that
read it threw the status away**. A 378,655,878-byte build had worked four days
earlier, so nothing in the product had said the shape was fragile.

THE FIX WAS NOT A THIRD CALLER WITH ITS OWN CARE. `request()` owns the request and
`api()`/`bytes()` own the parse, so a caller that needs a different body cannot
acquire a bare fetch by needing one. **This file is what stops the next one.**
"""
from __future__ import annotations

import pathlib
import re

import pytest

pytestmark = pytest.mark.extension

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extension"

#: `backend.js` IS the request path, so it is the one file allowed to call `fetch`
#: at the engine. Everything else asks it.
OWNS_THE_REQUEST_PATH = "backend.js"

#: Files that legitimately fetch something that is NOT the engine, with the reason.
#: A row here is a claim that the URL is external, and the test checks that claim
#: rather than trusting it.
NOT_THE_ENGINE: dict[str, str] = {
    "drive.js": "talks to Google and nothing else; the engine's address is "
                "deliberately not known to it",
    "sheets.js": "Google Sheets API",
    "releases.js": "the release feed, which is on the internet",
    "boot-app.js": "loads this extension's own scripts, not a service",
}

_FETCH = re.compile(r"(?<![\w.])fetch\s*\(")


def _sources() -> list[pathlib.Path]:
    return sorted(p for p in EXTENSION.glob("*.js") if p.name != OWNS_THE_REQUEST_PATH)


def test_no_module_but_the_request_path_fetches_the_engine():
    """The defect this closes, stated as a rule: a request to the engine that does
    not go through `backend.js` has no status check, no deadline and no abort."""
    offenders = []
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        for match in _FETCH.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            window = text[max(0, match.start() - 200):match.start() + 200]
            # `backendBase()` is the engine's address, so a fetch near it is a
            # request to the engine however the URL is spelled.
            if "backendBase" in window or "backend +" in window:
                offenders.append(f"{path.name}:{line}")
    assert not offenders, (
        "these fetch the engine directly, outside the one function that checks the "
        f"status, applies the deadline and attaches the abort signal: {offenders}. "
        "Use `api()` for JSON or `bytes()` for a body that is not JSON — and if a "
        "third kind of body is needed, add a parser beside them rather than a "
        "fourth bare fetch.")


def test_a_module_allowed_to_fetch_is_one_that_does_not_fetch_the_engine():
    """A row in `NOT_THE_ENGINE` is a claim, and this checks it.

    Without this the map is a place to put a file to silence the test above.
    """
    wrong = []
    for name, reason in sorted(NOT_THE_ENGINE.items()):
        path = EXTENSION / name
        if not path.is_file():
            wrong.append(f"{name} is listed and does not exist")
            continue
        text = path.read_text(encoding="utf-8")
        if "backendBase" in text:
            wrong.append(f"{name} is listed as not talking to the engine and "
                         f"imports its address ({reason!r})")
    assert not wrong, "\n  ".join(["the exemption map does not describe the tree:", *wrong])


def test_the_request_path_still_carries_all_three_guarantees():
    """Read off `backend.js`, because the rule above is worth nothing if the one
    function it points at stops doing the work."""
    text = (EXTENSION / OWNS_THE_REQUEST_PATH).read_text(encoding="utf-8")
    request = text.split("async function request(")[1].split("\nexport")[0]

    assert "if (!res.ok" in request, (
        "the request path no longer checks the status, so every failure becomes a "
        "body — which is the defect this whole file is about")
    # Written as a prefix on purpose: the condition gained `&& throwOnHttpError`
    # when `raw()` arrived, and an assertion pinned to the old literal failed on
    # a correct change. What matters is that the status is examined at all.
    assert "deadlineForLocalRequest" in request, (
        "the request path no longer takes its deadline from startup.js's table")
    assert "pageController.signal" in request, (
        "the request path no longer attaches the page's abort signal, so a request "
        "outlives the view that asked for it")
    for parser in ("export async function api(", "export async function bytes(",
                   "export async function raw("):
        assert parser in text, f"{parser} is gone, so a caller has no way to ask"

    # THE OPT-OUT HAS EXACTLY ONE USER. `throwOnHttpError: false` is how a caller
    # says "I read the status myself", and it is worth nothing if any call site can
    # pass it: the point of `raw()` is that a reader sees in ONE line which callers
    # own their own status handling.
    assert text.count("throwOnHttpError: false") == 1, (
        f"the status opt-out is passed in {text.count('throwOnHttpError: false')} "
        "places. It belongs to `raw()` alone, or the request path has no single "
        "answer to what a failure means.")
    for source in _sources():
        assert "throwOnHttpError" not in source.read_text(encoding="utf-8"), (
            f"{source.name} passes the status opt-out directly instead of calling "
            "`raw()`, which is the same escape by a longer route")


def test_the_archive_is_read_through_it():
    """The specific call that failed on his machine, named so a rewrite that
    reintroduces the bare fetch fails here rather than in Drive."""
    app = (EXTENSION / "app.js").read_text(encoding="utf-8")
    assert 'await bytes("/api/bundle/archive")' in app, (
        "the Drive backup no longer reads the archive through the request path")
    assert 'await bytes("/api/bundle/panel-pack")' in app, (
        "the panel-pack no longer reads through the request path")
    assert "fetch(base + " not in app, (
        "a bare fetch against the engine's base address is back in app.js")
