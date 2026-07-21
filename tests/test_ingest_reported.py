"""Reported rows: the source's dated claims, kept apart from what WE watched.

A reported row says "the publisher states this price held on that date". It is
real data worth keeping — ten years of it, in GPP's case — and it is not an
observation of ours. Everything here proves the separation holds end to end:
the date it lands under, the change stream it must never enter, the derived
timeline it must never rewrite, and the absence bookkeeping it must not touch.

The bug this file exists to prevent: before the pass-through, the ingest
adapter dropped provenance and as_of_date, so every history anchor landed as a
TODAY observation — three "months ago" prices stamped with the crawl date,
colliding with the current price, confirming or contradicting it at random.
"""
from __future__ import annotations

import sqlite3

import pytest

from scrapex import db as dbmod
from scrapex import pricehistory
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.base import ScrapedTable
from scrapex.ingest import ingest_payloads
from scrapex.rowspec import COMMODITY_PRICE, RowBuilder
from scrapex.vocab import ExtractKind, ExtractScope


def _entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="GPP_ENERGY", source_name="أسعار الطاقة العالمية",
        base_url="https://www.globalpetrolprices.com", family="static-html-table",
        cadence="weekly", authority="aggregator", currency="USD",
        extract=[ExtractSpec(kind=ExtractKind.COMMODITY_PRICE,
                             scope=ExtractScope.LATEST_ONLY,
                             materials=["DIESEL"], regions=["*"])],
    ))


def _payload(rows_kv: list[dict]):
    builder = RowBuilder(COMMODITY_PRICE)
    rows = []
    for kv in rows_kv:
        base = dict(material_key="DIESEL", region="EG", currency="EGP",
                    unit="liter", vat_included="1", price_basis="original")
        base.update(kv)
        rows.append(builder.row(**base))
    table = ScrapedTable("GPP_ENERGY", ExtractKind.COMMODITY_PRICE,
                         "https://www.globalpetrolprices.com",
                         builder.header, rows)
    return table.to_payload()


@pytest.fixture()
def conn():
    c: sqlite3.Connection = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


def _observations(conn):
    return conn.execute(
        "SELECT business_date, effective_price, provenance FROM price_observation "
        "ORDER BY price_observation_id").fetchall()


def _changes(conn):
    return conn.execute(
        "SELECT change_type, previous_value, new_value FROM change_event "
        "WHERE field_key = 'effective_price'").fetchall()


CURRENT = dict(effective_price="20.50")
ANCHOR_1M = dict(effective_price="20.50", provenance="reported", as_of_date="2026-06-21")
ANCHOR_1Y = dict(effective_price="15.50", provenance="reported", as_of_date="2025-07-21")


def test_a_reported_row_lands_under_the_date_the_source_names(conn):
    ingest_payloads(conn, _entry(), [_payload([CURRENT, ANCHOR_1M, ANCHOR_1Y])])

    rows = _observations(conn)
    assert [(r["provenance"], r["business_date"]) for r in rows] == [
        ("observed", rows[0]["business_date"]),   # ours, dated by the crawl
        ("reported", "2026-06-21"),
        ("reported", "2025-07-21"),
    ]
    # And the crawl date is NOT the anchor's date — the whole point.
    assert rows[0]["business_date"] not in ("2026-06-21", "2025-07-21")


def test_a_backfilled_anchor_never_fires_a_change_event(conn):
    """15.50-a-year-ago arriving after today's 20.50 is history, not a crash.
    Before the split it produced a 'price_decrease' dated this morning."""
    ingest_payloads(conn, _entry(), [_payload([CURRENT, ANCHOR_1Y])])

    assert _changes(conn) == []


def test_next_weeks_price_is_compared_to_our_last_observation_not_the_anchor(conn):
    """The previous-read orders by insertion; the freshest row after week 1 is
    the year-ago anchor at 15.50. Comparing 21.00 against IT would report a
    +35% jump when the real move is 20.50 -> 21.00."""
    ingest_payloads(conn, _entry(), [_payload([CURRENT, ANCHOR_1Y])])
    ingest_payloads(conn, _entry(), [_payload([dict(effective_price="21.00")])])

    moves = _changes(conn)
    assert len(moves) == 1
    # change_event stores values as text; the numbers are what matters.
    assert (float(moves[0]["previous_value"]), float(moves[0]["new_value"])) == (20.5, 21.0)


def test_reported_rows_do_not_open_or_close_derived_periods(conn):
    """The derived timeline records what ScrapeX watched (owner rule: real
    changes only). A publisher's anchors must not write it."""
    ingest_payloads(conn, _entry(), [_payload([CURRENT, ANCHOR_1M, ANCHOR_1Y])])
    offer_id = conn.execute("SELECT offer_id FROM source_offer").fetchone()[0]
    pricehistory.rebuild_offer(conn, offer_id)

    periods = conn.execute(
        "SELECT COUNT(*) FROM price_period WHERE offer_id = ?", (offer_id,)).fetchone()[0]
    assert periods == 1, "anchors opened periods — publisher dating wrote our history"


