"""The engine-neutral shared CONTRACT (ENGINEERING.md P1 DRY; two-engine strategy).

This is the small, frozen surface that BOTH engines (Python now, TypeScript
later) must agree on byte-for-byte so they can feed ONE append-only warehouse
without silently forking history:

  1. db/schema.sql          — the warehouse shape (owned here, single source)
  2. normalize + fingerprint — the dedup/spec-fingerprint rules
  3. golden_vectors()        — a frozen conformance corpus, committed at
                               contract/normalize-vectors.v{CONTRACT_VERSION}.json

Rules:
  - `golden_vectors()` is generated from the real `normalize` — never hand-copied.
  - The committed vectors file is the FROZEN artifact; `test_contract` fails CI if
    `normalize` output drifts from it (a deliberate change requires re-freezing).
  - The JS engine is validated against the SAME committed vectors in CI (parity gate).
  - `CONTRACT_VERSION` is stamped into every warehouse (see db.py); an engine whose
    version doesn't match must refuse to write.
"""
from __future__ import annotations

from pathlib import Path

from .normalize import fold_digits, option_fingerprint, record_hash

CONTRACT_VERSION = 1

CONTRACT_DIR = Path(__file__).resolve().parent.parent / "contract"
VECTORS_FILE = CONTRACT_DIR / f"normalize-vectors.v{CONTRACT_VERSION}.json"

# Adversarial corpus: Arabic-Indic/Eastern digits, Arabic separators, mixed
# scripts, dedup collisions, price-change events, float-vs-string hashing.
_FOLD_INPUTS = ["١٢٣٤٫٥٦", "۴۲", "1,234.56", "١٬٢٣٤٫٥٦", "abc١٢٣xyz", "", "٠.٠٠٤", "ريال ٥٠٠"]
_FP_INPUTS = [
    {"Thickness_MM": "١٨", "Width_MM": "1220"},
    {"color": "أحمر", "Size": "L"},
    {"b": "2", "a": "1"},
    {"لون": "أزرق", "نوع": "قطن"},
    {"Grade": "  A2 ", "قياس": "٣.٦٦م"},
]
# record_hash is fed CANONICAL STRINGS only (the parity spike proved float repr
# diverges across languages; the contract rule is: stringify before hashing).
_HASH_INPUTS = [
    {"effective": "1200.00", "regular": "1450.00", "sale": "None", "currency": "EGP",
     "vat": "1", "availability": "in_stock", "stock": "None"},
    {"effective": "168.78", "regular": "168.78", "sale": "None", "currency": "SAR",
     "vat": "0", "availability": "in_stock", "stock": "15.0", "name": "كابل شحن"},
    {"effective": "٣٥٠", "currency": "EGP", "vat": "1", "availability": "out_of_stock",
     "stock": "None", "name": "كابل شحن و نقل بيانات"},
]


def golden_vectors() -> dict:
    """Produce the conformance corpus from the real normalize functions."""
    return {
        "contract_version": CONTRACT_VERSION,
        "fold": [{"in": s, "out": fold_digits(s)} for s in _FOLD_INPUTS],
        "fingerprint": [{"in": d, "out": option_fingerprint(d)} for d in _FP_INPUTS],
        "record_hash": [{"in": d, "out": record_hash(d)} for d in _HASH_INPUTS],
    }


class ContractMismatchError(RuntimeError):
    """The warehouse was written by a different contract version — refuse to write
    (mixing fingerprint versions in one append-only store would fork history)."""


def stamp_contract(conn) -> None:
    """Record this engine's contract version in the warehouse (idempotent)."""
    conn.execute(
        "INSERT OR IGNORE INTO scrapex_meta (key, value) VALUES ('contract_version', ?)",
        (str(CONTRACT_VERSION),),
    )


def stored_contract_version(conn) -> int | None:
    row = conn.execute("SELECT value FROM scrapex_meta WHERE key = 'contract_version'").fetchone()
    return int(row[0]) if row else None


def assert_writable(conn) -> None:
    """Guardrail called before any write: the DB's contract version must match this
    engine's, or two engines could fork the append-only fingerprints."""
    stored = stored_contract_version(conn)
    if stored is not None and stored != CONTRACT_VERSION:
        raise ContractMismatchError(
            f"this warehouse was written by contract v{stored}; this engine is "
            f"v{CONTRACT_VERSION} — refusing to write. Upgrade the engine (or migrate the data)."
        )


def freeze() -> Path:
    """Write the current golden vectors to the committed contract file."""
    import json

    CONTRACT_DIR.mkdir(parents=True, exist_ok=True)
    VECTORS_FILE.write_text(json.dumps(golden_vectors(), ensure_ascii=False, indent=1), encoding="utf-8")
    return VECTORS_FILE


if __name__ == "__main__":  # python -m scrapex.contract  → re-freeze the vectors
    print(f"froze {freeze()}")
