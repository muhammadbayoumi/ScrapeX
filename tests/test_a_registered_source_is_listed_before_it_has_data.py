"""His requirement, in his words, and the reason it was not already true.

    «المفروض المصادر تظهر بدون بيانات فهى مسجلة ومحفوظة فى الكود»

He said it after `muqawil` was missing from **Choose sites** in the Run tab on a
warehouse created an hour earlier. `/api/sources` was the price manifest plus
`_dataset_listing()`, and that second half groups `dataset_definition` rows — so a
directory appeared only AFTER its first crawl had stored something, while
`directories.BUILDERS` had known how to crawl it the whole time.

THE ENGINE WAS ALREADY READY, which is what makes this a listing gap rather than a
feature: `POST /api/jobs` resolves keys through `SourceResolver` (`R-78`, *"asked of the
registry, not the file"*) and routes a `BUILDERS` key to the directory collector. The
button had a target and the panel drew no row for it — `R-81`.

The last test here is the one that matters: the key the row carries is a key the job
route accepts. A row he can see and cannot run would not have answered him.
"""

from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from scrapex import directories
from scrapex.databases.domain import EngineDatabase
from scrapex.webui.app import create_app


@pytest.fixture()
def empty_warehouse(tmp_path):
    """A warehouse with nothing in it — `R-23` calls that the normal first run."""
    path = tmp_path / "scrapex-engine.db"
    EngineDatabase(path).initialize()
    return path


def _sources(path) -> list[dict]:
    with TestClient(create_app(path)) as client:
        answer = client.get("/api/sources")
    assert answer.status_code == 200, answer.text
    return answer.json()["sources"]


def test_a_directory_registered_in_the_code_is_listed_with_no_data_at_all(empty_warehouse):
    """The requirement itself. Measured before this change: 12 rows, none of them a
    directory, on a warehouse holding `dataset_definition` 0 and `generic_record` 0."""
    rows = {row["source_key"]: row for row in _sources(empty_warehouse)}

    for key in directories.BUILDERS:
        assert key in rows, (
            f"{key} is registered in `directories.BUILDERS` and this build can crawl "
            "it, and the panel is not told it exists")

    muqawil = rows["muqawil_org"]
    assert muqawil["implemented"] is True, (
        "a collector exists for it in this build; `implemented` false would draw it "
        "as 'Not supported yet'")
    assert muqawil["active"] is False, "nothing is scheduled for it"
    assert muqawil["observations"] == 0 and muqawil["products"] == 0
    assert muqawil["last_success"] is None
    assert muqawil["base_url"] and muqawil["source_name"]


def test_it_declares_itself_a_directory_and_not_a_dataset(empty_warehouse):
    """`kind` DECIDES WHICH CONTROLS THE PANEL DRAWS, so borrowing the dataset marker
    to get the crawl button would have brought "Open the data table" with it — and that
    reaches `/api/table/{key}`, which 404s for a site holding no dataset. The rule this
    codebase states is that a button which cannot work is worse than no button."""
    rows = {row["source_key"]: row for row in _sources(empty_warehouse)}

    assert rows["muqawil_org"]["kind"] == "directory"
    assert rows["muqawil_org"]["site_key"] == "muqawil_org", (
        "the panel gates the crawl control on `site_key`")


def test_the_key_it_carries_is_a_key_the_job_route_accepts(empty_warehouse):
    """THE ASSERTION THAT MAKES THE ROW MORE THAN A LABEL.

    A dataset card carries `dataset_key` (`contractors`), which `POST /api/jobs`
    refuses — measured as `OP-52`. `BUILDERS` is keyed by `site_key`, which it accepts
    since `R-78`. So this row names the thing that can actually be run, and pressing
    Update now reaches a collector rather than a 404.
    """
    rows = {row["source_key"]: row for row in _sources(empty_warehouse)}
    key = rows["muqawil_org"]["source_key"]

    with TestClient(create_app(empty_warehouse)) as client:
        answer = client.post("/api/jobs", json={"source_keys": [key]})

    assert answer.status_code != 404, (
        f"the panel would offer a crawl for {key!r} and the route refuses it: "
        f"{answer.text}")
    assert answer.status_code < 500, answer.text


