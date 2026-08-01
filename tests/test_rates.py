"""Google Finance rate fetching + storage (scrapex.rates).

Fake fetchers only — the HTML snippets reproduce the shape captured from the
LIVE pages on 2026-07-27 (see the scrapex/rates.py docstring): one div per
page carrying data-source/data-target/data-last-price/
data-last-normal-market-timestamp, one "YMlKec fxKbKc" display div, and many
decoy bare-YMlKec figures (index tiles) that the parser must never grab.
"""
from __future__ import annotations

import sqlite3

import pytest

from scrapex import db as dbmod
from scrapex.connectors.base import CrawlBlocked
from scrapex.rates import (
    MAX_PLAUSIBLE_PER_USD,
    QUOTE_URL_TEMPLATE,
    Rate,
    SOURCE_KEY,
    fetch_rates,
    store_rates,
)

# Epoch 1785167520 == 2026-07-27T15:52:00Z — the value observed live.
OBSERVED_TS = 1785167520
OBSERVED_TS_ISO = "2026-07-27T15:52:00Z"

# The Dow Jones market tile as it appears on every quote page: a bare-YMlKec
# figure that a class-anchored parser would happily mistake for the rate.
DECOY_TILE = (
    '<div class="VKMjFc"><div class="pKBk1e">Dow Jones</div>'
    '<div class="wzUQBf"><span class="lh92"><div jsname="ip75Cb" class="s1OkXb">'
    '<div class="YMlKec">52,043.70</div></div></span></div></div>'
)


def quote_page(target: str, last_price: str, ts: int | None = OBSERVED_TS,
               display: str = "3.7477", source: str = "USD") -> str:
    """A page in the captured 2026-07-27 shape, decoy tile first."""
    stamp = f' data-last-normal-market-timestamp="{ts}"' if ts is not None else ""
    return (
        "<html><body>" + DECOY_TILE +
        '<div jscontroller="NdbN0c" jsaction="oFr1Ad:uxt3if;" jsname="AS5Pxb" '
        'data-mid="/g/11bvvxqvbw" data-entity-type="3" '
        f'data-source="{source}" data-target="{target}" '
        f'data-last-price="{last_price}"{stamp} data-tz-offset=0>'
        '<div class="rPF6Lc" jsname="OYCkv"><div class="ln0Gqe">'
        '<div jsname="LXPcOd"><div class="AHmHk"><span class="">'
        '<div jsname="ip75Cb" class="kf1m0">'
        f'<div class="YMlKec fxKbKc">{display}</div>'
        "</div></span></div></div></div></div></div></body></html>"
    )


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.status_code = 200


class FakeFetcher:
    """Injected in place of HttpFetcher: url -> HTML str or Exception to raise."""

    def __init__(self, pages: dict[str, str | Exception]) -> None:
        self.pages = pages
        self.calls: list[str] = []

    def get(self, url: str, **kwargs) -> FakeResponse:
        self.calls.append(url)
        answer = self.pages[url]     # unexpected URL -> KeyError -> loud failure
        if isinstance(answer, Exception):
            raise answer
        return FakeResponse(answer)


def url_for(code: str) -> str:
    return QUOTE_URL_TEMPLATE.format(code=code)


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


# ---------------------------------------------------------------- fetching --

def test_parses_the_observed_attribute_shape():
    fetcher = FakeFetcher({
        url_for("SAR"): quote_page("SAR", "3.747688"),
        url_for("EGP"): quote_page("EGP", "50.7216679", ts=OBSERVED_TS + 60,
                                   display="50.7217"),
    })
    batch = fetch_rates(fetcher, ["SAR", "EGP"])
    assert batch.warnings == []
    assert [(r.currency, r.per_usd) for r in batch.rates] == [
        ("SAR", 3.747688), ("EGP", 50.7216679)]
    sar, egp = batch.rates
    # as_of comes from the page's own market timestamp, not our clock.
    assert sar.as_of == OBSERVED_TS_ISO
    assert egp.as_of == "2026-07-27T15:53:00Z"
    assert sar.source_url == url_for("SAR")
    assert fetcher.calls == [url_for("SAR"), url_for("EGP")]


