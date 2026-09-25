"""Main's ruleset is read back on every CI run, and three answers stay three answers.

`tools/check_the_ruleset.py` exists because protection on `main` has vanished silently
once already (#864, #842) and nothing read the ruleset back (#1133). Its whole value is
that it can say three different things and never confuses them:

  0  main matches `.github/ruleset-main.json`;
  1  DRIFT, in either direction -- a rule or field missing, changed, or added;
  2  COULD NOT CHECK -- which must never read as "no drift", and never as drift either,
     or a rate-limited runner turns every pull request red for a ruleset nobody touched.

FULLY OFFLINE. The fetch function is injected, and every response here starts from
`tests/fixtures/github_rules_branches_main.json`, the real body of
`GET repos/muhammadbayoumi/ScrapeX/rules/branches/main` captured 2026-09-25 when
`.github/ruleset-main.json` was taken from it. Starting from the real body is the point:
a hand-written response would test what this file believes the API returns.
"""
from __future__ import annotations

import copy
import http.client
import io
import json
import urllib.error
from pathlib import Path

import pytest
import yaml

from tools import check_the_ruleset

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "github_rules_branches_main.json"
EXPECTED = ROOT / ".github" / "ruleset-main.json"

REPO = "muhammadbayoumi/ScrapeX"
RULES_ENDPOINT = f"repos/{REPO}/rules/branches/main"
RULES_URL = f"https://api.github.com/{RULES_ENDPOINT}"
REPO_URL = f"https://api.github.com/repos/{REPO}"
TOKEN = "a-token"
ENV = {"GITHUB_TOKEN": TOKEN, "GITHUB_REPOSITORY": REPO}


def _real_rules() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _rule(rules: list[dict], rule_type: str) -> dict:
    [rule] = [rule for rule in rules if rule["type"] == rule_type]
    return rule


def _checks(rules: list[dict]) -> list[dict]:
    return _rule(rules, "required_status_checks")["parameters"]["required_status_checks"]


class FakeGitHub:
    """Answers the two endpoints from memory. `queued` replies are served first, per
    URL, and may be an exception to raise; after that every call gets a 200."""

    def __init__(self, rules: object, visibility: str = "public",
                 queued: dict[str, list] | None = None):
        self.rules = rules
        self.visibility = visibility
        self.queued = {url: list(replies) for url, replies in (queued or {}).items()}
        self.calls: list[str] = []

    def __call__(self, url: str, token: str) -> tuple[int, bytes]:
        self.calls.append(url)
        assert token == TOKEN, f"the check sent {token!r} as its token"
        if self.queued.get(url):
            reply = self.queued[url].pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply
        if url == RULES_URL:
            return 200, json.dumps(self.rules).encode("utf-8")
        if url == REPO_URL:
            return 200, json.dumps({"full_name": REPO,
                                    "visibility": self.visibility}).encode("utf-8")
        raise AssertionError(f"the check asked for an endpoint it has no reason to read: {url}")


def _run(capsys, github, env=ENV, expected: Path = EXPECTED) -> tuple[int, str, list]:
    pauses: list[float] = []
    code = check_the_ruleset.check(env, fetch=github, sleep=pauses.append,
                                   expected_path=expected)
    return code, capsys.readouterr().out, pauses


def _errors(out: str) -> list[str]:
    return [line for line in out.splitlines() if line.startswith("::error")]


# --- the expected file is today's ruleset --------------------------------------------


def test_the_committed_expected_file_parses_and_holds_the_four_rule_types():
    visibility, rules = check_the_ruleset.load_expected(EXPECTED)

    assert visibility == "public"
    assert sorted(rules) == ["deletion", "non_fast_forward", "pull_request",
                             "required_status_checks"]
    checks = rules["required_status_checks"]["parameters"]
    assert checks["strict_required_status_checks_policy"] is True
    assert [c["context"] for c in checks["required_status_checks"]] == [
        "scope", "lint", "test", "contract-parity"]


