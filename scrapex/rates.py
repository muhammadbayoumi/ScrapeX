"""Exchange rates from Google Finance — the fetcher half of the USD column.

WHY THIS MODULE EXISTS
----------------------
The owner's ruling (2026-07-26): https://www.google.com/finance is the source
of truth for exchange rates, rates refresh continuously, and a converted
number must NEVER be shown without the rate used AND the date of that rate.
`currency_rate` already holds publisher-implied rates (GPP's local/USD pairs,
migration 0028); this module adds a second, deliberate source — the quote
pages themselves — under its own source_key, so provenance stays in the row
by construction. UI wiring comes later; this file only fetches and stores.

WHAT THE LIVE PAGES LOOK LIKE (observed 2026-07-27, USD-SAR and USD-EGP)
------------------------------------------------------------------------
https://www.google.com/finance/quote/USD-SAR carries the rate in EXACTLY ONE
element per page, a div that names the pair beside the price:

    <div jscontroller="NdbN0c" jsaction="oFr1Ad:uxt3if;" jsname="AS5Pxb"
         data-mid="/g/11bvvxqvbw" data-entity-type="3"
         data-source="USD" data-target="SAR"
         data-last-price="3.747688"
         data-last-normal-market-timestamp="1785167520" data-tz-offset=0>

`data-last-normal-market-timestamp` is epoch SECONDS, UTC (1785167520 ==
2026-07-27T15:52:00Z, matching the page's own rendered "Jul 27, 3:52:00 PM
UTC"). The displayed, rounded figure sits in ONE `<div class="YMlKec
fxKbKc">3.7477</div>` — but bare `YMlKec` appears ~30 times per page (Dow
Jones tiles, CSS), so the class alone is ambiguous and the parser anchors on
`data-last-price`, verifying `data-source`/`data-target` name the pair we
asked for. The display div is a FALLBACK only, taken with a loud shape-drift
warning, because a fallback that engages silently is how a parser rots.

DESIGN RULES
------------
- The page is foreign content: the pair is verified, the number is cleaned
  (commas, NBSP) and bounded — zero, negative, non-finite and absurd
  (> 1e6 per USD) values are refused OUT LOUD, never stored.
- The Turkey rule: one currency failing is a warning entry in the returned
  batch, never a silent drop and never fatal to the others. The one
  exception is CrawlBlocked — the site (or the owner, via CrawlInterrupted)
  said STOP, and per-currency isolation must not swallow the brakes.
- `as_of` is the page's own market timestamp when stated, else the fetch
  time — both real moments the rate was true, both in the blessed
  "%Y-%m-%dT%H:%M:%SZ" wire format. Full timestamps interleave correctly
  with the date-only GPP rows: `currency_rate.as_of` is TEXT, readers take
  `ORDER BY as_of DESC LIMIT 1`, and ISO text sorts chronologically —
  "2026-07-27T15:52:00Z" > "2026-07-27", so the finer-grained quote wins
  the day it shares with a publisher-implied rate.
- Storage respects the table's real uniqueness, UNIQUE(currency, as_of,
  source_key): re-storing the same batch upserts, distinct market
  timestamps accumulate as genuine intraday history under this source_key.

The transport is the injected house fetcher (connectors.base.HttpFetcher) —
its politeness, retries and honest UA are not re-implemented here, and tests
inject a fake serving captured-shape HTML instead of touching the network.
"""
from __future__ import annotations

import math
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .connectors.base import CrawlBlocked
from .payload import utc_now_iso

# Provenance: rows this module writes are distinguishable from GPP's
# publisher-implied rates by construction (0028's source_key column).
SOURCE_KEY = "google_finance"

QUOTE_URL_TEMPLATE = "https://www.google.com/finance/quote/USD-{code}"

# 1 USD buying more than a million units of anything is not a market rate we
# believe from a scraped page — it is a parse gone wrong (or a currency in a
# state where a stale figure would mislead worse than a missing one).
MAX_PLAUSIBLE_PER_USD = 1e6

# ISO-4217 alpha codes. The currency list comes from price_observation —
# scraped, therefore untrusted — and anything else would be interpolated
# straight into a URL.
_CURRENCY_CODE = re.compile(r"[A-Z]{3}")

# The ONE element carrying the machine-readable rate (shape observed above).
_QUOTE_TAG = re.compile(r"<[A-Za-z][^>]*\bdata-last-price=\"[^\"]*\"[^>]*>")
# Rounded display figure — fallback only; see the module docstring.
_DISPLAY_DIV = re.compile(r"class=\"YMlKec fxKbKc\"[^>]*>([^<]+)<")


@dataclass(frozen=True)
class Rate:
    """One exchange rate with everything the owner's ruling requires shown."""

    currency: str      # ISO code the rate converts USD into (1 USD = per_usd currency)
    per_usd: float
    as_of: str         # UTC ISO-8601 ("%Y-%m-%dT%H:%M:%SZ") — the date OF the rate
    source_url: str    # the quote page it was read from ("" for definitional USD)


