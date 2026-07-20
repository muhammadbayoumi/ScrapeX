"""Spec: the price history is a timeline of real changes, not a daily copy.

Everything here is derived from the append-only evidence, so the tests check two
different promises: that the derivation is correct, and that it is rebuildable —
because being rebuildable is the only reason these layers are allowed to be
mutable while the evidence beneath them is not.
"""
from __future__ import annotations

import pytest

from scrapex import db as dbmod, pricehistory
from scrapex.ingest import ingest_payloads
from tests.test_ingest import make_entry, make_payload, one_row


@pytest.fixture()
def conn(tmp_path):
    c = dbmod.connect(tmp_path / "harvest.db")
    dbmod.migrate(c)
    try:
        yield c
    finally:
        c.close()


def crawl(conn, *, price="100.00", day="2026-07-01", stock="", brand="Elsewedy"):
    ingest_payloads(conn, make_entry(), [make_payload(
        [one_row(effective_price=price, stock_quantity=stock, brand_raw=brand)],
        scraped_at=f"{day}T10:00:00Z")])


def offer(conn) -> int:
    return conn.execute("SELECT offer_id FROM price_observation LIMIT 1").fetchone()[0]


# ---- the timeline is changes, not confirmations ------------------------------

def test_a_price_that_never_moves_is_one_period_however_often_it_is_crawled(conn):
    for day in ("2026-07-01", "2026-07-02", "2026-07-03", "2026-07-04"):
        crawl(conn, price="100.00", day=day)
    pricehistory.rebuild_all(conn)

    periods = pricehistory.timeline(conn, offer(conn))
    assert len(periods) == 1, "four crawls of an unchanged price are one price"
    assert periods[0]["first_detected_at"].startswith("2026-07-01")
    assert periods[0]["last_confirmed_at"].startswith("2026-07-04")
    assert periods[0]["opened_because"] == "first_seen"


def test_each_real_change_opens_exactly_one_period(conn):
    crawl(conn, price="100.00", day="2026-07-01")
    crawl(conn, price="100.00", day="2026-07-02")
    crawl(conn, price="130.00", day="2026-07-03")
    crawl(conn, price="130.00", day="2026-07-04")
    pricehistory.rebuild_all(conn)

    periods = pricehistory.timeline(conn, offer(conn))
    assert [p["effective_price"] for p in periods] == [100.0, 130.0]
    assert periods[0]["closed_at"].startswith("2026-07-03"), "the old period closed"
    assert periods[1]["closed_at"] is None, "the current period stays open"
    assert periods[1]["opened_because"] == "price_change"


def test_a_stock_movement_alone_does_not_open_a_period(conn):
    """The owner wants the latest stock state, never its history."""
    crawl(conn, price="100.00", day="2026-07-01", stock="5")
    crawl(conn, price="100.00", day="2026-07-02", stock="41")
    pricehistory.rebuild_all(conn)
    assert len(pricehistory.timeline(conn, offer(conn))) == 1


def test_a_source_that_starts_publishing_a_manufacturer_is_not_a_price_change(conn):
    """Without the field list this is where every offer in a warehouse would
    appear to change price on the same day."""
    crawl(conn, price="100.00", day="2026-07-01", brand="")
    crawl(conn, price="100.00", day="2026-07-02", brand="Lafarge")
    pricehistory.rebuild_all(conn)

    periods = pricehistory.timeline(conn, offer(conn))
    assert len(periods) == 2, "the keys are genuinely incomparable"
    assert periods[1]["opened_because"] == "fields_changed", \
        "...and the reason must not read as a price change"
    assert periods[0]["effective_price"] == periods[1]["effective_price"], \
        "the price itself never moved"


# ---- current state -----------------------------------------------------------

def test_current_state_holds_the_latest_price_and_availability(conn):
    crawl(conn, price="100.00", day="2026-07-01")
    crawl(conn, price="130.00", day="2026-07-05", stock="9")
    pricehistory.rebuild_all(conn)

    state = conn.execute("SELECT * FROM offer_state WHERE offer_id = ?",
                         (offer(conn),)).fetchone()
    assert state["effective_price"] == 130.0
    assert state["stock_quantity"] == 9.0
    assert state["first_seen_at"].startswith("2026-07-01")
    assert state["last_confirmed_at"].startswith("2026-07-05")


def test_at_most_one_period_is_open_per_offer(conn):
    """Two open periods would mean two current prices. The schema refuses it."""
    for day, price in (("2026-07-01", "100.00"), ("2026-07-02", "110.00"),
                       ("2026-07-03", "120.00")):
        crawl(conn, price=price, day=day)
    pricehistory.rebuild_all(conn)
    assert conn.execute(
        "SELECT COUNT(*) FROM price_period WHERE offer_id = ? AND closed_at IS NULL",
        (offer(conn),)).fetchone()[0] == 1


