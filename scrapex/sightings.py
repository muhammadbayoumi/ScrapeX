"""What the site showed us, as against what we managed to store.

THE INCIDENT THIS EXISTS FOR. The owner asked whether membership number
10001274 was in the warehouse. It was not, and the site answers 200 for it —
شركة عبر المملكة سبك, active, a member since 2018/08/25. Its neighbours bracket
it exactly: membership 10001271 is our contractor 1298, 10001276 is our 1303,
and the id in his URL is 1301. **So the warehouse answered "does not exist"
about a real company, and had no way to know it was guessing.**

The information to answer him properly had existed and been thrown away.
`scrapex/sweep.py` accumulates every id it sees in a set and offers it as
`found`; `tools/sweep_muqawil.py` calls `record()`, prints `summary()`, and
never reads it. Six passes over 8h37m saw at least 17,283 contractors, the count
reached a log file, and the ids died with the process.

SO THE DISTINCTION THIS MODULE DRAWS is between two things that were previously
one: a contractor we STORED, and a contractor the site SHOWED US. The gap
between them is the answer to "what are we missing", and it is not derivable
from either side alone.

WHAT A SIGHTING IS NOT. It is not a record with missing fields, and it must
never be read as one — nothing here carries a company name, a city or a rating.
It carries an id, when it was first and last seen, and how many times. That is
deliberately the least that answers the question.
"""
from __future__ import annotations

import itertools
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class Coverage:
    """What one dataset's sightings say about what is stored."""

    dataset_key: str
    #: Distinct ids the site has shown us, ever.
    seen: int
    #: Of those, how many reached `generic_record`.
    stored: int

    @property
    def missing(self) -> int:
        return self.seen - self.stored

    @property
    def fraction(self) -> float:
        """Stored over seen. 1.0 when every sighting became a record."""
        return 1.0 if not self.seen else self.stored / self.seen

    def __str__(self) -> str:
        if not self.seen:
            return (f"{self.dataset_key}: nothing has been sighted, so coverage "
                    "cannot be stated. That is not the same as complete.")
        return (f"{self.dataset_key}: {self.stored:,} stored of {self.seen:,} "
                f"sighted — {self.missing:,} seen and never fetched "
                f"({100 * self.fraction:.1f}%). Sighted is a FLOOR, not the "
                "population: a contractor no pass has shown us is in neither "
                "number.")


def record_sightings(conn: sqlite3.Connection, dataset_key: str,
                     ids: Iterable[str], *, run_ref: str | None = None) -> int:
    """Note that the site showed us these ids. Returns how many were new.

    UPSERT rather than insert-or-ignore, because `seen_count` is the point: the
    2026-08-17 pass showed 6,503 contractors once, 3,249 twice, 1,021 three
    times and 13 six times, and that frequency distribution is a
    capture-recapture sample of the population. Losing it would leave only the
    set, which cannot estimate what the set is missing.

    The same guard `Sweep.record` learned the hard way: `if one` BEFORE
    `str(one)`, because `str(None)` is the perfectly non-empty string "None" and
    a parser that failed would otherwise contribute a contractor called None to
    every pass -- the same one each time, so a sweep would go dry looking
    convergent.
    """
    clean = {str(one).strip() for one in ids if one and str(one).strip()}
    if not clean:
        return 0
    before = _count(conn, dataset_key)
    conn.executemany(
        "INSERT INTO dataset_sighting (dataset_key, external_id, first_run_ref) "
        "VALUES (?,?,?) "
        "ON CONFLICT(dataset_key, external_id) DO UPDATE SET "
        "  seen_count = seen_count + 1, "
        "  last_seen_at = strftime('%Y-%m-%dT%H:%M:%SZ','now')",
        [(dataset_key, one, run_ref) for one in sorted(clean)])
    conn.commit()
    return _count(conn, dataset_key) - before


def _count(conn: sqlite3.Connection, dataset_key: str) -> int:
    return int(conn.execute(
        "SELECT COUNT(*) FROM dataset_sighting WHERE dataset_key = ?",
        (dataset_key,)).fetchone()[0])