@dataclass
class RateBatch:
    """What a fetch produced AND what went wrong, side by side.

    Same shape decision as connectors' ScrapedTable.warnings: carrying on when
    one currency breaks is correct; dropping the fact that it broke is not.
    Returned as one object (not a bare list[Rate]) precisely so the warnings
    cannot be left behind by an inattentive caller.
    """

    rates: list[Rate] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _clean_rate_number(text: str) -> float:
    """Parse a scraped rate defensively; ValueError (loud) on anything unfit.

    Google groups displayed figures with commas ("52,043.70") and its markup
    is free to use NBSP/narrow spaces; the attribute value today is plain
    ("50.7216679") but the fallback path reads the display div, so both are
    cleaned the same way.
    """
    cleaned = text.strip().replace(",", "")
    cleaned = cleaned.replace(" ", "").replace(" ", "").replace(" ", "")
    value = float(cleaned)          # ValueError for garbage — exactly what we want
    if not math.isfinite(value):
        raise ValueError(f"rate {text!r} is not a finite number")
    if value <= 0:
        raise ValueError(f"rate {text!r} is zero or negative — refused")
    if value > MAX_PLAUSIBLE_PER_USD:
        raise ValueError(
            f"rate {text!r} exceeds the {MAX_PLAUSIBLE_PER_USD:g} plausibility "
            "ceiling — refused as a probable parse error")
    return value


def _attr(tag: str, name: str) -> str | None:
    """A double-quoted attribute value from one raw opening tag, or None."""
    match = re.search(rf"\b{re.escape(name)}=\"([^\"]*)\"", tag)
    return match.group(1) if match else None