def test_usd_is_definitional_without_a_request():
    fetcher = FakeFetcher({})        # any request at all would KeyError
    batch = fetch_rates(fetcher, ["USD"])
    assert fetcher.calls == []
    assert batch.warnings == []
    [usd] = batch.rates
    assert (usd.currency, usd.per_usd, usd.source_url) == ("USD", 1.0, "")
    assert usd.as_of                 # still dated: the ruling covers USD too


def test_one_bad_currency_warns_and_the_rest_still_land():
    fetcher = FakeFetcher({
        url_for("SAR"): quote_page("SAR", "3.747688"),
        url_for("EGP"): "<html><body>layout rebuilt, nothing here</body></html>",
    })
    batch = fetch_rates(fetcher, ["SAR", "EGP"])
    assert [r.currency for r in batch.rates] == ["SAR"]
    [warning] = batch.warnings
    assert "EGP" in warning and url_for("EGP") in warning


def test_fetch_error_is_a_warning_not_fatal():
    fetcher = FakeFetcher({
        url_for("EGP"): RuntimeError("HTTP 503"),
        url_for("SAR"): quote_page("SAR", "3.747688"),
    })
    batch = fetch_rates(fetcher, ["EGP", "SAR"])
    assert [r.currency for r in batch.rates] == ["SAR"]
    [warning] = batch.warnings
    assert "EGP" in warning and "HTTP 503" in warning


def test_crawl_blocked_always_propagates():
    # The brakes (site refusals, the owner's Pause/Cancel) must not be
    # swallowed by per-currency isolation — same rule as every connector.
    fetcher = FakeFetcher({url_for("SAR"): CrawlBlocked("5 refusals in a row")})
    with pytest.raises(CrawlBlocked):
        fetch_rates(fetcher, ["SAR", "EGP"])


def test_zero_and_absurd_rates_are_refused_loudly():
    fetcher = FakeFetcher({
        url_for("SAR"): quote_page("SAR", "0"),
        url_for("EGP"): quote_page("EGP", "2500000"),     # > 1e6 per USD
        url_for("AED"): quote_page("AED", "3.6725"),
    })
    batch = fetch_rates(fetcher, ["SAR", "EGP", "AED"])
    assert [r.currency for r in batch.rates] == ["AED"]
    assert len(batch.warnings) == 2
    assert any("SAR" in w and "zero or negative" in w for w in batch.warnings)
    assert any("EGP" in w and "plausibility" in w for w in batch.warnings)


def test_wrong_pair_on_the_page_is_refused():
    # Foreign content: a redirect could serve some OTHER pair's page.
    fetcher = FakeFetcher({url_for("EGP"): quote_page("AED", "3.6725")})
    batch = fetch_rates(fetcher, ["EGP"])
    assert batch.rates == []
    [warning] = batch.warnings
    assert "USD-AED" in warning and "EGP" in warning


def test_display_fallback_parses_commas_and_warns_of_shape_drift():
    # data-last-price gone -> the rounded display div still yields a rate,
    # but NEVER silently: the drift is surfaced so the parser gets re-verified.
    page = quote_page("LBP", "89500.25", display="89,500.25")
    page = page.replace(' data-last-price="89500.25"', "")
    fetcher = FakeFetcher({url_for("LBP"): page})
    batch = fetch_rates(fetcher, ["LBP"])
    [rate] = batch.rates
    assert rate.per_usd == 89500.25       # comma-grouped display value cleaned
    [warning] = batch.warnings
    assert "shape" in warning and "LBP" in warning


def test_decoy_index_tiles_are_never_mistaken_for_the_rate():
    # No quote div at all: the Dow Jones 52,043.70 tile must NOT become a rate.
    fetcher = FakeFetcher({url_for("SAR"): "<html>" + DECOY_TILE + "</html>"})
    batch = fetch_rates(fetcher, ["SAR"])
    assert batch.rates == []
    assert len(batch.warnings) == 1