#: EVERY STATE A ROW CAN BE IN, and the vocabulary is CLOSED. His instruction:
#: «عمود يوضح الحالة الجديدة لا تدع المستخدم يستنتج الحالة» — the column says the
#: state; the reader never infers it from three dates and a status.
#:
#: A closed vocabulary is what makes `R-27` safe. The rule is that a row never leaves
#: the screen and its state becomes a column — and a state nobody enumerated is a row
#: displaying something its reader cannot interpret, which is worse than a hidden row
#: because it looks like information.
#:
#: ORDERED BY PRECEDENCE, and the order is the answer to "what should he see first
#: when two are true at once". A row can be both `absent` and `retired`; the retirement
#: is the decision someone took and outranks the observation.
STATE_RETIRED = "retired"            # someone marked the record; a decision, not a sighting
STATE_UNAVAILABLE = "unavailable"    # marked as temporarily not published
STATE_UNSIGHTED = "unsighted"        # stored, and not in the ledger at all
STATE_ABSENT = "absent"              # the last crawl did not show it
STATE_RETURNED = "returned"          # absent in an earlier crawl, and here again
STATE_NEW = "new"                    # first appeared in the last crawl
STATE_UPDATED = "updated"            # seen in the last crawl and its data changed
STATE_CONFIRMED = "confirmed"        # seen in the last crawl, unchanged

#: What the user reads, per state. Kept beside the vocabulary so a state cannot be
#: added without a sentence explaining it.
STATE_MEANING: dict[str, str] = {
    STATE_NEW: "First appeared in the most recent crawl",
    STATE_UPDATED: "Seen in the most recent crawl, and its data changed",
    STATE_CONFIRMED: "Seen in the most recent crawl, unchanged",
    STATE_RETURNED: "Was proved absent in an earlier crawl, and is here again",
    STATE_ABSENT: "The most recent crawl did not show this row",
    STATE_UNSIGHTED: "Stored before the sighting ledger existed, so never sighted",
    STATE_RETIRED: "Marked as gone",
    STATE_UNAVAILABLE: "Marked as not currently published",
}


def stored_ids(conn: sqlite3.Connection, dataset_key: str, *,
               id_field: str = "contractor_id",
               active_only: bool = True) -> dict[str, str]:
    """`external_id -> record_key` for every row this dataset holds. ONE PASS.

    THE COST THIS EXISTS TO REMOVE, measured on the live warehouse 2026-08-21:

        coverage    (correlated json_extract)   49.74 s
        missing_ids (correlated json_extract)   48.81 s
        the same answers, set-based             00.06 s

    ~800x, and it is not a micro-optimisation — the two together exceeded the
    two-minute limit and `--coverage` simply never returned. 14,180 sightings against
    1,172 records is **16.6M** comparisons, because both queries asked
    `json_extract(r.data_json, '$.contractor_id') = s.external_id` inside a
    correlated `EXISTS`, and **no index can serve a json_extract**. Reading each side
    once and intersecting is O(n+m).

    THE ROOT CAUSE IS STRUCTURAL AND THIS ONLY ROUTES AROUND IT. The external id
    lives INSIDE `data_json` and `record_key` is a SHA-256 of the identity values, so
    the warehouse has no indexed column carrying a site's own id. The fix is an
    `external_id` column written at approval time — a migration, recorded in
    `docs/BACKLOG.md` rather than smuggled in behind a performance patch.
    """
    return {external_id: record_key
            for external_id, (record_key, status)
            in _records_with_status(conn, dataset_key, id_field).items()
            if not active_only or status == "active"}


def _records_with_status(conn: sqlite3.Connection, dataset_key: str,
                         id_field: str) -> dict[str, tuple[str, str]]:
    """`external_id -> (record_key, status)`. The one pass `stored_ids` documents.

    KEPT AS ONE QUERY WITH TWO READERS rather than two similar queries, because the
    `json_extract` here is the expensive part — see `stored_ids` for the 800x — and a
    second copy of it is a second chance for the two to drift on which rows they
    count.
    """
    found: dict[str, tuple[str, str]] = {}
    for record_key, external_id, status in conn.execute(
            "SELECT r.record_key, json_extract(r.data_json, '$.' || ?), r.status "
            "  FROM generic_record AS r "
            "  JOIN dataset_definition AS d "
            "    ON d.dataset_definition_id = r.dataset_definition_id "
            " WHERE d.dataset_key = ?", (id_field, dataset_key)):
        if external_id is None:
            continue
        found[str(external_id)] = (record_key, status)
    return found


