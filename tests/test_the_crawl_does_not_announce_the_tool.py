"""What a crawl calls itself, and the four levels that decide it.

The engine named this tool in every request — `ScrapeX/0.1 (+contact: owner)` —
which told every site it visited who was crawling, and bought nothing back:
"owner" is not an address anyone can write to, and no site keys a robots rule to
a name it has never seen. Everything else a site learns about the person running
a crawl comes from the network (the IP, the TLS handshake) or from politeness
itself (the pace, the 304s, the honoured Retry-After) and is not ours to
withhold. The agent string is the one part that is.

So these tests hold two things:

  * the default names NO tool, and cannot drift back to naming one; and
  * `resolve_user_agent` is the ONE place that decides, with each of its four
    levels genuinely able to beat the level below it.

The second half matters because the chain used to exist three times — in
`resolve_fetcher`, in the robots-inspection endpoint, and as a two-level version
inside the Settings template. Three readings of one question, and the panel's
reported browser agent would have had to land in all three or the page would
have shown an agent no crawl sends.

NOT a disguise that changes per request: one stable identity that still stops
the moment a site says stop. `HttpFetcher`'s doctrine refuses rotation, header
spoofing and CAPTCHA handling, and none of that is touched here.
"""
from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path

import pytest

from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.base import (DEFAULT_USER_AGENT, HttpFetcher,
                                     browser_headers, resolve_fetcher,
                                     resolve_user_agent)
from scrapex.vocab import ExtractKind, ExtractScope

ROOT = Path(__file__).resolve().parent.parent

# Deliberately NOT a Chrome string. A guard that distinguishes two levels must
# use values that cannot coincide with either the default or each other, or it
# passes for the wrong reason the day someone edits one of them.
DECLARED = "DeclaredBySource/9.9"
TYPED = "TypedByTheOwner/9.9"
REPORTED = "ReportedByThePanel/9.9"


def _code_only(path: Path) -> list[tuple[int, str]]:
    """The file's CODE, as (line number, text) — no comments, no docstrings.

    Both structural guards below failed on their first run against prose: a
    comment explaining the defect they forbid matched as the defect itself. A
    guard that cannot tell code from the paragraph describing it would force
    every future comment here to avoid naming what it is about.

    Ordinary string literals are KEPT, because `chosen.get("user_agent")` is the
    very shape the chain guard looks for.
    """
    text = path.read_text(encoding="utf-8")
    skip: set[tuple[int, int]] = set()
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT or (
                token.type == tokenize.STRING
                and token.string.lstrip("rbfuRBFU")[:3] in ('"""', "'''")):
            skip.update(range(token.start[0], token.end[0] + 1))
    return [(number, line)
            for number, line in enumerate(text.splitlines(), start=1)
            if number not in skip]


def make_entry(**over) -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="SOMESHOP", source_name="Some Shop",
        base_url="https://someshop.test", family="zid-html", currency="SAR",
        default_region="SA", vat_mode="incl",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES,
                             scope=ExtractScope.CENSUS)],
        **over))


# ---- the guarantee ---------------------------------------------------------

def test_the_default_agent_names_no_tool():
    """The whole point of the change, in one assertion.

    Spelled as a search for the PRODUCT name rather than for the old literal, so
    re-introducing it in any shape — `ScrapeX/0.2`, `scrapex-bot` — fails here
    too, not just an exact copy of the string that was removed.
    """
    assert "scrapex" not in DEFAULT_USER_AGENT.lower(), (
        f"the default agent announces this tool again: {DEFAULT_USER_AGENT!r}. "
        "The name buys nothing — it is no contact and no site has a rule for "
        "it — and it costs the one thing a request can withhold.")
    assert "contact" not in DEFAULT_USER_AGENT.lower(), (
        "the default agent promises a contact. `(+contact: owner)` was never "
        "an address anyone could reach, and a published tool would have sent "
        "that empty promise from every user's machine.")


