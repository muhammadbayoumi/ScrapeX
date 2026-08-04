"""«المقاس: 50 Kg» in the Specifications panel, which no charter could read.

MADAR's «إسمنت السعودية» carries no size on its variants at all — its option
value is «Cement Type: Sulphate Resistant Cement» — and states «المقاس: 50 Kg»
in its Specifications. That is the shop saying what one bag is, and 48 of its
products state a mass or volume that way.

The charter was handed six fields and none of them was this one, so those
readings kept the units pre-charter code invented for them and kept saying, in
their own provenance, that nobody could name where they came from.

MEASURED OVER ALL 3,550 ACTIVE OFFERS BEFORE THE WITNESS WAS ADDED:
  13 agree with what is already stored, changing no number
  53 carry no unit at all today and gain the one the shop states
   2 CONTRADICT: stored 25 kg where the shop's own panel says «20 Kg»
"""

from __future__ import annotations

import json
import pathlib
import tempfile

import pytest

from scrapex import db as dbmod
from scrapex.config import MANIFEST_FILE, load_manifest
from scrapex.connectors.magento import _spec_size
from scrapex.units import Charter


@pytest.fixture(scope="module")
def madar() -> Charter:
    entry = load_manifest(MANIFEST_FILE).get("MADAR")
    return Charter(json.loads(entry.unit_charter.model_dump_json()))


def _fields(**over) -> dict:
    base = {"weight": "", "weight_unit": "", "variant_axes": "", "variant_axes_ar": "",
            "product_name": "", "product_name_ar": "", "spec_size": ""}
    base.update(over)
    return base


def test_the_specifications_size_is_read_where_the_variant_is_silent(madar):
    """The cement case. Its only option value names a cement TYPE, so every
    axis witness above this one has nothing to say."""
    r = madar.resolve(_fields(spec_size="50 Kg"))

    assert r is not None and (r.unit, r.quantity) == ("kg", 50.0)
    assert r.provenance == "stated_field"


def test_the_variant_own_axis_still_answers_first(madar):
    """THE RANKING THAT MATTERS, and it is load-bearing rather than
    theoretical: nine of the 48 products that state a size have more than one
    variant. A product-level figure printed on each member is how a family's
    size becomes every member's — the exact mistake reports.py names in writing
    about product-level attributes."""
    r = madar.resolve(_fields(spec_size="50 Kg", variant_axes='{"Size":"3.25 Kg"}'))

    assert r is not None and (r.unit, r.quantity) == ("kg", 3.25)


def test_a_specification_that_is_not_a_selling_unit_is_refused(madar):
    """The pack list governs this witness like every other."""
    assert madar.resolve(_fields(spec_size="20 mm")) is None
    assert madar.resolve(_fields(spec_size="Sulphate Resistant Cement")) is None


def test_the_connector_reads_both_shapes_the_api_returns():
    """A dropdown arrives as selected_options and a text value as `value`.
    Reading only one of them would have left half the catalogue silent."""
    dropdown = {"custom_attributesV2": {"items": [
        {"code": "size", "selected_options": [{"label": "50 Kg"}]}]}}
    text = {"custom_attributesV2": {"items": [{"code": "size", "value": "20 Kg"}]}}

    assert _spec_size(dropdown) == "50 Kg"
    assert _spec_size(text) == "20 Kg"
    assert _spec_size({"custom_attributesV2": {"items": [
        {"code": "manufacturer", "value": "SABIC"}]}}) == ""
    assert _spec_size(None) == ""


# ---- the rule that stops the corrected reading standing beside the wrong one --

@pytest.fixture()
def conn():
    path = pathlib.Path(tempfile.mkdtemp()) / "retire.db"
    c = dbmod.connect(path)
    dbmod.migrate(c)
    c.execute("INSERT INTO source_site (source_id, source_key, source_name_ar, source_name,"
              " base_url, platform, currency, timezone, authority, active) "
              "VALUES (1,'S','س','S','http://s','magento-graphql','SAR','UTC','shop',1)")
    c.execute("INSERT INTO source_product (source_product_id, source_id, "
              " external_product_id, product_name, product_name_ar) VALUES (1,1,'p','P','ب')")
    c.execute("INSERT INTO source_variant (source_variant_id, source_product_id, "
              " external_variant_id) VALUES (1,1,'v')")
    c.execute("INSERT INTO selling_unit (selling_unit_id, unit_code, name, name_ar) "
              "VALUES (2,'kg','kilogram','كيلوجرام')")
    return c


_LEGACY = ("pre-0058: written without a charter; the field it was read from was "
           "not recorded")

_CORRECTED = {"country_code_alpha2": "SA", "currency": "SAR", "tax_included": "1",
              "unit": "kg", "basis_quantity": "20",
              "unit_basis_provenance": "stated_field",
              "unit_basis_witness": "spec_size@und/v1: 20 Kg"}


