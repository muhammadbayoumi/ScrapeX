"""Passing over a listing until the new names stop coming.

WHY THIS EXISTS, measured: muqawil's listing is byte-stable for about thirty
seconds and then exchanges four of its twenty rows. A 2.8-hour crawl of 865
pages returned 17,275 rows and only 11,059 different contractors — 6,216 slots
spent on a row already seen, and an unknown number of rows never shown at all.

The two other remedies were measured first and set aside: no ordering parameter
is honoured (seven were tried), and a region slice is still hundreds of pages so
it does not finish inside the window either.

THE DISTINCTION THIS FILE GUARDS MOST CAREFULLY is the owner's own: a sweep that
goes dry has not proved the directory complete. It has proved that THIS RUN
stopped finding names IT had not seen. The next run will legitimately find new
contractors and changed data, and a report that said "complete" would make that
read as a fault.
"""
from __future__ import annotations

import pytest

from scrapex.sweep import Sweep


def test_a_sweep_that_finds_nothing_new_twice_has_converged():
    sweep = Sweep(dry_passes_before_stopping=2)

    sweep.record(["a", "b", "c"])
    assert sweep.keep_going, "stopped after one pass, having proved nothing"
    sweep.record(["a", "b", "c"])
    assert sweep.keep_going, "one dry pass is ordinary luck on a shuffling list"
    sweep.record(["a", "b", "c"])

    assert sweep.converged
    assert not sweep.keep_going
    assert sweep.found == {"a", "b", "c"}


def test_each_pass_reports_only_what_it_added():
    sweep = Sweep()

    first = sweep.record(["a", "b"])
    second = sweep.record(["b", "c", "d"])

    assert (first.number, first.seen, first.fresh) == (1, 2, 2)
    assert (second.number, second.seen, second.fresh) == (2, 4, 2)
    assert not second.dry


def test_one_new_name_after_four_dry_passes_resets_the_streak():
    """THE STREAK RESETS, IT NEVER DECREMENTS. A new contractor after four quiet
    passes means the list is still moving underneath, and treating that as
    "three quarters done" would stop a sweep that had just proved it should
    not."""
    sweep = Sweep(dry_passes_before_stopping=2, max_passes=20)
    sweep.record(["a"])
    for _ in range(4):
        sweep.record(["a"])
    assert sweep.converged

    sweep.record(["a", "b"])

    assert not sweep.converged
    assert sweep.keep_going, "a fresh name did not restart the sweep"


# ---- the two things that must never print the same word ----------------------

def test_stopping_at_the_ceiling_is_not_converging():
    """A run that stopped counting is not a run that finished."""
    sweep = Sweep(dry_passes_before_stopping=2, max_passes=3)

    for n in range(3):
        sweep.record([f"pass{n}"])          # every pass still bringing names

    assert not sweep.keep_going, "it ran past its own ceiling"
    assert not sweep.converged, "a ceiling was reported as convergence"


def test_the_summary_says_which_of_the_two_happened():
    stopped = Sweep(dry_passes_before_stopping=2, max_passes=2)
    stopped.record(["a"])
    stopped.record(["b"])

    said = stopped.summary()
    assert "STOPPED AT THE CEILING, NOT CONVERGED" in said
    assert "do not record this as complete" in said
    assert "1 new names" in said or "1," in said


def test_a_converged_summary_refuses_to_claim_the_directory_is_complete():
    """THE OWNER'S OWN POINT. Re-crawling later will find contractors registered
    since and changed data on ones already held — that is the directory living,
    not the crawl failing, and the wording must not invite the opposite
    reading."""
    sweep = Sweep(dry_passes_before_stopping=2)
    sweep.record(["a", "b"])
    sweep.record(["a", "b"])
    sweep.record(["a", "b"])

    said = sweep.summary()
    assert "stopped finding names it had not seen" in said
    assert "not the directory being complete" in said
    assert "registered since" in said


def test_it_reports_what_each_pass_contributed_so_the_shape_is_visible():
    """`11,059 + 900 + 40 + 0 + 0` tells you the crawl was converging.
    `11,059 + 900 + 800 + 750` tells you it was not, and the total alone hides
    which."""
    sweep = Sweep(dry_passes_before_stopping=2)
    sweep.record([str(n) for n in range(100)])
    sweep.record([str(n) for n in range(110)])
    sweep.record([str(n) for n in range(110)])
    sweep.record([str(n) for n in range(110)])

    assert "100 + 10 + 0 + 0" in sweep.summary()


# ---- what it refuses to be built as ------------------------------------------

def test_a_sweep_that_stops_before_a_dry_pass_is_refused():
    with pytest.raises(ValueError, match="has not swept"):
        Sweep(dry_passes_before_stopping=0)


def test_a_sweep_of_no_passes_is_refused():
    with pytest.raises(ValueError, match="reads nothing"):
        Sweep(max_passes=0)


def test_blank_ids_are_not_counted_as_names():
    sweep = Sweep()

    made = sweep.record(["a", "", None, "b"])

    assert made.fresh == 2
    assert sweep.found == {"a", "b"}


def test_nothing_recorded_yet_says_so_rather_than_claiming_zero_contractors():
    assert Sweep().summary() == "no passes made"
