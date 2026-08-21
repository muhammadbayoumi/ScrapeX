"""Fetch, VERIFY, and stage a new engine. Nothing here executes what it fetched.

`R-36` is the ruling this implements, and its third part is the one with
consequences, so it is written at its narrowest here too:

    A sha256 published in the release manifest, fetched over HTTPS from
    raw.githubusercontent.com, and CHECKED BEFORE THE SWAP, is enough to trust
    a download.

    It is NOT code signing and does not replace it. SmartScreen still warns on
    first install until a certificate exists, which only the owner can supply.
    What the chain buys is that an updater may exist BEFORE signing does.

`packaging/build_engine.py` refused to guess about this and said why: *"shipping
an updater that fetches and executes unsigned code would be worse than none."*
That objection is answered by the digest and by nothing else, which is why every
refusal in this module is about the digest and why none of them can be turned
off by a caller.

THE FOUR RULES, and they are the whole design:

  1. THE DIGEST IS REQUIRED. A release whose installer publishes no sha256 is
     reported and refused. There is no "download anyway" parameter, because the
     moment one exists it becomes the path somebody takes at 2am.
  2. THE BYTES ARE HASHED AS THEY ARRIVE, not read back afterwards. Reading back
     verifies the disk, not the download, and a file that changed between the
     two reads would pass.
  3. A FILE THAT FAILS IS DELETED, immediately, before returning. A rejected
     71 MB executable left lying in a staging directory is a thing somebody
     double-clicks a week later.
  4. THE STAGED PATH IS ONLY RETURNED ON SUCCESS. There is no shape of the
     return value that hands a caller unverified bytes, so no caller can
     misuse it by forgetting to check a flag.

WHAT THIS MODULE DELIBERATELY DOES NOT DO: replace the running executable.
Windows will not let a running .exe be overwritten, so the swap is a separate
act performed by a detached helper after this process exits — `plan_swap` names
that plan and `scrapex/relaunch.py` already owns the machinery, but performing
it cannot be honestly tested without a frozen build, and this module will not
pretend otherwise. See `swap_is_possible`.
"""
from __future__ import annotations

import hashlib
import os
import shutil
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import enginelaunch
from .release import DOWNLOAD_TIMEOUT_S, Installer

#: Where a download lands. Beside the warehouse rather than in %TEMP%, because a
#: 70 MB file that a virus scanner is still inspecting must not be swept away by
#: somebody else's cleaner half way through.
STAGING_DIRNAME = "updates"

#: Read in chunks so a 70 MB download does not become 70 MB of resident memory,
#: and so progress can be reported while it happens rather than at the end.
CHUNK_BYTES = 1 << 16

#: A ceiling on what we will write to disk even if the server keeps sending.
#: Without it a misconfigured endpoint (or a redirect to something enormous) can
#: fill the owner's disk while we wait for a digest that will never match.
#: 4x the largest engine we have ever built, which was 67.6 MB.
MAX_INSTALLER_BYTES = 300 * 1024 * 1024


class UpdateRefused(Exception):
    """The download did not earn the right to be installed.

    A distinct type, because the caller's response differs from every other
    failure: a network error is worth retrying and this is not. It carries the
    sentence a person should read, so the API layer never has to invent one.
    """


@dataclass(frozen=True)
class Staged:
    """A verified installer, on disk, ready for a swap this module will not do."""

    path: Path
    version: str
    sha256: str
    bytes: int


def staging_dir(root: Path | None = None) -> Path:
    """`~/.scrapex/updates`, created on demand.

    Honours `SCRAPEX_DATA_ROOT` through the same env var the registry reads, so
    a test and a second installation land somewhere of their own rather than in
    the owner's real directory.
    """
    if root is None:
        root = Path(os.environ.get("SCRAPEX_DATA_ROOT", str(Path.home() / ".scrapex")))
    target = Path(root) / STAGING_DIRNAME
    target.mkdir(parents=True, exist_ok=True)
    return target


def swap_is_possible() -> tuple[bool, str]:
    """Can this installation replace its own executable at all? Say so plainly.

    A source install has no executable to replace: it is a checkout, and it
    updates with `git pull`. Offering it an Update button would be offering
    something that cannot work, and reporting THAT is more useful than a button
    that fails.
    """
    if not enginelaunch.frozen():
        return False, ("This is a source checkout, not an installed engine. "
                       "Update it with git rather than from here.")
    return True, ""


def _digest_matches(expected: str, actual: str) -> bool:
    """Compared case-insensitively and in constant time.

    `hmac.compare_digest` is not about secrecy here — nothing is secret, the
    digest is published. It is about not writing a comparison that some future
    reader optimises into an early return and a timing signal, in a module whose
    whole job is a security check. Cheap, and it removes the question.
    """
    import hmac

    return hmac.compare_digest(expected.strip().lower(), actual.strip().lower())