def test_the_default_agent_is_the_string_the_repo_already_trusts():
    """One known-good UA in the repo, not two that can drift apart.

    sources.yaml declares this exact agent for ADVANCEDCASTLE because Zid 403s
    anything else. Two hand-written Chrome strings would be two things to keep
    current; this asserts they are one.
    """
    declared = (ROOT / "sources.yaml").read_text(encoding="utf-8")
    collapsed = re.sub(r"\s+", " ", declared)

    assert re.sub(r"\s+", " ", DEFAULT_USER_AGENT) in collapsed, (
        "DEFAULT_USER_AGENT no longer matches the agent sources.yaml declares "
        "for ADVANCEDCASTLE. Keep them identical, or the repo carries two "
        "Chrome strings that will age apart")


def test_no_request_can_be_made_without_an_agent():
    """An EMPTY agent is not anonymity — it is a rarer signature than a name.

    This is the bug class the Google Finance refresh actually shipped: the
    shipped default for `crawl_user_agent` is "", and a call site that passed it
    through unchanged sent `User-Agent: ` with nothing after it.
    """
    for nothing in ("", None):
        assert resolve_user_agent(nothing, {"user_agent": nothing}), (
            f"{nothing!r} resolved to a falsy agent, so the request would go "
            "out with an empty User-Agent header")


# ---- the four levels, each able to beat the one below ----------------------

def test_a_source_that_declares_an_agent_wins_over_everything():
    """Level 1. Zid 403s anything else (F5), so nothing global may override it."""
    agent = resolve_user_agent(DECLARED, {
        "user_agent": TYPED, "browser_user_agent": REPORTED})

    assert agent == DECLARED


def test_what_the_owner_typed_beats_what_the_browser_reported():
    """Level 2 over level 3. His word beats an automatic choice, always."""
    agent = resolve_user_agent(None, {
        "user_agent": TYPED, "browser_user_agent": REPORTED})

    assert agent == TYPED


def test_the_panel_browser_is_used_when_the_owner_typed_nothing():
    """Level 3 — the default path, and the reason for the change.

    It tracks the browser's real version as Chrome updates itself, so the agent
    never ages into a signature of its own; and a site watching one IP browse
    and crawl sees one agent rather than two.
    """
    agent = resolve_user_agent(None, {
        "user_agent": "", "browser_user_agent": REPORTED})

    assert agent == REPORTED


def test_the_built_in_agent_is_reached_only_when_nothing_else_answered():
    """Level 4 — no panel has ever spoken: the CLI and these tests."""
    assert resolve_user_agent(None, {}) == DEFAULT_USER_AGENT
    assert resolve_user_agent(None, None) == DEFAULT_USER_AGENT
    assert resolve_user_agent(
        None, {"user_agent": "", "browser_user_agent": ""}) == DEFAULT_USER_AGENT


@pytest.mark.parametrize("level,settings,expected", [
    ("declared", {"user_agent": TYPED, "browser_user_agent": REPORTED}, DECLARED),
    ("typed", {"user_agent": TYPED, "browser_user_agent": REPORTED}, TYPED),
    ("reported", {"browser_user_agent": REPORTED}, REPORTED),
])
def test_each_level_can_actually_be_reached(level, settings, expected):
    """The guards above must be able to FAIL, not merely to pass.

    Each case removes exactly the level being claimed and asserts the answer
    MOVES. A chain that returned its first non-empty value regardless of order
    would satisfy the three tests above and be caught here.
    """
    source = DECLARED if level == "declared" else None

    assert resolve_user_agent(source, settings) == expected

    without = dict(settings)
    if level == "declared":
        source = None
    else:
        without.pop("user_agent" if level == "typed" else "browser_user_agent")

    assert resolve_user_agent(source, without) != expected, (
        f"removing the {level} agent changed nothing, so that level is not "
        "what the assertion above was reading")


# ---- what actually reaches the wire ----------------------------------------

def test_the_fetcher_sends_what_the_chain_decided():
    """The chain is only worth testing if the client carries its answer."""
    fetcher = resolve_fetcher(make_entry(), {"browser_user_agent": REPORTED})
    try:
        assert fetcher._client.headers["user-agent"] == REPORTED
    finally:
        fetcher.close()


def test_a_declaring_source_still_reaches_the_wire_with_its_own_agent():
    fetcher = resolve_fetcher(make_entry(user_agent=DECLARED),
                              {"browser_user_agent": REPORTED})
    try:
        assert fetcher._client.headers["user-agent"] == DECLARED
    finally:
        fetcher.close()


