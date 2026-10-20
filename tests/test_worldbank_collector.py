"""The World Bank notice collector (milestone 51, part 3b-1), on the real migration stream.

Nothing here reaches the network. `Bank` answers the collector's requests from the
recorded responses of #1647: the area facet of request 12 (`fixtures/worldbank/
facets.json`) and the six real notices (`fixtures/worldbank/notices.json`), wrapped in
the envelope that response shows (`rows`, `os`, `page`, `total`, `procnotices`).

His ruling on #1701 Q1, option (a), is what a failure does:
  * a page that fails after its tries leaves its area unread, and the crawl goes on;
  * a notice the converter refuses is counted in Errors with its id;
  * a page whose every notice is refused stops the crawl as failed: the Bank changed shape.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import sqlite3
from pathlib import Path

import httpx
import pytest
import zstandard

from scrapex import tenderstore
from scrapex.connectors.base import CrawlBlocked, CrawlInterrupted, RobotsDisallowed
from scrapex.databases.domain import EngineDatabase
from scrapex.sites import worldbank as wb
from scrapex.sites import worldbank_collect as wc

FIXTURES = Path(__file__).parent / "fixtures" / "worldbank"
FACETS = json.loads((FIXTURES / "facets.json").read_text(encoding="utf-8"))["response"]
NOTICES = json.loads((FIXTURES / "notices.json").read_text(encoding="utf-8"))["notices"]
EGYPT = "Egypt, Arab Republic of"


def notices(count: int, *, start: int = 0) -> list[dict]:
    """`count` distinct notices made from the real six: each its own id and process."""
    made = []
    for i in range(start, start + count):
        notice = copy.deepcopy(NOTICES[i % len(NOTICES)])
        notice["id"] = f"OP{90_000_000 + i:08d}"
        notice["bid_reference_no"] = f"REF-{i}"
        made.append(notice)
    return made


def facet(areas: dict[str, list[dict]]) -> dict:
    """An area facet in the shape request 12 answered."""
    values = {str(i): {"count": len(rows), "name": name, "label": name}
              for i, (name, rows) in enumerate(areas.items())}
    total = sum(len(rows) for rows in areas.values())
    return {"rows": 0, "os": "0", "page": "0", "total": str(total), "procnotices": [],
            "facets": {wc.AREA_FACET: values}}


class Bank:
    """Answers the collector as search.worldbank.org would, from what #1647 recorded."""

    def __init__(self, areas: dict[str, list[dict]] | None = None, *, facets=None,
                 fail=(), raise_at=None, changed=(), totals=None):
        self.areas = areas or {}
        self.facets = facets if facets is not None else facet(self.areas)
        self.fail = dict(fail)            # (area, offset) -> HTTP status after its tries
        self.raise_at = raise_at or {}    # (area, offset) -> exception to raise instead
        self.changed = list(changed)      # notices, newest change first
        self.totals = totals or {}        # area -> the total the Bank answers instead
        self.calls: list[dict] = []
        self.requests_count = 0

    def get(self, url, params=None, **_):
        self.requests_count += 1
        params = dict(params or {})
        self.calls.append(params)
        request = httpx.Request("GET", url, params=params)
        if "fct" in params:
            return httpx.Response(200, json=self.facets, request=request)
        offset = int(params["os"])
        if params.get("srt") == "api_modified_date":
            rows = self.changed[offset:offset + wc.PAGE_ROWS]
            total = len(self.changed)
        else:
            area = params[wc.AREA_FACET]
            if (area, offset) in self.raise_at:
                raise self.raise_at[(area, offset)]
            if (area, offset) in self.fail:
                status = self.fail[(area, offset)]
                raise httpx.HTTPStatusError(f"HTTP {status}", request=request,
                                            response=httpx.Response(status, request=request))
            rows = self.areas[area][offset:offset + wc.PAGE_ROWS]
            total = self.totals.get(area, len(self.areas[area]))
        return httpx.Response(200, request=request, json={
            "rows": wc.PAGE_ROWS, "os": str(offset), "page": str(offset // wc.PAGE_ROWS + 1),
            "total": str(total), "procnotices": rows})


class Log(list):
    def __call__(self, level: str, message: str) -> None:
        self.append((level, message))

    def says(self, text: str) -> bool:
        return any(text in message for _, message in self)


@pytest.fixture()
def conn(tmp_path):
    db = EngineDatabase(tmp_path / "scrapex-engine.db")
    db.initialize()
    connection = db.connect()
    connection.execute("INSERT INTO source_site (source_key, source_name) VALUES (?, ?)",
                       ("worldbank_org", "World Bank procurement notices"))
    connection.commit()
    yield connection
    connection.close()


def site(conn) -> int:
    return conn.execute("SELECT source_id FROM source_site WHERE source_key = 'worldbank_org'"
                        ).fetchone()[0]


def count(conn, table: str) -> int:
    return conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]


