"""What this engine IS, as distinct from what its version file says.

THE DEFECT, MEASURED 2026-08-23. The owner's panel said "no successful crawl yet"
over 17,304 crawled rows. #255 had fixed exactly that two days earlier and the fix
was on `main`. It had not reached him, and nothing anywhere could say why:

    pythonw -m scrapex.cli ui --port 8000    started  07:35:44
    the checkout moved off 451468d           at       07:39:03
    delta                                            +199 seconds

**Python imports a module once.** A long-lived engine started from an editable
install holds whatever tree existed at import time for as long as it runs, and the
tree this one held still carried the literal #255 removed -- read it with
`git show 451468d:scrapex/webui/app.py`, at line 650 of THAT commit, where
`"last_success": None` still stands. The disk had the fix; the process did not.

AND NOTHING COULD TELL, WHICH IS THE PART THIS MODULE EXISTS FOR. `/api/health` and
`/api/version` both answered `"version": "0.3.0"` — truthfully. `451468d` IS
`engine-v0.3.0`. But a version string cannot separate three different things:

    the published engine-v0.3.0 build
    a source checkout sitting at that tag
    a process that imported that tree and kept running while the disk moved on

Measured: **ten distinct commits report `VERSION = "0.3.0"`** — every tree from
`e963269` (#247) to `31c369e`'s parent (#257), one of which is the release tag. That
is by design, not by accident: `R-77` moves the engine's number on a CONTRACT change,
so many trees share one number deliberately. **A string ten trees share cannot
identify one of them**, and it is the only thing the engine had ever been asked.

WHAT THIS MODULE ADDS, and it is the narrowest thing that catches the incident: the
engine reports the identity of the code it LOADED, and compares it against the code
on disk NOW. Two independent answers, because they fail independently:

    stale   a source file this process has loaded has CHANGED ON DISK since the
            process sealed its snapshot. This is the exact defect above, and it
            needs no git at all — it works on any checkout, tarball or editable
            install.
    moved   the git checkout's HEAD is not the HEAD this process started on. Not
            required for correctness, and it is what gives the answer WORDS a
            person can act on: "started at 451468d, the checkout is now 31c369e".

WHY BOTH, when `stale` alone proves the fault: `moved` fires on a checkout that
advanced without touching anything this process happens to have imported, which is
a restart the owner still wants to know about; `stale` fires on an editable install
with no `.git` reachable at all. Neither contains the other.

A FROZEN BUILD ANSWERS `None`, NEVER `False`. A PyInstaller one-file `.exe` has no
`.git` and no source tree on disk to compare itself against — its modules live in a
per-run temp directory that says nothing about whether newer code exists. So the
honest answer is *unknown*, and it is reported as unknown. `/api/health`'s own
worker block already set this precedent in this repository
(`scrapex/webui/app.py:1527`, `{"alive": None, ...}` — *"Unknown is now said as
unknown, and the reason for not knowing travels with it"*). A guessed `False` here
would be the defect, not the fix: it would tell the owner his engine is current on
the one build where we cannot know.

NOTHING HERE IMPORTS FROM `scrapex` EXCEPT `enginelaunch`, which imports nothing at
all — the same rule that module states about itself. `report()` is called from
`/api/health`, which the panel polls on a timer, so it must never raise and never
block: every filesystem read below is guarded, and the only unbounded work happens
when a file has ALREADY been seen to change.
"""
from __future__ import annotations

import hashlib
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from . import enginelaunch

#: The package this module describes. Derived, so a rename cannot leave it behind.
PACKAGE = __name__.split(".")[0]

#: How many changed modules the report names. A restart is the remedy whether one
#: module moved or forty, so the list is evidence rather than a work queue — and
#: `/api/health` is polled every few seconds, which is not the place for an
#: unbounded array.
NAMED_LIMIT = 12


def _package_root() -> Path:
    return Path(__file__).resolve().parent