def test_the_real_response_matches_the_committed_expected_file(capsys):
    """The equal case, on the real body. It is also what fails if the expected file is
    edited by hand into something main never was -- `strict` set to false, a check
    dropped -- because the fixture is the response the file was taken from. A
    deliberate ruleset change re-captures both from one GET."""
    code, out, pauses = _run(capsys, FakeGitHub(_real_rules()))

    assert code == 0, out
    assert _errors(out) == []
    assert "match" in out and "visibility public" in out
    assert pauses == [], "a clean read paused as if it had retried"


def test_a_recreated_ruleset_with_the_same_rules_is_not_drift(capsys):
    rules = _real_rules()
    for rule in rules:
        rule["ruleset_id"] = 99999999
        rule["ruleset_source"] = "someone/else"
        rule["ruleset_source_type"] = "Organization"

    code, out, _ = _run(capsys, FakeGitHub(rules))

    assert code == 0, out


def test_the_github_token_can_come_from_gh_token(capsys):
    """Locally the token is GH_TOKEN; on a runner it is GITHUB_TOKEN."""
    code, out, _ = _run(capsys, FakeGitHub(_real_rules()),
                        env={"GH_TOKEN": TOKEN, "GITHUB_REPOSITORY": REPO})

    assert code == 0, out


# --- drift: every direction is exit 1, with the rule and the field named ------------


def test_a_missing_rule_type_is_drift(capsys):
    rules = [rule for rule in _real_rules() if rule["type"] != "pull_request"]

    code, out, _ = _run(capsys, FakeGitHub(rules))

    assert code == 1, out
    assert _errors(out) == [
        "::error title=Ruleset drift::rule `pull_request` is missing from main's "
        "effective rules"]


def test_strict_turned_off_is_drift(capsys):
    rules = _real_rules()
    _rule(rules, "required_status_checks")["parameters"][
        "strict_required_status_checks_policy"] = False

    code, out, _ = _run(capsys, FakeGitHub(rules))

    assert code == 1, out
    [error] = _errors(out)
    assert "rule `required_status_checks`" in error
    assert "field `parameters.strict_required_status_checks_policy`" in error
    assert "expected true, found false" in error


def test_a_boolean_replaced_by_one_is_still_drift(capsys):
    """Python says `True == 1`. The comparison is on canonical JSON, where they differ."""
    rules = _real_rules()
    _rule(rules, "required_status_checks")["parameters"][
        "strict_required_status_checks_policy"] = 1

    code, out, _ = _run(capsys, FakeGitHub(rules))

    assert code == 1, out
    assert "expected true, found 1" in out


def test_a_required_check_removed_is_drift(capsys):
    rules = _real_rules()
    checks = _rule(rules, "required_status_checks")["parameters"]
    checks["required_status_checks"] = [c for c in checks["required_status_checks"]
                                        if c["context"] != "test"]

    code, out, _ = _run(capsys, FakeGitHub(rules))

    assert code == 1, out
    [error] = _errors(out)
    assert "field `parameters.required_status_checks`" in error
    assert "check `test` is no longer required on main" in error


def test_an_extra_required_check_is_drift(capsys):
    rules = _real_rules()
    _checks(rules).append({"context": "deploy", "integration_id": 15368})

    code, out, _ = _run(capsys, FakeGitHub(rules))

    assert code == 1, out
    [error] = _errors(out)
    assert "check `deploy` is required on main and not in the expected file" in error


def test_a_changed_integration_id_is_drift(capsys):
    """The same name from a different app is a different check: anything that can post
    a status called `test` would satisfy it."""
    rules = _real_rules()
    _checks(rules)[2]["integration_id"] = 12345

    code, out, _ = _run(capsys, FakeGitHub(rules))

    assert code == 1, out
    [error] = _errors(out)
    assert "check `test` integration_id: expected 15368, found 12345" in error


def test_an_integration_id_dropped_to_any_source_is_drift(capsys):
    rules = _real_rules()
    del _checks(rules)[0]["integration_id"]

    code, out, _ = _run(capsys, FakeGitHub(rules))

    assert code == 1, out
    assert "check `scope` integration_id: expected 15368, found null" in out


def test_the_same_checks_in_another_order_are_drift(capsys):
    """Compared as an ordered list; when no name differs, the order is what is named."""
    rules = _real_rules()
    _checks(rules).reverse()

    code, out, _ = _run(capsys, FakeGitHub(rules))

    assert code == 1, out
    [error] = _errors(out)
    assert "differ in order or repetition" in error


