"""One domain is one source, divided inside it (#1872): each row of /api/sources names its domain,
the part it is, and the last crawl that settled for it. The panel draws one row per domain from these."""
from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from scrapex import db as dbmod
from scrapex import directories, jobs, sourceboard
from scrapex.config import MANIFEST_FILE
from scrapex.webui.app import create_app

FINISHED = "2026-11-01T05:33:29Z"


@pytest.fixture()
def db_path(tmp_path):
    path = tmp_path / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    conn.commit()
    conn.close()
    return path


@pytest.fixture()
def client(db_path, tmp_path):
    manifest = tmp_path / "sources.yaml"
    shutil.copy(MANIFEST_FILE, manifest)
    return TestClient(create_app(db_path, manifest_path=manifest))


def rows_by_key(client):
    return {row["source_key"]: row for row in client.get("/api/sources").json()["sources"]}


def settle(db_path, status, *, kind="directory_crawl", key="tvtc_training_plans", error=None):
    conn = dbmod.connect(db_path)
    try:
        ref = jobs.create_job(conn, [key], job_kind=kind)
        conn.execute("UPDATE crawl_job SET status = ?, finished_at = ?, error_summary = ? WHERE job_ref = ?",
                     (status, FINISHED, error, ref))
        conn.commit()
    finally:
        conn.close()
    return ref


def test_both_tvtc_listings_name_one_domain_and_each_its_part(client):
    rows = rows_by_key(client)
    establishments, plans = rows["tvtc_establishments"], rows["tvtc_training_plans"]
    assert establishments["domain"] == plans["domain"] == "tvtc.gov.sa"
    assert establishments["domain_name"] == plans["domain_name"] == "TVTC licensed training"
    assert (establishments["part_name"], plans["part_name"]) == ("Establishments", "Training plans")
    assert establishments["listing"] is True and plans["listing"] is True
    # NEITHER HAS CRAWLED, and the row says so rather than leaving the key out.
    assert establishments["last_job"] is None and plans["last_job"] is None


def test_a_source_alone_on_its_domain_names_no_part(client):
    rows = rows_by_key(client)
    muqawil = rows["muqawil_org"]
    assert (muqawil["domain"], muqawil["domain_name"], muqawil["part_name"]) == ("muqawil.org", "", "")
    # A PRICE ENTRY NAMES ITS DOMAIN TOO, and no last crawl: a price job names many sources.
    madar = rows["MADAR"]
    assert (madar["domain"], madar["part_name"], madar["listing"]) == ("madar.com", "", True)
    assert "last_job" not in madar


def test_a_part_names_its_newest_settled_crawl_and_no_other_kind_of_job(client, db_path):
    settle(db_path, "completed")
    failed = settle(db_path, "failed", error="Server error '503 Service Unavailable'")
    settle(db_path, "skipped")                              # a skip fetched nothing
    settle(db_path, "completed", kind="dataset_interpret")  # says nothing about the site
    rows = rows_by_key(client)
    assert rows["tvtc_training_plans"]["last_job"] == {
        "job_ref": failed, "status": "failed", "finished_at": FINISHED,
        "error_summary": "Server error '503 Service Unavailable'"}
    assert rows["tvtc_establishments"]["last_job"] is None


def test_a_tender_crawl_is_a_crawl_the_row_names(client, db_path):
    """THE DESIGN NAMES THE KINDS (#1872, round 5): "`directory_crawl` today; #1802's
    `tender_crawl` joins the tuple at build", and #1802 is on main. No tender row is listed
    until 3b-2b (#1996) draws one, so the kind is proved on a row that is listed: a settled
    tender crawl naming it is its newest crawl."""
    settle(db_path, "completed")
    tender = settle(db_path, "failed", kind="tender_crawl", error="the Bank answered 503")
    assert rows_by_key(client)["tvtc_training_plans"]["last_job"] == {
        "job_ref": tender, "status": "failed", "finished_at": FINISHED,
        "error_summary": "the Bank answered 503"}


def test_a_crawl_still_running_is_not_the_last_crawl(client, db_path):
    done = settle(db_path, "completed")
    conn = dbmod.connect(db_path)
    try:
        jobs.create_job(conn, ["tvtc_training_plans"], job_kind="directory_crawl")
    finally:
        conn.close()
    assert rows_by_key(client)["tvtc_training_plans"]["last_job"]["job_ref"] == done


