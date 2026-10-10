"""A host ScrapeX never contacts stays uncontacted, whichever door it comes through (#1644).

`config.REFUSED_HOSTS` names the host; these tests hold each door to it. The fetcher's
cases run the REAL `HttpFetcher` over a mock transport that records every request that
would have reached the wire, so "refused" is measured as "nothing was sent", not as
"an exception was raised somewhere".
"""
from __future__ import annotations

import re

import httpx
import pytest

from scrapex import config
from scrapex.config import (
    REFUSED_HOSTS,
    canonical_host,
    checked_host,
    refusal,
    refused_host,
)
from scrapex.connectors.base import HostRefused, HttpFetcher, stopped_because

ENTRY = REFUSED_HOSTS["ahrambc.com"]
SENTENCE = refusal(ENTRY)


# ---- the registry --------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "https://ahrambc.com",
    "https://ahrambc.com/product/x/",
    "https://AhramBC.com./x",                       # case and the resolver's trailing dot
    "https://www.ahrambc.com/",                     # a name under it
    "https://shop.www.ahrambc.com/",
    "https://user:pw@ahrambc.com:8443/p?q=1",       # userinfo and a port
    "https://ａｈｒａｍｂｃ．ｃｏｍ/",                     # full-width letters and dot
    "https://ahrambc。com/",                    # the ideographic full stop
    "ahrambc.com/product/x",                        # typed with no scheme
    "  https://ahrambc.com  ",
])
def test_every_spelling_of_the_host_is_refused(url):
    assert refused_host(url) is ENTRY


@pytest.mark.parametrize("url", [
    "https://notahrambc.com/",                      # ends with the name, is not under it
    "https://ahrambc.com.eg/",                      # starts with it
    "https://ahrambc.co/",
    "https://example.com/ahrambc.com",              # in the path
    "https://example.com/?next=https://ahrambc.com",
    "",
])
def test_a_name_that_only_looks_like_it_is_not_refused(url):
    assert refused_host(url) is None


def test_every_entry_is_written_as_the_resolver_reads_it():
    """An entry spelt any other way would never match: `refused_host` compares the
    canonical form against the keys as they are."""
    for key, entry in REFUSED_HOSTS.items():
        assert key == entry.host == canonical_host(entry.host), entry
        assert "." in entry.host, f"{entry.host}: a bare label would refuse a whole TLD"
        assert entry.reason.strip(), entry
        assert re.fullmatch(r"#\d+", entry.record), f"{entry}: name the issue that records it"


def test_the_sentence_is_pinned():
    """Pinned, because every other test reads it back from `refusal` and would pass
    whatever it said. The host and its cause lead; ScrapeX is named as the one
    refusing; the record is last (design-the-experience review of #1644)."""
    assert SENTENCE == ("ahrambc.com served a malware page, so ScrapeX sends it nothing "
                        "(#1644).")


def test_checked_host_passes_a_url_through_and_refuses_with_the_sentence():
    assert checked_host("https://example.com/") == "https://example.com/"
    assert checked_host(None) is None
    with pytest.raises(ValueError) as refused:
        checked_host("https://www.ahrambc.com/")
    assert str(refused.value) == SENTENCE
    assert ENTRY.host in SENTENCE and ENTRY.record in SENTENCE


# ---- the fetcher ---------------------------------------------------------------------

class Wire:
    """A mock network that records what reached it and answers per host."""

    def __init__(self, answers):
        self.sent: list[str] = []
        self._answers = answers

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(str(request.url))
        return self._answers(request)


@pytest.fixture
def wire(monkeypatch):
    """Every HttpFetcher built while it is active talks to `wire`, WITH its hooks: the
    client is built by the fetcher's own constructor, only the transport is swapped."""
    holder: dict = {}
    real_client = httpx.Client

    def client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(holder["wire"])
        return real_client(*args, **kwargs)
    monkeypatch.setattr(httpx, "Client", client)

    def use(answers):
        holder["wire"] = Wire(answers)
        return holder["wire"]
    return use


def _fetcher() -> HttpFetcher:
    return HttpFetcher(min_interval_s=0, jitter=0, max_attempts=3)


