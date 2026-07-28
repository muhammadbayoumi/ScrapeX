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


def set_active(source_key: str, active: bool, path: Path | str = MANIFEST_FILE) -> bool:
    """Flip ONE source's active flag in place. Returns True when the file changed.

    Surgical by the same rule as add_source: the manifest is hand-commented and
    those comments are the owner's records, so the file is edited line-wise —
    only the one `active:` line inside the one source's block — never re-dumped.
    The result must still parse and validate; a write that breaks the manifest
    is rolled back whole. Validation is also what refuses activating a
    TBD-probe placeholder, with pydantic's own message.
    """
    import re

    path = Path(path)
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)

    start = None
    for i, line in enumerate(lines):
        if re.match(rf"^  - source_key:\s*{re.escape(source_key)}\s*$", line):
            start = i
            break
    if start is None:
        raise KeyError(source_key)
    end = next((j for j in range(start + 1, len(lines))
                if re.match(r"^  - source_key:", lines[j])), len(lines))

    for j in range(start, end):
        found = re.match(r"^(\s+active:\s*)(true|false)\s*$", lines[j])
        if found:
            replacement = f"{found.group(1)}{'true' if active else 'false'}\n"
            if lines[j] == replacement:
                return False                      # already in the asked state
            lines[j] = replacement
            break
    else:
        raise ValueError(f"{source_key} has no active line to flip")

    path.write_text("".join(lines), encoding="utf-8")
    try:
        load_manifest(path)
    except Exception:
        path.write_text(original, encoding="utf-8")   # never a corrupted manifest
        raise
    return True


def _block_bounds(lines: list[str], source_key: str) -> tuple[int, int]:
    """Where one source's block starts and ends in the manifest's lines."""
    import re

    start = next((i for i, line in enumerate(lines)
                  if re.match(rf"^  - source_key:\s*{re.escape(source_key)}\s*$", line)),
                 None)
    if start is None:
        raise KeyError(source_key)
    end = next((j for j in range(start + 1, len(lines))
                if re.match(r"^  - source_key:", lines[j])), len(lines))
    return start, end


def update_source(source_key: str, entry: SourceEntry,
                  path: Path | str = MANIFEST_FILE) -> None:
    """Replace ONE source's block with `entry`, or raise without changing the file.

    Deliberately NOT surgical the way set_active is, and the difference is worth
    stating: flipping `active` touches one line and every hand-written comment
    around it survives untouched, which is the whole reason that function edits
    line-wise. An EDIT can change any field, add one, or remove one — there is
    no single line to rewrite — so the block is replaced wholesale.

    The cost is real and is the owner's to know: comments the owner wrote INSIDE
    an edited source's block do not survive the edit. Comments elsewhere in the
    file are untouched, because only this block's lines are replaced.

    Renaming the KEY is refused here. source_key is what every warehouse row
    joins on, so changing it in the manifest alone would orphan the data rather
    than rename it — see sources_admin.rename_source, which moves both together.
    """
    if entry.source_key != source_key:
        raise ValueError(
            f"cannot rename {source_key!r} to {entry.source_key!r} by editing the "
            "manifest: the warehouse joins on source_key, so the rows would be "
            "orphaned. Use the rename path, which moves the data with the name.")

    path = Path(path)
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    start, end = _block_bounds(lines, source_key)

    block = entry_to_block(entry)
    if not block.endswith("\n"):
        block += "\n"
    lines[start:end] = [block]
    path.write_text("".join(lines), encoding="utf-8")
    try:
        load_manifest(path).get(source_key)
    except Exception:
        path.write_text(original, encoding="utf-8")   # never a corrupted manifest
        raise


def remove_source(source_key: str, path: Path | str = MANIFEST_FILE) -> bool:
    """Delete ONE source's block. Returns True when the file changed.

    This removes the source from the CRAWL LIST and nothing else: its warehouse
    rows, its price history and its crawl audit trail all survive, because they
    are evidence of what a shop published and deleting the entry is not a claim
    that none of it happened. Erasing the data is a separate, louder action
    (storage.wipe_source) — the owner asked for the two to stay apart so that
    neither can be mistaken for the other.
    """
    path = Path(path)
    original = path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)
    try:
        start, end = _block_bounds(lines, source_key)
    except KeyError:
        return False
    del lines[start:end]
    path.write_text("".join(lines), encoding="utf-8")
    try:
        load_manifest(path)
    except Exception:
        path.write_text(original, encoding="utf-8")
        raise
    return True