def sighted_ids(conn: sqlite3.Connection, dataset_key: str) -> tuple[str, ...]:
    """Every id the SITE has shown us, in id order. The counterpart to `stored_ids`.

    THE TWO ARE DIFFERENT NUMBERS AND THE DIFFERENCE MATTERS. Measured on the live
    warehouse 2026-08-21: 17,417 sighted against 15,707 stored, because a row exists
    only once a page has been approved. So a frontier built from `stored_ids` would
    silently omit the 1,710 contractors we have seen and not yet interpreted — which is
    the population a profile crawl most needs to reach.

    ONE INDEXED READ. `dataset_sighting` carries the site's own id in a real column,
    unlike `generic_record` where it lives inside `data_json` and no index can serve a
    `json_extract` — the 800x that `stored_ids` documents.
    """
    return tuple(row[0] for row in conn.execute(
        "SELECT external_id FROM dataset_sighting WHERE dataset_key = ? "
        " ORDER BY external_id", (dataset_key,)))


def missing_ids(conn: sqlite3.Connection, dataset_key: str,
                *, limit: int | None = None) -> tuple[str, ...]:
    """Ids the site showed us that never became a record.

    THIS IS THE LIST THE OWNER COULD NOT BE GIVEN. Ordered by how often the site
    showed it: a contractor seen six times and still unstored is a stronger
    signal than one glimpsed once, because the second may simply have arrived on
    the pass that ended.

    Joined on `generic_record.data_json ->> 'contractor_id'` rather than on a
    column, because the id lives inside the record's JSON body — there is no
    external-id column on generic_record, and inventing one here would be a
    schema change disguised as a query.
    """
    held = stored_ids(conn, dataset_key)
    # THE ORDER IS THE POINT AND STAYS IN SQL, where the index on
    # `(dataset_key, external_id)` and the `seen_count` are. Only the MEMBERSHIP test
    # moved into Python — see `stored_ids` for the 49.74s -> 0.06s that bought.
    rows = conn.execute(
        "SELECT external_id FROM dataset_sighting "
        " WHERE dataset_key = ? "
        " ORDER BY seen_count DESC, CAST(external_id AS INTEGER)",
        (dataset_key,))
    gap = (row[0] for row in rows if row[0] not in held)
    if limit is None:
        return tuple(gap)
    return tuple(itertools.islice(gap, int(limit)))


def coverage(conn: sqlite3.Connection, dataset_key: str) -> Coverage:
    """Stored against sighted, for one dataset."""
    seen = _count(conn, dataset_key)
    held = stored_ids(conn, dataset_key)
    # SIGHTED **AND** HELD, which is not the same as the number of rows: a row whose
    # id no pass ever sighted is stored and not counted here, and that asymmetry is
    # what makes `stored/seen` a coverage figure rather than a row count.
    sighted = {row[0] for row in conn.execute(
        "SELECT external_id FROM dataset_sighting WHERE dataset_key = ?",
        (dataset_key,))}
    return Coverage(dataset_key=dataset_key, seen=seen,
                    stored=len(sighted & set(held)))