def test_a_reported_row_without_a_date_is_rejected_not_guessed(conn):
    result = ingest_payloads(conn, _entry(), [_payload([
        dict(effective_price="19.00", provenance="reported"),   # no as_of_date
    ])])

    assert result.rejected_out_of_scope == 1
    assert _observations(conn) == []


def test_recrawling_the_same_anchor_is_idempotent(conn):
    """Week 2 re-reads the same country page; the same (date, price) anchor must
    not duplicate. The dedupe key includes business_date, so it cannot."""
    ingest_payloads(conn, _entry(), [_payload([CURRENT, ANCHOR_1M])])
    result = ingest_payloads(conn, _entry(), [_payload([CURRENT, ANCHOR_1M])])

    rows = _observations(conn)
    assert len([r for r in rows if r["provenance"] == "reported"]) == 1
    assert result.duplicates >= 1


def test_two_anchors_same_price_different_dates_both_persist(conn):
    """20.50 a month ago and 20.50 today-per-the-source are two claims, not one.
    A dedupe that ignored the date would silently drop half the history."""
    ingest_payloads(conn, _entry(), [_payload([
        ANCHOR_1M, dict(effective_price="20.50", provenance="reported",
                        as_of_date="2026-07-13"),
    ])])

    dates = [r["business_date"] for r in _observations(conn)]
    assert sorted(dates) == ["2026-06-21", "2026-07-13"]


def test_an_anchor_alone_does_not_mark_the_offer_as_seen(conn):
    """`seen` drives absence bookkeeping: it asserts the offer is on the site
    TODAY. A ten-year-old anchor asserts no such thing."""
    result = ingest_payloads(conn, _entry(), [_payload([ANCHOR_1Y])])

    assert result.seen == {}


# ---- the fetch-time pulse (lives here for the shared db fixture) -------------

def test_a_running_jobs_row_gains_a_pulse_during_the_fetch(conn):
    """The job's progress unit is sources, so a 450-page single-source fetch
    sat at '0/1, 0 requests' with a start-time heartbeat for a quarter hour —
    indistinguishable from a hang. The capture layer now hangs a throttled
    per-request hook on the fetcher; this drives it exactly as a fetcher would
    and reads what the panel reads."""
    import json

    from scrapex.capture import _job_progress
    from scrapex.jobs import create_job, job_logs

    job_ref = create_job(conn, ["GPP_ENERGY"])
    job_id = conn.execute("SELECT job_id FROM crawl_job WHERE job_ref=?",
                          (job_ref,)).fetchone()[0]
    tick = _job_progress(conn, job_id, "GPP_ENERGY")

    for count in range(1, 121):
        tick(count, f"https://example.test/page/{count}")

    row = conn.execute("SELECT counters_json, last_heartbeat_at FROM crawl_job "
                       "WHERE job_id=?", (job_id,)).fetchone()
    assert json.loads(row["counters_json"])["requests"] == 120, \
        "the Requests figure the panel shows never moved"
    assert row["last_heartbeat_at"], "no pulse — a watchdog reads this as a hang"
    lines = [entry["message"] for entry in job_logs(conn, job_ref)]
    assert "fetching — 50 requests so far" in lines
    assert "fetching — 100 requests so far" in lines
    # Throttled: two narrations for 120 pages, not 120.
    assert sum("fetching" in line for line in lines) == 2


def test_what_a_connector_could_not_collect_reaches_the_job_log(conn):
    """The run that lost NATURAL_GAS entirely logged three clean lines and read
    as a full success: the connector's warnings were printed by the CLI path
    and dropped by the job path. A loss the log never mentions is a loss the
    owner discovers from the data, months later."""
    from scrapex.capture import CaptureResult
    from scrapex.ingest import IngestResult
    from scrapex.jobs import create_job, job_logs, run_job_once

    def fake_capture(conn_, entry, job_id=None):
        return CaptureResult(
            ingest=IngestResult(source_key=entry.source_key, run_id=1),
            requests_count=5, tables=1, rows=3,
            warnings=["NATURAL_GAS/EG: country page published no local price"])

    class _Manifest:
        def get(self, key): return _entry()

    job_ref = create_job(conn, ["GPP_ENERGY"])
    run_job_once(conn, job_ref, _Manifest(), capture=fake_capture)

    lines = [(entry["level"], entry["message"]) for entry in job_logs(conn, job_ref)]
    assert ("warning", "NATURAL_GAS/EG: country page published no local price") in [
        (lvl.lower(), msg) for lvl, msg in lines], \
        "the connector's warning never reached the job log"
