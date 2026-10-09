"""His choices about one source live in the warehouse, and are read in one order (#1584).

His ruling (2026-10-08, option C): active, the robots choice, the custom rule, the user
agent and the pace move out of `sources.yaml` -- which the packaged engine deletes at
exit (#1583) and which a directory source is not in -- into `source_setting`, for every
kind of source. This file holds the table (migration 0022) and the module that reads and
writes it (`scrapex/source_settings.py`), on the real schema and the real migration
stream, never a fixture schema:

  * the table is there on a new warehouse AND on one upgraded from the version before;
  * its CHECKs refuse what a crawl could not act on, and its robots vocabulary is
    `robots.RobotsChoice`'s exactly;
  * `save` stores, clears and refuses, and a refusal writes nothing;
  * `effective` layers his choice over the shipped entry over no opinion at all, for a
    price source and for a directory source that has no entry.
"""
from __future__ import annotations

import math
import re
import sqlite3

import pytest

from scrapex import directories, source_settings
from scrapex.config import Manifest
from scrapex.databases.domain import EngineDatabase
from scrapex.robots import RobotsChoice
from scrapex.source_settings import (
    SourceRules,
    SourceSettingError,
    UnknownSourceError,
    effective,
    read,
    save,
    shipped_with,
)
from scrapex.sources_admin import rename_source

MIGRATION = "0022_his_choices_about_a_source_live_in_the_warehouse.sql"

#: A price source that SHIPS opinions on every field, so each layer is visible.
SHOP = "SHOP_A"
#: A price source that ships none, so its fallback is "no per-source opinion".
PLAIN = "PLAIN_B"
#: A price source nobody has probed: `SourceEntry` refuses to activate it.
UNPROBED = "UNPROBED_C"
#: A directory source: in `source_site`, not in `sources.yaml`.
DIRECTORY = "muqawil_org"
#: In the manifest, never crawled, so not in `source_site`.
NEVER_CRAWLED = "NEVER_D"


def _entry(key: str, **fields) -> dict:
    return {"source_key": key, "source_name": key.title(), "base_url": f"https://{key}.test",
            "family": "shopify-json", "extract": [{"kind": "product_prices"}], **fields}


@pytest.fixture()
def manifest() -> Manifest:
    return Manifest.model_validate({"sources": [
        _entry(SHOP, active=True, robots="obey", user_agent="ShippedAgent/1.0",
               crawl_pace_s=3.0),
        _entry(PLAIN),
        _entry(UNPROBED, family="TBD-probe"),
        _entry(NEVER_CRAWLED, user_agent="ZidNeedsThis/1.0"),
    ]})


@pytest.fixture()
def conn(tmp_path):
    """A warehouse built by the engine's own migrator, with four sources registered."""
    db = EngineDatabase(tmp_path / "scrapex-engine.db")
    db.initialize()
    connection = db.connect()
    for key in (SHOP, PLAIN, UNPROBED, DIRECTORY):
        connection.execute("INSERT INTO source_site (source_key, source_name) VALUES (?, ?)",
                           (key, key))
    connection.commit()
    yield connection
    connection.close()


def _row(conn, key: str) -> dict | None:
    row = conn.execute(
        "SELECT st.* FROM source_setting st JOIN source_site ss USING (source_id) "
        "WHERE ss.source_key = ?", (key,)).fetchone()
    return None if row is None else dict(row)


def _source_id(conn, key: str) -> int:
    return conn.execute("SELECT source_id FROM source_site WHERE source_key = ?",
                        (key,)).fetchone()[0]


# ---- the table ------------------------------------------------------------------

def test_a_new_warehouse_has_the_table_with_every_rule_column_nullable(conn):
    """NULL is how a column says "he has not chosen; inherit". A NOT NULL rule column
    could not say it, and a default would be a choice he never made."""
    columns = {r["name"]: r for r in conn.execute("PRAGMA table_info(source_setting)")}

    assert set(columns) == {"source_id", "active", "robots_choice",
                            "robots_enforce_disallow", "robots_crawl_delay_s",
                            "user_agent", "crawl_pace_s", "updated_at"}
    assert columns["source_id"]["pk"] == 1
    for name in ("active", "robots_choice", "robots_enforce_disallow",
                 "robots_crawl_delay_s", "user_agent", "crawl_pace_s"):
        assert columns[name]["notnull"] == 0, f"{name} must be nullable: NULL inherits"
        assert columns[name]["dflt_value"] is None, f"{name} must default to inherit"
    assert columns["updated_at"]["notnull"] == 1
    # NO ACTION on delete, deliberately: `source_site` rows are never deleted -- a wipe
    # keeps the registry row -- and a cascade would erase his choices with nothing said.
    assert [tuple(r)[2:7] for r in conn.execute("PRAGMA foreign_key_list(source_setting)")] \
        == [("source_site", "source_id", "source_id", "NO ACTION", "NO ACTION")]
    assert conn.execute("SELECT 1 FROM database_migration WHERE migration_name = ?",
                        (MIGRATION,)).fetchone(), "the ledger does not record 0022"


