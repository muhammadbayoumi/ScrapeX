"""Match source products to the unified material, with a human gate (spec 14, A5).

THE RULE THAT SHAPES THIS MODULE: no confidence level ever auto-approves. The
engine only ever *suggests*; every link is written `pending` and becomes real
only when the owner decides. A wrong auto-merge is near-impossible to unpick
once prices have accumulated under it, so the asymmetry is deliberate.

Suggestion precedence (highest first): GTIN exact -> SKU exact -> known identity
alias -> normalized-name similarity. Anything below MIN_SUGGEST is not offered
at all — an unconvincing suggestion costs more review time than it saves.
"""
from __future__ import annotations

import json
import sqlite3

from .normalize import name_similarity, normalize_name
from .vocab import CurationStatus, ReviewStatus

GTIN_CONFIDENCE = 0.99
SKU_CONFIDENCE = 0.90
ALIAS_CONFIDENCE = 0.85
MIN_SUGGEST = 0.55        # below this we stay silent rather than waste a review

# Precedence is by METHOD first, confidence second. Ranking on confidence alone
# was wrong: a name_fuzzy of 1.0 (two products that merely share every word)
# outranked an exact GTIN of 0.99, and the GTIN evidence was silently discarded.
# An identifier match is categorically stronger than any string resemblance.
_METHOD_RANK = {"gtin": 3, "sku": 2, "alias": 1, "name_fuzzy": 0}


def _strength(candidate: dict) -> tuple[int, float]:
    return _METHOD_RANK.get(candidate["match_method"], 0), candidate["confidence"]


class ConflictError(Exception):
    """The suggestion has already been decided — retrying would duplicate work."""


class Decision:
    """What the owner can do with a queued suggestion."""

    APPROVE = "approve"           # yes, this source product IS that material
    NEW = "new"                   # it's a real product, but a material of its own
    SEPARATE = "separate"         # not the same thing — never suggest this pair again
    LATER = "later"               # leave it queued


def _candidates_for(conn: sqlite3.Connection, product: sqlite3.Row) -> list[dict]:
    """Ranked material candidates for one source product, best first."""
    found: dict[int, dict] = {}
    # Pairs the owner already ruled apart must never be proposed again — but only
    # THIS pair, not every future candidate for the product.
    rejected = {r[0] for r in conn.execute(
        "SELECT material_id FROM source_product_match "
        "WHERE source_product_id = ? AND review_status = ?",
        (product["source_product_id"], ReviewStatus.IGNORED.value))}

    def offer(material_id: int, confidence: float, method: str, evidence: dict) -> None:
        if material_id in rejected:
            return
        candidate = {"material_id": material_id, "confidence": confidence,
                     "match_method": method, "evidence": evidence}
        best = found.get(material_id)
        if best is None or _strength(candidate) > _strength(best):
            found[material_id] = candidate

    sku = (product["external_sku"] or "").strip()
    if sku:
        for row in conn.execute(
                "SELECT material_id, gtin FROM material WHERE gtin IS NOT NULL AND gtin = ?", (sku,)):
            offer(row["material_id"], GTIN_CONFIDENCE, "gtin", {"gtin": sku})
        for row in conn.execute(
                "SELECT material_id, manufacturer_part_number FROM material "
                "WHERE manufacturer_part_number IS NOT NULL AND manufacturer_part_number = ?", (sku,)):
            offer(row["material_id"], SKU_CONFIDENCE, "sku", {"sku": sku})

    # A material already linked to a product that once carried one of OUR aliases
    # is very likely the same thing (the site re-slugged, we followed).
    for alias in conn.execute(
            "SELECT alias_type, alias_value FROM identity_alias WHERE source_product_id = ?",
            (product["source_product_id"],)):
        for row in conn.execute(
                "SELECT m.material_id FROM material m "
                "JOIN source_product_match spm ON spm.material_id = m.material_id "
                "JOIN source_product sp ON sp.source_product_id = spm.source_product_id "
                "WHERE spm.review_status = 'approved' AND spm.valid_to IS NULL "
                "AND (sp.external_sku = ? OR sp.product_url = ?)",
                (alias["alias_value"], alias["alias_value"])):
            offer(row["material_id"], ALIAS_CONFIDENCE, "alias",
                  {"alias_type": alias["alias_type"], "alias_value": alias["alias_value"]})

    name = product["source_name"] or ""
    if name:
        for row in conn.execute("SELECT material_id, material_name_ar, material_name_en FROM material"):
            score = max(name_similarity(name, row["material_name_ar"]),
                        name_similarity(name, row["material_name_en"]))
            if score >= MIN_SUGGEST:
                offer(row["material_id"], round(score, 3), "name_fuzzy",
                      {"normalized": normalize_name(name), "score": round(score, 3)})

    return sorted(found.values(), key=_strength, reverse=True)


