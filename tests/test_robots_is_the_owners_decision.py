"""The owner decides per site, and the decision is never silent.

Three things have to be true for this to be a feature rather than a dropdown:

  1. Looking at a site tells the truth about what it says — including the one
     fact that decides everything, whether obeying would leave the source
     unable to crawl at all.
  2. Every one of the three choices produces the behaviour it names.
  3. Whatever happens, the run can say WHY afterwards. A crawl that skipped
     pages or ran slow and cannot explain itself is how a source quietly stops
     being collected — the same failure `reclaim_orphaned_jobs` exists for, one
     layer up.

No network in any of it: robots.txt arrives as text.
"""
from __future__ import annotations

import pytest

from scrapex.robots import (Decision, RobotsChoice, RobotsCustom, decide,
                            inspect)

# A file shaped like the ones this actually meets: a general block, a delay,
# and a named exclusion for one crawler.
SITE = """
User-agent: *
Disallow: /admin/
Crawl-delay: 5
Allow: /

User-agent: GreedyBot
Disallow: /
"""

# The muqawil shape: everything allowed for `*`, and named AI crawlers refused.
NAMES_US = """
User-agent: *
Allow: /

User-agent: ScrapeX
Disallow: /
"""


# ---- 1. looking -------------------------------------------------------------

def test_looking_says_what_the_site_asks_of_us():
    report = inspect("https://shop.test/products", SITE, user_agent="ScrapeX/1.0")

    assert report.found
    assert report.host == "shop.test"
    assert report.crawl_delay_s == 5.0
    assert not report.base_url_disallowed
    assert not report.names_us, "this file does not name us; only GreedyBot"
    assert "5s between requests" in report.summary()


def test_looking_says_when_the_site_named_us_by_name():
    """The most important single fact in the report. A site that names your
    crawler has thought about your crawler."""
    report = inspect("https://muqawil.test/companies", NAMES_US, user_agent="ScrapeX/1.0")

    assert report.names_us == "ScrapeX"
    assert report.base_url_disallowed
    assert "names ScrapeX specifically" in report.summary()


def test_looking_warns_when_obeying_would_leave_nothing_to_crawl():
    """THE ANSWER THAT DECIDES THE CHOICE. Picking `obey` for a site that
    disallows the pages this source is for does not make the crawl polite — it
    makes it empty, and an empty crawl reports success. The owner has to be able
    to see that before choosing, not by watching a run return nothing."""
    blocked = inspect("https://muqawil.test/companies", NAMES_US, user_agent="ScrapeX/1.0")
    open_site = inspect("https://shop.test/products", SITE, user_agent="ScrapeX/1.0")

    assert blocked.obeying_would_block_everything
    assert not open_site.obeying_would_block_everything


def test_the_rules_shown_are_the_ones_that_touch_us():
    """A report that says "disallowed" without the line that disallowed it is
    asking the owner to take our word for it."""
    report = inspect("https://shop.test/products", SITE, user_agent="ScrapeX/1.0")

    kinds = {(rule.kind, rule.value) for rule in report.rules}
    assert ("disallow", "/admin/") in kinds
    assert ("crawl-delay", "5") in kinds
    assert all(rule.agent in ("*", "ScrapeX") for rule in report.rules), (
        "a rule aimed at GreedyBot is being shown as though it bound us")


def test_a_site_with_no_robots_file_has_not_refused_anything():
    report = inspect("https://plain.test/x", None)

    assert not report.found
    assert not report.obeying_would_block_everything
    assert "asks for nothing" in report.summary()


def test_an_unreadable_file_is_not_reported_as_an_empty_one():
    """"No rules" and "we could not read the rules" are different sentences and
    the owner would act differently on each."""
    report = inspect("https://down.test/x", None, unreadable="503 from the site")

    assert report.unreadable
    assert not report.found
    assert "could not be read" in report.summary()
    assert "503" in report.summary()


# ---- 2. choosing ------------------------------------------------------------

@pytest.fixture
def site():
    return inspect("https://shop.test/products", SITE, user_agent="ScrapeX/1.0")


