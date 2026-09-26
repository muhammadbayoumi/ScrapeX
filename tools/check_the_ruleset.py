"""Read main's ruleset back, and fail loudly if it is not the one on record.

    python3 tools/check_the_ruleset.py    (GITHUB_TOKEN or GH_TOKEN, and GITHUB_REPOSITORY)

WHY THIS EXISTS. Protection on `main` has already vanished once without a sound: after
the repository went private and back, classic protection was simply gone, and
`mergeStateStatus` read CLEAN, which looks like success (#864, #842). On GitHub Free a
ruleset binds only while the repository is PUBLIC, and every session acts as an admin
who can edit or delete it. Until this, nothing read it back (#1133).

WHAT IT COMPARES. `GET repos/{repo}/rules/branches/main` -- the EFFECTIVE rules, every
field of every rule -- and the repository's `visibility`, against
`.github/ruleset-main.json`. Both directions count: a rule or a field that is missing,
one that changed, and one on main that the file does not hold. Required checks compare
as an ordered list of `{context, integration_id}`. `ruleset_id`, `ruleset_source` and
`ruleset_source_type` are dropped, because a ruleset recreated with the same rules is
not drift.

    0  main matches the file
    1  DRIFT: one `::error::` line per difference, naming the rule and the field
    2  COULD NOT CHECK: no token, an endpoint still unreadable after one retry, or a
       body that is not the shape this reads. Never reported as "no drift", and never
       as drift.

WHAT IT CANNOT SEE: BYPASS ACTORS. The rules endpoint does not show them to a token
that holds only Metadata: read, which is all a workflow's GITHUB_TOKEN has, so an actor
added to the bypass list is invisible to this and to any check inside the repository.

NO ANONYMOUS FALLBACK. Runners share the 60-an-hour anonymous limit, and a rate-limit
403 must not read as drift; without a token this exits 2 and says why.

A DELIBERATE RULESET CHANGE UPDATES `.github/ruleset-main.json` IN THE SAME PR: one
`gh api repos/{repo}/rules/branches/main`, the three keys above removed, `visibility`
kept. Save that same response over `tests/fixtures/github_rules_branches_main.json`,
which the tests hold the expected file to.
"""
from __future__ import annotations

import http.client
import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = ROOT / ".github" / "ruleset-main.json"
API = "https://api.github.com"
BRANCH = "main"

#: Which ruleset a rule came from, not what it enforces.
VOLATILE = frozenset({"ruleset_id", "ruleset_source", "ruleset_source_type"})

#: One retry, after this long. A second failure is reported, never guessed past.
RETRY_PAUSE_SECONDS = 5

REPOSITORY = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

#: `(url, token) -> (status, body)`. Injected by the tests, so they never touch the network.
Fetch = Callable[[str, str], tuple[int, bytes]]


class CouldNotCheck(Exception):
    """The answer is unknown: not drift, and not the absence of it."""


def http_get(url: str, token: str) -> tuple[int, bytes]:
    """GET `url`. An HTTP error comes back as its status; no response raises OSError."""
    request = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "check_the_ruleset",
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _github_message(body: bytes) -> str:
    """GitHub's own `message` on an error response, which is what names a rate limit."""
    try:
        parsed = json.loads(body)
    except ValueError:
        return ""
    message = parsed.get("message") if isinstance(parsed, dict) else None
    return f" ({message[:200]})" if isinstance(message, str) else ""


def read_json(endpoint: str, token: str, fetch: Fetch = http_get,
              sleep: Callable[[float], object] = time.sleep) -> object:
    """GET `endpoint` under the API and parse it, retrying once after a short pause.

    Raises `CouldNotCheck` naming the endpoint and the status. A body that is not JSON
    is not retried: GitHub answered, and what it answered is not what this reads.
    """
    failure = ""
    for attempt in (1, 2):
        if attempt > 1:
            sleep(RETRY_PAUSE_SECONDS)
        try:
            status, body = fetch(f"{API}/{endpoint}", token)
        except (OSError, http.client.HTTPException) as exc:
            failure = f"no response ({type(exc).__name__}: {exc})"
            continue
        if status == 200:
            break
        failure = f"HTTP {status}{_github_message(body)}"
    else:
        raise CouldNotCheck(f"could not read {endpoint}: {failure}, on both attempts")
    try:
        return json.loads(body)
    except ValueError as exc:
        raise CouldNotCheck(
            f"could not read {endpoint}: HTTP 200, but the body is not JSON ({exc})") from exc


