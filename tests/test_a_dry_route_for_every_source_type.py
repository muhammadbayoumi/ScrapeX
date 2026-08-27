"""One dry route, both registries, and the four claims it makes about itself.

«اعمل مسار dry لكل المصادر مهما اختلفت نوعها» — a dry route for ALL sources, whatever
their type. `REQ-45`: `POST /api/jobs` validates against `app.state.manifest` alone, so
muqawil answered `404 unknown source_key 'contractors'` while `/api/table/contractors`
served 11,059 rows.

WHAT IS ASSERTED HERE RATHER THAN TRUSTED:

  * a key EITHER register knows answers 200 — price key, dataset key and site key;
  * zero requests, with the sockets taken away rather than a comment saying so;
  * zero writes, with the authorizer PROVEN to fire and the row counts held;
  * the passes and their hover come from ONE declaration the panel cannot retype.
"""
from __future__ import annotations

import shutil
import socket
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scrapex import contractors, dryrun, passes
from scrapex.config import MANIFEST_FILE, load_manifest
from scrapex.connectors.factory import _BUILDERS
from scrapex.crawlscope import CrawlScope
from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.extract import service
from scrapex.extract.models import ApprovalField, CandidateApproval, SnapshotCreate
from scrapex.extract.muqawil import listing_candidate
from scrapex.sightings import record_sightings
from scrapex.vocab import RunMode
from scrapex.webui.app import create_app

ROOT = Path(__file__).resolve().parent.parent
LISTING = (ROOT / "tests" / "fixtures" / "muqawil" / "listing-en.html").read_text(
    encoding="utf-8")

DATASET = "contractors"
SITE = "muqawil_org"
#: An id no page approved, so `coverage.missing` is not zero and the block is not
#: vacuous.
NEVER_STORED = "99999901"


def _price_key() -> str:
    """An ACTIVE, IMPLEMENTED source from the shipped manifest, chosen by the file.

    Not typed in: a key that stops being in `sources.yaml` must fail here as a
    missing fixture rather than as a mysterious 404.
    """
    entries = sorted((one for one in load_manifest(MANIFEST_FILE).sources
                      if one.active and one.family in _BUILDERS),
                     key=lambda one: one.source_key)
    assert entries, "sources.yaml has no active implemented source to test against"
    return entries[0].source_key


PRICE = _price_key()


@pytest.fixture(scope="module")
def engine(tmp_path_factory):
    """One approved dataset, its sightings, and one price source with a finished run."""
    tmp = tmp_path_factory.mktemp("dry-route")
    registry = DatabaseRegistry(EngineDatabase(tmp / "scrapex-engine.db"),
                               pointer_file=tmp / "databases.json")
    registry.initialize()
    conn = registry.engine.connect()
    try:
        snapshot = service.save_snapshot(conn, SnapshotCreate(
            source_url="https://muqawil.org/en/contractors?page=1",
            html_content=LISTING, crawl_run_ref="listing-test"))
        candidate = listing_candidate(LISTING)
        service.approve_candidate(
            conn, int(snapshot["page_snapshot_id"]),
            CandidateApproval(
                table_index=0, site_key=SITE, site_display_name="SCA",
                dataset_key=DATASET, dataset_name="Contractors",
                fields=[ApprovalField(field_key=f.field_key,
                                      display_name=f.source_name, data_type="text",
                                      identity=(f.field_key == "contractor_id"))
                        for f in candidate.fields]),
            candidate=candidate)
        stored_ids = [str(row["contractor_id"]) for row in candidate.rows]
        record_sightings(conn, DATASET, [*stored_ids, NEVER_STORED],
                         run_ref="listing-test")
        conn.execute(
            "INSERT INTO source_site (source_id, source_key, source_name_ar, "
            " source_name, base_url, platform, currency, timezone, authority, active) "
            "VALUES (1,?,'س','S','http://s','custom_json','SAR','UTC','shop',1)",
            (PRICE,))
        conn.execute(
            "INSERT INTO crawl_run (run_id, source_id, started_at, finished_at, "
            " status, requests_count, rows_seen, errors_count) "
            "VALUES (1,1,'2026-08-01T00:00:00Z','2026-08-01T00:04:00Z','success',"
            " 812, 4001, 0)")
        conn.commit()
    finally:
        conn.close()
    manifest = tmp / "sources.yaml"     # a COPY, so no test can edit the real one
    shutil.copy(MANIFEST_FILE, manifest)
    return registry, manifest


