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
import hashlib
import re
import uuid
from datetime import datetime, timezone
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


def safe_token(text: str) -> str:
    """A resume token that survives the round trip through a filename.

    write_payload SANITISES a token into the stem and list_tokens reads the
    SANITISED form back, so a connector holding the raw value compares against
    something it will never match — the crawl would refetch every page and the
    resume would look like it simply did not work. The docstring below warns
    about this; nothing enforced it.

    A URL is the natural checkpoint for a sitemap crawler (one request per
    product, no page numbers to count), and a URL is exactly the shape that
    does not survive sanitising. Hashing sidesteps both problems: the result is
    already filename-safe, so sanitising is a no-op, and two different URLs
    cannot collide into one token the way two sanitised URLs can.
    """
    return "t-" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:20]


def token_survives_a_filename(token: str) -> bool:
    """Does this token read back identically? The invariant resume depends on."""
    return token == re.sub(r"[^A-Za-z0-9_-]", "-", token)


def list_tokens(base: Path | str, source_key: str) -> set[str]:
    """The page tokens already journaled for this source (resume's skip set)."""
    target = _source_dir(base, source_key)
    if not target.is_dir():
        return set()
    return {p.name.split(_TOKEN_SEP, 1)[0]
            for p in target.glob(f"*{_TOKEN_SEP}*.json")}


def journal_state(base: Path | str, source_key: str) -> dict:
    """What this source has KEPT: pages a resume would skip, and when it stopped.

    The journal was already the resume checkpoint; nothing could REPORT it, so a
    source with 871 pages on disk looked exactly like one with none and the only
    button on offer was the one that throws them away.

    `pages` counts TOKENS, not files: the token set is precisely what resume
    hands the connector as its skip set (see `list_tokens`), and a count that
    could disagree with it would be a number the owner cannot act on.

    `stopped_at` is the newest page's mtime, not the scraped_at buried in its
    filename. Capture writes each page the moment it arrives, so the two mark
    the same instant, and mtime does not tie this readout to the filename
    layout — which exists to carry the token, not to be parsed back.

    A filename scan and a stat per page: no JSON is parsed, because the panel
    asks this for every source on every refresh.
    """
    target = _source_dir(base, source_key)
    if not target.is_dir():
        return {"pages": 0, "stopped_at": None}
    newest: dict[str, float] = {}
    for p in target.glob(f"*{_TOKEN_SEP}*.json"):
        try:
            mtime = p.stat().st_mtime
        except OSError:
            # The worker clears this directory the moment an ingest succeeds,
            # and the panel asks for this on a refresh — so the scan CAN race a
            # job finishing. A page that vanished between the listing and the
            # stat costs one page off a count, never the whole answer: raising
            # here would fail /api/sources, and the panel would report the
            # engine as unreachable because a crawl had gone WELL.
            continue
        token = p.name.split(_TOKEN_SEP, 1)[0]
        newest[token] = max(newest.get(token, 0.0), mtime)
    if not newest:
        return {"pages": 0, "stopped_at": None}
    stopped = datetime.fromtimestamp(max(newest.values()), timezone.utc)
    return {"pages": len(newest),
            "stopped_at": stopped.strftime("%Y-%m-%dT%H:%M:%SZ")}


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