def test_invalid_currency_code_never_reaches_the_network():
    fetcher = FakeFetcher({})
    batch = fetch_rates(fetcher, ["12X", "eg p", ""])
    assert fetcher.calls == []
    assert batch.rates == []
    assert len(batch.warnings) == 3


# ----------------------------------------------------------------- storing --

def rates_pair() -> list[Rate]:
    return [
        Rate("SAR", 3.747688, OBSERVED_TS_ISO, url_for("SAR")),
        Rate("EGP", 50.7216679, OBSERVED_TS_ISO, url_for("EGP")),
    ]


def test_store_twice_lands_once(conn):
    assert store_rates(conn, rates_pair()) == 2
    assert store_rates(conn, rates_pair()) == 2       # upsert, not append
    rows = conn.execute(
        "SELECT currency, per_usd, as_of, source_key FROM currency_rate "
        "ORDER BY currency").fetchall()
    assert [tuple(r) for r in rows] == [
        ("EGP", 50.7216679, OBSERVED_TS_ISO, SOURCE_KEY),
        ("SAR", 3.747688, OBSERVED_TS_ISO, SOURCE_KEY),
    ]


def test_store_refreshes_per_usd_on_the_same_timestamp(conn):
    store_rates(conn, [Rate("SAR", 3.747688, OBSERVED_TS_ISO, url_for("SAR"))])
    store_rates(conn, [Rate("SAR", 3.75, OBSERVED_TS_ISO, url_for("SAR"))])
    rows = conn.execute(
        "SELECT per_usd FROM currency_rate WHERE currency='SAR'").fetchall()
    assert [r[0] for r in rows] == [3.75]


def test_new_market_timestamp_accumulates_history(conn):
    store_rates(conn, [Rate("SAR", 3.747688, OBSERVED_TS_ISO, url_for("SAR"))])
    store_rates(conn, [Rate("SAR", 3.7480, "2026-07-27T18:00:00Z", url_for("SAR"))])
    count = conn.execute(
        "SELECT COUNT(*) FROM currency_rate WHERE currency='SAR'").fetchone()[0]
    assert count == 2                 # 0028: history accumulates


def test_usd_is_never_stored(conn):
    rates = [Rate("USD", 1.0, OBSERVED_TS_ISO, "")] + rates_pair()
    assert store_rates(conn, rates) == 2      # the skip is visible in the count
    assert conn.execute(
        "SELECT COUNT(*) FROM currency_rate WHERE currency='USD'").fetchone()[0] == 0


def test_store_refuses_out_of_range_rates_loudly(conn):
    with pytest.raises(ValueError):
        store_rates(conn, [Rate("SAR", -1.0, OBSERVED_TS_ISO, url_for("SAR"))])
    with pytest.raises(ValueError):
        store_rates(conn, [Rate("SAR", MAX_PLAUSIBLE_PER_USD * 2,
                                OBSERVED_TS_ISO, url_for("SAR"))])
    assert conn.execute("SELECT COUNT(*) FROM currency_rate").fetchone()[0] == 0


def test_timestamped_rate_outranks_a_date_only_row_from_the_same_day(conn):
    # The readers (reports.py) take ORDER BY as_of DESC LIMIT 1 over TEXT.
    # A GPP publisher-implied row is date-only; the quote page's full
    # timestamp must sort AFTER it lexicographically, so the finer-grained
    # google_finance figure wins the day they share.
    conn.execute(
        "INSERT INTO currency_rate "
        "  (currency, per_usd, as_of, source_key, source_kind) "
        "VALUES ('SAR', 3.70, '2026-07-27', 'globalpetrolprices', 'shop')")
    store_rates(conn, [Rate("SAR", 3.747688, OBSERVED_TS_ISO, url_for("SAR"))])
    latest = conn.execute(
        "SELECT per_usd FROM currency_rate WHERE currency='SAR' "
        "ORDER BY as_of DESC LIMIT 1").fetchone()[0]
    assert latest == 3.747688


# ---- the schedule half: refreshed without hammering the quote pages ----------