@pytest.fixture(scope="module")
def client(engine) -> TestClient:
    registry, manifest = engine
    return TestClient(create_app(databases=registry, manifest_path=manifest))


@pytest.fixture()
def log_elsewhere(tmp_path, monkeypatch):
    """`disown_impostors` reports through `contractors.say`, which appends to
    `~/.scrapex/contractors.log`. Kept out of a real home directory here."""
    monkeypatch.setattr(contractors, "LOG", tmp_path / "contractors.log")


pytestmark = pytest.mark.usefixtures("log_elsewhere")


# ---- the premise: without this every assertion below is vacuous --------------

def test_the_warehouse_really_holds_both_kinds(client):
    rows = client.get("/api/sources").json()["sources"]
    kinds = {row["source_key"]: row.get("kind") for row in rows}

    assert kinds.get(DATASET) == "dataset", "no dataset is being served"
    assert PRICE in kinds, f"{PRICE} is not in the manifest this app loaded"


# ---- a key EITHER register knows answers 200 --------------------------------

@pytest.mark.parametrize("key,kind,registry", [
    (PRICE, "price", "sources.yaml"),
    (DATASET, "dataset", "dataset_definition"),
    (SITE, "dataset", "site_profile"),
])
def test_a_key_either_register_knows_answers_200(client, key, kind, registry):
    """THE WHOLE POINT OF 'every source type'. `POST /api/jobs` answers 404 for two
    of these three."""
    response = client.get(f"/api/dry/{key}")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["kind"] == kind
    assert body["registry"] == registry
    assert body["passes"], "a source with no passes is a menu with no entries"


def test_an_unknown_key_is_404_and_names_both_registries(client):
    response = client.get("/api/dry/NOT_A_SOURCE")

    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "sources.yaml" in detail
    assert "dataset_definition" in detail and "site_profile" in detail


def test_the_route_answers_a_dataset_key_that_post_api_jobs_still_refuses(client):
    """The defect, both halves, in one test — so a fix to one cannot hide the other."""
    assert client.get(f"/api/dry/{DATASET}").status_code == 200
    refused = client.post("/api/jobs", json={"source_keys": [DATASET]})
    assert refused.status_code == 404, (
        "POST /api/jobs now resolves a dataset key; this route's reason for existing "
        "has changed and REQ-45 should be re-read")


# ---- zero requests, guarded --------------------------------------------------

def _refuse(*args, **kwargs):
    raise AssertionError("the dry route reached the network")


def _cut_the_wire(monkeypatch) -> None:
    """Every way this code base can reach a host, taken away.

    NOT `socket.socket` ITSELF, and that was measured rather than assumed:
    `TestClient` drives the app through an asyncio loop whose `ProactorEventLoop`
    builds a self-pipe with `socket.socketpair()`, so patching the constructor fails
    the HARNESS and reports a network call that never happened — an instrument
    failure wearing the costume of a defect. `getaddrinfo` is the chokepoint every
    outbound request by hostname must pass and the loopback self-pipe does not.
    """
    monkeypatch.setattr(socket, "getaddrinfo", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    monkeypatch.setattr("httpx.HTTPTransport.handle_request", _refuse)
    monkeypatch.setattr("urllib.request.urlopen", _refuse)
    monkeypatch.setattr("scrapex.connectors.base.HttpFetcher.__init__", _refuse)


def test_the_route_makes_no_request(client, monkeypatch):
    """THE WIRE IS CUT. `--plan` costs ~114 requests and is ADVERTISED by this
    payload, never run — so the guard has to be able to catch a call rather than
    trust that none is written."""
    _cut_the_wire(monkeypatch)

    for key in (PRICE, DATASET, SITE):
        assert client.get(f"/api/dry/{key}").status_code == 200, key


def test_the_network_guard_would_catch_the_pass_it_advertises(client, monkeypatch):
    """NON-VACUITY, AND AGAINST THE REAL CALL. Three guards shipped here passing
    under their own defect. This runs the sizing request `--plan` would make, with
    the same wire cut, and requires it to be caught."""
    _cut_the_wire(monkeypatch)

    with pytest.raises(AssertionError, match="reached the network"):
        contractors.make_fetch(1.0)


# ---- zero writes, guarded ---------------------------------------------------

def _row_counts(conn: sqlite3.Connection) -> dict[str, int]:
    tables = [row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        " AND name NOT LIKE 'sqlite_%'")]
    return {name: conn.execute(f"SELECT COUNT(*) FROM \"{name}\"").fetchone()[0]
            for name in tables}