def _show(value: object) -> str:
    """Canonical JSON. Also the comparison, so `true` and `1` are never equal."""
    return json.dumps(value, sort_keys=True)


def _required_checks(parameters: dict, source: str) -> list[dict]:
    """The required checks as an ordered list of `{context, integration_id}`."""
    entries = parameters.get("required_status_checks")
    if not isinstance(entries, list):
        raise CouldNotCheck(f"{source}: `required_status_checks` holds no list of checks")
    checks = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("context"), str):
            raise CouldNotCheck(f"{source}: a required check has no string `context`: "
                                f"{_show(entry)[:200]}")
        integration = entry.get("integration_id")
        if integration is not None and (isinstance(integration, bool)
                                        or not isinstance(integration, int)):
            raise CouldNotCheck(f"{source}: required check `{entry['context']}` has a "
                                f"non-integer `integration_id`: {_show(integration)}")
        checks.append({"context": entry["context"], "integration_id": integration})
    return checks


def rules_by_type(items: object, source: str) -> dict[str, list[dict]]:
    """Every rule keyed by its type, with the volatile keys dropped.

    A LIST PER TYPE, because a second ruleset that targets main adds a second rule of
    the same type, and folding the two into one would hide exactly that.
    """
    if not isinstance(items, list):
        raise CouldNotCheck(f"{source}: expected a list of rules, got {_show(items)[:200]}")
    rules: dict[str, list[dict]] = {}
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            raise CouldNotCheck(f"{source}: a rule has no string `type`: {_show(item)[:200]}")
        rule = {key: value for key, value in item.items() if key not in VOLATILE}
        if "parameters" in rule and not isinstance(rule["parameters"], dict):
            raise CouldNotCheck(f"{source}: rule `{rule['type']}` has `parameters` that are "
                                "not an object")
        if rule["type"] == "required_status_checks":
            parameters = rule.get("parameters")
            if parameters is None:
                raise CouldNotCheck(f"{source}: rule `required_status_checks` has no "
                                    "`parameters`")
            rule["parameters"] = {**parameters, "required_status_checks":
                                  _required_checks(parameters, source)}
        rules.setdefault(rule["type"], []).append(rule)
    return rules


def visibility_of(repository: object, source: str) -> str:
    if not isinstance(repository, dict) or not isinstance(repository.get("visibility"), str):
        raise CouldNotCheck(f"{source}: the repository has no string `visibility`")
    return repository["visibility"]


