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

#: The proofs `app.js` may declare, and what each one MEANS as a request. A new one has
#: to be added here before it can be used there, which is deliberate: the set of ways an
#: action can be justified is not open-ended.
#:
#: `RESOLVES_SOURCE` ARRIVED 2026-09-02 and it is the first that is not about a dataset
#: key at all. `#301`/`R-78` made `POST /api/jobs` resolve a source through `source_site`
#: as well as through `sources.yaml`, so it answers for `muqawil_org` -- while still
#: refusing `contractors`, which is what a dataset card carries as its own `source_key`.
#: Both halves are measured below, because either alone justifies nothing.
RESOLVES = "resolves-a-dataset-key"
REFUSES = "route-404-for-a-dataset-key"
NO_SECTION = "no-such-section-on-the-page"
RESOLVES_SOURCE = "route-resolves-a-registry-source"
PROOFS = {RESOLVES, REFUSES, NO_SECTION, RESOLVES_SOURCE}

#: The site behind the dataset the `client` fixture approves. `POST /api/jobs` resolves
#: THIS and not `KEY`, which is the whole reason the crawl action carries it.
SITE_KEY = "muqawil_org"

#: How to make each action's request. The `route` here is compared to the one
#: `app.js` declares, so a recipe cannot quietly test a different endpoint from
#: the one the panel drives — and an action with no recipe fails collection
#: rather than passing unmeasured.
RECIPES = {
    # `update`, NOT `current`: this recipe carried `run_mode: "current"` copied out of
    # `app.js`, and `current` is not a `RunMode`. So the route answered 400 for the run
    # mode and never reached the key -- while `test_an_action_withheld_for_its_route_
    # really_is_refused` accepted any 4xx and recorded the refusal as being about the
    # KEY. A valid mode is what makes that test measure what it claims.
    "update": ("POST /api/jobs", "post", "/api/jobs",
               {"source_keys": [KEY], "run_mode": "update"}),
    "table": ("GET /api/table/{key}", "get", f"/api/table/{KEY}", None),
    "enrich": ("GET /api/enrichment/sources/{key}", "get",
               f"/api/enrichment/sources/{KEY}", None),
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
        r"^const (RESOLVES_A_DATASET|MANIFEST_ONLY|NO_SECTION|RESOLVES_A_SOURCE_KEY) = \"([^\"]+)\";",
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


def test_every_proof_is_one_of_the_declared_set_and_they_say_what_they_mean():
    values = proof_values()

    assert values == {"RESOLVES_A_DATASET": RESOLVES,
                      "MANIFEST_ONLY": REFUSES,
                      "RESOLVES_A_SOURCE_KEY": RESOLVES_SOURCE,
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
        if entry["action"] == "table":
            assert payload["rows"], f"{entry['route']} answered 200 with no rows"
            assert payload["columns"], f"{entry['route']} answered 200 with no columns"
        elif entry["action"] == "enrich":
            assert payload["proposal"]["source_dataset_key"] == KEY
            assert payload["datasets"], f"{entry['route']} has no source datasets"
            assert payload["provider_availability"], (
                f"{entry['route']} has no provider contract")


def test_an_action_withheld_for_its_route_really_is_refused(client):
    """WITHHELD ⇒ PROVEN TOO, so the menu cannot hide an action that works.

    AND THE REFUSAL HAS TO BE ABOUT THE KEY, which this asked for as `400 <= status <
    500` until 2026-09-02. Under that range the `update` action passed while its request
    was malformed: the recipe carried `run_mode: "current"` copied out of `app.js`,
    `current` is not a `RunMode`, and the route answered 400 about the mode without ever
    looking at the key. **The reason recorded was not the reason measured.**

    A status-code RANGE standing in for a reason cannot tell one refusal from another. So
    it is `404` now -- the code a route uses for a key it does not know -- which is what
    separates a refusal about the KEY from one about the REQUEST.
    """
    values = proof_values()
    refused = [entry for entry in declared_actions()
               if values[entry["proof"]] == REFUSES]

    assert refused, "nothing is withheld on route grounds; the split has collapsed"
    for entry in refused:
        response = call(client, entry["action"])
        assert response.status_code == 404, (
            f"{entry['action']} is withheld from dataset cards because its route was "
            f"said to refuse a dataset KEY, and {entry['route']} answered "
            f"{response.status_code}: {response.text[:200]}. A 4xx that is not a 404 is "
            f"a refusal about something else -- the request, not the key. If the route "
            f"works now, offer the action.")
        # AND NOT "THE BODY MUST NAME THE KEY", which the first draft asserted and
        # measured wrong: `GET /sources/{key}` answers a bare `{"detail":"Not Found"}`,
        # because a route that does not match says so without quoting what was asked.
        # Naming the key is a property of some handlers, not of a 404. The code is the
        # part that separates a refusal about the KEY from one about the REQUEST, and it
        # is the part this can honestly hold every route to.


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


# ---- the fourth proof, measured on both sides -------------------------------

def test_the_crawl_route_resolves_the_site_key_and_still_refuses_the_dataset_key(client):
    """`RESOLVES_A_SOURCE_KEY`, AND BOTH HALVES ARE THE PROOF.

    A dataset card's own `source_key` IS its dataset key -- `scrapex/webui/app.py`'s
    dataset rows set it that way and carry the site separately as `site_key`. So
    `MANIFEST_ONLY` was, and remains, a TRUE statement about the key the card carries:
    `POST /api/jobs` really does refuse `contractors`.

    What changed is that `#301`/`R-78` taught that route to resolve a source through
    `source_site`, so it answers for `muqawil_org`. That is why `sourceActions` offers the
    crawl as `update:<site_key>` -- the key travels with the action, the way
    `table:<dataset_key>` already does -- rather than by relaxing the filter.

    ONE SIDE ALONE WOULD JUSTIFY NOTHING. If the route had started accepting the dataset
    key too, the honest fix would have been to change the base entry's proof and leave the
    action where it was. So the refusal is asserted here as deliberately as the success.

    THE PARSER CANNOT REACH THIS ACTION, said rather than left as a hole: `_declared()`
    reads the `SOURCE_ACTIONS` array, and the crawl entry is built inside `sourceActions()`
    from the card's `site_key`, exactly as `covered` is built from `coverage`. So the
    recipe table above cannot describe it and this measures the route directly.
    """
    resolved = client.post("/api/jobs",
                           json={"source_keys": [SITE_KEY], "run_mode": "update"})
    assert resolved.status_code == 200, (
        f"the site key {SITE_KEY!r} no longer resolves, so the crawl action on a dataset "
        f"card offers a control that fails: {resolved.status_code} {resolved.text}")

    refused = client.post("/api/jobs",
                          json={"source_keys": [KEY], "run_mode": "update"})
    assert refused.status_code == 404, (
        f"the dataset key {KEY!r} is now accepted too, which removes the reason the crawl "
        f"action carries the site key -- change the base entry's proof instead: "
        f"{refused.status_code} {refused.text}")
