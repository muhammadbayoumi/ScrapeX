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
def _code_only(text: str) -> str:
    """The source with its COMMENTS blanked -- same length, same line numbers.

    THE DETECTOR MATCHED PROSE. `extension/app.js` carries the sentence
    "// manifest fetch (`latestEngineRelease`) because `renderEngines` runs it
    with no ..." and the rule below read it as a bare call to the engine. A guard
    that fails on a comment somebody else wrote is the loudest possible way to be
    wrong about correct code, and it arrived the moment two unrelated pull
    requests added panel prose -- so the wider net this rule casts had to learn
    the difference between a call and a sentence about one.

    Blanked rather than deleted, so every line number it reports still points at
    the line it came from.

    A `//` preceded by a colon is left alone. An over-eager strip would cut the
    rest of a line after "http://" and could hide a real call sitting behind a
    URL -- a false negative here is a bare fetch reaching the engine unseen,
    which is the direction that costs something.
    """
    blanked = re.sub(
        r"/\*.*?\*/",
        lambda m: re.sub(r"[^\n]", " ", m.group(0)),
        text,
        flags=re.S,
    )
    kept = []
    for line in blanked.split("\n"):
        cut = None
        for hit in re.finditer(r"//", line):
            if hit.start() and line[hit.start() - 1] == ":":
                continue
            cut = hit.start()
            break
        kept.append(line if cut is None else line[:cut])
    return "\n".join(kept)


def _sources() -> list[pathlib.Path]:
    return sorted(p for p in EXTENSION.glob("*.js") if p.name != OWNS_THE_REQUEST_PATH)


def test_no_module_but_the_request_path_fetches_the_engine():
    """The defect this closes, stated as a rule: a request to the engine that does
    not go through `backend.js` throws its status away, and reports a failure it
    cannot describe. The deadline and the aborts come from the `window.fetch`
    override in the same file and were never the missing part -- saying they were
    sent an earlier reading of this to the wrong layer."""
    offenders = []
    for path in _sources():
        text = path.read_text(encoding="utf-8")
        # PER FILE, NOT PER 200 CHARACTERS. This read a window either side of
        # the `fetch(` and claimed, in its own comment, to catch the call
        # "however the URL is spelled" -- which a window cannot do: assign the
        # base 250 characters earlier, or build the URL in a helper, and it sees
        # nothing. The rule that holds is about the MODULE: one that knows the
        # engine's address does not also call `fetch` itself. Measured when this
        # replaced the window: ZERO modules newly offend, so the wider net costs
        # nothing today and closes the spellings a window never covered. A module
        # that genuinely fetches something else belongs in NOT_THE_ENGINE, which
        # already reasons per file and is checked by the test below.
        if "backendBase" not in text and "backend +" not in text:
            continue
        for match in _FETCH.finditer(_code_only(text)):
            line = text.count(chr(10), 0, match.start()) + 1
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

    # THE OPT-OUT LIVES ONLY IN THIS FILE. `throwOnHttpError: false` is how a
    # caller says "I read the status myself", and it is worth nothing if a call
    # site elsewhere can pass it.
    #
    # It was "exactly once" when `raw()` was the only user, and that broke the
    # moment `range()` and `sourceFor()` arrived — both of which read the status
    # for a real reason: a 206 is the SUCCESS case for a byte range, and `api()`
    # would have to be told that. The rule was pinned to a count when what it
    # means is a location, and the count is what changed.
    # WHO OWNS ITS STATUS, AND WHO MUST NOT -- both directions, because each
    # was wrong here in turn.
    #
    # `>= 1` was satisfied by any two of the three, so a function could lose its
    # opt-out unseen. Then the list itself was wrong: `sourceFor` and `range`
    # were on it because "a 206 is the SUCCESS case", and `res.ok` covers
    # 200-299, so a 206 was never an error to `request()` and neither ever
    # needed to read the status. Opting out anyway mapped EVERY non-206 to
    # "this engine will not serve byte ranges" -- a transient 500, or the 416
    # Starlette answers for `bytes=0-0` on an empty file -- and `app.js` answers
    # that by downloading the whole archive, which is the 541,531,989-byte read
    # that came back 0 on his machine.
    owns = {
        "raw": "a 404 from /api/native/status means 'this engine is too old', not a failure, and the restart poll needs a refusal to be ordinary",
    }
    must_not = {
        "sourceFor": "every non-206 would become \"no-range\", and app.js answers that by buffering the whole archive",
        "range": "an error status would lose the engine's own detail for no gain, since 200 and 206 are both ok",
    }
    for owner, why in {**owns, **must_not}.items():
        start = text.find(f"export async function {owner}(")
        assert start != -1, f"`{owner}()` is gone from backend.js"
        body = text[start:text.find(chr(10) + "export ", start + 1)]
        opts_out = "throwOnHttpError: false" in body
        if owner in owns:
            assert opts_out, (
                f"`{owner}()` no longer owns its own status handling, and {why}")
        else:
            assert not opts_out, (
                f"`{owner}()` opts out of the status check again: {why}")
    for source in _sources():
        assert "throwOnHttpError" not in source.read_text(encoding="utf-8"), (
            f"{source.name} passes the status opt-out directly instead of calling "
            "`raw()`, which is the same escape by a longer route")


def test_the_archive_is_read_through_it():
    """The specific call that failed on his machine, named so a rewrite that
    reintroduces the bare fetch fails here rather than in Drive."""
    app = (EXTENSION / "app.js").read_text(encoding="utf-8")
    assert 'await sourceFor("/api/bundle/archive")' in app, (
        "the Drive backup no longer reads the archive through the request path. It "
        "must be a SOURCE and not `bytes()`: holding 541,531,989 bytes in one Blob "
        "is what came back empty on his machine, and `bytes()` holds a whole body")
    # NOT "never buffer it whole" -- that was the rule as a LITERAL, and a
    # correct change broke it. The knowledge is that the DEFAULT path streams,
    # and a whole-body read of the archive is allowed only where an engine that
    # will not serve byte ranges leaves no other way to back up at all. Pinned as
    # an ordering and a betweenness rather than a fixed window, because a window
    # is a count in disguise and counts are what keep going stale here.
    whole = app.find('await bytes("/api/bundle/archive")')
    if whole != -1:
        streamed = app.find('await sourceFor("/api/bundle/archive")')
        assert streamed != -1 and streamed < whole, (
            "app.js reads the archive whole BEFORE it tries to stream it, so the "
            "541,531,989-byte Blob that came back empty on 2026-09-03 is the "
            "default path again rather than a fallback")
        assert '"no-range"' in app[streamed:whole], (
            "app.js reads the archive whole without first proving the engine "
            "refused a byte range. The whole-body read exists ONLY for an engine "
            "that cannot serve ranges; anywhere else it is the original defect")
    assert 'await bytes("/api/bundle/panel-pack")' in app, (
        "the panel-pack no longer reads through the request path")
    assert "fetch(base + " not in app, (
        "a bare fetch against the engine's base address is back in app.js")
