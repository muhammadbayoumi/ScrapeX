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
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from .payload import (
    PAYLOAD_COMPAT_VERSION,
    FunnelPayload,
    compat_generation,
    compat_problem,
)

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


@dataclass(frozen=True)
class SkippedPage:
    """One journaled page that could not be read, and why."""
    name: str      # the filename, so the page can actually be found on disk
    kind: str      # 'too_old' | 'too_new' | 'unreadable' — groups the report
    detail: str


@dataclass(frozen=True)
class JournalRead:
    """The pages that read back, and an account of the ones that did not."""
    payloads: list[FunnelPayload]
    skipped: list[SkippedPage]

    def report(self) -> list[str]:
        """One sentence per KIND of loss, each carrying its count and its cause.

        Grouped rather than one line per page: 871 sentences is not a report,
        and the owner's question is "what did I lose, and why", asked once.
        """
        total = len(self.payloads) + len(self.skipped)
        lines = []
        for kind, verdict in (
            ("too_old", "DISCARDED and will be re-fetched"),
            ("too_new", "left for a NEWER build to read — upgrade rather than re-crawl"),
            ("unreadable", "DISCARDED and will be re-fetched"),
        ):
            group = [s for s in self.skipped if s.kind == kind]
            if not group:
                continue
            # The distinct causes, in first-seen order: one truncated page and
            # 871 stale ones are different facts and must not average together.
            causes = list(dict.fromkeys(s.detail for s in group))
            shown = "; ".join(causes[:2])
            if len(causes) > 2:
                shown += f"; and {len(causes) - 2} other reason(s)"
            lines.append(
                f"{len(group)} of {total} journaled page(s) could not be read "
                f"and were {verdict} — {shown} [first: {group[0].name}]")
        return lines


def read_payloads(base: Path | str, source_key: str) -> JournalRead:
    """Read a source's journaled pages, CONTAINING failure to the page.

    A journal is an accumulation of SEPARATE pages, each written the moment it
    arrived. This was a list comprehension, so the first page that would not
    validate raised and took every other page with it — on 2026-07-30 one
    stale page made 3,570 of ELBUROJ's unreachable, the survivors of nine
    attempts against a 10-second crawl-delay. Refusing 3,570 pages because of
    one is the opposite of what a journal is for, and it is a separate bug
    from the version gate: a truncated page does the same thing, and would go
    on doing it however wide the compat range gets.

    ISOLATED IS NOT SILENT (the rule `_record_implied_rate` in ingest.py spells
    out): every skipped page is returned in `skipped` with its name and its
    reason, for the caller to put on the run's record. A page dropped here is
    dropped for good — capture clears the journal after a successful ingest —
    so a silent skip would be exactly the quiet discard the owner's standing
    rule forbids: a cancel discards the journal, a pause keeps it, and nothing
    else may throw pages away without saying so.
    """
    target = _source_dir(base, source_key)
    if not target.is_dir():
        return JournalRead(payloads=[], skipped=[])
    payloads: list[FunnelPayload] = []
    skipped: list[SkippedPage] = []
    for p in sorted(target.glob("*.json")):
        try:
            raw = p.read_text(encoding="utf-8")
        except OSError as exc:
            # The worker clears this directory the moment an ingest succeeds,
            # so the scan can race a job finishing (see journal_state).
            skipped.append(SkippedPage(p.name, "unreadable",
                                       f"file could not be read: {exc}"))
            continue
        try:
            payloads.append(FunnelPayload.model_validate_json(raw))
        except ValidationError as exc:
            kind, detail = _why_skipped(raw, exc)
            skipped.append(SkippedPage(p.name, kind, detail))
        except ValueError as exc:
            # Not even JSON: truncated by a crash mid-write, most likely.
            skipped.append(SkippedPage(p.name, "unreadable",
                                       f"not a readable payload: {exc}"))
    return JournalRead(payloads=payloads, skipped=skipped)


def _why_skipped(raw: str, exc: ValidationError) -> tuple[str, str]:
    """Classify a refused page: too old, too new, or simply broken.

    The two version numbers are read from the RAW json rather than the model,
    because the model is precisely what refused to build — and the verdict
    comes from `payload.compat_problem`, the ONE definition of what this build
    can read, shared with the wire check and the Apps Script consumer. Nothing
    here decides compatibility; it only asks, and reports the answer.
    """
    try:
        page = json.loads(raw)
        version = page.get("payload_version")
        declared = page.get("payload_compat_version")
    except (ValueError, AttributeError):
        version = declared = None
    if isinstance(version, int):
        problem = compat_problem(version, declared if isinstance(declared, int) else None)
        if problem:
            generation = compat_generation(
                version, declared if isinstance(declared, int) else None)
            # A generation this build has never heard of, or one above its own,
            # both mean the same repair — a newer reader. Re-crawling would
            # only produce the same page again.
            too_new = generation is None or generation > PAYLOAD_COMPAT_VERSION
            return ("too_new" if too_new else "too_old"), problem
    # A version this build reads that STILL would not validate is a broken
    # page, not a stale one: the version is not what is wrong with it. Keep it
    # to the first problem — the full pydantic report is a paragraph.
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(x) for x in first.get("loc", ())) or "payload"
    return "unreadable", f"{where}: {first.get('msg', exc)}"


def clear(base: Path | str, source_key: str) -> int:
    target = _source_dir(base, source_key)
    if not target.is_dir():
        return 0
    removed = 0
    for p in target.glob("*.json"):
        p.unlink()
        removed += 1
    return removed
