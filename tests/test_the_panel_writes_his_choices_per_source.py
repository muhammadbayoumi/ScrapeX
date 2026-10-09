"""The panel writes his per-source choices to the warehouse, for every source (#1584, PR 3).

His rulings: one system -- general rules, overridden per source; clearing a choice
returns the field to what the source ships with; and the panel shows where each value
comes from: `source` (its `sources.yaml` entry, or `directories.py` for a directory),
`general` (the Settings page) or `choice` (his, in `source_setting`). This holds the
engine's half on the real schema:

    GET  /api/sources/{key}/rules     each field's value, origin and shipped value
    POST /api/sources/{key}/rules     a partial save; null clears; 400 with the sentence
    POST /api/sources/{key}/active    the Auto switch, into the warehouse
    POST /api/sources/{key}/edit      contract fields only; the five are refused by name
    GET  /api/sources/{key}/robots    for a directory too

and that NONE of these writes moves a byte of `sources.yaml` (#1583: the packaged engine
deletes that file at exit, so a choice written there did not survive a restart).
"""
from __future__ import annotations

import sqlite3
import threading

import httpx
import pytest
import yaml
from fastapi.testclient import TestClient

from scrapex import db as dbmod
from scrapex import sourceboard
from scrapex.databases.domain import EngineDatabase
from scrapex.webui.app import create_app

#: Ships an opinion on robots and pace, and nothing on the agent.
SHOP = "SHOP_A"
#: Ships an agent of its own (as Zid shops do), and is switched on.
ZIDDY = "ZIDDY_B"
#: In the code's directory registry, not in the manifest.
DIRECTORY = "muqawil_org"


def _entry(key: str, **fields) -> dict:
    return {"source_key": key, "source_name": key.title(), "base_url": "https://shop.test",
            "family": "custom-json-api", "currency": "SAR",
            "extract": [{"kind": "product_prices"}], **fields}


class _ShippedShape(yaml.SafeDumper):
    """Indents a list under its key, as `sources.yaml` does."""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def _warehouse_and_manifest(tmp_path, entries: list[dict]):
    """A warehouse on the real schema and a manifest of these entries, not yet served."""
    database = tmp_path / "scrapex-engine.db"
    EngineDatabase(database).initialize()
    manifest = tmp_path / "sources.yaml"
    # Shaped as the shipped file is -- `  - source_key:` opening each block, keys in the
    # order written -- because the manifest editor finds a source's block by that line.
    manifest.write_text(yaml.dump({"sources": entries}, Dumper=_ShippedShape,
                                  sort_keys=False), encoding="utf-8")
    return database, manifest


@pytest.fixture()
def engine(tmp_path):
    """A warehouse with NO `source_site` rows -- every source here is one he has
    never crawled -- and a manifest of its own, whose bytes the tests compare."""
    database, manifest = _warehouse_and_manifest(tmp_path, [
        _entry(SHOP, robots="obey", crawl_pace_s=3.0),
        _entry(ZIDDY, active=True, user_agent="ShippedAgent/1.0"),
    ])
    client = TestClient(create_app(db_path=str(database), manifest_path=str(manifest)))
    return client, database, manifest


def _fields(client, key: str) -> dict:
    answer = client.get(f"/api/sources/{key}/rules")
    assert answer.status_code == 200, answer.text
    return answer.json()["fields"]


def _lifecycle(database, key: str) -> str | None:
    with sqlite3.connect(database) as conn:
        row = conn.execute("SELECT lifecycle FROM source_site WHERE source_key = ?",
                           (key,)).fetchone()
    return None if row is None else row[0]


# ---- read: every field, with where it comes from ----------------------------------------

def test_a_price_source_reads_with_each_fields_origin(engine):
    client, _, _ = engine

    answer = client.get(f"/api/sources/{SHOP}/rules").json()
    fields = answer["fields"]

    assert answer["kind"] == "price"
    assert (fields["robots"]["value"], fields["robots"]["origin"]) == ("obey", "source")
    assert (fields["crawl_pace_s"]["value"], fields["crawl_pace_s"]["origin"]) == (3.0, "source")
    assert (fields["user_agent"]["value"], fields["user_agent"]["origin"]) == (None, "general")
    assert (fields["active"]["value"], fields["active"]["origin"]) == (False, "source")
    assert answer["general"]["crawl_pace_s"] == 1.0
    assert answer["agent_sent"] == answer["general"]["user_agent"], (
        "a source with no agent of its own is fetched as his general rule says")