def test_rates_refresh_only_when_the_stored_ones_have_gone_stale(tmp_path):
    """Google Finance moves continuously, but a scraper that reloads a quote
    page every worker poll is a scraper that gets blocked. The freshness check
    is what makes calling this every pass cost one SELECT.
    """
    from scrapex import db as dbmod, rates

    conn = dbmod.connect(tmp_path / "r.db")
    dbmod.migrate(conn)
    conn.execute("INSERT INTO source_site (source_id, source_key, source_name_ar, "
                 " source_name, base_url, platform, currency, timezone, authority, active) "
                 "VALUES (1,'S','س','S','http://s','custom_json','SAR','UTC','shop',1)")

    class _Fetcher:
        calls = 0
        def get(self, url):
            _Fetcher.calls += 1
            class _R:
                text = ('<div data-source="USD" data-target="SAR" '
                        'data-last-price="3.75" '
                        'data-last-normal-market-timestamp="1785167520"></div>')
            return _R()

    # Nothing priced yet: nothing to convert, so nothing is fetched.
    assert rates.refresh_if_due(conn, _Fetcher()) is None
    assert _Fetcher.calls == 0

    conn.execute("INSERT INTO crawl_run (run_id, source_id, started_at, status) "
                 "VALUES (1,1,'2026-07-01T00:00:00Z','success')")
    conn.execute("INSERT INTO source_product (source_product_id, source_id, "
                 " external_product_id, product_name, product_name_ar) "
                 "VALUES (1,1,'p','P','ب')")
    conn.execute("INSERT INTO source_variant (source_variant_id, source_product_id, "
                 " external_variant_id) VALUES (1,1,'v')")
    conn.execute("INSERT INTO source_offer (offer_id, source_variant_id, "
                 " country_code_alpha2, customer_segment, basis_quantity, currency, "
                 " tax_included) VALUES (1,1,'SA','retail',1,'SAR',1)")
    conn.execute("INSERT INTO price_observation (offer_id, run_id, observed_at, "
                 " business_date, price, currency, tax_included, availability, "
                 " record_hash, price_hash, price_fields, provenance) "
                 "VALUES (1,1,'2026-07-01T00:00:00Z','2026-07-01',100,'SAR',1,"
                 "'in_stock','rh','ph','effective','observed')")
    conn.commit()

    # Every instant here is stated, because refresh_if_due stamps the store with
    # the `now` it is given. Letting the first call take the real clock and then
    # naming a fixed later date made this a bomb with a six-hour fuse: on
    # 2026-07-31 at 18:17Z the real stamp was only 5h43m before the named
    # 2026-08-01T00:00:00Z — inside the window, nothing due — and CI went red on
    # a docs-only PR. Once the real clock passed that date the age went
    # NEGATIVE, and `not (0 <= age < WINDOW)` calls a negative age due too, so
    # the test went green again while testing nothing: measured, it still passed
    # with REFRESH_AFTER_S set to ten years.
    first = rates.refresh_if_due(conn, _Fetcher(), now="2026-07-01T00:00:00Z")
    assert first is not None and _Fetcher.calls == 1
    assert [r.currency for r in first.rates] == ["SAR"]

    # One second inside the window: nothing is due, no second request.
    assert rates.refresh_if_due(conn, _Fetcher(), now="2026-07-01T05:59:59Z") is None
    assert _Fetcher.calls == 1

    # The exact instant the window closes: age == REFRESH_AFTER_S, and the
    # predicate is `age < WINDOW`, so this is the first due moment.
    assert rates.refresh_if_due(conn, _Fetcher(), now="2026-07-01T06:00:00Z") is not None
    assert _Fetcher.calls == 2


def test_only_currencies_the_warehouse_actually_prices_in_are_fetched(tmp_path):
    """Asked of the DATA, not the manifest: a source that never ran, or whose
    currency the owner changed after a crawl, must not send us fetching a quote
    page for a currency no row uses."""
    from scrapex import db as dbmod, rates

    conn = dbmod.connect(tmp_path / "c.db")
    dbmod.migrate(conn)
    assert rates.currencies_in_use(conn) == []


