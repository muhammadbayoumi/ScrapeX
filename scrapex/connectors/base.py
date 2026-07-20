"""Connector contract + fetchers (ENGINEERING.md A1, A2, A3, F5, S7).

One SiteConnector per source; families share base classes ONLY once proven
(A3). Connectors never import each other; everything downstream of FetchAsync
is uniform: ScrapedTable -> funnel payload -> ingest.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Iterable, Protocol, runtime_checkable

import httpx

from ..config import SourceEntry
from ..payload import FunnelPayload, PAYLOAD_VERSION, utc_now_iso
from ..vocab import ExtractKind, Fetcher, PayloadClient

# A single honest, stable UA for all HTTP fetching (F5). Zid/WAF sites that
# 403 generic clients get a browser UA via SourceEntry notes + per-family
# override — explicitly, per connector, never silently global.
DEFAULT_USER_AGENT = "ScrapeX/0.1 (+contact: owner)"


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

    def to_payload(self, client: PayloadClient = PayloadClient.CLI, run_ref: str | None = None) -> FunnelPayload:
        return FunnelPayload(
            payload_version=PAYLOAD_VERSION,
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
    # Never sleep longer than this for one retry, however large Retry-After is.
    MAX_BACKOFF_S = 120.0
    RETRY_STATUSES = frozenset({408, 425, 429, 500, 502, 503, 504})

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        min_interval_s: float = 1.0,  # F5: <= 1 req/s default
        timeout_s: float = 30.0,
        max_attempts: int = 3,
        jitter: float = 0.3,          # +/- 30% around the base interval
    ) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout_s,
            follow_redirects=True,
        )
        self._min_interval_s = min_interval_s
        self._last_request_at = 0.0
        self._max_attempts = max(1, max_attempts)
        self._jitter = max(0.0, min(jitter, 0.9))
        self._consecutive_refusals = 0
        # url -> {"ETag": ..., "Last-Modified": ...}, replayed on the next visit.
        self._validators: dict[str, dict[str, str]] = {}
        self.requests_count = 0   # recorded into crawl_run (F5 accounting)
        self.not_modified_count = 0
        self.retry_count = 0

    # ---- validators, so a repeat crawl can be answered with 304 -------------

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

    # ---- the request path ---------------------------------------------------

    def get(self, url: str, **kwargs) -> httpx.Response:
        return self._request("GET", url, **kwargs)

    def post(self, url: str, **kwargs) -> httpx.Response:
        return self._request("POST", url, **kwargs)

    def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        if method == "GET":
            kwargs["headers"] = self._conditional_headers(url, kwargs.get("headers"))
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

            self._store_validators(url, response)
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
        """Retry-After when the server names a delay, else exponential backoff."""
        delay = min(self._min_interval_s * (2 ** attempt), self.MAX_BACKOFF_S)
        if response is not None:
            named = response.headers.get("Retry-After", "")
            try:
                delay = min(float(named), self.MAX_BACKOFF_S)
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

    def get_html(self, url: str, wait_selector: str | None = None, retries: int = 2) -> str:
        """Fetch a fully-rendered page. S7: selector waits (never fixed sleeps),
        2 retries with backoff, artifacts on final failure."""
        from playwright.sync_api import sync_playwright

        last_error: Exception | None = None
        for attempt in range(retries + 1):
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
            except Exception as exc:  # noqa: BLE001 — recorded, retried, re-raised (Q3)
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
    return HttpFetcher(
        user_agent=source.user_agent or chosen.get("user_agent") or DEFAULT_USER_AGENT,
        min_interval_s=1.0 if interval is None else float(interval),
        timeout_s=30.0 if timeout is None else float(timeout),
    )
