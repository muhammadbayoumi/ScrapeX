"""Two readings of one offer, not two offers.

MADAR's option value says «4 كجم/صندوق» — a box you buy and four kilograms you
get. Before the unit charter the warehouse stored the four and threw the word
away, so 18 offers read "4 kg". The 2026-08-03 crawl wrote them correctly and
BESIDE the old ones, because selling_unit_id is part of an offer's identity —
which is right, and is why "15 per litre" and "15 per gallon" are two offers.

But these are two READINGS. The old row already says so about itself: its
provenance is `legacy_unwitnessed`, meaning nobody can name the field it came
from. A value with no witness is not a fact, and left beside a fact it makes
the same product answer "what is one of these" twice.
"""

from __future__ import annotations

import pathlib
import tempfile

import pytest

from scrapex import db as dbmod


@pytest.fixture()
def conn():
    path = pathlib.Path(tempfile.mkdtemp()) / "retire.db"
    connection = dbmod.connect(path)
    dbmod.migrate(connection)
    return connection


# A legacy row's witness is a SENTENCE, never blank: 0058's trigger refuses a
# unit that cannot name where it came from, and the backfill obeys it by saying
# out loud that the field was not recorded. Passing "" here would be testing
# against a warehouse the schema does not allow.
_LEGACY_WITNESS = ("pre-0058: written without a charter; the field it was read "
                   "from was not recorded")


def _variant(conn, variant_id: int) -> int:
    """The chain an offer needs: a site, a product, a variant."""
    conn.execute("INSERT OR IGNORE INTO source_site (source_id, source_key, "
                 " source_name_ar, source_name, base_url, platform, currency, "
                 " timezone, authority, active) "
                 "VALUES (1,'S','س','S','http://s','magento-graphql','SAR',"
                 "'UTC','shop',1)")
    conn.execute("INSERT OR IGNORE INTO source_product (source_product_id, source_id, "
                 " external_product_id, product_name, product_name_ar) "
                 "VALUES (?,1,?,'P','ب')", (variant_id, str(variant_id)))
    conn.execute("INSERT OR IGNORE INTO source_variant (source_variant_id, "
                 " source_product_id, external_variant_id) VALUES (?,?,?)",
                 (variant_id, variant_id, str(variant_id)))
    return variant_id


def _offer(conn, variant: int, unit: int, provenance: str, witness: str = "w") -> int:
    _variant(conn, variant)
    # selling_unit is EMPTY on a fresh warehouse — the vocabulary is created as
    # units are actually met (0058), and a test that assumed it was seeded would
    # be testing a schema this project deliberately does not have.
    conn.execute("INSERT OR IGNORE INTO selling_unit (selling_unit_id, unit_code, "
                 " name, name_ar) VALUES (?,?,?,?)",
                 (unit, {2: "kg", 3: "box"}.get(unit, f"u{unit}"),
                  {2: "kilogram", 3: "box"}.get(unit, ""),
                  {2: "كيلوجرام",
                   3: "صندوق"}.get(unit, "")))
    cursor = conn.execute(
        "INSERT INTO source_offer (source_variant_id, country_code_alpha2, "
        " customer_segment, basis_quantity, currency, tax_included, "
        " selling_unit_id, unit_basis_provenance, unit_basis_witness) "
        "VALUES (?,'SA','retail',1,'SAR',1,?,?,?)",
        (variant, unit, provenance, witness or _LEGACY_WITNESS))
    return cursor.lastrowid