def test_an_existing_warehouse_gains_the_table_and_keeps_its_sources(tmp_path, monkeypatch):
    """HIS warehouse is not new: it is at the version before this one, holding sources.
    Built the way the engine builds it -- the stream stopped short of 0022, rows put in,
    then the same database opened by this build."""
    db = EngineDatabase(tmp_path / "upgraded.db")
    whole = db._migrations
    assert whole[-1].name == MIGRATION, "0022 is no longer the newest; re-aim this test"
    monkeypatch.setattr(db, "_migrations", whole[:-1])
    db.initialize()
    with db.connect() as before:
        assert not before.execute("SELECT 1 FROM sqlite_master WHERE name = 'source_setting'"
                                  ).fetchone(), "the stop point already has the table"
        before.execute("INSERT INTO source_site (source_key, source_name) VALUES (?, ?)",
                       (DIRECTORY, "Saudi Contractors Authority"))
        before.commit()

    monkeypatch.setattr(db, "_migrations", whole)
    assert db.initialize() == [whole[-1].number]
    upgraded = db.connect()
    try:
        assert upgraded.execute("PRAGMA user_version").fetchone()[0] == whole[-1].number
        assert upgraded.execute("SELECT source_name FROM source_site WHERE source_key = ?",
                                (DIRECTORY,)).fetchone()[0] == "Saudi Contractors Authority"
        save(upgraded, DIRECTORY, directories.get(DIRECTORY),
             {"crawl_pace_s": 5.0})
        upgraded.commit()
        assert read(upgraded, DIRECTORY) == {"crawl_pace_s": 5.0}
        assert not upgraded.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        upgraded.close()


def test_the_robots_vocabulary_is_the_enums_and_nothing_else(conn):
    """A value the CHECK allows and `RobotsChoice` does not is a value a crawl raises
    on when it reads it. The study on #1584 named an `ignore` choice the code does not
    have; adding one is a migration AND an enum member, in one change."""
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE name = 'source_setting'"
                       ).fetchone()[0]
    allowed = re.search(r"robots_choice\s+TEXT\s+CHECK\s*\(\s*robots_choice\s+IN\s*\(([^)]*)\)",
                        sql)
    assert allowed, "the robots_choice CHECK is not where this test reads it"
    assert set(re.findall(r"'([^']*)'", allowed.group(1))) == {str(c) for c in RobotsChoice}


@pytest.mark.parametrize(("columns", "values"), [
    pytest.param("active", (2,), id="active-not-a-boolean"),
    pytest.param("active", ("yes",), id="active-text"),
    pytest.param("robots_choice", ("ignore",), id="choice-not-in-the-enum"),
    pytest.param("robots_choice", ("Obey",), id="choice-wrong-case"),
    pytest.param("robots_choice", ("custom",), id="custom-with-no-rule"),
    pytest.param("robots_choice, robots_enforce_disallow", ("custom", 2),
                 id="enforce-not-a-boolean"),
    pytest.param("robots_choice, robots_enforce_disallow, robots_crawl_delay_s",
                 ("custom", 0, -1.0), id="negative-custom-delay"),
    pytest.param("robots_choice, robots_enforce_disallow, robots_crawl_delay_s",
                 ("custom", 0, "slow"), id="custom-delay-text"),
    pytest.param("robots_choice, robots_enforce_disallow", ("obey", 1),
                 id="a-rule-under-obey"),
    pytest.param("robots_choice, robots_enforce_disallow", ("default", 0),
                 id="a-rule-under-default"),
    pytest.param("robots_enforce_disallow", (1,), id="a-rule-with-no-choice"),
    pytest.param("robots_crawl_delay_s", (2.0,), id="a-delay-with-no-choice"),
    pytest.param("user_agent", ("",), id="empty-agent"),
    pytest.param("user_agent", ("   ",), id="blank-agent"),
    pytest.param("user_agent", ("\u0645\u062a\u0635\u0641\u062d/1",), id="arabic-agent"),
    pytest.param("user_agent", ("\x85",), id="agent-c1-control"),
    pytest.param("user_agent", ("caf\u00e9/1",), id="agent-accented"),
    pytest.param("user_agent", ("A/1\tB",), id="agent-tab"),
    pytest.param("user_agent", ("A\x7f/1",), id="agent-delete"),
    pytest.param("user_agent", (b"A/1",), id="agent-a-blob"),
    pytest.param("crawl_pace_s", (float("inf"),), id="infinite-pace"),
    pytest.param("robots_choice, robots_enforce_disallow, robots_crawl_delay_s",
                 ("custom", 0, float("inf")), id="infinite-custom-delay"),
    pytest.param("crawl_pace_s", (0.0,), id="zero-pace"),
    pytest.param("crawl_pace_s", (-1.0,), id="negative-pace"),
    pytest.param("crawl_pace_s", ("fast",), id="pace-text"),
])
def test_the_table_refuses_what_a_crawl_could_not_act_on(conn, columns, values):
    """The CHECKs hold even against a writer that is not `save`. A word compared with a
    number is TRUE in SQLite (`'fast' > 0`), which is why the REAL checks test `typeof`."""
    marks = ", ".join("?" for _ in values)
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(f"INSERT INTO source_setting (source_id, {columns}) VALUES (?, {marks})",
                     (_source_id(conn, SHOP), *values))


@pytest.mark.parametrize(("columns", "values"), [
    pytest.param("active", (None,), id="nothing-chosen"),
    pytest.param("active", (0,), id="inactive"),
    pytest.param("robots_choice", ("default",), id="default"),
    pytest.param("robots_choice, robots_enforce_disallow", ("custom", 0),
                 id="custom-site-delay"),
    pytest.param("robots_choice, robots_enforce_disallow, robots_crawl_delay_s",
                 ("custom", 1, 0.0), id="custom-zero-delay"),
    pytest.param("crawl_pace_s", (0.001,), id="tiny-pace"),
    pytest.param("crawl_pace_s", (2,), id="integer-pace-stored-as-real"),
])
def test_the_table_accepts_the_edges_of_what_is_allowed(conn, columns, values):
    """Each refusal above is next to an acceptance, so a CHECK tightened past the bounds
    `config.py` and `robots.decide` already use fails here: a custom delay of 0 means
    "do not wait for this site", and `robots.decide` applies a custom delay as set."""
    marks = ", ".join("?" for _ in values)
    conn.execute(f"INSERT INTO source_setting (source_id, {columns}) VALUES (?, {marks})",
                 (_source_id(conn, SHOP), *values))