def test_a_crawl_with_no_settings_at_all_still_names_no_tool():
    """The path a CLI run takes, end to end: no panel, no settings, no name."""
    fetcher = resolve_fetcher(make_entry())
    try:
        sent = fetcher._client.headers["user-agent"]
    finally:
        fetcher.close()

    assert sent == DEFAULT_USER_AGENT
    assert "scrapex" not in sent.lower()


def test_an_unnamed_fetcher_still_sends_a_real_agent():
    """`HttpFetcher()` built with no argument at all — the last way in."""
    fetcher = HttpFetcher()
    try:
        assert "scrapex" not in fetcher._client.headers["user-agent"].lower()
    finally:
        fetcher.close()


# ---- the headers that go with the agent ------------------------------------

def test_the_request_does_not_contradict_the_agent_it_claims():
    """A UA alone was the smaller half. Measured, the crawl sent 5 headers where
    Chrome sends 13 — so it announced Chrome and then described a client that
    does not exist."""
    sent = browser_headers(DEFAULT_USER_AGENT)

    for header in ("Accept", "Accept-Language", "Sec-CH-UA", "Sec-CH-UA-Mobile",
                   "Sec-CH-UA-Platform", "Sec-Fetch-Dest", "Sec-Fetch-Mode",
                   "Sec-Fetch-Site", "Sec-Fetch-User",
                   "Upgrade-Insecure-Requests"):
        assert header in sent, (
            f"{header} is not sent, so the request still reads as a client that "
            "claims a browser and does not behave like one")
    assert sent["Accept"] != "*/*", (
        "`Accept: */*` was the most visible tell after the agent itself; no "
        "browser sends it for a page")


def test_we_never_offer_an_encoding_we_cannot_read():
    """A header that lies about this build is worse than one that differs.

    `Accept-Encoding` was written as Chrome's literal `gzip, deflate, br, zstd`
    while `brotli` is not installed — so httpx had no `br` decoder and any
    server taking the offer would have answered with a body nothing here could
    read. A cosmetic difference from Chrome beats a body we cannot parse.
    """
    from httpx._decoders import SUPPORTED_DECODERS

    offered = [name.strip() for name
               in browser_headers(DEFAULT_USER_AGENT)["Accept-Encoding"].split(",")]

    assert offered, "no encoding is offered at all"
    for name in offered:
        assert name in SUPPORTED_DECODERS, (
            f"{name!r} is advertised and this build cannot decode it. A server "
            "that honours the offer sends a body the parse cannot read.")


def test_the_encoding_offer_follows_the_decoders_rather_than_a_list():
    """The guard above passes trivially against a hardcoded safe list. This is
    what makes it mechanical: installing brotli must start offering `br`."""
    import httpx._decoders as decoders

    original = dict(decoders.SUPPORTED_DECODERS)
    try:
        decoders.SUPPORTED_DECODERS["br"] = original["gzip"]
        offered = browser_headers(DEFAULT_USER_AGENT)["Accept-Encoding"]
    finally:
        decoders.SUPPORTED_DECODERS.clear()
        decoders.SUPPORTED_DECODERS.update(original)

    assert "br" in offered, (
        "a decoder was added and the offer did not follow it, so this is a "
        "hand-kept list that will drift from what the build can read")
    assert offered.index("gzip") < offered.index("br") < offered.index("zstd"), (
        f"the offer is not in Chrome's order: {offered!r}")


def test_the_hints_never_announce_a_different_version_than_the_agent():
    """THE MISMATCH THIS FUNCTION EXISTS TO PREVENT. A fixed `Sec-CH-UA` beside
    an agent that moves with Chrome is a contradiction no real browser
    produces — a cheaper tell than the tool name it replaced."""
    for version in ("125", "152", "203"):
        agent = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                 f"(KHTML, like Gecko) Chrome/{version}.0.0.0 Safari/537.36")

        hints = browser_headers(agent)["Sec-CH-UA"]

        assert f'"Google Chrome";v="{version}"' in hints, (
            f"the agent says Chrome {version} and the hints say {hints!r}")


