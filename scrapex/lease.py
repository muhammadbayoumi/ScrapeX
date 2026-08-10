"""One device writes at a time, and a dead one does not hold the warehouse forever.

DECISION 3: one device at a time, with restore. Drive is enough — no server, no
shared SQLite file over a network — and a lease is the whole of what stops two
machines writing the same warehouse and silently forking its history.

WHY A LEASE AND NOT A LOCK. A lock is held until it is released, and the machine
that holds this one can be closed, unplugged or reinstalled. Nobody would ever
release it, and the owner would be locked out of his own data by a laptop that no
longer exists. A lease EXPIRES, so the failure mode is "wait a while", not "lose
everything".

WHY IT IS RENEWED AND NOT TAKEN ONCE. A crawl of muqawil's details ran 34 hours.
A lease long enough to cover that would leave a crashed machine holding the
warehouse for a day and a half; a lease short enough to recover from a crash
quickly would expire in the middle of the crawl. Renewing while working settles
both: the lease is short, and it stays alive exactly as long as something is
alive to keep renewing it.

WHAT THIS IS NOT. It is not a security boundary. Anyone with the owner's Drive
can delete the file; the lease exists to stop an ACCIDENT — the same person on
two machines — which is the only case Decision 3 is about.
"""
from __future__ import annotations

import json
import os
import platform
import socket
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

#: How long a lease is good for without being renewed. Short enough that a
#: machine which died is forgotten within a coffee break, long enough that an
#: ordinary pause — a sleeping laptop, a slow upload — does not lose it.
LEASE_MINUTES = 15

#: How often a working device renews. A third of the term, so two renewals can
#: be missed entirely before anything is at risk.
RENEW_MINUTES = 5

_ISO = "%Y-%m-%dT%H:%M:%SZ"


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _stamp(moment: datetime) -> str:
    return moment.strftime(_ISO)


def _read_stamp(text: str) -> datetime | None:
    try:
        return datetime.strptime(text, _ISO).replace(tzinfo=UTC)
    except (TypeError, ValueError):
        return None


def device_id(state_dir: Path | str) -> str:
    """This machine's identity, made once and kept.

    NOT the hostname, and not a MAC address. Two machines can share a hostname,
    a hostname changes, and a MAC is a different value per adapter and per VPN
    state — an identity that changes when the network does would make one
    machine look like several and break the lease exactly when it is needed.

    A random id in a file beside the database is stable for as long as the
    installation is, which is the thing being identified.
    """
    path = Path(state_dir) / "device.json"
    if path.is_file():
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(stored.get("device_id"), str) and stored["device_id"]:
                return stored["device_id"]
        except (ValueError, OSError):
            pass  # unreadable is the same as absent: make a new one and say so

    made = uuid.uuid4().hex
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "device_id": made,
        # For the owner reading the lease, never for identity: he needs to
        # recognise WHICH of his machines is holding it, and a bare uuid does
        # not tell him that.
        "label": f"{platform.system()} · {socket.gethostname()}",
        "made_at": _stamp(_now()),
    }, indent=2), encoding="utf-8")
    return made


def device_label(state_dir: Path | str) -> str:
    path = Path(state_dir) / "device.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("label", "")
    except (ValueError, OSError):
        return ""


@dataclass
class Lease:
    device: str
    label: str
    taken_at: str
    expires_at: str

    def expired(self, now: datetime | None = None) -> bool:
        moment = _read_stamp(self.expires_at)
        if moment is None:
            # A lease with an unreadable expiry cannot be trusted to expire, so
            # it is treated as already gone. The alternative is a malformed file
            # holding the warehouse for ever.
            return True
        return (now or _now()) >= moment

    def to_json(self) -> str:
        return json.dumps({
            "device": self.device, "label": self.label,
            "taken_at": self.taken_at, "expires_at": self.expires_at,
        }, indent=2) + "\n"

    @classmethod
    def from_json(cls, text: str) -> Lease | None:
        try:
            data = json.loads(text)
        except (ValueError, TypeError):
            return None
        if not isinstance(data, dict) or not isinstance(data.get("device"), str):
            return None
        return cls(device=data["device"], label=data.get("label", ""),
                   taken_at=data.get("taken_at", ""),
                   expires_at=data.get("expires_at", ""))


@dataclass
class Verdict:
    """Whether this device may write, and what to say when it may not."""
    allowed: bool
    lease: Lease | None = None
    reason: str = ""
    action: str = ""


def read(path: Path | str) -> Lease | None:
    path = Path(path)
    if not path.is_file():
        return None
    try:
        return Lease.from_json(path.read_text(encoding="utf-8"))
    except OSError:
        return None


def claim(path: Path | str, device: str, label: str = "",
          now: datetime | None = None,
          minutes: int = LEASE_MINUTES) -> Verdict:
    """Take or renew the lease, or refuse and say who holds it.

    Renewing is the same call as taking: a device that already holds the lease
    simply pushes the expiry out. Making renewal a separate operation is how a
    long crawl ends up holding a lease it forgot to keep.
    """
    path = Path(path)
    moment = now or _now()
    held = read(path)

    if held is not None and held.device != device and not held.expired(moment):
        remaining = _read_stamp(held.expires_at)
        minutes_left = max(
            0, int((remaining - moment).total_seconds() // 60)) if remaining else 0
        return Verdict(
            allowed=False, lease=held,
            reason=("another device holds this warehouse"
                    + (f" — {held.label}" if held.label else "")),
            action=(f"Stop ScrapeX there, or wait {minutes_left} minute"
                    f"{'' if minutes_left == 1 else 's'} for its lease to expire."))

    taken_at = held.taken_at if (held and held.device == device and held.taken_at) \
        else _stamp(moment)
    fresh = Lease(device=device, label=label, taken_at=taken_at,
                  expires_at=_stamp(moment + timedelta(minutes=minutes)))

    path.parent.mkdir(parents=True, exist_ok=True)
    # Written whole and then moved into place. A reader that arrives mid-write
    # would otherwise find half a lease, and `from_json` would call it garbage
    # — which reads as "nobody holds this" and is the one wrong answer here.
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(fresh.to_json(), encoding="utf-8")
    os.replace(temporary, path)
    return Verdict(allowed=True, lease=fresh)


def release(path: Path | str, device: str) -> bool:
    """Give the lease up on a clean stop. Another device can start at once.

    Only the holder may release: a device that lost the lease while it was
    asleep must not delete the one that took over from it.
    """
    held = read(path)
    if held is None or held.device != device:
        return False
    Path(path).unlink(missing_ok=True)
    return True


def may_write(path: Path | str, device: str, label: str = "",
              now: datetime | None = None) -> Verdict:
    """The question the engine asks before it writes anything.

    A refusal names the machine and the wait, because "locked" with no idea by
    whom or for how long is the same dead end as an engine that refuses on a
    stderr nobody reads.
    """
    return claim(path, device, label=label, now=now)
