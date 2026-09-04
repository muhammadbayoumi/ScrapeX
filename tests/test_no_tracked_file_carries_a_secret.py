"""No tracked file carries a credential, and the one that must ship is named here.

WHY THIS EXISTS. GitHub's secret scanning flagged three fixtures that carried Salla's
own browser key, captured verbatim when the page was saved. Scrubbing them fixes today;
nothing stopped the next capture from bringing the key straight back, because fixtures
are saved by hand and no tool sits in that path. This is that missing step.

WHAT IT IS NOT. It is not a scanner. It knows six credential shapes that are
unambiguous — a match is a credential, not a coincidence — and says nothing about
anything else. A password in a config file with a plausible-looking name is out of its
reach and is meant to be.

THE ALLOWLIST IS THE POINT. A browser key that must reach the browser cannot be hidden,
so the rule for it is different: it is restricted by referrer, not concealed. Naming it
here records that decision beside the guard, and pins the exact key — a DIFFERENT key
appearing at the same path still fails, because the exception was granted to one
reviewed credential and not to the file.
"""
from __future__ import annotations

import pathlib
import re
import subprocess

import pytest

pytestmark = pytest.mark.docs

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Shapes whose match is a credential by construction — each carries a vendor prefix
#: and a fixed length, so a random string cannot satisfy one.
SHAPES: dict[str, re.Pattern[str]] = {
    "google-api-key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "github-token": re.compile(r"gh[pousr]_[0-9A-Za-z]{36,}"),
    "aws-access-key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "slack-token": re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}"),
    "private-key-header": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "stripe-live-key": re.compile(r"sk_live_[0-9A-Za-z]{16,}"),
}

#: (path, shape) -> (the first 12 characters of the approved credential, the reason).
#: A key is pinned by prefix so that rotating it is a deliberate edit to this table
#: rather than something the guard lets through silently.
ALLOWED: dict[tuple[str, str], tuple[str, str]] = {
    ("docs/picker/scrapex-picker.html", "google-api-key"): (
        "AIzaSyBL5buz",
        "The picker's Google Maps browser key. A browser key is delivered to the "
        "browser and cannot be secret; it is protected by an HTTP-referrer "
        "restriction on the key itself, which is where that protection belongs.",
    ),
}

#: Binary and vendored trees are skipped by suffix rather than by reading them.
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".zip",
                 ".woff", ".woff2", ".ttf", ".eot", ".db", ".xlsx", ".exe"}


def _tracked() -> list[str]:
    listed = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True,
                            text=True, check=True).stdout.splitlines()
    return [rel for rel in listed if pathlib.Path(rel).suffix.lower() not in SKIP_SUFFIXES]


def _findings() -> list[tuple[str, str, int, str]]:
    """Every credential-shaped string in the tracked tree, as (path, shape, line, text)."""
    out: list[tuple[str, str, int, str]] = []
    for rel in _tracked():
        path = ROOT / rel
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:                      # pragma: no cover - unreadable is not a secret
            continue
        for shape, pattern in SHAPES.items():
            for match in pattern.finditer(text):
                out.append((rel, shape, text.count("\n", 0, match.start()) + 1,
                            match.group(0)))
    return out


def test_no_tracked_file_carries_an_unapproved_credential():
    """THE GUARD. Green today; it was red on three fixtures before they were scrubbed.

    It fails on a rotated key at an allowed path too, which is the case a
    path-only exception would wave through: the exception belongs to a credential
    that was reviewed, not to the file that happens to hold it.
    """
    unapproved = []
    for rel, shape, line, found in _findings():
        approved = ALLOWED.get((rel, shape))
        if approved is not None and found.startswith(approved[0]):
            continue
        unapproved.append(f"{rel}:{line} carries a {shape} ({found[:12]}...)")

    assert not unapproved, (
        "these tracked files carry a credential. A captured fixture is the usual "
        "cause — a saved page brings the site's own keys with it. Scrub the value "
        "and leave a placeholder that does not match the shape; if the credential "
        "genuinely has to ship, add it to ALLOWED with the protection that replaces "
        "secrecy:\n  " + "\n  ".join(unapproved))


def test_every_allowed_credential_is_still_there():
    """A stale exception is a hole nobody can see, so the allowlist ratchets shut.

    Once the picker's key is removed or replaced, this fails and the entry has to go.
    Without it the table would keep granting permission for a credential that no
    longer exists, and the next one to land at that path would inherit it.
    """
    present = {(rel, shape) for rel, shape, _, _ in _findings()}
    gone = [f"{rel} ({shape}): {ALLOWED[(rel, shape)][1].split('.')[0]}"
            for rel, shape in ALLOWED
            if (rel, shape) not in present]

    assert not gone, (
        "ALLOWED grants an exception for a credential that is no longer in the tree. "
        "Delete the entry — a permission left behind covers whatever lands there "
        "next:\n  " + "\n  ".join(gone))
