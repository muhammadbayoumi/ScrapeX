"""The privacy policy makes promises. This is what stops them becoming lies.

A privacy policy is normally prose nobody checks, drifting away from the
software month by month until it describes a product that no longer exists.
Every promise in ours that CAN be checked mechanically is checked here, so
breaking one fails a build instead of misleading a reader.

The Chrome Web Store requires this document and a support contact before an
extension can be published (Decision 6, milestone M4). Neither existed.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

pytestmark = pytest.mark.extension

ROOT = pathlib.Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs" / "privacy-policy.md"
SUPPORT = ROOT / "docs" / "support.md"
MANIFEST = json.loads(
    (ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))


def test_both_documents_the_store_requires_exist():
    """Neither did before M4. The store refuses a listing without them."""
    assert POLICY.is_file()
    assert SUPPORT.is_file()


def test_the_policy_names_every_scope_the_extension_actually_asks_for():
    """THE PROMISE MOST LIKELY TO ROT. A scope added later reaches users
    through an update prompt; a policy that still lists the old three is the
    difference between disclosure and a surprise."""
    policy = POLICY.read_text(encoding="utf-8")

    for scope in MANIFEST["oauth2"]["scopes"]:
        short = scope.rsplit("/", 1)[-1]
        assert short in policy, (
            f"the extension asks for {short} and the policy does not mention it")


def test_the_policy_claims_no_full_drive_access_and_the_manifest_agrees():
    """"ScrapeX never asks for full Drive access" is a sentence a single
    manifest edit can turn into a false one."""
    policy = POLICY.read_text(encoding="utf-8")
    scopes = MANIFEST["oauth2"]["scopes"]

    assert "never asks for full Drive access" in policy
    assert "https://www.googleapis.com/auth/drive" not in scopes, (
        "the manifest now asks for the whole of Drive, and the policy says it "
        "never does")


def test_the_policy_claims_no_telemetry_and_nothing_reports_anything():
    """"contains no telemetry of any kind" — asserted against the shipped
    extension rather than against intent."""
    policy = POLICY.read_text(encoding="utf-8")
    assert "no telemetry" in policy

    shipped = [p for p in (ROOT / "extension").rglob("*.js")
               if "tests" not in p.parts]
    assert shipped, "no extension JavaScript was found to check"

    banned = re.compile(
        r"google-analytics|googletagmanager|sentry\.io|mixpanel|segment\.io|"
        r"amplitude\.com|posthog", re.I)
    for path in shipped:
        found = banned.search(path.read_text(encoding="utf-8"))
        assert not found, (
            f"{path.name} contacts {found.group(0)}, and the policy says the "
            "extension contains no telemetry of any kind")


def test_the_policy_lists_every_host_the_extension_can_reach():
    """A host permission is a place data COULD go. One added without a line in
    the policy is exactly the drift this file exists to stop."""
    policy = POLICY.read_text(encoding="utf-8")

    for host in MANIFEST["host_permissions"]:
        if host.startswith("http://127.0.0.1") or host.startswith("http://localhost"):
            continue        # the engine on this machine, which the policy describes
        name = host.split("//", 1)[1].rstrip("/*")
        assert name in policy, (
            f"the extension may contact {name} and the policy does not say so")


def test_the_policy_tells_the_reader_how_to_delete_everything():
    """Four places, because there are four. A deletion section that names three
    leaves data somewhere the reader believes is clean."""
    policy = POLICY.read_text(encoding="utf-8")

    for where in ("Start fresh", "Google Drive", "myaccount.google.com/permissions",
                  "chrome://extensions"):
        assert where in policy, f"deleting {where} is not explained"


def test_the_support_page_names_a_reachable_route_and_what_to_send():
    """A support contact that is only an address collects reports nobody can
    act on. This one asks for the two version numbers the panel already shows
    side by side for exactly this purpose."""
    support = SUPPORT.read_text(encoding="utf-8")

    assert "github.com/muhammadbayoumi/ScrapeX/issues" in support
    assert "Installed version" in support and "About" in support
    assert "Do not send your database" in support, (
        "nothing warns the reader off attaching everything he has collected")


def test_the_two_documents_point_at_each_other():
    """The store links to one of them; a reader who lands on either must be
    able to reach the other."""
    assert "support.md" in POLICY.read_text(encoding="utf-8")
    assert "privacy-policy.md" in SUPPORT.read_text(encoding="utf-8")
