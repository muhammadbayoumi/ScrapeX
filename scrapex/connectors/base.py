"""Connector contract + fetchers (ENGINEERING.md A1, A2, A3, F5, S7).

One SiteConnector per source; families share base classes ONLY once proven
(A3). Connectors never import each other; everything downstream of FetchAsync
is uniform: ScrapedTable -> funnel payload -> ingest.
"""
from __future__ import annotations

import random
import ssl
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    # Named here so the annotation on `_robots_reports` resolves for a reader
    # and for a checker. The RUNTIME import stays inside `_request`, where the
    # module is actually used — scrapex.robots imports nothing from here, but
    # keeping the runtime edge where it is costs nothing and adds no cycle.
    from ..robots import RobotsReport

import httpx

from ..config import SourceEntry
from ..payload import FunnelPayload, new_payload, utc_now_iso
from ..vocab import ExtractKind, Fetcher, PayloadClient

# A single honest, stable UA for all HTTP fetching (F5). Zid/WAF sites that
# 403 generic clients get a browser UA via SourceEntry notes + per-family
# override — explicitly, per connector, never silently global.
DEFAULT_USER_AGENT = "ScrapeX/0.1 (+contact: owner)"

# WHY ONE SHARED SSL CONTEXT (2026-07-31)
#
# Every httpx.Client() builds its own, and building one here costs 1.6 SECONDS —
# not on the network, before a single byte is sent. cProfile puts 5.921s of 5.929s
# for three constructions inside one C call: _ssl._SSLContext.load_verify_locations.
# certifi's cacert.pem is 240 KB and this box has resident on-access AV, so OpenSSL
# re-reads it through the scanner every time. Same certificates from memory
# (cadata) cost 139 ms, so it is the file read, not the parse. Measured here:
#
#   httpx.Client()                          1633.1 ms
#   httpx.Client(verify=<shared context>)       0.6 ms      2700x
#
# It does NOT amortise: six consecutive builds ran 4083, 1744, 2121, 2503, 1675,
# 1601 ms. Nothing about that is ScrapeX's doing. What WAS ours is how often we
# paid it. The job worker built a fetcher on every poll while holding the
# warehouse write lock (jobs.py), so an idle engine burned ~42% of a core and
# stalled the owner's job inserts; the test suite paid it 37 times per run
# (10% of total wall clock).
#
# The context is built once, lazily, and shared. ssl.SSLContext is documented as
# safe for concurrent use once configured and nothing here mutates it afterwards.
# Verification is UNCHANGED — this is httpx's own default context, built via
# httpx.create_ssl_context(), just not rebuilt per client.
_SSL_CONTEXT: ssl.SSLContext | None = None
_SSL_CONTEXT_LOCK = threading.Lock()


def shared_ssl_context() -> ssl.SSLContext:
    """httpx's default CA-verifying context, built once per process."""
    global _SSL_CONTEXT
    if _SSL_CONTEXT is None:
        with _SSL_CONTEXT_LOCK:
            if _SSL_CONTEXT is None:      # another thread may have won the race
                _SSL_CONTEXT = httpx.create_ssl_context()
    return _SSL_CONTEXT