def test_a_harmless_host_is_still_fetched(wire):
    """The control: the hook refuses a listed host, not every host."""
    net = wire(lambda r: httpx.Response(200, text="ok"))
    assert _fetcher().get("https://good.example/p").text == "ok"
    assert net.sent == ["https://good.example/robots.txt", "https://good.example/p"]


def test_a_request_to_the_host_sends_nothing(wire):
    net = wire(lambda r: httpx.Response(200, text="should never be read"))
    fetcher = _fetcher()
    with pytest.raises(HostRefused) as refused:
        fetcher.get("https://www.ahrambc.com/product/x/")
    assert str(refused.value) == SENTENCE
    assert net.sent == [], "the robots.txt read, or the page itself, reached the wire"
    assert fetcher.retry_count == 0


def test_a_redirect_into_the_host_is_refused_at_the_hop(wire):
    """A harmless page that answers 302 to the refused host: its own requests go out,
    the hop does not -- the case a check on the URL a connector asked for misses."""
    def answers(request):
        if request.url.path == "/p":
            return httpx.Response(302, headers={"Location": "https://WWW.AhramBC.com./landing"})
        return httpx.Response(404)
    net = wire(answers)
    with pytest.raises(HostRefused):
        _fetcher().get("https://good.example/p")
    assert net.sent == ["https://good.example/robots.txt", "https://good.example/p"]