def test_a_choice_for_a_source_the_registry_does_not_have_is_refused_by_the_table(conn):
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO source_setting (source_id, active) VALUES (?, 1)", (9999,))


# ---- save and read ----------------------------------------------------------------

def test_every_field_round_trips(conn, manifest):
    chosen = {"active": False, "robots": "custom",
              "robots_custom": {"enforce_disallow": True, "crawl_delay_s": 4.5},
              "user_agent": "HisAgent/2.0", "crawl_pace_s": 1.5}

    stored = save(conn, SHOP, shipped_with(manifest, SHOP), chosen)
    conn.commit()

    assert stored == read(conn, SHOP) == {**chosen, "robots": RobotsChoice.CUSTOM}
    assert isinstance(stored["robots"], RobotsChoice)
    assert save(conn, SHOP, shipped_with(manifest, SHOP), read(conn, SHOP)) == stored, (
        "what read returns is not what save accepts")


def test_a_custom_rule_with_the_sites_own_delay_round_trips(conn, manifest):
    """A null delay under custom means "whatever the site asked for" -- not "no rule"."""
    save(conn, SHOP, shipped_with(manifest, SHOP), {"robots": "custom",
                                "robots_custom": {"enforce_disallow": False}})

    assert read(conn, SHOP)["robots_custom"] == {"enforce_disallow": False,
                                                 "crawl_delay_s": None}


def test_nothing_chosen_reads_empty_and_writes_nothing(conn, manifest):
    assert read(conn, SHOP) == {}
    assert save(conn, SHOP, shipped_with(manifest, SHOP), {}) == {}
    assert _row(conn, SHOP) is None


def test_a_partial_change_keeps_every_field_it_does_not_name(conn, manifest):
    """The panel sending the pace alone must not wipe his robots choice."""
    save(conn, SHOP, shipped_with(manifest, SHOP), {"active": True, "robots": "obey", "user_agent": "A/1"})
    save(conn, SHOP, shipped_with(manifest, SHOP), {"crawl_pace_s": 9.0})

    assert read(conn, SHOP) == {"active": True, "robots": RobotsChoice.OBEY,
                                "user_agent": "A/1", "crawl_pace_s": 9.0}


@pytest.mark.parametrize("field", source_settings.FIELDS)
def test_each_field_clears_back_to_inherit(conn, manifest, field):
    everything = {"active": True, "robots": "custom",
                  "robots_custom": {"enforce_disallow": True, "crawl_delay_s": 2.0},
                  "user_agent": "A/1", "crawl_pace_s": 2.0}
    save(conn, SHOP, shipped_with(manifest, SHOP), everything)
    cleared = {field: None}
    if field == "robots_custom":
        # custom with no rule is refused, so clearing the rule means leaving custom.
        cleared["robots"] = "obey"

    after = save(conn, SHOP, shipped_with(manifest, SHOP), cleared)

    assert field not in after
    assert set(after) == set(everything) - {field} - (
        {"robots_custom"} if field == "robots" else set())


def test_leaving_custom_clears_the_rule_so_it_cannot_come_back_unseen(conn, manifest):
    """`/api/sources/{key}/edit` clears a rule when the choice leaves custom, for the
    reason it gives: left behind, the rule governs the site again the day somebody
    switches back. The same holds here -- and clearing the choice to inherit too."""
    rule = {"enforce_disallow": True, "crawl_delay_s": 7.0}
    for leave_to in ("obey", "default", None):
        save(conn, SHOP, shipped_with(manifest, SHOP), {"robots": "custom", "robots_custom": rule})
        save(conn, SHOP, shipped_with(manifest, SHOP), {"robots": leave_to})
        row = _row(conn, SHOP)
        assert row["robots_enforce_disallow"] is None, leave_to
        assert row["robots_crawl_delay_s"] is None, leave_to
        with pytest.raises(SourceSettingError, match="needs its rule"):
            save(conn, SHOP, shipped_with(manifest, SHOP), {"robots": "custom"})


def test_custom_keeps_the_rule_already_stored_beside_it(conn, manifest):
    """Judged on the row as it will stand: a pace-only change to a custom source keeps
    its rule and is not refused for not re-sending it."""
    save(conn, SHOP, shipped_with(manifest, SHOP), {"robots": "custom",
                                "robots_custom": {"enforce_disallow": True}})
    save(conn, SHOP, shipped_with(manifest, SHOP), {"crawl_pace_s": 2.0})
    save(conn, SHOP, shipped_with(manifest, SHOP), {"robots": "custom"})

    assert read(conn, SHOP)["robots_custom"] == {"enforce_disallow": True,
                                                 "crawl_delay_s": None}


def test_a_change_moves_updated_at(conn, manifest):
    save(conn, SHOP, shipped_with(manifest, SHOP), {"active": True})
    conn.execute("UPDATE source_setting SET updated_at = '2000-01-01T00:00:00Z'")

    save(conn, SHOP, shipped_with(manifest, SHOP), {"crawl_pace_s": 2.0})

    assert _row(conn, SHOP)["updated_at"] > "2000-01-01T00:00:00Z"


