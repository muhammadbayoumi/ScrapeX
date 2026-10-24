"""The World Bank's procurement notices, collected area by area into the tender warehouse.

Studied live in `#1647`; every constant below is a measurement from that study, named
beside it by its request number there. One notice becomes one release through
`scrapex/sites/worldbank.py`, which reads and asserts the notice; this module fetches,
pages, and keeps what it read through `scrapex/tenderstore.py`. It holds no job and no
route: part 3b-2 runs it, and reports what it says.

AREA BY AREA, BECAUSE THE BANK PAGES NO FURTHER THAN 100,000 (#1647 request 39). One
facet request counts the notices in each of its 184 countries and regions (request 12);
each area is then read in pages of 1,000 (requests 13, 14), largest first. The figure
that request count makes, 537 for the world, is the one #1701's question asks him about.

WHAT A FAILURE DOES IS HIS RULING (#1701 Q1, option (a), 2026-10-17):
  * a page that still fails after the fetcher's tries leaves its area unread, and the
    crawl goes on with the next area;
  * a notice that cannot be kept is counted in Errors, with its id, and the rest of its
    page is kept;
  * a page none of whose notices can be kept stops the crawl as failed, because that is
    the Bank changing shape.
A stop that is not a page's (the owner's Pause or Cancel, a robots.txt refusal, a site
that keeps refusing) arrives as `CrawlBlocked` and is never taken for a failed page.

KEPT PAGE BY PAGE (#1733 item 5): one transaction a page, so the WAL holds one page of
1,000 notices, not an area of up to 47,395. Each notice inside it is undone to a
savepoint of its own when it cannot be kept (#1733 item 3): `store_release` writes the
release before every refusal that can follow it. A page that cannot be committed is undone
whole, and what it did reaches the tally and the log only once it is committed.
"""
from __future__ import annotations

import math
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from itertools import pairwise
from typing import Any

import httpx

from scrapex import tenderstore
from scrapex.connectors.base import CrawlBlocked
from scrapex.normalize import parse_instant
from scrapex.sites import worldbank as wb

#: The notices API (#1647 requests 10, 12-14).
API = "https://search.worldbank.org/api/v2/procnotices"
#: The facet that names each country and region, and filters a page to one (request 12).
AREA_FACET = "project_ctry_name_exact"
#: A page: `rows=1000` holds, and `fl=*` widens a notice to every field (requests 13, 14).
PAGE_ROWS = 1_000
#: The deepest offset the Bank pages to: "`$skip` must be between 0 and 100,000" (39).
OFFSET_LIMIT = 100_000

#: `(level, message)`: where the collector's words go. Part 3b-2's job writes them to its
#: log, in these words.
Log = Callable[[str, str], None]


class PageShapeError(ValueError):
    """A response that is not the envelope #1647 recorded: `rows`, `os`, `page`, `total`,
    `procnotices`, and for a count `facets`. The Bank changed what it answers."""


class ShapeChanged(RuntimeError):
    """A page none of whose notices could be kept: the Bank changed the notice's shape.
    It stops the crawl as failed (his ruling, #1701 Q1 (a))."""


@dataclass(frozen=True)
class Area:
    """One of the Bank's countries and regions, and how many notices it counted."""

    name: str
    count: int

    @property
    def pages(self) -> int:
        return math.ceil(self.count / PAGE_ROWS)


@dataclass(frozen=True)
class Plan:
    """What one count found: every area, largest first, and the notices in all."""

    areas: tuple[Area, ...]
    total: int

    @property
    def requests(self) -> int:
        """The count itself, then every page of every area: 537 for the world."""
        return 1 + sum(area.pages for area in self.areas)


@dataclass
class Tally:
    """What a run did, in the counters part 3b-2's job reports."""

    requests: int = 0
    notices: int = 0
    releases_new: int = 0
    releases_unchanged: int = 0
    errors: int = 0


@dataclass(frozen=True)
class AreaRead:
    """How one area's read ended: whole, or unread with the reason."""

    complete: bool
    pages_read: int
    reason: str | None = None


@dataclass(frozen=True)
class ChangesRead:
    """How one pass over what changed ended: complete when it reached a notice older than
    `since` or the end of what the Bank lists, else cut short with the reason. Only a
    complete pass may move the caller's `since` on (`read_changes`)."""

    complete: bool
    pages_read: int
    reason: str | None = None


def _counted(n: int, word: str) -> str:
    return f"{n:,} {word}{'' if n == 1 else 's'}"