@dataclass(frozen=True)
class Departures:
    """Contractors we hold that a later crawl did not show us.

    TWO LISTS, BECAUSE THEY ARE TWO DIFFERENT FACTS and merging them would produce a
    number nobody could act on:

      * `gone` — stored, active, and last sighted BEFORE the window. If the crawl
        covering them was provably complete, they have been delisted.
      * `unsighted` — stored, active, and **not in the ledger at all**. That is a gap
        in the LEDGER, not a contractor leaving: these rows predate the sightings
        table, which arrived with #227.
    """

    dataset_key: str
    not_seen_since: str
    gone: tuple[str, ...] = ()
    unsighted: tuple[str, ...] = ()

    def __str__(self) -> str:
        lines = [
            f"{self.dataset_key}: {len(self.gone):,} stored contractor(s) were not "
            f"sighted on or after {self.not_seen_since}."
        ]
        if self.unsighted:
            lines.append(
                f"  and {len(self.unsighted):,} stored contractor(s) are not in the "
                "sighting ledger at all — those predate it and are NOT departures")
        lines.append(
            "  THIS IS A DEPARTURE ONLY IF THE CRAWL COVERED THEM. A cell that closed "
            "with D=0 proves every row it publishes was seen, so a stored row of that "
            "cell missing from the run has left. Without that proof this list is "
            "'not seen lately', which a partial crawl produces too.")
        return "\n".join(lines)


def departures(conn: sqlite3.Connection, dataset_key: str, *,
               not_seen_since: str, id_field: str = "contractor_id",
               limit: int | None = None) -> Departures:
    """Stored contractors the site stopped showing us — the other half of coverage.

    THE QUESTION THIS ANSWERS, and it is not the one `missing_ids` answers. That one
    asks *"what did the site show us that we never stored"*. This asks *"what did we
    store that the site has stopped showing"* — and until now **nothing asked it at
    all**: no code sets `generic_record.status = 'superseded'`, so a delisted
    contractor keeps `status='active'` with a frozen `last_seen_at` and is
    indistinguishable from one this run did not crawl.

    IT IS TIME-BASED BECAUSE THE LEDGER IS. `dataset_sighting` records
    `first_seen_at`, `last_seen_at` and `seen_count` — there is **no per-run row**, so
    "was this id seen in run R" cannot be asked of the schema. `last_seen_at` against
    the run's start is the honest substitute, and the caller supplies the window.

    AND IT DOES NOT WRITE. Marking a row superseded is a change to the owner's data
    and a decision he has not been asked — whether a delisted contractor is retired,
    or kept active with a stale `last_seen_at` and a flag, is his call. Detection
    first; the write is `OP-26`.

    THE DISTINCTION HE HAD TO CORRECT ME ON: this reaches only contractors we ALREADY
    HOLD. A contractor the site has never shown us is in neither list — that is the
    deficit `D`, and membership 10001274 was that case, not this one.
    """
    # THE EXTERNAL ID IS INSIDE THE JSON, AND `record_key` IS NOT IT. The first draft
    # of this function joined `s.external_id = r.record_key` and was wrong in a way
    # that would have reported EVERY stored row as unsighted: `record_key` is
    # `_digest(_canonical(identity))`, a SHA-256 — `'ff88670d…'` where the contractor
    # id is `'20044482'`. Measured on the live warehouse: they match on **0 of
    # 1,172** rows. The tests passed because the fixture inserts `record_key =
    # contractor_id`, which production never does.
    #
    # TWO PASSES AND A SET, NOT A CORRELATED SUBQUERY. `coverage` and `missing_ids`
    # both join on `json_extract(data_json, '$.contractor_id')`, which no index can
    # serve — so each sighting scans every record: 13,727 x 1,172 is ~16M
    # `json_extract` calls, and `--coverage` exceeded two minutes on the real
    # warehouse. Reading each side once and intersecting in Python is O(n+m): ~15,000
    # operations for the same answer. The structural fix is an indexed external-id
    # column, which is a migration — recorded rather than smuggled in here.
    stored = {}
    for record_key, external_id, status in conn.execute(
            "SELECT r.record_key, json_extract(r.data_json, '$.' || ?), r.status "
            "  FROM generic_record AS r "
            "  JOIN dataset_definition AS d "
            "    ON d.dataset_definition_id = r.dataset_definition_id "
            " WHERE d.dataset_key = ?", (id_field, dataset_key)):
        if status == "active" and external_id is not None:
            stored[str(external_id)] = record_key
    sighted = dict(conn.execute(
        "SELECT external_id, last_seen_at FROM dataset_sighting "
        " WHERE dataset_key = ?", (dataset_key,)))

    gone: list[str] = []
    unsighted: list[str] = []
    for external_id in sorted(stored, key=lambda one: (len(one), one)):
        seen = sighted.get(external_id)
        if seen is None:
            unsighted.append(external_id)
        elif seen < not_seen_since:
            gone.append(external_id)
    if limit is not None:
        gone, unsighted = gone[:limit], unsighted[:limit]
    return Departures(dataset_key=dataset_key, not_seen_since=not_seen_since,
                      gone=tuple(gone), unsighted=tuple(unsighted))