def test_an_empty_agent_clears_as_an_empty_setting_does(conn, manifest):
    """`settings.save`'s rule: an emptied text box is "nothing of my own"."""
    save(conn, SHOP, shipped_with(manifest, SHOP), {"user_agent": "A/1"})
    save(conn, SHOP, shipped_with(manifest, SHOP), {"user_agent": "   "})

    assert "user_agent" not in read(conn, SHOP)
    assert save(conn, SHOP, shipped_with(manifest, SHOP), {"user_agent": "  B/2  "})["user_agent"] == "B/2"


def test_a_rename_carries_his_choices(conn, manifest):
    """Keyed on `source_id`, so `rename_source` -- which moves the tables that name a
    source by its key -- moves these without knowing they exist."""
    save(conn, DIRECTORY, shipped_with(manifest, DIRECTORY), {"crawl_pace_s": 4.0})

    rename_source(conn, DIRECTORY, "muqawil_renamed")

    assert read(conn, "muqawil_renamed") == {"crawl_pace_s": 4.0}
    assert read(conn, DIRECTORY) == {}


def test_an_unknown_source_is_refused_and_nothing_is_written(conn, manifest):
    """In the manifest is not enough: the row hangs off `source_site`, and a price
    source enters it at its first ingest."""
    for key in ("NOBODY", NEVER_CRAWLED):
        with pytest.raises(UnknownSourceError, match="source registry"):
            save(conn, key, shipped_with(manifest, key), {"active": True})
    assert conn.execute("SELECT COUNT(*) FROM source_setting").fetchone()[0] == 0


@pytest.mark.parametrize(("changes", "says"), [
    pytest.param({"actve": True}, "not per-source choices", id="unknown-field"),
    pytest.param({"active": 1}, "true, false or null", id="active-an-integer"),
    pytest.param({"active": "true"}, "true, false or null", id="active-text"),
    pytest.param({"robots": "ignore"}, "must be one of", id="choice-the-code-lacks"),
    pytest.param({"robots": "Obey"}, "must be one of", id="choice-wrong-case"),
    pytest.param({"robots": "custom"}, "needs its rule", id="custom-with-no-rule"),
    pytest.param({"robots": "custom", "robots_custom": None}, "needs its rule",
                 id="custom-with-a-cleared-rule"),
    pytest.param({"robots_custom": {"enforce_disallow": True}}, "needs robots = custom",
                 id="a-rule-with-no-choice"),
    pytest.param({"robots": "obey", "robots_custom": {"enforce_disallow": True}},
                 "needs robots = custom", id="a-rule-beside-obey"),
    pytest.param({"robots": None, "robots_custom": {"enforce_disallow": True}},
                 "needs robots = custom", id="a-rule-beside-inherit"),
    pytest.param({"robots": "custom", "robots_custom": {"crawl_delay_s": 2.0}},
                 "a custom robots rule is", id="a-rule-with-no-enforce"),
    pytest.param({"robots": "custom",
                  "robots_custom": {"enforce_disallow": True, "delay": 2.0}},
                 "a custom robots rule is", id="a-rule-with-a-stray-key"),
    pytest.param({"robots": "custom", "robots_custom": "strict"},
                 "a custom robots rule is", id="a-rule-not-a-mapping"),
    pytest.param({"robots": "custom", "robots_custom": {"enforce_disallow": 1}},
                 "true or false", id="enforce-an-integer"),
    pytest.param({"robots": "custom",
                  "robots_custom": {"enforce_disallow": False, "crawl_delay_s": -1}},
                 "0 or more", id="negative-custom-delay"),
    pytest.param({"robots": "custom",
                  "robots_custom": {"enforce_disallow": False, "crawl_delay_s": "5"}},
                 "number of seconds", id="custom-delay-text"),
    pytest.param({"crawl_pace_s": 0}, "more than 0", id="zero-pace"),
    pytest.param({"crawl_pace_s": -2.0}, "more than 0", id="negative-pace"),
    pytest.param({"crawl_pace_s": math.nan}, "number of seconds", id="nan-pace"),
    pytest.param({"crawl_pace_s": math.inf}, "number of seconds", id="infinite-pace"),
    pytest.param({"crawl_pace_s": True}, "number of seconds", id="boolean-pace"),
    pytest.param({"crawl_pace_s": "3"}, "number of seconds", id="pace-text"),
    pytest.param({"user_agent": 7}, "text or null", id="agent-not-text"),
    pytest.param({"user_agent": "A/1\r\nX-Injected: 1"}, "one line", id="agent-two-lines"),
    pytest.param({"user_agent": "A/1\x00"}, "one line", id="agent-control-character"),
    pytest.param({"user_agent": "A\r/1"}, "one line", id="agent-carriage-return"),
    pytest.param({"user_agent": "A\x0b/1"}, "one line", id="agent-vertical-tab"),
    pytest.param({"user_agent": "A\x1f/1"}, "one line", id="agent-unit-separator"),
    pytest.param({"user_agent": "A\x7f/1"}, "one line", id="agent-delete"),
    pytest.param({"user_agent": "\u0645\u062a\u0635\u0641\u062d/1"}, "printable ASCII",
                 id="agent-arabic"),
    pytest.param({"user_agent": "A\x85/1"}, "printable ASCII", id="agent-c1-control"),
    pytest.param({"user_agent": "caf\u00e9/1"}, "printable ASCII", id="agent-accented"),
    pytest.param({"crawl_pace_s": 10**400}, "finite", id="pace-too-large-for-a-float"),
    pytest.param({"robots": "custom",
                  "robots_custom": {"enforce_disallow": False, "crawl_delay_s": 10**400}},
                 "finite", id="custom-delay-too-large-for-a-float"),
    pytest.param({1: True}, "not per-source choices", id="a-key-that-is-not-text"),
    pytest.param({1: True, "actve": True}, "not per-source choices",
                 id="a-key-that-is-not-text-beside-a-misspelt-one"),
])
def test_a_refused_choice_says_why_and_writes_nothing(conn, manifest, changes, says):
    save(conn, SHOP, shipped_with(manifest, SHOP), {"crawl_pace_s": 8.0})
    before = _row(conn, SHOP)

    with pytest.raises(SourceSettingError, match=re.escape(says)):
        save(conn, SHOP, shipped_with(manifest, SHOP), changes)

    assert _row(conn, SHOP) == before