def read(conn, bank, area_name, **kw):
    log, tally, pages = kw.pop("log", Log()), kw.pop("tally", wc.Tally()), []
    plan = wc.count_areas(bank)
    area = next(a for a in plan.areas if a.name == area_name)
    result = wc.read_area(conn, bank, source_site_id=site(conn), area=area, tally=tally,
                          log=log, on_page=lambda name, page: pages.append((name, page)), **kw)
    return result, tally, log, pages


# ---- counting: one request, the area facet, its shape asserted ----------------------------

def test_counting_reads_the_banks_184_areas_in_one_request():
    bank = Bank(facets=FACETS)
    plan = wc.count_areas(bank)
    assert bank.requests_count == 1
    assert bank.calls[0]["fct"] == wc.AREA_FACET and bank.calls[0]["rows"] == "0"
    assert len(plan.areas) == 184
    assert plan.total == 422_285 == sum(area.count for area in plan.areas)
    # 536 pages of 1,000 and the count itself: the figure #1701's question asks about.
    assert plan.requests == 537 == 1 + sum(math.ceil(a.count / 1000) for a in plan.areas)
    # Largest first, so a stopped first crawl has read the most notices it could.
    assert plan.areas[0].name == "India" and plan.areas[0].count == 47_395
    assert [a.count for a in plan.areas] == sorted((a.count for a in plan.areas), reverse=True)


def test_areas_are_read_largest_first_whatever_order_the_bank_lists_them():
    """The Bank lists its facet largest first today, and says nowhere that it will."""
    smallest_first = facet({"Palau": notices(8), "Egypt, Arab Republic of": notices(1_448),
                            "Kenya": notices(1_204)})
    plan = wc.count_areas(Bank(facets=smallest_first))
    assert [a.name for a in plan.areas] == ["Egypt, Arab Republic of", "Kenya", "Palau"]


def test_the_count_line_is_the_contracts():
    plan = wc.count_areas(Bank(facets=FACETS))
    assert wc.count_line(plan) == "counted 422,285 notices in 184 areas: 537 requests"


@pytest.mark.parametrize("break_it", [
    lambda f: f.pop("facets"),
    lambda f: f["facets"].pop(wc.AREA_FACET),
    lambda f: f["facets"][wc.AREA_FACET]["0"].update(count="47395"),
    lambda f: f["facets"][wc.AREA_FACET]["0"].update(name="  "),
    lambda f: f.update(total="422,285"),
    # The counts no longer add up to the total: an area is missing from the list.
    lambda f: f["facets"][wc.AREA_FACET].pop("5"),
])
def test_a_count_not_in_the_measured_shape_is_refused(break_it):
    broken = copy.deepcopy(FACETS)
    break_it(broken)
    with pytest.raises(wc.PageShapeError):
        wc.count_areas(Bank(facets=broken))


# ---- one area, page by page ---------------------------------------------------------------

def test_an_area_is_read_page_by_page_and_kept_page_by_page(conn):
    bank = Bank({EGYPT: notices(1_200)})
    result, tally, log, pages = read(conn, bank, EGYPT)
    assert result.complete and result.reason is None
    reads = bank.calls[1:]
    assert [call["os"] for call in reads] == ["0", "1000"]
    assert all(call[wc.AREA_FACET] == EGYPT and call["rows"] == "1000" and call["fl"] == "*"
               and call["srt"] == "id" and call["order"] == "asc" for call in reads)
    assert pages == [(EGYPT, 0), (EGYPT, 1)]
    assert count(conn, "fetched_responses") == 2
    assert count(conn, "tender_releases") == 1_200
    assert (tally.requests, tally.notices, tally.releases_new, tally.releases_unchanged,
            tally.errors) == (2, 1_200, 1_200, 0, 0)
    assert log.says(f"{EGYPT}: 1,200 notices in 2 requests")
    assert not conn.in_transaction, "the last page was left uncommitted"