def test_a_shipped_agent_reads_as_the_sources_and_is_the_one_sent(engine):
    client, _, _ = engine

    answer = client.get(f"/api/sources/{ZIDDY}/rules").json()

    assert answer["fields"]["user_agent"] == {
        "value": "ShippedAgent/1.0", "shipped": "ShippedAgent/1.0", "origin": "source"}
    assert answer["agent_sent"] == "ShippedAgent/1.0"


def test_a_directory_reads_too(engine):
    """A directory ships `active` and nothing else (`directories.Directory`)."""
    client, _, _ = engine

    answer = client.get(f"/api/sources/{DIRECTORY}/rules").json()

    assert answer["kind"] == "directory"
    assert answer["fields"]["active"]["origin"] == "source"
    assert answer["fields"]["robots"] == {
        "value": "default", "custom": None, "shipped": "default", "shipped_custom": None,
        "origin": "general"}
    assert answer["fields"]["crawl_pace_s"]["origin"] == "general"


def test_a_key_the_build_does_not_crawl_is_404(engine):
    client, _, _ = engine

    assert client.get("/api/sources/NOBODY/rules").status_code == 404
    assert client.post("/api/sources/NOBODY/rules", json={"active": True}).status_code == 404


# ---- write: into the warehouse, never the file ------------------------------------------

def test_a_never_crawled_price_source_takes_a_choice_and_the_file_does_not_move(engine):
    """No `source_site` row yet: the write registers it, as the first crawl would."""
    client, database, manifest = engine
    before = manifest.read_bytes()

    answer = client.post(f"/api/sources/{SHOP}/rules", json={
        "user_agent": "HisAgent/2.0", "crawl_pace_s": 7.5, "robots": "custom",
        "robots_custom": {"enforce_disallow": True, "crawl_delay_s": 2}})

    assert answer.status_code == 200, answer.text
    fields = answer.json()["fields"]
    assert (fields["user_agent"]["value"], fields["user_agent"]["origin"]) == (
        "HisAgent/2.0", "choice")
    assert (fields["crawl_pace_s"]["value"], fields["crawl_pace_s"]["origin"]) == (7.5, "choice")
    assert fields["robots"]["custom"] == {"enforce_disallow": True, "crawl_delay_s": 2.0}
    assert answer.json()["agent_sent"] == "HisAgent/2.0"
    assert _lifecycle(database, SHOP) is not None, "the source was not registered"
    assert manifest.read_bytes() == before, "a per-source choice was written to sources.yaml"


def test_a_never_crawled_directory_takes_a_choice(engine):
    client, database, manifest = engine
    before = manifest.read_bytes()

    answer = client.post(f"/api/sources/{DIRECTORY}/rules",
                         json={"robots": "obey", "crawl_pace_s": 5})

    assert answer.status_code == 200, answer.text
    assert answer.json()["fields"]["robots"]["origin"] == "choice"
    assert _lifecycle(database, DIRECTORY) == "active", (
        "registered and put in step with what it ships: a built directory is on")
    assert manifest.read_bytes() == before


def test_clearing_returns_a_field_to_what_the_source_ships(engine):
    """His ruling: clearing returns to the SHIPPED value -- not to nothing."""
    client, _, _ = engine
    client.post(f"/api/sources/{SHOP}/rules", json={"robots": "default", "crawl_pace_s": 9})

    cleared = client.post(f"/api/sources/{SHOP}/rules",
                          json={"robots": None, "crawl_pace_s": None}).json()["fields"]

    assert (cleared["robots"]["value"], cleared["robots"]["origin"]) == ("obey", "source")
    assert (cleared["crawl_pace_s"]["value"], cleared["crawl_pace_s"]["origin"]) == (3.0, "source")


def test_clearing_a_field_the_source_ships_nothing_for_returns_it_to_the_general_rule(engine):
    client, _, _ = engine
    client.post(f"/api/sources/{SHOP}/rules", json={"user_agent": "HisAgent/2.0"})

    answer = client.post(f"/api/sources/{SHOP}/rules", json={"user_agent": None}).json()

    assert answer["fields"]["user_agent"]["origin"] == "general"
    assert answer["agent_sent"] == answer["general"]["user_agent"]


def test_a_partial_write_keeps_the_choices_it_does_not_name(engine):
    client, _, _ = engine
    client.post(f"/api/sources/{SHOP}/rules", json={"user_agent": "HisAgent/2.0"})

    fields = client.post(f"/api/sources/{SHOP}/rules", json={"crawl_pace_s": 4}).json()["fields"]

    assert fields["user_agent"]["origin"] == "choice"


