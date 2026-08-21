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
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from scrapex import update as update_mod
from scrapex.release import Installer

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
