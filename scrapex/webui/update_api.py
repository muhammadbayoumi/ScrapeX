"""The engine's own update surface. The panel asks; this acts.

`R-36`: the first install comes through the browser because nothing is installed
yet, and every update after it belongs here — Chrome grants an extension no way
to verify a checksum, read a file off disk, or launch a process, and this is a
local process with all three.

WHY GET AND POST ARE DIFFERENT ANSWERS TO DIFFERENT QUESTIONS. `GET` is safe to
poll and says only what is true right now; it never downloads. `POST` is the act,
and it is the only thing that touches the network for 70 MB. Merging them into
one "check and maybe install" endpoint would mean the panel's periodic poll could
start a download nobody pressed a button for.

THE DOWNLOAD RUNS IN THE BACKGROUND AND THE POST RETURNS AT ONCE, because a
70 MB fetch over a home connection outlasts any HTTP timeout the panel is willing
to hold. State lives in one place (`_State`) and `GET` reports it, so the panel
polls the same endpoint it already polls for everything else instead of holding a
socket open for four minutes.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field

from fastapi import APIRouter

from .. import release as release_mod
from .. import update as update_mod
from ..version import VERSION


@dataclass
class _Progress:
    """How far a download has got, in the two numbers a bar needs."""

    received: int = 0
    total: int = 0

    @property
    def percent(self) -> int:
        if self.total <= 0:
            return 0
        return min(100, int(self.received * 100 / self.total))


@dataclass
class _State:
    """Everything the panel can be told about an update, in one object.

    ONE object under ONE lock, because the alternative is what the panel has had
    to do until now: infer a state from several independent fields and get it
    wrong when two of them are momentarily out of step. `phase` is a closed
    vocabulary and every other field is only meaningful for some of its values,
    which is why `as_dict` reports the phase first.
    """

    #: idle | checking | downloading | staged | failed
    phase: str = "idle"
    detail: str = ""
    progress: _Progress = field(default_factory=_Progress)
    staged_version: str = ""
    staged_path: str = ""
    staged_sha256: str = ""

    def as_dict(self) -> dict:
        out = asdict(self)
        out["progress"] = {"received": self.progress.received,
                           "total": self.progress.total,
                           "percent": self.progress.percent}
        return out


def create_update_router() -> APIRouter:
    router = APIRouter(prefix="/api/update", tags=["update"])

    state = _State()
    lock = threading.Lock()
    # One at a time, for the obvious reason and one less obvious: two downloads
    # of the same version write the same staging filename, and the loser would
    # replace a verified file with a partial one under a name that means
    # "verified".
    running = threading.Event()

    def _set(**fields) -> None:
        with lock:
            for key, value in fields.items():
                setattr(state, key, value)

    @router.get("")
    def current() -> dict:
        """What is installed, what is published, and what this engine could do.

        Safe to poll: it reads the release manifest (a 4-second-timeout request
        for a few hundred bytes) and never touches the installer. `offline` is
        reported as a state rather than an error, because the engine the owner
        has keeps working and there is nothing for him to fix.
        """
        latest = release_mod.latest()
        possible, why = update_mod.swap_is_possible()
        with lock:
            snapshot = state.as_dict()

        available = (latest.ok
                     and release_mod.is_newer(latest.version, VERSION))
        return {
            "installed": VERSION,
            "latest": {
                "state": latest.state,
                "detail": latest.detail,
                "version": latest.version,
                "tag": latest.tag,
                "published_at": latest.published_at,
                "url": latest.url,
                "minimum_extension": latest.minimum_extension,
                "protocol": latest.protocol,
                "installer": (None if latest.installer is None else {
                    "name": latest.installer.name,
                    "bytes": latest.installer.bytes,
                    "sha256": latest.installer.sha256,
                    # The URL is reported so the panel can still hand the file to
                    # chrome.downloads for a FIRST install. It is not needed for
                    # an update -- the engine fetches that itself.
                    "url": latest.installer.url,
                    "verifiable": latest.installer.verifiable,
                }),
            },
            "update_available": available,
            # SEPARATE FROM `update_available` ON PURPOSE. A newer release can
            # exist and be uninstallable-from-here for two different reasons: a
            # source checkout has no executable to replace, and a release
            # without a digest will not be trusted. The panel must be able to
            # say WHICH.
            "can_self_update": bool(
                available and possible
                and latest.installer is not None
                and latest.installer.verifiable),
            "self_update_blocked_because": (
                why if available and not possible
                else "" if not available
                else "" if latest.installer and latest.installer.verifiable
                else "This release attaches no SHA-256, so its download cannot "
                     "be proved whole."),
            "progress_state": snapshot,
        }

    @router.post("")
    def start() -> dict:
        """Fetch and verify the published installer. Does NOT install it.

        Returns immediately; the work runs on a thread and `GET` reports it. The
        phase that follows success is `staged`, never `installed` — replacing a
        running executable is a separate act with its own approval, and calling
        this endpoint has never done it.
        """
        if running.is_set():
            with lock:
                return {"started": False,
                        "detail": "An update is already running.",
                        "progress_state": state.as_dict()}

        latest = release_mod.latest()
        if not latest.ok:
            _set(phase="failed", detail=latest.detail or "No release to install.")
            with lock:
                return {"started": False, "detail": state.detail,
                        "progress_state": state.as_dict()}
        if not release_mod.is_newer(latest.version, VERSION):
            _set(phase="idle",
                 detail=f"{VERSION} is already the published version.")
            with lock:
                return {"started": False, "detail": state.detail,
                        "progress_state": state.as_dict()}
        if latest.installer is None:
            _set(phase="failed",
                 detail="That release attaches no installer, so there is nothing "
                        "to download.")
            with lock:
                return {"started": False, "detail": state.detail,
                        "progress_state": state.as_dict()}

        installer = latest.installer
        version = latest.version
        running.set()
        _set(phase="downloading", detail=f"Downloading {version}…",
             progress=_Progress(received=0, total=installer.bytes),
             staged_version="", staged_path="", staged_sha256="")

        def work() -> None:
            try:
                def tick(received: int, total: int) -> None:
                    # No lock: two ints, written far more often than they are
                    # read, and a reader that catches them mid-write sees a
                    # percentage one chunk stale. Taking the lock 1,100 times a
                    # download to avoid that would be the wrong trade.
                    state.progress.received = received
                    state.progress.total = total or installer.bytes

                staged = update_mod.fetch_and_verify(
                    installer, version, progress=tick)
            except update_mod.UpdateRefused as refused:
                _set(phase="failed", detail=str(refused))
            except Exception as exc:
                # A transport failure is worth retrying and a refusal is not, so
                # they are reported as different sentences even though both end
                # here. Naming the type keeps a support conversation short.
                _set(phase="failed",
                     detail=f"The download did not finish "
                            f"({type(exc).__name__}: {exc}).")
            else:
                _set(phase="staged",
                     detail=f"{staged.version} is downloaded and its checksum "
                            f"matches. It is not installed yet.",
                     staged_version=staged.version,
                     staged_path=str(staged.path),
                     staged_sha256=staged.sha256)
            finally:
                running.clear()

        threading.Thread(target=work, name="scrapex-update", daemon=True).start()
        with lock:
            return {"started": True, "detail": state.detail,
                    "progress_state": state.as_dict()}

    @router.get("/plan")
    def plan() -> dict:
        """What installing the staged engine WOULD do, without doing it.

        Exists because `R-36` bought an updater before code signing, and the
        thing that makes that acceptable is that every step is inspectable
        before it happens. A plan nobody can read is the same trust problem in a
        new place.
        """
        with lock:
            if state.phase != "staged":
                return {"possible": False,
                        "detail": "Nothing is staged, so there is nothing to plan.",
                        "steps": []}
            staged = update_mod.Staged(
                path=state.staged_path,          # type: ignore[arg-type]
                version=state.staged_version,
                sha256=state.staged_sha256,
                bytes=state.progress.received)
        return update_mod.plan_swap(staged)

    return router
