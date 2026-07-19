# The ScrapeX contract (engine-neutral, frozen)

The **small shared surface** both engines — Python (now) and TypeScript (later,
the browser product) — must agree on byte-for-byte, so they can feed **one**
append-only warehouse without silently forking price history.

| Artifact | Owner | What it fixes |
|---|---|---|
| `../db/schema.sql` | Python (single source) | the 13-table warehouse shape + append-only triggers + view |
| `../scrapex/normalize.py` spec | Python (single source) | Arabic digit folding, spec-fingerprint, dedup `record_hash` |
| `normalize-vectors.v1.json` | **neither** — generated + frozen | the conformance corpus both engines are tested against |
| `CONTRACT_VERSION` (`scrapex/contract.py`) | shared constant | stamped into every warehouse; a version mismatch must refuse to write |

## Rules

- Vectors are **generated from the real `normalize`**, never hand-copied.
- The committed `normalize-vectors.v{N}.json` is **frozen**. `tests/test_contract.py`
  fails if Python `normalize` drifts from it; `parity/parity.test.mjs` fails if the
  JS engine drifts from it. Transitively: **Python ≡ JS**.
- A deliberate change: `python -m scrapex.contract` re-freezes; bump `CONTRACT_VERSION`
  for anything that changes stored fingerprints (a breaking change).
- **Contract rule (from the parity spike):** `record_hash` is fed **canonical strings
  only** — never a language-native float (`15.0` vs `15` diverges across languages).

## CI gate

`.github/workflows/ci.yml` runs `pytest` (Python-vs-frozen) **and**
`node contract/parity/parity.test.mjs` (JS-vs-frozen) on every push. Any divergence
red-fails the build — the guardrail that lets two engines share one warehouse safely.
