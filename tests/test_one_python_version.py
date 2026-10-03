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
never a number, or it would be a second pin wearing an exemption — and it must set
`check-latest`, or setup-python answers from the runner's cache, which took 107 days
to add 3.13. The release build sets it too, so the shipped engine takes the newest patch.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import tomllib

import pytest

from scrapex import nativehost
from scrapex.cli import build_parser

yaml = pytest.importorskip("yaml")

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
PIN_FILE = ".python-version"

#: (workflow file, step id) of the one step allowed a literal, and the literal it must hold.
NEWEST_PROBE = ("python-is-current.yml", "newest-python")
NEWEST_LITERAL = "3.x"
#: The workflow that builds the engine.exe he downloads. Only it, and the probe, check
#: for the newest patch; ci.yml keeps the runner's cached one because it is faster.
RELEASE_BUILD = "release-engine.yml"


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
    assert _takes_latest(probes[0]), (
        "without check-latest, '3.x' is the newest CPython the runner image has cached, "
        "not the newest released, and the probe reports 'on the newest' for months")


def _takes_latest(step: dict) -> bool:
    # Actions hands every input over as a string; setup-python reads true/True/TRUE alike.
    return str((step.get("with") or {}).get("check-latest")).lower() == "true"


def test_only_the_release_build_and_the_probe_check_for_the_newest_patch():
    """His ruling: the engine.exe he downloads takes the newest patch, and ci.yml and
    the rest keep the patch the runner has cached, which is faster."""
    steps = _setup_python_steps()
    release = [step for workflow, _job, step in steps if workflow == RELEASE_BUILD]
    assert release and all(_takes_latest(step) for step in release), (
        f"{RELEASE_BUILD} must set check-latest: true, or the engine.exe it ships "
        "carries whichever patch the runner happened to cache")
    latest = {workflow for workflow, _job, step in steps if _takes_latest(step)}
    assert latest == {RELEASE_BUILD, NEWEST_PROBE[0]}, (
        f"check-latest belongs to {RELEASE_BUILD} and the probe only, found it in {sorted(latest)}")


def _issue_body() -> str:
    doc = yaml.safe_load((WORKFLOWS / NEWEST_PROBE[0]).read_text(encoding="utf-8"))
    runs = [str(step.get("run") or "") for job in doc["jobs"].values()
            for step in job.get("steps") or []]
    filing = [run for run in runs if "gh issue create" in run]
    assert len(filing) == 1, f"expected one step that files the issue, found {len(filing)}"
    return filing[0]


def test_the_upgrade_issue_reaches_the_engine_he_runs():
    """Moving the pin moves CI and the release build, never his engine: it runs from
    source through a launcher that names its interpreter once, at registration. So the
    issue must name that step, and each name it cites must still be real — a renamed
    command would leave a checklist that sends the next upgrade to nothing."""
    body = _issue_body()
    for cited in ("scrapex/nativehost.py", "write_launcher", "install-native-host", "[ui]"):
        assert cited in body, f"the upgrade issue no longer names {cited!r}"
    assert callable(getattr(nativehost, "write_launcher", None))
    subcommands = next(action.choices for action in build_parser()._actions
                       if isinstance(action, argparse._SubParsersAction))
    assert "install-native-host" in subcommands
    assert "ui" in _pyproject()["project"]["optional-dependencies"]


def test_requires_python_is_the_pinned_version():
    major, minor = _pinned()
    assert _pyproject()["project"]["requires-python"] == f">={major}.{minor}"


def test_ruff_targets_the_pinned_version():
    major, minor = _pinned()
    assert _pyproject()["tool"]["ruff"]["target-version"] == f"py{major}{minor}"
