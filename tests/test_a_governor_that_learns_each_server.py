"""How hard to press one server, learned from how that server answers.

WHY THE LATENCY SIGNAL IS THE POINT OF THIS FILE. Measured on muqawil.org,
2026-08-16: four requests in flight cost 9.5s where four in series cost 26.4s —
a 2.8x gain, every answer a 200. And in the same measurement, per-request
latency rose from ~6.6s to ~9.2s. The server never refused, never sent 429,
never closed a connection. It just got slower.

That is a server saying it is hurting in the only language it has, and a crawler
that waits for a 429 before easing off has ignored the polite warning in order
to wait for the rude one. Half these tests are about hearing the polite one.

No network, no clock, no sleeping: the governor takes answers as data.
"""
from __future__ import annotations

import pytest

from scrapex.pacegovernor import Answer, PaceGovernor, Strain

HOST = "muqawil.org"


def clean(latency_s: float = 6.0) -> Answer:
    return Answer(latency_s=latency_s, status=200)


def settle(governor: PaceGovernor, host: str = HOST, *, at: float = 6.0,
           rounds: int = 40) -> None:
    """Feed clean answers until the governor has widened as far as it will."""
    for _ in range(rounds):
        governor.record(host, clean(at))


# ---- it starts by assuming nothing -------------------------------------------

def test_a_server_nobody_has_met_gets_one_request_at_a_time():
    """Starting wide would press an unknown server hardest at the moment least
    is known about it — and would also destroy the baseline, which can only be
    learned uncontended."""
    assert PaceGovernor().concurrency("a-site-never-seen.test") == 1


def test_it_widens_only_after_a_run_of_clean_answers():
    governor = PaceGovernor(ceiling=4, clean_before_widening=8)

    for _ in range(7):
        governor.record(HOST, clean())
    assert governor.concurrency(HOST) == 1, "widened before it had earned it"

    governor.record(HOST, clean())
    assert governor.concurrency(HOST) == 2


def test_it_never_goes_past_the_ceiling_the_owner_set():
    """The ceiling is the owner's decision about his relationship with a site.
    Nothing the server does may talk the governor above it."""
    governor = PaceGovernor(ceiling=3, clean_before_widening=2)
    settle(governor)

    assert governor.concurrency(HOST) == 3


# ---- the polite warning, which is the reason this file exists ----------------

def test_a_server_that_only_got_slower_is_heard():
    """No refusal, no 429, no broken connection — just 40% more latency, which
    is exactly what muqawil did under four in flight."""
    governor = PaceGovernor(ceiling=8, clean_before_widening=2, slowdown_factor=1.4)
    settle(governor, at=6.0)
    was = governor.concurrency(HOST)
    assert was > 1, "the run never widened, so there is nothing to ease"

    strain = governor.record(HOST, Answer(latency_s=9.2, status=200))

    assert strain is Strain.SLOWED
    assert governor.concurrency(HOST) == was // 2


def test_a_slowdown_within_the_normal_spread_is_not_a_signal():
    """Servers vary. Easing on every wobble would ratchet a crawl down to one
    and keep it there, which is a crawl that never finishes rather than a polite
    one."""
    governor = PaceGovernor(ceiling=8, clean_before_widening=2, slowdown_factor=1.4)
    settle(governor, at=6.0)
    was = governor.concurrency(HOST)

    assert governor.record(HOST, Answer(latency_s=8.0, status=200)) is Strain.NONE
    assert governor.concurrency(HOST) == was


def test_the_baseline_is_learned_uncontended_and_never_drifts_up_with_the_load():
    """THE SUBTLE ONE, AND THE TEST FOR IT HAD TO BE BUILT TWICE.

    A baseline averaged over every request would rise as concurrency rose, the
    comparison would always find "normal", and the latency signal would never
    fire again in the life of the crawl.

    The first version of this test fed obviously-slow answers and proved
    nothing: a slow answer is classified as strain and returns BEFORE the
    baseline is touched, so the drift it was written to catch was unreachable.

    The drift only happens through answers that are slower but still CLEAN —
    inside the tolerated band. So this widens, feeds a long run at 1.3x (below
    the 1.4 threshold, so never strain), and then asks whether a genuinely slow
    answer is still recognised. With a drifting baseline it would not be: 8.4s
    would have become the new normal and 9.0s would read as fine.
    """
    governor = PaceGovernor(ceiling=8, clean_before_widening=2, slowdown_factor=1.4)

    for _ in range(6):
        governor.record(HOST, clean(6.0))
    baseline = governor.pace_for(HOST).baseline_s
    assert governor.concurrency(HOST) > 1, "it never widened, so nothing can drift"

    # Acceptably slower, over and over. Never strain, so never an early return.
    for _ in range(20):
        assert governor.record(HOST, clean(7.8)) is Strain.NONE

    assert governor.pace_for(HOST).baseline_s == pytest.approx(baseline, rel=0.01), (
        "the baseline moved with the load, so the load can never be detected")
    assert governor.record(HOST, clean(9.0)) is Strain.SLOWED, (
        "a 50% slowdown went unheard — the baseline had crept up behind it")