def test_a_failing_quote_page_costs_one_attempt_per_interval_not_one_per_poll():
    """The attempt is stamped BEFORE the fetch, deliberately.

    Throttling on success alone means a quote page that is down is requested on
    every single worker poll — the hammering the interval exists to prevent,
    arriving precisely when the site is least able to answer.
    """
    import sqlite3

    from scrapex import db as dbmod, rates

    conn = dbmod.connect(":memory:")
    dbmod.migrate(conn)
    conn.execute("INSERT INTO source_site (source_id, source_key, source_name_ar, "
                 " source_name, base_url, platform, currency, timezone, authority, active) "
                 "VALUES (1,'S','س','S','http://s','custom_json','SAR','UTC','shop',1)")
    conn.execute("INSERT INTO crawl_run (run_id, source_id, started_at, status) "
                 "VALUES (1,1,'2026-07-01T00:00:00Z','success')")
    conn.execute("INSERT INTO source_product (source_product_id, source_id, "
                 " external_product_id, product_name, product_name_ar) VALUES (1,1,'p','P','ب')")
    conn.execute("INSERT INTO source_variant (source_variant_id, source_product_id, "
                 " external_variant_id) VALUES (1,1,'v')")
    conn.execute("INSERT INTO source_offer (offer_id, source_variant_id, "
                 " country_code_alpha2, customer_segment, basis_quantity, currency, "
                 " tax_included) VALUES (1,1,'SA','retail',1,'SAR',1)")
    conn.execute("INSERT INTO price_observation (offer_id, run_id, observed_at, "
                 " business_date, price, currency, tax_included, availability, "
                 " record_hash, price_hash, price_fields, provenance) "
                 "VALUES (1,1,'2026-07-01T00:00:00Z','2026-07-01',100,'SAR',1,"
                 "'in_stock','rh','ph','effective','observed')")
    conn.commit()

    class _Broken:
        calls = 0
        def get(self, url):
            _Broken.calls += 1
            raise RuntimeError("quote page is down")

    first = rates.refresh_if_due(conn, _Broken(), now="2026-07-28T00:00:00Z")
    assert first is not None and first.rates == []
    assert first.warnings and "SAR" in first.warnings[0]
    assert _Broken.calls == 1

    # Ten more polls in the same window make no further request.
    for _ in range(10):
        assert rates.refresh_if_due(conn, _Broken(), now="2026-07-28T00:05:00Z") is None
    assert _Broken.calls == 1