@pytest.mark.parametrize(("body", "says"), [
    pytest.param({"robots": "Obey"}, "robots must be one of", id="misspelt-choice"),
    pytest.param({"crawl_pace_s": "5"}, "crawl_pace_s must be a number of seconds",
                 id="pace-as-text"),
    pytest.param({"robots": "custom",
                  "robots_custom": {"enforce_disallow": False, "crawl_delay_s": "3"}},
                 "crawl_delay_s must be a number of seconds", id="custom-delay-as-text"),
    pytest.param({"user_agent": "A\nB"}, "printable ASCII", id="agent-two-lines"),
    pytest.param({"colour": "red"}, "not per-source choices", id="unknown-field"),
])
def test_a_refused_write_says_why_and_stores_nothing(engine, body, says):
    """The shared checker's sentence, as `SourceEntry` gives it -- and not even the
    registry row the write would have made."""
    client, database, manifest = engine
    before = manifest.read_bytes()

    answer = client.post(f"/api/sources/{SHOP}/rules", json=body)

    assert answer.status_code == 400, answer.text
    assert says in answer.json()["detail"]
    assert _lifecycle(database, SHOP) is None
    assert manifest.read_bytes() == before


def test_a_body_that_is_not_an_object_is_refused(engine):
    client, _, _ = engine

    answer = client.post(f"/api/sources/{SHOP}/rules", json=["active", True])

    assert answer.status_code in (400, 422)


# ---- the Auto switch, and every page that says on or off -------------------------------

def test_the_auto_switch_writes_the_warehouse_and_every_page_says_so(engine):
    client, database, manifest = engine
    before = manifest.read_bytes()

    answer = client.post(f"/api/sources/{SHOP}/active", json={"active": True})

    assert answer.status_code == 200 and answer.json()["active"] is True
    assert manifest.read_bytes() == before
    assert _lifecycle(database, SHOP) == "active", "lifecycle is not in step with his switch"
    assert _fields(client, SHOP)["active"] == {"value": True, "shipped": False,
                                               "origin": "choice"}
    listed = {s["source_key"]: s for s in client.get("/api/sources").json()["sources"]}
    assert listed[SHOP]["active"] is True
    conn = EngineDatabase(database).connect()
    try:
        board = {one.key: one.state for one in sourceboard.board(
            conn, manifest_file=manifest)}
    finally:
        conn.close()
    assert board[SHOP] == "active"
    assert "Auto is off" not in _schedule_card(client, SHOP), (
        "the schedules page still says his switched-on source will not fire")


def _schedule_card(client, key: str) -> str:
    page = client.get("/schedules").text
    start = page.index(f'data-sched="{key}"')
    return page[start:page.index("</form>", start)]


def test_the_schedules_page_says_a_shipped_on_source_he_switched_off_will_not_fire(engine):
    client, _, _ = engine
    assert "Auto is off" not in _schedule_card(client, ZIDDY), "fixture: ZIDDY ships on"

    client.post(f"/api/sources/{ZIDDY}/active", json={"active": False})

    assert "Auto is off" in _schedule_card(client, ZIDDY)


def test_lifecycle_follows_what_the_engines_own_manifest_ships(engine):
    """`reconcile_active` read the repository's `sources.yaml` whatever manifest the
    engine had loaded. ZIDDY is in this engine's manifest only, and ships on: a write
    that registers it must leave its record saying so."""
    client, database, _ = engine

    client.post(f"/api/sources/{ZIDDY}/rules", json={"crawl_pace_s": 4})

    assert _lifecycle(database, ZIDDY) == "active"


def test_switching_off_a_source_that_ships_on_is_his_and_is_said(engine):
    client, database, _ = engine

    client.post(f"/api/sources/{ZIDDY}/active", json={"active": False})

    # Registered by this write, so `draft` -- which `reconcile_active` reads as off and
    # leaves alone -- and never `active`.
    assert _lifecycle(database, ZIDDY) != "active"
    listed = {s["source_key"]: s for s in client.get("/api/sources").json()["sources"]}
    assert listed[ZIDDY]["active"] is False
    manage = client.get("/manage").text
    row = manage[manage.index(ZIDDY):][:1500]
    assert "Inactive" in row.split("</tr>")[0]