def test_not_one_row_moves(client, engine):
    """Every table in the warehouse, counted either side of all three requests."""
    registry, _ = engine
    conn = registry.engine.connect()
    try:
        before = _row_counts(conn)
    finally:
        conn.close()

    for key in (PRICE, DATASET, SITE):
        assert client.get(f"/api/dry/{key}").status_code == 200

    conn = registry.engine.connect()
    try:
        after = _row_counts(conn)
    finally:
        conn.close()
    moved = {name: (before[name], after[name])
             for name in before if before[name] != after[name]}
    assert not moved, f"the dry route wrote rows: {moved}"


def test_the_seal_is_live_so_a_write_on_the_route_would_raise(client, monkeypatch):
    """THE GUARD THAT MAKES 'zero writes' A CHECK AND NOT A PROMISE.

    `disown_impostors` DELETES when `dry_run=False`, so the destructive case is one
    wrong keyword away. Here the impostor step is replaced by one that tries an
    INSERT on the very connection the route opened: if `refuse_writes` were removed,
    this test would pass and the route would be writing."""
    def write_instead(conn, directory, *, dry_run=True):
        conn.execute("INSERT INTO dataset_sighting (dataset_key, external_id) "
                     "VALUES ('x','y')")
        return 0

    monkeypatch.setattr(dryrun.contractors, "disown_impostors", write_instead)
    with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
        client.get(f"/api/dry/{DATASET}")


@pytest.mark.parametrize("statement", [
    "INSERT INTO dataset_sighting (dataset_key, external_id) VALUES ('a','b')",
    "UPDATE dataset_sighting SET seen_count = 9",
    "DELETE FROM dataset_sighting",
    "DROP TABLE dataset_sighting",
    "CREATE TABLE sneaky (a TEXT)",
    "ALTER TABLE dataset_sighting ADD COLUMN sneaky TEXT",
    "REINDEX",
    "ANALYZE",
])
def test_refuse_writes_denies_every_shape_of_write(engine, statement):
    registry, _ = engine
    conn = registry.engine.connect()
    try:
        dryrun.refuse_writes(conn)
        with pytest.raises(sqlite3.DatabaseError, match="not authorized"):
            conn.execute(statement)
        # AND STILL READS, or the seal would be a closed door rather than a filter.
        assert conn.execute("SELECT COUNT(*) FROM dataset_sighting").fetchone()[0] >= 0
    finally:
        conn.close()


# ---- the passes are DERIVED, not retyped ------------------------------------

def test_the_directory_passes_are_the_command_line_s_own_flags():
    """Each declared pass is a real `--flag`, and no action flag is undeclared."""
    import argparse

    parser = argparse.ArgumentParser()
    contractors.add_arguments(parser)
    flags = {action.dest for action in parser._actions
             if isinstance(action, argparse._StoreTrueAction)}

    assert set(passes.DIRECTORY_PASSES) <= flags, (
        "a declared pass has no flag on `scrapex contractors`")
    # `--repair` is a MODIFIER of `--impostors`, not a pass of its own: it is the
    # only store_true flag that is not one.
    assert flags - set(passes.DIRECTORY_PASSES) == {"repair"}, (
        "a store_true flag exists that is neither a declared pass nor --repair; "
        "declare it in scrapex/passes.py or this menu goes stale silently")


def test_validate_reads_the_declaration_and_names_every_pass(capsys):
    """PROVES THE TUPLE IS THE ONE THE CLI GATES ON. If `validate` grew its own list
    the refusal would stop naming what `passes.py` declares."""
    import argparse

    parser = argparse.ArgumentParser()
    contractors.add_arguments(parser)
    with pytest.raises(SystemExit) as raised:
        contractors.validate(parser.parse_args([]))

    assert raised.value.code == 2
    message = capsys.readouterr().err
    for name in passes.DIRECTORY_PASSES:
        assert f"--{name}" in message


def test_the_price_passes_are_exactly_the_run_modes(client):
    body = client.get(f"/api/dry/{PRICE}").json()

    assert [one["key"] for one in body["passes"]] == [one.value for one in RunMode], (
        "POST /api/jobs accepts RunMode; a pass list that is not RunMode is retyped")


