"""The update report crosses a seam, and nothing has ever asserted its shape.

THE DEFECT THIS EXISTS FOR, MEASURED. `create_update_router()` returns the phase,
the progress and the failure detail nested under `progress_state`, and names the
refusal reason `self_update_blocked_because`. The panel's first caller read
`report.phase`, `report.progress` and `report.detail` — three keys that are not at
the top level — so the downloading, staged and failed sentences never rendered,
the poll exited on its first iteration, and the two opposite refusal causes that
`update_api.py` keeps separate on purpose collapsed into one generic sentence.

**AND FIVE PANEL TESTS WERE GREEN THROUGHOUT**, because their fixture invented the
flattened shape and their stub replaced `window.fetch` wholesale, so no test on
either side ever saw the real body. The code and the tests shared one wrong
assumption, and neither could expose the other. A mutation check passed five times
out of five: it proved the tests depended on the code, and nothing about whether
either matched the thing they described.

So this file asserts the CONTRACT rather than either side of it. It reads the keys
the engine actually emits and the keys the panel actually reads, and fails when
they disagree — which is the only check that could have caught the original
defect, and the only one that catches the next rename.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Read out of the panel's source rather than listed here, so this cannot drift
#: into a second copy of the truth — the failure mode the whole file is about.
PANEL = ROOT / "extension" / "app.js"

#: `report.<name>`, read only inside the functions that consume the UPDATE report.
#: The panel has another `report` — the version notice's — and scanning the whole
#: file catches its fields too, which would fail this for reasons that are not the
#: contract. Measured before narrowing: the unscoped pattern reported fourteen
#: names, eight of them the version notice's.
READS = re.compile(r"\breport\.([a-z_][a-z0-9_]*)", re.IGNORECASE)

#: The readers, by name. Slicing source between markers is a trap this repository
#: has already paid for — a window that silently becomes empty asserts nothing —
#: so `_update_readers` refuses an empty or suspiciously short slice rather than
#: returning one.
READERS = ("function engineUpdateSentence(", "async function pollEngineUpdate(")


def _update_readers() -> str:
    """The source of the functions that read the update report, and only those."""
    source = PANEL.read_text(encoding="utf-8")
    out = []
    for opener in READERS:
        assert source.count(opener) == 1, (
            f"{opener!r} is not in {PANEL.name} exactly once — this slice cannot "
            "be trusted, and a slice that cannot be trusted asserts nothing")
        start = source.index(opener)
        # To the next top-level `function`/`async function`, which is where each
        # of these ends in this file.
        rest = source[start + len(opener):]
        nxt = re.search(r"\n(?:async )?function ", rest)
        out.append(rest[:nxt.start()] if nxt else rest)
    slice_ = "\n".join(out)
    assert len(slice_) > 400, (
        f"the reader slice is {len(slice_)} characters, which is too short to be "
        "the two functions — the markers moved and this guard went blind")
    return slice_


def _engine_report() -> dict:
    """The body `GET /api/update` really returns, from the real router.

    Built by mounting the router rather than by copying its dict, because a copy
    is exactly what went wrong: the panel's fixture was a copy that had drifted.
    """
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from scrapex.webui import update_api

    # The worktree trap: `scrapex` is pip-installed editable against the MAIN
    # checkout, so a test that measures the wrong tree is silently useless. Assert
    # on the file AND on a symbol, because a path alone cannot catch a stale copy.
    assert str(ROOT) in str(pathlib.Path(update_api.__file__).resolve()), (
        f"update_api came from {update_api.__file__}, not from {ROOT}")
    assert hasattr(update_api, "create_update_router")

    app = FastAPI()
    app.include_router(update_api.create_update_router())
    response = TestClient(app).get("/api/update")
    assert response.status_code == 200, response.text
    return response.json()


def _panel_reads() -> set[str]:
    return set(READS.findall(_update_readers()))


def test_the_engine_still_answers_the_update_report():
    """A shape test is worthless if the route stopped answering."""
    report = _engine_report()
    assert isinstance(report, dict) and report, "GET /api/update returned nothing"


def _normaliser() -> str:
    """`engineUpdateState`'s own source, which is where the flatten must live."""
    source = PANEL.read_text(encoding="utf-8")
    opener = "async function engineUpdateState() {"
    assert source.count(opener) == 1, f"{opener!r} is not in {PANEL.name} once"
    rest = source[source.index(opener) + len(opener):]
    nxt = re.search(r"\n(?:async )?function ", rest)
    body = rest[:nxt.start()] if nxt else rest
    assert len(body) > 200, (
        f"the normaliser slice is {len(body)} characters — the marker moved and "
        "this guard went blind")
    return body


