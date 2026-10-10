"""The harness's server queues every connection a page opens at once.

`tools/tabpage_harness.serve` is what every served DOM suite loads its modules
from: the grid, the Data page, the Console, the panel. A browser opens several
connections to it at the same moment, and the accept thread shares a busy test
process. If those connections outnumber the listen backlog while the thread is
behind, Windows refuses the next one outright and the module it carried never
loads -- the page then fails as if the code under test were broken. Linux drops
the SYN instead and the client retries, which is why a backlog of five passed on
ubuntu CI and failed only on the Windows release runner.

So the test holds the accept thread still on purpose -- the server is bound and
listening and never served -- and opens more connections than a browser does.
Every one must complete its handshake in the backlog. At a backlog of five,
Windows refuses the sixth and Linux leaves it waiting; both fail here.
"""
from __future__ import annotations

import select
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import tabpage_harness  # noqa: E402

#: Chromium's six connections per host, twice: two pages, or a page and a retry.
AT_ONCE = 12


def _connect_all(port: int, count: int, *, within: float) -> tuple[int, int, int]:
    """Open `count` connections at once. Returns (connected, refused, still waiting)."""
    sockets = []
    try:
        for _ in range(count):
            client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client.setblocking(False)
            client.connect_ex(("127.0.0.1", port))
            sockets.append(client)
        connected = refused = 0
        pending = list(sockets)
        deadline = time.monotonic() + within
        while pending and time.monotonic() < deadline:
            _, writable, failed = select.select([], pending, pending, 0.2)
            for client in set(writable) | set(failed):
                if client.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) == 0:
                    connected += 1
                else:
                    refused += 1
                pending.remove(client)
        return connected, refused, len(pending)
    finally:
        for client in sockets:
            client.close()


def test_connections_the_server_has_not_yet_accepted_are_queued_not_refused():
    # Bound and listening, never served: the accept thread at its slowest.
    server = tabpage_harness._Server(("127.0.0.1", 0), tabpage_harness._QuietHandler)
    try:
        connected, refused, waiting = _connect_all(
            server.server_address[1], AT_ONCE, within=3.0)
    finally:
        server.server_close()
    assert (connected, refused, waiting) == (AT_ONCE, 0, 0), (
        f"of {AT_ONCE} connections opened at once, {connected} were queued, {refused} "
        f"were refused and {waiting} never completed: the listen backlog is "
        f"{tabpage_harness._Server.request_queue_size}, and a served page whose module "
        "lands on a refused connection fails as if the code under test were broken")


def test_the_served_page_still_answers_every_connection_it_queued():
    """The backlog only queues: each queued connection is then served in full."""
    with tabpage_harness.serve(ROOT / "tools") as base:
        port = int(base.rsplit(":", 1)[1])
        sockets = [socket.create_connection(("127.0.0.1", port), timeout=10)
                   for _ in range(AT_ONCE)]
        try:
            for client in sockets:
                client.sendall(b"GET /tabpage_harness.py HTTP/1.0\r\n\r\n")
            for client in sockets:
                reply = b""
                while chunk := client.recv(65536):
                    reply += chunk
                assert reply.startswith(b"HTTP/1.0 200"), reply[:80]
        finally:
            for client in sockets:
                client.close()
