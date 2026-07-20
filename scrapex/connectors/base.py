"""Connector contract + fetchers (ENGINEERING.md A1, A2, A3, F5, S7).

One SiteConnector per source; families share base classes ONLY once proven
(A3). Connectors never import each other; everything downstream of FetchAsync
is uniform: ScrapedTable -> funnel payload -> ingest.
"""
from __future__ import annotations

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


class HttpFetcher:
    """Shared polite HTTP transport (F5): rate-limited, retrying, one UA.

    Connectors receive a fetcher; they never build their own httpx client, so
    politeness and retry policy stay in one place (Q1).
    """

    def __init__(
        self,
        user_agent: str = DEFAULT_USER_AGENT,
        min_interval_s: float = 1.0,  # F5: <= 1 req/s default
        timeout_s: float = 30.0,
    ) -> None:
        self._client = httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=timeout_s,
            follow_redirects=True,
        )
        self._min_interval_s = min_interval_s
        self._last_request_at = 0.0
        self.requests_count = 0  # recorded into crawl_run (F5 accounting)

    def get(self, url: str, **kwargs) -> httpx.Response:
        self._throttle()
        response = self._client.get(url, **kwargs)
        self.requests_count += 1
        response.raise_for_status()
        return response

    def post(self, url: str, **kwargs) -> httpx.Response:
        self._throttle()
        response = self._client.post(url, **kwargs)
        self.requests_count += 1
        response.raise_for_status()
        return response

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self._min_interval_s:
            time.sleep(self._min_interval_s - elapsed)
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