# ---- rebuildable, which is what makes it safe to be mutable ------------------

def test_rebuilding_twice_produces_the_same_timeline(conn):
    for day, price in (("2026-07-01", "100.00"), ("2026-07-02", "100.00"),
                       ("2026-07-03", "130.00")):
        crawl(conn, price=price, day=day)

    pricehistory.rebuild_all(conn)
    first = pricehistory.timeline(conn, offer(conn))
    pricehistory.rebuild_all(conn)
    second = pricehistory.timeline(conn, offer(conn))

    strip = lambda rows: [{k: v for k, v in r.items() if k != "price_period_id"}
                          for r in rows]
    assert strip(first) == strip(second)


def test_rebuilding_never_touches_the_evidence(conn):
    for day in ("2026-07-01", "2026-07-02"):
        crawl(conn, price="100.00", day=day)
    before = conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
    pricehistory.rebuild_all(conn)
    assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == before


def test_an_offer_with_no_observations_has_no_state(conn):
    crawl(conn)
    conn.execute("DELETE FROM offer_state")
    assert pricehistory.rebuild_offer(conn, 999) == 0


# ---- exact-date lookup -------------------------------------------------------

def test_a_confirmed_date_returns_the_period_that_covered_it(conn):
    crawl(conn, price="100.00", day="2026-07-01")
    crawl(conn, price="100.00", day="2026-07-10")
    pricehistory.rebuild_all(conn)

    answer = pricehistory.price_on(conn, offer(conn), "2026-07-05")
    assert answer["status"] == "confirmed" and answer["effective_price"] == 100.0


def test_an_unconfirmed_date_says_so_instead_of_assuming_the_price_held(conn):
    """The spec is explicit: do not assume the previous price remained valid."""
    crawl(conn, price="100.00", day="2026-07-01")
    pricehistory.rebuild_all(conn)

    answer = pricehistory.price_on(conn, offer(conn), "2026-09-01")
    assert answer["status"] == "last_known"
    assert answer["effective_price"] == 100.0, "the last known price is still useful"
    assert "No reliable observation" in answer["detail"]
    assert answer["observed_at"].startswith("2026-07-01"), \
        "the answer must carry the date it was actually observed"


def test_a_date_before_tracking_began_reports_the_first_tracking_date(conn):
    crawl(conn, price="100.00", day="2026-07-01")
    pricehistory.rebuild_all(conn)

    answer = pricehistory.price_on(conn, offer(conn), "2020-01-01")
    assert answer["status"] == "before_tracking"
    assert "2026-07-01" in answer["detail"]
    assert answer["effective_price"] is None, "inventing a price here would be a lie"


def test_an_offer_with_no_history_says_nothing_was_ever_recorded(conn):
    crawl(conn)
    pricehistory.rebuild_all(conn)
    answer = pricehistory.price_on(conn, 999, "2026-07-01")
    assert answer["status"] == "no_history" and answer["effective_price"] is None


# ---- warehouses written before any of this existed ---------------------------

def test_a_warehouse_of_daily_duplicates_collapses_into_its_real_changes(conn):
    """The migration path, simulated honestly.

    Rows written before the price key carry no hash, so the number itself is the
    only comparable thing they have. They cannot be produced by UPDATE-ing real
    rows — the append-only triggers refuse, which is the point — so they are
    INSERTed as a pre-0015 warehouse would have written them.
    """
    crawl(conn, price="100.00", day="2026-07-01")
    offer_id = offer(conn)
    run_id = conn.execute("SELECT run_id FROM price_observation").fetchone()[0]
    conn.execute("DELETE FROM price_period")

    legacy = [("2026-07-01", 100.0), ("2026-07-02", 100.0),
              ("2026-07-03", 100.0), ("2026-07-04", 150.0)]
    for day, price in legacy[1:]:
        conn.execute(
            "INSERT INTO price_observation (offer_id, observed_at, business_date, "
            " effective_price, currency, vat_included, availability, run_id, "
            " record_hash, price_hash, price_fields) "
            "VALUES (?,?,?,?,?,?,?,?,?,NULL,NULL)",
            (offer_id, f"{day}T10:00:00Z", day, price, "EGP", 1, "in_stock",
             run_id, f"legacy-{day}"))
    conn.commit()

    pricehistory.rebuild_all(conn)
    periods = pricehistory.timeline(conn, offer_id)
    assert [p["effective_price"] for p in periods] == [100.0, 150.0], \
        "four daily rows are two prices"