def row_state(*, status: str, first_seen_at: str | None,
              last_seen_at: str | None, newest: str | None,
              changed_at: str | None = None,
              sighted_at: str | None = None,
              last_absent_at: str | None = None) -> str:
    """WHICH of the eight states this row is in. ONE place decides it.

    THE POINT IS THAT NOBODY INFERS. `R-27` puts the state on screen as a column, and
    his instruction was explicit: «لا تدع المستخدم يستنتج الحالة». Three dates and a
    status ARE inferable — that is exactly the problem, because two readers infer
    differently and one of them is wrong. The precedence lives here, once.

    `newest` is the dataset's latest `last_seen_at` — "the last crawl". Everything is
    relative to it, and when it is None nothing has ever been crawled, so the only
    honest answer is what the record itself says.

    PRECEDENCE, and each step is a decision rather than an accident:

      1. A MARKED row first. `retired` / `unavailable` are decisions somebody took,
         and a decision outranks an observation — a row can be both absent and
         retired, and the retirement is the more useful thing to say.
      2. NOT IN THE LEDGER next, because it is not a fact about the site at all: it
         means this row predates `dataset_sighting`, and calling it `absent` would
         invent a departure out of our own history.
      3. NOT SEEN IN THE LAST CRAWL → `absent`.
      4. SEEN, and first seen in that same crawl → `new`. Checked before `returned`
         and `updated` because a row cannot have returned or changed on the crawl that
         introduced it.
      5. SEEN, and proved absent before → `returned`.
      6. SEEN, and a revision was written in that crawl → `updated`. This is only
         meaningful because of `R-20`: an unchanged row now writes no revision, so a
         fresh revision IS the change. Before R-20 every row had one every crawl and
         this state would have been every row.
      7. Otherwise → `confirmed`.
    """
    if status == STATE_RETIRED:
        return STATE_RETIRED
    if status == STATE_UNAVAILABLE:
        return STATE_UNAVAILABLE
    if sighted_at is None:
        return STATE_UNSIGHTED
    if newest is None:
        # Nothing has been crawled, so "the last crawl" does not exist and no
        # comparison against it is honest.
        return STATE_CONFIRMED
    if last_seen_at is None or last_seen_at < newest:
        return STATE_ABSENT
    if first_seen_at is not None and first_seen_at >= newest:
        return STATE_NEW
    if last_absent_at is not None and last_seen_at >= last_absent_at:
        # `>=` AND NOT `>`, because both timestamps are `strftime(...,'now')` at
        # SECOND resolution: a crawl that finishes in the same second as the absence
        # it is answering produces two equal strings, and `>` then reads a returning
        # contractor as merely `confirmed`. It is not a test artefact — it is a race
        # that a fast cell would hit for real.
        #
        # And the ordering carries no weight here anyway: a row still missing from the
        # latest crawl was already caught as `absent` two checks above, so reaching
        # this line means it IS present now and has a recorded absence behind it.
        return STATE_RETURNED
    if changed_at is not None and changed_at >= newest:
        return STATE_UPDATED
    return STATE_CONFIRMED


