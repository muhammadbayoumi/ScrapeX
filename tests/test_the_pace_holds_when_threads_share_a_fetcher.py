"""One request per interval, however many threads share the fetcher.

WHY THIS FILE EXISTS. Item 1 of the owner's speed plan is to crawl the partition's
cells concurrently — they are independent, which is what makes each one provable, and
the wall clock is dominated by muqawil's measured **six-second** latency rather than
by our one-second pace. But `HttpFetcher._throttle` read `_last_request_at`, slept,
and wrote it back **with no lock**, so concurrency would have multiplied the real
request rate instead of the throughput.

MEASURED BEFORE THE FIX, not argued: four threads, a 200 ms interval, five requests
each.

    20 requests in 1.02 s, against an honest minimum of 3.80 s
    14 of 19 gaps under the interval, the shortest 0.0 ms

`R-21` — «التوازى يجب ان يكون مصدر واحد يدير اى استعلام او اتصال بالانترنت» — and
`F5`'s one-request-a-second default are exactly what that would have broken, and it
would have shipped calling itself a speedup.

WHAT THE FIX MUST NOT COST, and the last test here is that: holding the lock across
the sleep serialises the SLOT, not the request. Requests still start one interval
apart and overlap on the network, which is where the win is.
"""
from __future__ import annotations

import threading
import time
from itertools import pairwise

import pytest

from scrapex.connectors.base import HttpFetcher

#: Short enough to keep the suite quick, long enough that a breach is unambiguous
#: against the ~15.6 ms resolution of this platform's monotonic clock.
INTERVAL = 0.08
WORKERS = 4
EACH = 4


@pytest.fixture()
def fetcher():
    one = HttpFetcher(min_interval_s=INTERVAL, jitter=0.0)
    try:
        yield one
    finally:
        one.close()


def stamps_from(fetcher, workers: int = WORKERS, each: int = EACH) -> list[float]:
    """Every moment the pacer let a request through, across `workers` threads.

    `_throttle` is called directly. The alternative is a fake HTTP server, which
    would measure sockets as well as the pace and make a failure ambiguous.
    """
    fired: list[float] = []
    guard = threading.Lock()

    def worker() -> None:
        for _ in range(each):
            fetcher._throttle()
            with guard:
                fired.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return sorted(fired)


def gaps(stamps: list[float]) -> list[float]:
    return [b - a for a, b in pairwise(stamps)]


def test_no_two_requests_are_closer_than_the_interval(fetcher):
    """THE DEFECT, reproduced. Before the lock the shortest gap was 0.0 ms."""
    stamps = stamps_from(fetcher)

    # HALF AN INTERVAL, and the tolerance is for the MEASUREMENT and not the rule.
    # The stamp is taken after `_throttle` returns, so a thread preempted between
    # taking its slot and recording it reports a later time than its slot — which
    # makes the NEXT gap read shorter than it was. Measured 2026-08-21: this test
    # failed at `INTERVAL * 0.9` on a machine running six crawl workers and a test
    # suite, with no defect present.
    #
    # IT STILL CATCHES THE DEFECT DECISIVELY. Without the lock the gaps were
    # **0.0 ms** — four threads firing together — so half an interval is not a
    # weakened assertion, it is the same assertion with room for the clock. The
    # strict statement of the rule is the wall-clock test below, which cannot be
    # fooled by per-stamp jitter because it measures the whole run.
    floor = INTERVAL * 0.5
    breaches = [round(g * 1000, 1) for g in gaps(stamps) if g < floor]
    assert not breaches, f"gaps under {floor * 1000:.0f}ms: {breaches}"


def test_the_wall_clock_reflects_the_honest_minimum(fetcher):
    """A rate limit that is respected costs time, and that cost is the evidence.
    Before the lock, 20 requests took 1.02 s where 3.80 s was owed."""
    start = time.monotonic()
    stamps = stamps_from(fetcher)
    span = time.monotonic() - start

    owed = (len(stamps) - 1) * INTERVAL
    assert span >= owed * 0.9, f"{span:.2f}s for work that owes {owed:.2f}s"


def test_every_request_is_accounted_for(fetcher):
    """The lock must not lose a caller — a pacer that drops requests would look
    beautifully compliant and collect nothing."""
    assert len(stamps_from(fetcher)) == WORKERS * EACH


def test_one_thread_is_unaffected(fetcher):
    """The single-threaded path is the common one and must not have slowed down."""
    start = time.monotonic()
    stamps = stamps_from(fetcher, workers=1, each=EACH)
    span = time.monotonic() - start

    assert len(stamps) == EACH
    # (EACH - 1) intervals are owed, plus the first call which pays nothing.
    assert span < INTERVAL * (EACH + 1)


def test_a_slot_already_earned_is_not_paid_for_twice(fetcher):
    """FOUND BY A MUTATION THAT SURVIVED. `time.sleep(interval)` unconditionally —
    ignoring how long has actually passed — breaks no rate limit and is therefore
    invisible to every other test here: it is STRICTER than required, so no gap is
    ever too short and the wall clock is never too small.

    It is still wrong. The interval is a floor on the gap between requests, not a
    toll on each one, so a caller that waited longer than the interval for its own
    reasons must not be made to wait again. Over a crawl that does anything between
    requests — parsing, storing, recovering ids off disk — that is the whole pace
    paid a second time.
    """
    fetcher._throttle()          # take a slot
    time.sleep(INTERVAL * 2)     # and then be slow for entirely other reasons

    start = time.monotonic()
    fetcher._throttle()
    waited = time.monotonic() - start

    assert waited < INTERVAL / 2, (
        f"waited {waited * 1000:.0f}ms after a {INTERVAL * 2 * 1000:.0f}ms pause; "
        "the interval had already elapsed and nothing was owed")


def test_the_slot_is_serialised_and_not_the_request(fetcher):
    """WHAT THE FIX MUST NOT COST. If the lock were held across the whole request,
    concurrency would buy nothing at all: with a 1 s pace and a 6 s latency the
    crawl would still take 6 s a page instead of 1 s.

    Simulated by pacing and then sleeping far longer than the interval, as a real
    fetch does. The total must reflect the PACE, not the sum of the latencies.
    """
    latency = INTERVAL * 4
    done: list[float] = []
    guard = threading.Lock()

    def worker() -> None:
        fetcher._throttle()
        time.sleep(latency)        # the network, which must overlap
        with guard:
            done.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(WORKERS)]
    start = time.monotonic()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    span = time.monotonic() - start

    serial = WORKERS * latency
    assert span < serial * 0.8, (
        f"{span:.2f}s is close to the serial {serial:.2f}s — the requests are not "
        "overlapping, so the lock is being held across the fetch")
