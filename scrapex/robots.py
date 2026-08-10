"""What a site's robots.txt says, and whose decision it is.

Until now this was one ruling for every source, written down in
docs/robots-policy.md on 2026-07-22: Crawl-delay enforced, Disallow
informational. That was the right call for twelve shops the owner already knew.
It stops being right the moment the product crawls a site he has not read.

So the ruling moves from the repository to the source, in three steps that are
deliberately separate:

  1. LOOK. `inspect()` fetches robots.txt and says what it actually contains --
     for THIS crawler, at THIS base url. Not a summary of the file: the rules
     that would touch the paths this source crawls.
  2. CHOOSE. Each source carries `robots: default | obey | custom`.
  3. ENFORCE. `decide()` turns the choice plus the file into two answers the
     fetcher can act on: may this url be fetched, and how long to wait.

WHY LOOKING IS ITS OWN STEP. A choice offered before the facts is a guess with
a dropdown around it. The owner cannot sensibly pick "obey" for a site until he
knows whether obeying means a five-second delay or an empty crawl -- and the
only honest way to tell him is to read the file and show him.

NOTHING HERE FETCHES A PAGE. This module reads robots.txt and answers
questions. The walking, the pacing and the request budget stay where they were.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser


class RobotsChoice(StrEnum):
    """What one source does about robots.txt.

    A string would have done and would have let "Obey" or "obeys" through to be
    compared against "obey" and silently fall back to the default -- which is
    the one outcome nobody would notice, because the default is what happens
    when a source has said nothing at all.
    """

    #: Whatever the tool-wide setting says. The value a source has until the
    #: owner decides otherwise, so changing the setting moves every source that
    #: never asked for anything different.
    DEFAULT = "default"

    #: This site's robots.txt is followed: a disallowed url is not fetched, and
    #: its Crawl-delay wins over our pace whenever it is longer.
    OBEY = "obey"

    #: This site, and only this site, gets the rule written beside it.
    CUSTOM = "custom"


@dataclass(frozen=True)
class RobotsCustom:
    """The per-site rule, holding exactly what robots.txt itself controls.

    Two knobs and no more, on purpose. robots.txt grants a site two powers over
    a crawler -- where it may go and how fast -- so a custom rule that answered
    anything else would be answering a question the file never asked.
    """

    #: False is today's shipped behaviour: crawl the path and disclose it.
    enforce_disallow: bool = False
    #: None means "whatever the site asked for". A number overrides it, and
    #: overriding DOWNWARDS is the one that needs the owner's eyes -- which is
    #: why `decide` reports it rather than doing it quietly.
    crawl_delay_s: float | None = None


@dataclass(frozen=True)
class RobotsRule:
    """One line of robots.txt that touches this source, in plain terms."""

    kind: str            # "disallow" | "allow" | "crawl-delay" | "named-us"
    value: str
    #: Which User-agent block it came from, verbatim -- "*" or a name.
    agent: str


@dataclass
class RobotsReport:
    """What the site says, for this crawler, at this base url.

    This is the LOOK step's whole output, and it is shaped for a person: the
    fields answer the questions someone asks before choosing, in the order they
    ask them.
    """

    host: str
    #: False when there is no robots.txt, or it could not be read. A site with
    #: no file has not refused anything -- that is not the same as permitting
    #: everything, but it is the same for what a crawler may do.
    found: bool = False
    #: The file named this crawler's user agent specifically, rather than only
    #: matching it through `*`. The most important single fact in the report:
    #: a site that names you has thought about you.
    names_us: str = ""
    #: The site asks every crawler like us to wait this long, in seconds.
    crawl_delay_s: float | None = None
    #: Whether the base url itself is off limits. If this is True, "obey" means
    #: this source cannot be crawled at all, and the owner needs to know that
    #: BEFORE choosing it rather than by watching an empty run.
    base_url_disallowed: bool = False
    #: The rules that would bear on this source, for showing to a person.
    rules: list[RobotsRule] = field(default_factory=list)
    #: Set when the file could not be read at all, so "no rules" is never
    #: mistaken for "nothing to obey".
    unreadable: str = ""

    @property
    def obeying_would_block_everything(self) -> bool:
        """The answer that decides whether `obey` is even usable here."""
        return self.found and self.base_url_disallowed

    def summary(self) -> str:
        """One sentence, for a log line or a panel subtitle."""
        if self.unreadable:
            return f"{self.host}: robots.txt could not be read ({self.unreadable})"
        if not self.found:
            return f"{self.host}: no robots.txt — the site asks for nothing"
        parts = []
        if self.names_us:
            parts.append(f"names {self.names_us} specifically")
        if self.base_url_disallowed:
            parts.append("disallows the pages this source crawls")
        if self.crawl_delay_s:
            parts.append(f"asks for {self.crawl_delay_s:g}s between requests")
        return f"{self.host}: " + (", ".join(parts) if parts
                                   else "allows this source, asks for no delay")


def _parse(text: str) -> tuple[RobotFileParser, list[tuple[str, str, str]]]:
    """The stdlib parser for decisions, and the raw lines for showing a person.

    Both, because `RobotFileParser` answers questions correctly and cannot be
    asked what it read -- and a report that says "disallowed" without the line
    that disallowed it is asking the owner to take our word for it.
    """
    parser = RobotFileParser()
    parser.parse(text.splitlines())

    lines: list[tuple[str, str, str]] = []
    agent = "*"
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        name, _, value = line.partition(":")
        name, value = name.strip().lower(), value.strip()
        if name == "user-agent":
            agent = value
        elif name in ("disallow", "allow", "crawl-delay"):
            lines.append((agent, name, value))
    return parser, lines


def inspect(base_url: str, robots_text: str | None, *,
            user_agent: str = "*", unreadable: str = "") -> RobotsReport:
    """Turn a robots.txt into what it MEANS for one source.

    The text is passed in rather than fetched: this module has no opinion about
    HTTP, and a test that had to stand up a server to ask "what does this file
    mean" would be testing the server.
    """
    host = urlsplit(base_url).netloc or base_url
    if unreadable:
        return RobotsReport(host=host, unreadable=unreadable)
    if robots_text is None:
        return RobotsReport(host=host, found=False)

    parser, lines = _parse(robots_text)
    report = RobotsReport(host=host, found=True)

    # Does the file name US, or only reach us through `*`? Compared on the
    # leading token because a user agent string carries a version and a contact
    # url, and robots.txt names products, not builds.
    ours = (user_agent or "*").split("/", 1)[0].strip().lower()
    for agent, kind, value in lines:
        if ours and agent.lower() == ours:
            report.names_us = agent
        if agent.lower() in (ours, "*"):
            report.rules.append(RobotsRule(kind=kind, value=value, agent=agent))

    delay = parser.crawl_delay(user_agent) or parser.crawl_delay("*")
    report.crawl_delay_s = float(delay) if delay else None
    report.base_url_disallowed = not parser.can_fetch(user_agent, base_url)
    return report


@dataclass(frozen=True)
class Decision:
    """What the fetcher does about one url, and why -- the why is not optional.

    Every field here ends up in the job log. A crawl that was slower, or that
    skipped pages, must be explainable afterwards without re-reading the code:
    "this took an hour because muqawil asked for 5 seconds and SLOWSHOP is set
    to obey" is a sentence the owner can act on.
    """

    may_fetch: bool
    #: None leaves the caller's own pace alone.
    delay_s: float | None
    reason: str


def decide(report: RobotsReport, choice: RobotsChoice, *,
           custom: RobotsCustom | None = None,
           tool_default_obeys: bool = False,
           url_disallowed: bool = False) -> Decision:
    """Resolve one source's choice against what the site said.

    `tool_default_obeys` is the settings value, passed in rather than read:
    this module must stay usable from a test that never touches a database.
    """
    if choice is RobotsChoice.CUSTOM and custom is None:
        # Refused rather than defaulted, because the obvious default -- the
        # tool-wide setting -- is the very thing the owner chose CUSTOM to get
        # away from, and it would arrive wearing his own label.
        raise ValueError(
            "this source is set to a custom robots rule and none is stored. "
            "Choose 'default' or 'obey', or write the custom rule.")

    if not report.found or report.unreadable:
        why = report.unreadable or "no robots.txt"
        return Decision(may_fetch=True, delay_s=None,
                        reason=f"{report.host}: {why} — nothing to obey")

    if choice is RobotsChoice.OBEY:
        enforce, delay = True, report.crawl_delay_s
        label = "set to obey this site's robots.txt"
    elif choice is RobotsChoice.CUSTOM:
        enforce = custom.enforce_disallow
        delay = report.crawl_delay_s if custom.crawl_delay_s is None else custom.crawl_delay_s
        label = "a custom rule for this site"
    else:
        enforce, delay = tool_default_obeys, report.crawl_delay_s
        label = ("the tool default, which obeys Disallow" if tool_default_obeys
                 else "the tool default, which discloses Disallow and crawls anyway")

    if url_disallowed and enforce:
        return Decision(may_fetch=False, delay_s=delay,
                        reason=f"{report.host}: robots.txt disallows this path, and "
                               f"this source is {label} — not fetched")
    if url_disallowed:
        return Decision(may_fetch=True, delay_s=delay,
                        reason=f"{report.host}: robots.txt disallows this path; "
                               f"crawled anyway under {label}")
    return Decision(may_fetch=True, delay_s=delay,
                    reason=f"{report.host}: allowed under {label}")