def test_a_robots_txt_that_redirects_into_the_host_stops_the_run(wire):
    """NOT "robots.txt could not be read -- treated as if the site had none": the
    refusal reaches the run as itself, and the page after it never goes out."""
    def answers(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(301, headers={"Location": "https://ahrambc.com/robots.txt"})
        return httpx.Response(200, text="page")
    net = wire(answers)
    fetcher = _fetcher()
    with pytest.raises(HostRefused):
        fetcher.get("https://good.example/p")
    assert net.sent == ["https://good.example/robots.txt"]
    assert not any("robots.txt could not be read" in w for w in fetcher.robots_warnings)


def test_read_robots_of_the_host_sends_nothing(wire):
    net = wire(lambda r: httpx.Response(200, text="User-agent: *\n"))
    with pytest.raises(HostRefused):
        _fetcher().read_robots("https://ahrambc.com/")
    assert net.sent == []


def test_the_job_log_says_the_refusal_not_a_block_by_the_site():
    said = stopped_because(HostRefused(SENTENCE))
    assert said == SENTENCE
    assert "blocked by the site" not in said


def test_the_registry_is_the_one_the_fetcher_reads(monkeypatch, wire):
    """One source of truth: a host added to the registry is refused by the fetcher with
    no second list to update."""
    extra = config.RefusedHost("refused.example", "a test entry", "#1")
    monkeypatch.setitem(config.REFUSED_HOSTS, extra.host, extra)
    net = wire(lambda r: httpx.Response(200))
    with pytest.raises(HostRefused):
        _fetcher().get("https://refused.example/")
    assert net.sent == []


# ---- the runners settle it as a failure, never a pause ---------------------------------

def _guarded(site) -> httpx.Client:
    """A mock client built as the fetcher builds its own: WITH the refusal hook."""
    from scrapex.connectors.base import refuse_listed_host
    return httpx.Client(transport=httpx.MockTransport(site), follow_redirects=True,
                        event_hooks={"request": [refuse_listed_host]})


def _into_the_host(request: httpx.Request) -> httpx.Response:
    """A harmless site whose robots.txt reads and whose every page redirects to the
    refused host -- the way a compromised shop would hand a crawl over."""
    if request.url.path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\n")
    return httpx.Response(302, headers={"Location": "https://www.ahrambc.com/verify"})


class _Recorder:
    def __init__(self, answer):
        self.asked: list[str] = []
        self._answer = answer

    def __call__(self, request):
        self.asked.append(str(request.url))
        return self._answer(request)


@pytest.fixture()
def memory():
    from scrapex import db as dbmod
    connection = dbmod.connect(":memory:")
    dbmod.migrate(connection)
    yield connection
    connection.close()


@pytest.fixture()
def journal(tmp_path, monkeypatch):
    from scrapex import localinbox
    monkeypatch.setattr(localinbox, "JOURNAL_DIR", tmp_path / "job-journal")
    return tmp_path / "job-journal"


def _price_entry():
    from scrapex.config import ExtractSpec, SourceEntry
    from scrapex.vocab import ExtractKind, ExtractScope
    return SourceEntry.model_validate({
        "source_key": "GPP_ENERGY", "source_name": "أسعار الطاقة العالمية",
        "base_url": "https://www.globalpetrolprices.com",
        "family": "static-html-table", "cadence": "weekly", "authority": "aggregator",
        "currency": "USD",
        "extract": [ExtractSpec(kind=ExtractKind.COMMODITY_PRICE,
                                scope=ExtractScope.LATEST_ONLY,
                                materials=["DIESEL"], regions=["*"])],
    })


def test_a_price_source_led_into_the_host_fails_and_is_not_offered_a_resume(
        memory, journal, monkeypatch):
    import scrapex.capture as capmod
    from scrapex import jobs

    site = _Recorder(_into_the_host)
    real = capmod.build_connector

    def cut(entry, rules, crawl_settings=None):
        connector, fetcher = real(entry, rules, crawl_settings)
        fetcher._client.close()
        fetcher._client = _guarded(site)
        return connector, fetcher
    monkeypatch.setattr(capmod, "build_connector", cut)
    ref = jobs.create_job(memory, ["GPP_ENERGY"])

    jobs.run_job_once(memory, ref, {"GPP_ENERGY": _price_entry()})

    assert not any("ahrambc" in url for url in site.asked), site.asked
    lines = [line for line in jobs.job_logs(memory, ref)
             if line["source_key"] == "GPP_ENERGY"]
    said = [line for line in lines if SENTENCE in line["message"]]
    assert len(said) == 1, [line["message"] for line in lines]
    assert said[0]["level"] == "error" and said[0]["message"].startswith("failed:")
    assert not any("Resume" in line["message"] or "blocked by the site" in line["message"]
                   or line["message"].startswith("paused") for line in lines), lines
    assert SENTENCE in jobs.get_job(memory, ref)["error_summary"]


def test_a_directory_crawl_led_into_the_host_fails_rather_than_pauses(tmp_path,
                                                                       monkeypatch):
    from scrapex import contractors, directoryjob, jobs
    from scrapex import db as dbmod

    conn = dbmod.connect(tmp_path / "engine.db")
    dbmod.migrate(conn)
    conn.execute("INSERT INTO source_site (source_key, source_name, base_url, platform) "
                 "VALUES ('muqawil_org', 'muqawil.org', 'https://muqawil.org', 'directory')")
    conn.commit()
    monkeypatch.setattr("scrapex.connectors.base.time.sleep", lambda s: None)
    site = _Recorder(_into_the_host)
    real = contractors.make_fetch

    def cut(crawl_settings, rules):
        fetcher, fetch = real(crawl_settings, rules)
        fetcher._client.close()
        fetcher._client = _guarded(site)
        return fetcher, fetch
    monkeypatch.setattr(contractors, "make_fetch", cut)
    ref = jobs.create_job(conn, ["muqawil_org"], job_kind=directoryjob.JOB_KIND)
    conn.commit()
    try:
        directoryjob.run_directory_crawl_job_once(conn, ref)
        job = jobs.get_job(conn, ref)
        messages = [line["message"] for line in jobs.job_logs(conn, ref)]
    finally:
        conn.close()

    assert not any("ahrambc" in url for url in site.asked), site.asked
    assert job["status"] == "failed", (job["status"], messages)
    assert any(m == f"failed: {SENTENCE}" for m in messages), messages
    assert not any(m.startswith("paused") for m in messages), messages


# ---- organization enrichment's own client ------------------------------------------------

def test_enrichment_asks_the_host_for_nothing_not_even_its_address(monkeypatch):
    """Its client is not HttpFetcher's: it pins each request to an address it looks
    up first. The refusal comes before the lookup, so the name is not even resolved."""
    from scrapex.enrichment.providers import website as provider

    looked_up: list[str] = []
    monkeypatch.setattr(provider, "_public_addresses",
                        lambda host, port=443: looked_up.append(host) or ("8.8.8.8",))
    net = _Recorder(lambda request: httpx.Response(200, request=request))
    with httpx.Client(transport=httpx.MockTransport(net)) as client, \
            pytest.raises(ValueError) as refused:
        provider._fetch_with_client(client, "https://www.ahrambc.com/")
    assert str(refused.value) == SENTENCE
    assert looked_up == [] and net.asked == []


def test_an_organization_whose_site_is_the_host_records_the_refusal_as_its_reason(
        monkeypatch):
    from scrapex.enrichment.models import OrganizationIdentity
    from scrapex.enrichment.providers import website as provider

    monkeypatch.setattr(provider, "_public_addresses",
                        lambda host, port=443: pytest.fail(f"looked up {host}"))
    identity = OrganizationIdentity(
        organization_id="o1", external_id="1", source_record_id=1, source_snapshot_id=1,
        source_url="https://directory.example/1", company_name="Al Ahram",
        email="sales@ahrambc.com", website="ahrambc.com")
    result = provider.WebsiteProvider().run(identity)
    (fact,) = result.facts
    assert fact.value == "not_found"
    assert fact.evidence["reason"] == SENTENCE


def test_the_browser_fetcher_refuses_the_host_before_starting_a_browser(monkeypatch):
    """Before the Playwright import in `get_html`. Built without its constructor, which
    imports Playwright to check the extra is installed, so this holds without it."""
    import builtins

    from scrapex.connectors.base import BrowserFetcher

    real_import = builtins.__import__

    def no_playwright(name, *args, **kwargs):
        if name.startswith("playwright"):
            pytest.fail("the browser was started for a refused host")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", no_playwright)
    fetcher = BrowserFetcher.__new__(BrowserFetcher)
    fetcher.requests_count = 0
    with pytest.raises(HostRefused):
        fetcher.get_html("https://www.ahrambc.com/")
    assert fetcher.requests_count == 0


# ---- the doors: nothing on a refused host is declared ------------------------------------

def test_the_manifest_refuses_the_host_in_every_url_it_declares():
    from pydantic import ValidationError

    from scrapex.config import ApiConfig, SourceEntry, TaxEvidence, TaxonomyConfig

    base = {"source_key": "HOST_TEST", "source_name": "x", "base_url": "https://good.example",
            "family": "woocommerce-storeapi", "cadence": "manual", "authority": "shop",
            "extract": [{"kind": "product_prices", "scope": "census"}]}
    SourceEntry.model_validate(base)                     # the control
    for bad in (
        {**base, "base_url": "https://www.ahrambc.com"},
        {**base, "api": {"base_url": "https://api.ahrambc.com"}},
        {**base, "taxonomy": {"base_url": "https://ahrambc.com"}},
        {**base, "tax": [{"evidence": "general", "statement_url": "https://ahrambc.com/t"}]},
    ):
        with pytest.raises(ValidationError) as refused:
            SourceEntry.model_validate(bad)
        assert SENTENCE in str(refused.value)
    for model, field in ((ApiConfig, "base_url"), (TaxonomyConfig, "base_url")):
        with pytest.raises(ValidationError):
            model.model_validate({field: "https://ahrambc.com"})
    with pytest.raises(ValidationError):
        TaxEvidence.model_validate({"evidence": "general",
                                    "statement_url": "https://ahrambc.com/t"})


def test_the_shipped_manifest_declares_no_refused_host():
    from scrapex.config import load_manifest
    for entry in load_manifest().sources:
        urls = [entry.base_url, entry.api and entry.api.base_url,
                entry.taxonomy and entry.taxonomy.base_url,
                *(t.statement_url for t in entry.tax or [])]
        assert not [u for u in urls if u and refused_host(u)], entry.source_key


@pytest.fixture()
def app_client(tmp_path):
    import shutil

    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from scrapex import db as dbmod
    from scrapex.config import MANIFEST_FILE
    from scrapex.webui.app import create_app

    database = tmp_path / "engine.db"
    conn = dbmod.connect(database)
    dbmod.migrate(conn)
    conn.close()
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(database, manifest_path=manifest)), database, manifest