def suggest_for_source(conn: sqlite3.Connection, source_key: str, limit: int = 200) -> int:
    """Queue pending suggestions for this source's un-decided products.

    Returns how many suggestions were written. Products the owner already ruled
    on — approved, or explicitly kept separate, or curation-ignored — are skipped,
    so the same conflict never comes back round (spec 14).
    """
    products = conn.execute(
        "SELECT sp.* FROM source_product sp JOIN source_site ss ON ss.source_id = sp.source_id "
        "WHERE ss.source_key = ? AND sp.curation_status != ? "
        # An IGNORED row means "not that material" — it must retire the PAIR, not
        # the whole product, or one wrong suggestion would exile the product from
        # matching forever. The per-pair blocklist lives in _candidates_for.
        "AND NOT EXISTS (SELECT 1 FROM source_product_match m "
        "                WHERE m.source_product_id = sp.source_product_id "
        "                  AND m.valid_to IS NULL AND m.review_status != 'ignored') "
        "ORDER BY sp.source_product_id LIMIT ?",
        (source_key, CurationStatus.IGNORED.value, limit),
    ).fetchall()

    written = 0
    for product in products:
        candidates = _candidates_for(conn, product)
        if not candidates:
            continue
        best = candidates[0]
        conn.execute(
            "INSERT INTO source_product_match (source_product_id, material_id, confidence, "
            " match_method, evidence_json, review_status) VALUES (?,?,?,?,?,?)",
            (product["source_product_id"], best["material_id"], best["confidence"],
             best["match_method"], json.dumps(best["evidence"], ensure_ascii=False),
             ReviewStatus.PENDING.value),
        )
        written += 1
    return written


def pending_reviews(conn: sqlite3.Connection, source_key: str | None = None,
                    limit: int = 50) -> list[dict]:
    """The review queue: incoming record, suggested match, confidence, evidence."""
    sql = (
        "SELECT m.source_product_match_id, m.confidence, m.match_method, m.evidence_json, "
        "       sp.source_product_id, sp.source_name AS incoming_name, sp.external_sku, "
        "       sp.product_url, sp.brand_raw, ss.source_key, "
        "       mat.material_id, COALESCE(mat.material_name_en, mat.material_name_ar) AS material_name "
        "FROM source_product_match m "
        "JOIN source_product sp ON sp.source_product_id = m.source_product_id "
        "JOIN source_site ss ON ss.source_id = sp.source_id "
        "JOIN material mat ON mat.material_id = m.material_id "
        "WHERE m.review_status = ? AND m.valid_to IS NULL "
    )
    params: list = [ReviewStatus.PENDING.value]
    if source_key is not None:
        sql += "AND ss.source_key = ? "
        params.append(source_key)
    sql += "ORDER BY m.confidence DESC, m.source_product_match_id LIMIT ?"
    params.append(max(1, min(limit, 200)))

    out = []
    for row in conn.execute(sql, params):
        item = dict(row)
        item["evidence"] = json.loads(item.pop("evidence_json") or "{}")
        item["matched_fields"], item["conflicting_fields"] = _field_comparison(conn, row)
        out.append(item)
    return out