def test_obey_refuses_a_disallowed_path(site):
    verdict = decide(site, RobotsChoice.OBEY, url_disallowed=True)

    assert not verdict.may_fetch
    assert verdict.delay_s == 5.0, "obeying means the delay too, not only the paths"
    assert "not fetched" in verdict.reason


def test_the_default_follows_the_tool_setting_in_both_directions(site):
    lenient = decide(site, RobotsChoice.DEFAULT, url_disallowed=True,
                     tool_default_obeys=False)
    strict = decide(site, RobotsChoice.DEFAULT, url_disallowed=True,
                    tool_default_obeys=True)

    assert lenient.may_fetch and "crawled anyway" in lenient.reason
    assert not strict.may_fetch
    assert "tool default" in lenient.reason and "tool default" in strict.reason, (
        "the log does not say the behaviour came from the setting, so changing "
        "the setting later looks like the source changed its mind")


def test_a_custom_rule_overrides_both_the_site_and_the_setting(site):
    """The escape hatch: this site, and only this site."""
    verdict = decide(site, RobotsChoice.CUSTOM,
                     custom=RobotsCustom(enforce_disallow=True, crawl_delay_s=1.0),
                     tool_default_obeys=False, url_disallowed=True)

    assert not verdict.may_fetch, "the custom rule said enforce, the setting said not to"
    assert verdict.delay_s == 1.0, "the custom delay must win over the site's 5s"
    assert "custom rule for this site" in verdict.reason


def test_a_custom_rule_with_no_delay_keeps_the_sites_own(site):
    verdict = decide(site, RobotsChoice.CUSTOM,
                     custom=RobotsCustom(enforce_disallow=False), url_disallowed=False)

    assert verdict.delay_s == 5.0, (
        "leaving the delay unset must mean 'whatever the site asked for', not 'none'")


def test_custom_with_no_rule_stored_is_refused_not_defaulted():
    """Falling back to the tool default here would hand the owner the exact
    behaviour he chose CUSTOM to escape, under his own label."""
    report = inspect("https://shop.test/x", SITE)

    with pytest.raises(ValueError, match="custom robots rule"):
        decide(report, RobotsChoice.CUSTOM, custom=None)


def test_a_site_with_no_file_is_fetchable_under_every_choice():
    report = inspect("https://plain.test/x", None)

    for choice in (RobotsChoice.DEFAULT, RobotsChoice.OBEY):
        verdict = decide(report, choice, url_disallowed=True, tool_default_obeys=True)
        assert verdict.may_fetch, (
            f"{choice} refused a path on a site that published no rules at all")
        assert "nothing to obey" in verdict.reason


# ---- 3. saying why ----------------------------------------------------------

@pytest.mark.parametrize("choice,custom", [
    (RobotsChoice.DEFAULT, None),
    (RobotsChoice.OBEY, None),
    (RobotsChoice.CUSTOM, RobotsCustom(enforce_disallow=True)),
])
def test_every_decision_can_explain_itself(site, choice, custom):
    """A crawl that was slow, or that skipped pages, must be explainable
    afterwards from the log alone."""
    verdict = decide(site, choice, custom=custom, url_disallowed=True)

    assert isinstance(verdict, Decision)
    assert site.host in verdict.reason, "the reason does not say which site"
    assert len(verdict.reason) > 30, f"not a reason, a label: {verdict.reason!r}"
    assert ("not fetched" in verdict.reason) != verdict.may_fetch, (
        "the reason and the verdict disagree, which is worse than either alone")


# ---- the route the panel reads ----------------------------------------------

