"""How hard to press one server, learned from how that server answers.

WHAT THIS IS NOT. It is not a way past anything. `HttpFetcher`'s own doctrine
already names what this project refuses — "user-agent rotation, proxy rotation,
header spoofing, CAPTCHA handling … those evade a decision the site has made" —
and that line holds here. This governor only ever makes a crawl *gentler* than
its ceiling; it cannot raise one above what the owner allowed, and every signal
it reads is one the server chose to send.

WHY IT EXISTS. Measured on muqawil.org, 2026-08-16: a page costs 5.84s, of which
**5.69s is the server thinking** and 0.51s is the wire. Compression is already
on, HTTP/2 changed nothing, and there is no `ETag` — so nothing client-side
touches the cost. The one lever that moved it was concurrency: four in flight
took 9.5s where four in series took 26.4s, a 2.8x gain with every answer a 200.

AND THE PRICE WAS VISIBLE IN THE SAME MEASUREMENT. Per-request latency rose from
~6.6s to ~9.2s under those four — a 40% rise. The server never refused, never
sent 429, never closed a connection. It just got slower. **That is a server
saying it is hurting in the only language it has**, and a crawler that waits for
a 429 before easing off has ignored the polite warning to wait for the rude one.

SO THE RULE IS AIMD, which is what TCP does about exactly this problem:

    additive increase       one more in flight, only after a clean, quiet run
    multiplicative decrease HALVE, at the first sign of strain

Slow to take, quick to give back. The asymmetry is the whole algorithm: the cost
of being one too gentle is a longer crawl, and the cost of being one too greedy
is somebody else's website.

THE BASELINE IS MEASURED UNCONTENDED, and this is the subtle part. If the
baseline were a rolling average of every request, it would rise as concurrency
rose, the comparison would always find "normal", and the latency signal would
never fire once. So the baseline is only ever learned at a concurrency of ONE —
the uncontended truth about this server — and everything else is compared
against it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Strain(StrEnum):
    """Why the governor eased off, so a report can say which it was."""

    NONE = "none"
    #: 429 or 503 — the server said so in words.
    REFUSED = "refused"
    #: `Retry-After` — it also named its price.
    TOLD_TO_WAIT = "told-to-wait"
    #: No refusal, just slower. The polite warning.
    SLOWED = "slowed"
    #: The connection failed outright.
    BROKE = "broke"


@dataclass(frozen=True)
class Answer:
    """One completed request, as the governor needs to see it.

    Deliberately not an `httpx.Response`: this module must stay testable without
    a network, and a governor that knew about HTTP would be a governor nobody
    could prove the behaviour of.
    """

    latency_s: float
    status: int | None = None
    retry_after_s: float | None = None
    failed: bool = False


@dataclass
class HostPace:
    """What has been learned about one host. One per host, never shared."""

    #: How many requests may be in flight. Starts at one: nothing is assumed
    #: about a server nobody has met.
    concurrency: int = 1
    #: The uncontended latency, learned at concurrency 1 and only there.
    baseline_s: float = 0.0
    #: Clean answers in a row at the current width.
    clean_run: int = 0
    #: Requests still to pass before another increase may be considered.
    cooldown: int = 0
    #: Seconds the server explicitly asked to be left alone for.
    owed_wait_s: float = 0.0
    last_strain: Strain = Strain.NONE
    #: Every easing, for the report: (from, to, why).
    eased: list[tuple[int, int, Strain]] = field(default_factory=list)


class PaceGovernor:
    """One governor for a whole crawl; one `HostPace` for each host in it."""

    def __init__(self, *, ceiling: int = 4, floor: int = 1,
                 clean_before_widening: int = 8,
                 slowdown_factor: float = 1.4,
                 cooldown_after_easing: int = 12) -> None:
        """`ceiling` is the OWNER'S limit and the governor never exceeds it.

        `slowdown_factor` of 1.4 comes from the muqawil measurement: four in
        flight cost 40% more per request. Set at exactly the rise that was
        observed to hurt, so the governor eases at the point the evidence says
        it should — not at a number chosen because it looked round.
        """
        if floor < 1:
            raise ValueError("a floor below one request in flight is a stopped crawl")
        if ceiling < floor:
            raise ValueError(f"ceiling {ceiling} is below floor {floor}")
        self._ceiling = ceiling
        self._floor = floor
        self._clean_before_widening = clean_before_widening
        self._slowdown_factor = slowdown_factor
        self._cooldown_after_easing = cooldown_after_easing
        self._hosts: dict[str, HostPace] = {}

    def pace_for(self, host: str) -> HostPace:
        """This host's learned state, created at the floor if it is new."""
        return self._hosts.setdefault(
            host, HostPace(concurrency=self._floor))

    def concurrency(self, host: str) -> int:
        return self.pace_for(host).concurrency

    def owed_wait_s(self, host: str) -> float:
        """Seconds this host asked to be left alone for, and paid once.

        Read-and-clear, because a `Retry-After` is a debt discharged by waiting
        it out. Leaving it set would make every later request pay it again.
        """
        pace = self.pace_for(host)
        owed, pace.owed_wait_s = pace.owed_wait_s, 0.0
        return owed

    def record(self, host: str, answer: Answer) -> Strain:
        """Take one answer and adjust. Returns what it made of it."""
        pace = self.pace_for(host)
        strain = self._strain(pace, answer)
        pace.last_strain = strain

        if strain is not Strain.NONE:
            self._ease(pace, strain, answer)
            return strain

        # ONLY A 200 MAY BUY SPEED, and this is Scrapy's rule taken whole.
        # `scrapy/extensions/throttle.py` ends `_adjust_delay` with a one-way
        # ratchet — a non-200 response may only ever RAISE the delay — and its
        # comment gives the reason: error pages and redirects are SMALL, so they
        # come back fast, and a latency-driven controller reads an error storm as
        # "the site just got quicker" and accelerates into it. A positive
        # feedback loop, at the exact moment the site is failing.
        #
        # It bites us harder than it bites them, because `HttpFetcher` sends
        # conditional requests: a re-crawl is mostly 304s, which carry NO BODY
        # AT ALL and so are the fastest answers a server can give. Without this
        # line every re-crawl would widen on its own emptiness.
        #
        # `!= 200` and not `< 400`, deliberately — 204, 206, 301, 302 and 304 are
        # all real answers and none of them is a page. A neutral answer neither
        # eases nor widens: it simply does not count.
        if answer.status is not None and answer.status != 200:
            return strain

        # LEARNED ONLY AT ONE IN FLIGHT. See the module docstring: a baseline
        # that moved with the load could never detect the load.
        if pace.concurrency == self._floor and answer.latency_s > 0:
            pace.baseline_s = (answer.latency_s if not pace.baseline_s
                               else (pace.baseline_s * 3 + answer.latency_s) / 4)

        if pace.cooldown > 0:
            pace.cooldown -= 1
            return strain

        pace.clean_run += 1
        if (pace.clean_run >= self._clean_before_widening
                and pace.concurrency < self._ceiling):
            pace.concurrency += 1
            pace.clean_run = 0
        return strain

    # -- what counts as the server saying "enough" -----------------------------

    def _strain(self, pace: HostPace, answer: Answer) -> Strain:
        if answer.retry_after_s:
            return Strain.TOLD_TO_WAIT
        if answer.failed:
            return Strain.BROKE
        if answer.status in (429, 503):
            return Strain.REFUSED
        # THE POLITE WARNING, and the only signal here that is not an error.
        # Needs a baseline to compare against, and there is none until the
        # governor has run at one in flight — so a crawl that starts wide by
        # configuration never gets this signal, which is a reason not to.
        if (pace.baseline_s > 0
                and answer.latency_s > pace.baseline_s * self._slowdown_factor):
            return Strain.SLOWED
        return Strain.NONE

    def _ease(self, pace: HostPace, strain: Strain, answer: Answer) -> None:
        """Halve, and remember why.

        HALVED RATHER THAN DECREMENTED. Stepping down by one from four to three
        keeps three quarters of the pressure that just caused this, and on a
        server already struggling that is another two rounds of strain before it
        gets relief. Multiplicative decrease is how the algorithm apologises.
        """
        was = pace.concurrency
        pace.concurrency = max(self._floor, pace.concurrency // 2)
        pace.clean_run = 0
        pace.cooldown = self._cooldown_after_easing
        if answer.retry_after_s:
            pace.owed_wait_s = max(pace.owed_wait_s, answer.retry_after_s)
        if pace.concurrency != was:
            pace.eased.append((was, pace.concurrency, strain))
