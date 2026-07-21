"""wipe-source: one source's rows erased for a clean recrawl, loudly and safely.

Born from the GPP currency transition. 721 observations were stored as USD
conversions; the connector now stores the published local price. Currency is
outside offer identity and the canonical unit collapses USD/liter with liter,
so the two meanings would share offers and the switch would be recorded as a
~5,000% price change. The owner chose a wipe-and-recrawl over identity surgery.

What must hold: a backup happens FIRST and unconditionally; the append-only
guard on price_observation is back, byte for byte, before anyone else can see
the table; other sources' rows are untouched; the registration and the crawl
audit history survive.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from scrapex import db as dbmod
from scrapex.connectors.base import ScrapedTable
from scrapex.config import ExtractSpec, SourceEntry
from scrapex.ingest import ingest_payloads
from scrapex.rowspec import COMMODITY_PRICE, RowBuilder
from scrapex.storage import StorageRefused, wipe_source
from scrapex.vocab import ExtractKind, ExtractScope


def _entry(key: str) -> SourceEntry:
    return SourceEntry.model_validate(dict(
        source_key=key, source_name=key,
        base_url="https://www.globalpetrolprices.com", family="static-html-table",
        cadence="weekly", authority="aggregator", currency="USD",
        extract=[ExtractSpec(kind=ExtractKind.COMMODITY_PRICE,
                             scope=ExtractScope.LATEST_ONLY,
                             materials=["DIESEL"], regions=["*"])],
    ))


def _seed(conn, key: str, price: str = "0.404") -> None:
    builder = RowBuilder(COMMODITY_PRICE)
    rows = [builder.row(material_key="DIESEL", region="EG", currency="USD",
                        unit="USD/liter", vat_included="1", effective_price=price,
                        price_basis="converted")]
    table = ScrapedTable(key, ExtractKind.COMMODITY_PRICE,
                         "https://www.globalpetrolprices.com", builder.header, rows)
    ingest_payloads(conn, _entry(key), [table.to_payload()])


@pytest.fixture()
def db(tmp_path: Path):
    path = tmp_path / "harvest.db"
    conn = dbmod.connect(path)
    dbmod.migrate(conn)
    # Backups land beside the database unless configured; the temp dir keeps
    # them out of the real ~/.scrapex.
    yield conn, path
    conn.close()


def _counts(conn, key: str) -> dict:
    sid = conn.execute("SELECT source_id FROM source_site WHERE source_key=?",
                       (key,)).fetchone()
    if sid is None:
        return {"products": 0, "observations": 0}
    return {
        "products": conn.execute(
            "SELECT COUNT(*) FROM source_product WHERE source_id=?", sid).fetchone()[0],
        "observations": conn.execute(
            "SELECT COUNT(*) FROM price_observation po "
            "JOIN source_offer so ON so.offer_id=po.offer_id "
            "JOIN source_variant sv ON sv.source_variant_id=so.source_variant_id "
            "JOIN source_product sp ON sp.source_product_id=sv.source_product_id "
            "WHERE sp.source_id=?", sid).fetchone()[0],
    }


def test_the_wipe_erases_the_source_and_only_the_source(db):
    conn, path = db
    _seed(conn, "GPP_ENERGY")
    _seed(conn, "SAMEHGABRIEL", price="99.0")
    conn.commit()

    result = wipe_source(conn, path, "GPP_ENERGY")

    assert result.ok and result.rows > 0
    assert _counts(conn, "GPP_ENERGY") == {"products": 0, "observations": 0}
    kept = _counts(conn, "SAMEHGABRIEL")
    assert kept["products"] == 1 and kept["observations"] == 1, \
        "the neighbour source lost rows"


def test_a_backup_exists_before_anything_is_deleted(db):
    conn, path = db
    _seed(conn, "GPP_ENERGY")
    conn.commit()

    result = wipe_source(conn, path, "GPP_ENERGY")

    backup = Path(result.location)
    assert backup.exists(), "the pre-wipe backup is not on disk"
    check = sqlite3.connect(backup)
    try:
        n = check.execute("SELECT COUNT(*) FROM price_observation").fetchone()[0]
    finally:
        check.close()
    assert n == 1, "the backup does not hold the rows that were wiped"


def test_the_append_only_guard_is_back_and_identical(db):
    conn, path = db
    _seed(conn, "GPP_ENERGY")
    conn.commit()
    before = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='trg_price_obs_no_delete'"
    ).fetchone()[0]

    wipe_source(conn, path, "GPP_ENERGY")

    after = conn.execute(
        "SELECT sql FROM sqlite_master WHERE name='trg_price_obs_no_delete'"
    ).fetchone()
    assert after is not None and after[0] == before, "the guard changed or vanished"
    # And it guards: a bare DELETE must still be refused.
    _seed(conn, "GPP_ENERGY")
    conn.commit()
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM price_observation")


def test_registration_and_crawl_audit_survive(db):
    conn, path = db
    _seed(conn, "GPP_ENERGY")
    conn.commit()
    runs_before = conn.execute("SELECT COUNT(*) FROM crawl_run").fetchone()[0]

    wipe_source(conn, path, "GPP_ENERGY")

    assert conn.execute("SELECT COUNT(*) FROM source_site WHERE source_key='GPP_ENERGY'"
                        ).fetchone()[0] == 1, "the registration was deleted"
    assert conn.execute("SELECT COUNT(*) FROM crawl_run").fetchone()[0] == runs_before, \
        "the audit history of runs that DID happen was erased"


def test_an_unknown_source_is_refused_before_the_backup(db):
    conn, path = db
    with pytest.raises(StorageRefused, match="NEVER_INGESTED"):
        wipe_source(conn, path, "NEVER_INGESTED")


def test_a_recrawl_after_the_wipe_starts_clean(db):
    """The whole point: local-currency rows land on FRESH offers, with no USD
    row left for change detection to compare against."""
    conn, path = db
    _seed(conn, "GPP_ENERGY", price="0.404")            # the old USD world
    conn.commit()
    wipe_source(conn, path, "GPP_ENERGY")

    builder = RowBuilder(COMMODITY_PRICE)
    rows = [builder.row(material_key="DIESEL", region="EG", currency="EGP",
                        unit="liter", vat_included="1", effective_price="20.50",
                        price_basis="original")]
    table = ScrapedTable("GPP_ENERGY", ExtractKind.COMMODITY_PRICE,
                         "https://www.globalpetrolprices.com", builder.header, rows)
    ingest_payloads(conn, _entry("GPP_ENERGY"), [table.to_payload()])

    jumps = conn.execute(
        "SELECT COUNT(*) FROM change_event WHERE field_key='effective_price'"
    ).fetchone()[0]
    assert jumps == 0, "the recrawl was read as a price change — the false jump is back"
    obs = conn.execute(
        "SELECT effective_price, currency FROM price_observation").fetchall()
    assert [(r[0], r[1]) for r in obs] == [(20.5, "EGP")]
