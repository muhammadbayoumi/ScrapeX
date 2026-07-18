"""Funnel client: delivers payloads to the Apps Script staging inbox (A6, S1, T8).

Durability per environment (A6):
- Local/interactive: every batch is spooled to a persistent outbox BEFORE the
  first send attempt (TelemetryOutbox pattern from the add-in); successful
  delivery removes the spool file; `drain()` retries leftovers on any later run.
  An outbox size alarm makes producer>consumer imbalance loud.
- CI (ephemeral runner): callers use send() with in-run retries and treat a
  final failure as a red job; the workflow uploads the undelivered spool dir
  as an artifact. (The CLI wires this; this module stays environment-agnostic.)
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .payload import FunnelPayload, split_into_chunks

DEFAULT_OUTBOX_DIR = Path(os.environ.get("SCRAPEX_OUTBOX_DIR", str(Path.home() / ".scrapex" / "outbox")))

# A6: alarm threshold — if this many undelivered batches accumulate, something
# upstream is broken and the owner must know before the disk quietly fills.
OUTBOX_ALARM_THRESHOLD = 50

_RETRYABLE = (httpx.TransportError, httpx.HTTPStatusError)


class FunnelDeliveryError(RuntimeError):
    """Raised when a payload could not be delivered after all retries."""


class OutboxAlarm(RuntimeError):
    """Outbox grew past OUTBOX_ALARM_THRESHOLD (A6)."""


class FunnelClient:
    """POSTs chunked payloads to the staging Apps Script endpoint.

    The endpoint and token come from the environment/CLI — never from code (A4).
    """

    def __init__(
        self,
        endpoint: str,
        token: str,
        outbox_dir: Path | str = DEFAULT_OUTBOX_DIR,
        timeout_s: float = 30.0,
    ) -> None:
        if not endpoint or not token:
            raise ValueError("funnel endpoint and token are required (A4: set via env/CLI)")
        self._endpoint = endpoint
        self._token = token
        self._outbox = Path(outbox_dir)
        self._timeout_s = timeout_s

    # ---- delivery ----------------------------------------------------------

    def send(self, payload: FunnelPayload) -> int:
        """Chunk + deliver one payload. Returns the number of chunks sent.

        Spool-first (A6): the batch is written to the outbox before the first
        attempt; the spool file is removed only after ALL chunks are acked.
        """
        spool_file = self._spool(payload)
        chunks = split_into_chunks(payload)
        for chunk in chunks:
            self._post_chunk(chunk)
        spool_file.unlink(missing_ok=True)
        return len(chunks)

    def drain(self) -> tuple[int, int]:
        """Retry every spooled batch. Returns (delivered, still_pending)."""
        delivered = 0
        pending = 0
        for spool_file in sorted(self._outbox.glob("*.json")):
            payload = FunnelPayload.model_validate_json(
                spool_file.read_text(encoding="utf-8")
            )
            try:
                for chunk in split_into_chunks(payload):
                    self._post_chunk(chunk)
            except FunnelDeliveryError:
                pending += 1
                continue
            spool_file.unlink(missing_ok=True)
            delivered += 1
        return delivered, pending

    def outbox_count(self) -> int:
        return len(list(self._outbox.glob("*.json"))) if self._outbox.is_dir() else 0

    # ---- internals ---------------------------------------------------------

    def _spool(self, payload: FunnelPayload) -> Path:
        self._outbox.mkdir(parents=True, exist_ok=True)
        count = self.outbox_count()
        if count >= OUTBOX_ALARM_THRESHOLD:
            raise OutboxAlarm(
                f"outbox holds {count} undelivered batches (threshold "
                f"{OUTBOX_ALARM_THRESHOLD}) — fix delivery before scraping more (A6)"
            )
        name = f"{payload.source_key}_{payload.scraped_at.replace(':', '')}_{uuid.uuid4().hex[:8]}.json"
        spool_file = self._outbox / name
        spool_file.write_text(payload.model_dump_json(), encoding="utf-8")
        return spool_file

    @retry(
        retry=retry_if_exception_type(_RETRYABLE),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1, min=1, max=20),
        reraise=True,
    )
    def _post_once(self, body: dict) -> None:
        response = httpx.post(self._endpoint, json=body, timeout=self._timeout_s, follow_redirects=True)
        response.raise_for_status()
        ack = response.json()
        if not ack.get("ok"):
            # The funnel answered but refused — NOT retryable (bad token, bad
            # payload): fail loud immediately (Q3).
            raise FunnelDeliveryError(f"funnel refused chunk: {ack}")

    def _post_chunk(self, chunk: FunnelPayload) -> None:
        body = {
            "action": "staging_chunk",
            "token": self._token,
            "payload": json.loads(chunk.model_dump_json()),
        }
        try:
            self._post_once(body)
        except FunnelDeliveryError:
            raise
        except _RETRYABLE as exc:
            raise FunnelDeliveryError(
                f"chunk delivery failed after retries: {exc!r}"
            ) from exc
