"""muqawil appears ONCE in the listing, and its two datasets are still two.

HIS COMPLAINT, twice, with a screenshot each time. `REQ-37`:

    «المفروض مصدر مقاول يظهر مرة واحدة فقط واختيارات الزحف الخاصة به تكون متعغددة»

The Data screen drew two `muqawil.org` cards — `contractors [Row 17,304]` and
`contractor_profiles [Row 704]` — because `_dataset_rows` ends
`GROUP BY d.dataset_definition_id` and the panel draws a card per row. `R-47`
answered it: «زحفين لمجموعة واحدة» — two crawls of one dataset — **and ruled that the
two stored `dataset_definition` rows stay two.** Only the listing collapses.

SO THIS FILE ASSERTS BOTH HALVES, and the second half is the one that would rot
quietly. It is easy to collapse the listing by folding inside `_dataset_rows`, and
that function has a SECOND caller: `/source/{key}` resolves one dataset out of it by
key, so folding in place makes `/source/contractor_profiles` answer 404 again — the
exact regression #212 was built to close, arriving through a change that looks like a
display fix. `test_the_profile_table_still_opens_on_its_own` is that guard.

AND THE COLLAPSE IS CONDITIONAL, which is `R-47`'s own justification rather than a
caution of ours: *"the join is the thing that makes the single card honest rather than
a label over two unrelated tables."* Two datasets that merely share a site are two
populations. So a relationship that is `suggested` and not `confirmed`, or that is
`one_to_many` rather than `one_to_one`, leaves two cards standing — each of those is a
test here, because each is a way for one card to state a number nobody could act on.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from scrapex.catalog_models import (
    Cardinality,
    RelationshipCreate,
    RelationshipFieldPairCreate,
    RelationshipReviewStatus,
)
from scrapex.catalog_relations import propose_relationship, review_relationship
from scrapex.config import MANIFEST_FILE
from scrapex.databases import DatabaseRegistry, EngineDatabase
from scrapex.extract import service
from scrapex.extract.models import ApprovalField, CandidateApproval, SnapshotCreate
from scrapex.extract.muqawil import bilingual_profile_candidate, listing_candidate
from scrapex.webui.app import create_app

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "muqawil"
LISTING = (FIXTURES / "listing-en.html").read_text(encoding="utf-8")
PROFILE_EN = (FIXTURES / "profile-en.html").read_text(encoding="utf-8")
PROFILE_AR = (FIXTURES / "profile-ar.html").read_text(encoding="utf-8")

#: The site both datasets hang off. Measured read-only on his warehouse
#: 2026-08-23: `source_id = 2`, `site_key = 'muqawil_org'`, carrying
#: `contractors` (17,304 active rows) and `contractor_profiles` (704).
SITE = "muqawil_org"
PARENT = "contractors"
CHILD = "contractor_profiles"


def _approve(conn, url: str, candidate, dataset_key: str, dataset_name: str) -> int:
    """One dataset on the muqawil site, approved the way the crawl approves one."""
    snapshot = service.save_snapshot(conn, SnapshotCreate(
        source_url=url, html_content=LISTING))
    approved = service.approve_candidate(
        conn, int(snapshot["page_snapshot_id"]),
        CandidateApproval(
            table_index=0, site_key=SITE, site_display_name="SCA",
            dataset_key=dataset_key, dataset_name=dataset_name,
            fields=[ApprovalField(field_key=f.field_key,
                                  display_name=f.source_name,
                                  data_type="text",
                                  identity=(f.field_key == "contractor_id"))
                    for f in candidate.fields]),
        candidate=candidate)
    return int(approved["dataset_definition_id"])


def _field_id(conn, dataset_definition_id: int, field_key: str) -> int:
    row = conn.execute(
        "SELECT field_definition_id FROM field_definition "
        " WHERE dataset_definition_id = ? AND field_key = ? AND valid_to IS NULL",
        (dataset_definition_id, field_key)).fetchone()
    assert row is not None, f"no {field_key!r} on dataset {dataset_definition_id}"
    return int(row["field_definition_id"])


GRANDCHILD = "contractor_projects"


def _relate(conn, key: str, parent_id: int, child_id: int, cardinality, status):
    """One relationship, proposed and then decided — the two-step path, kept whole."""
    propose_relationship(conn, SITE, RelationshipCreate(
        relationship_key=key,
        parent_dataset_id=parent_id, child_dataset_id=child_id,
        cardinality=cardinality, confidence=1.0,
        evidence={"joined_on": "contractor_id"},
        field_pairs=[RelationshipFieldPairCreate(
            parent_field_id=_field_id(conn, parent_id, "contractor_id"),
            child_field_id=_field_id(conn, child_id, "contractor_id"))]))
    if status is not RelationshipReviewStatus.SUGGESTED:
        review_relationship(conn, SITE, key, status=status)


def _warehouse(tmp_path, *, cardinality=Cardinality.ONE_TO_ONE,
               status=RelationshipReviewStatus.CONFIRMED, relate=True,
               chain=False):
    """Two datasets on one site, joined the way HIS warehouse joins them.

    THROUGH `propose_relationship` AND `review_relationship`, not through an INSERT.
    He asked for the join by name — «اربطهم فى dataset_relationship» — and those two
    functions are the path his warehouse's row was written by, one proposing and one
    deciding. A hand-built INSERT here would let this file pass over a shape the real
    path cannot produce.

    `chain` ADDS A THIRD DATASET UNDER THE SECOND, which nothing in his warehouse has
    yet. It is here because the fold has to decide what to do about depth, and a
    decision no test exercises is a coin toss waiting to land.
    """
    registry = DatabaseRegistry(EngineDatabase(tmp_path / "scrapex-engine.db"),
                               pointer_file=tmp_path / "databases.json")
    registry.initialize()
    conn = registry.engine.connect()
    try:
        parent_id = _approve(
            conn, "https://muqawil.org/en/contractors?page=1",
            listing_candidate(LISTING), PARENT, "Saudi Contractors Authority")
        # ONE ROW AGAINST FOUR, deliberately: a profile page holds one contractor
        # and a listing page holds several, so the child count is genuinely a
        # fraction of the parent's. Both at four would let the coverage arithmetic
        # read 100% whatever it computed.
        child_id = _approve(
            conn, "https://muqawil.org/en/contractors/881/143",
            bilingual_profile_candidate(PROFILE_EN, PROFILE_AR,
                                        contractor_id="881"),
            CHILD, "Contractor profiles")
        if relate:
            _relate(conn, "contractor_profile", parent_id, child_id,
                    cardinality, status)
        if chain:
            grandchild_id = _approve(
                conn, "https://muqawil.org/en/contractors/881/projects",
                listing_candidate(LISTING), GRANDCHILD, "Contractor projects")
            _relate(conn, "profile_projects", child_id, grandchild_id,
                    Cardinality.ONE_TO_ONE, RelationshipReviewStatus.CONFIRMED)
        conn.commit()
    finally:
        conn.close()
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(databases=registry, manifest_path=manifest))


def _datasets(client: TestClient) -> list[dict]:
    return [row for row in client.get("/api/sources").json()["sources"]
            if row.get("kind") == "dataset"]


# ---- the premise ------------------------------------------------------------

def test_the_warehouse_really_holds_two_related_datasets(tmp_path):
    """WITHOUT THIS EVERY ASSERTION BELOW IS VACUOUS. A warehouse that failed to
    approve the second dataset shows one card for the right reason and one card for
    the wrong reason, and nothing here could tell the two apart."""
    client = _warehouse(tmp_path)
    conn = client.app.state.general_database.connect()
    try:
        rows = conn.execute(
            "SELECT d.dataset_key, d.source_id FROM dataset_definition AS d "
            " WHERE d.valid_to IS NULL ORDER BY d.dataset_key").fetchall()
        keys = [row["dataset_key"] for row in rows]
        sites = {row["source_id"] for row in rows}
        link = conn.execute(
            "SELECT cardinality, review_status FROM dataset_relationship "
            " WHERE valid_to IS NULL").fetchone()
    finally:
        conn.close()

    assert keys == [CHILD, PARENT], keys
    assert len(sites) == 1, (
        "the two datasets are on two sites, so nothing here tests a collapse")
    assert link["cardinality"] == "one_to_one"
    assert link["review_status"] == "confirmed"


# ---- the listing collapses --------------------------------------------------

def test_the_two_muqawil_datasets_are_one_card(tmp_path):
    """His screenshot showed two. `R-47` says one."""
    datasets = _datasets(_warehouse(tmp_path))

    assert [row["source_key"] for row in datasets] == [PARENT], (
        "muqawil is listed once — «المفروض مصدر مقاول يظهر مرة واحدة فقط»")


def test_the_card_states_the_population_once_and_the_second_crawl_as_coverage(tmp_path):
    """`R-47`'s second point, and it is the number he actually wants.

    The two cards read 17,304 and 704 as if they were two populations. They are one:
    17,304 contractors, of whom 704 have an approved profile. So the population is
    stated once and the profile crawl reports how much of it has been fetched.
    """
    card = _datasets(_warehouse(tmp_path))[0]

    assert card["observations"] == 4, "the listing's own row count, unchanged"
    assert card["coverage"] == [{
        "dataset_key": CHILD,
        # THE SITE'S OWN WORD FOR IT (`R-45`): the label is the child dataset's
        # stored `display_name`, which the approval recorded, never a noun of ours.
        "label": "Contractor profiles",
        "stored": 1,
        "population": 4,
    }], card["coverage"]


def test_a_lone_dataset_is_left_exactly_as_it_was(tmp_path):
    """THE `jobs` AND `tenders` CASE, which CLAUDE.md names as coming.

    A site with one dataset must be untouched by the fold, and it must carry NO
    `coverage` key — the panel's noun branches on its absence, so a `coverage: []`
    here would print an empty second line on every future dataset card.
    """
    datasets = _datasets(_warehouse(tmp_path, relate=False))

    assert sorted(row["source_key"] for row in datasets) == [CHILD, PARENT], (
        "with no relationship these are two populations and stay two cards")
    for row in datasets:
        assert "coverage" not in row, row


# ---- and it collapses only on a join a person confirmed ---------------------

def test_a_merely_suggested_relationship_does_not_collapse_anything(tmp_path):
    """`review_status` IS THE HUMAN GATE. `propose_relationship`'s own docstring says
    *"this path can never confirm it"*, and collapsing on a guess would hide a
    population behind a percentage nobody had agreed was a percentage."""
    datasets = _datasets(_warehouse(
        tmp_path, status=RelationshipReviewStatus.SUGGESTED))

    assert sorted(row["source_key"] for row in datasets) == [CHILD, PARENT]


def test_a_rejected_relationship_does_not_collapse_anything(tmp_path):
    """The third value of the vocabulary, and the one that means "no"."""
    datasets = _datasets(_warehouse(
        tmp_path, status=RelationshipReviewStatus.REJECTED))

    assert sorted(row["source_key"] for row in datasets) == [CHILD, PARENT]


def test_no_dataset_falls_off_the_listing_when_relationships_are_two_deep(tmp_path):
    """EVERY DATASET REACHES A CARD, and a naive fold loses the deepest one.

    Fold every child into its parent and a middle dataset disappears — it is somebody
    else's child, so it is skipped — and its OWN child disappears with it, because the
    card that would have carried its coverage was never emitted. Three datasets,
    two reachable, and no error anywhere.

    So a child that is itself a parent keeps its own card. Nothing in his warehouse is
    two deep today; the point is that the day something is, the answer is already
    decided and asserted rather than discovered from a screen with a table missing.
    """
    datasets = _datasets(_warehouse(tmp_path, chain=True))
    keys = sorted(row["source_key"] for row in datasets)
    covered = sorted(entry["dataset_key"]
                     for row in datasets for entry in row.get("coverage", []))

    assert keys == [CHILD, PARENT], keys
    assert covered == [GRANDCHILD], covered
    assert sorted(keys + covered) == sorted([PARENT, CHILD, GRANDCHILD]), (
        "a dataset is reachable from no card at all")


def test_one_to_many_does_not_become_a_fraction(tmp_path):
    """CARDINALITY IS WHAT MAKES "704 of 17,304" A SENTENCE.

    Under `one_to_many` a parent row can carry several children, so the child count
    is not a fraction of the parent count at all — 9 rows against 4 parents would
    print "9 of 4 (225.0%)". Confirmed is not sufficient on its own.
    """
    datasets = _datasets(_warehouse(tmp_path, cardinality=Cardinality.ONE_TO_MANY))

    assert sorted(row["source_key"] for row in datasets) == [CHILD, PARENT]


# ---- and the two stored datasets are still two ------------------------------

def test_the_profile_table_still_opens_on_its_own(tmp_path):
    """THE REGRESSION THIS CHANGE COULD EASILY HAVE SHIPPED.

    `/source/{key}` resolves one dataset out of `_dataset_rows` by key
    (`scrapex/webui/app.py`, `dataset = next((row for row in _dataset_rows() if
    row["source_key"] == source_key), None)`). Folding the two datasets THERE rather
    than in the listing would take `contractor_profiles` out of that lookup and the
    page would answer 404 — which is precisely the defect #212 closed for
    `contractors`, returning through a change that looks like a display fix.

    `R-47` is explicit that this must not happen: *"the two `dataset_definition` rows
    stay two."*
    """
    client = _warehouse(tmp_path)

    for key in (PARENT, CHILD):
        assert client.get(f"/source/{key}").status_code == 200, (
            f"/source/{key} stopped resolving; the collapse reached the resolver")
        assert client.get(f"/api/table/{key}").status_code == 200, (
            f"/api/table/{key} stopped resolving")


def test_the_folded_dataset_is_still_its_own_row_in_the_warehouse(tmp_path):
    """The schema half of `R-47`, asserted on the schema rather than inferred.

    `contractors._approval` refuses to put a 27-field profile and a 28-field listing
    under one approved schema, because a subset is what a broken parser looks like
    (`R-31`). A change that "simplified" the listing by merging the datasets would
    either be refused there or retire the listing's live schema version.
    """
    client = _warehouse(tmp_path)
    conn = client.app.state.general_database.connect()
    try:
        live = [row["dataset_key"] for row in conn.execute(
            "SELECT dataset_key FROM dataset_definition WHERE valid_to IS NULL "
            "ORDER BY dataset_key")]
    finally:
        conn.close()

    assert live == [CHILD, PARENT], (
        "the listing collapsed and took a stored dataset with it")


# ---- the panel prints it, and does not print "products" over a directory ----
#
# The DOM half is `tests/test_panel_dom.py`
# (`test_a_dataset_card_says_rows_and_coverage_never_products`), driven in a real
# browser. This one asserts the SHAPE the panel reads, because the two failed apart
# once already: #255 fixed `last_success` on the engine while the harness stub still
# carried the `None` the engine had stopped sending.

@pytest.mark.extension
def test_the_harness_stub_carries_the_SHAPE_the_engine_really_sends(tmp_path):
    """THE SEAM THAT FAILED ONCE ALREADY, and it failed exactly this way.

    #255 taught the engine to report a real `last_success` for a dataset while the
    panel harness stub still carried the literal `None` the engine had stopped
    sending. Every DOM assertion stayed green about a state the product no longer
    produced. The coverage entry is a new key with the same exposure, so the stub's
    keys are compared to the ENGINE'S keys here rather than trusted.

    A NOTE ON WHAT THIS REPLACED, because the first attempt was worse than nothing.
    It asserted that the string `c.stored` appears in `app.js` — and `c.stored`
    appears TWICE there, in `countLine` and in `coverageShare`, so renaming the one
    the card reads left the substring present and the guard green. Mutation caught
    it: M11 of this branch's table was the only mutation not caught, which is the
    "search for one spelling is not a measurement" lesson (`LESSONS.md` §9) arriving
    at a test instead of at a census. The property is behavioural, so the assertion
    has to be.
    """
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import panel_harness as harness

    card = _datasets(_warehouse(tmp_path))[0]
    stub = next(row for row in harness.STRESS_SOURCES
                if row.get("kind") == "dataset")

    assert "coverage" in stub, (
        "the stub carries no coverage entry, so tests/test_panel_dom.py's "
        "assertions about the card's second line are about nothing")
    assert set(stub["coverage"][0]) == set(card["coverage"][0]), (
        f"the stub and the engine disagree about a dataset card's coverage keys: "
        f"stub {sorted(stub['coverage'][0])} vs engine {sorted(card['coverage'][0])}")