def test_the_price_writes_are_exactly_what_ingest_writes():
    """Read off `scrapex/ingest.py`, so a new table it learns to write goes red here
    instead of being missing from a hover that promises what a run costs."""
    import re

    source = (ROOT / "scrapex" / "ingest.py").read_text(encoding="utf-8")
    written = set(re.findall(r"INSERT (?:OR [A-Z]+ )?INTO ([a-z_]+)", source))
    written |= set(re.findall(r"UPDATE ([a-z_]+) SET", source))

    declared = set(passes._INGEST_WRITES)
    assert declared == written, (
        f"ingest.py writes {sorted(written - declared)} that no pass declares, and "
        f"the declaration claims {sorted(declared - written)} it does not")


def test_every_table_a_pass_claims_to_write_exists():
    """A renamed table would otherwise leave a hover naming a table that is gone."""
    schema = (ROOT / "db" / "engine" / "schema.sql").read_text(encoding="utf-8")
    for folder in ("db/engine/migrations", "db/migrations"):
        for path in sorted((ROOT / folder).glob("*.sql")):
            schema += path.read_text(encoding="utf-8")

    claimed = {name for one in (*passes._DIRECTORY.values(), *passes._PRICE.values())
               for name in one.writes}
    assert claimed, "no pass declares a write; the field has stopped being filled"
    for name in sorted(claimed):
        assert f"TABLE {name} " in schema or f"TABLE IF NOT EXISTS {name} " in schema, (
            f"a pass says it writes {name!r} and no schema file creates it")


# ---- the hover: his explicit instruction ------------------------------------

def test_every_hover_says_what_it_does_what_it_writes_and_what_it_costs():
    every = [*passes.directory_passes(
                 contractors.get_directory(SITE), scope=CrawlScope.FULL_THEN_LISTING),
             *passes._PRICE.values()]
    for one in every:
        assert one.does in one.hover, one.key
        assert one.network_phrase in one.hover, one.key
        if one.writes:
            for name in one.writes:
                assert name in one.hover, f"{one.key} hides that it writes {name}"
        else:
            assert "writes nothing" in one.hover, one.key


def test_the_route_serves_the_declared_hover_verbatim(client):
    """ONE PLACE. If the route composed its own sentence there would be two.

    BOTH KINDS, and that is not symmetry for its own sake: the first version of this
    test checked the dataset payload only, and a mutation that replaced the PRICE
    hover with the label passed it — the guard held for one of the two halves it
    was written for.
    """
    entry = load_manifest(MANIFEST_FILE).get(PRICE)
    expected = {
        DATASET: {one.key: one for one in passes.directory_passes(
            contractors.get_directory(SITE), scope=CrawlScope.LISTING_ONLY)},
        PRICE: {one.key: one for one in passes.price_passes(entry,
                                                           last_requests=812)},
    }
    for key, declared in expected.items():
        for served in client.get(f"/api/dry/{key}").json()["passes"]:
            assert served["hover"] == declared[served["key"]].hover, key
            assert served["writes"] == list(declared[served["key"]].writes), key


def test_the_panel_does_not_retype_a_single_hover_string():
    """THE DRIFT THIS FEATURE EXISTS TO END. `extension/app.js` carried its own list
    of what a source can do and five of its six actions 404'd (`REQ-45`). A retyped
    sentence goes stale in the safe-looking direction — `LESSONS` §15."""
    surfaces = [*(ROOT / "extension").rglob("*.js"),
                *(ROOT / "scrapex" / "webui" / "static").rglob("*.js"),
                *(ROOT / "scrapex" / "webui" / "templates").rglob("*.html")]
    text = "\n".join(path.read_text(encoding="utf-8", errors="ignore")
                     for path in surfaces)

    for one in (*passes._DIRECTORY.values(), *passes._PRICE.values()):
        assert one.does not in text, (
            f"{one.key}'s description is retyped in a panel or page file; read it "
            "from GET /api/dry/{source_key} instead")
        assert one.network_phrase not in text, f"{one.key}'s cost is retyped"


# ---- the scope is visible, and the setter is deliberately not built ---------

def test_a_dataset_payload_shows_the_scope_and_the_refusal_it_causes(client):
    body = client.get(f"/api/dry/{DATASET}").json()
    scope = body["scope"]

    assert scope["value"] == CrawlScope.LISTING_ONLY.value
    assert scope["values"] == [one.value for one in CrawlScope]
    assert scope["settable_here"] is False
    assert "database" in scope["note"]

    details = next(one for one in body["passes"] if one["key"] == "details")
    assert details["blocked_by"] and "listing_only" in details["blocked_by"], (
        "the scope refuses --details and the payload does not say so")
    assert "change the scope" in details["blocked_by"]


