"""Conditional-request validators, kept between runs so a re-crawl is cheap.

WHY THIS EXISTS. He asked whether a new user waits the same hours every time —
«هل سينتظر كل هذا الوقت ايضا ؟ ام هناك استراتجية افضل؟» — and the answer should have
been no, because `HttpFetcher` has done conditional requests all along: it keeps each
response's `ETag` and `Last-Modified`, sends `If-None-Match` next time, handles the
304, and counts it in `not_modified_count`.

IT KEPT THEM IN A DICT THAT DIES WITH THE PROCESS. Measured 2026-08-21:
`remember_validators` — *"Load validators kept from a previous crawl"* — and
`validators()` — *"The validators to keep for the next crawl"* — had **zero callers
anywhere**. Nothing kept them, so every re-crawl asked for full bodies for pages that
had not changed, and that docstring had never once been true across two runs.

That is this project's founding failure in miniature, and `CLAUDE.md` names it:
`crawl_to_snapshots` was committed with no caller. **A capability with no caller is a
claim.** This module is the caller.

WHAT IT DELIBERATELY DOES NOT DO. It does not decide policy. Whether a crawl replays
validators at all is the crawl's business — a run that means to re-read everything
should not have to delete rows to do it — so loading is an explicit call and not a
side effect of opening a connection.
"""
from __future__ import annotations

import sqlite3

#: The two headers a conditional request is built from. Kept as a tuple rather than
#: assumed, because `HttpFetcher._store_validators` keeps exactly these and the two
#: sides must not drift.
HEADERS = ("ETag", "Last-Modified")

_COLUMN = {"ETag": "etag", "Last-Modified": "last_modified"}


def load(conn: sqlite3.Connection, urls: list[str] | None = None
         ) -> dict[str, dict[str, str]]:
    """Validators in the shape `HttpFetcher.remember_validators` expects.

    `urls` NARROWS IT ON PURPOSE. A warehouse accumulates a row per URL ever
    visited, and a crawl of one cell has no use for another cell's validators —
    loading all of them would put the whole history in memory to answer a few
    hundred lookups. Omit it and everything comes back, which is right for a full
    crawl.
    """
    if urls is not None and not urls:
        return {}
    sql = "SELECT url, etag, last_modified FROM fetch_validator"
    params: tuple = ()
    if urls is not None:
        marks = ",".join("?" * len(urls))
        sql += f" WHERE url IN ({marks})"
        params = tuple(urls)
    out: dict[str, dict[str, str]] = {}
    for url, etag, modified in conn.execute(sql, params):
        kept = {}
        if etag:
            kept["ETag"] = str(etag)
        if modified:
            kept["Last-Modified"] = str(modified)
        if kept:
            out[str(url)] = kept
    return out


def save(conn: sqlite3.Connection, state: dict[str, dict[str, str]]) -> int:
    """Keep what this run learned. Returns how many URLs were written.

    UPSERT, BECAUSE A VALIDATOR IS THE LATEST FACT ABOUT A URL and not a history.
    Appending would grow a row per visit and then need "the newest one" on every
    lookup — the shape migration 0008 explains it chose against.

    A PAGE WITH NEITHER HEADER IS SKIPPED RATHER THAN STORED. The table's CHECK
    refuses such a row, so "has a row" and "has a validator" stay the same question;
    a site that sends no validators simply gets no rows, and the fetcher already
    treats a missing one as "ask for the whole thing".
    """
    written = 0
    for url, kept in (state or {}).items():
        etag = kept.get("ETag")
        modified = kept.get("Last-Modified")
        if not etag and not modified:
            continue
        conn.execute(
            "INSERT INTO fetch_validator (url, etag, last_modified, seen_at) "
            "VALUES (?,?,?, strftime('%Y-%m-%dT%H:%M:%SZ','now')) "
            "ON CONFLICT(url) DO UPDATE SET etag = excluded.etag, "
            "  last_modified = excluded.last_modified, seen_at = excluded.seen_at",
            (url, etag, modified))
        written += 1
    conn.commit()
    return written


def forget_older_than(conn: sqlite3.Connection, cutoff: str) -> int:
    """Drop validators not seen since `cutoff`. Returns how many went.

    A VALIDATOR IS NEVER WRONG, ONLY USELESS, which is why this is pruning and not
    correctness: a stale one makes a conditional request that simply misses and the
    server sends the body. So nothing here is urgent, and nothing calls it on a
    schedule yet — it exists so that "this warehouse remembers every URL it ever
    visited" is a fact someone can act on rather than discover.
    """
    cursor = conn.execute("DELETE FROM fetch_validator WHERE seen_at < ?", (cutoff,))
    conn.commit()
    return int(cursor.rowcount or 0)
