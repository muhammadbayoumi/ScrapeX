"""Tax is EVIDENCED or reported as unverified — never assumed.

Before this, a source carried one flag (vat_mode) and that flag was stamped onto
every observation. GPP_ENERGY's manifest entry sets no vat_mode at all, so the
model default applied and all ~169 countries asserted "prices include VAT" on
the authority of nothing whatsoever. One fabricated fact, repeated 169 times,
inherited by every downstream comparison.

The owner's rule: be certain of what is written, never assume. A live survey of
globalpetrolprices found a source is in exactly one of three states, so those
are the three states these tests hold the system to.
"""
from __future__ import annotations

import sqlite3

import pytest

from scrapex import db as dbmod, tax
from scrapex.config import ExtractSpec, SourceEntry, TaxEvidence
from scrapex.ingest import ingest_payloads
from scrapex.payload import PAYLOAD_VERSION, FunnelPayload
from scrapex.reports import EXPORT_HEADER, browse_observations, export_source_table
from scrapex.rowspec import PRODUCT_PRICES, RowBuilder
from scrapex.vocab import ExtractKind, ExtractScope


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


def entry(tax_rules=(), **over) -> SourceEntry:
    base = dict(
        source_key="SHOP", source_name="متجر", base_url="https://shop.example",
        family="shopify-json", currency="SAR", default_region="SA", vat_mode="incl",
        tax=list(tax_rules),
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)])
    base.update(over)
    return SourceEntry.model_validate(base)


def payload(rows) -> FunnelPayload:
    return FunnelPayload(
        payload_version=PAYLOAD_VERSION, source_key="SHOP",
        kind=ExtractKind.PRODUCT_PRICES, client="cli",
        scraped_at="2026-07-20T10:00:00Z", source_url="https://shop.example",
        header=list(PRODUCT_PRICES.columns), rows=rows)


def row(**over) -> list[str]:
    fields = dict(external_product_id="P1", product_name="أسمنت", region="SA",
                  currency="SAR", vat_included="1", effective_price="325")
    fields.update(over)
    return RowBuilder(PRODUCT_PRICES).row(**fields)


STATED = TaxEvidence(region="*", evidence="stated", rate_pct=15,
                     statement_text="جميع الأسعار شاملة ضريبة القيمة المضافة 15%",
                     statement_url="https://shop.example/terms", statement_lang="ar",
                     verified_at="2026-07-20")
GENERAL = TaxEvidence(region="*", evidence="general",
                      statement_text="Prices shown are retail prices.",
                      statement_url="https://shop.example/about")


# ---- the manifest refuses evidence that is not evidence ----------------------

def test_a_rate_without_a_source_is_refused():
    """A rate with nowhere to read it is exactly the assertion this prevents."""
    with pytest.raises(ValueError, match="statement_url"):
        TaxEvidence(region="*", evidence="stated", rate_pct=15)


def test_a_stated_evidence_without_a_rate_is_refused():
    with pytest.raises(ValueError, match="must name a rate"):
        TaxEvidence(region="*", evidence="stated",
                    statement_url="https://shop.example/terms")


def test_a_general_statement_may_not_smuggle_in_a_rate():
    """'general' MEANS no rate was published. Carrying one would let a guess in
    through the door marked "the source did not say"."""
    with pytest.raises(ValueError, match="WITHOUT naming a rate"):
        TaxEvidence(region="*", evidence="general", rate_pct=15,
                    statement_url="https://shop.example/about")


def test_unknown_cannot_carry_a_statement():
    with pytest.raises(ValueError, match="nothing is published"):
        TaxEvidence(region="*", evidence="unknown", statement_text="something")


# ---- resolution ---------------------------------------------------------------

def test_a_country_uses_its_own_rule_when_it_has_one():
    rules = {"*": tax.TaxState("general", "incl", None, "", "u", "*"),
             "EG": tax.TaxState("stated", "incl", 14.0, "", "u2", "EG")}
    assert tax.resolve(rules, "EG").rate_pct == 14.0


def test_a_country_without_a_rule_falls_back_to_the_source_statement():
    rules = {"*": tax.TaxState("general", "incl", None, "", "u", "*")}
    assert tax.resolve(rules, "NO").evidence == "general"


def test_one_country_never_inherits_another_countrys_rate():
    """Norway's VAT says nothing about Egypt's. With no wildcard rule and no
    rule of its own, the answer is "we do not know"."""
    rules = {"NO": tax.TaxState("stated", "incl", 25.0, "", "u", "NO")}

    resolved = tax.resolve(rules, "EG")

    assert resolved.evidence == "unknown" and resolved.rate_pct is None


def test_a_source_with_no_rules_at_all_is_unverified():
    assert tax.resolve({}, "SA").evidence == "unknown"


# ---- the label never implies a rate we do not have ---------------------------

