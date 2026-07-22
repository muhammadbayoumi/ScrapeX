"""Local inbox: run the collect -> ingest loop on one machine without the cloud
funnel (dev/interactive path). Reuses the funnel payload format verbatim (T8),
so the local path and the sheet path carry byte-identical payloads.

Production path: connector -> funnel -> staging sheet -> ingest.
Local path:      connector -> local inbox dir -> ingest.

The JOB JOURNAL reuses these functions on a SEPARATE base dir: during a job,
capture writes each fetched page's payload here as it arrives, so a pause or
crash mid-crawl loses nothing — the filenames (see `token` below) double as
the resume checkpoint. A separate dir because the CLI inbox holds payloads the
owner crawled and has not ingested YET; a job clearing its own journal must
never touch those.
"""
from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from .payload import FunnelPayload

DEFAULT_INBOX_DIR = Path(os.environ.get("SCRAPEX_INBOX_DIR", str(Path.home() / ".scrapex" / "inbox")))
JOURNAL_DIR = Path(os.environ.get("SCRAPEX_JOURNAL_DIR", str(Path.home() / ".scrapex" / "job-journal")))

# token__rest.json — "__" separates the page token from the uniqueness suffix,
# so listing tokens is a filename scan, never a JSON parse of 400 files.
_TOKEN_SEP = "__"


def _source_dir(base: Path | str, source_key: str) -> Path:
    return Path(base) / source_key


def write_payload(base: Path | str, payload: FunnelPayload, token: str = "") -> Path:
    target = _source_dir(base, payload.source_key)
    target.mkdir(parents=True, exist_ok=True)
    stem = f"{payload.scraped_at.replace(':', '')}_{uuid.uuid4().hex[:8]}"
    if token:
        # The token is a resume checkpoint carried IN the filename (the payload
        # contract is frozen). Sanitised, not rejected: a token that round-trips
        # differently would silently never match on resume.
        stem = f"{re.sub(r'[^A-Za-z0-9_-]', '-', token)}{_TOKEN_SEP}{stem}"
    path = target / f"{stem}.json"
    path.write_text(payload.model_dump_json(), encoding="utf-8")
    return path


def list_tokens(base: Path | str, source_key: str) -> set[str]:
    """The page tokens already journaled for this source (resume's skip set)."""
    target = _source_dir(base, source_key)
    if not target.is_dir():
        return set()
    return {p.name.split(_TOKEN_SEP, 1)[0]
            for p in target.glob(f"*{_TOKEN_SEP}*.json")}


def clear_untokenized(base: Path | str, source_key: str) -> int:
    """Drop journal entries that carry no page token, keeping the tokenized ones.

    Resume calls this first: untokenized tables (summaries, single-page
    connectors, list rows) are re-emitted by the re-run, so their journaled
    copies from the interrupted attempt would be ingested twice.
    """
    target = _source_dir(base, source_key)
    if not target.is_dir():
        return 0
    removed = 0
    for p in target.glob("*.json"):
        if _TOKEN_SEP not in p.name:
            p.unlink()
            removed += 1
    return removed


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
