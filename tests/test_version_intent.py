"""A pull request's VERSION is compared with what its body says it is (#1086).

A rebase dropped #1042's VERSION commit on 2026-09-24 -- "dropping 6c2991b5 VERSION
0.4.17 ... patch contents already upstream", then "Successfully rebased" -- and every
version guard stayed green, because the branch then agreed with main. The body is
the one record a rebase cannot reach, so tools/version_intent.py reads the intent
there and .github/workflows/version-intent.yml runs it on every pull request.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scrapex.version import VERSION

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import version_intent as tool  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "version-intent.yml"
SCRIPT = ROOT / "tools" / "version_intent.py"


def _version_file(folder: Path, name: str, version: str) -> Path:
    path = folder / name
    path.write_text(f'VERSION = "{version}"\n', encoding="utf-8")
    return path


# ---- the line in the body --------------------------------------------------------

@pytest.mark.parametrize("body", [None, "", "No version talk here.\n",
                                  "VERSION 0.4.17, on his word\n",
                                  "- VERSION: 0.4.23\n",
                                  "It raises `VERSION: 0.4.23` somewhere mid-line.\n",
                                  "Version: 0.4.23\n"])
def test_a_body_without_a_declaration_means_unchanged(body):
    """Prose, a list item, inline code and the wrong case are not the line."""
    assert tool.declared(body) == tool.UNCHANGED


@pytest.mark.parametrize("body, expected", [
    ("VERSION: 0.4.23", "0.4.23"),
    ("Intro.\n\nVERSION: 0.4.23\n\nMore.", "0.4.23"),
    ("VERSION:0.4.23", "0.4.23"),
    ("VERSION: \t0.4.23 \t", "0.4.23"),
    ("Intro.\r\nVERSION: 0.4.23\r\nMore.\r\n", "0.4.23"),
    ("VERSION: unchanged", tool.UNCHANGED),
    ("VERSION: 0.4.23\nand again:\nVERSION: 0.4.23\n", "0.4.23"),
])
def test_the_declaration_is_read_at_the_start_of_a_line(body, expected):
    assert tool.declared(body) == expected


@pytest.mark.parametrize("fence", ["```", "~~~", "  ```text"])
def test_a_line_inside_a_code_block_is_an_example_not_a_declaration(fence):
    body = f"How to write it:\n{fence}\nVERSION: 9.9.9\n{fence}\nVERSION: 0.4.23\n"
    assert tool.declared(body) == "0.4.23"
    assert tool.declared(f"{fence}\nVERSION: 9.9.9\n{fence}\n") == tool.UNCHANGED


def test_two_declarations_that_disagree_are_refused_not_resolved():
    with pytest.raises(ValueError, match=r"more than once.*0\.4\.23, 0\.4\.24"):
        tool.declared("VERSION: 0.4.23\nVERSION: 0.4.24\n")
    with pytest.raises(ValueError, match="more than once"):
        tool.declared("VERSION: unchanged\nVERSION: 0.4.24\n")


@pytest.mark.parametrize("value", ["0.4", "0.4.23.1", "v0.4.23", "next", "Unchanged", "0.4.x"])
def test_a_declaration_that_is_not_a_version_is_refused_by_name(value):
    with pytest.raises(ValueError, match=f"VERSION: {value}"):
        tool.declared(f"VERSION: {value}\n")


# ---- the rule ----------------------------------------------------------------------

def test_unchanged_passes_only_while_the_branch_agrees_with_main():
    assert tool.problem(tool.UNCHANGED, "0.4.22", "0.4.22") == ""


def test_a_raise_the_body_does_not_mention_fails_and_names_the_line_to_add():
    sentence = tool.problem(tool.UNCHANGED, "0.4.23", "0.4.22")
    assert "`VERSION: 0.4.23`" in sentence
    assert "start of a line" in sentence


def test_a_branch_behind_mains_version_is_told_to_rebase():
    assert "Rebase onto main" in tool.problem(tool.UNCHANGED, "0.4.21", "0.4.22")


def test_a_declared_raise_that_is_on_the_branch_passes():
    assert tool.problem("0.4.23", "0.4.23", "0.4.22") == ""


def test_a_raise_the_rebase_dropped_fails_loudly():
    """#1086 exactly: the body still says 0.4.18, version.py has fallen back to main's."""
    sentence = tool.problem("0.4.18", "0.4.17", "0.4.17")
    assert "not on this branch" in sentence
    assert "#1086" in sentence
    assert "export-version" in sentence


def test_a_number_main_already_has_is_refused_even_when_the_branch_matches_it():
    """#1042's state after #1085 merged: it meant 0.4.17, and main had just reached 0.4.17."""
    sentence = tool.problem("0.4.17", "0.4.17", "0.4.17")
    assert "already at VERSION 0.4.17" in sentence
    assert "not a raise" in sentence


def test_a_declared_number_behind_main_is_refused():
    assert "not a raise" in tool.problem("0.4.17", "0.4.17", "0.4.22")


