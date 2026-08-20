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
from urllib.parse import urlparse

pytestmark = [pytest.mark.extension, pytest.mark.docs]

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
        # The workbook exports are written into, once the owner picks one
        # through the Picker. It outlives the panel deliberately — choosing
        # where a business's data lands is not a decision to re-make daily —
        # and outliving the panel is exactly what puts it in this table.
        "app.js": "spreadsheet",
        # The Console remembers WHICH workbook holds the Excel add-in's
        # configuration, so the owner does not hunt for it every morning. Same
        # reasoning, different file — and the same row covers both, because a
        # reader asking "what does this keep about my Drive" wants one answer.
        "console.js": "spreadsheet",
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


# ---- the date is a claim like any other -------------------------------------

def _stated_date(document: pathlib.Path) -> str:
    """The `*Last updated: 6 August 2026*` line, as an ISO date."""
    import datetime

    text = document.read_text(encoding="utf-8")
    found = re.search(r"\*Last updated:\s*(.+?)\s*\*", text)
    assert found, f"{document.name} carries no 'Last updated' line"
    return datetime.datetime.strptime(
        found.group(1), "%d %B %Y").date().isoformat()


def _last_changed(document: pathlib.Path) -> str | None:
    """When this document's CONTENT last changed, or None if unknowable.

    Not `git log -1`. Correcting the date is itself a change to the file, so a
    guard measured that way demands the date be moved again, and again after
    that: the document would be perpetually one commit behind a line that exists
    only to describe it. The first version of this helper did exactly that and
    failed the moment its own correction was committed.

    So commits whose only effect on this file is the `Last updated` line are
    walked past. What remains answers the question actually being asked — has
    anything a reader would care about changed since the date printed at the top.
    """
    import subprocess

    relative = str(document.relative_to(ROOT))

    def git(*arguments: str) -> str | None:
        try:
            out = subprocess.run(["git", *arguments], cwd=ROOT,
                                 capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None
        return out.stdout if out.returncode == 0 else None

    # A SHALLOW CLONE ANSWERS CONFIDENTLY AND WRONGLY, which is worse than not
    # answering. HEAD is grafted, so git treats it as a root commit and
    # `git show` prints the WHOLE FILE as added lines — for every file, whether
    # or not that commit touched it. The date-only skip below then never
    # triggers and this helper returns HEAD's date for everything.
    #
    # That is not hypothetical: publish-docs.yml and release-extension.yml both
    # checked out at depth 1 and both run this file. They now fetch the full
    # history, and this refuses to guess if one ever stops.
    shallow = git("rev-parse", "--is-shallow-repository")
    if shallow is None or shallow.strip() == "true":
        return None

    history = git("log", "--format=%H %ad", "--date=short", "--", relative)
    if not history:
        return None

    for line in history.splitlines():
        commit, _, stamp = line.partition(" ")
        # --unified=0 so the surrounding unchanged lines are not mistaken for
        # the change itself.
        patch = git("show", "--format=", "--unified=0", commit, "--", relative)
        if patch is None:
            return stamp.strip() or None
        touched = [
            body for body in (
                text[1:] for text in patch.splitlines()
                if text[:1] in "+-" and not text.startswith(("+++", "---"))
            )
            if body.strip() and not body.lstrip().startswith("*Last updated:")
        ]
        if touched:
            return stamp.strip() or None

    # Every commit that ever touched it only moved the date. Nothing to be late
    # for.
    return None


@pytest.mark.parametrize("name", ["privacy-policy.md", "support.md"])
def test_the_last_updated_line_is_not_older_than_the_document(name):
    """A DATE NOBODY MAINTAINS IS A CLAIM NOBODY CHECKS.

    Found 2026-08-12. The policy was edited three times that day — the accounts
    directory, three new hosts, the storage table — and its line still read
    "6 August 2026". The PUBLISHED copy said the same, because publishing copies
    the file including its stale date.

    That is not a cosmetic slip. "Last updated" is the one line telling a reader
    whether what follows describes the software they are running, and a policy
    that has changed while claiming it has not is worse than one with no date at
    all: it invites the reader to skip re-reading it.

    Compared against git rather than against a hand-kept list, because the
    question is "did this file change after the date it claims" and git is the
    only thing that knows. A shallow checkout cannot answer, and that is a skip
    rather than a pass — a check that cannot run must not report success.
    """
    document = ROOT / "docs" / name
    changed = _last_changed(document)
    if changed is None:
        pytest.skip("no git history here — the comparison cannot be made")

    stated = _stated_date(document)
    assert stated >= changed, (
        f"{name} says it was last updated {stated} and git records a change on "
        f"{changed}. Set the line to the day of the change: a policy that has "
        "moved while claiming it has not is the one a reader trusts and should "
        "not.")


@pytest.mark.parametrize("name", ["privacy-policy.md", "support.md"])
def test_the_last_updated_line_is_not_in_the_future(name):
    """The other direction, and the easier mistake: a date typed forward to
    "cover" a change that has not happened yet describes a document nobody has
    written."""
    import datetime

    stated = _stated_date(ROOT / "docs" / name)
    today = datetime.date.today().isoformat()
    assert stated <= today, (
        f"{name} claims it was updated on {stated}, which has not happened yet")


# ---- the chooser page, which is PUBLIC ---------------------------------------

PICKER = ROOT / "docs" / "picker" / "scrapex-picker.html"


def test_the_picker_page_carries_no_secret():
    """THIS FILE IS SERVED FROM A PUBLIC WEBSITE. Anything in it is readable by
    anyone, for ever, including after it is deleted.

    The OAuth client id is public by design and lives in the manifest already.
    A client SECRET, a refresh token, or an unrestricted key is not, and the
    JSON Google hands over when a client is created carries the id and the
    secret side by side — which is exactly how one ends up pasted into a page.
    """
    page = PICKER.read_text(encoding="utf-8")

    assert "GOCSPX-" not in page, (
        "a Google client SECRET is in a page served to the public internet")
    assert "client_secret" not in page
    assert "refresh_token" not in page
    assert re.search(r"\bya29\.", page) is None, (
        "an access token is written into the page rather than passed to it")


def test_the_picker_answers_only_this_extension():
    """`externally_connectable` says who may TALK TO the extension. It says
    nothing about who this page may talk to, and a page that sent a chosen file
    to any id in its query string would hand the owner's document to whatever
    opened it."""
    page = PICKER.read_text(encoding="utf-8")

    assert "ALLOWED_EXTENSIONS" in page
    assert "ekcgggphcfdbjgfkcmjagehfjhijeang" in page, (
        "the page does not name the extension it is allowed to answer")
    assert "indexOf(handed.extension) === -1" in page, (
        "the extension id is read and not checked, so any id would be answered")


def test_no_access_token_is_ever_put_into_the_chooser_url():
    """THE FIRST VERSION OF THIS TEST GUARDED THE WRONG FILE.

    It asserted `"?token=" not in page` against scrapex-picker.html — a file
    that only ever READS a URL. The URL is built in extension/app.js, so the
    line the test was written to protect was never looked at.

    And the design it protected was itself wrong. Putting the token in the
    fragment defends against the server, which is not the reader that matters:
    chrome.tabs.create COMMITS the URL, and the committed URL is delivered whole
    — fragment included — to every extension holding the `tabs` permission,
    through onCreated and onUpdated. Erasing it in the page afterwards cannot
    help; the delivery has already happened.

    So the URL carries a single-use nonce, and this checks the file that builds
    it.
    """
    app_js = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")
    built = re.search(r"const url = `\$\{PICKER_PAGE\}([^`]*)`\s*\n?\s*\+ `([^`]*)`",
                      app_js)
    assert built, "extension/app.js no longer builds a chooser URL this test can read"
    url = built.group(1) + built.group(2)

    assert "token" not in url.lower(), (
        f"a token is placed in the chooser URL: {url!r}. Every extension with "
        "the `tabs` permission reads that, whether it is in the query or the "
        "fragment")
    assert "#n=${encodeURIComponent(nonce)}" in url, (
        f"the chooser URL carries {url!r} rather than a single-use nonce")


def test_the_nonce_is_spent_once_and_expires():
    """A nonce that could be replayed would be a token with extra steps."""
    background = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")

    trade = background[background.index("async function tradeNonceForToken"):]
    trade = trade[:trade.index("\n}\n")]

    assert 'handoff.nonce !== nonce' in trade, "the nonce is not compared at all"
    assert 'remove("scrapexPickerHandoff")' in trade, (
        "the handoff survives being used, so the nonce can be traded twice")
    assert trade.index('remove("scrapexPickerHandoff")') < trade.index("handoff.expires"), (
        "the handoff is removed only after the expiry check passes, so an "
        "EXPIRED nonce is left in place and a wrong guess is free to repeat")


def test_the_page_still_erases_what_it_was_given():
    """Only a nonce now, but a URL that still describes a handoff invites a
    reload that cannot work."""
    page = PICKER.read_text(encoding="utf-8")

    assert "location.hash" in page
    assert "history.replaceState" in page


def test_the_extension_admits_exactly_one_origin():
    matches = MANIFEST.get("externally_connectable", {}).get("matches", [])
    assert matches == ["https://muhammadbayoumi.github.io/*"], (
        f"externally_connectable admits {matches}; it must name one origin, and "
        "widening it opens the panel to every page on whatever it matches")


def test_the_receiver_checks_the_origin_again():
    """The manifest already restricts the sender, and the listener checks it
    anyway. A match pattern is one character away from being widened, and this
    listener is the last thing between a web page and the panel."""
    background = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")

    assert "onMessageExternal" in background
    assert 'origin !== PICKER_ORIGIN' in background, (
        "the external listener trusts whatever the manifest let through")
    assert 'message.kind !== "scrapex-picked-spreadsheet"' in background, (
        "any message shape from that origin is accepted")


def test_the_choice_is_not_written_to_disk():
    """A spreadsheet someone opened once is not a preference. `storage.session`
    is gone when the browser closes; `storage.local` would keep a record of a
    document nobody asked to be remembered."""
    background = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
    listener = background[background.index("onMessageExternal"):]
    listener = listener[:listener.index("\n});")]

    assert "storage.session" in listener
    assert "storage.local" not in listener, (
        "the chosen file is kept on disk after the browser closes")


def test_the_three_places_that_name_the_chooser_agree():
    """The panel opens an address; the manifest admits an origin; the listener
    checks one. Three files naming the same host in three syntaxes is three
    chances to move the page and leave the button opening nothing."""
    app_js = (ROOT / "extension" / "app.js").read_text(encoding="utf-8")
    background = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")

    page = re.search(r'PICKER_PAGE\s*=\s*"([^"]+)"', app_js)
    assert page, "app.js no longer names a chooser page"
    opened = urlparse(page.group(1))
    origin = f"{opened.scheme}://{opened.netloc}"

    checked = re.search(r'PICKER_ORIGIN\s*=\s*"([^"]+)"', background)
    assert checked, "background.js no longer names an origin to check"
    assert checked.group(1) == origin, (
        f"the panel opens {origin} but the listener only answers "
        f"{checked.group(1)}, so nothing chosen there can ever come back")

    admitted = MANIFEST["externally_connectable"]["matches"][0]
    assert admitted == f"{origin}/*", (
        f"the manifest admits {admitted} while the chooser is served from "
        f"{origin}")

    # The path matters to nobody but the person publishing the file, which is
    # exactly why it is written down.
    readme = (ROOT / "docs" / "picker" / "README.md").read_text(encoding="utf-8")
    assert page.group(1) in readme, (
        "docs/picker/README.md does not state the address the panel actually "
        "opens, so the file would be published to the wrong place")


def test_the_picker_key_is_a_browser_key_and_nothing_else():
    """The API_KEY slot is the one place in a public file where a secret would
    look at home. It sits beside a client id, it is called a key, and the JSON
    Google hands over when a client is created carries the SECRET under a
    neighbouring name — so the wrong string lands here by resemblance, not by
    carelessness.

    A browser API key has a shape: `AIza` and 35 more characters. A client
    secret (`GOCSPX-…`), a service-account private key, or an access token do
    not have it, and none of them belongs in a page the whole internet reads.
    """
    page = PICKER.read_text(encoding="utf-8")
    found = re.search(r'API_KEY\s*=\s*"([^"]*)"', page)
    assert found, "the picker page no longer has an API_KEY to check"

    key = found.group(1)
    if not key:
        return  # empty is the honest state before one exists; it refuses by name

    assert re.fullmatch(r"AIza[0-9A-Za-z_\-]{35}", key), (
        "API_KEY does not have the shape of a browser API key. If this is a "
        "client secret or a service-account key, it is now public and must be "
        "revoked, not merely deleted")


def test_the_key_restrictions_are_written_down_where_they_can_be_checked():
    """A key that is public is safe only because of restrictions that live in
    Google Cloud, where this repository cannot see them. Nothing here can prove
    they are set — so the least dishonest thing is to say exactly which two are
    relied upon, so a future reader can go and look."""
    readme = (ROOT / "docs" / "picker" / "README.md").read_text(encoding="utf-8")

    assert "Google Picker API" in readme
    assert "https://muhammadbayoumi.github.io/*" in readme, (
        "the README does not state the website restriction the key's safety "
        "rests on")
    assert re.search(r"referrer.{0,40}forge", readme, re.I | re.S), (
        "the README claims the website restriction protects the key without "
        "saying that a referrer header is forgeable outside a browser. That "
        "overstates it, and someone will rely on the overstatement")
