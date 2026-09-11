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

pytestmark = pytest.mark.docs

HIS = (Path.home() / ".scrapex", Path.home() / "ScrapeX")


def _module_paths():
    """Every `NAME: Path` a `scrapex` module froze at import, with its module."""
    import scrapex

    for found in pkgutil.walk_packages(scrapex.__path__, "scrapex."):
        try:
            module = importlib.import_module(found.name)
        except Exception:  # noqa: BLE001 -- an optional extra, not this test's subject
            continue
        for name, value in vars(module).items():
            if name.isupper() and isinstance(value, Path):
                yield f"{found.name}.{name}", value


def test_no_constant_points_at_a_directory_of_his():
    offenders = []
    for name, value in _module_paths():
        try:
            resolved = value.resolve()
        except OSError:
            continue
        for his in HIS:
            if resolved == his or his in resolved.parents:
                offenders.append(f"{name} = {value}")

    assert not offenders, (
        "these constants point into a directory the owner uses, so a test run "
        "writes his data rather than a temporary copy:\n  "
        + "\n  ".join(sorted(offenders))
        + "\n\nEach should derive from `scrapex.databases.registry.DATABASE_ROOT`, "
          "which `tests/conftest.py` redirects before the first import. A default "
          "written as its own `Path.home() / \".scrapex\" / ...` reads no redirect.")


def test_the_walk_actually_finds_constants():
    """A walker that silently matched nothing would make the guard above vacuous --
    the failure this repository keeps finding. `scrapex` has module-level Path
    constants by construction; if this finds none, the reader changed shape."""
    found = list(_module_paths())

    assert len(found) >= 20, (
        f"only {len(found)} module-level Path constants found across scrapex/, "
        "which is too few to be real -- the walker has probably stopped importing "
        "or stopped matching, and the guard above is passing over nothing.")
