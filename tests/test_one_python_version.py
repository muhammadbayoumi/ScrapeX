"""The engine's Python is named in one file, and every copy that cannot read it agrees.

WHY THIS FILE EXISTS. Until 2026-09-29 the version was written out eight times —
seven `python-version: "3.12"` lines across `.github/workflows/`, plus `requires-python`
and ruff's `target-version` in `pyproject.toml` — while the engine he actually runs was
started by `C:\\Python314\\python.exe` (his native host's launcher). So CI tested a Python
nobody ran, and the release build shipped one he had already left. Eight literals had
drifted together from the interpreter they were meant to describe, and nothing noticed,
because nothing compared them with anything.

The rule he set is that the engine is always upgraded. That needs the version to be
**one fact in one place** — `.python-version`, which `actions/setup-python` reads
directly — so that upgrading is a one-line change. This test holds the copies that
cannot read the file (`requires-python`, ruff's `target-version`) to it, and refuses
any workflow that names a version of its own instead.

The one exception is the weekly job whose whole purpose is to ask for the NEWEST
stable Python (`python-is-current.yml`, step id `newest-python`). It must say `3.x`,
never a number, or it would be a second pin wearing an exemption.
"""

from __future__ import annotations

import pathlib
import re
import tomllib

import pytest

yaml = pytest.importorskip("yaml")

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PIN_FILE = ".python-version"

#: (workflow file, step id) of the one step allowed a literal, and the literal it must hold.
NEWEST_PROBE = ("python-is-current.yml", "newest-python")
NEWEST_LITERAL = "3.x"


def _pinned() -> tuple[int, int]:
    text = (ROOT / PIN_FILE).read_text(encoding="utf-8").strip()
    match = re.fullmatch(r"(\d+)\.(\d+)", text)
    assert match, (f"{PIN_FILE} must hold MAJOR.MINOR and nothing else, got {text!r}: "
                   "a patch number would stop patch releases arriving on their own")
    return int(match.group(1)), int(match.group(2))


def _setup_python_steps():
    """(workflow name, job name, step) for every actions/setup-python step."""
    found = []
    for path in sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for job_name, job in (doc.get("jobs") or {}).items():
            for step in job.get("steps") or []:
                if str(step.get("uses") or "").startswith("actions/setup-python"):
                    found.append((path.name, job_name, step))
    return found


def _pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_the_pin_file_names_a_major_and_minor_only():
    major, minor = _pinned()
    assert major == 3 and minor >= 14


def test_there_are_workflows_to_check():
    # A glob that silently matched nothing would pass every test below.
    assert len(_setup_python_steps()) >= 7


def test_every_workflow_reads_the_version_from_the_pin_file():
    wrong = []
    for workflow, job, step in _setup_python_steps():
        options = step.get("with") or {}
        if (workflow, step.get("id")) == NEWEST_PROBE:
            continue
        if options.get("python-version-file") != PIN_FILE or "python-version" in options:
            wrong.append(f"{workflow}:{job} -> {options}")
    assert not wrong, (f"these setup-python steps name a version of their own instead of "
                       f"reading {PIN_FILE}: {wrong}")


def test_the_newest_probe_asks_for_the_newest_and_nothing_else():
    probes = [step for workflow, _job, step in _setup_python_steps()
              if (workflow, step.get("id")) == NEWEST_PROBE]
    assert len(probes) == 1, f"expected exactly one {NEWEST_PROBE} step, found {len(probes)}"
    assert (probes[0].get("with") or {}).get("python-version") == NEWEST_LITERAL


def test_requires_python_is_the_pinned_version():
    major, minor = _pinned()
    assert _pyproject()["project"]["requires-python"] == f">={major}.{minor}"


def test_ruff_targets_the_pinned_version():
    major, minor = _pinned()
    assert _pyproject()["tool"]["ruff"]["target-version"] == f"py{major}{minor}"