def record_absences(conn: sqlite3.Connection, dataset_key: str, *,
                    seen: Iterable[str], run_ref: str,
                    id_field: str = "contractor_id") -> int:
    """Write down that these stored rows were NOT seen by a crawl that proved it.

    THE ONE FACT THAT CANNOT BE RECOMPUTED. Absence leaves no trace in
    `dataset_sighting`: a row simply stops being touched, and a `last_seen_at` two
    crawls old looks identical whether the id was missed once and seen again or has
    been gone all along. So `returned` is not derivable after the fact — the absence
    has to be recorded at the moment a crawl proved it. Migration 0006 is that column.

    **ONLY EVER CALLED FROM A PROOF.** `seen` must be the ids of a crawl whose cells
    closed with `D = 0`, because a partial crawl misses contractors for its own
    reasons — a dead page, a rolled cache generation, a cell above the witness
    ceiling. Recording those as absences would retire contractors because the crawler
    had a bad afternoon, which is the failure `R-27` exists to prevent arriving from
    the other side. This function cannot check that for itself; its caller must.

    Returns how many rows were newly marked absent.
    """
    held = set(stored_ids(conn, dataset_key, id_field=id_field))
    missing = sorted(held - {str(one) for one in seen})
    if not missing:
        return 0
    conn.executemany(
        "UPDATE dataset_sighting "
        "   SET last_absent_at = strftime('%Y-%m-%dT%H:%M:%SZ','now'), "
        "       last_absent_run_ref = ? "
        " WHERE dataset_key = ? AND external_id = ?",
        [(run_ref, dataset_key, one) for one in missing])
    conn.commit()
    return len(missing)


@dataclass(frozen=True)
class Marking:
    """What one `mark_unavailable` pass changed, both directions named separately.

    TWO NUMBERS AND NOT A TOTAL, because they are opposite facts and a caller that
    prints `7 changed` has told the reader nothing: seven contractors leaving the
    directory and seven coming back are the same total and different news.
    """

    dataset_key: str
    marked: tuple[str, ...] = ()
    restored: tuple[str, ...] = ()

    def __str__(self) -> str:
        if not self.marked and not self.restored:
            return f"{self.dataset_key}: no status change"
        parts = []
        if self.marked:
            parts.append(f"{len(self.marked):,} marked unavailable")
        if self.restored:
            parts.append(f"{len(self.restored):,} restored to active")
        return f"{self.dataset_key}: " + ", ".join(parts)