def test_a_deleted_ruleset_is_drift_and_names_all_four_rules(capsys):
    """`[]` is what the endpoint returns once the ruleset is gone -- a 200, not an error,
    which is exactly why it must not read as a clean answer."""
    code, out, _ = _run(capsys, FakeGitHub([]))

    assert code == 1, out
    errors = _errors(out)
    assert len(errors) == 4, errors
    for rule_type in ("deletion", "non_fast_forward", "pull_request",
                      "required_status_checks"):
        assert any(f"rule `{rule_type}` is missing" in e for e in errors), errors


def test_an_unexpected_extra_rule_type_is_drift(capsys):
    rules = [*_real_rules(), {"type": "required_linear_history",
                              "ruleset_id": 1, "ruleset_source": REPO,
                              "ruleset_source_type": "Repository"}]

    code, out, _ = _run(capsys, FakeGitHub(rules))

    assert code == 1, out
    [error] = _errors(out)
    assert "rule `required_linear_history` is on main and not in the expected file" in error


def test_a_second_ruleset_adding_the_same_rule_type_is_drift(capsys):
    """Keyed by type, two rules of one type would fold into one without a sound."""
    rules = _real_rules()
    rules.append(copy.deepcopy(_rule(rules, "pull_request")))

    code, out, _ = _run(capsys, FakeGitHub(rules))

    assert code == 1, out
    assert "rule `pull_request` is on main 2 times" in out


def test_a_changed_pull_request_parameter_is_drift(capsys):
    rules = _real_rules()
    _rule(rules, "pull_request")["parameters"]["required_approving_review_count"] = 1

    code, out, _ = _run(capsys, FakeGitHub(rules))

    assert code == 1, out
    [error] = _errors(out)
    assert ("rule `pull_request` field `parameters.required_approving_review_count`: "
            "expected 0, found 1") in error


def test_a_field_main_has_and_the_file_does_not_is_drift(capsys):
    """Both directions: a field GitHub starts returning is named, not ignored."""
    rules = _real_rules()
    _rule(rules, "pull_request")["parameters"]["a_new_parameter"] = True

    code, out, _ = _run(capsys, FakeGitHub(rules))

    assert code == 1, out
    [error] = _errors(out)
    assert "field `parameters.a_new_parameter` is on main (true)" in error


def test_a_field_the_file_has_and_main_does_not_is_drift(capsys):
    rules = _real_rules()
    del _rule(rules, "required_status_checks")["parameters"]["do_not_enforce_on_create"]

    code, out, _ = _run(capsys, FakeGitHub(rules))

    assert code == 1, out
    [error] = _errors(out)
    assert "field `parameters.do_not_enforce_on_create` is missing on main" in error


def test_a_private_repository_is_drift(capsys):
    """On GitHub Free a ruleset binds only while the repository is public, so a private
    repository has no protection even with every rule still listed."""
    code, out, _ = _run(capsys, FakeGitHub(_real_rules(), visibility="private"))

    assert code == 1, out
    [error] = _errors(out)
    assert "repository visibility: expected public, found private" in error


def test_a_newline_in_a_value_cannot_start_a_workflow_command_of_its_own(capsys):
    rules = _real_rules()
    _checks(rules).append({"context": "x\n::warning::forged", "integration_id": 1})

    code, out, _ = _run(capsys, FakeGitHub(rules))

    assert code == 1, out
    assert not any(line.startswith("::warning::") for line in out.splitlines())
    assert "x%0A::warning::forged" in out


# --- could not check: exit 2, the endpoint named, never a verdict -------------------


def test_an_endpoint_that_fails_twice_is_could_not_check_and_names_it(capsys):
    github = FakeGitHub(_real_rules(), queued={RULES_URL: [
        (503, b'{"message": "Service unavailable"}'),
        (403, b'{"message": "API rate limit exceeded for installation"}')]})

    code, out, pauses = _run(capsys, github)

    assert code == 2, out
    [error] = _errors(out)
    assert error.startswith("::error title=Ruleset not checked::")
    assert f"could not read {RULES_ENDPOINT}" in error
    assert "HTTP 403 (API rate limit exceeded for installation)" in error
    assert "drift" not in error.lower()
    assert github.calls == [RULES_URL, RULES_URL], "it retried more or less than once"
    assert pauses == [check_the_ruleset.RETRY_PAUSE_SECONDS]


