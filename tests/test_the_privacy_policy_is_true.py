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

#: Read from the extension rather than typed here. It is the one place the
#: public home is named, and a test that spelled it out again would be a second
#: place for it to be wrong.
PUBLIC_REPO = re.search(
    r'PUBLIC_REPO = "([^"]+)"',
    (ROOT / "extension" / "releases.js").read_text(encoding="utf-8")).group(1)


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


def test_the_policy_claims_no_scope_the_extension_stopped_asking_for():
    """THE OTHER DIRECTION, which went unchecked and let a false promise stand.

    The test above only asks whether every REQUESTED scope is disclosed. It says
    nothing about a scope the policy declares and the manifest no longer wants —
    so when `spreadsheets` was dropped from identity.js, this file went on
    telling users ScrapeX writes into their Google Sheets, and the suite stayed
    green. Over-declaring is not the safe direction it looks like: it is a
    promise about someone's data that is not true, and on the store's data-usage
    form it declares a SENSITIVE scope the extension does not request.
    """
    policy = POLICY.read_text(encoding="utf-8")
    asked = {scope.rsplit("/", 1)[-1] for scope in MANIFEST["oauth2"]["scopes"]}

    # ONLY the OAuth-scope section, bounded by its own heading. The first
    # version of this test read every backtick table row in the file and so
    # tripped over "Every other address ScrapeX contacts", whose rows are
    # HOSTNAMES -- a different table answering a different question. Prose
    # elsewhere may also name a scope in order to say it is NOT used, which is
    # the opposite of a false claim.
    heading = "### The permissions ScrapeX asks for, and why each one"
    assert heading in policy, (
        "the scope section was renamed; this test must follow it or it silently "
        "stops reading anything")
    section = policy.split(heading, 1)[1].split("\n## ", 1)[0]
    table = [line for line in section.splitlines()
             if line.startswith("| `") and "|" in line[3:]]
    assert table, "the scope table is empty, so this test is asserting nothing"
    for line in table:
        for named in line.split("|")[1].replace("`", "").split(","):
            short = named.strip()
            if not short:
                continue
            assert short in asked, (
                f"the privacy policy declares the {short!r} scope and "
                f"extension/manifest.json does not ask for it. The policy is a "
                "promise about a real person's data — it may not claim access "
                "the extension gave up.")


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

    assert f"github.com/{PUBLIC_REPO}/issues" in support
    assert "Installed version" in support and "About" in support
    assert "Do not send your database" in support, (
        "nothing warns the reader off attaching everything he has collected")


def test_the_two_documents_point_at_each_other():
    """The store links to one of them; a reader who lands on either must be
    able to reach the other."""
    assert "support.md" in POLICY.read_text(encoding="utf-8")
    assert "privacy-policy.md" in SUPPORT.read_text(encoding="utf-8")


# ---- everything a user can reach must be reachable ---------------------------

def test_nothing_public_points_at_the_private_source_repository():
    """THE FAILURE THIS PREVENTS IS SILENT AND TOTAL.

    ScrapeX's source is private. GitHub answers 404 on a private repository to
    anyone not signed in — which is every user — and `readVersionManifest`
    reads a 404 as "nothing has been released yet". Every panel in the world
    would say the engine had never shipped, in a sentence that is honest about
    a fact that is wrong. The support link would 404 in a browser for the same
    reason.

    So no URL a user can reach may name the private repository, and there is
    nothing else in this codebase that would notice if one did.
    """
    private = "muhammadbayoumi/ScrapeX"
    assert PUBLIC_REPO != private, "the release feed points at the private source"

    facing = [
        ROOT / "extension" / "releases.js",
        ROOT / "docs" / "support.md",
        ROOT / "docs" / "privacy-policy.md",
    ]
    for path in facing:
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.lstrip().startswith(("//", "#", "*")):
                continue        # comments explain the rule and may quote it
            assert private not in line, (
                f"{path.name} sends a user to {private}, which is private: {line.strip()}")


def test_the_public_home_is_named_once_and_derived_everywhere_else():
    """Three hard-coded copies of a repository name is three chances to move
    two of them. The feed URL and the human URL are both built from the one
    constant."""
    releases = (ROOT / "extension" / "releases.js").read_text(encoding="utf-8")

    assert releases.count('PUBLIC_REPO = "') == 1
    assert "raw.githubusercontent.com/${PUBLIC_REPO}/main/" in releases, (
        "the feed reads api.github.com again, which allows sixty "
        "unauthenticated requests an hour PER IP — every user behind a shared "
        "address starts being refused a check none of them can fix")
    assert "https://github.com/${PUBLIC_REPO}" in releases


def test_the_support_and_policy_name_the_same_public_home():
    """A support page pointing one way and a policy the other is a reader who
    cannot tell which is the real project."""
    for path in (ROOT / "docs" / "support.md", ROOT / "docs" / "privacy-policy.md"):
        assert PUBLIC_REPO in path.read_text(encoding="utf-8"), (
            f"{path.name} does not name the public home")


# ---- what the extension writes to disk, against what the policy admits ------

