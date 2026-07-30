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

import json
import sqlite3
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex import localinbox
from scrapex.capture import capture_source
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.connectors.base import CrawlInterrupted, ScrapedTable
from scrapex.ingest import ingest_payloads
from scrapex.jobs import create_job, get_job, job_logs, run_job_once
from scrapex.payload import PAYLOAD_VERSION
from scrapex.rowspec import COMMODITY_PRICE, RowBuilder
from scrapex.vocab import ExtractKind, ExtractScope, JobStatus, RunStatus


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
    row = _BUILDER.row(material_key="DIESEL", country_code_alpha2=region, currency="EGP",
                       unit="liter", tax_included="1", price=price,
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


def test_journal_state_reports_exactly_what_a_resume_would_skip(tmp_path):
    """The count the panel shows and the skip set the connector gets are the
    same number, or it is a number the owner cannot act on. Untokenized pages
    are re-emitted by the re-run, so they are not kept work and must not be
    counted as any."""
    localinbox.write_payload(tmp_path, _page("t", "EG", "1").to_payload(), token="T1")
    localinbox.write_payload(tmp_path, _page("t", "SA", "1").to_payload(), token="T2")
    localinbox.write_payload(tmp_path, _page("", "US", "1").to_payload())

    state = localinbox.journal_state(tmp_path, "GPP_ENERGY")

    assert state["pages"] == len(localinbox.list_tokens(tmp_path, "GPP_ENERGY")) == 2
    assert state["stopped_at"].endswith("Z"), state["stopped_at"]


def test_a_page_cleared_mid_scan_costs_one_page_not_the_whole_answer(
        tmp_path, monkeypatch):
    """capture clears the journal the moment an ingest succeeds, and the panel
    asks for this state on every refresh — so the scan can race a job
    finishing. Raising there would fail /api/sources, and the panel would
    report the engine unreachable because a crawl had gone WELL."""
    localinbox.write_payload(tmp_path, _page("t", "EG", "1").to_payload(), token="T1")
    real = localinbox._source_dir(tmp_path, "GPP_ENERGY")

    class _RacingDir:
        def is_dir(self):
            return True

        def glob(self, pattern):
            yield real / "T2__cleared_00000000.json"   # gone before we stat it
            yield from real.glob(pattern)

    monkeypatch.setattr(localinbox, "_source_dir", lambda base, key: _RacingDir())

    assert localinbox.journal_state(tmp_path, "GPP_ENERGY")["pages"] == 1


def test_a_source_that_kept_nothing_says_so_rather_than_failing(tmp_path):
    """Every source is asked this on every panel refresh, including the ones
    that have never been interrupted and have no directory at all."""
    assert localinbox.journal_state(tmp_path, "NEVER_RAN") == \
        {"pages": 0, "stopped_at": None}


def test_clear_untokenized_keeps_the_checkpoint_pages(tmp_path):
    localinbox.write_payload(tmp_path, _page("t", "EG", "1").to_payload(), token="T1")
    localinbox.write_payload(tmp_path, _page("", "SA", "1").to_payload())

    assert localinbox.clear_untokenized(tmp_path, "GPP_ENERGY") == 1
    assert localinbox.list_tokens(tmp_path, "GPP_ENERGY") == {"T1"}
    assert len(localinbox.read_payloads(tmp_path, "GPP_ENERGY").payloads) == 1


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


def test_a_seeded_checkpoint_resumes_a_journal_whose_own_job_is_gone(
        conn, journal, monkeypatch):
    """The failure this feature exists for: elburoj's paused job was cancelled,
    so the only non-terminal job that could have carried its 871 kept pages
    became terminal and the pages were unreachable. A NEW job seeded with the
    same partial_source picks them up — the journal, not the job row, is the
    asset."""
    localinbox.write_payload(journal, _page("DIESEL--EG", "EG", "20.50").to_payload(),
                             token="DIESEL--EG")
    localinbox.write_payload(journal, _page("DIESEL--SA", "SA", "1.77").to_payload(),
                             token="DIESEL--SA")
    connector = _PagedConnector()
    _with_connector(monkeypatch, connector)

    ref = create_job(conn, ["GPP_ENERGY"],
                     checkpoint={"completed_source_keys": [], "errors": [],
                                 "succeeded": 0, "partial_source": "GPP_ENERGY"})
    job = run_job_once(conn, ref, {"GPP_ENERGY": make_entry()})

    assert job["status"] == JobStatus.COMPLETED.value
    assert connector.skip_tokens == {"DIESEL--EG", "DIESEL--SA"}
    assert connector.served == ["DIESEL--US"], "a kept page was fetched again"
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


def test_a_rebuild_that_cannot_write_archives_NOTHING(conn, journal, monkeypatch):
    """The owner's sika loss: the job archived 87 products, THEN hit a held
    write lock and died — catalogue gone, nothing re-crawled. The archive now
    runs inside the same lock as the ingest, so a lock it cannot take means
    nothing was touched."""
    from contextlib import contextmanager

    from scrapex import db as dbmod

    _with_connector(monkeypatch, _PagedConnector())
    _, job_id = _job(conn)
    entry = make_entry()
    ingest_payloads(conn, entry, [_page("", "EG", "1.00").to_payload()])
    before = conn.execute("SELECT COUNT(*) FROM source_product "
                          "WHERE status = 'active'").fetchone()[0]
    assert before

    @contextmanager
    def held_lock():
        raise dbmod.DbLockedError("another scrapex process (pid 1) is writing")
        yield  # pragma: no cover

    with pytest.raises(dbmod.DbLockedError):
        capture_source(conn, entry, job_id, lock=held_lock, archive_first=True)

    after = conn.execute("SELECT COUNT(*) FROM source_product "
                         "WHERE status = 'active'").fetchone()[0]
    assert after == before, "a rebuild that could not write still archived"


# ---- a journal of MIXED versions: the real-world case ------------------------
#
# A journal accumulates pages ACROSS attempts, and the build can change between
# them. ELBUROJ's held 3,570 pages on 2026-07-30 — 2,699 stamped 6 and 871
# stamped 5, kept from the attempts before the additive bump — and read_payloads
# was a list comprehension, so the FIRST page that would not validate raised and
# took all 3,570 with it. Nine attempts against a 10-second crawl-delay were
# unreachable behind one page.
#
# Widening the version gate (PAYLOAD_COMPAT_VERSION, c5bf4b2) fixes the reason
# those particular pages were refused. It does NOT fix this: a page truncated by
# a crash still fails the same way, for every page in the directory, however
# wide the compat range gets. Containment is a separate requirement.

FIXTURE_JOURNAL = Path(__file__).resolve().parent / "fixtures" / "journal_elburoj_mixed"


def _journal_page(base, source_key: str, name: str, body: dict) -> Path:
    target = Path(base) / source_key
    target.mkdir(parents=True, exist_ok=True)
    path = target / name
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _restamp(table, **envelope) -> dict:
    """A journaled page's json with its version envelope overridden.

    Overridden rather than built that way, because a producer can only ever
    stamp the CURRENT version — which is exactly how a journal comes to hold
    versions this build no longer emits.
    """
    return {**json.loads(table.to_payload().model_dump_json()), **envelope}


def test_the_real_elburoj_pages_the_gate_refused_still_read_back(tmp_path):
    """The surviving evidence, not a reconstruction of it.

    These two files are real pages off the ELBUROJ journal — the SAME product
    (token t-00494d1b…) captured twice: once on 2026-07-29 under payload_version
    5, once on 2026-07-30 under 6. That is the mixed-version journal the whole
    incident is about, and the 871 v5 pages like the first one are all that
    survived nine failed attempts against a 10-second crawl-delay.
    """
    target = tmp_path / "ELBUROJ"
    target.mkdir()
    for src in sorted(FIXTURE_JOURNAL.glob("*.json")):
        (target / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    read = localinbox.read_payloads(tmp_path, "ELBUROJ")

    assert read.skipped == [], read.report()
    assert sorted(p.payload_version for p in read.payloads) == [5, 6]
    # The older page declares no generation at all — it predates the field, and
    # the ledger is what places it.
    older = min(read.payloads, key=lambda p: p.payload_version)
    assert older.payload_compat_version is None
    # And it carries v5's four-columns-shorter header, not a mislabelled v6 one.
    newer = max(read.payloads, key=lambda p: p.payload_version)
    assert set(newer.header) - set(older.header) == {
        "display_method", "minimum_quantity", "quantity_increment",
        "quantity_is_decimal"}


def test_one_unreadable_page_never_costs_the_batch(tmp_path):
    """THE bug, stated on its own: containment, independent of any version.

    Every page here is stamped with the CURRENT contract. One is truncated the
    way a crash mid-write leaves it. Before this fix that single page cost all
    three of the others, and no widening of the compat range would have helped.
    """
    for i, region in enumerate(("EG", "SA", "US")):
        _journal_page(tmp_path, "GPP_ENERGY", f"T{i}__ok.json",
                      _restamp(_page(f"t{i}", region, "1.50")))
    (tmp_path / "GPP_ENERGY" / "T9__truncated.json").write_text(
        '{"payload_version": 7, "source_k', encoding="utf-8")

    read = localinbox.read_payloads(tmp_path, "GPP_ENERGY")

    assert len(read.payloads) == 3, "a crash-truncated page took the batch with it"
    assert [s.kind for s in read.skipped] == ["unreadable"]
    assert "T9__truncated.json" in read.report()[0]


def test_a_mixed_journal_ingests_what_it_can_and_names_what_it_drops(tmp_path):
    """Readable pages land; every skip is grouped, counted and explained."""
    _journal_page(tmp_path, "GPP_ENERGY", "T1__cur.json",
                  _restamp(_page("t1", "EG", "20.50")))
    # Captured before the additive bump, declaring no generation: the ledger
    # places it in the one this build speaks, so it reads.
    _journal_page(tmp_path, "GPP_ENERGY", "T2__additive.json",
                  _restamp(_page("t2", "SA", "1.77"),
                           payload_version=6, payload_compat_version=None))
    # Captured before a RENAME: its columns mean other things now. Refused on
    # purpose — this is the half of the gate that was protecting something.
    _journal_page(tmp_path, "GPP_ENERGY", "T3__renamed.json",
                  _restamp(_page("t3", "US", "0.95"),
                           payload_version=4, payload_compat_version=None))
    # Written by a build from the future, in a generation this one cannot read.
    _journal_page(tmp_path, "GPP_ENERGY", "T4__future.json",
                  _restamp(_page("t4", "EG", "9.99"),
                           payload_version=9, payload_compat_version=9))
    (tmp_path / "GPP_ENERGY" / "T5__truncated.json").write_text(
        '{"payload_version": 7, "sou', encoding="utf-8")

    read = localinbox.read_payloads(tmp_path, "GPP_ENERGY")

    assert len(read.payloads) == 2
    assert sorted(p.payload_version for p in read.payloads) == [6, PAYLOAD_VERSION]
    assert {s.kind for s in read.skipped} == {"too_old", "too_new", "unreadable"}
    assert all(s.name and s.detail for s in read.skipped)

    report = read.report()
    # One sentence per KIND, never one per page: 871 sentences is not a report.
    assert len(report) == 3
    joined = " | ".join(report)
    # Every number carries its reference: how many, out of how many, and why.
    assert joined.count("1 of 5 journaled page(s)") == 3
    assert "older than this build reads" in joined      # the renamed one
    assert "update this reader" in joined               # the future one
    assert "T5__truncated.json" in joined
    # The two opposite remedies must not be reported as the same event.
    assert "re-fetched" in joined and "upgrade rather than re-crawl" in joined


def test_the_pages_from_before_an_additive_bump_actually_ingest(conn, tmp_path):
    """Readable is not the same claim as ingestable — so ingest them."""
    _journal_page(tmp_path, "GPP_ENERGY", "T1__old.json",
                  _restamp(_page("t1", "EG", "20.50"),
                           payload_version=6, payload_compat_version=None))
    _journal_page(tmp_path, "GPP_ENERGY", "T2__cur.json",
                  _restamp(_page("t2", "SA", "1.77")))

    read = localinbox.read_payloads(tmp_path, "GPP_ENERGY")
    result = ingest_payloads(conn, make_entry(), read.payloads)

    assert read.skipped == []
    assert result.observations == 2, "a page from before the bump did not land"


def test_a_resumed_capture_puts_the_dropped_pages_on_the_run(conn, journal, monkeypatch):
    """The journal is CLEARED after ingest, so this is the last chance to say so.

    A skip that reached nobody would be exactly the quiet discard the owner's
    standing rule forbids — a cancel discards the journal, a pause keeps it,
    and nothing else may throw pages away without saying it did.
    """
    _with_connector(monkeypatch, _PagedConnector())
    ref, job_id = _job(conn)
    # A page kept by a PAUSE taken before a RENAME bump. Only a resume keeps a
    # journal; a fresh capture clears it as a stale one.
    _journal_page(journal, "GPP_ENERGY", "STALE__old.json",
                  _restamp(_page("stale", "US", "0.95"),
                           payload_version=4, payload_compat_version=None))

    result = capture_source(conn, make_entry(), job_id, resume=True).ingest

    assert result.observations, "the readable pages did not land"
    dropped = [e for e in result.errors if "DISCARDED" in e]
    assert len(dropped) == 1, f"the dropped page was not reported: {result.errors}"
    assert "STALE__old.json" in dropped[0]
    # PARTIAL, not FAILED and not SUCCESS: rows genuinely did not land, and
    # everything else did.
    assert result.status is RunStatus.PARTIAL

    # And it reached the owner's log, not just the result object.
    messages = [e["message"] for e in job_logs(conn, ref)]
    assert any("DISCARDED" in m for m in messages), messages

    # Cleared, as it always was — the dropped page is gone, loudly.
    assert localinbox.read_payloads(journal, "GPP_ENERGY").payloads == []
