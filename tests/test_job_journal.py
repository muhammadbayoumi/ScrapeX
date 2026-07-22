"""Per-page resume: the job journal (localinbox + capture + jobs).

A pause at page 399 of a 400-page crawl used to throw away every fetched page.
Capture now journals each yielded table to disk AS IT ARRIVES; a pause keeps
the journal and marks the source in the job checkpoint; the resumed capture
hands the journaled tokens back to the connector as its skip set, refetches
only the tail, and ingests the whole. The journal is a separate dir from the
CLI inbox on purpose — a job clearing its own state must never touch payloads
the owner crawled and has not ingested yet.
"""
from __future__ import annotations

import sqlite3

import pytest

from scrapex import db as dbmod
from scrapex import localinbox
from scrapex.capture import capture_source
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.base import CrawlInterrupted, ScrapedTable
from scrapex.jobs import create_job, get_job, job_logs, run_job_once
from scrapex.rowspec import COMMODITY_PRICE, RowBuilder
from scrapex.vocab import ExtractKind, ExtractScope, JobStatus


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


@pytest.fixture()
def journal(tmp_path, monkeypatch):
    """Point BOTH consumers (capture + jobs) at a throwaway journal dir."""
    jdir = tmp_path / "job-journal"
    monkeypatch.setattr(localinbox, "JOURNAL_DIR", jdir)
    return jdir


def make_entry() -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key="GPP_ENERGY", source_name="أسعار الطاقة العالمية",
        base_url="https://www.globalpetrolprices.com", family="static-html-table",
        cadence="weekly", authority="aggregator", currency="USD",
        extract=[ExtractSpec(kind=ExtractKind.COMMODITY_PRICE,
                             scope=ExtractScope.LATEST_ONLY,
                             materials=["DIESEL"], regions=["*"])],
    ))


_BUILDER = RowBuilder(COMMODITY_PRICE)

_PAGES = [("DIESEL--EG", "EG", "20.50"),
          ("DIESEL--SA", "SA", "1.77"),
          ("DIESEL--US", "US", "0.95")]


def _page(token: str, region: str, price: str) -> ScrapedTable:
    row = _BUILDER.row(material_key="DIESEL", region=region, currency="EGP",
                       unit="liter", vat_included="1", effective_price=price,
                       provenance="observed", price_basis="original")
    return ScrapedTable("GPP_ENERGY", ExtractKind.COMMODITY_PRICE,
                        f"https://x/{region}", _BUILDER.header, [row],
                        page_token=token)


class _PagedConnector:
    """Three tokenized pages; optionally hits the owner's brakes mid-crawl."""
    connector_id = "paged-fake"

    def __init__(self, interrupt_after: int | None = None, control: str = "pause"):
        self.skip_tokens: set[str] = set()
        self.served: list[str] = []
        self._interrupt_after = interrupt_after
        self._control = control

    def fetch(self, entry):
        for token, region, price in _PAGES:
            if token in self.skip_tokens:
                continue
            if (self._interrupt_after is not None
                    and len(self.served) >= self._interrupt_after):
                raise CrawlInterrupted(self._control)
            self.served.append(token)
            yield _page(token, region, price)


class _Fetcher:
    requests_count = 0
    def close(self): pass


def _with_connector(monkeypatch, connector):
    import scrapex.capture as capmod
    monkeypatch.setattr(capmod, "build_connector",
                        lambda entry, crawl_settings=None: (connector, _Fetcher()))


def _job(conn) -> tuple[str, int]:
    ref = create_job(conn, ["GPP_ENERGY"])
    return ref, get_job(conn, ref)["job_id"]


# ---- localinbox: the filename IS the checkpoint ------------------------------

def test_tokens_ride_the_filename_and_list_back(tmp_path):
    localinbox.write_payload(tmp_path, _page("DIESEL--EG", "EG", "20.50").to_payload(),
                             token="DIESEL--EG")
    localinbox.write_payload(tmp_path, _page("", "SA", "1.77").to_payload())

    assert localinbox.list_tokens(tmp_path, "GPP_ENERGY") == {"DIESEL--EG"}


def test_a_hostile_token_is_sanitised_not_rejected(tmp_path):
    localinbox.write_payload(tmp_path, _page("x", "EG", "1").to_payload(),
                             token="a/b:c")

    assert localinbox.list_tokens(tmp_path, "GPP_ENERGY") == {"a-b-c"}


def test_clear_untokenized_keeps_the_checkpoint_pages(tmp_path):
    localinbox.write_payload(tmp_path, _page("t", "EG", "1").to_payload(), token="T1")
    localinbox.write_payload(tmp_path, _page("", "SA", "1").to_payload())

    assert localinbox.clear_untokenized(tmp_path, "GPP_ENERGY") == 1
    assert localinbox.list_tokens(tmp_path, "GPP_ENERGY") == {"T1"}
    assert len(localinbox.read_payloads(tmp_path, "GPP_ENERGY")) == 1


# ---- capture: journal on the way down, whole on the way back -----------------

def test_an_interrupted_capture_leaves_its_pages_in_the_journal(conn, journal, monkeypatch):
    _with_connector(monkeypatch, _PagedConnector(interrupt_after=2))
    _, job_id = _job(conn)

    with pytest.raises(CrawlInterrupted):
        capture_source(conn, make_entry(), job_id)

    assert localinbox.list_tokens(journal, "GPP_ENERGY") == {"DIESEL--EG", "DIESEL--SA"}