def test_every_place_the_extension_persists_data_is_in_the_policy():
    """THE GAP THIS FILE HAD, found while reviewing #168 on 2026-08-12.

    Every test above checks what the extension REACHES — scopes, hosts, remote
    calls. Nothing checked what it KEEPS. So when accounts.js began writing a
    directory of names, addresses and pictures into chrome.storage.local, the
    published policy still said of exactly those fields "Nothing is stored and
    nothing is sent anywhere", and the whole suite stayed green.

    That sentence was not a small inaccuracy. It is the answer to the question a
    reader of a privacy policy is actually asking, and it was false about the one
    kind of data — a person's name and email address — that a policy exists for.

    The check is deliberately crude: any module that touches a persistent store
    must be named in the policy's storage table. Crude and loud beats precise
    and absent, and the failure message says what to write rather than only that
    something is wrong.
    """
    policy = POLICY.read_text(encoding="utf-8")
    # Split on a horizontal RULE — a line that is only dashes — not on "---",
    # because a markdown table's own header separator (`|---|---|`) contains it
    # and the first version of this cut the section off above every data row.
    # It then reported all three modules as missing, including one whose row was
    # right there. A check that is wrong about its own input is worse than none.
    after = policy.split("## What is stored, and where", 1)[-1]
    storage_table = re.split(r"^-{3,}\s*$", after, maxsplit=1, flags=re.M)[0]

    # A CALL, not a mention. The first version matched the bare API name and
    # reported app.js, which names chrome.storage.local only in a comment
    # explaining that accounts.js is the module that uses it. A test that cannot
    # tell writing from talking about writing produces exactly the noise that
    # gets a test disabled.
    persistent = (r"chrome\.storage\.(?:local|sync)\.(?:set|get|remove|clear)\s*\(",
                  r"\blocalStorage\.(?:setItem|getItem|removeItem)\s*\(",
                  r"\bindexedDB\.open\s*\(")
    writers: dict[str, set[str]] = {}
    for module in sorted((ROOT / "extension").glob("*.js")):
        body = module.read_text(encoding="utf-8")
        found = {pattern for pattern in persistent if re.search(pattern, body)}
        if found:
            writers[module.name] = found

    # The panel keeps three things on this machine and the policy must own all
    # three: the appearance choice, the display time zone, and — since #168 —
    # the accounts directory.
    described = {
        "appearance.js": "appearance",
        "timezone.js": "time zone",
        "accounts.js": "accounts",
        "engine.js": "engine",
    }
    missing = [name for name in writers
               if name in described and described[name].lower() not in storage_table.lower()]
    assert not missing, (
        "these modules write to a store that survives closing the panel, and the "
        f"policy's storage table does not mention what they keep: {missing}. Add "
        "a row saying WHAT is kept, WHERE, and WHO can read it — a reader of a "
        "privacy policy is asking exactly that.")

    unknown = sorted(set(writers) - set(described))
    assert not unknown, (
        f"{unknown} began persisting data and nobody decided what the policy "
        "should say about it. Add it to `described` above WITH its policy row, "
        "or stop persisting.")


def test_the_policy_does_not_claim_the_accounts_list_is_unstored():
    """The exact sentence that went false, guarded by its own test.

    A general rule would let this be reintroduced in different words; the
    specific claim is worth naming because it was published and wrong.
    """
    policy = POLICY.read_text(encoding="utf-8")
    scopes_row = [line for line in policy.splitlines()
                  if "userinfo.email" in line and "|" in line]
    assert scopes_row, "the policy no longer describes the userinfo scopes"
    assert "Nothing is stored" not in scopes_row[0], (
        "the policy says nothing is stored about the account details, and "
        "extension/accounts.js keeps a directory of them in chrome.storage.local")


# ---- the listing is the manifest, in prose ----------------------------------

LISTING = ROOT / "docs" / "store-listing.md"


def test_the_listing_justifies_every_permission_the_manifest_asks_for():
    """FOUND ON 2026-08-12, on the day the owner asked to upload the listing.

    Three host permissions had been added that day — drive/v3, upload/drive/v3
    and sheets.googleapis.com/v4 — and the listing justified none of them. The
    store requires a justification per permission and rejects a submission
    without one, so this would have been discovered by a rejection days later
    rather than by a build.

    Every other document in this repository that repeats the manifest is
    guarded: the privacy policy names every host, the version ledger names every
    capability. The listing was the one that was not, and it is the document
    Google actually reads.
    """
    listing = LISTING.read_text(encoding="utf-8")

    for permission in MANIFEST["permissions"]:
        assert f"`{permission}`" in listing, (
            f"the manifest asks for the {permission!r} permission and the store "
            "listing does not justify it; the store rejects a submission that "
            "leaves one unexplained")

    for host in MANIFEST["host_permissions"]:
        # Loopback is described as one entry covering both spellings, which is
        # how the listing reads and how a reviewer thinks about it.
        if host.startswith("http://127.0.0.1") or host.startswith("http://localhost"):
            assert "127.0.0.1" in listing
            continue
        assert host in listing, (
            f"the manifest may reach {host} and the store listing does not "
            "justify it")


def test_the_listing_claims_no_permission_the_manifest_dropped():
    """The other direction, and the one that reads as a lie rather than an
    omission: a listing describing access the extension gave up still declares
    it on the store's data-usage form."""
    listing = LISTING.read_text(encoding="utf-8")
    asked = set(MANIFEST["permissions"])
    hosts = " ".join(MANIFEST["host_permissions"])

    section = listing.split("## Permission justifications", 1)[-1]
    section = section.split("## OAuth scope justifications", 1)[0]

    for heading in re.findall(r"^### `([^`]+)`", section, re.M):
        if heading.startswith("http"):
            stem = heading.rstrip("*").rstrip("/")
            assert stem in hosts or "127.0.0.1" in heading, (
                f"the listing justifies {heading}, which the manifest no longer "
                "asks for")
        else:
            assert heading in asked, (
                f"the listing justifies the {heading!r} permission and the "
                "manifest does not ask for it")


def test_the_listing_names_the_version_being_submitted():
    """A listing headed with last month's version is the surest sign nobody
    re-read it before pressing submit."""
    listing = LISTING.read_text(encoding="utf-8")
    assert MANIFEST["version"] in listing.splitlines()[0], (
        f"the listing is headed {listing.splitlines()[0]!r} and the manifest is "
        f"at {MANIFEST['version']}")
