"""A rule the data cannot teach you, and a count that watches it.

THE OWNER SUPPLIED THE RULE AND THE DATA CONFIRMED IT, in that order. He said
the membership number does not repeat. Measured afterwards over the 11,059
contractors of the first full crawl: 11,059 distinct numbers, none blank, none
shared. Without his sentence a repeat would have looked like ordinary data —
which is the whole reason this file exists. **The rule is not discoverable from
the rows**, so nothing in the pipeline could ever have derived it.

WHY IT COUNTS RATHER THAN REFUSES. A duplicate is not necessarily ScrapeX's
fault: the site may publish one, or a page may have shifted under a crawl that
took three hours. Throwing away an eleven-thousand-row dataset to punish one bad
row is not a guard, it is a tantrum. This reports beside the data, never in
front of it.

AND WHY IT IS NOT THE IDENTITY. `_validated_rows` refuses an approval outright
when ANY identity field is empty in ANY row — so a composite identity of
`contractor_id` + `membership_number` would let one contractor with a missing
number destroy a page of twenty. One identity, and a uniqueness count beside it.
"""
from __future__ import annotations

from pathlib import Path

from scrapex.extract.muqawil import check_drift, check_unique, read_listing

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "muqawil"
LISTING = (FIXTURES / "listing-en.html").read_text(encoding="utf-8")


def rows(**overrides):
    """Four synthetic contractors, easier to reason about than real markup."""
    made = [{"contractor_id": str(1000 + n),
             "card_membership_number": str(900_000 + n)} for n in range(4)]
    for index, value in overrides.items():
        made[int(index)]["card_membership_number"] = value
    return made


# ---- the rule holding --------------------------------------------------------

def test_the_real_listing_holds_the_rule():
    report = check_unique(read_listing(LISTING))

    assert report.holds
    assert report.checked == 4
    assert report.repeated == {}
    assert report.blank == ()
    assert "unique across 4 contractors" in report.summary()


def test_it_holds_across_pages_and_not_merely_within_one():
    """A repeat inside twenty rows is nearly impossible; a repeat across 865
    pages is the case worth catching. So it takes ROWS, never a page."""
    page_one = read_listing(LISTING)
    page_two = [dict(row, contractor_id=f"9{row['contractor_id']}",
                     card_membership_number=f"9{row['card_membership_number']}")
                for row in page_one]

    report = check_unique(page_one + page_two)

    assert report.holds
    assert report.checked == 8


# ---- the rule broken ---------------------------------------------------------

def test_two_contractors_sharing_a_number_are_named():
    shared = rows()
    shared[2]["card_membership_number"] = shared[0]["card_membership_number"]

    report = check_unique(shared)

    assert not report.holds
    assert report.repeated == {"900000": ("1000", "1002")}
    assert "shared by more than one contractor" in report.summary()
    assert "1,000" not in report.summary(), "four contractors, not a thousand"


def test_the_worst_offender_is_named_in_the_summary():
    """Three sharing one number is a different problem from two sharing it, and
    a summary that said only "1 duplicate" would hide which."""
    shared = rows()
    for index in (1, 2, 3):
        shared[index]["card_membership_number"] = "900000"

    report = check_unique(shared)

    assert "worst '900000' on 4 of them" in report.summary()


def test_the_same_contractor_read_twice_is_not_a_collision():
    """A page fetched twice, or a resumed crawl replaying a page, repeats the
    contractor AND its number. That is one contractor, not two — and counting it
    as a duplicate would report an error on a crawl that behaved perfectly."""
    twice = rows() + rows()

    report = check_unique(twice)

    assert report.holds, f"a replayed page was read as a collision: {report.summary()}"
    assert report.checked == 8