def test_reading_an_area_again_keeps_nothing_twice(conn):
    bank = Bank({EGYPT: notices(5)})
    read(conn, bank, EGYPT)
    _, tally, _, _ = read(conn, Bank({EGYPT: notices(5)}), EGYPT)
    assert count(conn, "tender_releases") == 5
    assert (tally.releases_new, tally.releases_unchanged) == (0, 5)


def test_one_request_reads_an_area_of_one_notice_and_says_request(conn):
    _, _, log, _ = read(conn, Bank({EGYPT: notices(1)}), EGYPT)
    assert log.says(f"{EGYPT}: 1 notice in 1 request")


def test_evidence_is_compressed_at_level_12_before_the_write_lock(conn, monkeypatch):
    """His ruling on #1733: level 12, and compressed before the lock is taken."""
    seen = []
    real = tenderstore.pack

    def spy(body: bytes) -> tenderstore.Packed:
        seen.append(conn.in_transaction)
        return real(body)

    monkeypatch.setattr(tenderstore, "pack", spy)
    bank = Bank({EGYPT: notices(3)})
    read(conn, bank, EGYPT)
    assert seen == [False], "the body was compressed while the write lock was held"
    blob, digest = conn.execute("SELECT body, body_sha256 FROM fetched_responses").fetchone()
    body = zstandard.ZstdDecompressor().decompress(blob)
    assert blob == zstandard.ZstdCompressor(level=12).compress(body)
    assert digest == hashlib.sha256(body).hexdigest()
    assert tenderstore.response_body(conn, 1) == body


# ---- his ruling on Q1: what a failure does ------------------------------------------------

def test_a_refused_notice_is_counted_with_its_id_and_the_rest_of_its_page_kept(conn):
    page = notices(3)
    page[1]["notice_type"] = "Prequalification Notice"
    _, tally, log, _ = read(conn, Bank({EGYPT: page}), EGYPT)
    assert count(conn, "tender_releases") == 2
    assert tally.errors == 1 and tally.notices == 3
    assert log.says(page[1]["id"]) and log.says("'Prequalification Notice'")
    assert count(conn, "tender_processes") == 2, "the refused notice left a process behind"


@pytest.mark.parametrize("break_it, raises", [
    # #1733 item 4: shapes the converter's docstring does not promise to catch.
    (lambda n: n.update(credit=[{}]), KeyError),
    (lambda n: n.update(credit=["IBRD91660"]), TypeError),
    (lambda n: n.update(agency_name=7), AttributeError),
])
def test_any_exception_from_one_notice_is_counted_not_only_a_shape_error(conn, break_it,
                                                                          raises):
    page = notices(3)
    break_it(page[0])
    with pytest.raises(raises):     # the shape really is one the docstring does not name
        wb.release_from_notice(page[0])
    _, tally, _, _ = read(conn, Bank({EGYPT: page}), EGYPT)
    assert tally.errors == 1 and count(conn, "tender_releases") == 2


def test_a_notice_that_fails_after_its_release_was_written_leaves_nothing(conn, monkeypatch):
    """#1733 item 3: `store_release` writes the release before a refusal can follow, so a
    notice is undone to a savepoint, never committed half-written."""
    page = notices(3)
    doomed = page[1]["id"]
    real = tenderstore.store_release

    def store(c, *, source_site_id, release, fetched_response_id):
        stored = real(c, source_site_id=source_site_id, release=release,
                      fetched_response_id=fetched_response_id)
        if release.payload["id"] == doomed:
            raise ValueError("refused after the release was written")
        return stored

    monkeypatch.setattr(tenderstore, "store_release", store)
    _, tally, _, _ = read(conn, Bank({EGYPT: page}), EGYPT)
    assert tally.errors == 1
    refs = {row[0] for row in conn.execute("SELECT release_ref FROM tender_releases")}
    assert doomed not in refs and len(refs) == 2