@dataclass
class ScrapedTable:
    """The raw normalized-row shape EVERY connector emits.

    Deliberately header[] + rows[][] of raw strings — the same shape the
    add-in's StreamingTsvReader yields, so downstream mapping is uniform and
    typing/cleaning happens once, later, in normalize + ingest (Q2).
    """

    source_key: str
    kind: ExtractKind
    source_url: str
    header: list[str]
    rows: list[list[str]] = field(default_factory=list)
    # Parts of a multi-page source that failed while the rest succeeded. Carrying
    # on when one page breaks is correct (Q3); silently dropping the fact that it
    # broke is not. GPP hid a whole energy type this way — four pages parsed,
    # electricity matched nothing, and the run reported plain success.
    # Deliberately NOT in to_payload: this describes the RUN, not the data, and
    # the payload contract is frozen across engines.
    warnings: list[str] = field(default_factory=list)
    # A warning says something went wrong and was contained. A DEFECT says more:
    # the data this run produced is KNOWN to be degraded, so the run may not be
    # reported clean. capture seeds these into the ingest result's errors, which
    # is what crawl_run.errors_count counts and what S8 alerts on. The distinction
    # is not academic: magento's English store failing was a warning, and that
    # warning was the only trace of a half-brand rewriting the price identity of
    # every offer the source publishes.
    defects: list[str] = field(default_factory=list)
    # Resume checkpoint for a multi-page source: a filename-safe id
    # ([A-Za-z0-9_-]) for the PAGE this table came from, empty when the
    # connector is single-page. The job journal embeds it in the payload's
    # FILENAME — never in the payload itself (same frozen-contract rule as
    # warnings) — and hands the journaled tokens back to the connector as
    # skip_tokens on resume, so a paused 400-page crawl re-fetches only what
    # it has not already fetched.
    page_token: str = ""
    # Exchange rates the SITE ITSELF publishes: ISO code -> units per USD.
    # A storefront that prices for more than one country prints the rate it
    # converts with in its own page bootstrap. That number is a fact ABOUT THE
    # SOURCE, not a row of its data, so it travels the same road as warnings
    # and defects and is deliberately NOT in to_payload — the payload contract
    # is frozen across engines. capture writes these to currency_rate under
    # source_kind='shop', where 0054 guarantees a storefront's rate can never
    # be read as a market rate.
    published_rates: dict[str, float] = field(default_factory=dict)

    def to_payload(self, client: PayloadClient = PayloadClient.CLI, run_ref: str | None = None) -> FunnelPayload:
        return new_payload(
            source_key=self.source_key,
            kind=self.kind,
            client=client,
            scraped_at=utc_now_iso(),
            source_url=self.source_url,
            header=self.header,
            rows=self.rows,
            run_ref=run_ref,
        )


@runtime_checkable
class SiteConnector(Protocol):
    """One implementation per source. The ONLY site-specific code in the system."""

    connector_id: str

    def fetch(self, source: SourceEntry) -> Iterable[ScrapedTable]:
        """Fetch + parse this source into raw tables. Implementations own:
        transport choice, pagination, encoding, selectors, shape assertions (Q4).
        Yield one ScrapedTable per logical table (streaming, F3)."""
        ...


class ConnectorRegistry:
    """source_key -> connector. Explicit registration, no magic discovery (P5)."""

    def __init__(self) -> None:
        self._by_source: dict[str, SiteConnector] = {}

    def register(self, source_key: str, connector: SiteConnector) -> None:
        if source_key in self._by_source:
            raise ValueError(f"connector already registered for {source_key!r}")
        self._by_source[source_key] = connector

    def get(self, source_key: str) -> SiteConnector:
        try:
            return self._by_source[source_key]
        except KeyError:
            raise KeyError(
                f"no connector registered for {source_key!r} — is its module imported?"
            ) from None


class CrawlBlocked(RuntimeError):
    """The site is refusing us repeatedly. Stop the run; do not keep pushing."""


class CrawlInterrupted(CrawlBlocked):
    """The OWNER asked this run to stop, mid-fetch.

    Subclasses CrawlBlocked deliberately: every connector isolates per-page
    errors with a broad except but re-raises CrawlBlocked explicitly, so the
    interrupt inherits guaranteed propagation through all of them — a fresh
    exception type would be swallowed by the first `except Exception` page
    guard and the run would sail on for another quarter hour.
    """

    def __init__(self, control: str):
        super().__init__(f"the owner asked to {control} this run")
        self.control = control


def declare_frontier(fetcher, pages: int) -> None:
    """"I now know I will fetch `pages` more pages" — for any fetcher, or none.

    THE ONE GUARD, so no connector grows its own. A connector is handed whatever
    fetcher its caller built, and the connector tests build minimal fakes with
    just the methods under test: reaching straight for `expect_requests` turned a
    progress-display improvement into an AttributeError that failed real crawls
    of magento and salla. A display fact must never be able to do that.

    The fetcher, when it can hear this, uses it to give the Activity panel a
    denominator that is a count rather than a guess (HttpFetcher.expect_requests).
    A fetcher that cannot falls back to the panel's dated estimate, which is a
    worse number and an honest one.
    """
    declare = getattr(fetcher, "expect_requests", None)
    if declare is None:
        return
    try:
        declare(pages)
    except Exception:
        pass


class RobotsDisallowed(RuntimeError):
    """This source is set to obey robots.txt, and robots.txt said no.

    Its own class because the alternative -- returning nothing, or a 403-shaped
    failure -- makes a deliberate refusal indistinguishable from a site being
    down, and those need opposite responses from the owner.
    """