def test_the_panels_own_hints_are_preferred_over_any_derived_ones():
    """Chrome's GREASE brand is deliberately underivable, so a computed header
    announces a browser that does not exist. What the panel reported wins."""
    reported = '"Chromium";v="152", "Odd?Brand";v="7"'

    assert browser_headers(DEFAULT_USER_AGENT, reported)["Sec-CH-UA"] == reported
    assert browser_headers(DEFAULT_USER_AGENT)["Sec-CH-UA"] != reported


def test_an_agent_that_is_not_chrome_gets_no_chrome_hints():
    """A source that declares its own agent means it (F5). `Sec-CH-UA` bolted
    onto a non-Chrome agent is the contradiction, not the cure."""
    sent = browser_headers(DECLARED)

    for header in ("Sec-CH-UA", "Sec-CH-UA-Mobile", "Sec-CH-UA-Platform"):
        assert header not in sent, (
            f"{header} was sent beside {DECLARED!r}, which claims no Chrome")
    assert sent["User-Agent"] == DECLARED


def test_the_platform_follows_the_agent():
    for needle, platform in (("Windows NT 10.0; Win64; x64", "Windows"),
                             ("Macintosh; Intel Mac OS X 10_15_7", "macOS"),
                             ("X11; Linux x86_64", "Linux")):
        agent = (f"Mozilla/5.0 ({needle}) AppleWebKit/537.36 "
                 "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36")

        assert browser_headers(agent)["Sec-CH-UA-Platform"] == f'"{platform}"'


def test_the_fetcher_sends_the_whole_set_not_just_the_agent():
    """Through the real constructor, because a function nothing calls is not a
    fix."""
    fetcher = resolve_fetcher(make_entry(), {
        "browser_user_agent": DEFAULT_USER_AGENT,
        "client_hints": '"Chromium";v="152"'})
    try:
        sent = fetcher._client.headers
        assert sent["sec-ch-ua"] == '"Chromium";v="152"'
        assert sent["accept-language"]
        assert sent["upgrade-insecure-requests"] == "1"
    finally:
        fetcher.close()


def test_the_panels_hints_never_ride_beside_a_different_agent():
    """The hints describe ONE browser. Sending this machine's brands beside a
    source's declared agent, or beside one the owner typed, re-creates exactly
    the mismatch they exist to remove.

    THE AGENTS HERE ARE CHROME-SHAPED ON PURPOSE. Written with the non-Chrome
    `DECLARED`/`TYPED` above, this passed against a build with the gating
    deleted — `browser_headers` was returning early because the agent named no
    Chrome, so a DIFFERENT guard was satisfying the assertion and this one
    tested nothing. A mutation caught it. To read the gating, the agent has to
    be one that would otherwise get hints.
    """
    # Both Chrome, and neither is the panel's. If the gating goes, the panel's
    # 152 brands appear beside an agent announcing 99.
    old_chrome = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/99.0.0.0 Safari/537.36")
    panel_hints = '"Chromium";v="152", "Odd?Brand";v="7"'

    for label, settings, source_agent in (
            ("declared by the source", {"client_hints": panel_hints}, old_chrome),
            ("typed by the owner",
             {"user_agent": old_chrome, "client_hints": panel_hints}, None)):
        fetcher = resolve_fetcher(make_entry(user_agent=source_agent), settings)
        try:
            sent = fetcher._client.headers["sec-ch-ua"]
        finally:
            fetcher.close()

        assert sent != panel_hints, (
            f"the panel's brands were sent beside an agent {label}, so the "
            "request claims one browser in its agent and another in its hints")
        assert '"Google Chrome";v="99"' in sent, (
            f"the hints beside an agent {label} do not describe that agent")


# ---- one definition, not three ---------------------------------------------