def test_the_refusal_lifts_when_the_scope_asks_for_profiles(client, engine):
    """NON-VACUITY FOR THE BLOCK. A `blocked_by` that is always set says nothing."""
    registry, _ = engine
    conn = registry.engine.connect()
    try:
        conn.execute("UPDATE site_profile SET crawl_scope = ? WHERE site_key = ?",
                     (CrawlScope.FULL_THEN_LISTING.value, SITE))
        conn.commit()
        body = client.get(f"/api/dry/{DATASET}").json()
        details = next(one for one in body["passes"] if one["key"] == "details")
        assert details["blocked_by"] is None
        assert body["scope"]["value"] == CrawlScope.FULL_THEN_LISTING.value
    finally:
        conn.execute("UPDATE site_profile SET crawl_scope = ? WHERE site_key = ?",
                     (CrawlScope.LISTING_ONLY.value, SITE))
        conn.commit()
        conn.close()


def test_plan_is_advertised_with_its_cost_and_derived_from_the_partition(client):
    """~114 IS DERIVED, NOT CARRIED. `size_cell` costs at most 2 requests, so the
    ceiling is 2 x (cells + 1) — 114 over muqawil's 56 cells."""
    body = client.get(f"/api/dry/{DATASET}").json()
    plan = next(one for one in body["passes"] if one["key"] == "plan")
    cells = len(contractors.get_directory(SITE).partition().cells())

    assert plan["network"] == 2 * (cells + 1)
    assert plan["writes"] == [], (
        "plan() returns before open_engine(), so it cannot write even on error")
    assert body["network_requests"] == 0, (
        "the ROUTE advertises plan's cost and must not pay it")


# ---- the payload calls sightings rather than reimplementing it --------------

def test_coverage_comes_from_the_sightings_module(client, monkeypatch):
    """The audit's own finding was `dataset_table_payload` reimplementing
    `fields.hidden_columns` inline. If this payload grew its own SQL the sentinel
    below would never appear."""
    calls: list[str] = []

    real = dryrun.coverage

    def spy(conn, dataset_key):
        calls.append(dataset_key)
        return real(conn, dataset_key)

    monkeypatch.setattr(dryrun, "coverage", spy)
    body = client.get(f"/api/dry/{DATASET}").json()

    assert calls == [DATASET]
    assert body["coverage"][0]["sentence"].startswith(DATASET)
    assert body["coverage"][0]["missing"] >= 1, (
        f"{NEVER_STORED} was sighted and never stored; coverage says nothing is "
        "missing, so the block is vacuous")


def test_the_route_and_the_cli_share_one_departure_window(client, engine):
    """`contractors.default_window` — the same function `--coverage` uses. Two copies
    of `MAX(last_seen_at)` is how a route and a printer come to disagree."""
    registry, _ = engine
    conn = registry.engine.connect()
    try:
        expected = contractors.default_window(conn, DATASET)
    finally:
        conn.close()
    block = client.get(f"/api/dry/{DATASET}").json()["coverage"][0]

    assert expected, "the ledger has no sightings, so this asserts nothing"
    assert block["departures"]["not_seen_since"] == expected
    assert len(block["missing_sample"]) <= contractors.COVERAGE_SAMPLE


def test_the_impostor_check_runs_dry_and_says_which_dataset(client):
    body = client.get(f"/api/dry/{SITE}").json()

    assert body["impostors"]["dry_run"] is True
    assert body["impostors"]["dataset_key"] == "contractor_profiles"


def test_a_generic_run_does_not_claim_it_finished(client):
    """`R-52` ruled a generic crawl-run table and it is not built, so `partial` is
    NULL with its basis named — `R-55`: absence beats a placeholder."""
    body = client.get(f"/api/dry/{DATASET}").json()

    assert body["last_run"]["partial"] is None
    assert "R-52" in body["last_run"]["partial_basis"]
    assert body["last_run"]["run_ref"] == "listing-test"


def test_a_price_run_does_state_whether_it_was_partial(client):
    """The other side: `crawl_run.status` is a real column, so this is not NULL."""
    body = client.get(f"/api/dry/{PRICE}").json()

    assert body["last_run"]["partial"] is False
    assert body["last_run"]["partial_basis"] == "crawl_run.status"
    assert body["last_run"]["requests"] == 812
    assert all(one["network"] == 812 for one in body["passes"]), (
        "a price pass must cost this source's own measured requests, not a number "
        "borrowed from another shop")
