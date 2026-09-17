r"""No test may write the warehouse, the logs or the exports he actually uses.

`CLAUDE.md`: "The warehouse write permission is exclusive... the engine holds the
write lock, and a second writer is a defect." A test run was that second writer.
Observed 2026-09-11 while a full `pytest` was in progress:

    ~/.scrapex/engine/scrapex-engine.db-wal   3,011,752 bytes, timestamp inside the run
    ~/.scrapex/contractors.log                  193,326 bytes, likewise
    ~/.scrapex/databases.json  ->  an engine_path inside that same directory

That is the file `databases.json` points the PANEL at.

DISCOVERED, NOT NAMED, and the first fix is why. `tests/conftest.py` redirects
`SCRAPEX_DATA_ROOT` before the first `scrapex` import, which was believed to move
everything. It moved three of seven: `funnel`, `localinbox`, `localsheets` and
`storage` each derived their own default from `Path.home()` under their own
variable, so one root moved and four did not -- and nothing said so. A guard that
listed the paths it knew about would have had the same blind spot as the fix.

SO IT WALKS THE PACKAGE. Every module-level `Path` constant in `scrapex` is read
back and checked against the two directories that are his: `~/.scrapex`, the data
root, and `~/ScrapeX`, where his workbooks land. Constants pointing INTO THE
REPOSITORY are fine and are the majority -- `db/engine/schema.sql`, `sources.yaml`,
the contract vectors -- so the test asks about his directories, not about his home,
which contains the checkout too.
"""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

import pytest

# NOT `pytest.mark.docs`: this guards no document, it imports 118 modules and
# reads their constants. The mark would put a full-package import walk into the
# documentation-only CI tier and make the mark mean two things.

HIS = (Path.home() / ".scrapex", Path.home() / "ScrapeX")


def _walk():
    """Every `NAME: Path` a `scrapex` module froze at import -- and what it could not read.

    THE SKIPS ARE RETURNED, NOT SWALLOWED. A module that fails to import has its
    constants checked by nothing, so a swallowed ImportError is exactly how this
    guard would cover less than it claims while staying green -- the failure it
    exists to catch, one level up. `test_the_walk_reaches_every_module` asserts on
    the list.
    """
    import scrapex

    constants, skipped = [], []
    for found in pkgutil.walk_packages(scrapex.__path__, "scrapex."):
        try:
            module = importlib.import_module(found.name)
        except Exception as exc:            # reported below, never dropped
            skipped.append(f"{found.name}: {type(exc).__name__}: {exc}")
            continue
        for name, value in vars(module).items():
            if not name.isupper():
                continue
            for label, path in _paths_in(f"{found.name}.{name}", value):
                constants.append((label, path))
    return constants, skipped


def _paths_in(label, value, depth=0):
    """Every path inside `value`, whatever shape it was written in.

    A FIRST VERSION MATCHED `isinstance(value, Path)` AND NOTHING ELSE, and an
    adversary killed it with two constants this repository already contains:
    `scrapex/cli.py`'s `str(Path.home() / "ScrapeX")` and
    `scrapex/nativehost.py:20`'s `{"win32": Path.home() / ...}`. Both name a
    directory of his, both passed green. A guard blind to a shape is the same
    defect as a guard blind to a module -- it covers less than it says while
    staying green.
    """
    if isinstance(value, Path):
        yield label, value
    elif isinstance(value, str):
        # Only an absolute path: a bare word is a name, not a location, and
        # every relative string would resolve against the working directory.
        if len(value) > 3 and Path(value).is_absolute():
            yield label, Path(value)
    elif depth == 0 and isinstance(value, (dict, list, tuple, set, frozenset)):
        members = value.values() if isinstance(value, dict) else value
        for index, member in enumerate(members):
            yield from _paths_in(f"{label}[{index}]", member, depth + 1)


def _module_paths():
    return _walk()[0]


def test_no_constant_points_at_a_directory_of_his():
    offenders, unresolvable = [], []
    for name, value in _module_paths():
        try:
            resolved = value.resolve()
        except OSError:
            unresolvable.append(name)     # reported below, never dropped
            continue
        for his in HIS:
            if resolved == his or his in resolved.parents:
                offenders.append(f"{name} = {value}")

    assert not unresolvable, (
        "these constants could not be resolved, so they were compared against "
        "nothing: " + ", ".join(unresolvable) + ". Dropping them silently is the "
        "failure this file exists to catch, one level down.")
    assert not offenders, (
        "these constants point into a directory the owner uses, so a test run "
        "writes his data rather than a temporary copy:\n  "
        + "\n  ".join(sorted(offenders))
        + "\n\nEach should derive from `scrapex.databases.registry.DATABASE_ROOT`, "
          "which `tests/conftest.py` redirects before the first import. A default "
          "written as its own `Path.home() / \".scrapex\" / ...` reads no redirect.")