def test_a_site_that_already_has_a_card_is_not_drawn_twice(empty_warehouse):
    """`REQ-37` and `R-47`: he complained twice, with screenshots, that `muqawil.org`
    appeared TWICE on one screen. A registered row beside its own dataset card would be
    that defect again, so anything already listed wins."""
    conn = sqlite3.connect(str(empty_warehouse))
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(source_site)")}
        wanted = {"source_key": "muqawil_org", "source_name": "muqawil.org",
                  "source_name_ar": "مقاول", "base_url": "https://muqawil.org/",
                  "platform": "directory", "currency": "SAR",
                  "default_tax_mode": "incl", "authority": "official",
                  "lifecycle": "active"}
        use = {k: v for k, v in wanted.items() if k in columns}
        conn.execute(f"INSERT INTO source_site ({', '.join(use)}) VALUES "
                     f"({', '.join('?' for _ in use)})", tuple(use.values()))
        source_id = conn.execute(
            "SELECT source_id FROM source_site WHERE source_key = 'muqawil_org'"
        ).fetchone()[0]

        # EVERY NOT-NULL COLUMN WITHOUT A DEFAULT, discovered rather than listed: the
        # fixture must survive a migration adding one (`discovery_method` is how it
        # first failed) instead of pinning today's shape.
        # A CHECK-CONSTRAINED COLUMN NEEDS A REAL VALUE, not a placeholder: the
        # discovery below fills what it can and `known` carries the ones the schema
        # constrains to a set.
        known = {"source_id": source_id, "dataset_key": "contractors",
                 "display_name": "Contractors", "original_name": "Contractors",
                 "dataset_name": "Contractors", "discovery_method": "manual"}
        use = {}
        for row in conn.execute("PRAGMA table_info(dataset_definition)"):
            name, kind, notnull, default, pk = row[1], row[2], row[3], row[4], row[5]
            if name in known:
                use[name] = known[name]
            elif notnull and default is None and not pk:
                use[name] = 0 if "INT" in (kind or "").upper() else "test"
        conn.execute(f"INSERT INTO dataset_definition ({', '.join(use)}) VALUES "
                     f"({', '.join('?' for _ in use)})", tuple(use.values()))
        conn.commit()
    finally:
        conn.close()

    rows = _sources(empty_warehouse)
    for_site = [row for row in rows
                if row.get("site_key") == "muqawil_org"
                or row["source_key"] == "muqawil_org"]

    assert len(for_site) == 1, (
        "muqawil is drawn twice — the dataset card and the registered row — which is "
        f"REQ-37 again: {[row['source_key'] for row in for_site]}")
    assert for_site[0]["kind"] == "dataset", (
        "the card with the data lost to the placeholder")


def test_the_panel_and_the_command_line_answer_from_one_place(empty_warehouse):
    """`ENGINEERING` P1/Q1, as a property rather than as a promise.

    THE SPLIT THIS GUARDS AGAINST EXISTED FOR A FEW HOURS AND WAS MINE. The first
    version of `_registered_directories` knew `directories.BUILDERS` itself, so
    `/api/sources` listed muqawil and `sourceboard.board()` — which the `scrapex
    sources` report reads — did not. Two answers to "which sources exist", from two
    places, in one product.

    On an empty warehouse both surfaces reduce to the same two registries, the manifest
    and the code, so their KEY SETS must be identical. If a later change teaches one
    surface about a registry the other cannot see, this fails and names the difference.
    """
    from scrapex import sourceboard

    panel = {row["source_key"] for row in _sources(empty_warehouse)}
    board = {one.key for one in sourceboard.board(None)}

    assert panel == board, (
        "the panel and the board disagree about which sources exist.\n"
        f"  only the panel: {sorted(panel - board)}\n"
        f"  only the board: {sorted(board - panel)}")
    assert "muqawil_org" in panel, "neither surface knows the one registered directory"