def test_one_failure_then_a_200_is_read_after_one_pause(capsys):
    github = FakeGitHub(_real_rules(), queued={RULES_URL: [(502, b"Bad gateway")]})

    code, out, pauses = _run(capsys, github)

    assert code == 0, out
    assert github.calls.count(RULES_URL) == 2
    assert pauses == [check_the_ruleset.RETRY_PAUSE_SECONDS]


def test_no_response_twice_is_could_not_check(capsys):
    github = FakeGitHub(_real_rules(), queued={RULES_URL: [
        TimeoutError("timed out"), ConnectionResetError("reset")]})

    code, out, _ = _run(capsys, github)

    assert code == 2, out
    assert "no response (ConnectionResetError: reset)" in out


@pytest.mark.parametrize("broken", [
    lambda: http.client.IncompleteRead(b"[{", 500),
    lambda: http.client.BadStatusLine("HTTP/1.1 ???"),
    lambda: http.client.LineTooLong("header line"),
], ids=["IncompleteRead", "BadStatusLine", "LineTooLong"])
def test_a_broken_response_twice_is_could_not_check_and_names_it(capsys, broken):
    """A response cut off or garbled mid-read raises `http.client.HTTPException`, which
    is not an OSError. Left uncaught it ends the run with a traceback and exit 1 -- the
    code that means drift."""
    github = FakeGitHub(_real_rules(), queued={RULES_URL: [broken(), broken()]})

    code, out, pauses = _run(capsys, github)

    assert code == 2, out
    [error] = _errors(out)
    assert error.startswith("::error title=Ruleset not checked::")
    assert f"could not read {RULES_ENDPOINT}" in error
    assert type(broken()).__name__ in error and "on both attempts" in error
    assert "drift" not in error.lower()
    assert github.calls == [RULES_URL, RULES_URL], "it retried more or less than once"
    assert pauses == [check_the_ruleset.RETRY_PAUSE_SECONDS]


def test_the_repository_endpoint_failing_is_could_not_check_and_names_it(capsys):
    github = FakeGitHub(_real_rules(), queued={REPO_URL: [(404, b"{}"), (404, b"{}")]})

    code, out, _ = _run(capsys, github)

    assert code == 2, out
    assert f"could not read repos/{REPO}: HTTP 404" in out


def test_a_body_that_is_not_json_is_could_not_check(capsys):
    github = FakeGitHub(_real_rules(), queued={RULES_URL: [(200, b"<html>unicorn</html>")]})

    code, out, _ = _run(capsys, github)

    assert code == 2, out
    assert f"could not read {RULES_ENDPOINT}: HTTP 200, but the body is not JSON" in out


@pytest.mark.parametrize("body, says", [
    ({"message": "Not Found"}, "expected a list of rules"),
    ([{"parameters": {}}], "a rule has no string `type`"),
    ([{"type": "pull_request", "parameters": []}], "not an object"),
    ([{"type": "required_status_checks"}], "has no `parameters`"),
    ([{"type": "required_status_checks", "parameters": {}}], "holds no list of checks"),
    ([{"type": "required_status_checks",
       "parameters": {"required_status_checks": [{"integration_id": 1}]}}],
     "no string `context`"),
    ([{"type": "required_status_checks",
       "parameters": {"required_status_checks": [{"context": "t", "integration_id": "1"}]}}],
     "non-integer `integration_id`"),
])
def test_a_response_of_another_shape_is_could_not_check(capsys, body, says):
    """Every parse asserts its shape, and a shape it does not know is not a verdict."""
    code, out, _ = _run(capsys, FakeGitHub(body))

    assert code == 2, out
    assert says in out


def test_a_repository_without_visibility_is_could_not_check(capsys):
    github = FakeGitHub(_real_rules(), queued={REPO_URL: [(200, b'{"private": false}')]})

    code, out, _ = _run(capsys, github)

    assert code == 2, out
    assert "no string `visibility`" in out