def _digest(path: Path) -> str | None:
    """SHA-256 of a source file, newline-normalised.

    NORMALISED BECAUSE THIS REPOSITORY HAS SHIPPED THE OTHER THING AS AN OUTAGE.
    `.gitattributes` sets `* text=auto` and `core.autocrlf` is true, so the repo
    stores LF and Windows checks out CRLF (`docs/LESSONS.md` §1). Here both reads
    happen on one machine so the raw bytes would agree in practice — but a digest
    that is only accidentally stable is the kind this project has already paid for
    once, and one `.replace()` removes the whole question.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return None
    return hashlib.sha256(
        data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")).hexdigest()


def _loaded_sources() -> dict[str, Path]:
    """Every module of this package that is loaded AND has a real file on disk.

    `sys.modules` is the authority on what this process actually imported, which is
    the whole question — a file the engine has never loaded cannot make it stale,
    and reading the tree instead would report edits to tests and documents as a
    reason to restart. That is the cry-wolf failure
    `tests/test_the_published_documents_are_checked_not_announced.py` already warns
    about, and it would arrive within a day on a repository under this much traffic.

    A module with no `__file__`, or one outside the package directory, is skipped:
    namespace packages, C extensions and a frozen bundle's archive entries all have
    nothing on disk to compare against.
    """
    root = _package_root()
    found: dict[str, Path] = {}
    for name, module in list(sys.modules.items()):
        if name != PACKAGE and not name.startswith(PACKAGE + "."):
            continue
        origin = getattr(module, "__file__", None)
        if not origin:
            continue
        try:
            path = Path(origin).resolve()
            path.relative_to(root)
        except (OSError, ValueError):
            continue
        found[name] = path
    return found


def _git_dir(start: Path) -> Path | None:
    """The `.git` directory governing `start`, or None.

    Handles the worktree form, because this repository is worked in worktrees and
    an engine started from one must still be able to answer. In a worktree `.git`
    is a FILE reading `gitdir: <path>` and the branch pointer lives under that
    path, not under the shared repository.
    """
    for candidate in (start, *start.parents):
        marker = candidate / ".git"
        try:
            if marker.is_dir():
                return marker
            if marker.is_file():
                text = marker.read_text(encoding="utf-8", errors="replace")
                for line in text.splitlines():
                    if line.startswith("gitdir:"):
                        pointed = Path(line.split(":", 1)[1].strip())
                        if not pointed.is_absolute():
                            pointed = (candidate / pointed).resolve()
                        return pointed if pointed.is_dir() else None
        except OSError:
            return None
    return None


def _read_head(git_dir: Path) -> str | None:
    """The commit HEAD points at, read from files rather than from `git`.

    NO SUBPROCESS, DELIBERATELY. This is called from `/api/health`, which the panel
    polls behind a 2,500 ms deadline — and that deadline has already been blown once
    in this product's history by an endpoint doing more work than a poll can afford
    (`scrapex/webui/app.py:1484`: it *"answered in 3.8 s, the deadline expired, and
    the panel reported the engine as 'Not detected'"*). Three small file reads cannot
    do that. Neither can they fail on a machine with no git on PATH, which is the
    owner's machine for `python` already (`docs/LESSONS.md` §1).
    """
    try:
        head = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not head.startswith("ref:"):
        return head or None
    ref = head.split(":", 1)[1].strip()
    # A worktree's own HEAD lives in its gitdir; the REF it names lives in the
    # shared repository, which `commondir` points at. Getting this wrong reports
    # "no commit" for every engine started from a worktree.
    roots = [git_dir]
    try:
        common = (git_dir / "commondir").read_text(encoding="utf-8").strip()
        resolved = Path(common)
        roots.append(resolved if resolved.is_absolute()
                     else (git_dir / resolved).resolve())
    except OSError:
        pass
    for root in roots:
        try:
            return (root / ref).read_text(encoding="utf-8").strip() or None
        except OSError:
            continue
    # Packed. `packed-refs` is the fallback and not the first read: a freshly
    # checked-out branch has a loose ref and no packed entry.
    for root in roots:
        try:
            for line in (root / "packed-refs").read_text(encoding="utf-8").splitlines():
                if line.startswith(("#", "^")):
                    continue
                parts = line.split()
                if len(parts) == 2 and parts[1] == ref:
                    return parts[0]
        except OSError:
            continue
    return None


class _Snapshot:
    """What the process had loaded at the moment it sealed, and when that was.

    THE REFERENCE POINT IS THE WHOLE DESIGN, so it is an object with a time on it
    rather than a module global that is true at some unstated moment. Every claim
    `report()` makes is relative to `sealed_at`, and the report says what that
    moment was — because a measurement that does not carry its base is the exact
    failure family this module was written for (`docs/LESSONS.md` §14).
    """

    def __init__(self) -> None:
        self.sealed_at: float | None = None
        self.frozen: bool = False
        self.head: str | None = None
        self.git_dir: Path | None = None
        #: name -> (path, mtime, size, digest). Both the cheap stamp and the exact
        #: one, because `_changed()` uses the first to decide whether to spend the
        #: second.
        self.loaded: dict[str, tuple[Path, float, int, str]] = {}

    def seal(self) -> None:
        self.sealed_at = time.time()
        self.frozen = enginelaunch.frozen()
        self.loaded = {}
        self.head = None
        self.git_dir = None
        if self.frozen:
            # A frozen build has no source tree and no repository. Sealing it
            # records the MODE and nothing else, so `report()` has a truthful
            # basis for answering `None` rather than inventing a comparison.
            return
        self.git_dir = _git_dir(_package_root())
        if self.git_dir is not None:
            self.head = _read_head(self.git_dir)
        for name, path in _loaded_sources().items():
            try:
                stat = path.stat()
            except OSError:
                continue
            digest = _digest(path)
            if digest is not None:
                self.loaded[name] = (path, stat.st_mtime, stat.st_size, digest)


_SNAPSHOT = _Snapshot()


def seal() -> None:
    """Fix the reference point: this is the code the process is running.

    CALLED ONCE, WHEN THE SERVER IS BUILT AND ABOUT TO SERVE, which is the only
    moment that makes the claim exact. Sealing at import time would snapshot the
    handful of modules loaded that early and miss `webui.app` — the module the
    incident was actually about. Sealing lazily on the first `report()` would take
    its baseline AFTER the edit it exists to notice, which is worse than not
    checking: it would report "current" about a process that is not.
    """
    _SNAPSHOT.seal()


def _changed() -> list[str]:
    """Loaded modules whose file on disk no longer matches what was sealed.

    Two stages, because the cheap one is enough almost always. `stat()` per module
    is a handful of microseconds; a digest is a read. So the digest is computed only
    for a file whose size or mtime has already moved — and it is what decides, so a
    file that git rewrote to identical content does NOT report as changed. mtime
    alone would cry wolf on every `git checkout` that touched a file without
    changing it, and a warning that fires when nothing is wrong is one the owner
    learns to scroll past.

    THEN A THIRD PASS over modules imported after the seal, which the snapshot by
    definition does not hold. See the comment at that loop: without it, a module
    first imported inside a request handler is a divergence this check cannot see.
    """
    changed: list[str] = []
    for name, (path, mtime, size, digest) in sorted(_SNAPSHOT.loaded.items()):
        try:
            stat = path.stat()
        except OSError:
            # Deleted or renamed under a running process. That IS a divergence
            # between memory and disk, and it is reported as one.
            changed.append(name)
            continue
        if stat.st_mtime == mtime and stat.st_size == size:
            continue                   # untouched: no read, no hash
        if _digest(path) != digest:
            changed.append(name)

    # AND THE MODULES THAT ARRIVED AFTER THE SEAL, which the loop above cannot see
    # because they are not in the snapshot at all. This repository has several
    # `from ..x import y` inside route handlers, so a module can first be imported
    # while serving a request -- minutes or hours after the reference point.
    #
    # A FILE WHOSE mtime IS LATER THAN THE SEAL WAS WRITTEN AFTER THIS PROCESS
    # STARTED SERVING, so the process is now running a MIX of pre- and post-edit
    # code. That is worse than being uniformly behind, not better, and reporting it
    # is the point. There is no false positive available here: mtime records when
    # the file was last written to disk, and for untouched code that is always
    # before the process started.
    #
    # Found by asking what `seal()` does NOT cover rather than by a failure -- the
    # blind spot a guard does not know it has is the defect this whole module is
    # about.
    for name, path in sorted(_loaded_sources().items()):
        if name in _SNAPSHOT.loaded:
            continue
        try:
            if path.stat().st_mtime > _SNAPSHOT.sealed_at:
                changed.append(name)
        except OSError:
            continue
    return changed


def report() -> dict:
    """What this engine is running, and whether the disk has moved past it.

    Never raises. This is reached from `/api/health`, which the panel polls on a
    timer and which already carries a comment about why it must survive the thing it
    reports on (`scrapex/webui/app.py:1427`).
    """
    try:
        return _report()
    # A BARE `except Exception` ON PURPOSE, and deliberately with no suppression
    # comment beside it. The three in `packaging/engine_entry.py` suppress BLE001 --
    # which is where this was copied from -- but the lint gate runs
    # `ruff check scrapex/` and never looks at `packaging/`, so that rule is not
    # enabled here and the directive was dead. RUF100 caught it.
    #
    # AND THE FIRST DRAFT OF THIS COMMENT SPELLED THE DIRECTIVE OUT to explain it,
    # which made ruff parse the explanation as a directive and warn about it. A
    # comment that quotes an instruction is holding one -- the same trap
    # `docs/LESSONS.md` §7 records twice about prose. Name the rule, never the syntax.
    except Exception as exc:
        # The one branch where `stale` may not be a verdict. A check that crashed
        # knows nothing, and saying so is the only honest answer available — the
        # alternative is a `False` that means "we failed to look".
        return {
            "mode": "unknown", "sealed_at": None, "commit": None,
            "commit_now": None, "moved": None, "stale": None, "changed": [],
            "detail": ("this engine could not read its own provenance: "
                       f"{type(exc).__name__}: {exc}"),
        }


def _report() -> dict:
    sealed_at = _SNAPSHOT.sealed_at
    mode = "frozen" if _SNAPSHOT.frozen else "source"
    stamp = (datetime.fromtimestamp(sealed_at, UTC).isoformat()
             if sealed_at is not None else None)
    out: dict = {
        "mode": mode,
        "sealed_at": stamp,
        "commit": _SNAPSHOT.head,
        "commit_now": None,
        "moved": None,
        "stale": None,
        "changed": [],
        "detail": "",
    }
    if sealed_at is None:
        out["detail"] = ("this engine never recorded which code it loaded, so "
                         "whether the disk has moved past it cannot be answered.")
        return out
    if _SNAPSHOT.frozen:
        # THE HONEST UNKNOWN, and the reason it is a branch of its own rather than
        # a fall-through: an installed build genuinely cannot answer this, and
        # `False` would be a claim it has no way to support.
        out["detail"] = ("this is an installed build; it carries no source tree to "
                         "compare against, so whether newer code exists on disk "
                         "cannot be answered from inside it.")
        return out

    changed = _changed()
    out["stale"] = bool(changed)
    out["changed"] = changed[:NAMED_LIMIT]
    if _SNAPSHOT.git_dir is not None:
        out["commit_now"] = _read_head(_SNAPSHOT.git_dir)
        if _SNAPSHOT.head and out["commit_now"]:
            out["moved"] = out["commit_now"] != _SNAPSHOT.head

    # THE SENTENCE IS PART OF THE PRODUCT, not a log line. `REQ-35` asks for a word
    # for "running from source", which the panel does not have; the words a person
    # reads are decided here, once, so the panel and the engine's own page cannot
    # say it two different ways.
    #
    # AND ONE THING `REQ-35` GETS WRONG ABOUT ITS OWN CAUSE, measured 2026-08-23
    # against the live engine so the next reader does not inherit it. That entry
    # blames the panel guessing from an EMPTY version string. The engine does not
    # report an empty version: `GET /api/health` answered `"version": "0.3.1"` in
    # 486 ms. What produces "Not detected" is `setEngineChecking()` rendering the
    # spec rows BEFORE any answer arrives, so the pair shows during every check
    # window on a perfectly healthy engine. That is a separate defect from this
    # one and is NOT fixed here; the measurement is recorded under `REQ-35` itself,
    # beside the claim it corrects. What IS this one: those 11 keys carry no
    # statement of how the engine was started, and none of them can.
    if changed:
        which = f"{len(changed)} loaded module(s)"
        detail = (f"the code this engine is running is not the code on disk — "
                  f"{which} changed since it started. Restart the engine to pick "
                  f"the new code up.")
    elif out["moved"]:
        detail = ("the checkout has moved to another commit since this engine "
                  "started, though nothing it has loaded changed. Restart the "
                  "engine if you expect newer behaviour.")
    else:
        detail = "running from source, and level with the code on disk."
    out["detail"] = detail
    return out


def summary() -> dict:
    """The compact form `/api/health` carries on every poll.

    `changed` is the part a timed poll must not carry: it is a list, it grows with
    the size of the divergence, and the panel's answer is the same for one module as
    for forty. The full block including it is on `/api/version`, which is fetched
    once — the same split `/api/health` already makes for the capability ledger
    (`scrapex/webui/app.py:1536`).
    """
    full = report()
    return {key: full[key] for key in
            ("mode", "sealed_at", "commit", "commit_now", "moved", "stale", "detail")}
