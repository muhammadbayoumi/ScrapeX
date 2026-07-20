"""Tax evidence: what the source SAYS about tax, and where it says it.

Before this module a source carried one flag — vat_mode: incl or excl — and
that flag was stamped onto every observation. For globalpetrolprices, whose
manifest entry sets no vat_mode at all, the model default applied and every one
of ~169 countries asserted "prices include VAT" on the authority of nothing. A
fabricated fact, repeated 169 times, that every downstream comparison inherited.

The owner's rule is to be certain of what is written and never assume. A live
survey of globalpetrolprices on 2026-07-20 found that a source is in one of
exactly three states, so those are the three this module records:

  stated   a clause naming a rate       — a Saudi shop: "prices include 15% VAT"
  general  a clause confirming that the — GPP: "the retail price of diesel is
           price is what a customer        different ... due to the various
           pays, without naming a rate     taxes and subsidies"
  unknown  nothing published            — GPP's electricity and gas pages say
                                          nothing about tax whatsoever

The interface must be able to show the difference, because "15% VAT included",
"tax-inclusive, rate not published" and "we do not know" are three different
answers and only the first is a number anyone may calculate with.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from .config import SourceEntry

WILDCARD = "*"


@dataclass(frozen=True)
class TaxState:
    """The resolved tax position for one price, ready to display."""

    evidence: str          # stated | general | unknown
    vat_mode: str          # incl | excl | unknown
    rate_pct: float | None
    statement_text: str
    statement_url: str
    region: str            # which rule matched: an ISO code, or '*'

    @property
    def verified(self) -> bool:
        return self.evidence != "unknown"

    def label(self) -> str:
        """One honest phrase. Never implies a rate we do not have."""
        if self.evidence == "stated" and self.rate_pct is not None:
            rate = f"{self.rate_pct:g}%"
            return (f"Incl. {rate} tax" if self.vat_mode == "incl"
                    else f"Excl. {rate} tax")
        if self.evidence == "general":
            return ("Tax included, rate not published" if self.vat_mode == "incl"
                    else "Tax excluded, rate not published")
        return "Tax treatment unverified"

    def as_dict(self) -> dict:
        return {"tax_evidence": self.evidence, "tax_mode": self.vat_mode,
                "tax_rate_pct": self.rate_pct, "tax_statement": self.statement_text,
                "tax_statement_url": self.statement_url, "tax_label": self.label(),
                "tax_verified": self.verified}


UNVERIFIED = TaxState("unknown", "unknown", None, "", "", WILDCARD)


def upsert_rules(conn: sqlite3.Connection, entry: SourceEntry) -> int:
    """Write the manifest's tax evidence into tax_rule. Returns rules changed.

    Rules are TEMPORAL and never edited in place: a rule whose content changed
    is closed with valid_to and a successor opens. price_observation is
    append-only, so silently rewriting today's rate would restate the tax
    position of every price ever recorded under the old one.
    """
    changed = 0
    for spec in entry.tax:
        region = (spec.region or WILDCARD).strip() or WILDCARD
        mode = (spec.vat_mode or entry.vat_mode).value
        current = conn.execute(
            "SELECT tax_rule_id, vat_mode, rate_pct, evidence, statement_text, statement_url "
            "FROM tax_rule WHERE source_key = ? AND region = ? AND valid_to IS NULL",
            (entry.source_key, region)).fetchone()
        incoming = (mode, spec.rate_pct, spec.evidence,
                    spec.statement_text or None, spec.statement_url or None)
        if current is not None:
            if tuple(current[1:]) == incoming:
                continue                       # unchanged: nothing to record
            conn.execute(
                "UPDATE tax_rule SET valid_to = strftime('%Y-%m-%d','now') "
                "WHERE tax_rule_id = ?", (current[0],))
        conn.execute(
            "INSERT INTO tax_rule (source_key, region, vat_mode, rate_pct, evidence, "
            "statement_text, statement_url, statement_lang, verified_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (entry.source_key, region, mode, spec.rate_pct, spec.evidence,
             spec.statement_text, spec.statement_url, spec.statement_lang,
             spec.verified_at))
        changed += 1
    return changed


def load_rules(conn: sqlite3.Connection, source_key: str) -> dict[str, TaxState]:
    """Every current rule for a source, keyed by region.

    Loaded ONCE per read and resolved in memory: GPP is 169 countries x 5 fuels,
    and a per-row query would be ~845 lookups to answer one page.
    """
    try:
        rows = conn.execute(
            "SELECT region, vat_mode, rate_pct, evidence, "
            "       COALESCE(statement_text,''), COALESCE(statement_url,'') "
            "FROM tax_rule WHERE source_key = ? AND valid_to IS NULL",
            (source_key,)).fetchall()
    except sqlite3.DatabaseError:
        # A database older than migration 0018 has no tax_rule. Reporting every
        # price as unverified is correct there — it is exactly what we know.
        return {}
    return {r[0]: TaxState(evidence=r[3], vat_mode=r[1], rate_pct=r[2],
                           statement_text=r[4], statement_url=r[5], region=r[0])
            for r in rows}


def resolve(rules: dict[str, TaxState], region: str | None) -> TaxState:
    """The rule for a region: its own if there is one, else the source-wide one.

    A country with no rule of its own falls back to the general statement, and a
    source with neither resolves to UNVERIFIED. It never falls back to a
    DIFFERENT country's rate — Norway's VAT says nothing about Egypt's.
    """
    if region and region != WILDCARD and region in rules:
        return rules[region]
    return rules.get(WILDCARD, UNVERIFIED)