def _envelope(response: httpx.Response, offset: int) -> dict[str, Any]:
    """The page as #1647 recorded it, or `PageShapeError`."""
    try:
        body = response.json()
    except ValueError as exc:
        raise PageShapeError(f"{response.url}: not JSON ({exc})") from None
    if not isinstance(body, dict):
        raise PageShapeError(f"{response.url}: a {type(body).__name__}, not an object")
    total = body.get("total")
    if not isinstance(total, str) or not total.isdigit():
        raise PageShapeError(f"{response.url}: total {total!r} is not a count")
    if body.get("os") != str(offset):
        raise PageShapeError(f"{response.url}: answered offset {body.get('os')!r} for {offset}")
    rows = body.get("procnotices")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise PageShapeError(f"{response.url}: procnotices is not a list of notices")
    return body


def count_areas(fetcher) -> Plan:
    """One request: every area and its count, from the area facet (#1647 request 12)."""
    response = fetcher.get(API, params={"format": "json", "rows": "0", "fct": AREA_FACET})
    body = _envelope(response, 0)
    values = (body.get("facets") or {}).get(AREA_FACET)
    if not isinstance(values, dict) or not values:
        raise PageShapeError(f"{response.url}: no {AREA_FACET} facet")
    areas = []
    for value in values.values():
        name, count = (value or {}).get("name"), (value or {}).get("count")
        if not isinstance(name, str) or not name.strip():
            raise PageShapeError(f"{response.url}: an area without a name: {value!r}")
        if not isinstance(count, int) or count < 0:
            raise PageShapeError(f"{response.url}: {name!r} counts {count!r}")
        areas.append(Area(name=name, count=count))
    total = int(body["total"])
    if sum(area.count for area in areas) != total:
        # The 184 counts add up to the total (#1647 §4); when they do not, an area is
        # missing from the list, and a crawl of the list would miss it without a word.
        raise PageShapeError(f"{response.url}: the areas count "
                             f"{sum(a.count for a in areas):,} of {total:,} notices")
    # LARGEST FIRST, so a first crawl that stops has read as many notices as it could.
    return Plan(areas=tuple(sorted(areas, key=lambda a: (-a.count, a.name))), total=total)


def count_line(plan: Plan) -> str:
    """The line a run logs when it has counted, in the words #1701's contract gives."""
    return (f"counted {plan.total:,} notices in {len(plan.areas)} areas: "
            f"{plan.requests:,} requests")


def newest_held(conn: sqlite3.Connection, source_site_id: int) -> str | None:
    """The latest change stamp of any release the source holds: where a pass over what
    changed stops (#1647 B6: the Bank has no date filter, only a sort)."""
    row = conn.execute(
        "SELECT max(r.source_modified_at) FROM tender_releases r "
        "JOIN tender_processes p ON p.id = r.tender_process_id WHERE p.source_site_id = ?",
        (source_site_id,)).fetchone()
    return row[0] if row else None


def _instant(stamp: Any) -> datetime | None:
    """A change stamp read through `normalize`, not as a string, or None when it does not
    read: absent, blank, or in another shape. A notice whose stamp does not read is never
    taken for older: it is kept, and the converter refuses it by name, so a change in the
    stamp's shape cannot end a pass in silence."""
    if not isinstance(stamp, str):
        return None
    try:
        return parse_instant(stamp)
    except ValueError:
        return None


def _not_its_share(where: str, rows: list[dict], due: int) -> str | None:
    """Why a page is not the page asked for, or None. Under the total it answers, a page
    holds `min(PAGE_ROWS, total - offset)` notices; any other number means notices went
    missing or came twice, and a page kept anyway would mark its read whole."""
    if len(rows) == due:
        return None
    return f"{where}: the Bank answered {len(rows):,} notices where {due:,} were due"


def _get(fetcher, params: dict[str, str], where: str) -> tuple[httpx.Response | None, str]:
    """One page, or why it failed after the fetcher's own tries. A stop is re-raised."""
    try:
        return fetcher.get(API, params=params), ""
    except CrawlBlocked:
        raise
    except httpx.HTTPStatusError as exc:
        return None, f"{where}: HTTP {exc.response.status_code} after its tries"
    except httpx.TransportError as exc:
        return None, f"{where}: {type(exc).__name__} after its tries"