def test_the_probe_refuses_before_asking_the_site_anything(app_client, monkeypatch):
    client, _, _ = app_client
    monkeypatch.setattr("scrapex.webui.app.probe_url",
                        lambda url: pytest.fail("the probe ran for a refused host"))
    answer = client.post("/api/probe", json={"url": "https://WWW.AhramBC.com./shop"})
    assert answer.status_code == 400 and answer.json()["detail"] == SENTENCE


def test_adding_the_host_is_refused_with_the_sentence_alone(app_client):
    client, _, manifest = app_client
    before = manifest.read_bytes()
    answer = client.post("/api/sources", json={
        "source_key": "AHRAM_AGAIN", "source_name": "x", "base_url": "https://ahrambc.com",
        "family": "woocommerce-storeapi", "kind": "product_prices", "scope": "census"})
    assert answer.status_code == 400
    assert answer.json()["detail"] == SENTENCE, "not pydantic's report, not 'invalid source:'"
    assert manifest.read_bytes() == before


def test_editing_a_source_onto_the_host_is_refused(app_client):
    from scrapex.config import load_manifest

    client, _, manifest = app_client
    entry = load_manifest(manifest).sources[0]
    before = manifest.read_bytes()
    from scrapex import source_settings
    # His per-source choices are refused by /edit before anything else (#1584).
    form = {k: v for k, v in entry.model_dump(mode="json").items()
            if k not in source_settings.FIELDS}
    form["base_url"] = "https://shop.ahrambc.com"
    answer = client.post(f"/api/sources/{entry.source_key}/edit", json=form)
    assert answer.status_code == 400 and answer.json()["detail"] == SENTENCE
    assert manifest.read_bytes() == before


