"""Frozen-executable entry point for the ScrapeX engine.

Chrome starts this with no arguments when acting as a native messaging host, so
that is the DEFAULT mode: bare invocation speaks framed JSON on stdio. Any other
argument falls through to the normal CLI, so the single binary is still the whole
tool (`scrapex-engine ui`, `scrapex-engine install-native-host ...`).
"""
from __future__ import annotations

import sys


# The CLI's subcommands. Anything NOT in here means Chrome launched us.
KNOWN_COMMANDS = frozenset({
    "init-db", "validate-manifest", "export-contract", "funnel-test", "crawl",
    "ingest", "peek", "google-connect", "push", "export", "ui", "native-host",
    "install-native-host", "status",
})


def main() -> int:
    from scrapex.cli import main as cli_main
    from scrapex.native import serve

    # Chrome passes the host manifest path and an origin argument whose shape
    # varies by Chrome build. Testing for "looks like a manifest" was fragile —
    # any unrecognised argument fell through to the CLI, which would then print
    # usage to a pipe Chrome expects framed JSON on and exit. So: dispatch to the
    # CLI ONLY for a known subcommand; everything else is the native host.
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    if argv and argv[0] in KNOWN_COMMANDS:
        return cli_main()
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
