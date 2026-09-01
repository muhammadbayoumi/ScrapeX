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

import argparse
from types import SimpleNamespace

import pytest

from scrapex import contractors

# ---- what a usable list looks like ------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("881", ("881",)),
    ("881,20074580", ("881", "20074580")),
    (" 881 , 20074580 ", ("881", "20074580")),      # a pasted list has spaces
    ("881,881,881", ("881",)),                       # and repeats
    ("881,,20074580", ("881", "20074580")),          # and empty slots
    # A LEADING ZERO IS ACCEPTED AND THE SITE HAS NONE, which is worth stating
    # rather than implying either way. An adversarial review asked whether layer 1
    # would then refuse a good page — `read_profile` compares `contractor_id` to the
    # page's self-links by exact string, so `007` against a link written `/7/` would
    # raise `PageIsNotAProfile`. Measured over all 17,452 stored profile URLs: **zero
    # ids begin with a zero**, and the id space is 3, 4 or 8 digits. So the case is
    # unreachable, not handled. The comment this replaced said "leading zeros are the
    # site's" — true of `membership_number`, which `CONTRACTOR-SOURCE.md` documents as
    # text for exactly that reason, and not of the contractor id. Two different fields.
    ("007", ("007",)),
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


# ---- the GUARD, which is where all five states lived ------------------------
#
# Everything above calls `_named_ids` directly, and an adversarial review measured
# what that is worth: `contractors.run(` had ZERO call sites in `tests/`, and of the
# twelve calls to `details(` not one passed `ids=`. So reverting the guard to
# `args.ids.strip()`, or to an unconditional call, or to `if args.ids` left the whole
# suite green — three of the five states, undetectable. The tests below drive
# `contractors.run` through the real parser and assert on what `details` was handed.

@pytest.fixture
def parsed():
    """The real parser, so `default=` is under test and not restated here."""
    parser = argparse.ArgumentParser()
    contractors.add_arguments(parser)
    return parser


@pytest.fixture
def handed(monkeypatch):
    """`run` stubbed down to the decisions under test: which ids reach each mode."""
    seen: dict = {}

    def _details(conn, directory, fetch, fetcher, run_ref, **kw):
        seen["ids"] = kw.get("ids")

    def _approve(conn, directory, run_ref, **kw):
        seen["approve_ids"] = kw.get("ids")

    monkeypatch.setattr(contractors, "details", _details)
    monkeypatch.setattr(contractors, "approve", _approve)
    monkeypatch.setattr(contractors, "open_engine", lambda: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr(contractors, "get_directory", lambda key: SimpleNamespace(key="muqawil_org"))
    monkeypatch.setattr(contractors, "make_fetch", lambda pace: (None, None))
    monkeypatch.setattr(contractors, "say", lambda message: None)
    return seen


def test_the_ordinary_detail_run_is_not_a_usage_error(parsed, handed):
    """THE ROUND-3 STATE. `--details --run-ref R` with no `--ids` at all must reach
    `details` with an empty tuple — the primary path, which one repair killed
    outright by calling `_named_ids` on the default."""
    contractors.run(parsed.parse_args(["--details", "--run-ref", "R"]))
    assert handed["ids"] == ()


@pytest.mark.parametrize("typed", ["", " ", "  ", ",", ",,", " , ", "\t"])
def test_a_typed_but_empty_ids_flag_refuses_instead_of_widening(parsed, handed, typed):
    """THE ROUND-2, ROUND-4 AND ROUND-5 STATES, in one parametrisation.

    `""` is the round-5 case and the reason `--ids` now defaults to `None`: with
    `default=""` a typed empty string and an untyped flag are the same value, so a
    guard reading the value must get one of them wrong. The field trigger is
    ordinary — `--ids "$SELECTION"` with the variable unset."""
    with pytest.raises(SystemExit) as refused:
        contractors.run(parsed.parse_args(["--details", "--run-ref", "R", "--ids", typed]))
    assert refused.value.code == 2
    assert "ids" not in handed, (
        "details was reached anyway, and with no ids it crawls the registered scope")


def test_named_ids_reach_details_unchanged(parsed, handed):
    contractors.run(parsed.parse_args(
        ["--details", "--run-ref", "R", "--ids", "881, 20074580"]))
    assert handed["ids"] == ("881", "20074580")


def test_named_ids_reach_approve_unchanged(parsed, handed):
    contractors.run(parsed.parse_args(
        ["--approve", "--run-ref", "R", "--ids", "1089, 2079"]))
    assert handed["approve_ids"] == ("1089", "2079")


def test_a_typed_empty_ids_without_details_is_still_refused(parsed):
    """`validate` carried the same defect and the same fix. `--ids ""` without
    `--details` names work nothing will do, and read as absent it was allowed."""
    with pytest.raises(SystemExit) as refused:
        contractors.run(parsed.parse_args(["--coverage", "--ids", ""]))
    assert refused.value.code == 2