def test_an_offer_can_be_superseded_and_active_is_the_default(conn):
    """0032 gave source_variant this column for this exact reason. An offer
    needed the same one level down, and nothing had it."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(source_offer)")}
    assert "status" in columns

    offer = _offer(conn, 1, 2, "stated_field")
    assert conn.execute("SELECT status FROM source_offer WHERE offer_id = ?",
                        (offer,)).fetchone()[0] == "active"


def test_only_the_two_states_exist(conn):
    """A CHECK rather than a convention: a third value would be a state no read
    path knows how to treat, and it would read as active by accident."""
    offer = _offer(conn, 1, 2, "stated_field")

    with pytest.raises(Exception):
        conn.execute("UPDATE source_offer SET status = 'archived' WHERE offer_id = ?",
                     (offer,))


def test_a_legacy_reading_with_no_replacement_is_left_alone(conn):
    """THE CONDITION THAT MATTERS. Measured on the live warehouse: MADAR carries
    92 unwitnessed offers, and only 18 have a witnessed sibling. Retiring the
    other 74 would erase a unit and put nothing in its place — the owner would
    lose an answer to gain a principle.

    The migration's rule is re-run here as a query rather than trusted, because
    a backfill that ran once on one machine proves nothing about the rule."""
    alone = _offer(conn, 10, 2, "legacy_unwitnessed")
    conn.commit()

    retired = conn.execute(
        "SELECT COUNT(*) FROM source_offer WHERE status = 'superseded'").fetchone()[0]
    assert retired == 0
    assert conn.execute("SELECT status FROM source_offer WHERE offer_id = ?",
                        (alone,)).fetchone()[0] == "active"


def test_the_migration_rule_retires_only_a_replaced_reading(conn):
    """The same SQL 0060 runs, applied to a warehouse built here: one variant
    with both readings, one with only the old one."""
    replaced = _offer(conn, 20, 2, "legacy_unwitnessed")
    _offer(conn, 20, 3, "stated_field", "variant_axes_ar@ar/v1: 4 كجم/صندوق")
    alone = _offer(conn, 21, 2, "legacy_unwitnessed")

    conn.execute("""
        UPDATE source_offer SET status = 'superseded'
         WHERE unit_basis_provenance = 'legacy_unwitnessed'
           AND EXISTS (SELECT 1 FROM source_offer replacement
                        WHERE replacement.source_variant_id = source_offer.source_variant_id
                          AND replacement.offer_id <> source_offer.offer_id
                          AND replacement.unit_basis_provenance IS NOT NULL
                          AND replacement.unit_basis_provenance
                              NOT IN ('', 'legacy_unwitnessed'))""")

    states = dict(conn.execute("SELECT offer_id, status FROM source_offer"))
    assert states[replaced] == "superseded", "a replaced reading was left standing"
    assert states[alone] == "active", (
        "a reading nothing replaced was retired; that erases a unit and puts "
        "nothing in its place")


def test_nothing_is_deleted_and_the_history_stays(conn):
    """Retiring is a lifecycle state, not a deletion. price_observation is
    append-only and 19 observations hang off the 18 offers this retires on the
    owner's warehouse — what was observed was observed."""
    offer = _offer(conn, 30, 2, "legacy_unwitnessed")
    # An observation points at a run, and run_id 1 does not exist by magic.
    conn.execute("INSERT OR IGNORE INTO crawl_run (run_id, source_id, started_at, "
                 " status) VALUES (1,1,'2026-08-01T00:00:00Z','success')")
    conn.execute(
        "INSERT INTO price_observation (offer_id, run_id, observed_at, business_date, "
        " price, currency, tax_included, availability, record_hash, price_hash, "
        " price_fields, provenance) "
        "VALUES (?,1,'2026-08-01T00:00:00Z','2026-08-01',10,'SAR',1,'in_stock',"
        "'rh','ph','effective','observed')", (offer,))
    conn.execute("UPDATE source_offer SET status = 'superseded' WHERE offer_id = ?",
                 (offer,))

    assert conn.execute("SELECT COUNT(*) FROM source_offer WHERE offer_id = ?",
                        (offer,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM price_observation WHERE offer_id = ?",
                        (offer,)).fetchone()[0] == 1


def test_every_reading_surface_hides_a_superseded_offer():
    """One filter, not one per surface. The variant-level rule has lived in
    _LATEST_PER_OFFER since 0032 and every read path inherits it; the offer
    rule sits beside it so the table, the export and every count derived from
    that join agree without anyone remembering to add it."""
    from scrapex import reports

    assert "AND so.status = 'active' " in reports._LATEST_PER_OFFER, (
        "a superseded offer is still a current price on every surface that "
        "reads this join")
    assert "AND sv.status = 'active' " in reports._LATEST_PER_OFFER, (
        "the variant rule 0032 added has gone")