def test_no_token_is_could_not_check_and_reads_nothing(capsys):
    """No anonymous fallback: runners share the anonymous limit, and a rate-limit 403
    from it must not read as drift."""
    github = FakeGitHub(_real_rules())

    code, out, _ = _run(capsys, github, env={"GITHUB_REPOSITORY": REPO, "GITHUB_TOKEN": ""})

    assert code == 2, out
    assert "no token" in out
    assert github.calls == [], "it read the API without a token"


def test_no_repository_is_could_not_check(capsys):
    github = FakeGitHub(_real_rules())

    code, out, _ = _run(capsys, github, env={"GITHUB_TOKEN": TOKEN})

    assert code == 2, out
    assert "GITHUB_REPOSITORY" in out
    assert github.calls == []


class _Response:
    status = 200

    def read(self) -> bytes:
        return b"[]"

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> bool:
        return False


def test_the_real_fetch_sends_the_token_and_returns_status_and_body(monkeypatch):
    seen = {}

    def urlopen(request, timeout):
        seen["url"], seen["timeout"] = request.full_url, timeout
        seen["authorization"] = request.get_header("Authorization")
        return _Response()

    monkeypatch.setattr(check_the_ruleset.urllib.request, "urlopen", urlopen)

    assert check_the_ruleset.http_get(RULES_URL, TOKEN) == (200, b"[]")
    assert seen == {"url": RULES_URL, "timeout": 30, "authorization": f"Bearer {TOKEN}"}


def test_the_real_fetch_returns_an_http_error_as_its_status(monkeypatch):
    def urlopen(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {},
                                     io.BytesIO(b'{"message": "rate limited"}'))

    monkeypatch.setattr(check_the_ruleset.urllib.request, "urlopen", urlopen)

    assert check_the_ruleset.http_get(RULES_URL, TOKEN) == (403, b'{"message": "rate limited"}')


def test_the_real_fetch_with_no_network_is_could_not_check(monkeypatch, capsys):
    """End to end through the default fetch: no response at all is exit 2, not 0."""
    def urlopen(request, timeout):
        raise urllib.error.URLError("Name or service not known")

    monkeypatch.setattr(check_the_ruleset.urllib.request, "urlopen", urlopen)
    pauses: list[float] = []

    code = check_the_ruleset.check(ENV, sleep=pauses.append)
    out = capsys.readouterr().out

    assert code == 2, out
    assert f"could not read {RULES_ENDPOINT}: no response (URLError" in out
    assert pauses == [check_the_ruleset.RETRY_PAUSE_SECONDS]


@pytest.mark.parametrize("content, says", [
    ("{not json", "could not read"),
    ('{"rules": []}', "exactly `visibility` and `rules`"),
    ('{"visibility": true, "rules": []}', "`visibility` is not a string"),
    ('{"visibility": "public", "rules": [{"type": "deletion"}, {"type": "deletion"}]}',
     "more than once"),
])
def test_a_malformed_expected_file_is_could_not_check(capsys, tmp_path, content, says):
    expected = tmp_path / "ruleset-main.json"
    expected.write_text(content, encoding="utf-8")

    code, out, _ = _run(capsys, FakeGitHub(_real_rules()), expected=expected)

    assert code == 2, out
    assert says in out


# --- it is wired where it runs on every change --------------------------------------


def test_ci_runs_the_check_in_the_scope_job_on_every_run():
    """`scope` is required and always runs. A step with an `if:`, or one in a job that
    can be skipped, would let the check vanish the way protection did."""
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml")
                              .read_text(encoding="utf-8"))
    scope = workflow["jobs"]["scope"]
    assert "if" not in scope and "needs" not in scope

    steps = scope["steps"]
    runs = [i for i, step in enumerate(steps)
            if "tools/check_the_ruleset.py" in str(step.get("run") or "")]
    assert len(runs) == 1, "the scope job no longer runs the ruleset check exactly once"
    step = steps[runs[0]]
    assert "if" not in step and not step.get("continue-on-error")
    assert step["env"]["GITHUB_TOKEN"] == "${{ secrets.GITHUB_TOKEN }}"
    assert str(steps[runs[0] - 1].get("uses", "")).startswith("actions/checkout"), (
        "the check no longer runs right after the checkout")