def test_the_auto_switch_refuses_what_is_not_a_switch(engine):
    client, _, _ = engine

    answer = client.post(f"/api/sources/{SHOP}/active", json={"active": "yes"})

    assert answer.status_code == 400
    assert "true or false" in answer.json()["detail"]


# ---- /edit keeps the contract fields, and only those ------------------------------------

@pytest.mark.parametrize("field", ["robots", "robots_custom", "user_agent", "crawl_pace_s",
                                   "active"])
def test_the_manifest_editor_refuses_his_per_source_choices_by_name(engine, field):
    """ONE WRITER PER FIELD. A request that wrote some fields to the file and others to
    the warehouse would succeed halfway when either refused; the refusal names the
    route that saves them instead."""
    client, _, manifest = engine
    before = manifest.read_bytes()

    answer = client.post(f"/api/sources/{SHOP}/edit",
                         json={"source_name": "Renamed", field: None})

    assert answer.status_code == 400
    assert field in answer.json()["detail"]
    assert f"/api/sources/{SHOP}/rules" in answer.json()["detail"]
    assert manifest.read_bytes() == before, "half of a refused edit was written"


def test_the_manifest_editor_still_edits_the_contract(engine):
    client, _, manifest = engine

    answer = client.post(f"/api/sources/{SHOP}/edit", json={"source_name": "Renamed Shop"})

    assert answer.status_code == 200, answer.text
    assert "Renamed Shop" in manifest.read_text(encoding="utf-8")


# ---- robots, for a directory too --------------------------------------------------------

def test_the_robots_screen_reads_a_directory_with_his_choice(engine, monkeypatch):
    """It answered 404 for muqawil_org and the Oman register, whose crawls read
    robots.txt like any other."""
    client, _, _ = engine
    client.post(f"/api/sources/{DIRECTORY}/rules", json={
        "robots": "custom", "robots_custom": {"enforce_disallow": True, "crawl_delay_s": 4}})
    seen = []
    real_client = httpx.Client

    def site(*args, **kwargs):
        def answer(request):
            seen.append(str(request.url))
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
        kwargs["transport"] = httpx.MockTransport(answer)
        return real_client(*args, **kwargs)
    monkeypatch.setattr(httpx, "Client", site)
    answer = client.get(f"/api/sources/{DIRECTORY}/robots")
    monkeypatch.setattr(httpx, "Client", real_client)

    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["choice"] == "custom"
    assert body["custom"] == {"enforce_disallow": True, "crawl_delay_s": 4.0}
    assert body["on_a_disallowed_path"]["may_fetch"] is False
    assert seen and seen[0].startswith("https://muqawil.org/robots.txt")


def test_a_directory_card_carries_no_automation_switch(engine):
    """Nothing schedules a directory yet; his ruling (2026-10-09) is that the panel draws
    no automation switch for it until that is built, so the card carries no `active` --
    while its rules still answer, `active` among them, for when it is."""
    client, _, _ = engine
    listed = {s["source_key"]: s for s in client.get("/api/sources").json()["sources"]}

    assert listed[DIRECTORY]["kind"] == "directory"
    assert "active" not in listed[DIRECTORY]
    assert "active" in listed[SHOP], "a price source keeps its switch"


# ---- adding a source writes no choice of his (#1584) ------------------------------------

def _new_source(**fields) -> dict:
    return {"source_key": "NEW_SHOP", "source_name": "New", "base_url": "https://new.test",
            "family": "custom-json-api", "currency": "SAR", "kind": "product_prices",
            "scope": "census", **fields}


@pytest.mark.parametrize("field, value", [
    ("active", True), ("active", "false"), ("active", None), ("robots", "obey"),
    ("robots_custom", {"enforce_disallow": True, "crawl_delay_s": 2}),
    ("user_agent", "Mine/1.0"), ("crawl_pace_s", 4.0),
])
def test_adding_a_source_refuses_his_per_source_choices_by_name(engine, field, value):
    """The same one writer per field as /edit: they are chosen in the editor, into the
    warehouse. Only `active` exactly false passes -- not "false", not null."""
    client, database, manifest = engine
    before = manifest.read_bytes()

    answer = client.post("/api/sources", json=_new_source(**{field: value}))

    assert answer.status_code == 400, answer.text
    assert field in answer.json()["detail"]
    assert manifest.read_bytes() == before, "a refused add wrote the manifest"
    assert _lifecycle(database, "NEW_SHOP") is None