def fetch_and_verify(
    installer: Installer,
    version: str,
    *,
    into: Path | None = None,
    progress: Callable[[int, int], None] | None = None,
    client: object | None = None,
) -> Staged:
    """Stream the installer down, hash it as it arrives, and refuse it if it lies.

    Raises `UpdateRefused` for anything that means "do not install this", and
    lets a genuine transport error propagate as itself — the caller's answer to
    a dropped connection is "try again", and to a digest mismatch is not.

    `client` is injectable so the tests drive a real local HTTP server rather
    than a mocked `httpx`: the thing under test is a streamed download with a
    running hash, and a mock that returns bytes in one lump would not exercise
    it at all.
    """
    if not installer.verifiable:
        raise UpdateRefused(
            "This release publishes no SHA-256 for its installer, so a download "
            "cannot be proved whole. Install it by hand from the release page, "
            "or cut a release that attaches one.")

    target_dir = staging_dir() if into is None else Path(into)
    target_dir.mkdir(parents=True, exist_ok=True)
    # Named for the version, so two attempts at the same version reuse one name
    # and a staging directory cannot silently accumulate a copy per press.
    final = target_dir / f"scrapex-engine-{version}.exe"
    partial = final.with_suffix(".part")

    import httpx

    digest = hashlib.sha256()
    written = 0
    owned_client = client is None
    http = httpx.Client(timeout=DOWNLOAD_TIMEOUT_S, follow_redirects=True) \
        if owned_client else client
    try:
        with http.stream("GET", installer.url) as response:  # type: ignore[union-attr]
            if response.status_code != 200:
                raise UpdateRefused(
                    f"The installer could not be downloaded: the release host "
                    f"answered {response.status_code}.")
            with partial.open("wb") as handle:
                for chunk in response.iter_bytes(CHUNK_BYTES):
                    written += len(chunk)
                    if written > MAX_INSTALLER_BYTES:
                        raise UpdateRefused(
                            "The download is larger than any engine we have ever "
                            "built and was stopped. Nothing was installed.")
                    digest.update(chunk)
                    handle.write(chunk)
                    if progress is not None:
                        progress(written, installer.bytes)
    except UpdateRefused:
        partial.unlink(missing_ok=True)
        raise
    except Exception:
        # A dropped connection leaves a partial file that is worthless and
        # confusing. Rule 3 applies to every exit, not only to a bad digest.
        partial.unlink(missing_ok=True)
        raise
    finally:
        if owned_client:
            http.close()                                 # type: ignore[union-attr]

    actual = digest.hexdigest()
    if not _digest_matches(installer.sha256, actual):
        partial.unlink(missing_ok=True)
        raise UpdateRefused(
            f"The downloaded installer does not match the checksum this release "
            f"publishes, so it was deleted and nothing was installed. "
            f"Expected {installer.sha256}, got {actual}.")

    # The size is checked AFTER the digest and only as a sanity note: a digest
    # match already proves the bytes, so a size mismatch here would mean the
    # manifest's own two fields disagree. Worth refusing, because it means the
    # release was built wrong and something else in it may be wrong too.
    if installer.bytes and written != installer.bytes:
        partial.unlink(missing_ok=True)
        raise UpdateRefused(
            f"The release manifest disagrees with itself: it declares "
            f"{installer.bytes} bytes and the file that matched its checksum is "
            f"{written}. Nothing was installed.")

    # Only now does a verified file get its real name. Anything that reads the
    # staging directory for a usable installer sees `.exe` files only, and every
    # one of them passed.
    final.unlink(missing_ok=True)
    partial.replace(final)
    return Staged(path=final, version=version, sha256=actual, bytes=written)


def plan_swap(staged: Staged) -> dict:
    """WHAT WOULD HAPPEN, described rather than done.

    Returned as data so it can be shown, logged and tested without a frozen
    build in the room. The steps are in this order for reasons, not for
    presentation:

      1. The running executable cannot be overwritten while it runs — Windows
         holds the file. So the new one is put BESIDE it under a temporary name.
      2. A DETACHED helper is started, which waits for this process to exit.
         `scrapex/relaunch.py:spawn_helper` already does exactly this waiting,
         for exactly this reason, and it is why `OP-36` had to be fixed first:
         before that, the helper a frozen engine spawned was a silent native
         messaging host and would have waited forever.
      3. Only after the engine has exited does the helper rename. A rename is
         atomic on one volume, so there is no moment where neither file is
         installable.
      4. The helper starts the new engine on the same port and stands down.

    The current executable's path is included because a plan that cannot say
    what it would overwrite is not a plan anybody should approve.
    """
    possible, why = swap_is_possible()
    return {
        "possible": possible,
        "detail": why,
        "verified_installer": str(staged.path),
        "sha256": staged.sha256,
        "version": staged.version,
        "replaces": enginelaunch.runner(windowless=False).as_posix()
                    if possible else "",
        "steps": [
            "put the verified installer beside the running engine",
            "start a detached helper that waits for this process to exit",
            "rename the new engine over the old one (atomic, same volume)",
            "start the new engine on the same port",
        ],
    }


def discard(staged: Staged) -> None:
    """Throw a staged installer away.

    Exists because the alternative is that they accumulate: one verified 70 MB
    file per version the owner ever considered, in a directory nobody opens.
    """
    Path(staged.path).unlink(missing_ok=True)


def clear_staging(root: Path | None = None) -> int:
    """Empty the staging directory. Returns how many files went.

    Called when an update completes, and safe to call when it did not: the
    directory holds nothing but downloads, and a verified installer that has
    already been swapped in is a duplicate of the running engine.
    """
    target = staging_dir(root)
    removed = 0
    for path in target.iterdir():
        if path.is_file():
            path.unlink(missing_ok=True)
            removed += 1
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            removed += 1
    return removed
