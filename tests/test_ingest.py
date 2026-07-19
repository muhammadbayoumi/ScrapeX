"""A5/A7/Q3/T4: ingest — upserts, idempotency, scope guard, curation skip, isolation."""
from __future__ import annotations

import sqlite3

import pytest

from scrapex import db as dbmod
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.ingest import ingest_payloads, scope_reason
from scrapex.payload import PAYLOAD_VERSION, FunnelPayload
from scrapex.rowspec import PRODUCT_PRICES, RowBuilder
from scrapex.vocab import CurationStatus, ExtractKind, ExtractScope


@pytest.fixture()
def conn() -> sqlite3.Connection:
    c = dbmod.connect(":memory:")
    dbmod.migrate(c)
    yield c
    c.close()


def make_entry(**over) -> SourceEntry:
    base = dict(
        source_key="ELSEWEDYSHOP", source_name="السويدي شوب",
        base_url="https://elsewedyshop.com", family="shopify-json",
        currency="EGP", default_region="EG",
        extract=[ExtractSpec(kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.CENSUS)],
    )
    base.update(over)
    return SourceEntry.model_validate(base)


def make_payload(rows: list[list[str]], source_key="ELSEWEDYSHOP", scraped_at="2026-07-16T10:00:00Z") -> FunnelPayload:
    return FunnelPayload(
        payload_version=PAYLOAD_VERSION, source_key=source_key,
        kind=ExtractKind.PRODUCT_PRICES, client="cli", scraped_at=scraped_at,
        source_url="https://elsewedyshop.com/products.json",
        header=list(PRODUCT_PRICES.columns), rows=rows,
    )


def one_row(**over) -> list[str]:
    fields = dict(
        external_product_id="1001", external_variant_id="5001", external_sku="SKU1",
        product_name="LED Floodlight 400W", brand_raw="Elsewedy",
        region="EG", currency="EGP", vat_included="1",
        regular_price="1,200.00", sale_price="", effective_price="1,200.00",
        availability="in_stock",
    )
    fields.update(over)
    return RowBuilder(PRODUCT_PRICES).row(**fields)


# ---- happy path + the warehouse spine ---------------------------------------

def test_ingest_creates_full_chain(conn):
    result = ingest_payloads(conn, make_entry(), [make_payload([one_row()])])
    assert (result.products, result.variants, result.observations) == (1, 1, 1)
    assert result.status.value == "success"
    assert conn.execute("SELECT external_product_id FROM source_product").fetchone()[0] == "1001"
    obs = conn.execute("SELECT effective_price, vat_included, currency FROM price_observation").fetchone()
    assert obs[0] == 1200.00 and obs[1] == 1 and obs[2] == "EGP"  # comma parsed by the shared parser


def test_new_source_product_is_inventoried(conn):
    ingest_payloads(conn, make_entry(), [make_payload([one_row()])])
    status = conn.execute("SELECT curation_status FROM source_product").fetchone()[0]
    assert status == CurationStatus.INVENTORIED.value


# ---- idempotency (T4) --------------------------------------------------------

def test_reingest_same_content_is_idempotent(conn):
    entry = make_entry()
    ingest_payloads(conn, entry, [make_payload([one_row()])])
    second = ingest_payloads(conn, entry, [make_payload([one_row()])])
    assert second.observations == 0 and second.duplicates == 1
    assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM source_product").fetchone()[0] == 1


def test_changed_price_appends_new_observation(conn):
    entry = make_entry()
    ingest_payloads(conn, entry, [make_payload([one_row()])])
    ingest_payloads(conn, entry, [make_payload([one_row(effective_price="1,300.00")],
                                              scraped_at="2026-07-17T10:00:00Z")])
    assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == 2


# ---- curation gate (A5) ------------------------------------------------------

def test_ignored_product_skips_observation(conn):
    entry = make_entry()
    ingest_payloads(conn, entry, [make_payload([one_row()])])
    conn.execute("UPDATE source_product SET curation_status = 'ignored'")
    result = ingest_payloads(conn, entry,
                             [make_payload([one_row(effective_price="9,999.00")],
                                           scraped_at="2026-07-18T10:00:00Z")])
    assert result.skipped_ignored == 1
    # No new observation for the ignored product:
    assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == 1


# ---- scope guard (gate 2) ----------------------------------------------------