def test_a_stated_rate_is_shown_as_a_rate():
    assert tax.TaxState("stated", "incl", 15, "", "", "*").label() == "Incl. 15% tax"
    assert tax.TaxState("stated", "excl", 15, "", "", "*").label() == "Excl. 15% tax"


def test_a_general_statement_says_the_rate_is_not_published():
    label = tax.TaxState("general", "incl", None, "", "", "*").label()
    assert label == "Tax included, rate not published"
    assert "%" not in label, "a label must never imply a rate we were not given"


def test_no_evidence_says_unverified_out_loud():
    assert tax.UNVERIFIED.label() == "Tax treatment unverified"
    assert not tax.UNVERIFIED.verified


# ---- end to end ---------------------------------------------------------------

def test_evidence_from_the_manifest_reaches_the_table(conn):
    ingest_payloads(conn, entry([STATED]), [payload([row()])])

    shown = browse_observations(conn, "SHOP").rows[0]

    assert shown["tax_evidence"] == "stated"
    assert shown["tax_rate_pct"] == 15
    assert shown["tax_statement_url"] == "https://shop.example/terms"
    assert shown["tax_label"] == "Incl. 15% tax"


def test_a_source_with_no_tax_block_reports_unverified_not_incl(conn):
    """This is the GPP defect in miniature: vat_mode defaulted to inclusive and
    every row asserted it as though the source had said so."""
    ingest_payloads(conn, entry(), [payload([row()])])

    shown = browse_observations(conn, "SHOP").rows[0]

    assert shown["tax_evidence"] == "unknown"
    assert shown["tax_verified"] is False
    assert shown["tax_label"] == "Tax treatment unverified"


def test_the_export_carries_the_evidence_and_where_to_read_it(conn):
    ingest_payloads(conn, entry([STATED]), [payload([row()])])

    header, table = export_source_table(conn, "SHOP")

    assert {"tax_evidence", "tax_rate_pct", "tax_statement_url"} <= set(header)
    assert table[0][header.index("tax_evidence")] == "stated"
    assert table[0][header.index("tax_rate_pct")] == 15
    assert table[0][header.index("tax_statement_url")] == "https://shop.example/terms"
    assert all(len(r) == len(header) for r in table), "a column shifted the row"


def test_an_unverified_export_cell_is_empty_not_zero(conn):
    """A 0 in a rate column reads as "zero tax", which is a claim."""
    ingest_payloads(conn, entry(), [payload([row()])])

    header, table = export_source_table(conn, "SHOP")

    assert table[0][header.index("tax_rate_pct")] == ""


# ---- rules are temporal ------------------------------------------------------

def test_changing_a_rate_closes_the_old_rule_instead_of_editing_it(conn):
    """price_observation is append-only. Editing today's rate in place would
    silently restate the tax position of every price ever recorded under it."""
    ingest_payloads(conn, entry([STATED]), [payload([row()])])
    raised = STATED.model_copy(update={"rate_pct": 20.0})
    ingest_payloads(conn, entry([raised]), [payload([row(effective_price="330")])])

    rules = conn.execute(
        "SELECT rate_pct, valid_to FROM tax_rule ORDER BY tax_rule_id").fetchall()

    assert len(rules) == 2, "the rate was edited in place"
    assert rules[0][0] == 15 and rules[0][1] is not None, "the old rule was not closed"
    assert rules[1][0] == 20 and rules[1][1] is None, "the new rule is not current"


def test_an_unchanged_rule_is_not_rewritten_every_crawl(conn):
    ingest_payloads(conn, entry([STATED]), [payload([row()])])
    ingest_payloads(conn, entry([STATED]), [payload([row(effective_price="330")])])

    assert conn.execute("SELECT count(*) FROM tax_rule").fetchone()[0] == 1


def test_only_one_rule_per_region_is_ever_current(conn):
    ingest_payloads(conn, entry([STATED]), [payload([row()])])
    ingest_payloads(conn, entry([STATED.model_copy(update={"rate_pct": 20.0})]),
                    [payload([row(effective_price="330")])])

    current = conn.execute(
        "SELECT count(*) FROM tax_rule WHERE region = '*' AND valid_to IS NULL").fetchone()[0]
    assert current == 1


# ---- the real manifest --------------------------------------------------------

def test_gpp_records_the_real_statement_and_claims_no_rate():
    """What the live site actually supports: a general statement, no rate. If
    this ever gains a rate_pct, someone invented one for 169 countries."""
    from scrapex.config import load_manifest

    rules = load_manifest().get("GPP_ENERGY").tax

    assert len(rules) == 1
    rule = rules[0]
    assert rule.evidence == "general"
    assert rule.rate_pct is None, "a rate was invented for 169 countries"
    assert rule.statement_url.startswith("https://www.globalpetrolprices.com")
    assert "retail price" in rule.statement_text