def _parse_quote_page(html: str, code: str, url: str) -> tuple[float, str, list[str]]:
    """(per_usd, as_of, shape_warnings) from one quote page; ValueError when
    the page holds no usable rate. Every deviation from the observed shape is
    surfaced — a fallback that engages silently would hide the drift until
    the day it too breaks."""
    shape_warnings: list[str] = []
    tag_match = _QUOTE_TAG.search(html)
    if tag_match:
        tag = tag_match.group(0)
        source = _attr(tag, "data-source")
        target = _attr(tag, "data-target")
        if source != "USD" or target != code:
            # Foreign content: a redirect or layout change could serve some
            # OTHER pair. Storing AED under EGP would be corruption, not data.
            raise ValueError(
                f"page names the pair {source}-{target}, not USD-{code} — refused")
        per_usd = _clean_rate_number(_attr(tag, "data-last-price") or "")
        stamp = _attr(tag, "data-last-normal-market-timestamp")
        if stamp and stamp.isdigit():
            as_of = datetime.fromtimestamp(int(stamp), tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ")
        else:
            as_of = utc_now_iso()
            shape_warnings.append(
                f"{code}: data-last-normal-market-timestamp missing from {url}; "
                "as_of falls back to the fetch time")
        return per_usd, as_of, shape_warnings

    display = _DISPLAY_DIV.search(html)
    if display:
        per_usd = _clean_rate_number(display.group(1))
        shape_warnings.append(
            f"{code}: data-last-price attribute missing from {url} — page shape "
            "drifted; used the displayed (rounded) figure and the fetch time. "
            "Re-verify the parser against the live page.")
        return per_usd, utc_now_iso(), shape_warnings

    raise ValueError("no rate found on the page (neither data-last-price nor "
                     "the display figure) — the page shape has changed")


def fetch_rates(fetcher, currencies: list[str]) -> RateBatch:
    """Fetch USD->currency rates from Google Finance quote pages.

    `fetcher` is the house HTTP seam (connectors.base.HttpFetcher or a test
    fake exposing .get(url).text). One page per non-USD currency; each
    currency is isolated — its failure becomes a warning in the batch while
    the rest proceed — except CrawlBlocked, which always propagates (the
    brakes are not decorative; see connectors.base).
    """
    batch = RateBatch()
    seen: set[str] = set()
    for raw in currencies:
        code = (raw or "").strip().upper()
        if code in seen:
            continue                 # DISTINCT input, harmless duplicates
        seen.add(code)
        if not _CURRENCY_CODE.fullmatch(code):
            batch.warnings.append(
                f"{raw!r} is not an ISO currency code — skipped (no request made)")
            continue
        if code == "USD":
            # 1 USD = 1.0 USD by definition — no request, no source page.
            batch.rates.append(Rate(currency="USD", per_usd=1.0,
                                    as_of=utc_now_iso(), source_url=""))
            continue
        url = QUOTE_URL_TEMPLATE.format(code=code)
        try:
            html = fetcher.get(url).text
            per_usd, as_of, shape_warnings = _parse_quote_page(html, code, url)
        except CrawlBlocked:
            raise                    # the site (or the owner) said stop — stop
        except Exception as exc:  # noqa: BLE001 — recorded per currency, never silent
            batch.warnings.append(f"{code}: no rate from {url} — {exc}")
            continue
        batch.warnings.extend(shape_warnings)
        batch.rates.append(Rate(currency=code, per_usd=per_usd,
                                as_of=as_of, source_url=url))
    return batch


def store_rates(conn: sqlite3.Connection, rates: list[Rate]) -> int:
    """Upsert rates into currency_rate under this module's source_key.

    Idempotent by the table's REAL uniqueness, UNIQUE(currency, as_of,
    source_key): the same batch stored twice lands once; a re-read of the
    same market timestamp refreshes per_usd in place; a NEW market timestamp
    is a new row — genuine intraday history, which 0028 says accumulates.

    USD rows are NOT written: per_usd = 1.0 is definitional, and the table's
    convention (ingest.py's implied-rate writer) is that a rate of 1 is
    noise. The skip is stated here and visible in the returned count.

    Returns the number of rows written or refreshed. Commits on success.
    """
    written = 0
    for rate in rates:
        if rate.currency == "USD":
            continue
        # The bounds hold at the storage door too — store_rates is public and
        # a Rate built by hand must not smuggle in what fetch would refuse.
        if not math.isfinite(rate.per_usd) or rate.per_usd <= 0 \
                or rate.per_usd > MAX_PLAUSIBLE_PER_USD:
            raise ValueError(
                f"refusing to store {rate.currency} rate {rate.per_usd!r}: "
                "outside the plausible range (0, 1e6]")
        conn.execute(
            "INSERT INTO currency_rate (currency, per_usd, as_of, source_key) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(currency, as_of, source_key) DO UPDATE SET "
            "  per_usd = excluded.per_usd",
            (rate.currency, rate.per_usd, rate.as_of, SOURCE_KEY))
        written += 1
    conn.commit()
    return written


# How stale a stored rate may be before the worker fetches again. Google Finance
# moves continuously, but the owner's question is "what was this worth", not
# "what is it worth this second" — and a scraper that reloads a quote page every
# poll is a scraper that gets blocked. Six hours keeps the USD column honest
# within a trading day while costing one request per currency per quarter-day.
REFRESH_AFTER_S = 6 * 60 * 60


# When WE last asked, which is not the same as how old the rate is. Throttling
# on the stored rate's own market timestamp looked right and is wrong: a
# weekend, a holiday or any closed market leaves that stamp hours old forever,
# so every worker poll would decide a refresh was due and hammer the quote page
# — the exact failure the interval exists to prevent.
LAST_CHECK_KEY = "rates_last_checked"


def last_checked(conn: sqlite3.Connection) -> str:
    """When this module last ATTEMPTED a refresh, or "" if it never has."""
    row = conn.execute("SELECT value FROM scrapex_meta WHERE key = ?",
                       (LAST_CHECK_KEY,)).fetchone()
    return (row[0] if row and row[0] else "") or ""


def currencies_in_use(conn: sqlite3.Connection) -> list[str]:
    """Every currency the warehouse actually prices in.

    Asked of the DATA, not the manifest: a source that has never run, or one
    whose currency the owner changed after a crawl, would otherwise send us
    fetching a page for a currency no row uses — or, worse, leave a currency
    that IS in use without a rate because its manifest entry says otherwise.
    """
    return [r[0] for r in conn.execute(
        "SELECT DISTINCT currency FROM price_observation "
        "WHERE TRIM(COALESCE(currency,'')) <> '' AND currency <> 'USD' "
        "ORDER BY currency")]


def refresh_if_due(conn: sqlite3.Connection, fetcher, *,
                   now: str | None = None) -> RateBatch | None:
    """Fetch and store rates when we last asked longer ago than the interval.

    Returns the batch when it fetched, or None when nothing was due — so a
    caller can report what happened without inspecting the clock itself.

    The attempt is stamped BEFORE the fetch, so a quote page that is failing
    does not turn into a request on every single poll. A failure costs one
    attempt per interval, exactly like a success.

    Never raises for a fetch failure: the batch carries per-currency warnings
    (the Turkey rule) and the caller reports them. CrawlBlocked still
    propagates, because the brakes are not decorative.
    """
    stamp = now or utc_now_iso()
    if not (wanted := currencies_in_use(conn)):
        return None                  # nothing priced yet — nothing to convert
    previous = last_checked(conn)
    if previous:
        try:
            age = (datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ")
                   - datetime.strptime(previous, "%Y-%m-%dT%H:%M:%SZ")).total_seconds()
        except ValueError:
            age = None               # an unparseable stamp is not a fresh one
        if age is not None and 0 <= age < REFRESH_AFTER_S:
            return None
    conn.execute(
        "INSERT INTO scrapex_meta (key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (LAST_CHECK_KEY, stamp))
    batch = fetch_rates(fetcher, wanted)
    store_rates(conn, batch.rates)
    return batch