def mark_unavailable(conn: sqlite3.Connection, dataset_key: str, *,
                     id_field: str = "contractor_id") -> Marking:
    """Write the status a proven absence earns, and take it back when the row returns.

    `OP-26`, RULED BY HIM ON 2026-08-21: a delisted contractor becomes
    **`unavailable`**, not `retired`. The two were both in the schema's `CHECK` from
    the beginning and **nothing ever set either** — so a delisted contractor kept
    `status='active'` with a frozen `last_seen_at` and was indistinguishable from one
    the last crawl simply had not reached.

    `retired` IS DELIBERATELY UNREACHABLE FROM HERE. `row_state` calls a marked row *"a
    decision somebody took"*, and that is the difference: `unavailable` is what the
    SITE did, so a crawl may write it, while `retired` is what a PERSON decided and no
    crawl should be able to reach it. One vocabulary, two authors.

    That rule is enforced by the two branch conditions naming their own status, **not**
    by a guard at the top of the loop. There was one, and a mutation removed it without
    a single test failing — because `retired` is neither `'active'` nor `'unavailable'`
    and the branches had already excluded it. It is recorded here because deleting an
    untestable guard looks like weakening the code and is the opposite.

    THE PROOF IS `last_absent_at`, AND THAT IS WHY THIS FUNCTION CAN CHECK ITSELF.
    `record_absences` says its caller must guarantee the crawl was complete, because it
    cannot see the proof from inside. This function is downstream of it and therefore
    can: `last_absent_at` is written **only** from a crawl whose cells closed with
    `D = 0`, so a row carrying one has already been proven absent by a crawl that could
    have found it. A row with no `last_absent_at` is never marked, and the reason is
    the failure `R-27` exists to prevent from the other side — a crawler having a bad
    afternoon must not delist contractors.

    THE BOUNDARY IS THE EXACT COMPLEMENT OF `row_state`'S, deliberately. That function
    reads `last_seen_at >= last_absent_at` as `returned`, with a written reason for the
    `>=`: both timestamps come from `strftime(...,'now')` at SECOND resolution, so a
    crawl finishing in the same second as the absence it answers produces two equal
    strings. "Still absent" is therefore `last_seen_at < last_absent_at` and nothing
    else. **If these two ever disagree, a row is marked unavailable and displays
    `returned`, or the reverse** — so they are written as one comparison in two places
    rather than two comparisons that happen to agree today.

    AND THE RESTORE IS NOT OPTIONAL — WITHOUT IT `returned` IS UNREACHABLE. `row_state`
    puts a marked row FIRST in its precedence, above every observation. So a
    contractor marked `unavailable` who reappears would keep displaying `unavailable`
    for as long as the row exists, and the `returned` state that migration 0006 was
    written for would never be seen by anyone. Marking without restoring would not be
    half of this feature; it would be a regression that silently disables another.

    A ROW WITH NO SIGHTING IS NEVER TOUCHED. That is `unsighted` — a gap in **our**
    ledger, from rows predating `dataset_sighting` — and calling it a departure would
    invent one out of our own history.

    Returns a `Marking` naming both directions. Idempotent: a second pass over an
    unchanged warehouse reports nothing, because it compares the status it would write
    against the one already there.
    """
    sighted = {
        str(external_id): (last_seen_at, last_absent_at)
        for external_id, last_seen_at, last_absent_at in conn.execute(
            "SELECT external_id, last_seen_at, last_absent_at "
            "  FROM dataset_sighting WHERE dataset_key = ?", (dataset_key,))}

    marked: list[str] = []
    restored: list[str] = []
    for external_id, (record_key, status) in _records_with_status(
            conn, dataset_key, id_field).items():
        seen = sighted.get(external_id)
        if seen is None:
            continue                      # unsighted: our gap, not a departure
        last_seen_at, last_absent_at = seen
        if last_absent_at is None:
            still_absent = False          # nothing ever proved this row absent
        else:
            # THE COMPLEMENT OF `row_state`'s `returned` test. See the docstring.
            still_absent = str(last_seen_at or "") < str(last_absent_at)
        # BOTH BRANCHES NAME THE STATUS THEY ACT ON, and that is what keeps `retired`
        # out rather than a guard above the loop. There WAS such a guard, and a mutation
        # deleted it with every test still passing: `retired` is neither `'active'` nor
        # `'unavailable'`, so these two conditions had already excluded it and the guard
        # was decoration. A line that reads like protection and cannot fail is worse than
        # no line, because the next reader believes it is what protects the row.
        #
        # So the rule lives where it acts: `unavailable` is what the SITE did and a crawl
        # may write it; `retired` is what a PERSON decided and no crawl may reach it, in
        # either direction.
        if still_absent and status == "active":
            marked.append(record_key)
        elif not still_absent and status == STATE_UNAVAILABLE:
            restored.append(record_key)

    for new_status, keys in ((STATE_UNAVAILABLE, marked), ("active", restored)):
        if keys:
            conn.executemany(
                "UPDATE generic_record SET status = ? "
                " WHERE record_key = ? AND dataset_definition_id = ("
                "   SELECT dataset_definition_id FROM dataset_definition "
                "    WHERE dataset_key = ?)",
                [(new_status, key, dataset_key) for key in keys])
    if marked or restored:
        conn.commit()
    return Marking(dataset_key=dataset_key,
                   marked=tuple(sorted(marked)),
                   restored=tuple(sorted(restored)))


def sighting_frequencies(conn: sqlite3.Connection,
                         dataset_key: str) -> dict[int, int]:
    """How many ids were seen once, twice, three times… — the sample itself.

    Kept as a query rather than a computed estimate on purpose. Turning this into
    a population number is a statistical choice (Chao1, Lincoln-Petersen, and
    they disagree), and this module's job is to hand over the observations
    without picking a school.
    """
    return {int(times): int(count) for times, count in conn.execute(
        "SELECT seen_count, COUNT(*) FROM dataset_sighting "
        " WHERE dataset_key = ? GROUP BY seen_count ORDER BY seen_count",
        (dataset_key,))}