def test_an_unprobed_source_cannot_be_activated_as_the_manifest_refuses_it(conn, manifest):
    """`SourceEntry._probe_placeholder_is_inactive`: TBD-probe has no collector to run."""
    with pytest.raises(SourceSettingError, match="TBD-probe"):
        save(conn, UNPROBED, shipped_with(manifest, UNPROBED), {"active": True})
    assert _row(conn, UNPROBED) is None

    assert save(conn, UNPROBED, shipped_with(manifest, UNPROBED), {"active": False}) == {"active": False}
    assert save(conn, UNPROBED, shipped_with(manifest, UNPROBED), {"crawl_pace_s": 2.0})["crawl_pace_s"] == 2.0


def test_a_directory_source_takes_every_choice(conn, manifest):
    """It has no family in the manifest, so nothing stands in for TBD-probe; and it is
    the kind of source that had nowhere to keep a choice before this table."""
    chosen = save(conn, DIRECTORY, shipped_with(manifest, DIRECTORY), {
        "active": True, "robots": "obey", "user_agent": "Dir/1", "crawl_pace_s": 5.0})

    assert chosen == {"active": True, "robots": RobotsChoice.OBEY, "user_agent": "Dir/1",
                      "crawl_pace_s": 5.0}


# ---- effective: his choice > the shipped entry > no opinion ---------------------------

NOTHING_SAID = SourceRules(active=False, robots=RobotsChoice.DEFAULT, robots_custom=None,
                         user_agent=None, crawl_pace_s=None)


def test_a_price_source_he_never_touched_is_what_it_shipped_with(conn, manifest):
    assert effective(conn, SHOP, manifest.get(SHOP)) == SourceRules(
        active=True, robots=RobotsChoice.OBEY, robots_custom=None,
        user_agent="ShippedAgent/1.0", crawl_pace_s=3.0)


def test_his_choice_wins_over_what_the_source_shipped_with(conn, manifest):
    save(conn, SHOP, shipped_with(manifest, SHOP), {"active": False, "robots": "custom",
                                "robots_custom": {"enforce_disallow": True,
                                                  "crawl_delay_s": 0.0},
                                "user_agent": "HisAgent/2.0", "crawl_pace_s": 1.0})

    assert effective(conn, SHOP, manifest.get(SHOP)) == SourceRules(
        active=False, robots=RobotsChoice.CUSTOM,
        robots_custom={"enforce_disallow": True, "crawl_delay_s": 0.0},
        user_agent="HisAgent/2.0", crawl_pace_s=1.0)


def test_a_field_he_has_not_chosen_still_inherits_beside_one_he_has(conn, manifest):
    """Per field, not per row: one choice stored does not erase the shipped others."""
    save(conn, SHOP, shipped_with(manifest, SHOP), {"crawl_pace_s": 10.0})

    rules = effective(conn, SHOP, manifest.get(SHOP))

    assert rules.crawl_pace_s == 10.0
    assert (rules.active, rules.robots, rules.user_agent) == (
        True, RobotsChoice.OBEY, "ShippedAgent/1.0")


def test_a_cleared_choice_falls_back_to_what_shipped(conn, manifest):
    save(conn, SHOP, shipped_with(manifest, SHOP), {"user_agent": "HisAgent/2.0", "active": False})
    save(conn, SHOP, shipped_with(manifest, SHOP), {"user_agent": None, "active": None})

    assert effective(conn, SHOP, manifest.get(SHOP)) == SourceRules(
        active=True, robots=RobotsChoice.OBEY, robots_custom=None,
        user_agent="ShippedAgent/1.0", crawl_pace_s=3.0)


def test_his_default_is_a_choice_and_beats_a_shipped_obey(conn, manifest):
    """'default' and not-chosen are two different things: 'default' follows the
    tool-wide setting even where the source shipped `obey`."""
    save(conn, SHOP, shipped_with(manifest, SHOP), {"robots": "default"})

    assert effective(conn, SHOP, manifest.get(SHOP)).robots is RobotsChoice.DEFAULT


def test_the_choice_and_its_rule_move_together(conn):
    """A shipped custom rule is not inherited under his `obey`; it is meaningless there."""
    shipped_custom = Manifest.model_validate({"sources": [_entry(
        SHOP, robots="custom", robots_custom={"enforce_disallow": True, "crawl_delay_s": 9})]})
    assert effective(conn, SHOP, shipped_custom.get(SHOP)).robots_custom == {
        "enforce_disallow": True, "crawl_delay_s": 9}

    save(conn, SHOP, shipped_with(shipped_custom, SHOP), {"robots": "obey"})

    rules = effective(conn, SHOP, shipped_custom.get(SHOP))
    assert (rules.robots, rules.robots_custom) == (RobotsChoice.OBEY, None)