def test_scope_reason_census_accepts_all():
    assert scope_reason(make_entry(), ExtractKind.PRODUCT_PRICES, "EG") is None


def test_scope_reason_targeted_rejects_foreign_region():
    entry = make_entry(extract=[ExtractSpec(
        kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.TARGETED, regions=["EG"])])
    assert scope_reason(entry, ExtractKind.PRODUCT_PRICES, "SA") is not None
    assert scope_reason(entry, ExtractKind.PRODUCT_PRICES, "EG") is None


def test_ingest_rejects_out_of_scope_row(conn):
    entry = make_entry(extract=[ExtractSpec(
        kind=ExtractKind.PRODUCT_PRICES, scope=ExtractScope.TARGETED, regions=["EG"])])
    result = ingest_payloads(conn, entry, [make_payload([one_row(region="SA")])])
    assert result.rejected_out_of_scope == 1
    assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == 0


# ---- per-row isolation (Q3) --------------------------------------------------

def test_one_bad_row_does_not_kill_the_batch(conn):
    good = one_row(external_product_id="1001", external_variant_id="5001")
    bad = one_row(external_product_id="1002", external_variant_id="5002", effective_price="Call us")
    result = ingest_payloads(conn, make_entry(), [make_payload([good, bad])])
    assert result.observations == 1
    assert len(result.errors) == 1 and "row 1" in result.errors[0]


def test_wrong_source_key_payload_is_flagged(conn):
    result = ingest_payloads(conn, make_entry(), [make_payload([one_row()], source_key="ALSWEED")])
    assert result.observations == 0 and any("source_key" in e for e in result.errors)


def test_header_drift_payload_is_rejected_whole(conn):
    payload = make_payload([one_row()])
    broken = payload.model_copy(update={"header": payload.header[:-1] + ["renamed_col"],
                                        "rows": [r[:-1] + ["x"] for r in payload.rows]})
    result = ingest_payloads(conn, make_entry(), [broken])
    assert result.observations == 0 and any("header drift" in e for e in result.errors)


# ---- append-only guarantee holds through ingest (A7) ------------------------

def test_price_scale_does_not_fork_the_dedupe_hash(conn):
    """Regression: '0.620' and '0.62' are the SAME price. Hashing str(Decimal)
    kept the scale, so a source that reformatted its decimals minted a second
    record_hash and appended a phantom price change to an append-only table."""
    entry = make_entry()
    ingest_payloads(conn, entry, [make_payload([one_row(effective_price="0.620")])])
    second = ingest_payloads(conn, entry, [make_payload([one_row(effective_price="0.62")])])
    assert second.observations == 0 and second.duplicates == 1
    assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == 1


def test_same_day_price_change_publishes_the_newer_price(conn):
    """Regression (HIGH): the latest-per-offer selector ordered only by observed_at,
    and ONE crawl stamps every row with the same scraped_at — so a same-day price
    change resolved the tie to the OLDEST row and published the superseded price
    all the way into the exported sheet."""
    from scrapex.reports import export_source_table

    entry = make_entry()
    ingest_payloads(conn, entry, [make_payload([one_row(effective_price="100.00")])])
    ingest_payloads(conn, entry, [make_payload([one_row(effective_price="130.00")])])
    assert conn.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0] == 2

    header, rows = export_source_table(conn, "ELSEWEDYSHOP")
    prices = [r[header.index("effective_price")] for r in rows]
    assert prices == [130.00]  # the NEWER price, not the superseded one


def test_run_records_rows_seen_for_the_volume_canary(conn):
    ingest_payloads(conn, make_entry(), [make_payload([one_row(), one_row(
        external_product_id="1002", external_variant_id="5002")])])
    assert conn.execute("SELECT rows_seen FROM crawl_run").fetchone()[0] == 2


def test_ingest_never_updates_price_observation(conn):
    """Even re-ingesting a changed price never UPDATEs — it appends. The A7
    trigger would raise if ingest tried to update; this proves it doesn't."""
    entry = make_entry()
    ingest_payloads(conn, entry, [make_payload([one_row()])])
    # A changed price on the SAME business_date + offer: different record_hash
    # -> a NEW row (append), not an update.
    ingest_payloads(conn, entry, [make_payload([one_row(effective_price="1,250.00")])])
    prices = {r[0] for r in conn.execute("SELECT effective_price FROM price_observation")}
    assert prices == {1200.00, 1250.00}
