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
import time
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
                                  "It raises `VERSION: 0.4.23` somewhere mid-line.\n",
                                  "The version-intent check is advisory.\n",
                                  "| Version | Date |\n",
                                  "VERSIONS move rarely.\n",
                                  "version-intent: advisory until required\n",
                                  "Version history is in the CHANGELOG.\n"])
def test_a_body_without_a_declaration_means_unchanged(body):
    """Prose, a mid-line mention and a word that only begins with VERSION are not the line."""
    assert tool.declared(body) == tool.UNCHANGED


@pytest.mark.parametrize("body, expected", [
    ("VERSION: 0.4.23", "0.4.23"),
    ("Intro.\n\nVERSION: 0.4.23\n\nMore.", "0.4.23"),
    ("VERSION:0.4.23", "0.4.23"),
    ("VERSION: \t0.4.23 \t", "0.4.23"),
    ("Intro.\r\nVERSION: 0.4.23\r\nMore.\r\n", "0.4.23"),
    ("Intro.\rVERSION: 0.4.23\rMore.\r", "0.4.23"),
    ("\ufeffVERSION: 0.4.23\n\nThe body GitHub delivered started with a BOM.", "0.4.23"),
    ("VERSION: unchanged", tool.UNCHANGED),
    ("VERSION: 0.4.23\nand again:\nVERSION: 0.4.23\n", "0.4.23"),
])
def test_the_declaration_is_read_at_the_start_of_a_line(body, expected):
    assert tool.declared(body) == expected


def test_a_declaration_inside_a_code_block_still_counts():
    """A fence tracker failed open twice in review, so there is none: examples go mid-line."""
    assert tool.declared("```\nVERSION: 0.4.23\n```\n") == "0.4.23"
    with pytest.raises(ValueError, match="more than once"):
        tool.declared("```\nVERSION: 9.9.9\n```\nVERSION: 0.4.23\n")


@pytest.mark.parametrize("line", [
    "VERSION: 0.4.23      this pull request raises VERSION to 0.4.23",
    "VERSION: 0.4.23, on his word",
    "VERSION: 0.4.23 (raises)",
    "VERSION:",
    "VERSION:   ",
    "**VERSION: 0.4.23**",
    "> VERSION: 0.4.23",
    "## VERSION 0.4.23",
    "## VERSION 0.4.22, derived rather than reserved",
    "- VERSION: 0.4.23",
    "1. VERSION: 0.4.23",
    "`VERSION: 0.4.23`",
    "| VERSION: 0.4.23 |",
    "Version: 0.4.23",
    "version: 0.4.23",
    "  VERSION: 0.4.23",
    "\u00a0VERSION: 0.4.23",
    "VERSION 0.4.17, on his word",
    # Round 2 of the review: forms the first fix still read as unchanged.
    "+ VERSION: 0.4.23",
    "- [x] VERSION: 0.4.23",
    "- [ ] VERSION: 0.4.23",
    "* [X] VERSION: 0.4.23",
    "## Version 0.4.23",
    "Version 0.4.23",
    "**Version**: 0.4.23",
    "**Version** 0.4.23",
    "| Version | 0.4.23 |",
    "Version -> 0.4.23",
    "## Version 0.4.13 " + chr(0x2192) + " 0.4.14",        # #877's merged body, verbatim
    "**1 " + chr(0xB7) + " `VERSION` moves because the contract moved**",   # #799's
    *(chr(code) + "VERSION: 0.4.23"
      for code in (0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0xAD)),
    "<b>VERSION: 0.4.23</b>",
    "<!-- --> VERSION: 0.4.23",
    "<details><summary>VERSION: 0.4.23</summary>",
    "[VERSION: 0.4.23](x)",
    "\\VERSION: 0.4.23",
    chr(0x2022) + " VERSION: 0.4.23",
    # ...and forms the first fix caught but no test held.
    "~~VERSION: 0.4.23~~",
    "__VERSION: 0.4.23__",
    "_VERSION: 0.4.23_",
    "1) VERSION: 0.4.23",
    "`VERSION`: 0.4.23",
    "Version : 0.4.23",
    "Version: v0.4.23",
    "Version0.4.23",
    "**Version**: v0.4.23",
    "Version : unchanged",
])
def test_a_line_that_looks_like_a_declaration_is_refused_never_read_as_unchanged(line):
    """Read as unchanged, each of these passes the exact #1086 state: the raise gone,
    the body still claiming it. So each is refused, and the refusal quotes it."""
    for body in (f"{line}\n", f"Intro.\n\n{line}\n", f"VERSION: 0.4.23\n{line}\n"):
        with pytest.raises(ValueError, match="names VERSION but is not a declaration") as err:
            tool.declared(body)
        assert repr(line[:80]) in str(err.value)


