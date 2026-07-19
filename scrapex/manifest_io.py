"""Safely add a source to sources.yaml from the UI (ENGINEERING.md S5, A7-spirit).

Append-and-validate: the new entry is validated with the SAME pydantic models
as CLI/CI, serialized as a YAML block, and appended to the file. Appending (vs
rewriting) preserves every existing comment. If the file no longer parses after
the write, it is rolled back — never a corrupted manifest.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from .config import MANIFEST_FILE, IdentityRules, SourceEntry, load_manifest

# Field order in the written block — matches the hand-authored entries (readability).
_FIELD_ORDER = ("source_key", "source_name", "base_url", "family", "cadence",
                "authority", "fetcher", "currency", "default_region", "vat_mode", "active")


class DuplicateSourceError(ValueError):
    """A source with this key already exists in the manifest."""


def entry_to_block(entry: SourceEntry) -> str:
    """Serialize one validated entry to a 2-space-indented YAML list item."""
    body: dict = {}
    dumped = entry.model_dump(mode="json")
    for key in _FIELD_ORDER:
        value = dumped.get(key)
        if key == "fetcher" and value == "http":
            continue  # default; keep the block terse
        if key == "currency" and not value:
            continue
        body[key] = value
    body["extract"] = [_extract_block(spec) for spec in dumped["extract"]]
    # Only write the advanced blocks when they carry a non-default choice, so a
    # simple source's YAML stays as short as a hand-written one.
    if dumped.get("fallback_families"):
        body["fallback_families"] = dumped["fallback_families"]
    if dumped.get("auth_required"):
        body["auth_required"] = True
    identity = dumped.get("identity") or {}
    if identity != IdentityRules().model_dump(mode="json"):
        body["identity"] = identity
    for opt in ("min_expected_rows", "max_drop_pct", "notes"):
        if dumped.get(opt) is not None:
            body[opt] = dumped[opt]

    raw = yaml.safe_dump([body], sort_keys=False, allow_unicode=True, default_flow_style=False)
    return "\n".join("  " + line if line else line for line in raw.splitlines()) + "\n"


def _extract_block(spec: dict) -> dict:
    out = {"kind": spec["kind"], "scope": spec["scope"]}
    if spec.get("materials"):
        out["materials"] = spec["materials"]
    if spec.get("regions") and spec["regions"] != ["*"]:
        out["regions"] = spec["regions"]
    if spec.get("categories"):
        out["categories"] = spec["categories"]
    return out


def add_source(entry: SourceEntry, path: Path | str = MANIFEST_FILE) -> None:
    """Validate + append `entry` to the manifest file, or raise without changing it."""
    path = Path(path)
    existing = load_manifest(path)
    if any(s.source_key == entry.source_key for s in existing.sources):
        raise DuplicateSourceError(f"source_key {entry.source_key!r} already exists")

    original = path.read_text(encoding="utf-8")
    block = entry_to_block(entry)
    new_text = original + ("" if original.endswith("\n") else "\n") + "\n" + block
    path.write_text(new_text, encoding="utf-8")
    try:
        reloaded = load_manifest(path)  # must still parse + validate as a whole
        reloaded.get(entry.source_key)
    except Exception:
        path.write_text(original, encoding="utf-8")  # roll back a bad write
        raise
