"""Tender sources, declared in a registry of their own (milestone 51, part 3b-1).

His ruling of 2026-10-10, option (a): a tender source registers the way
`scrapex/directories.py` registers a directory, the World Bank first. What it ships with
is his too: robots.txt obeyed, and the user can change it (#1701 Q2, 2026-10-17); 2.5 s
between requests, the pace #1647's Q2 put to him; and off for schedules until he turns
it on (`CLAUDE.md`: no source is made active without his word).
"""
from __future__ import annotations

import pytest

from scrapex import source_settings, tenders
from scrapex.connectors.base import source_fetcher
from scrapex.databases.domain import EngineDatabase
from scrapex.robots import RobotsChoice


@pytest.fixture()
def conn(tmp_path):
    db = EngineDatabase(tmp_path / "scrapex-engine.db")
    db.initialize()
    connection = db.connect()
    # Registered as its collector's first run will register it (part 3b-2's job).
    connection.execute("INSERT INTO source_site (source_key, source_name, base_url) "
                       "VALUES (?, ?, ?)", ("worldbank_org", "World Bank procurement notices",
                                            "https://search.worldbank.org"))
    connection.commit()
    yield connection
    connection.close()


def test_the_world_bank_is_the_first_tender_source():
    assert tenders.keys() == ("worldbank_org",)
    bank = tenders.get("worldbank_org")
    assert bank.key == "worldbank_org"
    assert bank.display_name == "World Bank procurement notices"
    assert bank.base_url == "https://search.worldbank.org"


def test_the_world_bank_carries_the_figures_measured_before_any_count():
    """What the cost question asks before the job has counted anything: #1647's request
    12 of 10 Oct 2026, the figure #1701's question shows (537), not a guess."""
    measured = tenders.get("worldbank_org").measured
    assert (measured.requests, measured.total, measured.areas, measured.counted_at) == (
        537, 422_285, 184, "2026-10-10")


def test_a_full_rebuild_is_not_offered_and_says_why_in_its_host():
    bank = tenders.get("worldbank_org")
    assert bank.host == "search.worldbank.org"
    assert bank.runs_blocked == {
        "full_rebuild": "Full rebuild is not offered for search.worldbank.org: it keeps "
                        "every notice as it was read, so there is nothing to archive."}


def test_an_unknown_tender_source_is_refused_by_name():
    with pytest.raises(KeyError) as refused:
        tenders.get("worldbank")
    assert "'worldbank' is not a tender source this build can collect" in str(refused.value)
    assert "worldbank_org" in str(refused.value)


def test_it_ships_obeying_robots_at_two_and_a_half_seconds_and_off(conn):
    rules = source_settings.effective(conn, "worldbank_org", tenders.get("worldbank_org"))
    assert rules.robots is RobotsChoice.OBEY
    assert rules.robots_custom is None
    assert rules.crawl_pace_s == 2.5
    assert rules.active is False
    assert rules.user_agent is None


def test_a_tender_source_handed_for_another_key_is_refused(conn):
    """One source's settings never govern another's crawl: a mixed-up caller is stopped
    by name, not served the World Bank's robots and pace for some other site."""
    with pytest.raises(ValueError, match="asked for 'another_site' with 'worldbank_org'"
                                         "'s tender source"):
        source_settings.effective(conn, "another_site", tenders.get("worldbank_org"))


def test_the_rules_say_each_comes_from_the_source(conn):
    explained = source_settings.explained(conn, "worldbank_org", tenders.get("worldbank_org"))
    assert explained["robots"] == {"value": "obey", "custom": None, "shipped": "obey",
                                   "shipped_custom": None, "origin": "source"}
    assert explained["crawl_pace_s"]["value"] == 2.5
    assert explained["crawl_pace_s"]["origin"] == "source"


def test_his_choice_overrides_what_it_ships_and_clearing_it_returns_there(conn):
    bank = tenders.get("worldbank_org")
    source_settings.save(conn, "worldbank_org", bank, {"robots": "default"})
    assert source_settings.effective(conn, "worldbank_org", bank).robots is RobotsChoice.DEFAULT
    source_settings.save(conn, "worldbank_org", bank, {"robots": None})
    assert source_settings.effective(conn, "worldbank_org", bank).robots is RobotsChoice.OBEY


def test_the_fetcher_obeys_and_keeps_the_sources_pace(conn):
    rules = source_settings.effective(conn, "worldbank_org", tenders.get("worldbank_org"))
    fetcher = source_fetcher(rules, {"min_interval_s": 1.0})
    try:
        assert fetcher._robots_choice == "obey"
        assert fetcher._min_interval_s == 2.5
    finally:
        fetcher.close()


def test_a_directory_and_a_tender_source_never_share_a_key():
    from scrapex import directories
    assert not set(tenders.keys()) & set(directories.keys())
