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


#: Asked BEFORE anything else, because the rule below deliberately sends every
#: dash-argument to the native host and would swallow these too.
VERSION_FLAGS = frozenset({"--version", "-V"})


def main() -> int:
    from scrapex.cli import main as cli_main
    from scrapex.native import serve
    from scrapex.version import VERSION

    # WHAT IS THIS BINARY? — answered first, and on stdout.
    #
    # It is the only question that can be asked of an engine you have just
    # downloaded and do not yet trust, and until this existed there was NO WAY
    # TO ASK IT. `--version` starts with a dash, the filter below dropped it,
    # `argv` came out empty, and the executable quietly became a native
    # messaging host waiting on stdin for framed JSON. It printed nothing and
    # looked like a hang.
    #
    # The release workflow's "the thing that was built must actually run" step
    # is what found this, on its first real run, by getting an empty string back
    # from a flag it had assumed existed.
    #
    # Chrome never passes these: its launch arguments are the host manifest
    # path, the calling origin, and on Windows `--parent-window=<handle>`. An
    # exact match on two spellings cannot collide with any of them, which is why
    # this is a membership test and not a prefix test.
    if VERSION_FLAGS & set(sys.argv[1:]):
        from scrapex.native import PROTOCOL_VERSION

        print(f"ScrapeX-Engine {VERSION} (protocol {PROTOCOL_VERSION})")
        return 0

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