def test_a_locked_warehouse_is_not_a_refused_notice(conn, monkeypatch):
    """`CLAUDE.md`: another app holding the write lock is waited for, never routed around.
    Counting it as a refused notice would skip notices in silence; the page is undone."""
    real = tenderstore.store_release
    calls = []

    def store(c, **kw):
        calls.append(kw["release"].payload["id"])
        if len(calls) == 2:
            raise sqlite3.OperationalError("database is locked")
        return real(c, **kw)

    monkeypatch.setattr(tenderstore, "store_release", store)
    tally = wc.Tally()
    with pytest.raises(sqlite3.OperationalError, match="locked"):
        read(conn, Bank({EGYPT: notices(3)}), EGYPT, tally=tally)
    assert tally.errors == 0
    assert count(conn, "tender_releases") == 0 and count(conn, "fetched_responses") == 0
    assert not conn.in_transaction


def test_a_page_whose_every_notice_is_refused_stops_the_crawl_as_failed(conn):
    page = notices(3)
    for notice in page:
        notice["notice_type"] = "Prequalification Notice"
    with pytest.raises(wc.ShapeChanged) as stopped:
        read(conn, Bank({EGYPT: page}), EGYPT)
    message = str(stopped.value)
    assert message.startswith(f"Stopped because the Bank's notices changed shape at {EGYPT}, "
                              "page 1: none of 3 notices could be read")
    assert "'Prequalification Notice'" in message
    assert count(conn, "tender_releases") == 0


def test_a_page_that_fails_after_its_tries_leaves_its_area_unread(conn):
    bank = Bank({EGYPT: notices(1_500)}, fail={(EGYPT, 1000): 503})
    result, _, log, pages = read(conn, bank, EGYPT)
    assert not result.complete
    assert result.reason == f"{EGYPT}, page 2: HTTP 503 after its tries"
    assert pages == [(EGYPT, 0)], "the page before the failure was not kept"
    assert count(conn, "tender_releases") == 1_000
    assert log.says(result.reason)


def test_an_area_whose_total_differs_from_its_count_is_left_unread(conn):
    """The filter is the area's name, and some names hold commas: a total that is not the
    count read a moment ago means this is not the area counted, so nothing is kept."""
    bank = Bank({EGYPT: notices(5)}, totals={EGYPT: 7})
    result, _, log, pages = read(conn, bank, EGYPT)
    assert not result.complete and pages == []
    assert result.reason == f"the Bank answered 7 notices for {EGYPT}, and counted 5"
    assert count(conn, "tender_releases") == 0 and count(conn, "fetched_responses") == 0
    assert log.says(result.reason)


def test_an_area_past_the_offset_limit_is_refused_by_name_without_a_request(conn):
    big = wc.Area(name="Everywhere", count=wc.OFFSET_LIMIT + 1)
    bank = Bank()
    log = Log()
    result = wc.read_area(conn, bank, source_site_id=site(conn), area=big, tally=wc.Tally(),
                          log=log)
    assert bank.requests_count == 0 and not result.complete
    assert result.reason == ("Everywhere: 100,001 notices, past the 100,000 the Bank pages "
                             "to; it is not read")


@pytest.mark.parametrize("stop", [CrawlInterrupted("pause"), CrawlInterrupted("cancel"),
                                  RobotsDisallowed("robots.txt disallows the path"),
                                  CrawlBlocked("5 refusals in a row")])
def test_a_stop_is_never_taken_for_a_failed_page(conn, stop):
    """The owner's Pause or Cancel arrives through the fetcher (`CrawlInterrupted`), and a
    site's refusal as `CrawlBlocked`: both end the crawl, and what was kept stays kept."""
    bank = Bank({EGYPT: notices(1_500)}, raise_at={(EGYPT, 1000): stop})
    with pytest.raises(type(stop)):
        read(conn, bank, EGYPT)
    assert count(conn, "tender_releases") == 1_000
    assert not conn.in_transaction