# Short ids: pytest copies a test's id into an environment variable, and Windows caps
# one at 32,767 characters.
@pytest.mark.parametrize("line", ["<>" * 20000 + "a", "[ ]" * 20000 + "a", "<" * 60000,
                                  "[x]" * 20000 + "a", "-" * 60000 + "Version"],
                         ids=["tags", "empty-boxes", "open-angles", "ticked-boxes", "dashes"])
def test_a_hostile_line_is_read_in_linear_time(line):
    """The body is text the author writes. The first candidate pattern for the prefix
    backtracked exponentially on '<>' repeated (0.7 s at 22 repeats, doubling each
    one), so a short line could outlast the job's timeout. The possessive prefix reads
    each of these 40-60 thousand character lines in milliseconds."""
    started = time.perf_counter()
    try:
        tool.declared(line)
    except ValueError:
        pass
    assert time.perf_counter() - started < 1.0


def test_a_byte_order_mark_anywhere_but_the_start_is_refused_and_shown():
    with pytest.raises(ValueError, match=r"\\ufeffVERSION"):
        tool.declared("Intro.\n\ufeffVERSION: 0.4.23\n")


def test_two_declarations_that_disagree_are_refused_not_resolved():
    with pytest.raises(ValueError, match=r"more than once.*0\.4\.23, 0\.4\.24"):
        tool.declared("VERSION: 0.4.23\nVERSION: 0.4.24\n")
    with pytest.raises(ValueError, match="more than once"):
        tool.declared("VERSION: unchanged\nVERSION: 0.4.24\n")


@pytest.mark.parametrize("value", ["0.4", "0.4.23.1", "v0.4.23", "next", "Unchanged", "0.4.x",
                                   "0.4.23,"])
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


@pytest.mark.parametrize("declaration, head", [("0.4.24", "0.4.23"), ("0.4.23", "0.4.24")])
def test_a_body_and_a_file_that_disagree_are_told_to_agree(declaration, head):
    """Both directions: the file behind the body, and the file ahead of it."""
    assert "make them agree" in tool.problem(declaration, head, "0.4.22")


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


def _run_script(tmp_path, body, head_version, main_version):
    """The script as the workflow's last step runs it: a file, from elsewhere, with no
    site-packages (-S) and a bare environment, so nothing installed can stand in for
    the sys.path line that finds scrapex.version."""
    head = _version_file(tmp_path, "head.py", head_version)
    main = _version_file(tmp_path, "main.py", main_version)
    return subprocess.run(
        [sys.executable, "-S", str(SCRIPT), "--head", str(head), "--main", str(main)],
        cwd=tmp_path, capture_output=True, text=True, encoding="utf-8",
        env={"PR_BODY": body, "SYSTEMROOT": os.environ.get("SYSTEMROOT", "")})


def test_the_premise_nothing_installed_is_importable_under_dash_s(tmp_path):
    """Without this, the standalone runs below could pass on an editable install of
    scrapex and prove nothing about the script finding it by itself."""
    probe = subprocess.run([sys.executable, "-S", "-c", "import scrapex"], cwd=tmp_path,
                           capture_output=True, text=True,
                           env={"SYSTEMROOT": os.environ.get("SYSTEMROOT", "")})
    assert probe.returncode != 0 and "ModuleNotFoundError" in probe.stderr, probe.stderr


