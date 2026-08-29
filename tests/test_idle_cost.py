"""What an engine serving NOTHING is allowed to cost.

Measured on 2026-07-31: a `scrapex ui` started from the Startup folder had
accumulated 6036 seconds of CPU over 4.6 hours of complete idleness — no crawl
queued, no browser attached — and sampling it showed 44-52% of one core. Two
such engines (ports 8000 and 8010) were between them eating ~42% of the
machine's total physical CPU.

It was not the poll loop's frequency and not a busy-wait: `_stop.wait(0.5)` is a
proper blocking Event.wait. It was one line of the poll BODY. `_refresh_rates`
built its transport eagerly, to pass in:

    batch = rates.refresh_if_due(conn, HttpFetcher())

`HttpFetcher()` constructs an httpx.Client, which builds an SSL context, which
calls `load_verify_locations` and reloads the whole OS certificate store — 1.3s
of pure CPU on this machine. Python evaluates the argument first, so the engine
paid that twice a second in order to hand a fully-armed HTTPS client to a
function whose first act, for six hours out of every six hours and one poll, was
`return None`. Bisecting proved where it lived: uvicorn with the worker off idled
at 0.1% of a core; the worker alone idled at 30%.

The cost of this is not only the waste. It silently stretches everything else on
the machine, including this suite: `dbmod.migrate()` measured 5.945s with two
idle engines running against 1.9s beside none, which is the kind of thing that
gets blamed on the code under test.

These tests are about the shape of the idle path, not about rates. The cheap
question must be asked before anything expensive is built — so the first test
is the one that will still fail if someone reintroduces the cost by a different
route, and it does not depend on a clock at all.
"""
from __future__ import annotations

import sqlite3
import time

import pytest

from scrapex import db as dbmod
from scrapex import rates
from scrapex.jobs import JobRunner


def _idle_warehouse(path) -> None:
    """A warehouse in the state a real idle engine is in: priced rows, so the
    USD column has currencies to convert, and a rate check that already
    happened — the ordinary case, and the one that was expensive."""
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    conn.execute("INSERT INTO source_site (source_id, source_key, source_name_ar, "
                 " source_name, base_url, platform, currency, timezone, authority, lifecycle) "
                 "VALUES (1,'S','س','S','http://s','custom_json','SAR','UTC','shop','active')")
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
    # We asked just now, so no refresh is due — the state an engine spends
    # virtually all of its life in.
    conn.execute("INSERT INTO scrapex_meta (key, value) VALUES (?,?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (rates.LAST_CHECK_KEY, rates.utc_now_iso()))
    conn.commit()
    conn.close()


def test_an_idle_poll_never_builds_an_http_client(tmp_path, monkeypatch):
    """THE regression test for the 44% core. No clock, no threshold: the idle
    path must not construct the transport at all.

    A timing assertion alone would let this back in the moment someone finds a
    cheaper way to build an SSL context — the bug is that a decline pays for
    machinery it never uses, and that is what is asserted.
    """
    from scrapex.connectors import base

    db = tmp_path / "idle.db"
    _idle_warehouse(db)

    built = []

    class _Tripwire:
        def __init__(self, *args, **kwargs):
            built.append(1)

    # _refresh_rates imports HttpFetcher from this module inside the function,
    # so patching the attribute is what the call will actually resolve.
    monkeypatch.setattr(base, "HttpFetcher", _Tripwire)

    runner = JobRunner(str(db), lambda: None, path_provider=lambda: str(db))
    conn = dbmod.connect(db)
    try:
        for _ in range(50):
            runner._refresh_rates(conn)
    finally:
        conn.close()

    assert built == [], (
        f"{len(built)} HTTPS client(s) built across 50 idle polls. Whatever a "
        "refresh needs but a DECLINE does not — above all the transport, whose "
        "constructor reloads the OS certificate store — belongs on the far side "
        "of rates.refresh_is_due.")


def test_an_idle_poll_does_not_take_the_write_lock(tmp_path):
    """The cheaper half of the same mistake: the lock file was created, written,
    and unlinked twice a second, 172,800 times a day, to be told no. It also put
    ~/.scrapex/marketlens/marketlens.db.lock under constant churn, which is
    where the owner first noticed something was moving."""
    db = tmp_path / "lock.db"
    _idle_warehouse(db)
    lock_path = str(db) + ".lock"

    taken = []
    real = dbmod.write_lock

    def counting(path, *args, **kwargs):
        taken.append(str(path))
        return real(path, *args, **kwargs)

    runner = JobRunner(str(db), lambda: None, path_provider=lambda: str(db))
    conn = dbmod.connect(db)
    original = dbmod.write_lock
    dbmod.write_lock = counting
    try:
        for _ in range(20):
            runner._refresh_rates(conn)
    finally:
        dbmod.write_lock = original
        conn.close()

    assert taken == [], f"idle polls took the write lock {len(taken)} times"
    import os
    assert not os.path.exists(lock_path)


def test_an_idle_engine_uses_almost_no_cpu(tmp_path):
    """The end-to-end guard, in the units the problem was reported in.

    Measured as CPU TIME, not wall time, so a loaded machine makes this test
    slower but never flakier — a busy CI box does not inflate how much CPU our
    own threads burned. The gap it is policing is enormous (about 0.9s of CPU
    over this window before the fix, against roughly nothing after), so the
    threshold sits far from both.
    """
    db = tmp_path / "cpu.db"
    _idle_warehouse(db)

    runner = JobRunner(str(db), lambda: None, path_provider=lambda: str(db))
    runner.start()
    try:
        time.sleep(1.0)                      # let the first pass settle
        started = time.process_time()
        time.sleep(3.0)
        burned = time.process_time() - started
    finally:
        runner.stop()

    assert burned < 0.5, (
        f"an idle worker burned {burned:.2f}s of CPU in 3s of doing nothing "
        f"(~{100 * burned / 3:.0f}% of a core). An engine serving nothing must "
        "cost nothing; see this module's docstring for how this went unnoticed "
        "for hours at a time.")