class HttpFetcher:
    """Shared polite HTTP transport (F5): rate-limited, retrying, one UA.

    Connectors receive a fetcher; they never build their own httpx client, so
    politeness and retry policy stay in one place (Q1).

    STAYING UNBLOCKED ACROSS A LARGE CRAWL
    --------------------------------------
    A source like globalpetrolprices needs ~845 country pages for original
    local-currency prices. The way through that is not to look less like a bot;
    it is to cost the server almost nothing and to stop the moment it objects.
    Four mechanisms, in order of how much they help:

    1. CONDITIONAL REQUESTS. Every response's ETag / Last-Modified is kept and
       replayed on the next crawl. An unchanged page then answers 304 with no
       body at all. Prices move weekly, so after the first pass the great
       majority of a re-crawl is 304s — cheaper for the server than for us, and
       the single biggest reason a large recurring crawl stays welcome.
    2. BACK OFF WHEN TOLD TO. 429 and 503 are honoured, including Retry-After,
       with exponential backoff. This was documented as "retrying" and was not
       implemented at all: any 429 simply raised and killed the run.
    3. JITTER. A request exactly every 1.000s is a machine signature and hits
       rate limiters in phase. The interval is randomised around its base.
    4. A CIRCUIT BREAKER. After enough consecutive refusals the run raises
       CrawlBlocked instead of hammering a site that has already said no.

    Deliberately NOT here: user-agent rotation, proxy rotation, header
    spoofing, CAPTCHA handling. Those evade a decision the site has made. The
    UA stays honest and contactable, and when the site says stop, we stop.
    """

    # Refusals in a row before we accept that the answer is no.
    BLOCK_LIMIT = 5
    # Exponential-backoff ceiling for OUR OWN retries.
    MAX_BACKOFF_S = 120.0
    # A server-named Retry-After is the site telling us its price; honouring
    # two minutes of a requested hour is not honouring it. 15 minutes is the
    # most a single retry will wait — beyond that the wait is noted and capped,
    # not silently shrunk to 120s as before.
    MAX_RETRY_AFTER_S = 900.0
    RETRY_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})
    # Statuses that may mean "not in that shape" rather than "not at all", and
    # so are worth one attempt without the optional parameters. 429 is NOT here:
    # it is about pace, and asking again immediately in any shape is the one
    # thing a rate-limited site has just told us not to do.
    DROP_STATUSES = frozenset({400, 403, 404, 414, 422})

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        min_interval_s: float = 1.0,  # F5: <= 1 req/s default
        timeout_s: float = 30.0,
        max_attempts: int = 3,
        jitter: float = 0.3,          # +/- 30% around the base interval
        honour_crawl_delay: bool = True,
                 robots_choice: str = "default",
                 robots_custom: dict | None = None,
                 obey_disallow: bool = False,
    ) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout_s,
            follow_redirects=True,
            verify=shared_ssl_context(),   # see the note above: 1633ms -> 0.6ms
        )
        self._min_interval_s = min_interval_s
        self._last_request_at = 0.0
        self._max_attempts = max(1, max_attempts)
        self._jitter = max(0.0, min(jitter, 0.9))
        self._consecutive_refusals = 0
        # host -> parsed robots.txt (None = fetched and unusable). Loaded
        # lazily on the first request to each host. The manifest promised
        # "robots crawl-delay 10s — honored" for ELBUROJ and NOTHING read
        # robots.txt at all; a promise in a comment is not a mechanism.
        self._robots: dict[str, object] = {}
        #: host -> the file as it arrived, for the report.
        self._robots_text: dict[str, str] = {}
        self._user_agent = user_agent
        # The owner's per-run choice (2026-07-28). Default TRUE: a crawler that
        # ignores a site's asked-for pace by default is one that gets the owner
        # blocked without him choosing it. Turning it off is his to make and is
        # recorded in the run's warnings either way, so a job's log always says
        # which pace it ran at — otherwise a fast crawl and a polite one look
        # identical afterwards.
        self._honour_crawl_delay = honour_crawl_delay
        # WHOSE DECISION THIS FETCHER CARRIES. Passed in rather than read from
        # settings here, because one crawl can run several sources and each may
        # have answered differently -- a fetcher that looked the answer up would
        # give them all the same one.
        self._robots_choice = robots_choice
        self._robots_custom = robots_custom
        # NAMED EXACTLY AS THE SETTING IS, because `HttpFetcher(**crawl_settings(
        # conn))` is a real call site: a parameter whose name drifts from its
        # settings key is a TypeError the moment somebody adds the setting.
        # tests/test_http_fetcher.py pins the two together.
        self._obey_disallow = obey_disallow
        #: host -> RobotsReport, so the file is read once and the report can be
        #: shown to the owner afterwards without fetching it again. Typed as the
        #: real thing rather than `object`: it was the latter, so nothing checked
        #: what went in, and `decide()` -- which needs a RobotsReport -- was
        #: being handed something the type system knew nothing about.
        self._robots_reports: dict[str, RobotsReport] = {}
        self.robots_warnings: list[str] = []
        # url -> {"ETag": ..., "Last-Modified": ...}, replayed on the next visit.
        self._validators: dict[str, dict[str, str]] = {}
        self.requests_count = 0   # recorded into crawl_run (F5 accounting)
        self.not_modified_count = 0
        self.retry_count = 0
        #: Requests this run had to make in a costlier shape because the site
        #: refused the efficient one. Read into the run's warnings — a crawl
        #: that quietly costs ten times the requests is a bill nobody sees.
        self.degradations: list[str] = []
        #: (host, parameter) pairs proven refused, so the lesson is asked once
        #: on that host and never leaked to a second host the same connector
        #: happens to visit. A parameter name alone is not a site decision.
        self._refused_params: set[tuple[str, str]] = set()
        # How many requests this crawl expects to make IN TOTAL, once something
        # actually knows. None until then, and None is the honest answer: a
        # sitemap-driven connector learns its frontier before it fetches a
        # single product page, while a connector that discovers pages as it
        # walks genuinely cannot know, and must not be made to guess.
        #
        # It lives here because this object is already the one counting
        # requests: an expectation in a different unit from the count it is
        # compared against is how a progress bar starts lying. See
        # expect_requests below for the one arithmetic rule.
        self.expected_requests: int | None = None
        # Optional live-progress hook, called after EVERY completed request with
        # (requests_count, url). A 450-page country crawl used to be a quarter
        # hour of total silence — 0/1 sources, zero requests, a start-time
        # heartbeat — indistinguishable from a hang while everything was fine.
        # The display's failure must never become the crawl's: the call site
        # guards the hook.
        self.on_request = None
        # Called once with the new total whenever expect_requests raises it, so
        # a denominator reaches the panel the moment it is known instead of at
        # the next throttled request tick.
        self.on_expectation = None

    # ---- what this crawl expects to cost ------------------------------------

    def expect_requests(self, pages: int) -> None:
        """A connector declaring "I now know I will fetch `pages` more pages".

        Counted FROM THE REQUESTS ALREADY MADE, because that is the only way the
        expectation stays in the same unit as the counter it will be compared
        with: reading a sitemap index costs real requests before the frontier is
        known, and an expectation that ignored them would be short by exactly
        those pages and the bar would arrive at 100% early.

        The declaration only ever goes UP. A connector that enumerates a second
        frontier (a second sitemap, a second category tree) is adding to what it
        will fetch, not replacing it — and a bar that shrank mid-crawl would be
        the same lie in the other direction.

        The number remains an EXPECTATION and every screen that shows it says
        so: a retry, a 404 or a variant page can still make the real count
        differ. It is not a budget and nothing here enforces it.
        """
        try:
            more = int(pages)
        except (TypeError, ValueError):
            return                      # a display input never breaks a crawl
        if more < 0:
            return
        declared = self.requests_count + more
        if self.expected_requests is None or declared > self.expected_requests:
            self.expected_requests = declared
            if self.on_expectation is not None:
                # Published NOW rather than at the next request tick. That tick
                # is throttled to every tenth request to keep the writes free,
                # but a frontier is normally known while the count is still in
                # single figures — so waiting for it would leave every crawl
                # that DOES know its total showing "unknown" for its first ten
                # pages, which is the exact complaint being fixed.
                try:
                    self.on_expectation(declared)
                except Exception:
                    pass

    # ---- validators, so a repeat crawl can be answered with 304 -------------

    def fresh_session(self) -> HttpFetcher:
        """A SECOND fetcher with this one's settings and none of its state.

        For the rare case where a site's answer depends on the session itself
        and the crawl's session must not be disturbed. advancedcastle is the
        one: it pins the country in a cookie on a session's first request and
        thereafter redirects every URL to that country, so reading its Egyptian
        page on the crawl's own session returns the Saudi one — 200, no error —
        and asking for it FIRST would have turned every remaining product page
        Egyptian. A separate session answers the question and touches nothing.

        Deliberately a method here rather than a connector building its own
        client: politeness, retries and the honest UA stay defined in exactly
        one place (Q1). Deliberately NOT inheriting validators, robots cache or
        counters either — those describe the crawl, and this is not the crawl.
        The caller closes it.
        """
        return HttpFetcher(
            user_agent=self._user_agent,
            min_interval_s=self._min_interval_s,
            timeout_s=self._client.timeout.read or 30.0,
            max_attempts=self._max_attempts,
            jitter=self._jitter,
            honour_crawl_delay=self._honour_crawl_delay,
        )

    def remember_validators(self, state: dict[str, dict[str, str]]) -> None:
        """Load validators kept from a previous crawl."""
        self._validators.update(state or {})

    def validators(self) -> dict[str, dict[str, str]]:
        """The validators to keep for the next crawl."""
        return dict(self._validators)

    def _conditional_headers(self, url: str, headers: dict | None) -> dict:
        stored = self._validators.get(url)
        if not stored:
            return headers or {}
        merged = dict(headers or {})
        if "ETag" in stored:
            merged.setdefault("If-None-Match", stored["ETag"])
        if "Last-Modified" in stored:
            merged.setdefault("If-Modified-Since", stored["Last-Modified"])
        return merged

    def _store_validators(self, url: str, response: httpx.Response) -> None:
        keep = {k: response.headers[k] for k in ("ETag", "Last-Modified")
                if k in response.headers}
        if keep:
            self._validators[url] = keep

    @staticmethod
    def _validator_url(url: str, params) -> str:
        """The exact resource a validator describes, including its query.

        An ETag for ``?page=1`` says nothing about ``?page=2``.  Keying the
        cache only by the path made the second live samehgabriel page inherit
        page one's validator and answer 304 with no JSON body.
        """
        if params is None:
            return str(url)
        return str(httpx.URL(url, params=params))

    # ---- the request path ---------------------------------------------------

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self._request("GET", url, **kwargs)

    def get_dropping(self, url: str, optional: Iterable[str] = (),
                     **kwargs) -> httpx.Response:
        """GET, and if the request is REFUSED, ask again without `optional`.

        WHY THIS EXISTS, measured 2026-08-13 on samehgabriel.com. Its Store API
        answers 200 to /wp-json/wc/store/products and 403 to the same URL with
        `?per_page=1` — any value, even 1. Not the page size, not the range: the
        presence of that one parameter trips a rule at the edge. The crawl had
        been dead for twelve days over a query string.

        A refusal of the whole endpoint is a decision to respect. A refusal of
        one OPTIONAL parameter is not the same thing: `per_page` is an
        efficiency, and asking for the same rows in smaller pages is the request
        the site is willing to answer. So this degrades ONCE, and only for
        parameters the caller has named as optional — never the address, never
        anything the answer depends on.

        THE DEGRADATION IS RECORDED, NOT ABSORBED. `degradations` is read into
        the run's warnings, because a crawl that quietly costs ten times the
        requests is a bill nobody sees until it is a block. Silence here would
        turn one visible outage into a permanent invisible cost.

        `sticky` keeps the lesson for the rest of the run: having learned that
        the site refuses a parameter, asking 300 more times is both rude and
        slow.
        """
        from urllib.parse import urlsplit

        names = [n for n in optional if n]
        params = dict(kwargs.pop("params", None) or {})
        droppable = [n for n in names if n in params]
        host = urlsplit(url).netloc.lower()

        if droppable and all((host, n) in self._refused_params for n in droppable):
            for name in droppable:
                params.pop(name)
            return self._request("GET", url, params=params or None, **kwargs)

        try:
            return self._request("GET", url, params=params or None, **kwargs)
        except httpx.HTTPStatusError as refusal:
            if not droppable or refusal.response.status_code not in self.DROP_STATUSES:
                raise
            lighter = {k: v for k, v in params.items() if k not in droppable}
            answer = self._request("GET", url, params=lighter or None, **kwargs)
            # Only now, with proof that the lighter request works, is the lesson
            # worth keeping — a 403 that was really about something else must
            # not teach us to drop a parameter for ever.
            self._refused_params.update((host, name) for name in droppable)
            self.degradations.append(
                f"{host} refused "
                f"{', '.join(sorted(droppable))} with HTTP "
                f"{refusal.response.status_code} and answered without it — this "
                "crawl is using the site's own page size, which costs more "
                "requests for the same rows")
            return answer

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self._request("POST", url, **kwargs)

    def _robots_for(self, url: str):
        from urllib.parse import urlsplit
        from urllib.robotparser import RobotFileParser

        host = urlsplit(url).netloc
        if host in self._robots:
            return self._robots[host]
        parser = None
        try:
            robots_url = f"{urlsplit(url).scheme}://{host}/robots.txt"
            # The plain client, NOT self.get: a robots fetch inside _request
            # would recurse, and it must not count as a crawl request either.
            answer = self._client.get(robots_url)
            if answer.status_code == 200:
                parser = RobotFileParser()
                parser.parse(answer.text.splitlines())
                # Kept so the report shown to the owner can quote the actual
                # lines. RobotFileParser answers questions and cannot be asked
                # what it read.
                self._robots_text[host] = answer.text
        except Exception:
            parser = None
        self._robots[host] = parser
        if parser is not None:
            delay = parser.crawl_delay(self._user_agent) or parser.crawl_delay("*")
            if delay and float(delay) > self._min_interval_s:
                if self._honour_crawl_delay:
                    # The site's own asked-for pace WINS over our default.
                    # Slowing down is never the wrong direction.
                    self._min_interval_s = float(delay)
                    self.robots_warnings.append(
                        f"{host}: robots.txt asks for a {delay}s crawl delay — honoured")
                else:
                    # The owner turned it off for this run. Said OUT LOUD and
                    # with the number, because the whole point of the switch is
                    # that he knows what he is overriding — and because a run
                    # that was fast for this reason must be distinguishable
                    # afterwards from one that was fast because the site asked
                    # for nothing.
                    self.robots_warnings.append(
                        f"{host}: robots.txt asks for a {delay}s crawl delay — "
                        f"IGNORED at your request; this run paces itself at "
                        f"{self._min_interval_s}s and may be rate-limited or "
                        "blocked by the site")
        return parser

    def sitemap_urls(self, url: str) -> list[str]:
        """Sitemap addresses the site's own robots.txt advertises, in order.

        The robots file is already fetched lazily before the first request to a
        host. Exposing only its `Sitemap:` declarations lets a fallback discover
        a catalogue without guessing a plugin-specific filename, while keeping
        the robots cache and its network accounting in one place.
        """
        from urllib.parse import urlsplit

        self._robots_for(url)
        host = urlsplit(url).netloc
        found: list[str] = []
        for line in self._robots_text.get(host, "").splitlines():
            name, separator, value = line.partition(":")
            if separator and name.strip().lower() == "sitemap" and value.strip():
                found.append(value.strip())
        return list(dict.fromkeys(found))

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        robots = self._robots_for(url)
        if robots is not None and not robots.can_fetch(self._user_agent, url):
            # NO LONGER ONE RULING FOR EVERY SITE. docs/robots-policy.md carried
            # "Disallow is informational" for every source from 2026-07-22; it
            # is now what a source gets when it has said nothing, and the source
            # can say otherwise. scrapex/robots.py resolves the three cases and
            # writes the sentence that explains whichever happened.
            from urllib.parse import urlsplit

            from ..robots import RobotsChoice, RobotsCustom, decide, inspect

            host = urlsplit(url).netloc
            report = self._robots_reports.get(host)
            if report is None:
                report = inspect(url, self._robots_text.get(host),
                                 user_agent=self._user_agent)
                self._robots_reports[host] = report

            custom = None
            if self._robots_choice == RobotsChoice.CUSTOM and self._robots_custom:
                custom = RobotsCustom(
                    enforce_disallow=bool(self._robots_custom.get("enforce_disallow")),
                    crawl_delay_s=self._robots_custom.get("crawl_delay_s"))
            verdict = decide(report, RobotsChoice(self._robots_choice), custom=custom,
                             tool_default_obeys=self._obey_disallow,
                             url_disallowed=True)

            # ONE line per host: a 400-page crawl must not write 400 of them.
            marker = f"{host}: robots.txt disallows"
            if not any(w.startswith(marker) for w in self.robots_warnings):
                self.robots_warnings.append(f"{marker} — {verdict.reason}")
            if not verdict.may_fetch:
                # RAISED, not skipped. A skipped page becomes an empty crawl
                # that reports success, and a source that silently stops being
                # collected is the worst failure this product has. The owner
                # chose to obey; the run must say so out loud and stop.
                raise RobotsDisallowed(verdict.reason)
        validator_url = str(url)
        if method == "GET":
            validator_url = self._validator_url(url, kwargs.get("params"))
            kwargs["headers"] = self._conditional_headers(
                validator_url, kwargs.get("headers"))
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            self._throttle()
            try:
                response = self._client.request(method, url, **kwargs)
            except httpx.TransportError as exc:
                # A dropped connection is not a refusal; it is worth one more try.
                last_error = exc
                if attempt == self._max_attempts:
                    raise
                self.retry_count += 1
                self._sleep_backoff(attempt)
                continue
            self.requests_count += 1
            if self.on_request is not None:
                try:
                    self.on_request(self.requests_count, url)
                except CrawlBlocked:
                    # The hook is also where the owner's Pause/Cancel arrives
                    # (CrawlInterrupted). Swallowing THAT with the display
                    # errors would make the brakes decorative.
                    raise
                except Exception:
                    pass

            if response.status_code == 304:
                # Unchanged since our last visit. The caller asked for content,
                # so this is only useful to a caller that opted in by keeping
                # validators — it is surfaced, never silently treated as empty.
                self.not_modified_count += 1
                self._consecutive_refusals = 0
                return response

            if response.status_code in self.RETRY_STATUSES and attempt < self._max_attempts:
                if response.status_code in (429, 503):
                    self._consecutive_refusals += 1
                    self._trip_breaker_if_needed(url, response.status_code)
                self.retry_count += 1
                self._sleep_backoff(attempt, response)
                continue

            if response.status_code in (401, 403, 429):
                self._consecutive_refusals += 1
                self._trip_breaker_if_needed(url, response.status_code)
            else:
                self._consecutive_refusals = 0

            self._store_validators(validator_url, response)
            response.raise_for_status()
            return response

        raise last_error or RuntimeError(f"{method} {url} exhausted its attempts")

    def _trip_breaker_if_needed(self, url: str, status: int) -> None:
        if self._consecutive_refusals >= self.BLOCK_LIMIT:
            raise CrawlBlocked(
                f"{self._consecutive_refusals} refusals in a row (last: HTTP {status} "
                f"on {url}). Stopping rather than pressing a site that has said no — "
                "slow the crawl down or spread it over more runs, and retry later.")

    def _sleep_backoff(self, attempt: int, response: httpx.Response | None = None) -> None:
        """Retry-After when the server names a delay, else exponential backoff.

        A server-named delay gets its own, much higher ceiling: silently
        shrinking a requested hour to two minutes was the OPPOSITE of
        honouring it, and re-knocking early is how a polite crawler stops
        being welcome. When the cap does bite, it is recorded, not hidden.
        """
        delay = min(self._min_interval_s * (2 ** attempt), self.MAX_BACKOFF_S)
        if response is not None:
            named = response.headers.get("Retry-After", "")
            try:
                asked = float(named)
                delay = min(asked, self.MAX_RETRY_AFTER_S)
                if asked > self.MAX_RETRY_AFTER_S:
                    self.robots_warnings.append(
                        f"server asked for Retry-After {asked:.0f}s; waited the "
                        f"{self.MAX_RETRY_AFTER_S:.0f}s ceiling instead")
            except ValueError:
                pass          # Retry-After may be an HTTP date; the default stands
        time.sleep(max(0.0, delay))

    def _throttle(self) -> None:
        # Jittered, so a long crawl is not a metronome sitting in phase with
        # whatever window a rate limiter counts in.
        interval = self._min_interval_s
        if self._jitter:
            interval *= 1.0 + random.uniform(-self._jitter, self._jitter)
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < interval:
            time.sleep(interval - elapsed)
        self._last_request_at = time.monotonic()

    def close(self) -> None:
        self._client.close()


