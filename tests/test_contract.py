"""The frozen contract: normalize must not drift from the committed golden vectors.

A deliberate normalize change requires re-freezing (`python -m scrapex.contract`);
an ACCIDENTAL change red-fails here — which is the whole point of freezing the
shared surface before the Python↔TS fork.
"""
from __future__ import annotations

import json

from scrapex.contract import CONTRACT_VERSION, VECTORS_FILE, golden_vectors


def test_contract_version_is_int():
    assert isinstance(CONTRACT_VERSION, int) and CONTRACT_VERSION >= 1


def test_golden_vectors_match_frozen_file():
    committed = json.loads(VECTORS_FILE.read_text(encoding="utf-8"))
    current = golden_vectors()
    assert current == committed, (
        "normalize output drifted from the frozen contract. If intentional, "
        "re-freeze: python -m scrapex.contract  (and bump CONTRACT_VERSION for a breaking change)."
    )


def test_vectors_cover_arabic_and_hash():
    v = golden_vectors()
    assert any("١" in c["in"] for c in v["fold"])          # Arabic-Indic digits covered
    assert all(len(c["out"]) == 64 for c in v["record_hash"])  # sha256 hex


# ---- contract-version DB stamp + write guardrail ----------------------------

def test_warehouse_is_stamped_and_guarded():
    import pytest

    from scrapex import db as dbmod
    from scrapex.contract import (ContractMismatchError, assert_writable,
                                  stored_contract_version)

    conn = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        assert stored_contract_version(conn) == CONTRACT_VERSION
        assert_writable(conn)  # matches -> ok
        conn.execute("UPDATE scrapex_meta SET value = '999' WHERE key = 'contract_version'")
        with pytest.raises(ContractMismatchError):
            assert_writable(conn)
    finally:
        conn.close()


def test_ingest_refuses_across_contract_versions():
    import pytest

    from scrapex import db as dbmod
    from scrapex.contract import ContractMismatchError
    from scrapex.ingest import ingest_payloads
    from tests.test_ingest import make_entry, make_payload, one_row

    conn = dbmod.connect(":memory:")
    try:
        dbmod.migrate(conn)
        conn.execute("UPDATE scrapex_meta SET value = '999' WHERE key = 'contract_version'")
        with pytest.raises(ContractMismatchError):
            ingest_payloads(conn, make_entry(), [make_payload([one_row()])])
    finally:
        conn.close()