# ---- the rude warnings -------------------------------------------------------

@pytest.mark.parametrize("status, why", [(429, Strain.REFUSED), (503, Strain.REFUSED)])
def test_a_refusal_halves_it(status, why):
    governor = PaceGovernor(ceiling=8, clean_before_widening=2)
    settle(governor)
    was = governor.concurrency(HOST)

    assert governor.record(HOST, Answer(latency_s=1.0, status=status)) is why
    assert governor.concurrency(HOST) == was // 2


def test_a_broken_connection_is_strain_and_not_merely_a_failure():
    governor = PaceGovernor(ceiling=8, clean_before_widening=2)
    settle(governor)
    was = governor.concurrency(HOST)

    assert governor.record(HOST, Answer(latency_s=0.0, failed=True)) is Strain.BROKE
    assert governor.concurrency(HOST) == was // 2


def test_it_halves_rather_than_stepping_down_by_one():
    """Stepping four down to three keeps three quarters of the pressure that
    just caused the strain, and on a server already struggling that is two more
    rounds of it before any relief. Multiplicative decrease is the apology."""
    governor = PaceGovernor(ceiling=8, clean_before_widening=1)
    settle(governor)
    assert governor.concurrency(HOST) == 8

    governor.record(HOST, Answer(latency_s=1.0, status=429))
    assert governor.concurrency(HOST) == 4, "stepped down by one instead of halving"


def test_it_never_eases_below_the_floor():
    governor = PaceGovernor(ceiling=4, floor=1)

    for _ in range(10):
        governor.record(HOST, Answer(latency_s=1.0, status=429))

    assert governor.concurrency(HOST) == 1, "a floor of zero is a stopped crawl"


# ---- Retry-After, which is the server naming its own price -------------------

def test_a_named_wait_is_owed_and_paid_once():
    governor = PaceGovernor()

    governor.record(HOST, Answer(latency_s=1.0, status=429, retry_after_s=30.0))

    assert governor.owed_wait_s(HOST) == 30.0
    assert governor.owed_wait_s(HOST) == 0.0, (
        "the debt was charged twice — a Retry-After is discharged by waiting it "
        "out once, not by every request after it")


def test_the_longest_named_wait_wins_when_two_arrive():
    governor = PaceGovernor()

    governor.record(HOST, Answer(latency_s=1.0, status=429, retry_after_s=10.0))
    governor.record(HOST, Answer(latency_s=1.0, status=429, retry_after_s=60.0))

    assert governor.owed_wait_s(HOST) == 60.0


# ---- recovery, and not oscillating -------------------------------------------

def test_it_does_not_widen_again_the_moment_after_it_eased():
    """Without a cooldown the governor oscillates: ease, widen, ease, widen —
    pressing hardest exactly when the server is least able to take it."""
    governor = PaceGovernor(ceiling=8, clean_before_widening=2,
                            cooldown_after_easing=12)
    settle(governor)
    governor.record(HOST, Answer(latency_s=1.0, status=429))
    eased_to = governor.concurrency(HOST)

    for _ in range(11):
        governor.record(HOST, clean())
    assert governor.concurrency(HOST) == eased_to, "widened during the cooldown"


def test_it_does_recover_once_the_server_has_been_quiet_for_a_while():
    """A governor that only ever eased would end every long crawl at one."""
    governor = PaceGovernor(ceiling=8, clean_before_widening=2,
                            cooldown_after_easing=4)
    settle(governor)
    governor.record(HOST, Answer(latency_s=1.0, status=429))
    eased_to = governor.concurrency(HOST)

    settle(governor)
    assert governor.concurrency(HOST) > eased_to


# ---- one host's lesson is not another's --------------------------------------

def test_what_was_learned_about_one_server_is_not_applied_to_another():
    """muqawil taking five seconds a page says nothing about alsweed, and a
    429 from one must not throttle a crawl of the other."""
    governor = PaceGovernor(ceiling=4, clean_before_widening=2)
    settle(governor, "muqawil.org")
    settle(governor, "alsweed.sa")
    assert governor.concurrency("alsweed.sa") == 4

    governor.record("muqawil.org", Answer(latency_s=1.0, status=429))

    assert governor.concurrency("muqawil.org") == 2
    assert governor.concurrency("alsweed.sa") == 4, "one site's 429 throttled another"


# ---- what it refuses to be built as ------------------------------------------

