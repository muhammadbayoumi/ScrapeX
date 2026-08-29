"""Opening and closing a crawl run, for any kind of source.

WHY THIS MODULE EXISTS AND WHY IT IS NOT A SECOND RUN TABLE. `R-52` chose a new table for
generic crawls, on a measurement it recorded honestly: *"`crawl_run` is the price path alone
— its `source_id` points at a price source, nothing for a dataset."* That was true on
2026-08-24. `R-62`'s registry merge (`0014`) put `muqawil_org` into `source_site`, so
`crawl_run.source_id` now resolves for a dataset source like any other, and he ruled on
2026-08-29: **one run table for everything.** It is `R-72`'s reasoning one layer down — two
concepts for one thing is what the duplicated migration stream cost all day.

WHAT A GENERIC RUN LEAVES EMPTY, said out loud rather than discovered later.
`products_discovered` and `variants_discovered` mean nothing for a directory and stay 0;
`rows_seen` carries the number that does. `extractor_version` names the crawl kind, which is
the only place a reader can tell a listing sweep from a profile sweep after the fact.

THE PRICE PATH STILL HAS ITS OWN COPY of this lifecycle, inline in `ingest.py` around the
`_insert(conn, "crawl_run", …)` call. It is not routed through here yet — that is a change to
working code with no defect behind it, and it is recorded as `OP-99` rather than done
quietly on the way past.
"""
from __future__ import annotations

import sqlite3

from .vocab import RunStatus


class UnknownSource(LookupError):
    """The source key names nothing in the registry, so no run can belong to it."""


def open_run(conn: sqlite3.Connection, source_key: str, *,
             kind: str, job_id: int | None = None) -> int:
    """Start a run for `source_key` and return its id.

    THE SOURCE IS RESOLVED HERE AND NOT PASSED IN, because a caller holding a `source_id`
    has already had to know which registry to ask — and since `0014` there is only one, so
    the lookup is a single statement and the caller has one less thing to be wrong about.

    IT DOES NOT COMMIT. Every writer in this codebase leaves the transaction to its caller
    (`extract/service.py` says so explicitly), and a run that committed itself would survive
    a crawl that then rolled back — a row saying `running` for ever with nothing behind it.
    """
    row = conn.execute(
        "SELECT source_id FROM source_site WHERE source_key = ? AND valid_to IS NULL",
        (source_key,)).fetchone()
    if row is None:
        raise UnknownSource(
            f"no active source is registered as {source_key!r}, so a run cannot be opened "
            "for it; register the source first")
    return int(conn.execute(
        "INSERT INTO crawl_run (source_id, status, extractor_version, job_id) "
        "VALUES (?,?,?,?)",
        (int(row[0]), RunStatus.RUNNING.value, kind, job_id)).lastrowid)


def close_run(conn: sqlite3.Connection, run_id: int, *, status: RunStatus,
              rows_seen: int = 0, requests: int = 0, errors: int = 0) -> None:
    """Finish a run. Anything the caller does not know stays at its default of 0.

    `finished_at` is written HERE rather than by the caller, so "when did this run end" can
    never disagree with "is this run still running" — the two are set in one statement.
    """
    conn.execute(
        "UPDATE crawl_run SET finished_at = strftime('%Y-%m-%dT%H:%M:%SZ','now'), "
        "       status = ?, rows_seen = ?, requests_count = ?, errors_count = ? "
        " WHERE run_id = ?",
        (status.value, int(rows_seen), int(requests), int(errors), int(run_id)))


def started_at_of(conn: sqlite3.Connection, run_id: int | None) -> str | None:
    """When a run began. `new` and `updated` are asked against this rather than against
    a row's own date, so a revision written any time during a nine-hour sweep belongs to
    that sweep -- which is precisely what one timestamp could not express."""
    if run_id is None:
        return None
    row = conn.execute("SELECT started_at FROM crawl_run WHERE run_id = ?",
                       (int(run_id),)).fetchone()
    return None if row is None else row[0]


def latest_run_for(conn: sqlite3.Connection, dataset_key: str) -> int | None:
    """The newest run that actually wrote a page this dataset's rows came from.

    NOT `MAX(run_id)` FOR THE SOURCE, and the difference is the whole point. A source can
    have runs that wrote nothing this dataset can see — a listing sweep leaves no profile
    page — and comparing a profile row against a listing run would call every profile
    `absent` the moment a listing crawl finished. So the question is asked THROUGH the rows:
    the latest run among the snapshots this dataset's records actually point at.

    None when no record of this dataset names a run, which is every dataset until a crawl
    has run since `0016`. His ruling for that state is `unsighted`.
    """
    row = conn.execute(
        "SELECT MAX(s.run_id) "
        "  FROM generic_record AS r "
        "  JOIN dataset_definition AS d "
        "    ON d.dataset_definition_id = r.dataset_definition_id "
        "  JOIN generic_page_snapshot AS s ON s.page_snapshot_id = r.source_snapshot_id "
        " WHERE d.dataset_key = ? AND d.valid_to IS NULL",
        (dataset_key,)).fetchone()
    return None if row is None or row[0] is None else int(row[0])