class BrowserFetcher:
    """Playwright transport — owner-decided day-one infrastructure (A3 carve-out).

    Import cost is paid only when a connector actually requests
    fetcher: browser (S7 flakiness policy lives with the implementation).
    """

    def __init__(self) -> None:
        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "BrowserFetcher requires the browser extra: "
                "pip install -e .[browser] && playwright install chromium"
            ) from exc
        # The two members every caller reads unconditionally. They were missing,
        # and the consequence was worse than a missing number: capture.py:220
        # and cli.py:212 call close() from a `finally`, so the AttributeError
        # was raised BY the release path and replaced whatever the crawl had
        # actually failed with. The owner would have read
        # "'BrowserFetcher' object has no attribute 'close'" instead of the
        # real cause, on the one path built to guarantee release.
        self.requests_count = 0   # recorded into crawl_run, same as HttpFetcher
        self.robots_warnings: list[str] = []

    def close(self) -> None:
        """Nothing outlives a fetch, so there is nothing to release.

        Deliberate and stated rather than absent: each get_html opens its own
        playwright context and browser and closes both in its own `finally`
        (below), so no handle survives the call. The method exists because the
        callers' guaranteed-release path is allowed to assume it does.
        """

    def get_html(self, url: str, wait_selector: str | None = None, retries: int = 2) -> str:
        """Fetch a fully-rendered page. S7: selector waits (never fixed sleeps),
        2 retries with backoff, artifacts on final failure."""
        from playwright.sync_api import sync_playwright

        last_error: Exception | None = None
        for attempt in range(retries + 1):
            self.requests_count += 1   # every attempt is a real page load
            try:
                with sync_playwright() as pw:
                    browser = pw.chromium.launch()
                    try:
                        page = browser.new_page()
                        page.goto(url, wait_until="networkidle")
                        if wait_selector:
                            page.wait_for_selector(wait_selector)
                        return page.content()
                    finally:
                        browser.close()
            except Exception as exc:
                last_error = exc
                time.sleep(2**attempt)
        raise RuntimeError(f"browser fetch failed after {retries + 1} attempts: {url}") from last_error