@pytest.mark.parametrize("body, head, main, code, says", [
    ("", "0.4.22", "0.4.22", 0, "consistent"),
    ("VERSION: 0.4.23\n", "0.4.23", "0.4.22", 0, "consistent"),
    ("VERSION: 0.4.23\n", "0.4.22", "0.4.22", 1, "not on this branch"),
    ("", "0.4.23", "0.4.22", 1, "`VERSION: 0.4.23`"),
    ("VERSION: 0.4.22\n", "0.4.22", "0.4.22", 1, "not a raise"),
    ("VERSION: 0.4.23\nVERSION: 0.4.24\n", "0.4.23", "0.4.22", 2, "error: "),
    ("## VERSION 0.4.23\n", "0.4.22", "0.4.22", 2, "names VERSION"),
])
def test_the_script_exits_by_verdict_as_github_reads_it(tmp_path, body, head, main, code, says):
    """The exit status is the check's only output GitHub reads. main() returning the
    right number proves nothing if the file stops passing it to sys.exit."""
    done = _run_script(tmp_path, body, head, main)
    assert done.returncode == code, (done.stdout, done.stderr)
    assert says in (done.stdout if code == 0 else done.stderr)


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


def test_how_the_two_versions_and_the_verdict_travel_is_pinned():
    """Five one-line edits each passed every other test here, and each turned verdicts
    green or wrong: main's copy taken from the branch, HEAD read instead of FETCH_HEAD,
    --head and --main swapped, `|| true`, and continue-on-error."""
    data = _workflow()
    steps = data["jobs"]["version-intent"]["steps"]
    fetch = next(step for step in steps if "FETCH_HEAD" in step.get("run", ""))
    assert [line.strip() for line in fetch["run"].strip().splitlines()] == [
        "set -euo pipefail",
        "git fetch --no-tags --depth=1 origin main",
        'git show FETCH_HEAD:scrapex/version.py > "$RUNNER_TEMP/main-version.py"',
    ]
    runner = next(step for step in steps if "tools/version_intent.py" in step.get("run", ""))
    assert runner["run"].strip() == (
        'python tools/version_intent.py --head scrapex/version.py '
        '--main "$RUNNER_TEMP/main-version.py"')
    for where in (data, *data["jobs"].values(), *steps):
        assert "continue-on-error" not in where, "a failing verdict must fail the job"


def test_the_job_is_exactly_its_four_steps_and_nothing_can_skip_them():
    """An `if:` on the verdict step or on the job skips it, and a skipped job reports
    success to a required check; an extra step can overwrite main's copy. Pinning the
    keys of the job and of each step, and the step count, leaves no room for either."""
    job = _workflow()["jobs"]["version-intent"]
    assert set(job) == {"runs-on", "steps"}
    assert [set(step) for step in job["steps"]] == [
        {"uses", "with"},              # checkout
        {"uses", "with"},              # setup-python
        {"name", "run"},               # read main's VERSION
        {"name", "env", "run"},        # the verdict
    ]
    assert [str(step.get("uses", "")).split("@")[0] for step in job["steps"][:2]] == [
        "actions/checkout", "actions/setup-python"]


def test_the_job_can_read_and_cannot_write():
    data = _workflow()
    assert data["permissions"] == {"contents": "read"}
    for name, job in data["jobs"].items():
        # A job-level block overrides the workflow's, so it may only repeat it.
        assert job.get("permissions", {"contents": "read"}) == {"contents": "read"}, name
    checkout = next(step for step in data["jobs"]["version-intent"]["steps"]
                    if str(step.get("uses", "")).startswith("actions/checkout"))
    assert checkout["with"]["persist-credentials"] is False
