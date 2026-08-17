"""Passing over a listing until the new names stop coming.

WHY A LISTING HAS TO BE READ MORE THAN ONCE. Measured on muqawil.org
2026-08-16: the same listing page is byte-stable for about thirty seconds and
then exchanges four of its twenty rows. Over a crawl of 865 pages taking 2.8
hours the effect is severe and one-sided — 17,275 rows came back and only
**11,059 were different contractors**. 6,216 slots went to a row already seen.

AND THE REPEATS ARE THE VISIBLE HALF OF AN INVISIBLE LOSS. A contractor that
slides from page 42 to page 41 is read twice; the one that slides from 41 to 42
is never read at all. All 4,556 repeats were byte-identical — not one differing
field, not one membership number on two companies — so this is not bad data. It
is one row read from two places, and the rows that were skipped left no trace.

TWO REMEDIES WERE MEASURED AND SET ASIDE BEFORE THIS ONE WAS BUILT:

  * A STABLE SORT. `sort`, `order`, `order_by`, `orderby`, `sort_by`,
    `direction` and `sort_field` were each tried against the live listing and
    NOT ONE changed the order. There is nothing to build.
  * A SLICE. `region_id` and `city_id` ARE honoured over GET, and blind
    pagination works under them — but a region is still hundreds of pages, so a
    sliced pass does not finish inside the thirty-second window either. It
    narrows the problem; it does not end it.

So: pass again, and keep passing while new names keep arriving. It assumes
nothing about the ordering, which is the only assumption this site has not
already broken.

WHAT "DRY" DOES NOT MEAN, and the owner named this himself: it does not mean the
directory is complete. It means THIS RUN stopped finding names IT had not seen.
The next run will legitimately find contractors that were registered since, and
find changed data on ones it already had — that is the directory living, not the
crawl failing. `generic_record.content_hash` and `generic_record_revision` are
what carry that across runs; this module is only ever about one run's own
convergence.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Pass:
    """One complete read of the listing."""

    number: int
    seen: int
    #: Ids this pass produced that no earlier pass in this run had.
    fresh: int

    @property
    def dry(self) -> bool:
        return self.fresh == 0


class Sweep:
    """Passes over one listing, and when to stop making them."""

    def __init__(self, *, dry_passes_before_stopping: int = 2,
                 max_passes: int = 10) -> None:
        """TWO DRY PASSES, NOT ONE, and the difference is not caution.

        A single dry pass is ordinary luck on a list that reshuffles: the pass
        can happen to revisit the same window twice and find nothing new while
        a thousand contractors sit in a part of the ordering it did not reach.
        Two in a row is a much weaker coincidence.

        `max_passes` is a CEILING AND NOT A TARGET. A sweep that hits it has NOT
        converged, and `converged` says so — a run that stopped counting is not
        a run that finished, and the two must never print the same word.
        """
        if dry_passes_before_stopping < 1:
            raise ValueError("a sweep that stops before a dry pass has not swept")
        if max_passes < 1:
            raise ValueError("a sweep of no passes reads nothing")
        self._needed = dry_passes_before_stopping
        self._max = max_passes
        self._found: set[str] = set()
        self._passes: list[Pass] = []
        self._dry_streak = 0

    def record(self, ids: Iterable[str]) -> Pass:
        """Take one pass's ids and say what it added."""
        before = len(self._found)
        # `if one` BEFORE `str(one)`, and the order is the bug that was there
        # first: `str(None)` is `"None"`, a perfectly non-empty string, so a
        # parser that failed to find an id would have contributed a contractor
        # called None to every pass — and it would have been the same one each
        # time, so the sweep would have gone dry looking convergent.
        self._found.update(str(one) for one in ids if one and str(one).strip())
        made = Pass(number=len(self._passes) + 1,
                    seen=len(self._found),
                    fresh=len(self._found) - before)
        self._passes.append(made)
        # THE STREAK RESETS ON ANY FIND, never decrements. One new contractor
        # after four dry passes means the list is still moving under us, and
        # counting that as "three quarters done" would stop a sweep that had
        # just proved it should not.
        self._dry_streak = self._dry_streak + 1 if made.dry else 0
        return made

    @property
    def keep_going(self) -> bool:
        if len(self._passes) >= self._max:
            return False
        return self._dry_streak < self._needed

    @property
    def converged(self) -> bool:
        """Dry for long enough — as opposed to merely stopped."""
        return self._dry_streak >= self._needed

    @property
    def found(self) -> frozenset[str]:
        return frozenset(self._found)

    @property
    def passes(self) -> tuple[Pass, ...]:
        return tuple(self._passes)

    def summary(self) -> str:
        made = len(self._passes)
        counts = " + ".join(str(one.fresh) for one in self._passes)
        if not self._passes:
            return "no passes made"
        if self.converged:
            return (f"{len(self._found):,} contractors after {made} passes "
                    f"({counts} new) — {self._dry_streak} dry passes in a row, so "
                    "this run has stopped finding names it had not seen. That is "
                    "not the directory being complete: a later run will "
                    "legitimately find contractors registered since, and changed "
                    "data on ones it already had.")
        return (f"{len(self._found):,} contractors after {made} passes "
                f"({counts} new) — STOPPED AT THE CEILING, NOT CONVERGED. The "
                f"last pass still brought {self._passes[-1].fresh:,} new names, "
                "so an unknown number remain unseen. Raise max_passes or accept "
                "a partial directory, but do not record this as complete.")