def _keep(conn: sqlite3.Connection, response: httpx.Response, notices: list[dict], *,
          source_site_id: int, crawl_job_id: int | None, tally: Tally, log: Log,
          where: str) -> None:
    """One page: its response as evidence, then each notice under a savepoint of its own,
    committed together. Raises `ShapeChanged` when not one notice could be kept.

    WHAT IT DID IS REPORTED ONCE IT IS COMMITTED. An undone page is read again once the
    lock is free, and reports then; and part 3b-2's job writes its log through the
    warehouse, so a line written inside the page would commit half of it."""
    # BEFORE THE LOCK (#1733): nothing is written yet, so no transaction holds it.
    packed = tenderstore.pack(response.content)
    new = unchanged = 0
    refused: list[tuple[Any, str]] = []
    try:
        response_id = tenderstore.store_response(
            conn, target_uri=str(response.url), status_code=response.status_code,
            content_type=response.headers.get("content-type", ""),
            headers=dict(response.headers), body=packed, crawl_job_id=crawl_job_id)
        for notice in notices:
            # INSIDE THE PAGE'S OPEN TRANSACTION, so in the sqlite3 module's legacy mode its
            # RELEASE commits nothing on its own (#1733 item 3).
            conn.execute("SAVEPOINT notice")
            try:
                stored = tenderstore.store_release(
                    conn, source_site_id=source_site_id,
                    release=wb.release_from_notice(notice), fetched_response_id=response_id)
            except sqlite3.OperationalError:
                # NOT A NOTICE'S FAULT: a lock another app holds, or the disk. Counted as a
                # refused notice it would skip notices in silence; the page is undone below
                # (`CLAUDE.md`: wait for the lock, never route around it).
                raise
            except Exception as exc:  # any shape, recorded with its id (#1733 item 4)
                conn.execute("ROLLBACK TO notice")
                conn.execute("RELEASE notice")
                reason = (str(exc) if isinstance(exc, wb.NoticeShapeError)
                          else f"{type(exc).__name__}: {exc}")
                refused.append((notice.get("id"), reason))
                continue
            conn.execute("RELEASE notice")
            if stored.new:
                new += 1
            else:
                unchanged += 1
        # The evidence of a page that changed shape is kept: it is what shows how it changed.
        conn.commit()
    except BaseException:
        # THE PAGE IS UNDONE WHOLE, whatever stopped it: a lock another app holds at its
        # first write or at the commit, the disk, an interrupt. Left open, the transaction
        # would keep the write lock, and the next read would refuse to start inside it.
        if conn.in_transaction:
            conn.rollback()
        raise
    tally.notices += len(notices)
    tally.releases_new += new
    tally.releases_unchanged += unchanged
    tally.errors += len(refused)
    for notice_id, reason in refused:
        log("error", f"{notice_id!r} not kept: {reason}")
    if notices and len(refused) == len(notices):
        raise ShapeChanged(f"Stopped because the Bank's notices changed shape at {where}: "
                           f"none of {_counted(len(notices), 'notice')} could be read "
                           f"({refused[0][1]})")


def read_area(conn: sqlite3.Connection, fetcher, *, source_site_id: int, area: Area,
              tally: Tally, log: Log, first_page: int = 0, crawl_job_id: int | None = None,
              on_page: Callable[[str, int], None] | None = None) -> AreaRead:
    """Read one area page by page, from `first_page`, keeping each page as it arrives.

    `on_page(area, page)` is called once a page is committed: it is the point a paused
    run goes on from (part 3b-2's checkpoint). An area left unread returns its reason,
    which is also logged; a stop raises."""
    if conn.in_transaction:
        raise ValueError("read_area commits page by page; call it outside a transaction")
    if area.count > OFFSET_LIMIT:
        reason = (f"{area.name}: {area.count:,} notices, past the {OFFSET_LIMIT:,} the Bank "
                  "pages to; it is not read")
        log("warning", reason)
        return AreaRead(complete=False, pages_read=0, reason=reason)
    read = notices = 0
    for page in range(first_page, area.pages):
        offset = page * PAGE_ROWS
        where = f"{area.name}, page {page + 1}"
        response, failed = _get(fetcher, {
            "format": "json", "rows": str(PAGE_ROWS), "os": str(offset), "fl": "*",
            # A STABLE ORDER, so the pages of one area neither repeat nor skip a notice.
            "srt": "id", "order": "asc", AREA_FACET: area.name}, where)
        if response is None:
            log("warning", failed)
            return AreaRead(complete=False, pages_read=read, reason=failed)
        tally.requests += 1
        body = _envelope(response, offset)
        if int(body["total"]) != area.count:
            # THE FILTER IS THE AREA'S NAME, and some names hold commas ("Mid East,North
            # Africa, Afghan, Pakistan"). A total that is not the count read a moment ago
            # means this is not the area counted, or the index moved under the run; either
            # way nothing of it is kept, and an update reads it again.
            reason = (f"the Bank answered {int(body['total']):,} notices for {area.name}, "
                      f"and counted {area.count:,}")
            log("warning", reason)
            return AreaRead(complete=False, pages_read=read, reason=reason)
        rows = body["procnotices"]
        short = _not_its_share(where, rows, min(PAGE_ROWS, area.count - offset))
        if short:
            log("warning", short)
            return AreaRead(complete=False, pages_read=read, reason=short)
        _keep(conn, response, rows, source_site_id=source_site_id,
              crawl_job_id=crawl_job_id, tally=tally, log=log, where=where)
        read += 1
        notices += len(rows)
        if on_page is not None:
            on_page(area.name, page)
    # What THIS call read: an area resumed partway counts its own pages only.
    log("info", f"{area.name}: {_counted(notices, 'notice')} in {_counted(read, 'request')}")
    return AreaRead(complete=True, pages_read=read)


