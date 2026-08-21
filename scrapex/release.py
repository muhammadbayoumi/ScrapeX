"""What the newest ScrapeX-Engine is — read by the ENGINE, not only the panel.

THE THIRD READER OF ONE FILE, and that is the whole risk this module carries.
`ScrapeX/json/version.json` on the hub is written by
`.github/workflows/release-engine.yml` and read by `extension/releases.js`;
`tests/test_the_two_release_paths.py` already asserts those two agree about where
it lives. This is a third participant, so the same constants are declared here
and `tests/test_the_engine_reads_the_same_release_feed.py` holds all three
together. A version manifest that the engine and the panel disagree about is
worse than none: they would report different verdicts about the same
installation, and the owner would have no way to tell which was lying.

WHY THE ENGINE NEEDS TO READ IT AT ALL, given the panel already does. `R-36`:
the first install must come through the browser because nothing is installed
yet, but **every update after that belongs to the engine** — the panel is a
Chrome extension and Chrome grants it no way to verify a checksum, no way to
read a file off disk, and no way to launch a process. The engine is a local
process with all three. So the panel asks and the engine acts, and acting starts
with knowing what is published.

THE STATE VOCABULARY IS DELIBERATELY THE SAME FOUR as `releases.js` — `ok`,
`none`, `offline`, `unreadable` — because "we do not know the latest engine" has
several causes and only one of them is anybody's fault. Two surfaces that name
those causes differently will eventually be shown side by side.

NOT `HttpFetcher`. That is the crawl transport: conditional requests, jitter, a
circuit breaker, one-request-per-second politeness. This is a single request to
our own release host, and none of that applies — borrowing it would inherit a
rate limiter and a block counter that mean nothing here, and would put our own
release feed behind a governor built for somebody else's website.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

#: The public delivery endpoint. ScrapeX's own repository goes private before
#: the first release and GitHub answers 404 on a private repository to anyone
#: not signed in — which is every user. Named once here; `extension/releases.js`
#: holds the same string and a test asserts they match.
PUBLIC_REPO = "muhammadbayoumi/mbiX-hub"

#: Where this product's manifest lives, beside the Excel add-in's.
VERSION_MANIFEST = (
    f"https://raw.githubusercontent.com/{PUBLIC_REPO}/main/ScrapeX/json/version.json"
)

#: Where a human goes.
PUBLIC_HOME = f"https://github.com/{PUBLIC_REPO}"

#: The product this manifest must be about. The hub serves several, and reading
#: the add-in's as ours would report a confident, wrong version.
PRODUCT = "scrapex-engine"

#: Its own timeout, held apart from anything else the engine does. A stalled
#: fetch to a third party must never delay the thing the owner asked for.
CHECK_TIMEOUT_S = 4.0

#: How long the whole installer download may take. Generous, because it is
#: ~70 MB over somebody's home connection, and because failing a real download
#: at four minutes would be worse than waiting.
DOWNLOAD_TIMEOUT_S = 900.0

_VERSION_SHAPE = ("0123456789.", 3)


@dataclass(frozen=True)
class Installer:
    """The file a release attaches, and the digest that proves it arrived whole."""

    name: str
    url: str
    bytes: int
    sha256: str

    @property
    def verifiable(self) -> bool:
        """Is there enough here to refuse a bad download?

        A release whose installer carries no digest is installable only by
        trusting the transport alone. `R-36` names the published SHA-256 as the
        thing that makes an updater acceptable before code signing exists, so an
        installer without one is reported and NOT offered for automatic update.
        """
        return bool(self.url) and len(self.sha256) == 64


@dataclass(frozen=True)
class Release:
    """One of the four things a reader can be told, and never a guess."""

    state: str                     # ok | none | offline | unreadable
    detail: str = ""
    version: str = ""
    tag: str = ""
    published_at: str = ""
    url: str = ""
    minimum_extension: str = ""
    protocol: int | None = None
    installer: Installer | None = None
    #: Everything the manifest said, kept so a field added upstream is not lost
    #: on the way through this module.
    raw: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.state == "ok"


def _looks_like_a_version(value: object) -> bool:
    """`1.2.3`, and nothing else — the same shape `releases.js` requires.

    Written out rather than done with a regex because the rule is small and the
    failure mode of a loose one is a manifest that names `latest` or `v2` and is
    then compared with `<` against a real version.
    """
    if not isinstance(value, str):
        return False
    allowed, dots = _VERSION_SHAPE
    parts = value.split(".")
    return (len(parts) == dots
            and all(p.isdigit() and p != "" for p in parts)
            and all(c in allowed for c in value))


def read_manifest(status: int, body: object) -> Release:
    """Turn the endpoint's answer into one of the four states.

    `status` and `body` are passed IN rather than fetched, for the same reason
    `releases.js` does it: the offline branch can then be tested honestly. A
    test that had to reach the network to prove what happens when the network is
    unreachable would prove nothing.
    """
    if status == 404:
        # On this endpoint a missing file means exactly one thing, and it is not
        # an error: no engine has been released yet. Reporting it as a failure
        # would tell every fresh installation that something is broken.
        return Release(state="none", detail="No engine has been released yet.")
    if status != 200:
        return Release(state="unreadable",
                       detail=f"The release manifest answered {status}.")
    if not isinstance(body, dict):
        return Release(state="unreadable",
                       detail="The release manifest could not be read.")

    product = body.get("product")
    if product != PRODUCT:
        return Release(
            state="unreadable",
            detail=(f"That manifest is for {product or 'another product'}, "
                    f"not the ScrapeX engine."),
            raw=body)

    version = body.get("version")
    if not _looks_like_a_version(version):
        return Release(
            state="unreadable",
            detail=f"The release manifest names no usable version ({version or 'empty'}).",
            raw=body)

    spec = body.get("installer")
    installer = None
    if isinstance(spec, dict) and isinstance(spec.get("url"), str):
        try:
            size = int(spec.get("bytes") or 0)
        except (TypeError, ValueError):
            size = 0
        installer = Installer(
            name=spec.get("name") or "scrapex-engine.exe",
            url=spec["url"],
            bytes=size,
            sha256=(spec.get("sha256") or "").strip().lower(),
        )

    return Release(
        state="ok",
        version=version,
        tag=body.get("tag") if isinstance(body.get("tag"), str) else f"engine-v{version}",
        published_at=body.get("published_at") if isinstance(body.get("published_at"), str) else "",
        url=body.get("release_url") if isinstance(body.get("release_url"), str) else PUBLIC_HOME,
        minimum_extension=(body.get("minimum_extension_version")
                           if isinstance(body.get("minimum_extension_version"), str) else ""),
        protocol=(body.get("protocol_version")
                  if isinstance(body.get("protocol_version"), int) else None),
        # Named even when absent: a release with no installer attached is a
        # release nobody can install, and that is worth seeing before the moment
        # somebody presses Install.
        installer=installer,
        raw=body,
    )


def manifest_url(minute: int) -> str:
    """The URL actually fetched, with a cache key that changes once a minute.

    NOT SUPERSTITION, and the reason is `releases.js`'s: raw.githubusercontent
    .com serves this file through a CDN that caches it for about five minutes.
    The manifest is rewritten in place on every release, so without a changing
    key a release can exist and be invisible for five minutes after it is cut.

    The minute BUCKET rather than a unique timestamp is deliberate too: everyone
    asking within the same minute shares one cache entry, so the CDN still
    absorbs almost every request. A per-request value pushes every caller
    through to origin, which measurably slowed the fetch on the add-in's own
    path and made its timeout far likelier to fire.

    The bucket is passed in rather than read from the clock, so this is a pure
    function and the caller owns the only clock read.
    """
    return f"{VERSION_MANIFEST}?t={int(minute)}"


def latest(*, now_s: float | None = None) -> Release:
    """Ask the endpoint, and never let the asking delay anything.

    Import-local `httpx` and `time`: this module is read by tests that never
    touch the network, and the whole point of `read_manifest` being separate is
    that they do not have to.
    """
    import time

    import httpx

    minute = int((time.time() if now_s is None else now_s) // 60)
    try:
        response = httpx.get(manifest_url(minute), timeout=CHECK_TIMEOUT_S,
                             follow_redirects=True,
                             headers={"Cache-Control": "no-cache"})
    except Exception:
        # A refusal, a DNS failure and the timeout all land here, and from the
        # engine they are one fact: nobody answered. The engine you have keeps
        # working, so this is not an error state to act on.
        return Release(state="offline",
                       detail=("Could not reach the release endpoint. The engine "
                               "you have keeps working."))
    try:
        body = response.json()
    except (json.JSONDecodeError, ValueError):
        body = None
    return read_manifest(response.status_code, body)


def is_newer(candidate: str, installed: str) -> bool:
    """Is `candidate` a later version than `installed`?

    Numeric per component, never string comparison: `"0.10.0" > "0.9.0"` is
    false as text and true as a version, and getting that backwards offers a
    downgrade as an update. An unparseable version on either side answers False
    — refusing to claim an update is the safe direction.
    """
    if not (_looks_like_a_version(candidate) and _looks_like_a_version(installed)):
        return False
    left = [int(p) for p in candidate.split(".")]
    right = [int(p) for p in installed.split(".")]
    return left > right