def resolve_fetcher(source: SourceEntry,
                    crawl_settings: dict | None = None) -> HttpFetcher | BrowserFetcher:
    """Build the transport for a source.

    Precedence for the user agent is deliberate: a source that DECLARES one wins,
    because it declares it for a reason (Zid 403s anything else, F5). The owner's
    global setting fills in for every source that does not.
    """
    if source.fetcher == Fetcher.BROWSER:
        return BrowserFetcher()
    chosen = crawl_settings or {}
    # `or` would treat a deliberate 0 as "unset" and silently restore the 1-second
    # default, so a setting the owner changed would appear not to work at all.
    interval = chosen.get("min_interval_s")
    timeout = chosen.get("timeout_s")
    # Absent means HONOUR. A missing setting must never be read as permission
    # to ignore a site's asked-for pace — the safe reading of silence is the
    # polite one.
    honour = chosen.get("honour_crawl_delay")
    # ONE PLACE DECIDES THE PACE, AND IT TAKES THE SLOWEST OPINION.
    #
    # There were three of these and only one was connected. The owner's setting
    # reached the fetcher; a site's own robots Crawl-delay is applied later in
    # `_robots_for`; and `robots_custom.crawl_delay_s` — declared in the
    # manifest, documented, shown in the web UI, computed all the way into
    # `Decision.delay_s` — was read by nobody. `decide()`'s verdict is consulted
    # only for `may_fetch`, and only on a path robots.txt DISALLOWS, so an owner
    # who set a per-source delay saw it in the interface and it did nothing.
    #
    # Slowest wins, which is the rule `_robots_for` already follows in its own
    # words: "slowing down is never the wrong direction". So a per-source pace
    # can hold a site back and can never push one forward past the owner's
    # setting — including a `crawl_pace_s` typed too small by accident.
    paces = [1.0 if interval is None else float(interval)]
    if source.crawl_pace_s:
        paces.append(float(source.crawl_pace_s))
    custom_delay = (source.robots_custom or {}).get("crawl_delay_s")
    if custom_delay:
        paces.append(float(custom_delay))

    return HttpFetcher(
        user_agent=source.user_agent or chosen.get("user_agent") or DEFAULT_USER_AGENT,
        min_interval_s=max(paces),
        timeout_s=30.0 if timeout is None else float(timeout),
        honour_crawl_delay=True if honour is None else bool(honour),
        # The source's own answer, and what it means when the source did not
        # give one. Read HERE and not inside the fetcher because a single crawl
        # can run several sources and each may have answered differently.
        robots_choice=source.robots or "default",
        robots_custom=source.robots_custom,
        obey_disallow=bool(chosen.get("obey_disallow")),
    )