def test_a_leftover_registration_cannot_queue_a_job(app_client):
    """A source removed for its host can leave its `source_site` row behind (#1650);
    the resolver refuses it rather than queue a job only the fetcher would stop."""
    from scrapex import db as dbmod
    from scrapex.sourceresolver import RefusedSource, SourceResolver

    client, database, _ = app_client
    conn = dbmod.connect(database)
    conn.execute("INSERT INTO source_site (source_key, source_name, base_url) "
                 "VALUES ('AHRAMBC', 'x', 'https://ahrambc.com')")
    conn.commit()
    conn.close()
    resolver = SourceResolver(_EmptyManifest(), lambda: dbmod.connect(database))
    with pytest.raises(RefusedSource) as refused:
        resolver.get("AHRAMBC")
    assert str(refused.value) == SENTENCE
    answer = client.post("/api/jobs", json={"source_keys": ["AHRAMBC"]})
    assert answer.status_code == 400 and answer.json()["detail"] == SENTENCE
    conn = dbmod.connect(database)
    assert conn.execute("SELECT COUNT(*) FROM crawl_job").fetchone()[0] == 0
    conn.close()


class _EmptyManifest:
    def get(self, key):
        raise KeyError(key)


def test_registering_the_host_as_a_general_site_is_a_conflict(app_client):
    client, database, _ = app_client
    answer = client.post("/api/catalog/sites", json={
        "site_key": "ahram_site", "display_name": "x", "base_url": "https://ahrambc.com/"})
    assert answer.status_code == 409 and answer.json()["detail"] == SENTENCE
    from scrapex import db as dbmod
    conn = dbmod.connect(database)
    assert conn.execute("SELECT COUNT(*) FROM source_site WHERE source_key='ahram_site'"
                        ).fetchone()[0] == 0
    conn.close()


def test_a_probe_of_a_site_that_redirects_into_the_host_says_so(app_client, wire):
    """The typed address is harmless; its pages answer 302 to the refused host. The
    probe must not read that as silence and offer to register the site (review of
    #1644): the route answers the sentence, and only the harmless host was asked."""
    client, _, _ = app_client
    net = wire(_into_the_host)
    answer = client.post("/api/probe", json={"url": "https://good.example/"})
    assert answer.status_code == 400
    assert answer.json()["detail"] == f"{SENTENCE} good.example redirects to it.", (
        "the refusal must name the address he typed, which is not the refused host")
    assert net.sent and all("good.example" in url for url in net.sent), net.sent