def test_the_look_route_reports_a_site_it_could_not_reach_as_unreachable(tmp_path):
    """"The site asks for nothing" and "we could not find out" lead the owner to
    OPPOSITE choices, so the route must never let one wear the other's clothes.

    Driven against a domain that does not resolve, because that is the failure
    a person actually meets — a typo'd base_url, or a site that is down at the
    moment he opens the screen.
    """
    import os
    import subprocess
    import sys

    from fastapi.testclient import TestClient

    manifest = tmp_path / "sources.yaml"
    manifest.write_text("""
sources:
  - source_key: PROBE
    source_name: Probe
    base_url: https://nothing.invalid
    family: custom-json-api
    cadence: daily
    authority: shop
    active: true
    currency: EGP
    default_region: EG
    vat_mode: excl
    robots: obey
    extract:
      - kind: product_prices
        scope: census
""", encoding="utf-8")
    database = tmp_path / "engine.db"
    made = subprocess.run([sys.executable, "-m", "scrapex.cli", "init-db",
                           "--db", str(database)],
                          env=dict(os.environ, SCRAPEX_SOURCES=str(manifest)),
                          capture_output=True, text=True, timeout=300)
    assert made.returncode == 0, made.stderr

    from scrapex.webui.app import create_app

    client = TestClient(create_app(db_path=str(database), manifest_path=str(manifest)))
    answer = client.get("/api/sources/PROBE/robots")

    assert answer.status_code == 200
    body = answer.json()
    assert body["unreadable"], "an unreachable site is being reported as having no rules"
    assert not body["found"]
    assert "could not be read" in body["summary"]
    assert body["choice"] == "obey", "the route does not report the source's own choice"
    # It must still say what would happen, rather than leaving the screen blank.
    assert body["on_a_disallowed_path"]["reason"]


def test_the_look_route_refuses_a_source_that_does_not_exist(tmp_path):
    import os
    import subprocess
    import sys

    from fastapi.testclient import TestClient

    manifest = tmp_path / "sources.yaml"
    # One real source, because a manifest with none is refused by the model —
    # correctly: a warehouse with nothing to collect is a mistake, not a state.
    manifest.write_text("""
sources:
  - source_key: PRESENT
    source_name: Present
    base_url: https://present.invalid
    family: custom-json-api
    cadence: daily
    authority: shop
    active: true
    currency: EGP
    default_region: EG
    vat_mode: excl
    extract:
      - kind: product_prices
        scope: census
""", encoding="utf-8")
    database = tmp_path / "engine.db"
    subprocess.run([sys.executable, "-m", "scrapex.cli", "init-db", "--db", str(database)],
                   env=dict(os.environ, SCRAPEX_SOURCES=str(manifest)),
                   capture_output=True, timeout=300)

    from scrapex.webui.app import create_app

    client = TestClient(create_app(db_path=str(database), manifest_path=str(manifest)))
    assert client.get("/api/sources/NOPE/robots").status_code == 404


def test_switching_away_from_custom_clears_the_rule_it_leaves_behind(tmp_path):
    """The edit route drops nulls so a partial edit cannot wipe a field, which
    means a client CANNOT clear the custom rule by sending null. Left behind, it
    sits under a choice that ignores it and reads as "this site is customised"
    on every later open — until someone switches back and is governed by a rule
    they last saw weeks ago."""
    import os
    import subprocess
    import sys

    from fastapi.testclient import TestClient

    manifest = tmp_path / "sources.yaml"
    manifest.write_text("""
sources:
  - source_key: SWITCHY
    source_name: Switchy
    base_url: https://switchy.invalid
    family: custom-json-api
    cadence: daily
    authority: shop
    active: true
    currency: EGP
    default_region: EG
    vat_mode: excl
    robots: custom
    robots_custom:
      enforce_disallow: true
      crawl_delay_s: 9.0
    extract:
      - kind: product_prices
        scope: census
""", encoding="utf-8")
    database = tmp_path / "engine.db"
    subprocess.run([sys.executable, "-m", "scrapex.cli", "init-db", "--db", str(database)],
                   env=dict(os.environ, SCRAPEX_SOURCES=str(manifest)),
                   capture_output=True, timeout=300)

    from scrapex.config import load_manifest
    from scrapex.webui.app import create_app

    assert load_manifest(manifest).get("SWITCHY").robots_custom, "fixture is wrong"

    client = TestClient(create_app(db_path=str(database), manifest_path=str(manifest)))
    answer = client.post("/api/sources/SWITCHY/edit",
                         json={"robots": "default", "robots_custom": None})
    assert answer.status_code == 200, answer.text

    after = load_manifest(manifest).get("SWITCHY")
    assert after.robots == "default"
    assert not after.robots_custom, (
        f"the 9-second rule is still stored under a choice that ignores it: "
        f"{after.robots_custom}")
