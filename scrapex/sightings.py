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
    sql = (
        "SELECT s.external_id FROM dataset_sighting AS s "
        "WHERE s.dataset_key = ? "
        "  AND NOT EXISTS ("
        "    SELECT 1 FROM generic_record AS r "
        "     WHERE r.status = 'active' "
        "       AND json_extract(r.data_json, '$.contractor_id') = s.external_id) "
        "ORDER BY s.seen_count DESC, CAST(s.external_id AS INTEGER)")
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    return tuple(row[0] for row in conn.execute(sql, (dataset_key,)))


def coverage(conn: sqlite3.Connection, dataset_key: str) -> Coverage:
    """Stored against sighted, for one dataset."""
    seen = _count(conn, dataset_key)
    stored = int(conn.execute(
        "SELECT COUNT(*) FROM dataset_sighting AS s "
        " WHERE s.dataset_key = ? "
        "   AND EXISTS ("
        "     SELECT 1 FROM generic_record AS r "
        "      WHERE r.status = 'active' "
        "        AND json_extract(r.data_json, '$.contractor_id') = s.external_id)",
        (dataset_key,)).fetchone()[0])
    return Coverage(dataset_key=dataset_key, seen=seen, stored=stored)


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
