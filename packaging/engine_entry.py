"""Frozen-executable entry point for the ScrapeX engine.

One binary, three callers, told apart by the argument list alone:

    no arguments        a PERSON double-clicked the file -> `_first_run()`
    a known subcommand  the CLI (`scrapex-engine ui`, `... install-native-host`)
    anything else       Chrome, starting us as a native messaging host

Bare invocation used to mean the native host, which is why a double-click opened
a console that waited on stdin for framed JSON and showed nothing. Chrome always
passes arguments; a person never does. See `main()` for the whole argument.
"""
from __future__ import annotations

import sys


# The CLI's subcommands. Anything NOT in here means Chrome launched us.
KNOWN_COMMANDS = frozenset({
    "init-db", "validate-manifest", "export-contract", "funnel-test", "crawl",
    "ingest", "peek", "export", "ui", "native-host",
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

    # DOUBLE-CLICKED, OR LAUNCHED BY CHROME? The answer is the argument list,
    # and getting it backwards is what produced the black window.
    #
    # Chrome ALWAYS passes arguments: the host manifest path, the calling
    # origin, and on Windows `--parent-window=<handle>`. A person
    # double-clicking the file in Explorer passes NONE. So an empty argv is not
    # "Chrome with nothing to say" — it is a human who has just downloaded a
    # 67 MB file and is waiting to be told something.
    #
    # It used to mean `serve()`: a console window opened, waited on stdin for
    # framed JSON that would never arrive, and showed a black rectangle with no
    # text in it. Measured on the real 0.2.1 release, and it is the same root
    # cause as the `--version` defect fixed hours earlier — bare invocation
    # falling through to the messaging host.
    if not sys.argv[1:]:
        return _first_run()

    # Chrome passes the host manifest path and an origin argument whose shape
    # varies by Chrome build. Testing for "looks like a manifest" was fragile —
    # any unrecognised argument fell through to the CLI, which would then print
    # usage to a pipe Chrome expects framed JSON on and exit. So: dispatch to the
    # CLI ONLY for a known subcommand; everything else is the native host.
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    if argv and argv[0] in KNOWN_COMMANDS:
        return cli_main()
    return serve()


def _close_splash() -> None:
    """Take down the image the bootloader drew during the unpack.

    `pyi_splash` exists ONLY inside a one-file build made with `--splash`, so
    every other way of running this file — the source tree, a test, a onedir
    build — must reach here and do nothing rather than fail. That is what the
    bare except is for, and it is the one place in this file where swallowing an
    error is right: the splash is a courtesy, and a courtesy must never be able
    to stop the engine starting.
    """
    try:
        import pyi_splash                          # type: ignore[import-not-found]
    except Exception:                              # noqa: BLE001
        return
    try:
        pyi_splash.close()
    except Exception:                              # noqa: BLE001
        pass


def _say(line: str = "") -> None:
    # The first real line means the unpack is over and the console has something
    # to show, so the image comes down HERE rather than at some later "ready"
    # point — leaving it up while text scrolls behind it is worse than never
    # showing it.
    _close_splash()
    print(line, flush=True)


def _first_run() -> int:
    """What a person sees when they double-click the file they just downloaded.

    Not a progress bar for its own sake. Each line is a step that can fail on
    somebody's machine, so each is named before it is attempted and confirmed
    after — a run that stops half way says WHERE it stopped instead of closing.

    The window stays open because THE ENGINE IS RUNNING IN IT, not as a courtesy.
    An earlier version printed "All set" and then exited, which left nothing
    running and nothing registered while claiming both; the window being open is
    now the same fact as the engine being up.
    """
    try:
        code = _set_up_then_serve()
    except KeyboardInterrupt:
        _say()
        _say("  Stopped. Double-click this file again whenever you want the engine.")
        return 0
    except Exception as exc:                      # noqa: BLE001
        _say()
        _say(f"  It stopped here — {type(exc).__name__}: {exc}")
        code = 1
    if code != 0:
        # Only a FAILURE needs holding. On success the process is inside the
        # server and does not reach this line at all.
        _say()
        _say("  Open ScrapeX in Chrome; the Engine page says what is missing.")
        try:
            input("  Press Enter to close this window. ")
        except (EOFError, KeyboardInterrupt):
            pass
    return code


def _set_up_then_serve() -> int:
    """The three visible steps, then the server, which does not return."""
    from scrapex.version import VERSION

    _say(f"  ScrapeX-Engine {VERSION}")
    _say("  " + "-" * 46)
    _say()

    _say("  [1/3] Unpacking...")
    # Reaching this line at all means PyInstaller has already unpacked the
    # bundle and started Python — there is nothing left to wait for, and
    # pretending otherwise would be a fake progress bar.
    _say("        done. Python and everything it needs are inside this file;")
    _say("        nothing else has to be installed.")
    _say()

    _say("  [2/3] Preparing your database...")
    from scrapex.databases.registry import DatabaseRegistry

    registry = DatabaseRegistry.defaults()
    report = registry.ensure_ready()
    _say(f"        {'created' if report['created'] else 'already there'}: "
         f"{registry.engine.path}")
    _say()

    # THIS STEP USED TO CLAIM TO REGISTER THE NATIVE HOST, AND COULD NOT.
    #
    # It called `scrapex.nativehost.install()` with no arguments, whose first
    # parameter `extension_ids` is required — so it raised TypeError on every
    # machine, was swallowed by a bare `except`, and printed a failure line under
    # a heading that promised Chrome had been told something. The promise was not
    # merely unfulfilled, it was unfulfillable: Chrome only lets a native host
    # talk to extension ids named in its manifest, and THIS PROGRAM CANNOT KNOW
    # THE ID of an extension it has never spoken to. The panel registers itself,
    # over HTTP, once it can reach us (see the `forbidden` repair in app.js).
    #
    # So the step became the one thing a double-click genuinely can do, and the
    # one thing the person wanted: start the engine. The panel's DATA path is
    # plain HTTP to 127.0.0.1 and needs no native host at all.
    _say("  [3/3] Starting the engine...")
    _say('        Open ScrapeX in Chrome and press "Check ScrapeX-Engine again".')
    _say()
    _say("  LEAVE THIS WINDOW OPEN while you work — closing it stops the engine.")
    _say("  Ctrl+C stops it too.")
    _say()

    from scrapex.cli import main as cli_main

    # The supported path, reused rather than reimplemented: `ui` binds the log
    # streams, upgrades a database that is merely behind, starts the worker, and
    # serves. `--no-open` because the control room is the Chrome panel; opening a
    # browser window here would offer a second, competing face.
    sys.argv = [sys.argv[0], "ui", "--no-open"]
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
