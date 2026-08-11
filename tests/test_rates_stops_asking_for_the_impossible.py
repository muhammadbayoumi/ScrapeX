"""Three codes the engine asked Google about on every refresh, for ever.

MEASURED ON THE OWNER'S DATABASE, 2026-08-10. Of 123 currencies with price
observations, 119 had a rate and four did not — and three of the four were not
gaps at all:

    UNKNOWN   3,149 observations   not a currency. All of them belong to
                                   SPARK_ESHOP, the source deleted from the
                                   manifest; `ingest` and three connectors write
                                   this placeholder when a source declares none.
    USD       2,242 observations   the BASE. `currency_rate.per_usd` is defined
                                   against it, so it cannot be missing its own
                                   rate. Already excluded in SQL.
    SLL          52 observations   retired in 2022 — redenominated to SLE.
    ZWD          50 observations   retired in 2009 — abandoned.

So the standing backlog item "the five currencies with no exchange rate" was
never five, and after this it is none: one orphan, one base, two dead codes.

WHY IT MATTERS MORE THAN THE COUNT. `currencies_in_use` feeds the refresh, which
builds `https://www.google.com/finance/quote/USD-{code}` for each. Three of those
requests could never succeed. Every cycle spent three fetches and wrote three
warnings nobody could act on — and a warning that is always there is a warning
that gets ignored, taking the real one after it along with it.
"""
from __future__ import annotations

import sqlite3

import pytest

from scrapex.rates import UNQUOTABLE, currencies_in_use


@pytest.fixture
def priced():
    """Observations in a real currency, the base, the placeholder, and a code
    that no longer exists."""
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE price_observation (currency TEXT)")
    conn.executemany("INSERT INTO price_observation VALUES (?)",
                     [("EGP",), ("EGP",), ("SAR",), ("USD",),
                      ("UNKNOWN",), ("SLL",), ("ZWD",), ("",), (None,)])
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()


def test_only_currencies_a_service_could_quote_are_asked_for(priced):
    assert currencies_in_use(priced) == ["EGP", "SAR"]


def test_the_placeholder_is_not_treated_as_a_currency(priced):
    """`UNKNOWN` is what a connector writes when a source declares no currency.
    Asking a rate service about it can only ever fail, and the rows it marks are
    `storage.undeclared_sources`' business rather than the rate fetcher's."""
    assert "UNKNOWN" not in currencies_in_use(priced)


def test_a_retired_code_is_not_asked_for_every_cycle_for_ever(priced):
    """SLL and ZWD are real codes that were real money. No service quotes them
    now, and no amount of retrying will change that."""
    for dead in ("SLL", "ZWD"):
        assert dead not in currencies_in_use(priced)


def test_the_base_currency_is_not_reported_as_missing_its_own_rate(priced):
    assert "USD" not in currencies_in_use(priced)


def test_every_exclusion_carries_a_reason(priced):
    """A list of codes with no reasons is a list nobody can ever shorten. When
    Sierra Leone's SLE has been in the warehouse long enough that SLL is gone,
    the note is what tells the next reader it is safe to drop the entry."""
    for code, why in UNQUOTABLE.items():
        assert isinstance(why, str) and len(why) > 20, (
            f"{code} is excluded with no usable reason: {why!r}")


def test_a_real_currency_is_never_silently_dropped(priced):
    """The failure this must not have. Excluding a live currency would leave its
    prices uncomparable and NOTHING would say so — the same silence as a source
    that stops collecting."""
    conn = priced
    conn.execute("INSERT INTO price_observation VALUES ('SLE')")   # the successor
    conn.commit()

    assert "SLE" in currencies_in_use(conn), (
        "the code that REPLACED SLL is being excluded with it, so every price "
        "in Sierra Leone's actual currency would go unconverted in silence")