def test_a_shipped_rule_under_a_choice_that_ignores_it_is_refused_and_never_handed_on(
        conn, manifest):
    """The manifest refuses a leftover rule beside `obey`, as the table does. An entry
    that got one past validation anyway (`model_copy` does not validate) still hands on
    no rule: the effective answer keeps the table's invariant."""
    leftover = {"enforce_disallow": False, "crawl_delay_s": 30}
    with pytest.raises(ValueError, match="needs robots = custom"):
        Manifest.model_validate({"sources": [_entry(SHOP, robots="obey",
                                                    robots_custom=leftover)]})

    bypassed = manifest.get(SHOP).model_copy(update={"robots_custom": leftover})
    assert effective(conn, SHOP, bypassed).robots_custom is None


def test_a_misspelt_shipped_choice_fails_loudly_rather_than_acting_as_default(
        conn, manifest):
    """Refused where the manifest loads -- so the panel's `/edit` answers 400 -- and,
    for an entry that got past that, refused by `effective` with the same sentence."""
    with pytest.raises(ValueError, match="robots must be one of"):
        Manifest.model_validate({"sources": [_entry(SHOP, robots="obeys")]})

    bypassed = manifest.get(SHOP).model_copy(update={"robots": "obeys"})
    with pytest.raises(SourceSettingError, match="robots must be one of"):
        effective(conn, SHOP, bypassed)


def test_a_price_source_that_shipped_nothing_has_no_opinion(conn, manifest):
    assert effective(conn, PLAIN, manifest.get(PLAIN)) == NOTHING_SAID


def test_a_directory_source_has_no_shipped_layer(conn, manifest):
    """Not in `sources.yaml`, so between his choice and the general rules there is
    nothing -- and before this table there was nothing above the general rules either."""
    assert effective(conn, DIRECTORY, None) == NOTHING_SAID

    save(conn, DIRECTORY, shipped_with(manifest, DIRECTORY), {"robots": "obey", "crawl_pace_s": 5.0})

    assert effective(conn, DIRECTORY, None) == SourceRules(
        active=False, robots=RobotsChoice.OBEY, robots_custom=None,
        user_agent=None, crawl_pace_s=5.0)


def test_a_price_source_never_crawled_still_gets_what_it_shipped_with(conn, manifest):
    """Its first crawl runs before its first ingest registers it in `source_site`, and
    that crawl still needs its shipped agent: a Zid shop answers 403 to any other."""
    assert read(conn, NEVER_CRAWLED) == {}
    rules = effective(conn, NEVER_CRAWLED, manifest.get(NEVER_CRAWLED))
    assert rules.user_agent == "ZidNeedsThis/1.0"


# ---- the bounds agree wherever a pace is written, and the edges the review found -----

@pytest.mark.parametrize(("value", "allowed"), [
    pytest.param(0, False, id="zero"),
    pytest.param(0.001, True, id="a-thousandth"),
    pytest.param(math.inf, False, id="infinite"),
    pytest.param(math.nan, False, id="nan"),
    pytest.param(-1, False, id="negative"),
    pytest.param(10**400, False, id="too-large-for-a-float"),
    pytest.param(True, False, id="a-boolean"),
    pytest.param("5", False, id="a-numeric-string"),
])
def test_a_pace_means_the_same_in_the_manifest_the_module_and_the_table(conn, manifest,
                                                                        value, allowed):
    """THREE PLACES HOLD THE PACE'S BOUND -- `SourceEntry.crawl_pace_s` and `save`, both
    through `config.checked_seconds`, and the table's CHECK -- and a value one of them takes and another refuses is a pace that
    works from the manifest and fails from the panel, or the reverse. NaN reaches the
    table as NULL, which is "not chosen", so the table "accepting" it stores no pace."""
    from scrapex.config import SourceEntry

    try:
        SourceEntry.model_validate(_entry(SHOP, crawl_pace_s=value))
        by_manifest = True
    except ValueError:
        by_manifest = False
    try:
        save(conn, SHOP, shipped_with(manifest, SHOP), {"crawl_pace_s": value})
        by_module = True
    except SourceSettingError:
        by_module = False
    assert (by_manifest, by_module) == (allowed, allowed)

    # THE TABLE IS ASKED ABOUT NUMBERS ONLY. A bool or a string never reaches it -- both
    # doors refuse them above -- and SQLite's REAL affinity would turn "5" into 5.0 before
    # any CHECK ran, so the table cannot be the one to refuse a numeric string.
    if type(value) not in (int, float):
        return
    try:
        # Bound as text and cast, because sqlite3 cannot bind an int past 64 bits; the
        # CAST turns 10**400 into the infinity SQLite would hold for it.
        conn.execute("INSERT INTO source_setting (source_id, crawl_pace_s) "
                     "VALUES (?, CAST(? AS REAL))", (_source_id(conn, PLAIN), repr(value)
                                                    if isinstance(value, int)
                                                    else value))
        stored = conn.execute("SELECT crawl_pace_s FROM source_setting WHERE source_id = ?",
                              (_source_id(conn, PLAIN),)).fetchone()[0]
        by_table = stored is not None
    except sqlite3.IntegrityError:
        by_table = False
    assert by_table is allowed


def test_the_custom_rule_takes_exactly_the_knobs_the_crawl_obeys(conn, manifest):
    """`robots.RobotsCustom` is the rule the fetcher builds. A knob added there and not
    accepted here would be a rule the panel could never write."""
    from dataclasses import asdict

    from scrapex.robots import RobotsCustom

    rule = asdict(RobotsCustom(enforce_disallow=True, crawl_delay_s=2.0))

    assert save(conn, SHOP, shipped_with(manifest, SHOP), {"robots": "custom", "robots_custom": rule}
                )["robots_custom"] == rule