def test_the_attempt_survives_an_exception_that_escapes_the_fetch(tmp_path):
    """The throttle has to hold for the errors this module lets THROUGH, too.

    A per-currency failure is swallowed into warnings, so the caller commits and
    the stamp lands. CrawlBlocked deliberately propagates — and the worker's
    recorder, which is where it lands, calls conn.rollback() before writing its
    report. An uncommitted stamp went with it, so the very next poll was due
    again: a blocked quote page became a request every half-second against the
    one site this module most needs to stay welcome at. Hence the stamp is
    committed on its own, before the fetch.
    """
    from scrapex import db as dbmod, rates

    db = tmp_path / "blocked.db"
    conn = dbmod.connect(db)
    dbmod.migrate(conn)
    conn.execute("INSERT INTO source_site (source_id, source_key, source_name_ar, "
                 " source_name, base_url, platform, currency, timezone, authority, active) "
                 "VALUES (1,'S','س','S','http://s','custom_json','SAR','UTC','shop',1)")
    conn.execute("INSERT INTO crawl_run (run_id, source_id, started_at, status) "
                 "VALUES (1,1,'2026-07-01T00:00:00Z','success')")
    conn.execute("INSERT INTO source_product (source_product_id, source_id, "
                 " external_product_id, product_name, product_name_ar) "
                 "VALUES (1,1,'p','P','ب')")
    conn.execute("INSERT INTO source_variant (source_variant_id, source_product_id, "
                 " external_variant_id) VALUES (1,1,'v')")
    conn.execute("INSERT INTO source_offer (offer_id, source_variant_id, "
                 " country_code_alpha2, customer_segment, basis_quantity, currency, "
                 " tax_included) VALUES (1,1,'SA','retail',1,'SAR',1)")
    conn.execute("INSERT INTO price_observation (offer_id, run_id, observed_at, "
                 " business_date, price, currency, tax_included, availability, "
                 " record_hash, price_hash, price_fields, provenance) "
                 "VALUES (1,1,'2026-07-01T00:00:00Z','2026-07-01',100,'SAR',1,"
                 "'in_stock','rh','ph','effective','observed')")
    conn.commit()

    class _Blocked:
        calls = 0
        def get(self, url):
            _Blocked.calls += 1
            raise CrawlBlocked("the site said no")

    with pytest.raises(CrawlBlocked):
        rates.refresh_if_due(conn, _Blocked(), now="2026-07-28T00:00:00Z")
    assert _Blocked.calls == 1

    # What the worker does with a propagated failure: roll back, then report.
    conn.rollback()

    assert rates.last_checked(conn) == "2026-07-28T00:00:00Z", (
        "the attempt was rolled back with the failure it was reporting")
    for _ in range(10):
        assert rates.refresh_if_due(conn, _Blocked(), now="2026-07-28T00:05:00Z") is None
    assert _Blocked.calls == 1

    # And it is a THROTTLE, not a lockout: due again once the window passes.
    with pytest.raises(CrawlBlocked):
        rates.refresh_if_due(conn, _Blocked(), now="2026-07-29T00:00:00Z")
    assert _Blocked.calls == 2


def test_a_clock_that_went_backwards_counts_as_due_not_as_fresh(tmp_path):
    """The mechanism that hid the bomb above, pinned deliberately.

    refresh_is_due returns `not (0 <= age < REFRESH_AFTER_S)`, so a stored stamp
    in the FUTURE — a corrected clock, a restored backup, a machine that ran in
    another timezone — reads as due rather than as fresh. That is the safe
    direction: we re-ask rather than sit on a figure we cannot date. Nothing may
    quietly narrow it to `age >= WINDOW`, which would call a future stamp
    permanently fresh and stop the USD column ever updating again."""
    from scrapex import db as dbmod, rates

    conn = dbmod.connect(tmp_path / "back.db")
    dbmod.migrate(conn)
    conn.execute("INSERT INTO source_site (source_id, source_key, source_name_ar, "
                 " source_name, base_url, platform, currency, timezone, authority, active) "
                 "VALUES (1,'S','س','S','http://s','custom_json','SAR','UTC','shop',1)")
    conn.execute("INSERT INTO crawl_run (run_id, source_id, started_at, status) "
                 "VALUES (1,1,'2026-07-01T00:00:00Z','success')")
    conn.execute("INSERT INTO source_product (source_product_id, source_id, "
                 " external_product_id, product_name, product_name_ar) "
                 "VALUES (1,1,'p','P','ب')")
    conn.execute("INSERT INTO source_variant (source_variant_id, source_product_id, "
                 " external_variant_id) VALUES (1,1,'v')")
    conn.execute("INSERT INTO source_offer (offer_id, source_variant_id, "
                 " country_code_alpha2, customer_segment, basis_quantity, currency, "
                 " tax_included) VALUES (1,1,'SA','retail',1,'SAR',1)")
    conn.execute("INSERT INTO price_observation (offer_id, run_id, observed_at, "
                 " business_date, price, currency, tax_included, availability, "
                 " record_hash, price_hash, price_fields, provenance) "
                 "VALUES (1,1,'2026-07-01T00:00:00Z','2026-07-01',100,'SAR',1,"
                 "'in_stock','rh','ph','effective','observed')")
    conn.execute("INSERT INTO scrapex_meta (key, value) VALUES (?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (rates.LAST_CHECK_KEY, "2027-01-01T00:00:00Z"))
    conn.commit()

    assert rates.refresh_is_due(conn, now="2026-07-01T00:00:00Z") is True