# ---- the directory crawl: a refusal deep inside a cell ends the crawl ----------------------
#
# Every layer of the listing crawl turns a fetch error into a record and goes on (the
# walker, the witness, both sizings), which is right for a dead page and wrong for a site
# that leads into a refused host: filed as a failed page, the walk asked for every page
# after it and the sentence reached no screen (second design review of #1644). Each case
# below refuses ONE fetch at one of those layers and asserts the crawl stops there.

def _partition_crawl(conn, refuse_when):
    """`crawl_partition` over the existing fake directory, with the fetch that
    `refuse_when(url, hits)` names raising HostRefused instead of answering."""
    from scrapex.partitioncrawl import crawl_partition
    from tests.test_a_crawl_that_can_prove_it_read_everything import (
        BASE,
        Directory,
        Partition,
        cell,
        register,
    )

    register(conn)
    ids = [str(n) for n in range(1, 10)]
    directory = Directory({"whole": list(ids), "region_id_1": list(ids)})
    partition = Partition(directory, cells=(cell(region_id=1),))
    hits: dict[str, int] = {}
    asked: list[str] = []

    def fetch(url: str) -> str:
        hits[url] = hits.get(url, 0) + 1
        asked.append(url)
        if refuse_when(url, hits[url], directory):
            raise HostRefused(SENTENCE)
        return directory.fetch(url)

    with pytest.raises(HostRefused):
        crawl_partition(conn, partition, BASE, fetch=fetch, run_ref="run-1",
                        dataset_key="rows", max_attempts=1)
    return asked


@pytest.fixture()
def engine_conn(tmp_path):
    from tests.test_a_crawl_that_can_prove_it_read_everything import conn as make
    yield from make.__wrapped__(tmp_path)


def test_a_page_inside_a_cell_that_leads_to_the_host_ends_the_walk(engine_conn):
    """Page 2 is read only by the walker (sizing reads pages 1 and 3)."""
    asked = _partition_crawl(engine_conn,
                             lambda url, n, d: url.endswith("region_id=1&page=2"))
    assert asked[-1].endswith("region_id=1&page=2"), (
        f"the walk went on asking after the refusal: {asked[asked.index(next(u for u in asked if u.endswith('page=2'))):]}")


def test_sizing_a_cell_that_leads_to_the_host_ends_the_crawl(engine_conn):
    asked = _partition_crawl(engine_conn,
                             lambda url, n, d: url.endswith("region_id=1&page=1") and n == 1)
    assert asked[-1].endswith("region_id=1&page=1"), asked


def test_a_witness_that_leads_to_the_host_ends_the_crawl(engine_conn):
    """Page 1 is asked three times: sizing, the read, then the witness."""
    asked = _partition_crawl(engine_conn,
                             lambda url, n, d: url.endswith("region_id=1&page=1") and n == 3)
    assert asked[-1].endswith("region_id=1&page=1"), asked
    assert asked.count(asked[-1]) == 3, asked


def test_resizing_a_short_cell_that_leads_to_the_host_ends_the_crawl(engine_conn):
    """A cell that came up short is sized again at the end; that request refused.
    The shortfall is made by the site dropping rows after the read began."""
    state = {"read_done": False}

    def refuse(url, n, directory):
        if url.endswith("region_id=1&page=3") and n == 2:
            # The read's last page: the site drops two rows, so the read comes up short.
            directory.roll("region_id_1", [str(k) for k in range(1, 8)])
            state["read_done"] = True
            return False
        # After the read and its witness, the next sizing request is the resize.
        return state["read_done"] and url.endswith("region_id=1&page=1") and n == 4
    asked = _partition_crawl(engine_conn, refuse)
    assert asked[-1].endswith("region_id=1&page=1") and asked.count(asked[-1]) == 4, asked