def test_resume_refetches_only_the_tail_and_ingests_the_whole(conn, journal, monkeypatch):
    _with_connector(monkeypatch, _PagedConnector(interrupt_after=2))
    _, job_id = _job(conn)
    with pytest.raises(CrawlInterrupted):
        capture_source(conn, make_entry(), job_id)

    second = _PagedConnector()
    _with_connector(monkeypatch, second)
    result = capture_source(conn, make_entry(), job_id, resume=True)

    assert second.skip_tokens == {"DIESEL--EG", "DIESEL--SA"}
    assert second.served == ["DIESEL--US"], "a journaled page was refetched"
    # The volume canary and the ingest both see the WHOLE crawl, not the tail.
    assert (result.tables, result.rows) == (3, 3)
    assert result.ingest.observations == 3
    assert localinbox.list_tokens(journal, "GPP_ENERGY") == set(), \
        "the journal must be consumed after a successful ingest"


def test_a_fresh_capture_never_ingests_a_stale_journal(conn, journal, monkeypatch):
    """Pages fetched on a DIFFERENT day (crashed or cancelled job) must not mix
    into this crawl's ingest as if they were today's prices."""
    localinbox.write_payload(journal, _page("DIESEL--ZZ", "ZW", "9.99").to_payload(),
                             token="DIESEL--ZZ")
    connector = _PagedConnector()
    _with_connector(monkeypatch, connector)
    _, job_id = _job(conn)

    result = capture_source(conn, make_entry(), job_id)

    assert connector.skip_tokens == set()
    assert result.ingest.observations == 3, "a stale journaled page was ingested"


def test_resume_with_a_connector_that_cannot_skip_refetches_whole_without_doubling(
        conn, journal, monkeypatch):
    class _Single:
        connector_id = "single-fake"
        def fetch(self, entry):
            yield _page("", "EG", "20.50")

    # As if an older version journaled tokenized pages for this source.
    localinbox.write_payload(journal, _page("DIESEL--EG", "EG", "20.50").to_payload(),
                             token="DIESEL--EG")
    _with_connector(monkeypatch, _Single())
    _, job_id = _job(conn)

    result = capture_source(conn, make_entry(), job_id, resume=True)

    assert result.ingest.observations == 1, \
        "keeping a journal the connector cannot skip double-ingests every page"


def test_warnings_fetched_before_a_pause_reach_the_log_not_the_void(conn, journal, monkeypatch):
    """Journal payloads carry no warnings (frozen contract), and the resume
    skips the pages that produced them — flushing at the interrupt is the only
    moment they can still be said."""
    class _Warny(_PagedConnector):
        def fetch(self, entry):
            table = _page("DIESEL--EG", "EG", "20.50")
            table.warnings.append("EG: something notable this week")
            yield table
            raise CrawlInterrupted("pause")

    _with_connector(monkeypatch, _Warny())
    ref, job_id = _job(conn)

    with pytest.raises(CrawlInterrupted):
        capture_source(conn, make_entry(), job_id)

    messages = [entry["message"] for entry in job_logs(conn, ref)]
    assert any("EG: something notable this week" in m for m in messages)


# ---- jobs: pause keeps, resume completes, cancel discards --------------------

def test_pause_mid_fetch_keeps_pages_and_resume_completes_the_job(conn, journal, monkeypatch):
    manifest = {"GPP_ENERGY": make_entry()}
    _with_connector(monkeypatch, _PagedConnector(interrupt_after=2, control="pause"))
    ref = create_job(conn, ["GPP_ENERGY"])

    job = run_job_once(conn, ref, manifest)

    assert job["status"] == JobStatus.PAUSED.value
    assert job["checkpoint"]["partial_source"] == "GPP_ENERGY"
    messages = [entry["message"] for entry in job_logs(conn, ref)]
    assert any("2 fetched page(s) kept" in m for m in messages)

    second = _PagedConnector()
    _with_connector(monkeypatch, second)
    job = run_job_once(conn, ref, manifest)

    assert job["status"] == JobStatus.COMPLETED.value
    assert second.served == ["DIESEL--US"]
    assert "partial_source" not in job["checkpoint"]
    assert localinbox.list_tokens(journal, "GPP_ENERGY") == set()
    observations = conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
    assert observations == 3, "the resumed job must land the WHOLE crawl"


def test_politeness_notes_land_in_the_job_log_as_info_not_warning(conn, journal, monkeypatch):
    """Owner robots ruling (docs/robots-policy.md): a Disallow crossed — like
    every politeness disclosure — is ONE info-level line. A warning would
    dress a policy decision as a defect that needs review."""
    class _NotingFetcher(_Fetcher):
        robots_warnings = [
            "x.com: robots.txt disallows some of the paths we crawl (first: "
            "/p) — crawled anyway per the robots policy: Disallow is "
            "informational, not enforced"]

    import scrapex.capture as capmod
    monkeypatch.setattr(capmod, "build_connector",
                        lambda entry, crawl_settings=None: (_PagedConnector(),
                                                            _NotingFetcher()))
    ref = create_job(conn, ["GPP_ENERGY"])

    run_job_once(conn, ref, {"GPP_ENERGY": make_entry()})

    entries = [e for e in job_logs(conn, ref) if "disallows" in e["message"]]
    assert len(entries) == 1, "the disclosure must appear exactly once"
    assert entries[0]["level"] == "info", "a politeness note was dressed as a warning"


def test_cancel_mid_fetch_discards_the_journal(conn, journal, monkeypatch):
    _with_connector(monkeypatch, _PagedConnector(interrupt_after=2, control="cancel"))
    ref = create_job(conn, ["GPP_ENERGY"])

    job = run_job_once(conn, ref, {"GPP_ENERGY": make_entry()})

    assert job["status"] == JobStatus.CANCELLED.value
    assert localinbox.list_tokens(journal, "GPP_ENERGY") == set(), \
        "a cancelled job left stale journal state behind"
    messages = [entry["message"] for entry in job_logs(conn, ref)]
    assert any("partial fetch was discarded" in m for m in messages)
