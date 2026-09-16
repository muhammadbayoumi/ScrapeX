"""Nothing the engine downloads gets installed without matching its digest.

THIS IS THE SECURITY-RELEVANT PART OF `R-36`, so it is tested against a real
local HTTP server rather than a mocked `httpx`. The thing under test is a
STREAMED download with a running hash: a mock that hands back all the bytes in
one lump would satisfy every assertion here while exercising none of the code
that matters.

`R-36` part 3, at its narrowest, is what these tests hold to:

    A sha256 published in the release manifest, fetched over HTTPS from
    raw.githubusercontent.com, and CHECKED BEFORE THE SWAP, is enough to trust
    a download. It is NOT code signing and does not replace it.

`packaging/build_engine.py` had refused to build an updater and said why —
*"shipping an updater that fetches and executes unsigned code would be worse
than none"*. The digest is the only thing that answers that objection, so every
refusal below is about the digest, and none of them can be switched off by a
caller: there is no `verify=False`, and the staged path is returned only on
success, so no caller can misuse the result by forgetting to check a flag.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scrapex import release as release_mod
from scrapex import update as update_mod
from scrapex.release import Installer, Release
from scrapex.version import VERSION, parse_version

#: Big enough to arrive in several chunks (CHUNK_BYTES is 64 KiB), because a
#: payload that fits in one read would never exercise the streaming loop or the
#: running hash — which is the whole mechanism.
PAYLOAD = b"MZ" + b"scrapex-engine-pretend-binary\n" * 20_000
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


class _Host(BaseHTTPRequestHandler):
    """The release host, in the four ways it can behave.

    Path decides the behaviour so one server covers every case and the tests
    read as a list of situations rather than a list of fixtures.
    """

    def do_GET(self):                                    # noqa: N802
        if self.path == "/good":
            body = PAYLOAD
        elif self.path == "/tampered":
            # One byte different, at the END, so a check that hashed only the
            # first chunk would pass. That is the mistake this shape exists to
            # catch.
            body = PAYLOAD[:-1] + b"X"
        elif self.path == "/short":
            body = PAYLOAD[: len(PAYLOAD) // 2]
        elif self.path == "/huge":
            self.send_response(200)
            self.send_header("Content-Length", str(10 * 1024 * 1024 * 1024))
            self.end_headers()
            # Keep sending until the client stops us. If the ceiling does not
            # work, this test hangs — which is a louder failure than a wrong
            # assertion, and appropriate for a disk-filling defect.
            try:
                for _ in range(4000):
                    self.wfile.write(b"\0" * (1 << 16))
            except (BrokenPipeError, ConnectionAbortedError, OSError):
                pass
            return
        elif self.path == "/missing":
            self.send_response(404)
            self.end_headers()
            return
        else:
            self.send_response(500)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):                        # noqa: A003
        pass


@pytest.fixture(autouse=True)
def _local_origin_is_allowed_here(monkeypatch):
    """Let these tests fetch from 127.0.0.1 over http, and say so out loud.

    Production refuses both: `release.ALLOWED_INSTALLER_HOSTS` is github.com and
    raw.githubusercontent.com, and `ALLOWED_INSTALLER_SCHEMES` is https alone —
    because the published digest proves the CONTENT arrived whole and proves
    nothing about WHERE it was fetched from.

    The policy is patched HERE, at the top, by name, rather than by handing
    `fetch_and_verify` a parameter that relaxes it. A parameter would exist in
    production too, and the moment one exists it becomes the path somebody takes.
    The real policy is asserted unpatched in
    `test_the_engine_reads_the_same_release_feed.py`, on the near-miss hosts a
    substring check would have let through.
    """
    from scrapex import release as release_mod

    monkeypatch.setattr(release_mod, "ALLOWED_INSTALLER_HOSTS",
                        frozenset({"127.0.0.1"}))
    monkeypatch.setattr(release_mod, "ALLOWED_INSTALLER_SCHEMES",
                        frozenset({"http"}))


@pytest.fixture
def host():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Host)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _installer(host: str, path: str, *, sha256: str = DIGEST,
               size: int | None = None) -> Installer:
    return Installer(name="scrapex-engine.exe", url=f"{host}{path}",
                     bytes=len(PAYLOAD) if size is None else size,
                     sha256=sha256)


def test_a_good_download_is_staged_and_its_digest_is_reported(host, tmp_path):
    """The happy path, and it must report the digest it COMPUTED, not the one asked for.

    Returning the expected digest back would make the mismatch test below the
    only thing standing between a caller and a false confirmation.
    """
    staged = update_mod.fetch_and_verify(
        _installer(host, "/good"), "0.3.0", into=tmp_path)

    assert staged.path.exists()
    assert staged.path.read_bytes() == PAYLOAD
    assert staged.sha256 == DIGEST
    assert staged.bytes == len(PAYLOAD)
    assert staged.version == "0.3.0"
    # The name carries the version, so two versions cannot land on one filename.
    assert "0.3.0" in staged.path.name
    # And nothing half-written is left beside it.
    assert list(tmp_path.glob("*.part")) == []


def test_a_tampered_download_is_refused_and_deleted(host, tmp_path):
    """THE ONE THAT MATTERS. A single changed byte must stop the install.

    And the file must be GONE: a rejected 71 MB executable left in a staging
    directory is a thing somebody double-clicks a week later.
    """
    with pytest.raises(update_mod.UpdateRefused) as refused:
        update_mod.fetch_and_verify(
            _installer(host, "/tampered"), "0.3.0", into=tmp_path)

    assert "checksum" in str(refused.value).lower()
    assert DIGEST in str(refused.value), "the message must name what was expected"
    assert list(tmp_path.iterdir()) == [], (
        f"the refused download was left on disk: {list(tmp_path.iterdir())}")


def test_a_release_with_no_digest_is_refused_before_a_byte_is_fetched(host, tmp_path):
    """No digest, no install — and no download either.

    Asserted by the absence of any file: if this fetched first and refused
    after, it would spend 71 MB of somebody's connection to reach a conclusion
    available for free.
    """
    with pytest.raises(update_mod.UpdateRefused) as refused:
        update_mod.fetch_and_verify(
            _installer(host, "/good", sha256=""), "0.3.0", into=tmp_path)

    assert "sha-256" in str(refused.value).lower()
    assert list(tmp_path.iterdir()) == []


def test_a_digest_that_is_not_a_digest_is_refused(host, tmp_path):
    """A truncated or padded digest must not be accepted as "close enough"."""
    for bad in ("deadbeef", DIGEST[:-1], DIGEST + "00", "not-a-digest" * 5):
        with pytest.raises(update_mod.UpdateRefused):
            update_mod.fetch_and_verify(
                _installer(host, "/good", sha256=bad), "0.3.0", into=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_a_digest_that_matches_only_at_its_START_is_refused(host, tmp_path):
    """A WEAKENED COMPARISON, which is how this check gets defeated rather than deleted.

    Every other test here supplies a digest that differs from the real one
    everywhere, so a comparison shortened to `expected[:8] == actual[:8]` — or
    degenerated to a `startswith` — would refuse those and pass. **Both
    mutations survived until this test existed.**

    These two share a long prefix with the true digest and differ late, so only
    a full comparison rejects them. `hmac.compare_digest` is what does that in
    `update._digest_matches`; the value of this test is that shortening it now
    fails here instead of silently accepting a substituted binary whose digest
    was ground to share a prefix.
    """
    last_char_differs = DIGEST[:-1] + ("0" if DIGEST[-1] != "0" else "1")
    tail_differs = DIGEST[:40] + ("f" * 24 if not DIGEST.endswith("f" * 24)
                                  else "e" * 24)
    assert last_char_differs != DIGEST and len(last_char_differs) == 64
    assert tail_differs != DIGEST and len(tail_differs) == 64

    for near in (last_char_differs, tail_differs):
        with pytest.raises(update_mod.UpdateRefused) as refused:
            update_mod.fetch_and_verify(
                _installer(host, "/good", sha256=near), "0.3.0", into=tmp_path)
        assert "checksum" in str(refused.value).lower()
        assert list(tmp_path.iterdir()) == [], (
            "a near-miss digest left the download on disk")


def test_the_digest_is_matched_case_insensitively(host, tmp_path):
    """An upper-case digest in a manifest is the same digest.

    Worth a test because the natural fix for it — lowercasing on the way in —
    is easy to lose in a refactor, and losing it would refuse every good
    download from a manifest written by a different tool.
    """
    staged = update_mod.fetch_and_verify(
        _installer(host, "/good", sha256=DIGEST.upper()), "0.3.0", into=tmp_path)
    assert staged.sha256 == DIGEST


def test_a_manifest_that_disagrees_with_itself_is_refused(host, tmp_path):
    """Digest right, size wrong: the release was built wrong, so refuse it.

    A digest match already proves the bytes, so this can only mean the
    manifest's own two fields disagree — and if the release process got one
    wrong, something else in it may be wrong too.
    """
    with pytest.raises(update_mod.UpdateRefused) as refused:
        update_mod.fetch_and_verify(
            _installer(host, "/good", size=len(PAYLOAD) + 999), "0.3.0", into=tmp_path)

    assert "disagrees with itself" in str(refused.value)
    assert list(tmp_path.iterdir()) == []


def test_a_truncated_download_is_refused(host, tmp_path):
    """Half a file hashes to something else, which is the point of hashing it."""
    with pytest.raises(update_mod.UpdateRefused):
        update_mod.fetch_and_verify(
            _installer(host, "/short"), "0.3.0", into=tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_a_404_is_refused_without_writing_anything(host, tmp_path):
    with pytest.raises(update_mod.UpdateRefused) as refused:
        update_mod.fetch_and_verify(
            _installer(host, "/missing"), "0.3.0", into=tmp_path)
    assert "404" in str(refused.value)
    assert list(tmp_path.iterdir()) == []


def test_an_endless_response_is_stopped_before_it_fills_the_disk(host, tmp_path, monkeypatch):
    """A ceiling, because a digest that will never match is not a stopping condition.

    Without this, a misconfigured endpoint or a redirect to something enormous
    writes until the disk is full and only THEN fails the digest. The real
    ceiling is 300 MB; it is lowered here so the test costs a moment instead of
    a third of a gigabyte.
    """
    monkeypatch.setattr(update_mod, "MAX_INSTALLER_BYTES", 2 * 1024 * 1024)
    with pytest.raises(update_mod.UpdateRefused) as refused:
        update_mod.fetch_and_verify(
            _installer(host, "/huge"), "0.3.0", into=tmp_path)

    assert "larger than any engine" in str(refused.value)
    assert list(tmp_path.iterdir()) == [], "the oversized partial was not cleaned up"


def test_progress_is_reported_while_it_downloads_and_not_only_at_the_end(host, tmp_path):
    """A progress bar that jumps 0 → 100 is a spinner with extra steps.

    The payload is deliberately larger than one chunk, so more than one call
    proves the callback rides the stream rather than the return.
    """
    seen: list[tuple[int, int]] = []
    update_mod.fetch_and_verify(
        _installer(host, "/good"), "0.3.0", into=tmp_path,
        progress=lambda received, total: seen.append((received, total)))

    assert len(seen) > 1, f"progress was reported {len(seen)} time(s): {seen}"
    assert [r for r, _ in seen] == sorted(r for r, _ in seen), "progress went backwards"
    assert seen[-1][0] == len(PAYLOAD)
    assert all(total == len(PAYLOAD) for _, total in seen)


def test_two_attempts_at_one_version_do_not_accumulate_files(host, tmp_path):
    """The staging directory must not grow by 71 MB every time a button is pressed."""
    for _ in range(3):
        update_mod.fetch_and_verify(_installer(host, "/good"), "0.3.0", into=tmp_path)
    assert len(list(tmp_path.iterdir())) == 1


def test_a_failed_attempt_does_not_destroy_an_already_staged_good_one(host, tmp_path):
    """A rejected download of a version must not take the verified one with it.

    This is a real ordering question: the partial is written under `.part` and
    only replaces the final name after the digest passes, so a later failure
    has nothing to overwrite. Asserted because the obvious implementation —
    writing straight to the final name — would delete a good installer on a
    failed retry.
    """
    good = update_mod.fetch_and_verify(
        _installer(host, "/good"), "0.3.0", into=tmp_path)
    assert good.path.exists()

    with pytest.raises(update_mod.UpdateRefused):
        update_mod.fetch_and_verify(
            _installer(host, "/tampered"), "0.3.0", into=tmp_path)

    assert good.path.exists(), "a refused retry deleted the verified installer"
    assert good.path.read_bytes() == PAYLOAD


def test_a_source_checkout_says_it_cannot_swap_rather_than_offering_to(monkeypatch):
    """There is no executable to replace in a checkout, and saying so beats failing."""
    monkeypatch.setattr("sys.frozen", False, raising=False)
    possible, why = update_mod.swap_is_possible()
    assert possible is False
    assert "git" in why.lower(), why


def test_the_swap_plan_names_what_it_would_overwrite(monkeypatch, tmp_path):
    """A plan that cannot say what it replaces is not a plan anybody should approve."""
    exe = tmp_path / "scrapex-engine.exe"
    exe.write_bytes(b"MZ")
    monkeypatch.setattr("sys.frozen", True, raising=False)
    monkeypatch.setattr("sys.executable", str(exe))

    staged = update_mod.Staged(path=tmp_path / "new.exe", version="0.3.0",
                              sha256=DIGEST, bytes=len(PAYLOAD))
    plan = update_mod.plan_swap(staged)

    assert plan["possible"] is True
    assert plan["replaces"], "the plan does not say which file it would overwrite"
    assert "scrapex-engine.exe" in plan["replaces"]
    assert plan["sha256"] == DIGEST
    assert len(plan["steps"]) >= 4
    # The ordering IS the safety argument: the helper must wait for this process
    # to exit before renaming, or Windows refuses and the install half-happens.
    joined = " | ".join(plan["steps"])
    assert joined.index("waits for this process to exit") < joined.index("rename")


def test_an_installer_from_a_host_we_do_not_publish_to_is_refused(host, tmp_path,
                                                                 monkeypatch):
    """THE GAP CodeQL POINTED AT, closed in production rather than in the test.

    Its alert was `py/incomplete-url-substring-sanitization` against
    `"raw.githubusercontent.com" in url` in a sibling test. That assertion was
    not a security control — but the ABSENCE of one was the real finding: nothing
    checked that the URL the engine is told to fetch belongs to us. The digest
    proves the content arrived whole; it says nothing about where the request
    went, and a mistaken or edited manifest could send a user's address anywhere.

    Refused BEFORE a byte is requested, which is why this asserts on an empty
    directory as well as on the message.
    """
    from scrapex import release as release_mod

    # Undo the fixture: this test wants the real policy.
    monkeypatch.setattr(release_mod, "ALLOWED_INSTALLER_HOSTS",
                        frozenset({"github.com"}))
    monkeypatch.setattr(release_mod, "ALLOWED_INSTALLER_SCHEMES",
                        frozenset({"https"}))

    with pytest.raises(update_mod.UpdateRefused) as refused:
        update_mod.fetch_and_verify(
            _installer(host, "/good"), "0.3.0", into=tmp_path)

    assert "does not publish to" in str(refused.value)
    assert list(tmp_path.iterdir()) == [], (
        "an off-host installer was fetched before being refused")


# ===========================================================================
# THE ROUTE THAT DRIVES ALL OF THE ABOVE, AND NOTHING HAD EVER EXECUTED IT.
#
# Everything above calls `scrapex.update` directly. `POST /api/update`
# (`scrapex/webui/update_api.py:147`) is the only thing that calls it in
# production, and until these tests its 35 statements had run zero times —
# `start()`, its inner `work` and `tick`, and `plan` were entered by nothing,
# which is what left the module at 45.2%. MEASURED, not assumed: with
# `raise AssertionError("reached")` as the first statement of `start()`, all
# sixteen tests above stayed green (#962).
#
# NONE OF IT NEEDS A NETWORK, AN INSTALLER OR A FROZEN BUILD.
# `create_update_router()` reads `release_mod` and `update_mod` at module
# scope, so both are replaceable by name — the same door
# `_local_origin_is_allowed_here` uses above, and for the same reason: a
# parameter that relaxed this would exist in production too.
#
# WHAT THE BRANCHES ARE, in the order `start()` takes them: an update already
# running, a release feed that cannot be read, a published version that is not
# newer, a release with no installer attached, and then the worker thread —
# whose three outcomes are a refusal, a transport failure, and a download that
# is STAGED. Never installed; see the test that says so.
# ===========================================================================


def _one_version_newer(installed: str) -> str:
    major, minor, patch = parse_version(installed)
    return f"{major}.{minor}.{patch + 1}"


#: A published version this engine would take as an update, DERIVED from the
#: engine's own number rather than written down. A literal stops being newer the
#: day `VERSION` passes it, and every test below would then quietly exercise the
#: "already the published version" branch while still passing.
NEWER_VERSION = _one_version_newer(VERSION)


def _attached(size: int = 4096) -> Installer:
    """The installer a published release attaches, as `read_manifest` builds it."""
    return Installer(
        name="scrapex-engine.exe",
        url=(f"https://github.com/{release_mod.PUBLIC_REPO}/releases/download/"
             f"engine-v{NEWER_VERSION}/scrapex-engine.exe"),
        bytes=size, sha256=DIGEST)


def _a_release(*, installer: Installer | None, version: str = NEWER_VERSION,
               state: str = "ok", detail: str = "") -> Release:
    """What `release.latest()` answers, built as the REAL dataclass.

    Never a stand-in with the same four attributes: `start()` reads `.ok`,
    `.version`, `.detail` and `.installer` off this, and a look-alike would keep
    passing on the day one of them is renamed.
    """
    return Release(state=state, detail=detail, version=version,
                   tag=f"engine-v{version}",
                   url=f"https://github.com/{release_mod.PUBLIC_REPO}/releases",
                   installer=installer)


def _staged(tmp_path, version: str, size: int) -> update_mod.Staged:
    """What a verified download looks like coming back out of `fetch_and_verify`.

    The file is deliberately never written. The route is meant to RECORD where a
    verified installer is and do nothing else with it, so a path that does not
    exist is a fair thing to hand it.
    """
    return update_mod.Staged(path=tmp_path / f"scrapex-engine-{version}.exe",
                             version=version, sha256=DIGEST, bytes=size)


def _download_threads() -> list[threading.Thread]:
    return [t for t in threading.enumerate() if t.name == "scrapex-update"]


def _let_the_download_finish(timeout: float = 10.0) -> None:
    """JOIN the worker by name. Never sleep and hope.

    `start()` names its thread `scrapex-update` and returns before it has done
    anything, so every assertion about the outcome has to wait for something
    real. A `time.sleep` here would be a guess that passes on this box and flakes
    on a loaded runner — and the flake would read as the route's fault.
    """
    deadline = time.monotonic() + timeout
    for thread in _download_threads():
        thread.join(timeout=max(0.0, deadline - time.monotonic()))
    still_going = _download_threads()
    assert not still_going, (
        f"the update worker was still running after {timeout}s: {still_going}")


def _progress_state(response) -> dict:
    """The `progress_state` block, which is where every answer here lives."""
    assert response.status_code == 200, response.text
    return response.json()["progress_state"]


def _recorded(calls: list[str], name: str, behaviour):
    def recorder(*args, **kwargs):
        calls.append(name)
        return behaviour(*args, **kwargs)

    recorder.__name__ = name
    return recorder


@pytest.fixture
def updater(monkeypatch):
    """`scrapex.update`, with EVERY function it exposes replaced by a recorder.

    NOT ONLY THE TWO THE ROUTE NAMES, and that is the point. The claim under
    test is a negative one — `start()`'s docstring says it "does NOT install it"
    and that "calling this endpoint has never done it" — and a negative claim is
    only as strong as the list of names it covers. So the whole surface is
    replaced and `calls` is asserted as an exact list; the completeness check
    below then fails the day a function is added to `scrapex.update` without
    being named here, because a new one is a new thing this route could call
    with nothing watching.
    """
    control = types.SimpleNamespace(
        calls=[],
        #: Every `(installer, version)` the route handed the verifier. Recorded
        #: rather than merely counted: the installer carries the sha256, which is
        #: the entire substance of `R-36` part 3, and a route that passed a
        #: DIFFERENT installer would satisfy a call count exactly as well.
        verified=[],
        #: What the worker's verifier does. Every test that lets the thread run
        #: sets it; there is no working default, because a silent one would let
        #: a test assert on an outcome nobody chose.
        verify=None,
        #: What `plan_swap` answers, and what it was handed.
        plan={"possible": True, "detail": "", "verified_installer": "",
              "sha256": "", "version": "", "replaces": "", "steps": ["a step"]},
        planned=[],
    )

    def fetch_and_verify(installer, version, *, progress=None, **unused):
        control.verified.append((installer, version))
        assert control.verify is not None, (
            "the worker reached the verifier and the test never said what it "
            "should do")
        return control.verify(installer, version, progress)

    def plan_swap(staged):
        control.planned.append(staged)
        return dict(control.plan)

    def _never(name):
        def refuse(*args, **kwargs):
            raise AssertionError(
                f"the update route called update.{name}(), which no branch of it "
                "has any business calling")

        return refuse

    replacements = {
        "fetch_and_verify": fetch_and_verify,
        "plan_swap": plan_swap,
        # `GET /api/update` asks this on every poll, so it is answered rather
        # than refused — and answered WITHOUT reading `sys.frozen`, which the
        # real one does. Letting the real one through would make these tests say
        # one thing on his frozen build and another in a checkout, and a third
        # on Linux CI.
        "swap_is_possible": lambda: (True, ""),
        "staging_dir": _never("staging_dir"),
        "discard": _never("discard"),
        "clear_staging": _never("clear_staging"),
    }
    exposed = sorted(
        name for name, value in vars(update_mod).items()
        if not name.startswith("_") and isinstance(value, types.FunctionType)
        and value.__module__ == update_mod.__name__)
    assert exposed == sorted(replacements), (
        f"`scrapex.update` exposes {exposed}; this fixture replaces "
        f"{sorted(replacements)}. Name the new one here — an unreplaced function "
        "is one this route can call for real, and `calls` would not see it.")

    for name, behaviour in replacements.items():
        monkeypatch.setattr(update_mod, name,
                            _recorded(control.calls, name, behaviour))
    return control


@pytest.fixture
def published(monkeypatch):
    """What the release feed says, and the one thing here that would use a socket.

    Patched by name for the same reason as the policy above: `release.latest()`
    is a real HTTP request with a four-second timeout, and a route test that made
    it would be testing the network.
    """
    control = types.SimpleNamespace(release=_a_release(installer=_attached()))
    monkeypatch.setattr(release_mod, "latest", lambda **unused: control.release)
    return control


@pytest.fixture
def nothing_the_worker_does_goes_unnoticed(monkeypatch):
    """The two ways this route could misbehave with every assertion below green.

    A WORKER THAT DIES AFTER SETTING THE PHASE IS INVISIBLE. `work()` writes the
    state on its second-to-last statement and the thread is a daemon, so a crash
    on any line after `_set(phase="staged", ...)` leaves the panel reading
    `staged`, the join succeeding, and the traceback arriving as a pytest
    warning nobody's gate reads. MEASURED: a `subprocess.Popen` of the staged
    installer added after that `_set` kept all thirty tests here passing.

    AND INSTALLING IS NOT A CALL INTO `scrapex.update`. The `updater` fixture
    watches that module's whole surface, which is why it reads as proof that
    nothing was installed — but a swap is `Popen`, `os.startfile` or `os.execv`,
    and none of those is in it. `start()`'s promise is a negative one, so the
    mechanisms an install would actually use are banned here by name; the
    `updater` fixture's completeness check cannot cover a module it does not
    own, and this is the other half of that guard.
    """
    faults: list[str] = []
    previous_hook = threading.excepthook

    def hook(args):
        if getattr(args.thread, "name", "") == "scrapex-update":
            faults.append(f"{args.exc_type.__name__}: {args.exc_value}")
        previous_hook(args)

    monkeypatch.setattr(threading, "excepthook", hook)

    def _no_process(name):
        def refuse(*args, **kwargs):
            raise AssertionError(
                f"the update route called {name}(). POST /api/update stages a "
                "verified installer and runs nothing; the swap is a separate "
                "act with its own approval")

        return refuse

    monkeypatch.setattr(subprocess, "Popen", _no_process("subprocess.Popen"))
    monkeypatch.setattr(subprocess, "run", _no_process("subprocess.run"))
    # `startfile` exists on Windows alone, and `execv` everywhere — named by
    # `hasattr` rather than by `sys.platform` so this says the same thing on his
    # box and on Linux CI.
    for launcher in ("startfile", "execv", "execvp", "execl"):
        if hasattr(os, launcher):
            monkeypatch.setattr(os, launcher, _no_process(f"os.{launcher}"))

    yield faults

    assert not faults, (
        f"the update worker died after the route had already reported its "
        f"outcome, so nothing else here noticed: {faults}")


@pytest.fixture
def panel(updater, published, nothing_the_worker_does_goes_unnoticed):
    """The update routes, mounted the way `scrapex/webui/app.py:650` mounts them.

    A FRESH ROUTER PER TEST. `create_update_router` keeps the phase, the lock and
    the one-at-a-time flag in a closure, so a shared router would carry a staged
    version into the test that asserts nothing is staged.

    It takes all three patches as dependencies so that no test can reach the
    route with the real `release.latest()` or the real `fetch_and_verify` behind
    it, or with a worker free to die quietly or start a process.
    """
    pytest.importorskip("fastapi")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from scrapex.webui import update_api

    app = FastAPI()
    app.include_router(update_api.create_update_router())
    return TestClient(app)


def test_the_version_these_route_tests_are_built_on_really_is_an_update():
    """One derivation, six tests, so it is asserted rather than trusted."""
    assert release_mod.is_newer(NEWER_VERSION, VERSION), (
        f"{NEWER_VERSION} is not newer than {VERSION}")
    assert not release_mod.is_newer(VERSION, VERSION)
    assert release_mod.is_newer(VERSION, "0.0.1"), (
        "0.0.1 is used below as a version older than this engine's")


def test_a_second_press_while_one_is_running_is_refused_rather_than_queued(
        panel, published, updater, tmp_path):
    """One download at a time, and the second press must SAY so.

    Not politeness. Two downloads of one version write the same staging
    filename, and the loser replaces a verified file with a partial one under a
    name that means "verified" (`update_api.py:78`). The flag is set on the
    request thread before the worker starts, so the second POST below is
    deterministic rather than a race.
    """
    size = 8_000
    may_finish = threading.Event()

    def verify(installer, version, progress):
        assert may_finish.wait(timeout=10), "the test never released the worker"
        return _staged(tmp_path, version, size)

    published.release = _a_release(installer=_attached(size=size))
    updater.verify = verify
    first = panel.post("/api/update").json()
    try:
        assert first["started"] is True
        # The worker is parked before its first tick, so the bar the panel is
        # handed at the start is knowable: nothing received, the published size
        # as the total.
        assert first["progress_state"]["progress"] == {
            "received": 0, "total": size, "percent": 0}
        # The sentence the panel shows for the next four minutes, and the ONE
        # word it must never contain: this endpoint downloads, and an owner told
        # "Installing 0.4.16" would read a swap that has not been approved and
        # will not happen here.
        assert first["detail"] == first["progress_state"]["detail"]
        assert "Downloading" in first["detail"], first["detail"]
        assert "install" not in first["detail"].lower(), first["detail"]
        # And the worker is a daemon, so a panel restart is not held open by a
        # 70 MB fetch nobody is waiting for.
        assert [t.daemon for t in _download_threads()] == [True], (
            "the update worker would keep the engine process alive at shutdown")

        second = panel.post("/api/update").json()
        assert second["started"] is False
        assert "already running" in second["detail"].lower(), second["detail"]
        # And it reports the run that IS going, rather than a fresh state.
        assert second["progress_state"]["phase"] == "downloading"
    finally:
        may_finish.set()
        _let_the_download_finish()

    assert updater.calls == ["fetch_and_verify"], (
        f"the refused press still reached scrapex.update: {updater.calls}")


def test_the_flag_is_set_on_the_request_thread_before_the_worker_is_started(
        panel, published, updater, monkeypatch):
    """Where `running.set()` lives is the difference between a guard and a race.

    THE TEST ABOVE DOES NOT PIN THIS, and that was measured: moving
    `running.set()` from the request thread into `work()` keeps it green,
    because a worker parked in the verifier has already set the flag by the time
    the second press arrives. *Usually* is the defect — two presses a
    millisecond apart would both get through, and two downloads of one version
    write the same staging filename, the loser replacing a verified file with a
    partial one under a name that means "verified" (`update_api.py:78`).

    So the worker is stopped from running AT ALL here. Only the thread this
    route names is held back; `TestClient` runs the request on a thread of its
    own and would deadlock if every thread were.
    """
    real_start = threading.Thread.start

    def start_everything_except_the_worker(self):
        if self.name == "scrapex-update":
            return          # never started, so there is nothing to join
        return real_start(self)

    monkeypatch.setattr(threading.Thread, "start",
                        start_everything_except_the_worker)
    published.release = _a_release(installer=_attached())
    updater.verify = lambda *unused: pytest.fail("the worker was allowed to run")

    assert panel.post("/api/update").json()["started"] is True
    second = panel.post("/api/update").json()

    assert second["started"] is False, (
        "the second press started a second download of the same version: the "
        "flag is being set inside the worker, so a press that arrives before "
        "the thread is scheduled slips past it")
    assert "already running" in second["detail"].lower(), second["detail"]
    assert updater.calls == []
    assert not _download_threads()


def test_a_release_feed_that_cannot_be_read_fails_the_phase_and_says_why(
        panel, published, updater):
    """`offline` and `unreadable` are refusals that arrive WITH a reason.

    The route has one sentence of its own for this branch and uses it only when
    the feed gave none — so a test that asserted the fallback alone would pass
    while the real reason (a timeout, a manifest for another product) was thrown
    away on the way to the panel. Both are asserted.
    """
    published.release = _a_release(
        state="offline", version="", installer=None,
        detail=("Could not reach the release endpoint. The engine you have "
                "keeps working."))
    body = panel.post("/api/update").json()
    assert body["started"] is False
    assert body["progress_state"]["phase"] == "failed"
    assert body["detail"] == published.release.detail
    assert body["progress_state"]["detail"] == published.release.detail

    # And the fallback, for a state that arrives with nothing to say.
    published.release = _a_release(state="unreadable", version="",
                                   installer=None, detail="")
    body = panel.post("/api/update").json()
    assert body["started"] is False
    assert body["progress_state"]["phase"] == "failed"
    assert body["detail"] == "No release to install."

    assert updater.calls == [], (
        f"a release that could not be read was acted on anyway: {updater.calls}")
    assert not _download_threads()


def test_the_published_version_being_the_installed_one_is_not_a_failure(
        panel, published, updater):
    """Refused, and refused as `idle` — nothing is wrong, there is nothing to do.

    The phase is the panel's entire vocabulary for this screen, so reporting
    `failed` here would put a red state in front of an owner whose engine is
    current. The same branch covers a published version that is OLDER than the
    installed one, which is a downgrade and must never be offered as an update.
    """
    for version in (VERSION, "0.0.1"):
        published.release = _a_release(version=version, installer=_attached())
        body = panel.post("/api/update").json()
        assert body["started"] is False, f"{version} was offered as an update"
        assert body["progress_state"]["phase"] == "idle"
        assert VERSION in body["detail"], body["detail"]
        assert "already the published version" in body["detail"]

    assert updater.calls == [], (
        f"a version that is not newer reached the verifier: {updater.calls}")
    assert not _download_threads()


def test_a_release_with_no_installer_attached_is_refused_before_a_thread_starts(
        panel, published, updater):
    """A newer version with nothing to download is a refusal, not a download.

    `read_manifest` returns `installer=None` for a release whose manifest
    attaches none, and the route reads `installer.bytes` two lines later — so
    without this branch a real published release with a missing `installer`
    block would be an AttributeError on the request thread instead of a sentence
    the panel can show.
    """
    published.release = _a_release(installer=None)
    body = panel.post("/api/update").json()

    assert body["started"] is False
    assert body["progress_state"]["phase"] == "failed"
    assert "installer" in body["detail"], body["detail"]
    assert "nothing to download" in body["detail"]
    assert updater.calls == []
    assert not _download_threads()


def test_progress_reaches_the_panel_while_the_download_is_still_running(
        panel, published, updater, tmp_path):
    """A bar that only moves when the download ends is a spinner with extra steps.

    This is the reason the POST returns at once and the panel polls GET: the
    worker writes `state.progress` and GET reads the SAME object. Observed
    mid-flight through an event rather than a sleep — a sleep would be a guess
    that passes here and flakes on a loaded runner, and the flake would look like
    the route's fault rather than the test's.
    """
    size = 8_000
    ticked, may_finish = threading.Event(), threading.Event()

    def verify(installer, version, progress):
        progress(2_000, size)
        ticked.set()
        assert may_finish.wait(timeout=10), "the test never released the worker"
        return _staged(tmp_path, version, size)

    published.release = _a_release(installer=_attached(size=size))
    updater.verify = verify
    assert panel.post("/api/update").json()["started"] is True
    try:
        assert ticked.wait(timeout=10), "the worker reported no progress at all"
        mid = _progress_state(panel.get("/api/update"))
        assert mid["phase"] == "downloading"
        assert mid["progress"] == {"received": 2_000, "total": size,
                                   "percent": 25}
        assert NEWER_VERSION in mid["detail"], mid["detail"]
    finally:
        may_finish.set()
        _let_the_download_finish()

    assert _progress_state(panel.get("/api/update"))["phase"] == "staged"


def test_a_tick_that_is_given_no_total_falls_back_to_the_published_size(
        panel, published, updater, tmp_path):
    """`tick` substitutes the manifest's byte count when it is told a total of 0.

    HONEST ABOUT WHAT THIS DOES AND DOES NOT PROVE. `fetch_and_verify` passes
    `installer.bytes` as the total on every tick (`scrapex/update.py:199`), so
    through the real verifier `total or installer.bytes` can never change the
    value — a manifest with no `bytes` field makes both of them 0. The fallback
    is a guard on the callback's own contract, not a production path, and this
    pins what it does rather than claiming a scenario that cannot happen.
    """
    size = 8_000

    def verify(installer, version, progress):
        progress(4_000, 0)
        return _staged(tmp_path, version, size)

    published.release = _a_release(installer=_attached(size=size))
    updater.verify = verify
    panel.post("/api/update")
    _let_the_download_finish()

    progress = _progress_state(panel.get("/api/update"))["progress"]
    assert progress["received"] == 4_000
    assert progress["total"] == size, (
        "a tick with no total zeroed the bar instead of falling back to the "
        "size the release published")
    assert progress["percent"] == 50


def test_a_refusal_from_the_verifier_lands_as_failed_carrying_its_own_sentence(
        panel, published, updater):
    """`UpdateRefused` already carries the sentence a person should read.

    The tests above prove those sentences name the digest, the size or the host.
    This one proves the route passes the sentence it was given through UNCHANGED
    instead of replacing it with the transport sentence below — the two are
    opposite advice, one "try again" and one "do not install this", and
    `update.py` goes to the trouble of a distinct exception type to keep them
    apart.
    """
    reason = ("The downloaded installer does not match the checksum this "
              f"release publishes, so it was deleted. Expected {DIGEST}.")

    def refuse(installer, version, progress):
        raise update_mod.UpdateRefused(reason)

    published.release = _a_release(installer=_attached())
    updater.verify = refuse
    assert panel.post("/api/update").json()["started"] is True
    _let_the_download_finish()

    state = _progress_state(panel.get("/api/update"))
    assert state["phase"] == "failed"
    assert state["detail"] == reason
    assert "did not finish" not in state["detail"], (
        "a refusal was reported with the transport sentence, which tells the "
        "owner to retry a download that must not be retried")
    assert state["staged_version"] == ""
    assert state["staged_path"] == ""
    assert state["staged_sha256"] == ""


def test_a_transport_failure_is_reported_as_one_and_names_its_type(
        panel, published, updater):
    """A dropped connection is worth retrying, so it must not read as a refusal.

    The type name is in the sentence on purpose — `update_api.py:204` says it
    keeps a support conversation short — and it is asserted here because the
    obvious tidy-up is to drop it, which leaves every failure looking the same.
    """
    def drop(installer, version, progress):
        raise ConnectionResetError("the connection was reset by the peer")

    published.release = _a_release(installer=_attached())
    updater.verify = drop
    assert panel.post("/api/update").json()["started"] is True
    _let_the_download_finish()

    state = _progress_state(panel.get("/api/update"))
    assert state["phase"] == "failed"
    assert "did not finish" in state["detail"], state["detail"]
    assert "ConnectionResetError" in state["detail"]
    assert "the connection was reset by the peer" in state["detail"]
    assert state["staged_version"] == ""


def test_a_verified_download_is_staged_and_the_route_installs_nothing(
        panel, published, updater, tmp_path):
    """THE PROMISE THE DOCSTRING MAKES. Success is `staged`, never `installed`.

    "Does NOT install it ... replacing a running executable is a separate act
    with its own approval, and calling this endpoint has never done it"
    (`update_api.py:148`). Asserted four ways over, because a negative claim is
    only as strong as the list of ways it could be false: the phase is the word
    `staged`; the ONLY function this route touched in `scrapex.update` is the
    verifier, with `plan_swap`, `discard`, `clear_staging` and `staging_dir`
    untouched and the `updater` fixture failing if a new one appears there
    unnamed; no process was started, because installing is `Popen` or
    `os.startfile` and neither is in `scrapex.update` for that fixture to see;
    and the worker did not die on a line after the state was written.
    """
    size = 4096
    published.release = _a_release(installer=_attached(size=size))
    staged = _staged(tmp_path, NEWER_VERSION, size)
    updater.verify = lambda installer, version, progress: staged

    assert panel.post("/api/update").json()["started"] is True
    _let_the_download_finish()
    did = list(updater.calls)

    state = _progress_state(panel.get("/api/update"))
    assert state["phase"] == "staged"
    assert state["phase"] != "installed"
    assert state["staged_version"] == NEWER_VERSION
    assert state["staged_path"] == str(staged.path)
    assert state["staged_sha256"] == DIGEST
    assert NEWER_VERSION in state["detail"]
    assert "not installed yet" in state["detail"], state["detail"]

    assert did == ["fetch_and_verify"], (
        f"the route did more than fetch and verify: {did}")
    # AND IT VERIFIED THE FILE THE RELEASE PUBLISHED. A call count says the
    # verifier ran; it does not say what it was pointed at, and an installer the
    # route assembled itself — with a blank sha256, or another release's URL —
    # would satisfy the count exactly as well while removing the one thing that
    # makes an unsigned download trustworthy.
    assert len(updater.verified) == 1
    handed_installer, handed_version = updater.verified[0]
    assert handed_installer is published.release.installer, (
        f"the verifier was handed {handed_installer}, not the installer the "
        f"release published ({published.release.installer})")
    assert handed_version == NEWER_VERSION
    assert not staged.path.exists(), (
        "the route wrote the staged installer somewhere; it is meant only to "
        "record where the verified file is")


def test_a_failed_download_leaves_the_updater_free_to_try_again(
        panel, published, updater, tmp_path):
    """`running.clear()` is in a `finally`, and this is the whole reason it is.

    A refusal that left the flag set would turn one bad download into an engine
    that answers "an update is already running" until it is restarted — and he
    restarts it from the panel, which is the surface that would be stuck.
    """
    size = 4096
    published.release = _a_release(installer=_attached(size=size))

    def refuse(installer, version, progress):
        raise update_mod.UpdateRefused("that download did not match its checksum")

    updater.verify = refuse
    assert panel.post("/api/update").json()["started"] is True
    _let_the_download_finish()
    assert _progress_state(panel.get("/api/update"))["phase"] == "failed"

    updater.verify = lambda installer, version, progress: _staged(
        tmp_path, version, size)
    second = panel.post("/api/update").json()
    assert second["started"] is True, (
        f"a failed download jammed the updater: {second['detail']}")
    _let_the_download_finish()
    assert _progress_state(panel.get("/api/update"))["phase"] == "staged"


def test_starting_a_second_download_forgets_the_version_that_was_staged(
        panel, published, updater, tmp_path):
    """A staged installer must not stay on offer while its successor downloads.

    The plan route builds its `Staged` out of `staged_path`, `staged_version`
    and `staged_sha256`. Leaving the previous run's values in place would let the
    panel plan a swap onto a file for a version that is no longer the one being
    fetched — and the plan would look perfectly well-formed.
    """
    size = 4096
    published.release = _a_release(installer=_attached(size=size))
    updater.verify = lambda installer, version, progress: _staged(
        tmp_path, version, size)
    panel.post("/api/update")
    _let_the_download_finish()
    assert _progress_state(panel.get("/api/update"))["staged_version"] == \
        NEWER_VERSION

    may_finish = threading.Event()

    def slow(installer, version, progress):
        assert may_finish.wait(timeout=10), "the test never released the worker"
        return _staged(tmp_path, version, size)

    published.release = _a_release(version=_one_version_newer(NEWER_VERSION),
                                   installer=_attached(size=size))
    updater.verify = slow
    assert panel.post("/api/update").json()["started"] is True
    try:
        state = _progress_state(panel.get("/api/update"))
        assert state["phase"] == "downloading"
        assert state["staged_version"] == ""
        assert state["staged_path"] == ""
        assert state["staged_sha256"] == ""
        # ...and the plan route refuses for as long as that is true.
        assert panel.get("/api/update/plan").json()["possible"] is False
    finally:
        may_finish.set()
        _let_the_download_finish()


def test_the_plan_route_offers_nothing_until_something_is_staged(panel, updater):
    """`GET /api/update/plan` on a fresh engine, which is what the panel asks first.

    `possible: False` AND an empty step list, because a step list is a thing a
    panel renders — and rendering the four steps of a swap with no verified
    installer behind it is an offer nobody can honour.
    """
    response = panel.get("/api/update/plan")
    assert response.status_code == 200, response.text
    plan = response.json()

    assert plan["possible"] is False
    assert plan["steps"] == []
    assert "nothing" in plan["detail"].lower(), plan["detail"]
    assert updater.calls == [], (
        f"the plan route reached into scrapex.update with nothing staged: "
        f"{updater.calls}")
    assert updater.planned == []


def test_the_plan_is_built_from_the_download_that_was_actually_verified(
        panel, published, updater, tmp_path):
    """The plan must describe THIS file, not a version number somebody typed.

    Every field `plan_swap` is handed comes out of the state the download wrote,
    including the byte count — which is read off the progress counter rather
    than off the verifier's return value (`update_api.py:242`). Asserted on the
    real `update.Staged` rather than on a dict, so a renamed field fails here
    instead of arriving as a `None` in a plan somebody approves.
    """
    size = 4096
    published.release = _a_release(installer=_attached(size=size))
    staged = _staged(tmp_path, NEWER_VERSION, size)

    def verify(installer, version, progress):
        progress(size, size)          # the last tick a finished download reports
        return staged

    updater.verify = verify
    panel.post("/api/update")
    _let_the_download_finish()

    updater.plan = {"possible": True, "detail": "", "steps": ["one", "two"],
                    "verified_installer": str(staged.path), "sha256": DIGEST,
                    "version": NEWER_VERSION, "replaces": "/somewhere/engine.exe"}
    answered = panel.get("/api/update/plan").json()

    assert answered == updater.plan, "the route edited the plan on the way out"
    assert len(updater.planned) == 1, (
        f"plan_swap was called {len(updater.planned)} times")
    asked = updater.planned[0]
    assert isinstance(asked, update_mod.Staged)
    assert str(asked.path) == str(staged.path)
    assert asked.version == NEWER_VERSION
    assert asked.sha256 == DIGEST
    assert asked.bytes == size, (
        "the plan was handed a byte count that is not the one the download "
        "reported")