def test_a_floor_below_one_is_refused():
    with pytest.raises(ValueError, match="stopped crawl"):
        PaceGovernor(floor=0)


def test_a_ceiling_below_the_floor_is_refused():
    with pytest.raises(ValueError, match="below floor"):
        PaceGovernor(ceiling=1, floor=2)


def test_every_easing_is_remembered_so_a_report_can_say_what_happened():
    """A crawl that quietly ran at one for nine hours because of a 429 in
    minute two is a crawl whose duration nobody can explain afterwards."""
    governor = PaceGovernor(ceiling=8, clean_before_widening=1)
    settle(governor)
    governor.record(HOST, Answer(latency_s=1.0, status=429, retry_after_s=5.0))

    assert governor.pace_for(HOST).eased == [(8, 4, Strain.TOLD_TO_WAIT)]


# ---- only a 200 may buy speed -----------------------------------------------
#
# Scrapy's ratchet, taken whole. `scrapy/extensions/throttle.py` ends
# `_adjust_delay` by refusing to let a non-200 lower the delay, and its comment
# gives the reason: error pages and redirects are SMALL, so they come back fast,
# and a latency-driven controller reads an error storm as "the site got quicker"
# and accelerates into it — at the exact moment the site is failing.

@pytest.mark.parametrize("status", [404, 301, 302, 500, 204, 206])
def test_a_fast_error_never_widens_the_crawl(status):
    """A 404 page is a few hundred bytes and answers in milliseconds. Counted as
    clean, a storm of them is the fastest the server has ever looked."""
    governor = PaceGovernor(ceiling=8, clean_before_widening=2)
    settle(governor, at=6.0)
    was = governor.concurrency(HOST)

    for _ in range(20):
        governor.record(HOST, Answer(latency_s=0.05, status=status))

    assert governor.concurrency(HOST) == was, (
        f"twenty fast {status}s widened the crawl — the site is failing and we "
        "sped up")


def test_a_304_is_the_sharpest_case_because_it_carries_no_body_at_all():
    """`HttpFetcher` sends conditional requests, so a RE-crawl is mostly 304s.
    They are the fastest answer a server can give — nothing is sent. Without
    the ratchet every re-crawl would widen on its own emptiness."""
    governor = PaceGovernor(ceiling=8, clean_before_widening=2)
    settle(governor, at=6.0)
    was = governor.concurrency(HOST)

    for _ in range(30):
        governor.record(HOST, Answer(latency_s=0.01, status=304))

    assert governor.concurrency(HOST) == was


def test_a_fast_error_does_not_teach_the_baseline_either():
    """The second half of the same defect. A baseline dragged down by empty
    error pages makes the slowdown threshold far too tight, and the governor
    then eases on ordinary healthy responses."""
    governor = PaceGovernor(ceiling=8, clean_before_widening=99)
    for _ in range(6):
        governor.record(HOST, clean(6.0))
    baseline = governor.pace_for(HOST).baseline_s

    for _ in range(20):
        governor.record(HOST, Answer(latency_s=0.02, status=404))

    assert governor.pace_for(HOST).baseline_s == pytest.approx(baseline, rel=0.01), (
        "empty error pages taught the governor that this server is fast")


def test_an_error_is_neutral_and_not_a_reason_to_ease():
    """It must not widen, and it must not narrow either. A 404 is a missing
    page, not a server in distress — easing on one would shrink a crawl for
    every dead link in a directory."""
    governor = PaceGovernor(ceiling=8, clean_before_widening=2)
    settle(governor, at=6.0)
    was = governor.concurrency(HOST)

    assert governor.record(HOST, Answer(latency_s=0.05, status=404)) is Strain.NONE
    assert governor.concurrency(HOST) == was


def test_a_real_200_still_buys_speed_after_a_run_of_errors():
    """The ratchet must not JAM. It refuses to let an error buy speed; it must
    not also refuse the 200 that comes after one."""
    governor = PaceGovernor(ceiling=8, clean_before_widening=2)
    governor.record(HOST, Answer(latency_s=1.0, status=429))     # eased to 1
    for _ in range(20):
        governor.record(HOST, Answer(latency_s=0.05, status=404))
    was = governor.concurrency(HOST)
    assert was == 1, "the errors themselves moved it"

    settle(governor, at=6.0)

    assert governor.concurrency(HOST) > was, "the ratchet jammed shut"


def test_an_answer_with_no_status_is_still_read_as_clean():
    """A fetcher that reports latency without a status — the governor's own
    tests do — must keep working, or every existing caller silently stops
    widening."""
    governor = PaceGovernor(ceiling=4, clean_before_widening=2)

    for _ in range(6):
        governor.record(HOST, Answer(latency_s=6.0))

    assert governor.concurrency(HOST) > 1
