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


def known_commands() -> frozenset[str]:
    """The CLI's subcommands. Anything NOT in here means Chrome launched us.

    A FUNCTION, AND DERIVED, because the frozenset that used to sit here was
    written by hand and drifted to half the CLI. It listed twelve names;
    `scrapex.cli` had twenty-four. The other twelve -- `database-status`,
    `autostart`, `backup-databases`, `restore-database`, `carry-over`,
    `contractors`, `export-version`, `relaunch`, `restore-database`, `run-due`,
    `schedule`, `sources`, `wipe-source` -- fell through to `serve()`, the Chrome
    native messaging host, which waits on stdin and prints nothing. Measured on
    the published 0.2.1: `status` answered in 94 bytes, `database-status` in
    ZERO. `OP-35`.

    `relaunch` being on that list is the sharpest of them: the engine spawns
    itself with that very subcommand in order to restart, so a frozen engine
    could not restart itself even once the argv was right (`OP-36`).

    Deriving it means a subcommand added tomorrow is reachable from the shipped
    binary the same day, with nobody having to remember this file exists.
    """
    from scrapex.cli import subcommands

    return subcommands()


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
    if argv and argv[0] in known_commands():
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
    """The four visible steps, then the server, which does not return."""
    from scrapex.version import VERSION

    _say(f"  ScrapeX-Engine {VERSION}")
    _say("  " + "-" * 46)
    _say()

    _say("  [1/4] Unpacking...")
    # Reaching this line at all means PyInstaller has already unpacked the
    # bundle and started Python — there is nothing left to wait for, and
    # pretending otherwise would be a fake progress bar.
    _say("        done. Python and everything it needs are inside this file;")
    _say("        nothing else has to be installed.")
    _say()

    _say("  [2/4] Preparing your database...")
    from scrapex.databases.registry import DatabaseRegistry

    registry = DatabaseRegistry.defaults()
    report = registry.ensure_ready()
    _say(f"        {'created' if report['created'] else 'already there'}: "
         f"{registry.engine.path}")
    _say()

    restartable = _link_chrome(report)

    # The panel's DATA path is plain HTTP to 127.0.0.1 and needs no native host
    # at all, so whatever the step above said, this one starts the engine.
    _say("  [4/4] Starting the engine...")
    # The control as the panel names it: Run's card and the Engine page both say
    # "Check again". This said "Check ScrapeX-Engine again", an icon's old label.
    _say('        Open ScrapeX in Chrome and press "Check again".')
    _say()
    _say("  LEAVE THIS WINDOW OPEN while you work — closing it stops the engine.")
    _say("  Ctrl+C stops it too.")
    if restartable:
        # Only where step 3 left Chrome starting THIS program: after "kept" it starts
        # the project files, and after a refusal it starts nothing.
        _say("  Once it is closed, Start engine in the ScrapeX panel starts it again.")
    _say()

    from scrapex.cli import main as cli_main

    # The supported path, reused rather than reimplemented: `ui` binds the log
    # streams, upgrades a database that is merely behind, starts the worker, and
    # serves. `--no-open` because the control room is the Chrome panel; opening a
    # browser window here would offer a second, competing face.
    sys.argv = [sys.argv[0], "ui", "--no-open"]
    return cli_main()


def _link_chrome(report: dict) -> bool:
    """Step 3: register Chrome's helper, so the panel can start this engine (#839).

    True when Chrome now starts this program for the panel.

    THIS STEP ONCE CLAIMED TO REGISTER THE NATIVE HOST, AND COULD NOT. It called
    `scrapex.nativehost.install()` with no arguments, whose `extension_ids` is
    required, so it raised TypeError on every machine, a bare `except` swallowed it,
    and the heading promised Chrome had been told something. The comment that
    replaced it said this program cannot know the panel's id, and left the panel to
    register itself over HTTP — which it did only when a helper already existed and
    refused it, so a fresh machine never got one and Start engine stayed dead. The id
    IS known: `extension/manifest.json`'s `key` pins it (`PANEL_EXTENSION_ID`).

    WHAT IT WRITES, AND WHAT IT NEVER TAKES, is `nativehost.link_installed_engine`'s.

    NOT WHEN THIS ENGINE CANNOT OPEN THE WAREHOUSE. An older copy run after a newer
    one meets a database it refuses ("Needs a newer ScrapeX"); moving the helper to
    it would make Start engine fail for the copy that can. A database that is only
    behind does not stop it: `scrapex ui` backs it up and upgrades it on the way up.
    """
    from scrapex import nativehost
    from scrapex.dbupgrade import BEHIND

    _say("  [3/4] Linking Chrome to this engine...")
    refused = [state["status"] for state in report["databases"].values()
               if not state["ok"] and state["status"] != BEHIND]
    if refused:
        _say(f"        skipped: this engine cannot open your database ({refused[0]}).")
        _say()
        return False
    try:
        outcome, before = nativehost.link_installed_engine()
    except Exception as exc:                       # noqa: BLE001
        # SAID, NEVER FATAL: the panel's data path is HTTP and needs no helper, so
        # nothing that goes wrong here may stop the engine starting below.
        _say(f"        could not: {type(exc).__name__}: {exc}")
        _say()
        return False
    if outcome == "moved":
        _say(f"        done. Chrome now starts this copy, not {before.launcher}.")
    elif outcome == "kept":
        _say(f"        left as it is: Chrome starts your project files ({before.launcher}).")
    elif outcome == "already":
        # Specific, not "done", which copywriting.mdx@86c813ec:98 lists as Bad.
        _say("        already linked to this copy.")
    else:
        _say("        done. The ScrapeX panel can now start this engine itself.")
    _say()
    return outcome != "kept"


if __name__ == "__main__":
    raise SystemExit(main())
