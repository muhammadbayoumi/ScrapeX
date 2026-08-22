"""Every action a dataset card offers is CALLED here, against a real dataset.

WHY THIS FILE EXISTS. `sourceMenu` used to answer the question "what can be done
to a generic dataset?" with `return ""` — no menu at all — and its comment gave a
reason that was true of five of the six entries: they post to routes that read the
manifest, and a dataset is not in it. The sixth, `Open the data table`, was BUILT
AFTER that blanket hide and works perfectly on a dataset. Nothing noticed for ten
days. The owner did: «ال 3 نقاط لا تظهر فى كارد مقاول».

A hand-written rule about somebody else's routing rots exactly like that. So the
panel now declares, per action, the ENGINE ROUTE it drives and a PROOF of what
that route does with a dataset key — and this file turns each declaration into a
request. Both directions are checked, which is the part that matters:

  * an action the panel OFFERS on a dataset must answer 2xx and carry content;
  * an action it WITHHOLDS must be proven unable — either the route refuses the
    key, or the page it opens has nothing of what the action promises.

So the day `/api/export/{key}` learns to resolve a dataset, this goes red until
the menu says so. That is the whole point: the engine's behaviour decides, and the
panel's list is a mirror that cannot silently stop matching.

WHAT THIS FILE DOES NOT COVER, so it is not looked for here: whether the menu
RENDERS those actions is a DOM fact, asserted in `tests/test_panel_dom.py`
(`test_a_dataset_card_offers_only_the_actions_that_work`), and whether the page
`table` opens can draw a dataset is asserted in `tests/test_tab_page_dom.py`.
Three surfaces, three files, one declaration between them.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scrapex.config import MANIFEST_FILE
from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.extract import service
from scrapex.extract.models import ApprovalField, CandidateApproval, SnapshotCreate
from scrapex.extract.muqawil import listing_candidate
from scrapex.webui.app import create_app

# Guards the extension: this file reads extension/ sources, so a change to the
# menu must run it. See tests/test_the_extension_gate_is_complete.py.
pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
APP_JS = ROOT / "extension" / "app.js"
LISTING = (ROOT / "tests" / "fixtures" / "muqawil" / "listing-en.html").read_text(
    encoding="utf-8")

#: The dataset every request below is made against.
KEY = "contractors"

#: The three proofs `app.js` may declare, and what each one MEANS as a request.
#: A fourth would have to be added here before it could be used there, which is
#: deliberate: the set of ways an action can be justified is not open-ended.
RESOLVES = "resolves-a-dataset-key"
REFUSES = "route-404-for-a-dataset-key"
NO_SECTION = "no-such-section-on-the-page"
PROOFS = {RESOLVES, REFUSES, NO_SECTION}

#: How to make each action's request. The `route` here is compared to the one
#: `app.js` declares, so a recipe cannot quietly test a different endpoint from
#: the one the panel drives — and an action with no recipe fails collection
#: rather than passing unmeasured.
RECIPES = {
    "update": ("POST /api/jobs", "post", "/api/jobs",
               {"source_keys": [KEY], "run_mode": "current"}),
    "table": ("GET /api/table/{key}", "get", f"/api/table/{KEY}", None),
    "changes": ("GET /source/{key}", "get", f"/source/{KEY}", None),
    "settings": ("GET /sources/{key}", "get", f"/sources/{KEY}", None),
    "pause": ("POST /api/sources/{key}/active", "post",
              f"/api/sources/{KEY}/active", {"active": False}),
    "sheet": ("GET /api/export/{key}", "get", f"/api/export/{KEY}", None),
}


def declared_actions() -> list[dict]:
    """`SOURCE_ACTIONS`, read out of the shipped file rather than restated here."""
    source = APP_JS.read_text(encoding="utf-8")
    start = source.index("const SOURCE_ACTIONS = [")
    end = source.index("\n];", start)
    body = source[start:end]
    entries = []
    for chunk in body.split("{action:")[1:]:
        name = re.match(r'\s*"([a-z]+)"', chunk)
        route = re.search(r'route:\s*"([^"]+)"', chunk)
        proof = re.search(r"proof:\s*([A-Z_]+)", chunk)
        entries.append({
            "action": name.group(1) if name else None,
            "route": route.group(1) if route else None,
            # The constant's NAME, resolved to its value below: a bare
            # "MANIFEST_ONLY" says nothing about what was measured.
            "proof": proof.group(1) if proof else None,
        })
    return entries


def proof_values() -> dict[str, str]:
    """The three `const` lines, so the test compares values and not spellings."""
    source = APP_JS.read_text(encoding="utf-8")
    return dict(re.findall(
        r"^const (RESOLVES_A_DATASET|MANIFEST_ONLY|NO_SECTION) = \"([^\"]+)\";",
        source, re.MULTILINE))


@pytest.fixture(scope="module")
def client(tmp_path_factory) -> TestClient:
    """An engine holding ONE APPROVED DATASET and no price rows.

    Module-scoped: approving the listing is the slow part and no test here
    writes, so one warehouse serves them all.
    """
    tmp = tmp_path_factory.mktemp("dataset-actions")
    registry = DatabaseRegistry(EngineDatabase(tmp / "scrapex-engine.db"),
                               pointer_file=tmp / "databases.json")
    registry.initialize()
    conn = registry.engine.connect()
    try:
        snapshot = service.save_snapshot(conn, SnapshotCreate(
            source_url="https://muqawil.org/en/contractors?page=1",
            html_content=LISTING))
        candidate = listing_candidate(LISTING)
        service.approve_candidate(
            conn, int(snapshot["page_snapshot_id"]),
            CandidateApproval(
                table_index=0, site_key="muqawil_org", site_display_name="SCA",
                dataset_key=KEY, dataset_name="Contractors",
                fields=[ApprovalField(field_key=f.field_key,
                                      display_name=f.source_name,
                                      data_type="text",
                                      identity=(f.field_key == "contractor_id"))
                        for f in candidate.fields]),
            candidate=candidate)
        conn.commit()
    finally:
        conn.close()
    # A COPY of the manifest, so no test can edit the real one.
    manifest = tmp / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(databases=registry, manifest_path=manifest))


def call(client: TestClient, action: str):
    _, method, path, body = RECIPES[action]
    return client.post(path, json=body) if method == "post" else client.get(path)


# ---- the premise ------------------------------------------------------------

def test_the_engine_really_is_serving_a_dataset(client):
    """WITHOUT THIS EVERY ASSERTION BELOW IS VACUOUS. A warehouse with no dataset
    in it answers 404 to all six routes, and the file would report that the five
    refusals are proven while proving nothing at all."""
    rows = client.get("/api/sources").json()["sources"]
    datasets = [row for row in rows if row.get("kind") == "dataset"]

    assert [row["source_key"] for row in datasets] == [KEY]
    assert datasets[0]["observations"] > 0, "the dataset has no rows to serve"


# ---- the declarations are complete and legible ------------------------------

def test_every_action_declares_a_route_and_a_proof():
    for entry in declared_actions():
        assert entry["route"], f"{entry['action']} declares no route"
        assert entry["proof"], f"{entry['action']} declares no proof"


def test_every_proof_is_one_of_the_three_and_they_say_what_they_mean():
    values = proof_values()

    assert values == {"RESOLVES_A_DATASET": RESOLVES,
                      "MANIFEST_ONLY": REFUSES,
                      "NO_SECTION": NO_SECTION}, (
        "app.js and this file disagree about what a proof IS; the constants are "
        "the contract between them")
    for entry in declared_actions():
        assert values[entry["proof"]] in PROOFS


def test_every_action_has_a_recipe_and_the_routes_agree():
    """The join. A recipe testing a route the panel does not drive would report a
    healthy menu for an endpoint nobody opens."""
    declared = declared_actions()

    assert {entry["action"] for entry in declared} == set(RECIPES), (
        "an action was added or removed in app.js and this file was not told; "
        "add its request to RECIPES so it is measured rather than assumed")
    for entry in declared:
        assert entry["route"] == RECIPES[entry["action"]][0], (
            f"{entry['action']}: app.js drives {entry['route']!r} and this file "
            f"calls {RECIPES[entry['action']][0]!r}")


# ---- the measurements ------------------------------------------------------

def test_an_action_offered_on_a_dataset_answers_and_carries_content(client):
    """OFFERED ⇒ PROVEN. Not 2xx alone: a 200 holding nothing is the same dead
    end as a 404, one step later."""
    values = proof_values()
    offered = [entry for entry in declared_actions()
               if values[entry["proof"]] == RESOLVES]

    assert offered, "no action is offered on a dataset card; that was the defect"
    for entry in offered:
        response = call(client, entry["action"])
        assert response.status_code == 200, (
            f"{entry['action']} is offered on a dataset card and "
            f"{entry['route']} answered {response.status_code}")
        payload = response.json()
        assert payload["rows"], f"{entry['route']} answered 200 with no rows"
        assert payload["columns"], f"{entry['route']} answered 200 with no columns"


def test_an_action_withheld_for_its_route_really_is_refused(client):
    """WITHHELD ⇒ PROVEN TOO, so the menu cannot hide an action that works."""
    values = proof_values()
    refused = [entry for entry in declared_actions()
               if values[entry["proof"]] == REFUSES]

    assert refused, "nothing is withheld on route grounds; the split has collapsed"
    for entry in refused:
        response = call(client, entry["action"])
        assert 400 <= response.status_code < 500, (
            f"{entry['action']} is withheld from dataset cards because its route "
            f"was said to refuse a dataset key, and {entry['route']} answered "
            f"{response.status_code}. If it works now, offer it.")


def test_an_action_withheld_for_its_page_opens_a_page_without_that_section(client):
    """The third proof, and the only one that is not a status code.

    `changes` opens `/source/{key}`, which renders for a dataset — 200 and a full
    grid. What is not there is any changes section: `browse_observations` and
    `changes_by_offer` are both skipped behind `is_dataset` in
    `scrapex/webui/app.py`, because a company has no offer and no price history.
    Offering "Recent changes" would open a page that answers a different question.
    """
    values = proof_values()
    by_page = [entry for entry in declared_actions()
               if values[entry["proof"]] == NO_SECTION]

    assert by_page, "the page-level proof is unused; delete it or use it"
    for entry in by_page:
        response = call(client, entry["action"])
        assert response.status_code == 200, (
            f"{entry['route']} no longer even renders; the reason this action is "
            f"withheld has changed and the declaration must change with it")
        assert 'id="changes"' not in response.text, (
            f"{entry['route']} now carries a changes section for a dataset, so "
            f"{entry['action']} can be offered")
        assert "Recent changes" not in response.text