def test_choices_that_are_not_a_mapping_are_refused(conn, manifest):
    with pytest.raises(SourceSettingError, match="mapping"):
        save(conn, SHOP, shipped_with(manifest, SHOP), [("active", True)])


def test_an_unknown_source_reads_as_a_sentence_not_a_quoted_key(conn, manifest):
    """`str()` of a KeyError is its argument's repr, so the sentence reached the panel in
    quotes. It is still a LookupError, which is what a caller catching lookups expects."""
    with pytest.raises(LookupError) as raised:
        save(conn, "NOBODY", shipped_with(manifest, "NOBODY"), {"active": True})

    assert not isinstance(raised.value, KeyError)
    assert str(raised.value) == raised.value.args[0]


def test_a_source_whose_family_went_back_to_tbd_probe_is_not_active(conn, manifest):
    """A later release can put a family back to TBD-probe after he activated the source.
    There is then no collector, so `effective` reads it inactive whatever was stored --
    and an unrelated edit to it is not refused for an activation he made earlier."""
    save(conn, SHOP, shipped_with(manifest, SHOP), {"active": True})
    reverted = Manifest.model_validate({"sources": [_entry(SHOP, family="TBD-probe")]})

    assert effective(conn, SHOP, reverted.get(SHOP)).active is False
    assert save(conn, SHOP, shipped_with(reverted, SHOP), {"crawl_pace_s": 2.0})["crawl_pace_s"] == 2.0
    with pytest.raises(SourceSettingError, match="TBD-probe"):
        save(conn, SHOP, shipped_with(reverted, SHOP), {"active": True})


def test_the_shipped_rule_handed_out_is_a_copy(conn):
    """A consumer that edits the rule it was handed must not be editing the manifest
    every later crawl of every source reads."""
    rule = {"enforce_disallow": True, "crawl_delay_s": 9}
    shipped = Manifest.model_validate({"sources": [_entry(
        SHOP, robots="custom", robots_custom=rule)]})

    handed = effective(conn, SHOP, shipped.get(SHOP)).robots_custom
    handed["crawl_delay_s"] = 0

    assert shipped.get(SHOP).robots_custom == {"enforce_disallow": True, "crawl_delay_s": 9}
    assert effective(conn, SHOP, shipped.get(SHOP)).robots_custom == {"enforce_disallow": True,
                                                           "crawl_delay_s": 9.0}


@pytest.mark.parametrize("rule", [
    pytest.param({"crawl_delay_s": 5}, id="no-enforce"),
    pytest.param({"enforce_disallow": True, "crawl_delay_s": -1}, id="negative-delay"),
    pytest.param({"enforce_disallow": "yes"}, id="enforce-text"),
    pytest.param({"enforce_disallow": True, "delay": 5}, id="stray-key"),
])
def test_a_shipped_custom_rule_is_held_to_the_rules_a_saved_one_is(conn, manifest, rule):
    """ONE CHECKER, TWO DOORS. A rule `save` refuses, the manifest refuses with the same
    sentence; and one that got past the manifest anyway is refused by `effective`
    rather than read with defaults filled in."""
    with pytest.raises(SourceSettingError) as by_panel:
        save(conn, SHOP, shipped_with(manifest, SHOP),
             {"robots": "custom", "robots_custom": rule})
    sentence = str(by_panel.value).removeprefix(f"{SHOP}: ")
    with pytest.raises(ValueError) as by_manifest:
        Manifest.model_validate({"sources": [_entry(SHOP, robots="custom",
                                                    robots_custom=rule)]})
    assert sentence in str(by_manifest.value)

    bypassed = manifest.get(SHOP).model_copy(update={"robots": "custom",
                                                     "robots_custom": rule})
    with pytest.raises(SourceSettingError, match=re.escape(sentence)):
        effective(conn, SHOP, bypassed)


def test_the_schema_page_says_what_an_empty_field_follows():
    """Not only the shipped value: a directory source shipped nothing, and its empty
    field follows his general settings."""
    from scrapex.reports import TABLE_GROUPS

    purpose = dict(row for _title, _note, rows in TABLE_GROUPS for row in rows)["source_setting"]

    assert "shipped with" in purpose and "general settings" in purpose


def test_one_sources_change_never_touches_anothers(conn, manifest):
    """Every statement `save` runs is scoped to ONE source: the read of the stored row
    and the UPDATE both. Unscoped, the third save below would rewrite the directory's row
    or judge SHOP's change against it."""
    save(conn, SHOP, shipped_with(manifest, SHOP), {"crawl_pace_s": 2.0})
    save(conn, DIRECTORY, shipped_with(manifest, DIRECTORY), {"user_agent": "Dir/1"})
    save(conn, SHOP, shipped_with(manifest, SHOP), {"crawl_pace_s": 3.0})

    assert read(conn, DIRECTORY) == {"user_agent": "Dir/1"}
    assert read(conn, SHOP) == {"crawl_pace_s": 3.0}


def test_a_rule_on_one_source_does_not_decide_anothers_change(conn, manifest):
    save(conn, DIRECTORY, shipped_with(manifest, DIRECTORY), {"robots": "custom",
                                     "robots_custom": {"enforce_disallow": True}})

    with pytest.raises(SourceSettingError, match="needs its rule"):
        save(conn, SHOP, shipped_with(manifest, SHOP), {"robots": "custom"})