def _legacy_offer(conn, quantity: float) -> int:
    return conn.execute(
        "INSERT INTO source_offer (source_variant_id, country_code_alpha2, "
        " customer_segment, basis_quantity, currency, tax_included, selling_unit_id, "
        " unit_basis_provenance, unit_basis_witness) "
        "VALUES (1,'SA','retail',?,'SAR',1,2,'legacy_unwitnessed',?)",
        (quantity, _LEGACY)).lastrowid


def test_a_corrected_reading_retires_the_one_it_replaces(conn):
    """Migration 0060 did this once, by hand, for 18 offers on one warehouse on
    one day. Nothing made it a RULE — so the next charter that learns to read a
    field recreates the same pair: two rows, both active, one product answering
    "what is one of these" twice.

    It happens again here: the shop's panel says «20 Kg» where the row says 25,
    and a different basis_quantity mints a NEW offer rather than replacing one —
    which is right for two STATED units and wrong for two readings of one."""
    from scrapex.ingest import _get_offer_id
    stale = _legacy_offer(conn, 25.0)

    fresh = _get_offer_id(conn, 1, dict(_CORRECTED))

    states = dict(conn.execute("SELECT offer_id, status FROM source_offer"))
    assert fresh != stale
    assert states[stale] == "superseded", "the unsourced 25 kg is still a current price"
    assert states[fresh] == "active"


def test_a_legacy_reading_nothing_replaces_is_left_alone(conn):
    """The condition 0060 was careful about, kept. Retiring a reading with no
    replacement erases a unit and puts nothing in its place — the owner would
    lose an answer to gain a principle. MADAR carried 92 unwitnessed offers and
    only 18 had a witnessed sibling; the other 74 had to survive.

    THE CRAWL IS RUN, not just the row inserted. An earlier version of this
    test asserted on a row it had written itself and never called
    _get_offer_id, so deleting the whole "unless something replaced it" clause
    left it green — a guard for the condition that matters, guarding nothing."""
    from scrapex.ingest import _get_offer_id
    alone = _legacy_offer(conn, 25.0)
    other = _legacy_offer(conn, 30.0)

    # The variant is crawled again by code that still cannot name a witness.
    # Writing an offer is not the same as answering for one, and a row with no
    # witness can never be another row's replacement.
    _get_offer_id(conn, 1, {"country_code_alpha2": "SA", "currency": "SAR",
                            "tax_included": "1", "unit": "kg", "basis_quantity": "30"})

    states = dict(conn.execute("SELECT offer_id, status FROM source_offer"))
    assert states[alone] == "active", (
        "a reading nothing witnessed replaced was retired; that erases a unit "
        "and puts nothing in its place")
    assert states[other] == "active"


def test_a_witnessed_reading_never_retires_another_witnessed_one(conn):
    """Two STATED units are two offers — "15 per litre" and "15 per gallon" —
    and ingest has said so in writing since the sika fix. Only a row that says
    of ITSELF that nobody can name its source may be retired."""
    from scrapex.ingest import _get_offer_id
    witnessed = conn.execute(
        "INSERT INTO source_offer (source_variant_id, country_code_alpha2, "
        " customer_segment, basis_quantity, currency, tax_included, selling_unit_id, "
        " unit_basis_provenance, unit_basis_witness) "
        "VALUES (1,'SA','retail',25,'SAR',1,2,'stated_field','variant_axes: 25 Kg')"
    ).lastrowid

    _get_offer_id(conn, 1, dict(_CORRECTED))

    assert conn.execute("SELECT status FROM source_offer WHERE offer_id = ?",
                        (witnessed,)).fetchone()[0] == "active"


def test_nothing_is_deleted(conn):
    """Retiring is the lifecycle state 0032 defined. price_observation is
    append-only and what was observed was observed."""
    from scrapex.ingest import _get_offer_id
    stale = _legacy_offer(conn, 25.0)
    conn.execute("INSERT INTO crawl_run (run_id, source_id, started_at, status) "
                 "VALUES (1,1,'2026-08-04T00:00:00Z','success')")
    conn.execute(
        "INSERT INTO price_observation (offer_id, run_id, observed_at, business_date, "
        " price, currency, tax_included, availability, record_hash, price_hash, "
        " price_fields, provenance) VALUES (?,1,'2026-08-04T00:00:00Z','2026-08-04',"
        "10,'SAR',1,'in_stock','rh','ph','effective','observed')", (stale,))

    _get_offer_id(conn, 1, dict(_CORRECTED))

    assert conn.execute("SELECT COUNT(*) FROM source_offer WHERE offer_id = ?",
                        (stale,)).fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM price_observation WHERE offer_id = ?",
                        (stale,)).fetchone()[0] == 1
