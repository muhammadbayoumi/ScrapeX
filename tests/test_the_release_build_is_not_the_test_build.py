"""The engine a person downloads must not carry what its tests needed.

THE DEFECT THIS EXISTS FOR, measured on 2026-08-10 against the published
engine-v0.2.1: `scrapex-engine.exe` is 67.6 MB, and from double-click to its
first character is 2.6-6.9 seconds on a warm machine — with `--version`, which
does nothing. A PyInstaller one-file binary opens its console immediately and
extracts the whole bundle BEFORE Python starts, so all of that is a black window
with no text. On a first run, with Defender inspecting a new unsigned 68 MB
executable, it is longer. The owner met it, concluded the engine was broken, and
closed it.

Nothing in this repository could have caught it. Every one of the ~2,200 tests
runs against the source tree; not one has ever started the built artifact. The
binary WORKS — it is simply enormous and slow to start, which no assertion about
behaviour will ever notice.

WHY IT WAS BIG. The release workflow installs `.[dev,browser,ui,local,commodity]`
and downloads Chromium, because the same job runs the whole suite and the panel
tests drive a real browser. PyInstaller then built in that same environment and
swept up pytest and the whole of Playwright — neither of which the shipped
engine calls. `packaging/build_engine.py` has documented the correct build all
along (`pip install -e ".[ui,local,commodity]" pyinstaller`); the workflow had
drifted from its own instructions.

AND WHAT TRIMMING DID NOT FIX, measured rather than assumed. Excluding the test
extras took the binary from 67.6 MB to 60.1 MB — eleven per cent, not the two
thirds the disk sizes suggested, because PyInstaller compresses and most of
Playwright's 105 MB is driver binaries it never bundles. Sixty megabytes still
unpacks in seconds. Size and silence are two separate problems: this file guards
the size, and `--splash` in packaging/build_engine.py answers the silence, by
drawing something from the bootloader while Python is still not running.

These tests read the workflow rather than building a binary: a build takes
minutes and needs PyInstaller, and what has to stay true is a property of the
recipe.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release-engine.yml"

#: Extras that exist for TESTING and must never reach a shipped binary.
TEST_ONLY_EXTRAS = ("dev", "browser")


@pytest.fixture(scope="module")
def workflow() -> str:
    assert WORKFLOW.is_file(), f"{WORKFLOW} is gone; this guard must follow it"
    return WORKFLOW.read_text(encoding="utf-8")


def test_the_build_step_does_not_inherit_the_test_environment(workflow):
    """The build must run somewhere the test extras are not installed.

    Not "the workflow must not install them" — it has to, the suite needs a real
    browser. The requirement is that the BUILD does not happen in that same
    environment, which is what put 105 MB of Playwright inside a 68 MB engine.
    """
    build = re.search(r"- name: Build\b(.*?)(?=\n      - name: )", workflow, re.S)
    assert build, "the Build step was renamed; this guard must follow it"
    body = build.group(1)

    assert "venv" in body or "--exclude-module" in body, (
        "the Build step runs in whatever environment the tests left behind. "
        "PyInstaller bundles what it finds, so pytest and Playwright ship "
        "inside the engine and every launch pays seconds of unpacking for "
        "code the engine never calls.")

    if "venv" in body:
        installed = re.search(r'pip install[^\n]*-e\s+"?\.\[([^\]]+)\]', body)
        assert installed, (
            "the build environment installs no extras at all, so the engine "
            "would ship without fastapi, openpyxl or pycountry")
        extras = {name.strip() for name in installed.group(1).split(",")}
        leaked = sorted(extras & set(TEST_ONLY_EXTRAS))
        assert not leaked, (
            f"the build environment installs {leaked}, which exist for the test "
            "suite. Playwright alone is 105 MB unpacked and the browser tier "
            "(M8) is not built, so it is weight paid for a feature that does "
            "not exist yet.")


def test_a_bloated_artifact_is_refused_before_it_is_published(workflow):
    """A size ceiling, because this defect is invisible any other way.

    The binary starts, answers `--version`, and passes every check a release
    makes of it. Only a person double-clicking it can tell that it is wrong, and
    by then it is published.
    """
    assert re.search(r"stat -c%s dist/scrapex-engine", workflow), (
        "nothing measures the artifact, so the build environment can leak into "
        "it again and the only symptom will be an owner waiting at a black "
        "window")
    ceiling = re.search(r'if \[ "\$bytes" -gt (\d+) \]', workflow)
    assert ceiling, "the size check does not compare against anything"
    limit = int(ceiling.group(1))
    assert limit < 67_600_000, (
        f"the ceiling is {limit / 1048576:.0f} MB, which the 68 MB build that "
        "shipped as 0.2.1 would have passed — a limit that admits the defect "
        "it was written for guards nothing")


def test_the_documented_build_and_the_shipped_build_agree(workflow):
    """packaging/build_engine.py's docstring is an instruction someone follows
    by hand. When the workflow disagrees with it, one of them is lying and there
    is no way to tell which from either file alone."""
    documented = (ROOT / "packaging" / "build_engine.py").read_text(encoding="utf-8")
    named = re.search(r'pip install -e "\.\[([^\]]+)\]"', documented)
    assert named, "build_engine.py no longer documents how to build it"
    intended = {name.strip() for name in named.group(1).split(",")}

    build = re.search(r"- name: Build\b(.*?)(?=\n      - name: )", workflow, re.S)
    actual = re.search(r'pip install[^\n]*-e\s+"?\.\[([^\]]+)\]', build.group(1))
    if actual is None:
        pytest.skip("the workflow builds without naming extras; nothing to compare")
    shipped = {name.strip() for name in actual.group(1).split(",")}

    assert shipped == intended, (
        f"packaging/build_engine.py says to build with {sorted(intended)} and "
        f"the release workflow uses {sorted(shipped)}. The workflow is what "
        "ships, so the documented command is the one nobody has run — and that "
        "drift is exactly how Playwright ended up inside the engine.")


def test_something_is_drawn_while_the_bootloader_unpacks():
    """THE ANSWER TO THE BLACK WINDOW, which trimming the bundle did not give.

    A one-file binary opens its console and extracts the bundle before any of
    our code runs, so nothing this repository writes can appear during it —
    measured at 2.6-6.9 seconds warm, longer on a first run. `--splash` is the
    only mechanism that can put anything on the screen in that window, because
    PyInstaller's own bootloader draws it.
    """
    build = (ROOT / "packaging" / "build_engine.py").read_text(encoding="utf-8")
    assert "--splash" in build, (
        "the build draws nothing during the unpack, so a person who "
        "double-clicks the engine sees a black window for several seconds and "
        "has no way to tell it from a broken download")
    assert (ROOT / "packaging" / "splash.png").is_file(), (
        "build_engine.py asks PyInstaller for a splash image that does not "
        "exist, which fails the build rather than the launch")

    entry = (ROOT / "packaging" / "engine_entry.py").read_text(encoding="utf-8")
    assert "pyi_splash" in entry, (
        "nothing closes the splash, so the image stays on top of the console "
        "while the engine reports what it is doing behind it")