@pytest.mark.parametrize("extra", [{"active": False}, {}])
def test_adding_a_source_off_or_saying_nothing_is_added_off(engine, extra):
    """`active: false` is what the panel's add form sends; saying nothing is the same."""
    client, _, manifest = engine

    answer = client.post("/api/sources", json=_new_source(**extra))

    assert answer.status_code == 200, answer.text
    shipped = yaml.safe_load(manifest.read_text(encoding="utf-8"))["sources"]
    assert [entry.get("active", False) for entry in shipped
            if entry["source_key"] == "NEW_SHOP"] == [False]
    assert _fields(client, "NEW_SHOP")["active"] == {
        "value": False, "shipped": False, "origin": "source"}


def test_the_manage_page_offers_no_switch_when_adding(engine):
    """Its "Active now" box sent `active`, which adding refuses; the editor sets it."""
    client, _, _ = engine

    page = client.get("/manage")

    assert page.status_code == 200
    assert 'name="active"' not in page.text
    assert "Active now" not in page.text


# ---- one writer: a crawl holding the lock makes a choice wait, never half-write ---------

@pytest.mark.parametrize("route, body", [
    ("rules", {"crawl_pace_s": 5}), ("active", {"active": True}),
])
def test_a_choice_made_while_a_crawl_writes_is_refused_and_stores_nothing(
        engine, monkeypatch, route, body):
    client, database, manifest = engine
    held, release = threading.Event(), threading.Event()
    real_lock = dbmod.write_lock

    def crawl():
        with real_lock(str(database)):
            held.set()
            release.wait(30)

    # The engine waits half a second, not the ten it gives a real crawl to finish.
    monkeypatch.setattr(dbmod, "write_lock",
                        lambda path, timeout_s=0.5: real_lock(path, timeout_s=0.5))
    holder = threading.Thread(target=crawl)
    holder.start()
    assert held.wait(10)
    try:
        answer = client.post(f"/api/sources/{SHOP}/{route}", json=body)
    finally:
        release.set()
        holder.join()

    assert answer.status_code == 409, answer.text
    with sqlite3.connect(database) as conn:
        assert conn.execute("SELECT COUNT(*) FROM source_setting").fetchone()[0] == 0
    assert _lifecycle(database, SHOP) is None
    assert _fields(client, SHOP)["crawl_pace_s"]["origin"] == "source"
    assert _fields(client, SHOP)["active"]["origin"] == "source"


# ---- startup brings lifecycle in line with what the engine's manifest ships -------------

def test_startup_switches_on_a_registered_source_its_manifest_ships_on(tmp_path):
    """A row registered as `draft` before this engine started, for a source its own
    manifest ships `active: true`: the engine reconciles at startup, not at first save."""
    database, manifest = _warehouse_and_manifest(tmp_path, [_entry(ZIDDY, active=True)])
    with sqlite3.connect(database) as conn:
        conn.execute("INSERT INTO source_site (source_key, lifecycle) VALUES (?, 'draft')",
                     (ZIDDY,))

    TestClient(create_app(db_path=str(database), manifest_path=str(manifest)))

    assert _lifecycle(database, ZIDDY) == "active"


# ---- what clearing returns to, and the general rule, are answered as stored ------------

def test_the_shipped_values_and_the_general_rule_are_answered_beside_his_choice(tmp_path):
    """Under his choice the answer still carries what the source ships -- the custom
    rule included -- since that is what Clear returns to and what the panel says."""
    database, manifest = _warehouse_and_manifest(tmp_path, [_entry(
        SHOP, robots="custom", robots_custom={"enforce_disallow": True, "crawl_delay_s": 2},
        crawl_pace_s=3.0)])
    client = TestClient(create_app(db_path=str(database), manifest_path=str(manifest)))
    assert client.post("/api/settings", json={"crawl_obey_disallow": 1}).status_code == 200

    answer = client.post(f"/api/sources/{SHOP}/rules",
                         json={"robots": "obey", "crawl_pace_s": 9}).json()

    assert answer["general"]["obey_disallow"] is True
    pace, robots = answer["fields"]["crawl_pace_s"], answer["fields"]["robots"]
    assert (pace["value"], pace["shipped"], pace["origin"]) == (9.0, 3.0, "choice")
    assert (robots["value"], robots["shipped"], robots["origin"]) == ("obey", "custom", "choice")
    assert robots["shipped_custom"] == {"enforce_disallow": True, "crawl_delay_s": 2.0}
    assert client.get(f"/api/sources/{SHOP}/rules").json() == {
        key: value for key, value in answer.items() if key != "warehouse_updated"}
