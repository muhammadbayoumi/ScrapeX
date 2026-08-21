"""What "the contract changed" means, as something a test can check.

WHY THIS EXISTS. `VERSION` sat at `0.2.2` for **91 commits** — last moved `adf31b2`
on 2026-08-10 — while the owner could no longer tell whether the work had gone into
the engine or the extension. Measured 2026-08-21: 42 of those commits touched
`scrapex/` or `db/`, 36 touched `extension/`, and 12 touched both. One number asked
about two products answers neither.

**A gate already existed and watched the wrong thing.** `tests/test_version.py` fails
when the CAPABILITY SET changes without `VERSION` moving. Capabilities had not
changed in those 91 commits, so the gate stayed quiet while three engine migrations
landed in one day. He ruled the criterion instead: **the engine's version moves on a
CONTRACT change** — schema, protocol, or endpoint — and the extension's on a
user-visible one (`R-35`).

WHAT COUNTS AS THE CONTRACT, and each of the three is here because breaking it breaks
somebody else's code rather than merely changing ours:

    schema     the engine migration stream. A warehouse written by a newer build
               cannot be read by an older one, which is the definition `R-24` and
               `OP-30` both turn on.
    protocol   `PROTOCOL_VERSION`. The extension refuses an engine whose protocol it
               does not know; that refusal IS the contract.
    endpoints  the routes the panel calls. A removed or renamed route is a client
               that stops working with no error we control.

WHAT IS DELIBERATELY NOT IN IT. Not the code that implements any of it, not tests, not
documents, not the number of commits. A refactor that leaves all three identical has
changed nothing another program can observe — and a version that moves for it is the
commit counter `R-05` was superseded for being.

THE FINGERPRINT IS A SORTED LIST AND NOT A HASH, on purpose. When the gate fails it
has to say WHICH part of the contract moved: a digest can only say "something did",
which is the report that sends the next session reading three subsystems to find out.
"""
from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
MIGRATIONS = ROOT / "db" / "engine" / "migrations"
APP = ROOT / "scrapex" / "webui" / "app.py"

#: Every decorator that mounts a route the panel or extension may call.
_ROUTE = re.compile(
    r"""@app\.(get|post|put|patch|delete)\(\s*["']([^"']+)["']""", re.VERBOSE)


def schema_stream() -> list[str]:
    """The engine's migrations, by name. Sorted, so order of arrival cannot matter."""
    if not MIGRATIONS.is_dir():
        return []
    return sorted(p.name for p in MIGRATIONS.glob("*.sql"))


def protocol_version() -> str:
    """The native-messaging protocol both sides agree on.

    IT LIVES IN `native.py`, NOT `version.py`, and looking rather than assuming
    mattered: the first draft imported it from `version` and raised `ImportError`.
    `extension/transport.js` holds the JavaScript copy and the two are compared by
    the contract-parity job — so this reads the Python side, which is the one a
    Python gate can be sure of.
    """
    from .native import PROTOCOL_VERSION

    return str(PROTOCOL_VERSION)


def endpoints() -> list[str]:
    """`METHOD /path` for every mounted route.

    READ FROM THE SOURCE RATHER THAN BY IMPORTING THE APP, because importing it
    builds a FastAPI instance and needs its optional dependency. A contract gate that
    only runs where `fastapi` is installed is a gate that skips, and a guard that can
    skip is the failure this repository has recorded three times.
    """
    if not APP.is_file():
        return []
    text = APP.read_text(encoding="utf-8")
    return sorted({f"{method.upper()} {path}"
                   for method, path in _ROUTE.findall(text)})


def fingerprint() -> dict[str, object]:
    """The three parts of the engine's contract, named so a failure can point."""
    return {
        "schema": schema_stream(),
        "protocol": protocol_version(),
        "endpoints": endpoints(),
    }


def differences(recorded: dict, current: dict | None = None) -> dict[str, dict]:
    """What moved, per part. Empty when the contract is unchanged.

    Returns added/removed per part rather than a boolean, because "the schema gained
    0008" and "a route disappeared" are the same verdict and very different news.
    """
    current = current or fingerprint()
    out: dict[str, dict] = {}
    for part in ("schema", "endpoints"):
        was, now = set(recorded.get(part) or []), set(current.get(part) or [])
        if was != now:
            out[part] = {"added": sorted(now - was), "removed": sorted(was - now)}
    if str(recorded.get("protocol")) != str(current.get("protocol")):
        out["protocol"] = {"was": recorded.get("protocol"),
                           "now": current.get("protocol")}
    return out


def read(path: pathlib.Path) -> dict:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: pathlib.Path, version: str) -> tuple[dict, bool]:
    """Record today's contract against `version`. Returns `(body, written)`.

    A BASELINE IS NEVER REWRITTEN FOR THE VERSION IT DESCRIBES, and the first draft
    of this got it wrong: it overwrote unconditionally, so anyone hitting the gate
    could silence it by re-running `export-version` instead of bumping the number.
    Measured — the gate went quiet exactly that way before this guard existed.

    `_write_capability_baseline` had already said why in one sentence: *"An exporter
    that refreshed it in place would go green on precisely the commit it exists to
    stop."* A gate holding its own key is not a gate.

    So an existing file describing the CURRENT version is left exactly as committed,
    and only a version it has never described gets a new one written.
    """
    body = {"version": version, **fingerprint()}
    if path.is_file():
        existing = read(path)
        if existing.get("version") == version:
            return existing, False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    return body, True
