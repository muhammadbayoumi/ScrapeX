"""Fifty-nine columns nobody agreed to, and no door to send them back through.

The owner asked three times to have the many un-agreed columns moved to the
details. Measured on his MADAR: 112 columns in the table, 59 of them variation
axes, and 33 of those non-empty on under 1% of its 3,550 rows — «الكثافة
(كجم/م3)» filled on four.

They could not be moved. fields.promotable_attributes — the chooser that shows
each detail with the count of products that fill it, so "an attribute two
products carry is a column of blanks" is visible BEFORE choosing — read
source_product_attribute only. An axis was never in the list, so there was no
way to demote one however much the owner wanted to.

NOTHING IS LOST BY NOT PRINTING THEM. variant and variant_ar already carry the
same words in both languages — "Width (mm): 610" / «العرض (ملم): 610».
Verified across every source that publishes axes at all: zero variants carry an
axis without carrying it in `variant` too.
"""

from __future__ import annotations

import json

import pytest

from scrapex import db as dbmod, fields, reports


@pytest.fixture()
def conn(tmp_path):
    c = dbmod.connect(tmp_path / "w.db")
    dbmod.migrate(c)
    c.execute("INSERT INTO source_site (source_id, source_key, source_name_ar, source_name,"
              " base_url, platform, currency, timezone, authority, active) "
              "VALUES (1,'SHOP','م','Shop','http://s','magento-graphql','SAR','UTC','shop',1)")
    for pid, axes in enumerate([{"Thickness (mm)": "3"}, {"Density (Kg/M3)": "40"}], start=1):
        c.execute("INSERT INTO source_product (source_product_id, source_id, "
                  " external_product_id, product_name, product_name_ar, status) "
                  "VALUES (?,1,?,'P','ب','active')", (pid, str(pid)))
        blob = json.dumps(axes, ensure_ascii=False)
        label = ", ".join(f"{k}: {v}" for k, v in axes.items())
        c.execute("INSERT INTO source_variant (source_variant_id, source_product_id, "
                  " external_variant_id, variant, variant_ar, variant_axes, "
                  " variant_axes_ar, status) VALUES (?,?,?,?,?,?,?,'active')",
                  (pid, pid, str(pid), label, label, blob, blob))
        # A row only reaches the table through the price join, so the fixture
        # has to carry an offer and an observation or the export is empty and
        # every assertion below passes for the wrong reason.
        c.execute("INSERT INTO source_offer (offer_id, source_variant_id, "
                  " country_code_alpha2, customer_segment, basis_quantity, currency, "
                  " tax_included, status) VALUES (?,?,'SA','retail',1,'SAR',1,'active')",
                  (pid, pid))
        c.execute("INSERT OR IGNORE INTO crawl_run (run_id, source_id, started_at, status) "
                  "VALUES (1,1,'2026-08-04T00:00:00Z','success')")
        c.execute("INSERT INTO price_observation (offer_id, run_id, observed_at, "
                  " business_date, price, currency, tax_included, availability, "
                  " record_hash, price_hash, price_fields, provenance) "
                  "VALUES (?,1,'2026-08-04T00:00:00Z','2026-08-04',10,'SAR',1,'in_stock',"
                  "?,?,'effective','observed')", (pid, f"rh{pid}", f"ph{pid}"))
    c.commit()
    return c


def _axes_offered(conn) -> dict[str, int]:
    return {a["label"]: a["products"] for a in fields.promotable_axes(conn, "SHOP")}


def test_the_chooser_offers_the_axes_with_how_much_they_fill(conn):
    """THE MISSING DOOR. The count is the whole point — the owner should see
    that an axis covers one product in two before he chooses, not after he
    exports."""
    offered = _axes_offered(conn)

    assert offered == {"Thickness (mm)": 1, "Density (Kg/M3)": 1}


def test_the_axes_ride_the_same_list_the_details_already_use(conn):
    """One endpoint, one panel, one place to decide — rather than a second
    chooser the owner has to discover. The panel that already reads
    promotable_attributes gains them without any change."""
    codes = {a["attribute_code"] for a in fields.promotable_attributes(conn, "SHOP")}

    assert fields.AXIS_PREFIX + "Thickness (mm)" in codes


def test_an_axis_and_a_detail_that_share_a_name_stay_apart(conn):
    """madar publishes «المقاس» as BOTH a variation axis and a product
    specification. A promotion has to say which one it promoted, or promoting
    the spec would silently promote the axis too."""
    assert fields.AXIS_PREFIX + "Size" != "Size"
    assert all(a["attribute_code"].startswith(fields.AXIS_PREFIX)
               for a in fields.promotable_axes(conn, "SHOP"))


def test_an_axis_is_not_a_column_until_it_is_promoted(conn):
    """The default the owner asked for. 112 columns is not a table anyone
    reads."""
    header, _ = reports.export_source_table(conn, "SHOP", limit=50)

    assert "Thickness (mm)" not in header
    assert "Density (Kg/M3)" not in header


def test_promoting_one_brings_exactly_that_one_back(conn):
    """Reversible by construction, and specific: promoting the axis that fills
    40% of the rows must not drag in the one that fills four of them."""
    fields.set_promotion(conn, "SHOP", fields.AXIS_PREFIX + "Thickness (mm)", True)

    header, _ = reports.export_source_table(conn, "SHOP", limit=50)

    assert "Thickness (mm)" in header
    assert "Density (Kg/M3)" not in header


def test_demoting_it_again_sends_it_back(conn):
    """The row IS the promotion, so nothing has to remember a previous shape."""
    code = fields.AXIS_PREFIX + "Thickness (mm)"
    fields.set_promotion(conn, "SHOP", code, True)
    fields.set_promotion(conn, "SHOP", code, False)

    header, _ = reports.export_source_table(conn, "SHOP", limit=50)

    assert "Thickness (mm)" not in header


def test_the_fact_is_still_on_the_row(conn):
    """THE REASON THIS IS SAFE. Demoting an axis hides a duplicate, not a fact:
    `variant` and `variant_ar` sit near the front of the table and carry the
    same words. If this ever stops being true, demoting starts losing data."""
    header, rows = reports.export_source_table(conn, "SHOP", limit=50)
    at, at_ar = header.index("variant"), header.index("variant_ar")

    assert any("Thickness (mm): 3" == row[at] for row in rows)
    assert any("Thickness (mm): 3" == row[at_ar] for row in rows)