def test_a_table_derived_from_another_crawl_is_a_part_but_not_a_listing():
    plans = directories.get("tvtc_training_plans")
    licences = plans.derived[0]
    rows = [{"source_key": plans.dataset_key, "site_key": plans.key, "base_url": plans.base_url},
            {"source_key": licences.dataset_key, "site_key": plans.key, "base_url": plans.base_url}]
    out = sourceboard.with_domains(rows, {plans.key: {"status": "failed"}})
    assert [(row["listing"], row["part_name"]) for row in out] == [
        (True, "Training plans"), (False, "Establishment licences")]
    # THE CRAWL'S OUTCOME BELONGS TO THE ROW A TICK CAN START, not to the table it feeds.
    assert out[0]["last_job"] == {"status": "failed"} and "last_job" not in out[1]


def test_a_directory_holding_rows_is_its_dataset_card_and_still_names_its_part_and_crawl():
    """ONCE A DIRECTORY HOLDS ROWS IT IS LISTED AS ITS DATASET CARD, whose `source_key` is the
    dataset key, and its registered row is no longer drawn (`_registered_directories`). The
    card is the listing a tick starts, so it names its part and carries its crawl. The merge
    gate of #2000 found no test that read a card: TVTC's establishments are the case where
    the two keys differ."""
    establishments = directories.get("tvtc_establishments")
    assert establishments.dataset_key != establishments.key, "precondition: the keys differ"
    card = {"kind": "dataset", "source_key": establishments.dataset_key,
            "site_key": establishments.key, "base_url": establishments.base_url}
    out = sourceboard.with_domains([card], {establishments.key: {"status": "failed"}})
    assert (out[0]["listing"], out[0]["part_name"], out[0]["last_job"]) == (
        True, "Establishments", {"status": "failed"})


def test_the_world_bank_is_named_on_the_row_it_has_today(client):
    """THE NAME IS READ NOW, not only once tender rows land: the Pink Sheet's base is
    www.worldbank.org, a part of the one source worldbank.org that stage 6 was approved on."""
    pink = rows_by_key(client)["WORLDBANK_PINK_SHEET"]
    assert (pink["domain"], pink["domain_name"], pink["part_name"]) == (
        "worldbank.org", "World Bank", "")


def test_an_entry_added_on_a_host_the_code_reads_does_not_hide_it(client):
    """THE ROUTE'S OWN PROMISE (#1872): "an unbuilt entry added there must not hide it". Add
    refuses only a duplicate key, so a second entry on muqawil.org can be filed, and a tab
    there must still select the source the code reads."""
    entry = {"source_key": "muqawil_again", "source_name": "Muqawil, filed again",
             "base_url": "https://muqawil.org", "family": "shopify-json",
             "kind": "product_prices", "scope": "census", "active": False}
    assert client.post("/api/sources", json=entry).status_code == 200, "precondition"
    assert client.get("/api/resolve", params={"url": "https://muqawil.org/ar/contractors"}).json() == {
        "matched": True, "source_key": "muqawil_org",
        "source_name": directories.get("muqawil_org").display_name, "implemented": True}


def test_every_directory_s_own_address_selects_a_directory_on_that_host(client):
    """EVERY HOST THE CODE READS, not only the first in sort order: a tab on each directory's
    own address selects a directory there (both TVTC listings share pt-api.tvtc.gov.sa)."""
    for key in directories.BUILDERS:
        base = directories.get(key).base_url
        answer = client.get("/api/resolve", params={"url": f"{base}/any/page"}).json()
        assert answer.get("matched") and answer["source_key"] in directories.BUILDERS, (key, answer)
        chosen = directories.get(answer["source_key"]).base_url
        assert jobs.host_of_url(chosen, "") == jobs.host_of_url(base, ""), (key, answer)


def test_a_tab_on_a_host_the_code_reads_selects_that_source(client):
    assert client.get("/api/resolve", params={"url": "https://muqawil.org/ar/contractors"}).json() == {
        "matched": True, "source_key": "muqawil_org",
        "source_name": directories.get("muqawil_org").display_name, "implemented": True}


def test_a_tab_on_another_host_of_a_known_domain_names_the_domain(client):
    assert client.get("/api/resolve", params={"url": "https://pt-web.tvtc.gov.sa/institutes"}).json() == {
        "matched": False, "domain": "tvtc.gov.sa"}