def _display(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def load_expected(path: Path) -> tuple[str, dict[str, dict]]:
    """The visibility and the rules on record, each rule type exactly once."""
    name = _display(path)
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CouldNotCheck(f"could not read {name}: {exc}") from exc
    if not isinstance(parsed, dict) or set(parsed) != {"visibility", "rules"}:
        raise CouldNotCheck(f"{name}: expected an object with exactly `visibility` and "
                            f"`rules`, got {_show(parsed)[:200]}")
    if not isinstance(parsed["visibility"], str):
        raise CouldNotCheck(f"{name}: `visibility` is not a string")
    rules = rules_by_type(parsed["rules"], name)
    doubled = sorted(rule_type for rule_type, copies in rules.items() if len(copies) > 1)
    if doubled:
        raise CouldNotCheck(f"{name}: holds {doubled} more than once")
    return parsed["visibility"], {rule_type: copies[0] for rule_type, copies in rules.items()}


def _compare_checks(expected: list[dict], found: list[dict], out: list[str]) -> None:
    """Required checks: by name first, then order and repetition if names say nothing."""
    if expected == found:
        return
    field = "rule `required_status_checks` field `parameters.required_status_checks`"
    before = len(out)
    wanted = {check["context"]: check["integration_id"] for check in expected}
    present = {check["context"]: check["integration_id"] for check in found}
    for name, integration in wanted.items():
        if name not in present:
            out.append(f"{field}: check `{name}` is no longer required on main")
        elif present[name] != integration:
            out.append(f"{field}: check `{name}` integration_id: expected "
                       f"{_show(integration)}, found {_show(present[name])}")
    for name in present:
        if name not in wanted:
            out.append(f"{field}: check `{name}` is required on main and not in the "
                       "expected file")
    if len(out) == before:
        out.append(f"{field}: the checks differ in order or repetition: expected "
                   f"{_show(expected)}, found {_show(found)}")


def _compare_fields(rule_type: str, prefix: str, expected: dict, found: dict,
                    out: list[str]) -> None:
    for key in sorted(set(expected) | set(found)):
        field = f"rule `{rule_type}` field `{prefix}{key}`"
        if key not in found:
            out.append(f"{field} is missing on main (expected {_show(expected[key])})")
        elif key not in expected:
            out.append(f"{field} is on main ({_show(found[key])}) and not in the "
                       "expected file")
        elif (rule_type == "required_status_checks"
              and f"{prefix}{key}" == "parameters.required_status_checks"):
            _compare_checks(expected[key], found[key], out)
        elif isinstance(expected[key], dict) and isinstance(found[key], dict):
            _compare_fields(rule_type, f"{prefix}{key}.", expected[key], found[key], out)
        elif _show(expected[key]) != _show(found[key]):
            out.append(f"{field}: expected {_show(expected[key])}, "
                       f"found {_show(found[key])}")


def differences(expected_visibility: str, expected_rules: dict[str, dict],
                visibility: str, rules: dict[str, list[dict]]) -> list[str]:
    """Every way main differs from the record, in both directions. Empty means none."""
    out: list[str] = []
    if visibility != expected_visibility:
        out.append(f"repository visibility: expected {expected_visibility}, found "
                   f"{visibility}. On GitHub Free a ruleset binds only while the "
                   "repository is public")
    for rule_type in sorted(set(expected_rules) | set(rules)):
        if rule_type not in rules:
            out.append(f"rule `{rule_type}` is missing from main's effective rules")
            continue
        copies = rules[rule_type]
        if rule_type not in expected_rules:
            out.append(f"rule `{rule_type}` is on main and not in the expected file: "
                       f"{_show(copies)[:300]}")
            continue
        if len(copies) > 1:
            out.append(f"rule `{rule_type}` is on main {len(copies)} times: more than one "
                       "ruleset targets the branch")
        for rule in copies:
            _compare_fields(rule_type, "", expected_rules[rule_type], rule, out)
    return out


def _annotation(title: str, message: str) -> str:
    """One workflow command. `%`, CR and LF are escaped as GitHub requires, or a value
    carrying a newline would end this line and start a command of its own."""
    escaped = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    return f"::error title={title}::{escaped}"


def check(environ: Mapping[str, str], fetch: Fetch = http_get,
          sleep: Callable[[float], object] = time.sleep,
          expected_path: Path = EXPECTED) -> int:
    """Compare main with the record and print the verdict. Returns the exit code."""
    not_checked = "The ruleset was NOT checked; this is not a verdict either way."
    token = environ.get("GITHUB_TOKEN") or environ.get("GH_TOKEN")
    if not token:
        print(_annotation("Ruleset not checked",
                          "no token: set GITHUB_TOKEN or GH_TOKEN. This check does not read "
                          "anonymously: runners share the 60-an-hour anonymous limit, and a "
                          f"rate-limit 403 is not drift. {not_checked}"))
        return 2
    repository = environ.get("GITHUB_REPOSITORY", "")
    if not REPOSITORY.match(repository):
        print(_annotation("Ruleset not checked",
                          f"GITHUB_REPOSITORY is {repository!r}, not owner/name. "
                          f"{not_checked}"))
        return 2

    name = _display(expected_path)
    rules_endpoint = f"repos/{repository}/rules/branches/{BRANCH}"
    try:
        expected_visibility, expected_rules = load_expected(expected_path)
        rules = rules_by_type(read_json(rules_endpoint, token, fetch, sleep), rules_endpoint)
        visibility = visibility_of(read_json(f"repos/{repository}", token, fetch, sleep),
                                   f"repos/{repository}")
    except CouldNotCheck as exc:
        print(_annotation("Ruleset not checked", f"{exc}. {not_checked}"))
        return 2

    found = differences(expected_visibility, expected_rules, visibility, rules)
    if not found:
        print(f"main's effective rules match {name}: {len(rules)} rule types "
              f"({', '.join(sorted(rules))}), visibility {visibility}. Bypass actors "
              "are not visible to this token and were not compared.")
        return 0
    for line in found:
        print(_annotation("Ruleset drift", line))
    print(f"{len(found)} difference(s) between main's effective rules and {name}. If the "
          f"ruleset was changed on purpose, update {name} in the same PR; if not, the "
          "ruleset is what needs restoring.")
    return 1


if __name__ == "__main__":
    raise SystemExit(check(os.environ))
