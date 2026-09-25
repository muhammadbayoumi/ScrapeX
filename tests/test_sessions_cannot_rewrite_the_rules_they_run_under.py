"""A session cannot rewrite the rules it runs under with the commands it writes.

Ruleset 23994761 on main has an empty bypass list, so a push that breaks the rules
is refused. That does not stop the same account rewriting the rules: every session
acts as the repository's only admin, through a token with the repo and workflow
scopes, so any session could delete the ruleset, change the visibility or another
setting, disable a workflow or change a secret. Those are his decisions, and
`.claude/settings.json` denies them to both shell tools. This file keeps the list
honest in both directions: every write in the tables below is refused, and the reads
that verify protection are not.

A FIRST LAYER, NOT A WALL. Claude Code matches a Bash or PowerShell rule against the
command text a session writes, and its documentation says so itself: a rule for
`git push` does not stop `git -C . push`. Anything that is not the `gh` command line
-- curl against the API, `sh -c`, gh by its full path, the web UI -- passes these
rules. What they stop is the spelling a session actually produces, before it runs.

WHY A MATCHER LIVES IN THIS FILE. A rule list is only as good as what it matches.
`_refusing` models Claude Code's matcher as
https://code.claude.com/docs/en/permissions documents it: `*` stands for any text,
spaces included; the rule must match the whole command; a trailing ` *` that is the
rule's only wildcard also matches the bare command, and `:*` at the end means the
same; a compound command is split on its separators and a deny rule applies when any
part matches, the body of a `$(...)` included; Bash strips a fixed set of wrappers
and any leading variable assignment first; PowerShell matches case-insensitively. It
is a model of Claude Code's matcher, not Claude Code itself.
`test_the_model_agrees_with_the_documented_examples` holds it to the documentation's
own examples, so a model that drifted would fail before it could vouch for a rule.

RECORDING STAYS OPEN. He remembers how a problem was solved by the issue that
recorded it. A rule that refused `gh issue create`, a comment, or the API call that
posts one would take that away, so those are in a table of their own below.

The `docs` mark is not decoration. CI counts every path under `.claude/` as
documentation, so a change to the settings alone runs only `-m docs`. Without the
mark, the guard would not run on a change to the very file it guards.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.docs

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / ".claude" / "settings.json"
TOOLS = ("Bash", "PowerShell")
RULE = re.compile(r"(?P<tool>Bash|PowerShell)\((?P<spec>.+)\)", re.DOTALL)

# The hooks block exactly as #1126 wired it. The deny list was added beside it and
# must not have touched it; a deliberate change to the hook edits this pin with it.
HOOKS = {
    "PreToolUse": [
        {
            "matcher": "Bash",
            "hooks": [
                {
                    "type": "command",
                    "command": "python",
                    "args": [
                        "-c",
                        "import os, runpy, sys; path = sys.argv[1]; os.path.isfile(path) or sys.exit('refuse_long_bash: hook script missing at ' + path + '; this Bash call runs unchecked'); sys.argv = [path]; runpy.run_path(path, run_name='__main__')",
                        "${CLAUDE_PROJECT_DIR}/.claude/hooks/refuse_long_bash.py",
                    ],
                    "timeout": 10,
                }
            ],
        }
    ]
}


# ---------------------------------------------------------------------------
# The model of Claude Code's matcher.
# ---------------------------------------------------------------------------

SEPARATORS = {
    "Bash": ("&&", "||", "|&", ";", "|", "&", "\n"),
    # PowerShell splits on pipelines, statements and (7+) chains. A lone `&` is its
    # call operator, not a separator.
    "PowerShell": ("&&", "||", ";", "|", "\n"),
}

# What Bash strips before matching. A deny rule matches past ANY leading assignment,
# not only the known-safe ones an allow rule tolerates. `timeout` is modelled with its
# flags and a numeric duration, which is every spelling the tables use.
STRIPPED = [
    re.compile(r"[A-Za-z_]\w*=(?:\$\([^)]*\)|'[^']*'|\"[^\"]*\"|\S*)\s+"),
    re.compile(r"(?:time|nohup|builtin|noglob)\s+"),
    re.compile(r"command\s+(?!-[vV]\b)"),
    re.compile(r"timeout\s+(?:-\S+\s+)*\d\S*\s+"),
    re.compile(r"nice\s+(?:-n\s+\S+\s+|-\d+\s+)?"),
    re.compile(r"stdbuf\s+(?:-\S+\s+)+"),
    re.compile(r"xargs\s+(?!-)"),
]


def _closing(text: str, start: int) -> int:
    depth = 1
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    raise AssertionError(f"unbalanced $( in a table command: {text!r}")


def _subcommands(command: str, tool: str) -> list[str]:
    """Split on separators outside quotes, and add the body of every `$(...)`."""
    parts: list[str] = []
    nested: list[str] = []
    start, i, quote = 0, 0, None
    while i < len(command):
        ch = command[i]
        if quote == "'":
            if ch == "'":
                quote = None
        elif command.startswith("$(", i):
            end = _closing(command, i + 2)
            nested += _subcommands(command[i + 2:end], tool)
            i = end + 1
            continue
        elif quote == '"':
            if ch == '"':
                quote = None
        elif ch in "'\"":
            quote = ch
        else:
            sep = next((s for s in SEPARATORS[tool] if command.startswith(s, i)), None)
            if sep == "&" and (command[i - 1:i] in ("<", ">") or command[i + 1:i + 2] == ">"):
                sep = None  # `2>&1` and `&>file` redirect; they do not background
            if sep:
                parts.append(command[start:i])
                i += len(sep)
                start = i
                continue
        i += 1
    assert quote is None, f"unterminated {quote} in a table command: {command!r}"
    parts.append(command[start:])
    return [p.strip() for p in parts if p.strip()] + nested


def _unwrapped(command: str, tool: str) -> str:
    if tool != "Bash":
        return command
    while True:
        for pattern in STRIPPED:
            found = pattern.match(command)
            if found:
                command = command[found.end():]
                break
        else:
            return command


def _matches(tool: str, spec: str, command: str, ignore_case: bool) -> bool:
    if spec.endswith(":*"):
        spec = spec[:-2] + " *"
    flags = re.DOTALL | (re.IGNORECASE if ignore_case or tool == "PowerShell" else 0)
    if re.fullmatch(".*".join(re.escape(piece) for piece in spec.split("*")), command, flags):
        return True
    if spec.endswith(" *") and spec.count("*") == 1:
        return re.fullmatch(re.escape(spec[:-2]), command, flags) is not None
    return False


def _refusing(tool: str, command: str, rules: list[str], *,
              ignore_case: bool = False) -> list[str]:
    """Every rule for `tool` that refuses `command`."""
    parts = [_unwrapped(part, tool) for part in _subcommands(command, tool)]
    refusing = []
    for rule in rules:
        parsed = RULE.fullmatch(rule)
        if parsed and parsed["tool"] == tool and any(
                _matches(tool, parsed["spec"], part, ignore_case) for part in parts):
            refusing.append(rule)
    return refusing


# The examples https://code.claude.com/docs/en/permissions gives, as (tool, rule
# specifier, command, refused?): the wildcard table, the `:*` suffix, compound
# commands, wrappers, and what a rule does not match. PowerShell aliases are not
# modelled; no alias names gh.
DOCUMENTED = [
    ("Bash", "npm run build", "npm run build", True),
    ("Bash", "npm run build", "npm run build --watch", False),
    ("Bash", "npm run *", "npm run build", True),
    ("Bash", "npm run *", "npm run test --watch", True),
    ("Bash", "npm run *", "npm run", True),
    ("Bash", "npm run *", "npm install", False),
    ("Bash", "git log * main", "git log --oneline main", True),
    ("Bash", "git log * main", "git log -5 main", True),
    ("Bash", "git log * main", "git log --output=<file> main", True),
    ("Bash", "git log * main", "git log main", False),
    ("Bash", "git log * main", "git push origin main", False),
    ("Bash", "git * main", "git merge main", True),
    ("Bash", "git * main", "git push origin main", True),
    ("Bash", "git * main", "git -c core.fsmonitor=<script> diff main", True),
    ("Bash", "git * main", "git log", False),
    ("Bash", "* --version", "node --version", True),
    ("Bash", "* --version", "bash -c 'echo hi' --version", True),
    ("Bash", "* --version", "node -v", False),
    ("Bash", "ls *", "ls -la", True),
    ("Bash", "ls *", "ls", True),
    ("Bash", "ls *", "lsof", False),
    ("Bash", "ls*", "ls -la", True),
    ("Bash", "ls*", "lsof", True),
    ("Bash", "* --help *", "npm --help x", True),
    ("Bash", "* --help *", "npm --help", False),
    ("Bash", "ls:*", "ls -la", True),
    ("Bash", "ls:*", "ls", True),
    ("Bash", "ls:*", "lsof", False),
    ("Bash", "git:* push", "git push", False),
    ("Bash", "git push *", "git push origin main", True),
    ("Bash", "git clean *", "cd /tmp && git clean -f", True),
    ("Bash", "git clean *", 'echo "$(git clean -f)"', True),
    ("Bash", "npm test *", "timeout 30 npm test", True),
    ("Bash", "npm test *", "NODE_ENV=test npm test", True),
    ("Bash", "rm *", "FOO=bar rm -rf tmp/", True),
    ("Bash", "grep *", "xargs grep pattern", True),
    ("Bash", "grep *", "xargs -n1 grep pattern", False),
    ("Bash", "curl *", "curl https://example.com", True),
    ("Bash", "curl *", "/usr/bin/curl https://example.com", False),
    ("Bash", "curl *", "sh -c 'curl https://example.com'", False),
    ("Bash", "rm *", "bash -c 'rm -rf build/'", False),
    ("Bash", "git push *", "git -C . push origin main", False),
    ("Bash", "git push *", "git -c push.default=current push origin main", False),
    ("Bash", "git push *", "git 'push' origin main", False),
    ("PowerShell", "Remove-Item *", "Remove-Item C:\\tmp\\x", True),
    ("PowerShell", "Remove-Item *", "remove-item C:\\tmp\\x", True),
    ("PowerShell", "Remove-Item *", "Get-Date; Remove-Item C:\\tmp\\x", True),
    ("PowerShell", "Remove-Item *", "Get-ChildItem | Remove-Item", True),
    ("PowerShell", "Remove-Item *", "Get-Date && Remove-Item C:\\tmp\\x", True),
    ("PowerShell", "Remove-Item *", "Get-ChildItem C:\\tmp", False),
]


@pytest.mark.parametrize(("tool", "spec", "command", "refused"), DOCUMENTED)
def test_the_model_agrees_with_the_documented_examples(tool, spec, command, refused):
    assert bool(_refusing(tool, command, [f"{tool}({spec})"])) is refused


# ---------------------------------------------------------------------------
# What the settings hold.
# ---------------------------------------------------------------------------


def _settings() -> dict:
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    assert isinstance(settings, dict), settings
    return settings


def _deny() -> list[str]:
    permissions = _settings().get("permissions")
    assert isinstance(permissions, dict), f"expected a permissions object, found {permissions!r}"
    deny = permissions.get("deny")
    assert isinstance(deny, list) and deny, f"expected a non-empty deny list, found {deny!r}"
    assert all(isinstance(rule, str) for rule in deny), deny
    return deny


def test_the_settings_file_is_strict_json_with_a_deny_list():
    """Claude Code skips a settings file that is not strict JSON
    (https://code.claude.com/docs/en/settings), and with it this list and the hook
    beside it."""
    assert _deny()


def test_the_hooks_block_is_exactly_what_it_was():
    assert _settings().get("hooks") == HOOKS


def test_every_deny_entry_is_a_scoped_gh_rule_and_both_shells_hold_the_same_list():
    specs: dict[str, list[str]] = {tool: [] for tool in TOOLS}
    for rule in _deny():
        parsed = RULE.fullmatch(rule)
        assert parsed, f"{rule!r} is not Bash(...) or PowerShell(...)"
        spec = parsed["spec"]
        assert spec == spec.strip(), f"{rule!r}: whitespace at an edge is part of the pattern"
        assert spec.strip("*"), f"{rule!r} would remove the whole {parsed['tool']} tool"
        assert spec.startswith("gh "), (
            f"{rule!r} must name the gh program first, or it can refuse a command that is not gh")
        assert ":*" not in spec[:-2], (
            f"{rule!r}: `:*` is only a wildcard at the end; anywhere else the colon is literal")
        specs[parsed["tool"]].append(spec)
    for tool, listed in specs.items():
        assert len(listed) == len(set(listed)), f"a {tool} rule is listed twice"
    assert set(specs["Bash"]) == set(specs["PowerShell"]), (
        "a write refused in one shell must be refused in the other; "
        f"Bash only: {set(specs['Bash']) - set(specs['PowerShell'])}, "
        f"PowerShell only: {set(specs['PowerShell']) - set(specs['Bash'])}")


# ---------------------------------------------------------------------------
# The writes. Every one is a gh command line valid in both shells, so each is
# checked against both; the shell-specific spellings follow.
# ---------------------------------------------------------------------------

WRITES = [
    # The ruleset, through the REST API: -X/--method before or after the path.
    "gh api -X DELETE repos/muhammadbayoumi/ScrapeX/rulesets/23994761",
    "gh api repos/muhammadbayoumi/ScrapeX/rulesets/23994761 -X DELETE",
    "gh api -XDELETE repos/muhammadbayoumi/ScrapeX/rulesets/23994761",
    "gh api -X=DELETE /repos/muhammadbayoumi/ScrapeX/rulesets/23994761",
    "gh api --method DELETE repos/muhammadbayoumi/ScrapeX/rulesets/23994761",
    "gh api repos/{owner}/{repo}/rulesets/23994761 --method=DELETE",
    "gh api https://api.github.com/repos/muhammadbayoumi/ScrapeX/rulesets/23994761 -X DELETE",
    "gh api -X DELETE 'repos/{owner}/{repo}/rulesets/23994761'",
    "gh api -X DELETE repos/:owner/:repo/rulesets/23994761",
    "gh api -X PUT repos/muhammadbayoumi/ScrapeX/rulesets/23994761 --input ruleset.json",
    "gh api repos/muhammadbayoumi/ScrapeX/rulesets/23994761 --method PUT -F enforcement=disabled",
    "gh api -X PATCH repos/muhammadbayoumi/ScrapeX/rulesets/23994761 -f enforcement=evaluate",
    "gh api --method POST repos/muhammadbayoumi/ScrapeX/rulesets --input loose.json",
    # -f/-F/--field/--raw-field/--input with no method: gh sends a POST.
    "gh api repos/{owner}/{repo}/rulesets --input file.json",
    "gh api repos/muhammadbayoumi/ScrapeX/rulesets -f name=loose -f enforcement=disabled",
    "gh api -f enforcement=disabled repos/muhammadbayoumi/ScrapeX/rulesets/23994761",
    "gh api repos/muhammadbayoumi/ScrapeX/rulesets/23994761 -fenforcement=disabled",
    "gh api -F enforcement=disabled repos/muhammadbayoumi/ScrapeX/rulesets/23994761",
    "gh api --field enforcement=disabled repos/muhammadbayoumi/ScrapeX/rulesets/23994761",
    "gh api repos/muhammadbayoumi/ScrapeX/rulesets/23994761 --field=enforcement=disabled",
    "gh api --raw-field enforcement=disabled repos/muhammadbayoumi/ScrapeX/rulesets/23994761",
    "gh api repos/muhammadbayoumi/ScrapeX/rulesets/23994761 --raw-field enforcement=disabled",
    "gh api --input - repos/muhammadbayoumi/ScrapeX/rulesets/23994761",
    "echo '{}' | gh api -X PUT repos/muhammadbayoumi/ScrapeX/rulesets/23994761 --input -",
    # The ruleset, through a GraphQL mutation.
    "gh api graphql -f query='mutation { deleteRepositoryRuleset(input: {repositoryRulesetId: \"RRS_1\"}) { clientMutationId } }'",
    "gh api graphql -F rid=RRS_1 -f query='mutation($rid: ID!) { updateRepositoryRuleset(input: {repositoryRulesetId: $rid, enforcement: DISABLED}) { clientMutationId } }'",
    "gh api graphql -f query='mutation { createRepositoryRuleset(input: {sourceId: \"R_1\", name: \"loose\", enforcement: ACTIVE, rules: []}) { clientMutationId } }'",
    # The repository object itself, PATCH or DELETE, by name and by both of gh's
    # placeholder spellings (`:owner/:repo` is the one .claude/skills/record-it
    # uses), bare, single-quoted (what gh's help asks PowerShell for around `{...}`)
    # or double-quoted, with the method flag before or after the path.
    "gh api -X DELETE repos/muhammadbayoumi/ScrapeX",
    "gh api -X PATCH repos/muhammadbayoumi/ScrapeX -f visibility=private",
    "gh api -X PATCH 'repos/muhammadbayoumi/ScrapeX' -F private=true",
    'gh api -X DELETE "/repos/muhammadbayoumi/ScrapeX"',
    "gh api repos/muhammadbayoumi/ScrapeX -X PATCH -f default_branch=loose",
    "gh api 'repos/muhammadbayoumi/ScrapeX' -XDELETE",
    'gh api "repos/muhammadbayoumi/ScrapeX" -X PATCH --input settings.json',
    "gh api --method DELETE /repos/muhammadbayoumi/ScrapeX",
    "gh api --method PATCH repos/muhammadbayoumi/ScrapeX --input settings.json",
    "gh api --method=PATCH 'repos/muhammadbayoumi/ScrapeX' -f has_issues=false",
    'gh api --method DELETE "repos/muhammadbayoumi/ScrapeX"',
    "gh api repos/muhammadbayoumi/ScrapeX --method DELETE",
    "gh api 'repos/muhammadbayoumi/ScrapeX' --method PATCH -f archived=true",
    'gh api "https://api.github.com/repos/muhammadbayoumi/ScrapeX" --method=DELETE',
    "gh api -X DELETE repos/muhammadbayoumi/ScrapeX 2>&1",
    "gh api -X DELETE repos/{owner}/{repo}",
    "gh api -X PATCH repos/{owner}/{repo} -F allow_auto_merge=false",
    "gh api -X PATCH 'repos/{owner}/{repo}' -f visibility=private",
    'gh api -X DELETE "repos/{owner}/{repo}"',
    "gh api repos/{owner}/{repo} -X DELETE",
    "gh api 'repos/{owner}/{repo}' -X PATCH -f default_branch=loose",
    'gh api "repos/{owner}/{repo}" -X=PATCH -f visibility=private',
    "gh api --method DELETE repos/{owner}/{repo}",
    "gh api --method PATCH repos/{owner}/{repo} -f has_wiki=false",
    "gh api --method DELETE 'repos/{owner}/{repo}'",
    'gh api --method=PATCH "repos/{owner}/{repo}" -F private=true',
    "gh api repos/{owner}/{repo} --method=PATCH -f default_branch=loose",
    "gh api 'repos/{owner}/{repo}' --method DELETE",
    'gh api "repos/{owner}/{repo}" --method PATCH -f visibility=private',
    "gh api -X DELETE repos/:owner/:repo",
    "gh api -X PATCH repos/:owner/:repo -f visibility=private",
    "gh api -X PATCH 'repos/:owner/:repo' -f default_branch=loose",
    'gh api -X DELETE "repos/:owner/:repo"',
    "gh api repos/:owner/:repo -X PATCH -F private=true",
    "gh api 'repos/:owner/:repo' -X DELETE",
    'gh api "repos/:owner/:repo" -XPATCH -f visibility=private',
    "gh api --method DELETE repos/:owner/:repo",
    "gh api --method=PATCH repos/:owner/:repo -f has_projects=false",
    "gh api --method PATCH 'repos/:owner/:repo' --input settings.json",
    'gh api --method DELETE "repos/:owner/:repo"',
    "gh api repos/:owner/:repo --method PATCH -f visibility=private",
    "gh api 'repos/:owner/:repo' --method=DELETE",
    'gh api "repos/:owner/:repo" --method PATCH -F private=true',
    # The gh commands that change the repository, its workflows, secrets and variables.
    "gh repo edit --visibility private --accept-visibility-change-consequences",
    "gh repo edit muhammadbayoumi/ScrapeX --default-branch loose",
    "gh repo edit",
    "gh repo delete muhammadbayoumi/ScrapeX --yes",
    "gh repo archive --yes",
    "gh repo archive",
    "gh repo rename ScrapeY --yes",
    "gh workflow disable ci.yml",
    "gh workflow disable CI --repo muhammadbayoumi/ScrapeX",
    "gh secret set SHEET_KEY --body value",
    "gh secret delete SHEET_KEY",
    "gh secret remove SHEET_KEY --repo muhammadbayoumi/ScrapeX",
    "gh variable set SCOPE --body docs",
    "gh variable delete SCOPE",
    "gh variable remove SCOPE",
]

BASH_WRITES = [
    # The prefix every session here puts in front of gh, in both of its forms.
    "export GH_TOKEN=$(gh auth token --user muhammadbayoumi) && gh api -X DELETE repos/muhammadbayoumi/ScrapeX/rulesets/23994761",
    "GH_TOKEN=$(gh auth token --user muhammadbayoumi) gh repo edit --visibility private --accept-visibility-change-consequences",
    "timeout 60 gh api -X DELETE repos/muhammadbayoumi/ScrapeX/rulesets/23994761",
    "nohup gh workflow disable ci.yml",
    "command gh secret delete SHEET_KEY",
    "git status; gh repo archive --yes",
    "cd /c/Users/sapac/Desktop/Claude/ScrapeX && gh api --method PATCH repos/muhammadbayoumi/ScrapeX -f visibility=private",
    "true || gh repo delete muhammadbayoumi/ScrapeX --yes",
    "gh api repos/muhammadbayoumi/ScrapeX/rulesets > before.json\ngh api -X DELETE repos/muhammadbayoumi/ScrapeX/rulesets/23994761",
    'echo "$(gh repo delete muhammadbayoumi/ScrapeX --yes)"',
    "gh secret set SHEET_KEY < key.txt",
    "cat ruleset.json | gh api -X PUT repos/{owner}/{repo}/rulesets/23994761 --input -",
    "gh api -X DELETE repos/muhammadbayoumi/ScrapeX 2>&1 | tail -5",
]

POWERSHELL_WRITES = [
    "$env:GH_TOKEN = (gh auth token --user muhammadbayoumi); gh api -X DELETE repos/muhammadbayoumi/ScrapeX/rulesets/23994761",
    "gh api -x delete repos/muhammadbayoumi/ScrapeX/rulesets/23994761",
    "Get-Content ruleset.json | gh api --method put repos/muhammadbayoumi/ScrapeX/rulesets/23994761 --input -",
    "Set-Location C:\\Users\\sapac\\Desktop\\Claude\\ScrapeX; gh repo edit --visibility private --accept-visibility-change-consequences",
    "git status && gh secret set SHEET_KEY --body value",
]

WRITES_BY_TOOL = {"Bash": WRITES + BASH_WRITES, "PowerShell": WRITES + POWERSHELL_WRITES}


@pytest.mark.parametrize(("tool", "command"), [
    (tool, command) for tool, commands in WRITES_BY_TOOL.items() for command in commands])
def test_every_write_to_his_decisions_is_refused(tool, command):
    assert _refusing(tool, command, _deny()), f"no {tool} rule refuses: {command}"


@pytest.mark.parametrize("tool", TOOLS)
def test_every_rule_refuses_at_least_one_write_in_the_table(tool):
    """A rule no write exercises is a rule nobody has checked matches anything."""
    unused = [rule for rule in _deny() if rule.startswith(f"{tool}(") and not any(
        rule in _refusing(tool, command, [rule]) for command in WRITES_BY_TOOL[tool])]
    assert not unused, f"add a write that each of these refuses: {unused}"


# ---------------------------------------------------------------------------
# What stays open. Checked against both shells' rules and without regard to case,
# which is stricter than Claude Code is for Bash.
# ---------------------------------------------------------------------------

READS = [
    # The four calls that verify protection, exactly as they are used.
    "gh api repos/muhammadbayoumi/ScrapeX/rulesets",
    "gh api repos/muhammadbayoumi/ScrapeX/rulesets/23994761",
    "gh api repos/muhammadbayoumi/ScrapeX/rules/branches/main",
    "gh api repos/muhammadbayoumi/ScrapeX",
    # The same, in the other ways they get written.
    "gh api repos/muhammadbayoumi/ScrapeX --jq .visibility",
    "gh api repos/muhammadbayoumi/ScrapeX/rulesets/23994761 --jq '.enforcement, .bypass_actors'",
    "gh api repos/muhammadbayoumi/ScrapeX/rules/branches/main --paginate",
    "gh api repos/muhammadbayoumi/ScrapeX/rulesets/23994761/history",
    "gh api repos/{owner}/{repo}/rulesets",
    "gh api 'repos/{owner}/{repo}'",
    "gh api repos/:owner/:repo",
    "gh api repos/:owner/:repo/rulesets/23994761",
    "export GH_TOKEN=$(gh auth token --user muhammadbayoumi) && gh api repos/muhammadbayoumi/ScrapeX/rulesets/23994761",
    "gh api graphql -f query='{ repository(owner: \"muhammadbayoumi\", name: \"ScrapeX\") { rulesets(first: 5) { nodes { name enforcement } } } }'",
    "gh ruleset list",
    "gh ruleset view 23994761",
    "gh ruleset check main",
    "gh repo view muhammadbayoumi/ScrapeX --json visibility,defaultBranchRef",
    "gh secret list",
    "gh variable list",
    "gh variable get SCOPE",
    "gh workflow list",
    "gh workflow view ci.yml",
    "gh workflow enable ci.yml",
    # Ordinary writes under the repository that are not his settings.
    "gh api -X DELETE repos/muhammadbayoumi/ScrapeX/git/refs/heads/claude/merged-branch",
    "gh api --method PATCH repos/muhammadbayoumi/ScrapeX/pulls/1130 -f title='Sessions cannot rewrite the rules'",
]

RECORDING = [
    "gh issue create --title 'Deny rules miss curl' --body-file finding.md",
    "gh issue comment 1104 --body-file comment.md",
    "gh issue comment 1104 --body 'gh api -X DELETE repos/muhammadbayoumi/ScrapeX/rulesets/23994761 is refused now'",
    "gh issue close 5 --comment 'No longer true: see #1126'",
    "gh issue edit 5 --add-label bug",
    "gh pr create --base main --head claude/x --title t --body-file pr.md",
    "gh pr comment 1130 --body-file review.md",
    "gh api repos/muhammadbayoumi/ScrapeX/issues -f title='Deny rules miss curl' -f body='found in review'",
    "gh api repos/{owner}/{repo}/issues/1104/comments -f body='Hi from CLI'",
    "gh api -X PATCH repos/muhammadbayoumi/ScrapeX/issues/5 -f state=closed",
    "gh api repos/:owner/:repo/milestones",
    "gh api repos/:owner/:repo/milestones -f title='Deny the repository-setting writes'",
]


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("command", READS)
def test_the_reads_that_verify_protection_are_never_refused(tool, command):
    assert not _refusing(tool, command, _deny(), ignore_case=True)


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("command", RECORDING)
def test_recording_a_problem_is_never_refused(tool, command):
    assert not _refusing(tool, command, _deny(), ignore_case=True)
