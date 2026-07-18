"""Local inbox: run the collect -> ingest loop on one machine without the cloud
funnel (dev/interactive path). Reuses the funnel payload format verbatim (T8),
so the local path and the sheet path carry byte-identical payloads.

Production path: connector -> funnel -> staging sheet -> ingest.
Local path:      connector -> local inbox dir -> ingest.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from .payload import FunnelPayload

DEFAULT_INBOX_DIR = Path(os.environ.get("SCRAPEX_INBOX_DIR", str(Path.home() / ".scrapex" / "inbox")))


def _source_dir(base: Path | str, source_key: str) -> Path:
    return Path(base) / source_key


def write_payload(base: Path | str, payload: FunnelPayload) -> Path:
    target = _source_dir(base, payload.source_key)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{payload.scraped_at.replace(':', '')}_{uuid.uuid4().hex[:8]}.json"
    path.write_text(payload.model_dump_json(), encoding="utf-8")
    return path


def read_payloads(base: Path | str, source_key: str) -> list[FunnelPayload]:
    target = _source_dir(base, source_key)
    if not target.is_dir():
        return []
    return [
        FunnelPayload.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(target.glob("*.json"))
    ]


def clear(base: Path | str, source_key: str) -> int:
    target = _source_dir(base, source_key)
    if not target.is_dir():
        return 0
    removed = 0
    for p in target.glob("*.json"):
        p.unlink()
        removed += 1
    return removed