def test_a_blank_number_is_counted_but_is_not_a_duplicate():
    """Two contractors with no number share nothing — they are two absences.
    Counting them as a collision would report a fault where there is a gap."""
    thin = rows()
    thin[1]["card_membership_number"] = ""
    thin[2]["card_membership_number"] = "   "

    report = check_unique(thin)

    assert not report.holds
    assert report.repeated == {}, "two absences were read as a shared value"
    assert set(report.blank) == {"1001", "1002"}
    assert "2 blank" in report.summary()


def test_a_field_that_is_absent_altogether_counts_as_blank():
    report = check_unique([{"contractor_id": "1"}, {"contractor_id": "2"}])

    assert report.blank == ("1", "2")
    assert report.repeated == {}


# ---- it reports, it never refuses --------------------------------------------

def test_nothing_here_raises_however_bad_the_data_is():
    """An eleven-thousand-row dataset must not be thrown away to punish one bad
    row. The count belongs beside the data, not in front of it."""
    awful = [{"contractor_id": str(n), "card_membership_number": "same"}
             for n in range(50)]

    report = check_unique(awful)

    assert report.checked == 50
    assert len(report.repeated["same"]) == 50


def test_it_can_watch_a_field_other_than_the_one_it_was_written_for():
    """The rule is muqawil's, the mechanism is not. A second site with a second
    unique field should not need a second copy of this."""
    report = check_unique(
        [{"contractor_id": "1", "cr": "x"}, {"contractor_id": "2", "cr": "x"}],
        field_key="cr")

    assert report.field_key == "cr"
    assert report.repeated == {"x": ("1", "2")}


# ---- the crawl's own drift, which is a different question --------------------

def test_a_steady_listing_shows_every_contractor_once():
    paged = [(page, {"contractor_id": str(page * 10 + n)})
             for page in (1, 2, 3) for n in range(4)]

    drift = check_drift(paged)

    assert drift.steady
    assert (drift.pages, drift.rows, drift.distinct) == (3, 12, 12)
    assert drift.reshown == 0
    assert "every one a different contractor" in drift.summary()


def test_a_listing_that_moved_under_the_crawl_is_counted():
    """PROVED REAL, 2026-08-16: 865 pages of twenty offered 17,300 slots, 6,241
    went to a row already seen, and 11,059 contractors came back. The repeats
    were BYTE-IDENTICAL — one row read from two places, not two rows."""
    paged = [(1, {"contractor_id": "a"}), (1, {"contractor_id": "b"}),
             (2, {"contractor_id": "b"}), (2, {"contractor_id": "c"}),
             (3, {"contractor_id": "b"}), (3, {"contractor_id": "d"})]

    drift = check_drift(paged)

    assert not drift.steady
    assert (drift.rows, drift.distinct, drift.reshown) == (6, 4, 2)
    assert drift.repeated == {"b": 3}
    assert "worst b on 3 pages" in drift.summary()
    assert "never shown at all" in drift.summary(), (
        "the summary counts the repeats but does not say what they imply — the "
        "rows that were skipped are the finding, and they cannot be counted")


def test_the_same_contractor_twice_on_ONE_page_is_not_drift():
    """Drift is about a row MOVING between pages. Twice on one page is a parsing
    fault or a genuinely duplicated card, and calling it drift would send
    somebody to fix the crawl for a problem in the page."""
    paged = [(1, {"contractor_id": "a"}), (1, {"contractor_id": "a"})]

    drift = check_drift(paged)

    assert drift.steady, "one page counted as two"
    assert drift.rows == 2 and drift.distinct == 1


def test_drift_and_uniqueness_answer_different_questions():
    """The same data: unique membership numbers AND a listing that repeated.
    Reporting them together would let a clean uniqueness result read as a clean
    crawl, which is exactly the mistake the real run invited."""
    rows = [{"contractor_id": "a", "card_membership_number": "1"},
            {"contractor_id": "a", "card_membership_number": "1"}]

    assert check_unique(rows).holds, "one contractor read twice is one contractor"
    assert check_drift([(1, rows[0]), (2, rows[1])]).steady is False
