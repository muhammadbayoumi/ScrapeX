"""The two ways a linter stops being one, made into failures.

A gate is only a gate while somebody cannot get round it cheaply. There are
exactly two cheap ways round this one, and both are quiet:

1. Add the failing rule to `ignore` and move on. The list grows, nobody rereads
   it, and one day the gate passes because it checks nothing.
2. Let `ruff --fix` delete something it thinks is unused. That is not
   hypothetical here -- see the second test.

Neither is caught by running ruff, because in both cases ruff is happy. They are
caught here.
"""
from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def test_every_ruff_ignore_says_why():
    """An ignore with no reason is a rule someone turned off in a hurry.

    The reason has to be a comment ABOVE the code in pyproject.toml, because
    that is where the next person reads it -- not in a commit message they will
    never go looking for.
    """
    raw = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "ignore = [" in raw, "the ruff ignore list moved; this test must follow it"
    block = raw.split("ignore = [", 1)[1].split("\n]", 1)[0]

    undocumented, explained = [], False
    for line in block.splitlines():
        text = line.strip()
        if not text:
            continue
        if text.startswith("#"):
            explained = True
            continue
        if not explained:
            undocumented.append(text)
        explained = False

    assert not undocumented, (
        "these ruff ignores carry no comment saying why:\n  "
        + "\n  ".join(undocumented)
        + "\n\nAn ignore list nobody has to justify is how a gate becomes "
          "decoration. Say what the rule gets wrong here, or fix the code.")


def test_the_gate_actually_runs_on_the_code_that_ships():
    """CI must lint `scrapex/`. A gate pointed at nothing passes forever."""
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "ruff check scrapex/" in workflow, (
        "the CI lint step no longer runs ruff over scrapex/ — the gate is off")
    assert "pip install ruff==" in workflow, (
        "ruff is no longer pinned in CI: somebody else's release can now turn a "
        "branch red without a line of this repository changing")


def test_the_javascript_half_of_the_gate_runs_too():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "eslint@9." in workflow, "the eslint step is gone, or is no longer pinned"
    step = workflow.split("eslint@9.", 1)[1].splitlines()[0]
    for area in ("extension", "scrapex/webui/static", "contract", "apps_script"):
        assert area in step, (
            f"eslint no longer covers {area} — a whole area went quietly unlinted")


# MARKED ON THE TEST, not the module: only this one reads extension/ sources, so
# only this one has to run when a change touches nothing but the extension. The
# rest are about pyproject.toml and the workflow, and marking them too would put
# ruff's configuration inside a gate named for the panel.
@pytest.mark.extension
def test_the_javascript_gate_still_has_a_config_to_run_against():
    """eslint.config.mjs is TRACKED, and deleting it turns the gate into a
    crash rather than a pass — which sounds safe and is not.

    It happened. Testing the gate locally means copying the config into a
    worktree; cleaning up afterwards with `rm` deletes the tracked file, and
    `git add -A` commits the deletion. CI then fails with "ESLint couldn't find
    an eslint.config file" — an error about tooling, in a job whose failures are
    supposed to be about code, and the sort of red people learn to wave through.

    The other tests here read the workflow. This one reads the disk.
    """
    config = ROOT / "eslint.config.mjs"
    assert config.is_file(), (
        "eslint.config.mjs is gone, so the JavaScript half of the gate cannot "
        "run at all — it will fail as a tooling error rather than catch anything")
    text = config.read_text(encoding="utf-8")
    assert "no-undef" in text, (
        "the config no longer enables no-undef, which is the rule that found "
        "the undefined `el` in the panel")
    assert "export default" in text, "eslint.config.mjs exports no configuration"


def test_the_panel_defines_every_helper_it_calls():
    """The regression test for the defect that paid for the whole JavaScript gate.

    `el(...)` was called four times in renderSchemaLag and defined nowhere, from
    c4ea06b (2026-07-30) until the gate found it. The early return above those
    lines meant the normal case never reached them, so the panel looked fine —
    it threw ReferenceError only when the database really was behind the engine,
    which is the single situation that banner exists for.

    eslint's `no-undef` is the mechanism; this is the plain-language reminder of
    why, and it fails without needing node installed.
    """
    source = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")
    called = re.search(r"[^.\w]el\(", source) is not None
    # ANCHORED TO COLUMN ZERO, and the first version of this test was not --
    # it accepted `const el = $(id)`, a LOCAL inside an unrelated function 2600
    # lines away, and so it passed with the helper deleted. Only a definition at
    # module scope is in scope for renderSchemaLag.
    defined = re.search(r"^(const|let|var|function)\s+el\b", source, re.M) is not None
    assert not called or defined, (
        "extension/app.js calls el(...) and does not define it. That is a "
        "ReferenceError in renderSchemaLag, which runs from setStatus on every "
        "status update — and it fires exactly when the owner's database is "
        "behind the engine and he needs the banner most.")


@pytest.mark.parametrize("name", [
    "offer_price", "parse_product_jsonld", "sitemap_locs", "brand_name",
    "category_path",
])
def test_sallas_re_exports_survive_a_linter(name):
    """These five are imported by salla.py and used only OUTSIDE it.

    THIS IS NOT A HYPOTHETICAL. Adding the ruff gate ran `--fix` over the tree,
    F401 read four of these as unused imports, and deleted them -- straight
    through a comment two lines above that said, in words, that they are
    re-exported for salla's tests. tests/test_salla.py stopped importing at all.

    A comment cannot stop a fixer. `__all__` can, because the tool reads it, and
    this test fails if someone removes the name from either place.
    """
    from scrapex.connectors import salla

    assert hasattr(salla, name), (
        f"scrapex.connectors.salla.{name} is gone. It is re-exported on purpose: "
        "the salla tests and the jsonld family both read it from here. If a "
        "linter removed it, put it back and keep it in __all__.")
    assert name in salla.__all__, (
        f"{name} is importable but missing from salla.__all__, which is the only "
        "thing standing between it and the next `ruff --fix`")


def test_the_linter_is_actually_installed_and_clean_here():
    """Runs the gate itself, so a local failure is found locally.

    Skipped rather than failed when ruff is absent: a contributor who has not
    installed it has not broken anything, and a test that fails for a missing
    dev tool teaches people to ignore red.
    """
    try:
        found = subprocess.run([sys.executable, "-m", "ruff", "check", "scrapex/"],
                               cwd=str(ROOT), capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=300)
    except (OSError, subprocess.SubprocessError) as exc:      # pragma: no cover
        pytest.skip(f"ruff is not installed here ({exc})")
    if found.returncode == 1 and "No module named" in (found.stderr or ""):
        pytest.skip("ruff is not installed here")
    assert found.returncode == 0, (
        "ruff is failing on scrapex/ right now:\n" + (found.stdout or found.stderr))