def read_changes(conn: sqlite3.Connection, fetcher, *, source_site_id: int, since: str,
                 tally: Tally, log: Log, crawl_job_id: int | None = None) -> ChangesRead:
    """Read what changed since `since`, newest change first, keeping each page as it
    arrives.

    The Bank has no date filter; `srt=api_modified_date&order=desc` sorts (#1647 B6,
    request 20), so a pass reads until a notice older than `since`, or the end of what the
    Bank lists. A notice stamped exactly `since` is read: the stamp is to the second, and
    a second can hold more than one change.

    THE CALLER MOVES `since` ON ONLY AFTER A COMPLETE PASS. One cut short (a page that
    failed after its tries, a page that is not its share, a list that shrank under it, the
    Bank's offset limit) returns `complete=False` with the reason, which is also logged;
    one that raised returns nothing. Either way the notices behind its last page are newer
    than `newest_held`, which already counts the pages it kept, so `since` stays where it
    was, and the next pass reads them."""
    if conn.in_transaction:
        raise ValueError("read_changes commits page by page; call it outside a transaction")
    since_at = parse_instant(since)
    pages = notices = 0
    offset = 0
    listed = None   # the total the page before answered
    reason = None
    while True:
        if offset >= OFFSET_LIMIT:
            reason = (f"{OFFSET_LIMIT:,} notices or more changed since {since}, and the Bank "
                      "pages no further")
            break
        where = f"changes, page {offset // PAGE_ROWS + 1}"
        response, failed = _get(fetcher, {
            "format": "json", "rows": str(PAGE_ROWS), "os": str(offset), "fl": "*",
            "srt": "api_modified_date", "order": "desc"}, where)
        if response is None:
            reason = failed
            break
        tally.requests += 1
        body = _envelope(response, offset)
        rows, total = body["procnotices"], int(body["total"])
        if listed is not None and total < listed:
            # A NOTICE LEFT THE LIST during the pass: every row after it moved up one, so the
            # first of this page slid onto the page before, already read. Taken as complete,
            # the pass would move `since` past it for good. A list that grows only moves
            # rows down, which repeats a row and loses none.
            reason = (f"{where}: the Bank lists {total:,} notices, {listed - total:,} fewer "
                      "than a page before, so one may have passed this read unseen")
            break
        listed = total
        reason = _not_its_share(where, rows, min(PAGE_ROWS, total - offset))
        if reason:
            break
        stamps = [_instant(row.get("api_modified_date")) for row in rows]
        # NEWEST FIRST, ASSERTED: the pass stops at the first notice older than `since`, so
        # it is right only in the order it asked for, and this API has ignored a parameter
        # without a word (`strdate`, #1647 request 20). Asserted within a page, which one
        # response answers at once; not across pages, because a change made during the
        # pass puts its notice first and moves every row down, so a page can open with
        # the rows the page before closed with. Equal stamps are common: the index updates
        # once a day, all at one minute (request 20).
        readable = [(row, at) for row, at in zip(rows, stamps, strict=True) if at is not None]
        for (before, before_at), (row, at) in pairwise(readable):
            if at > before_at:
                raise PageShapeError(
                    f"{where}: {row.get('id')!r} changed {row['api_modified_date']} follows "
                    f"{before.get('id')!r} changed {before['api_modified_date']}: the "
                    "Bank's answer is not newest first")
        newer = [row for row, at in zip(rows, stamps, strict=True)
                 if at is None or at >= since_at]
        if newer:
            _keep(conn, response, newer, source_site_id=source_site_id,
                  crawl_job_id=crawl_job_id, tally=tally, log=log, where=where)
        pages += 1
        notices += len(newer)
        if len(newer) < len(rows) or offset + len(rows) >= total:
            break
        offset += PAGE_ROWS
    if reason:
        log("warning", reason)
    log("info", f"changes: {_counted(notices, 'notice')} in {_counted(pages, 'request')}")
    return ChangesRead(complete=reason is None, pages_read=pages, reason=reason)
