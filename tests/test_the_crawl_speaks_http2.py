"""The layer under the headers: what the connection itself says.

`browser_headers` made the crawl's headers match the agent it claims. This is
the one below them. HTTP/2 is chosen during the TLS handshake by ALPN — before
a single header is sent — so a client announcing Chrome and then speaking
HTTP/1.1 contradicted itself where no header could fix it, and any server could
see it without reading one.

THE FAILURE MODE THIS FILE EXISTS FOR is not a crash. It is `http2=True` that
changes nothing: httpcore adds "h2" to ALPN only when the connection is built
with it, and this project passes a SHARED `ssl.SSLContext` into every client
(measured: 1633ms -> 0.6ms per client, `connectors/base.py`). A setting that
looks applied and never reaches the handshake would leave the contradiction in
place with a comment claiming otherwise, which is worse than not doing it.

Nothing here reaches the network. The negotiation itself was verified once
against a live endpoint that speaks HTTP/2 — `response.http_version` came back
`HTTP/2` — and that is a fact about a server, not about this code, so it is
recorded here rather than asserted on every run.
"""
from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path

from scrapex.connectors.base import HttpFetcher

ROOT = Path(__file__).resolve().parent.parent


def test_the_crawl_client_is_built_to_speak_http2():
    """Read off the pool the client actually built, not off the argument."""
    fetcher = HttpFetcher()
    try:
        pool = fetcher._client._transport._pool
    finally:
        fetcher.close()

    assert pool._http2 is True, (
        "the crawl's connection pool does not offer HTTP/2, so the handshake "
        "advertises http/1.1 alone and every request contradicts the Chrome "
        "agent it carries")


def test_http1_is_still_offered_so_a_site_may_refuse_http2():
    """NOT a demand. The server picks from the ALPN list, so a site that speaks
    only HTTP/1.1 must keep working exactly as it did."""
    fetcher = HttpFetcher()
    try:
        pool = fetcher._client._transport._pool
        assert pool._http1 is True, (
            "HTTP/1.1 is no longer offered, so a site that does not speak "
            "HTTP/2 can no longer be crawled at all")
    finally:
        fetcher.close()


def test_the_dependency_is_declared_and_not_merely_installed():
    """A local green proves nothing here: `h2` may be installed for another
    reason entirely, and CI builds from pyproject."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = data["project"]["dependencies"]

    assert any(name.startswith("httpx[") and "http2" in name
               for name in declared), (
        f"httpx is declared without the http2 extra in {declared}. The client "
        "asks for HTTP/2 and a fresh install would raise ImportError on the "
        "first crawl")


def test_the_h2_package_is_actually_importable():
    """The other half: declared is not installed. httpx raises at CLIENT
    CONSTRUCTION when `h2` is absent, so this would be every crawl, not one."""
    assert importlib.util.find_spec("h2"), (
        "`h2` is not importable, so building any HttpFetcher raises. Run: "
        "pip install -e .[dev]")


def test_the_shared_ssl_context_does_not_cost_the_negotiation():
    """WHY THIS IS NOT OBVIOUS, and why it is asserted.

    httpcore calls `ssl_context.set_alpn_protocols(...)` on the context it is
    HANDED, at connection time. This project hands every fetcher ONE shared
    context, so that call mutates shared state — and if some other client were
    to share it with `http2=False`, the two would overwrite each other's ALPN
    list and the crawl's protocol would depend on connection order.

    Measured when this landed: `HttpFetcher` is the only caller of
    `shared_ssl_context()`. This pins that, because the day a second caller
    appears with different settings is the day the negotiation becomes a race
    nobody is watching.
    """
    users = []
    for path in sorted((ROOT / "scrapex").rglob("*.py")):
        for number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.lstrip()
            if stripped.startswith("#") or "def shared_ssl_context" in line:
                continue
            if "shared_ssl_context()" in line:
                users.append(f"{path.relative_to(ROOT)}:{number}")

    assert len(users) == 1, (
        f"{users} share one ssl.SSLContext. httpcore sets ALPN on the context "
        "it is given, so two clients sharing it with different http2 settings "
        "overwrite each other and the protocol becomes whichever connected "
        "last. Give the second caller its own context, or make them agree.")