def test_a_paused_area_goes_on_from_the_next_unread_page(conn):
    rows = notices(2_500)
    with pytest.raises(CrawlInterrupted):
        read(conn, Bank({EGYPT: rows}, raise_at={(EGYPT, 2000): CrawlInterrupted("pause")}),
             EGYPT)
    bank = Bank({EGYPT: rows})
    result, tally, _, pages = read(conn, bank, EGYPT, first_page=2)
    assert result.complete and pages == [(EGYPT, 2)]
    assert [call["os"] for call in bank.calls[1:]] == ["2000"]
    assert count(conn, "tender_releases") == 2_500 and tally.releases_new == 500


@pytest.mark.parametrize("break_it", [
    lambda body: body.pop("procnotices"),
    lambda body: body.update(procnotices={"OP1": {}}),
    lambda body: body.update(total="many"),
    lambda body: body.update(os="1000"),
])
def test_a_page_not_in_the_measured_envelope_is_refused(conn, break_it):
    bank = Bank({EGYPT: notices(3)})
    real = bank.get

    def get(url, params=None, **kw):
        response = real(url, params=params, **kw)
        if "fct" in (params or {}):
            return response
        body = response.json()
        break_it(body)
        return httpx.Response(200, json=body, request=response.request)

    bank.get = get
    with pytest.raises(wc.PageShapeError):
        read(conn, bank, EGYPT)
    assert count(conn, "tender_releases") == 0


# ---- the pass over what changed -----------------------------------------------------------

def stamped(rows: list[dict], stamps: list[str]) -> list[dict]:
    for notice, stamp in zip(rows, stamps, strict=True):
        notice["api_modified_date"] = stamp
    return rows


def test_the_newest_held_is_the_latest_change_stamp_kept(conn):
    assert wc.newest_held(conn, site(conn)) is None
    rows = stamped(notices(3), ["2026-10-01T08:00:00Z", "2026-10-09T16:11:00Z",
                                "2026-10-05T00:00:00Z"])
    read(conn, Bank({EGYPT: rows}), EGYPT)
    assert wc.newest_held(conn, site(conn)) == "2026-10-09T16:11:00Z"


def test_changes_are_read_newest_first_until_the_newest_held(conn):
    since = "2026-10-09T16:11:00Z"
    changed = stamped(notices(4, start=100), ["2026-10-12T09:00:00Z", "2026-10-11T09:00:00Z",
                                              since, "2026-10-01T00:00:00Z"])
    bank = Bank(changed=changed)
    log, tally = Log(), wc.Tally()
    pages = wc.read_changes(conn, bank, source_site_id=site(conn), since=since, tally=tally,
                            log=log)
    call = bank.calls[0]
    assert (call["srt"], call["order"], call["os"], call["fl"]) == (
        "api_modified_date", "desc", "0", "*")
    assert pages == 1
    # The two newer notices and the one at the stamp itself; the older one is not read.
    assert tally.notices == 3 and count(conn, "tender_releases") == 3
    assert log.says("changes: 3 notices in 1 request")


@pytest.mark.parametrize("stamp", [None, 20261012, "12 October 2026"])
def test_a_change_stamp_that_does_not_read_is_kept_and_refused_by_name(conn, stamp):
    """Not taken for older: the pass goes on, and the converter refuses the notice."""
    changed = stamped(notices(3, start=100), ["2026-10-12T09:00:00Z"] * 3)
    changed[1]["api_modified_date"] = stamp
    log, tally = Log(), wc.Tally()
    wc.read_changes(conn, Bank(changed=changed), source_site_id=site(conn),
                    since="2026-10-09T16:11:00Z", tally=tally, log=log)
    assert tally.notices == 3 and tally.errors == 1
    assert count(conn, "tender_releases") == 2


def test_changes_past_the_offset_limit_stop_by_name(conn, monkeypatch):
    monkeypatch.setattr(wc, "OFFSET_LIMIT", 2_000)
    changed = stamped(notices(3_000, start=100), ["2026-10-12T09:00:00Z"] * 3_000)
    log = Log()
    wc.read_changes(conn, Bank(changed=changed), source_site_id=site(conn),
                    since="2026-10-01T00:00:00Z", tally=wc.Tally(), log=log)
    assert count(conn, "tender_releases") == 2_000
    assert log.says("more than 2,000 notices changed since 2026-10-01T00:00:00Z")