def test_nothing_rebuilds_the_chain_for_itself():
    """The duplication that made this change three edits instead of one.

    `resolve_fetcher`, the robots-inspection endpoint and the Settings template
    each read the same question their own way. The template's copy knew nothing
    of the panel's reported agent, so it would have displayed a string no crawl
    sends — a page that answers the wrong question confidently.

    Asked as "who names the fallback?" rather than by matching the shape of an
    `or` chain. The first draft of this guard matched the shape and flagged
    three lines of `crawl_delay(agent) or crawl_delay("*")` — robots' delay
    fallback, a different question wearing the same clothes. A module that
    builds its own agent fallback has to name `DEFAULT_USER_AGENT` to do it, so
    naming it anywhere outside the module that decides is the real signal.
    """
    offenders = []
    for path in sorted((ROOT / "scrapex").rglob("*.py")):
        if path.name == "base.py" and path.parent.name == "connectors":
            continue
        for number, line in _code_only(path):
            if "DEFAULT_USER_AGENT" in line:
                offenders.append(f"{path.relative_to(ROOT)}:{number}")

    assert not offenders, (
        f"{offenders} reaches for DEFAULT_USER_AGENT directly, which means it "
        "is deciding the agent for itself. One place decides — "
        "`connectors.base.resolve_user_agent` — and the second copy is exactly "
        "how the robots endpoint and the Settings page came to answer this "
        "question without knowing about the agent the panel reports")


def test_the_settings_page_shows_the_agent_that_is_actually_sent():
    """The template's own copy of the chain, and why it could not stay.

    It rendered `crawl_user_agent.value or about.default_user_agent` — a
    two-level reading that skipped the panel's reported agent entirely. Left
    alone it would have shown the built-in fallback to an owner whose every
    crawl was going out as his own Chrome.
    """
    page = (ROOT / "scrapex" / "webui" / "templates"
            / "settings.html").read_text(encoding="utf-8")

    assert "about.effective_user_agent" in page, (
        "the Settings page stopped showing the agent the engine resolved")
    assert "about.default_user_agent" not in page, (
        "the page rebuilt the fallback chain in Jinja again, so it can once "
        "more display an agent no crawl would send")


def test_robots_still_reaches_a_site_that_wrote_no_rule_for_us():
    """THE politeness question, asked of the new agent.

    robots matching keys on the token before the first "/" (`robots.py`), so the
    old default matched a `User-agent: ScrapeX` rule and the new one matches
    `User-agent: Mozilla`. No site has written either, and the answer that
    matters is that a site's `*` rules still bind us — hiding the tool's name
    must not quietly widen what it may crawl.
    """
    from scrapex.robots import inspect

    robots = ("User-agent: *\n"
              "Crawl-delay: 7\n"
              "Disallow: /private\n")

    report = inspect("https://shop.test/private", robots,
                     user_agent=DEFAULT_USER_AGENT)

    assert report.crawl_delay_s == 7.0, (
        "a site's asked-for pace stopped applying when the agent stopped "
        "naming this tool")
    assert report.base_url_disallowed is True, (
        "a site's Disallow stopped applying to us. Anonymity may not widen "
        "what a crawl is allowed to take")
    assert report.names_us == "", (
        "the new default matched a site's rule BY NAME, which means the agent "
        "is identifying this tool to robots after all")


def test_the_rate_refresh_does_not_splat_settings_into_the_fetcher():
    """The defect this change had to fix to avoid crashing on it.

    `HttpFetcher(**crawl_settings(conn))` tied that call to crawl_settings' key
    set, which nothing enforced — and it passed `user_agent=""` straight
    through, so every Google Finance refresh went out with an EMPTY User-Agent
    header while every crawl sent a real one. Adding a key to crawl_settings
    would have turned that silent defect into a TypeError.
    """
    source = "\n".join(
        line for _, line in _code_only(ROOT / "scrapex" / "webui" / "app.py"))

    assert "HttpFetcher(**crawl_settings" not in source, (
        "the rate refresh splats crawl settings into HttpFetcher again. Name "
        "the arguments: the splat sent an empty User-Agent for as long as the "
        "owner typed none, and it breaks on the next key crawl_settings grows")


def test_the_engine_carries_the_panels_agent_to_the_crawl():
    """The wiring, not the value: a setting nothing reads is a setting nobody has."""
    capture = (ROOT / "scrapex" / "capture.py").read_text(encoding="utf-8")

    assert "crawl_browser_user_agent" in capture, (
        "crawl_settings no longer reads the agent the panel reports, so the "
        "panel writes a setting the crawl never sees")