def test_a_body_and_a_file_that_disagree_are_told_to_agree():
    assert "make them agree" in tool.problem("0.4.24", "0.4.23", "0.4.22")


def test_versions_are_compared_as_numbers_not_as_text():
    """As text, 0.4.10 sorts before 0.4.9, and a real raise would read as a step back."""
    assert tool.problem("0.4.10", "0.4.10", "0.4.9") == ""
    assert "not a raise" in tool.problem("0.4.9", "0.4.9", "0.4.10")
    assert "`VERSION: 0.4.10`" in tool.problem(tool.UNCHANGED, "0.4.10", "0.4.9")


# ---- reading VERSION out of a copy of scrapex/version.py ----------------------------

def test_the_real_version_module_is_read_by_path():
    """The real file builds dataclasses under `from __future__ import annotations`,
    which needs the module in sys.modules while it runs -- the loader provides that."""
    assert tool.version_in(ROOT / "scrapex" / "version.py") == VERSION


def test_two_copies_read_one_after_the_other_do_not_bleed_into_each_other(tmp_path):
    first = _version_file(tmp_path, "a.py", "1.2.3")
    second = _version_file(tmp_path, "b.py", "4.5.6")
    assert (tool.version_in(first), tool.version_in(second)) == ("1.2.3", "4.5.6")
    assert not [name for name in sys.modules if name.startswith("_version_intent_copy_")]


def test_a_copy_with_no_version_string_is_refused(tmp_path):
    empty = tmp_path / "v.py"
    empty.write_text("OTHER = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no VERSION string"):
        tool.version_in(empty)


def test_a_copy_whose_version_is_malformed_is_refused(tmp_path):
    with pytest.raises(ValueError, match=r"MAJOR\.MINOR\.PATCH"):
        tool.version_in(_version_file(tmp_path, "v.py", "0.4"))


def test_a_missing_copy_is_an_error_not_a_pass(tmp_path):
    with pytest.raises(OSError):
        tool.version_in(tmp_path / "absent.py")


# ---- the command, as the workflow runs it -------------------------------------------

def test_the_command_exits_by_verdict(tmp_path, monkeypatch, capsys):
    head = _version_file(tmp_path, "head.py", "0.4.23")
    main = _version_file(tmp_path, "main.py", "0.4.22")
    argv = ["--head", str(head), "--main", str(main)]

    monkeypatch.setenv("PR_BODY", "VERSION: 0.4.23\n")
    assert tool.main(argv) == 0
    assert "consistent" in capsys.readouterr().out

    monkeypatch.setenv("PR_BODY", "Nothing declared.\n")
    assert tool.main(argv) == 1
    assert "`VERSION: 0.4.23`" in capsys.readouterr().err

    monkeypatch.setenv("PR_BODY", "VERSION: 0.4.23\nVERSION: 0.4.24\n")
    assert tool.main(argv) == 2
    assert "error: " in capsys.readouterr().err

    monkeypatch.delenv("PR_BODY")
    assert tool.main(["--head", str(tmp_path / "absent.py"), "--main", str(main)]) == 2
    assert "error: " in capsys.readouterr().err


def test_the_script_runs_standalone_from_any_directory(tmp_path):
    """The workflow calls it as a file, with nothing installed: it must find
    scrapex.version on its own."""
    head = _version_file(tmp_path, "head.py", "0.4.22")
    main = _version_file(tmp_path, "main.py", "0.4.22")
    done = subprocess.run(
        [sys.executable, str(SCRIPT), "--head", str(head), "--main", str(main)],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8",
        # A bare environment, as a runner step has: no PYTHONPATH to lean on.
        env={"PR_BODY": "", "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")})
    assert done.returncode == 0, done.stderr
    assert "consistent" in done.stdout


# ---- the workflow -------------------------------------------------------------------

def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_the_check_reruns_when_only_the_body_is_edited():
    data = _workflow()
    trigger = data.get("on", data.get(True))      # YAML 1.1 reads a bare `on` as True
    pull = trigger["pull_request"]
    assert set(pull["types"]) >= {"opened", "edited", "synchronize", "reopened"}
    assert pull["branches"] == ["main"]


def test_the_body_reaches_the_script_only_through_the_environment():
    steps = _workflow()["jobs"]["version-intent"]["steps"]
    for step in steps:
        assert "github.event.pull_request" not in step.get("run", ""), (
            f"step {step.get('name')!r} splices pull request text into a shell command")
    runner = next(step for step in steps if "tools/version_intent.py" in step.get("run", ""))
    assert runner["env"]["PR_BODY"] == "${{ github.event.pull_request.body }}"
    assert (ROOT / "tools" / "version_intent.py").is_file()


def test_the_job_can_read_and_cannot_write():
    data = _workflow()
    assert data["permissions"] == {"contents": "read"}
    checkout = next(step for step in data["jobs"]["version-intent"]["steps"]
                    if str(step.get("uses", "")).startswith("actions/checkout"))
    assert checkout["with"]["persist-credentials"] is False
