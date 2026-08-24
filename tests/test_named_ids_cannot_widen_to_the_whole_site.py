"""`--ids` that names nobody must REFUSE, never fall through to the registered scope.

WHY THIS FILE EXISTS, AND WHY IT IS ITS OWN FILE. This one hole was opened, closed,
and opened again by the repair for a different bug — three rounds of adversarial
review, three different states:

  round 2   `--ids ","` parsed to an empty tuple, `details()` took the else branch,
            and the registered scope is `full_then_listing`: **34,806 pages, about
            seventeen hours**, from a command that named nobody. The run did not even
            say so, because the `named N contractor(s)` line never printed.
  round 3   the repair called `_named_ids` unconditionally, and `args.ids` defaults
            to `""` — so the ORDINARY `--details --run-ref R` exited 2 with a usage
            error naming a flag the user never typed. The primary path, dead.
  round 4   the repair for THAT guarded on `args.ids.strip()`, which sent whitespace
            straight back down the round-2 path.

**There was no test on `--ids` in any of those rounds.** `grep` over `tests/` found
nothing touching `_named_ids` or `--details`, which is why a reviewer running the
command was the only thing that ever caught it. This file is that test, kept apart
from the parser suites so it cannot be lost in one.

THE RULE, in one line: **the flag being TYPED decides whether ids were meant; its
CONTENT decides whether they are usable.** Conflating the two is what produced all
three states.
"""
from __future__ import annotations

import pytest

from scrapex import contractors


# ---- what a usable list looks like ------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("881", ("881",)),
    ("881,20074580", ("881", "20074580")),
    (" 881 , 20074580 ", ("881", "20074580")),      # a pasted list has spaces
    ("881,881,881", ("881",)),                       # and repeats
    ("881,,20074580", ("881", "20074580")),          # and empty slots
    ("007", ("007",)),                               # leading zeros are the site's
])
def test_a_list_that_names_someone_is_taken(raw, expected):
    assert contractors._named_ids(raw) == expected


# ---- what must never widen ---------------------------------------------------

@pytest.mark.parametrize("raw", [",", " ", "  ", "\t", "\n", ",,", " , ", "  ,\t,  "])
def test_a_list_that_names_nobody_is_refused_and_never_widened(raw):
    """THE ROUND-2 AND ROUND-4 HOLE. Falling through here is not a smaller action
    than the one asked for — it is the largest action the tool can take."""
    with pytest.raises(SystemExit) as refused:
        contractors._named_ids(raw)
    assert refused.value.code == 2


@pytest.mark.parametrize("raw", ["abc", "?page=9999", "../../admin", "881;rm", "8 81",
                                 "٤٢", "４２", "²"])
def test_anything_that_is_not_an_ascii_number_is_refused(raw):
    """THE ROUND-2 INJECTION, and the round-3 hole inside its own repair.

    `profile_urls` interpolates, so `'?page=9999'` built a LISTING url and
    `'../../admin'` walked out of the path — and whatever came back was stored as
    DETAIL evidence a later `--approve` would route to the listing parser.

    `str.isdigit()` was the first fix and it is true of `٤٢`, `４２` and `²`, while
    `_contractor_of`'s `\\d` is not — so those passed the filter and broke the
    matching anyway. An id here is ASCII digits and nothing else."""
    with pytest.raises(SystemExit) as refused:
        contractors._named_ids(raw)
    assert refused.value.code == 2


def test_the_refusal_says_which_value_was_wrong(capsys):
    """A refusal that does not name the offender sends the reader back to a paste of
    fifty ids to find it by eye."""
    with pytest.raises(SystemExit):
        contractors._named_ids("881,abc,20074580")
    said = capsys.readouterr().err
    assert "'abc'" in said, f"the bad value was not named: {said!r}"


def test_the_empty_refusal_says_what_falling_through_would_have_done(capsys):
    """The message has to carry the consequence, because the consequence is the
    reason the refusal exists rather than a shrug."""
    with pytest.raises(SystemExit):
        contractors._named_ids("  ")
    said = capsys.readouterr().err
    assert "34,806" in said or "registered scope" in said, (
        f"the refusal does not say what it prevented: {said!r}")