def test_the_walk_reaches_every_module():
    """The floor above counts what was FOUND; this counts what was missed.

    CI installs `.[dev,browser]`, so nothing under `scrapex/` has an unmet import
    there -- measured, 118 of 118 import in 0.82s. Anything in this list is a real
    defect or a new optional extra, and either way it must be named rather than
    quietly reduce what the guard covers.
    """
    constants, skipped = _walk()

    assert not skipped, (
        "these modules could not be imported, so their path constants were "
        "checked by nothing:\n  " + "\n  ".join(skipped)
        + f"\n\n{len(constants)} constants were still found, which is why the "
        "floor below stays green -- a count of what was found cannot notice "
        "what was skipped.")


def test_the_walk_actually_finds_constants():
    """A walker that silently matched nothing would make the guard above vacuous --
    the failure this repository keeps finding. `scrapex` has module-level Path
    constants by construction; if this finds none, the reader changed shape."""
    found = list(_module_paths())

    assert len(found) >= 20, (
        f"only {len(found)} module-level Path constants found across scrapex/, "
        "which is too few to be real -- the walker has probably stopped importing "
        "or stopped matching, and the guard above is passing over nothing.")


def test_the_export_folder_is_decided_in_one_place():
    """A path the guard above cannot see, because it is a local, not a constant.

    `scrapex export --folder` defaulted to its own `str(Path.home() / "ScrapeX")`
    inside `build_parser()`. That agreed with `localsheets.DEFAULT_EXPORT_DIR` until
    the constant started following `SCRAPEX_DATA_ROOT` -- after which the panel's
    route followed the redirect and the CLI wrote his real folder, with the walk
    above green because a lowercase local in a function body is not a module
    constant. Found by an adversary, not by the guard.
    """
    from scrapex import localsheets
    from scrapex.cli import build_parser

    asked = build_parser().parse_args(["export", "any-source"]).folder

    assert asked == str(localsheets.DEFAULT_EXPORT_DIR), (
        f"`scrapex export` defaults to {asked!r} and the panel exports to "
        f"{str(localsheets.DEFAULT_EXPORT_DIR)!r}. Two spellings of one decision, "
        "and under a redirect only one of them follows it.")


def test_the_engine_log_opener_is_wrapped_for_the_whole_run():
    """#983: the log is the one path #910's redirect never reached.

    `scrapex/relaunch.py:145` `engine_log()` is a bare `Path.home() / ".scrapex" /
    "engine.log"` with no environment variable behind it, so `SCRAPEX_DATA_ROOT`
    -- which `conftest.py` sets before the first `scrapex` import -- does not move
    it. `open_engine_log()` then mkdirs, ROTATES and opens for append. A test that
    calls it with no `path` writes the file every panel failure message tells him
    to open, and can roll it aside under a running engine.

    The walk at the top of this file cannot see it: that guard reads module-level
    UPPERCASE `Path` constants, and `engine_log` is a function. So `conftest.py`
    wraps the opener instead -- and THIS asks whether the wrapper is still there.

    BY NAME, NOT BY CALLING. Calling the opener to find out would, on a conftest
    where the wrapper was removed, perform the exact write this exists to prevent.
    The name is enough: the wrapper is installed once at conftest import, before
    any test runs, and nothing legitimate replaces it afterwards.

    Without this, the wrapper was unfalsifiable: deleting its one assignment line
    left tests/test_db.py, tests/test_relaunch_log.py and tests/test_native.py
    green, 79 passed.
    """
    from scrapex import relaunch

    # BOTH DOORS. `rotate_engine_log` carries the same `path or engine_log()`
    # and is the worse of the two: it unlinks the kept copy and renames the live
    # log. An adversary rolled a log aside through it while the opener's guard
    # was installed and green.
    for name in ("open_engine_log", "rotate_engine_log"):
        installed = getattr(relaunch, name)
        assert installed.__name__ == f"_guarded_{name}", (
            f"`relaunch.{name}` is {installed.__name__!r}, so tests/conftest.py's "
            f"wrapper is not installed and a call with no `path` reaches his real "
            f"~/.scrapex/engine.log")