def _field_comparison(conn: sqlite3.Connection, row: sqlite3.Row) -> tuple[list[str], list[str]]:
    """Which fields agree and which disagree — what the owner actually decides on."""
    material = conn.execute(
        "SELECT material_name_ar, material_name_en, gtin, manufacturer_part_number "
        "FROM material WHERE material_id = ?", (row["material_id"],)).fetchone()
    matched, conflicting = [], []
    incoming_name = row["incoming_name"] or ""
    if name_similarity(incoming_name, material["material_name_ar"]) >= MIN_SUGGEST or \
       name_similarity(incoming_name, material["material_name_en"]) >= MIN_SUGGEST:
        matched.append("name")
    elif incoming_name:
        conflicting.append("name")
    sku = (row["external_sku"] or "").strip()
    if sku and sku in {material["gtin"], material["manufacturer_part_number"]}:
        matched.append("sku")
    elif sku and (material["gtin"] or material["manufacturer_part_number"]):
        conflicting.append("sku")
    return matched, conflicting


def decide(conn: sqlite3.Connection, source_product_match_id: int, decision: str,
           material_id: int | None = None) -> dict:
    """Apply the owner's verdict. Returns the resulting state.

    Nothing here deletes: a rejected suggestion is RETIRED (valid_to) or marked
    ignored, so the audit trail of what was proposed and refused survives.
    """
    row = conn.execute(
        "SELECT m.*, sp.source_name, sp.brand_raw FROM source_product_match m "
        "JOIN source_product sp ON sp.source_product_id = m.source_product_id "
        "WHERE m.source_product_match_id = ?", (source_product_match_id,)).fetchone()
    if row is None:
        raise KeyError(f"unknown match {source_product_match_id}")
    # Without this guard a double-clicked NEW minted a duplicate material each
    # time, and approving an already-retired row reported success while leaving
    # no active link at all.
    if row["valid_to"] is not None or row["review_status"] != ReviewStatus.PENDING.value:
        raise ConflictError(
            f"match {source_product_match_id} is already {row['review_status']}"
            + (" and retired" if row["valid_to"] is not None else ""))

    if decision == Decision.LATER:
        return {"status": ReviewStatus.PENDING.value}

    if decision == Decision.SEPARATE:
        # Remembered as ignored so the suggester never offers this pair again.
        conn.execute("UPDATE source_product_match SET review_status = ? "
                     "WHERE source_product_match_id = ?",
                     (ReviewStatus.IGNORED.value, source_product_match_id))
        return {"status": ReviewStatus.IGNORED.value}

    if decision == Decision.NEW:
        cur = conn.execute(
            "INSERT INTO material (material_name_ar, material_type) VALUES (?, 'product')",
            (row["source_name"],))
        material_id = int(cur.lastrowid)
    elif decision == Decision.APPROVE:
        material_id = material_id or row["material_id"]
    else:
        raise ValueError(f"unknown decision {decision!r}")

    conn.execute(
        "UPDATE source_product_match SET review_status = ?, material_id = ?, match_method = ? "
        "WHERE source_product_match_id = ?",
        (ReviewStatus.APPROVED.value, material_id, "manual", source_product_match_id))
    conn.execute("UPDATE source_product SET curation_status = ? WHERE source_product_id = ?",
                 (CurationStatus.SELECTED.value, row["source_product_id"]))
    return {"status": ReviewStatus.APPROVED.value, "material_id": material_id}


def undo_decision(conn: sqlite3.Connection, source_product_match_id: int) -> bool:
    """Undo a merge/approval by RETIRING it (valid_to), never by deleting.

    Price history is untouched — it hangs off the offers, not the match — so the
    link can be re-made later without having lost anything.
    """
    cur = conn.execute(
        "UPDATE source_product_match SET valid_to = strftime('%Y-%m-%dT%H:%M:%SZ','now') "
        "WHERE source_product_match_id = ? AND valid_to IS NULL",
        (source_product_match_id,))
    return cur.rowcount == 1