def _normaliser_adds() -> set[str]:
    """What the normaliser ADDS, read from its source rather than listed here.

    THE FIRST VERSION OF THIS FILE LISTED `{"blocked"}` AS A CONSTANT, and both
    repairs could then be deleted with every test still green: the constant said
    `blocked` existed whether or not the code produced it, and the flatten was
    never checked at all. **A hand-written map compared against a hand-written map
    asserts that two people agree, not that the code does** — which is the same
    defect this whole file was written about, one level in, committed by the file
    written about it.
    """
    body = _normaliser()
    adds = set()
    for name, produced in re.findall(r"(\w+)\s*:\s*body\.(\w+)", body):
        adds.add(name)
    assert "...(body.progress_state || {})" in body.replace(" ", "").replace(
        "...(body.progress_state||{})", "...(body.progress_state || {})") or \
        "...(body.progress_state||{})" in body.replace(" ", ""), (
        "`engineUpdateState` no longer flattens `progress_state`, so `phase`, "
        "`progress` and `detail` are `undefined` at every reader again — the "
        "original defect, restored")
    return adds


def test_every_field_the_panel_reads_survives_the_normaliser():
    """THE ASSERTION THE ORIGINAL DEFECT WOULD HAVE FAILED.

    Not "does the panel read sensible names" — it did; they were the names inside
    `progress_state`. The question is whether they reach the reader, and that is a
    chain of three: what the engine sends, what the normaliser makes of it, what
    the readers ask for. Asserting either end against the other is what produced
    the defect — the readers were checked against a fixture, and the fixture was a
    copy of a shape that had drifted.
    """
    report = _engine_report()
    available = (set(report)
                 | set(report.get("progress_state") or {})
                 | _normaliser_adds())
    read = _panel_reads()
    NORMALISER_ADDS = _normaliser_adds()

    missing = sorted(read - available)
    assert not missing, (
        f"the panel reads report.{{{', '.join(missing)}}} and nothing produces "
        f"them. The engine sends {sorted(report)}; `progress_state` carries "
        f"{sorted(report.get('progress_state') or {})}; the normaliser adds "
        f"{sorted(NORMALISER_ADDS)}. Every name outside that set is `undefined` at "
        "run time, so the sentence built from it is empty or wrong and NOTHING "
        "FAILS — which is how this shipped green the first time.")


def test_the_nested_progress_block_is_still_where_the_panel_expects_it():
    """The normaliser flattens `progress_state`, so its own shape is a contract.

    Named separately because the failure it guards is silent in the other
    direction: if the engine stops nesting, the flatten becomes a no-op and every
    phase sentence goes empty again, with the key-agreement test above still green
    because the names would then be top level.
    """
    report = _engine_report()
    assert "progress_state" in report, (
        "the engine no longer nests the phase under `progress_state`. The panel "
        "flattens that block on arrival; if it is gone, delete the flatten in "
        "`engineUpdateState` rather than leaving a spread over `undefined`.")

    block = report["progress_state"]
    assert isinstance(block, dict)
    for field in ("phase", "progress", "detail"):
        assert field in block, (
            f"`progress_state` no longer carries `{field}`, which the panel reads "
            "after flattening")

    assert isinstance(block["progress"], dict) and "percent" in block["progress"], (
        "the panel renders `progress.percent`; the engine no longer sends it")


def test_the_refusal_reason_is_its_own_field_and_not_the_failure_detail():
    """`OP-126`'s shape at the seam: two different facts must not share a name.

    `self_update_blocked_because` says why an update CANNOT START — a source
    checkout, a release with no digest. `progress_state.detail` says why one
    FAILED. Mapping the first onto the second would make the panel print a
    refusal where a failure belongs, and the panel would have no way to tell.
    """
    report = _engine_report()
    assert "self_update_blocked_because" in report, (
        "the engine no longer names the refusal reason separately, so the panel "
        "cannot say WHICH of the two opposite causes applies — which is the "
        "distinction `update_api.py` keeps the field for")
    assert "detail" not in report, (
        "a top-level `detail` on the update report would collide with the failure "
        "detail the panel flattens out of `progress_state`")


def test_the_panel_reads_the_refusal_reason_at_all():
    """The field existing is not the point; the panel using it is.

    This is the test that fails if someone repairs the key mismatch by flattening
    only `progress_state` and leaves the refusal reason unread — which would leave
    the two opposite causes still collapsed into one sentence, the original defect
    surviving its own fix.
    """
    source = PANEL.read_text(encoding="utf-8")
    assert "self_update_blocked_because" in source, (
        "nothing in the panel reads `self_update_blocked_because`, so a source "
        "checkout and a release with no SHA-256 produce the same sentence — the "
        "two states this feature exists to tell apart")