def test_an_empty_change_to_a_stored_row_writes_nothing(conn, manifest):
    """No field named is no write: the row keeps its date, because nothing changed."""
    save(conn, SHOP, shipped_with(manifest, SHOP), {"crawl_pace_s": 2.0})
    conn.execute("UPDATE source_setting SET updated_at = '2000-01-01T00:00:00Z'")

    assert save(conn, SHOP, shipped_with(manifest, SHOP), {}) == {"crawl_pace_s": 2.0}
    assert _row(conn, SHOP)["updated_at"] == "2000-01-01T00:00:00Z"


def test_a_new_row_is_stamped_now_in_the_warehouses_own_format(conn, manifest):
    """The format every stored timestamp uses (`payload.py`), UTC, and the moment of the
    write -- not a constant and not epoch seconds."""
    from datetime import UTC, datetime

    save(conn, SHOP, shipped_with(manifest, SHOP), {"crawl_pace_s": 2.0})
    stamp = _row(conn, SHOP)["updated_at"]

    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", stamp)
    written = datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    assert abs((datetime.now(UTC) - written).total_seconds()) < 120


def test_a_rule_without_a_choice_names_what_is_missing(conn, manifest):
    with pytest.raises(SourceSettingError, match="choice is not set"):
        save(conn, SHOP, shipped_with(manifest, SHOP), {"robots_custom": {"enforce_disallow": True}})


def test_the_module_names_the_same_nothing_said_this_file_expects():
    """`NO_OPINION` is the bottom layer and what the command line's `--plan` crawls
    under; written out here so a change to it is a change somebody sees."""
    assert source_settings.NO_OPINION == NOTHING_SAID


def test_another_sources_entry_is_refused_rather_than_layered(conn, manifest):
    """A caller holding the wrong entry would hand one shop's agent to another."""
    with pytest.raises(ValueError, match="manifest entry"):
        effective(conn, PLAIN, manifest.get(SHOP))


def test_a_built_directory_ships_on_and_nothing_else(conn):
    """`directories.Directory` is a directory's shipped layer: on, and no robots, agent
    or pace of its own -- so those fall to his general settings, and clearing a choice
    returns `active` to on (his ruling)."""
    directory = directories.get(DIRECTORY)

    assert effective(conn, DIRECTORY, directory) == SourceRules(
        active=True, robots=RobotsChoice.DEFAULT, robots_custom=None,
        user_agent=None, crawl_pace_s=None)
    save(conn, DIRECTORY, directory, {"active": False})
    assert effective(conn, DIRECTORY, directory).active is False
    save(conn, DIRECTORY, directory, {"active": None})
    assert effective(conn, DIRECTORY, directory).active is True


def test_what_a_source_ships_with_is_found_in_the_manifest_then_the_directories(manifest):
    assert shipped_with(manifest, SHOP) is manifest.get(SHOP)
    assert shipped_with(manifest, DIRECTORY) == directories.get(DIRECTORY)
    assert shipped_with(manifest, "NOBODY") is None


def test_another_directorys_registry_entry_is_refused(conn):
    with pytest.raises(ValueError, match="directory"):
        effective(conn, DIRECTORY, directories.get("oman_tenderboard"))


#: Every real agent has spaces in it, and the printable range starts AT the space.
REAL_AGENT = "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0 Safari/537.36"


def test_a_real_agent_with_spaces_is_taken_at_every_door(conn, manifest):
    """The refusals above are all about what is outside 0x20-0x7E; this is the edge on
    the inside. A range that began one past the space would refuse every browser's
    agent -- from the panel, in the table and in the manifest alike."""
    from scrapex.config import SourceEntry, checked_user_agent

    assert save(conn, SHOP, shipped_with(manifest, SHOP),
                {"user_agent": REAL_AGENT})["user_agent"] == REAL_AGENT
    conn.execute("INSERT INTO source_setting (source_id, user_agent) VALUES (?, ?)",
                 (_source_id(conn, PLAIN), REAL_AGENT))
    assert checked_user_agent(REAL_AGENT) == REAL_AGENT
    assert SourceEntry.model_validate(_entry(SHOP, user_agent=REAL_AGENT)).user_agent \
        == REAL_AGENT


def test_a_shipped_custom_choice_with_no_rule_is_refused_when_the_manifest_loads(
        conn, manifest):
    """At the door, and -- for an entry that got past it -- by `effective`, rather than
    handed on as custom-with-no-rule for `robots.decide` to refuse mid-crawl."""
    with pytest.raises(ValueError, match="needs its rule"):
        Manifest.model_validate({"sources": [_entry(SHOP, robots="custom")]})

    bypassed = manifest.get(SHOP).model_copy(update={"robots": "custom",
                                                     "robots_custom": None})
    with pytest.raises(SourceSettingError, match="a custom robots rule is"):
        effective(conn, SHOP, bypassed)


def test_a_directorys_own_shipped_answer_is_the_one_read(conn):
    """Not "every directory is on": the registry entry's own `active` is what ships."""
    from dataclasses import replace

    switched_off = replace(directories.get(DIRECTORY), active=False)

    assert effective(conn, DIRECTORY, switched_off).active is False
    assert effective(conn, DIRECTORY, directories.get(DIRECTORY)).active is True


def test_an_unprobed_sources_off_is_explained_as_the_sources_not_his(conn, manifest):
    """`layered` forces a TBD-probe source off whatever he chose, so the off the panel
    shows is the source's -- saying "your choice" beside a value he did not choose
    would send him to clear a choice that changes nothing."""
    save(conn, SHOP, shipped_with(manifest, SHOP), {"active": True})
    reverted = Manifest.model_validate({"sources": [_entry(SHOP, family="TBD-probe")]})

    active = source_settings.explained(conn, SHOP, reverted.get(SHOP))["active"]

    assert (active["value"], active["origin"]) == (False, "source")
