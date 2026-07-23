"""Funnel client: delivers payloads to the Apps Script staging inbox (A6, S1, T8).

Durability per environment (A6):
- Local/interactive: every batch is spooled to a persistent outbox BEFORE the
  first send attempt (TelemetryOutbox pattern from the add-in); successful
  delivery removes the spool file; `drain()` retries leftovers on any later run.
  An outbox size alarm makes producer>consumer imbalance loud.
- CI (ephemeral runner): callers use send() with in-run retries and treat a
  final failure as a red job; the workflow uploads the undelivered spool dir
  as an artifact. (The CLI wires this; this module stays environment-agnostic.)

Two properties this transport now has, and did not (A9):
- Every request is SIGNED: hmac-sha256 over the canonical body, keyed with the
  same shared token. The token still travels in the body — the signature proves
  the body was not altered on the way, it does not replace authentication.
- Delivery ADAPTS: a chunk the funnel chokes on is halved and retried, down to
  one row per chunk. Only a single row that still cannot be delivered fails.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import uuid
from collections.abc import Mapping
from pathlib import Path

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .payload import FunnelPayload, split_into_chunks

DEFAULT_OUTBOX_DIR = Path(os.environ.get("SCRAPEX_OUTBOX_DIR", str(Path.home() / ".scrapex" / "outbox")))

# A6: alarm threshold — if this many undelivered batches accumulate, something
# upstream is broken and the owner must know before the disk quietly fills.
OUTBOX_ALARM_THRESHOLD = 50

# The body field carrying the signature. It is EXCLUDED from what it signs, and
# it is additive on the wire: a script that was pasted before signing existed
# simply ignores the extra key, so a new client never locks an old sheet out.
SIGNATURE_FIELD = "signature"

_RETRYABLE = (httpx.TransportError, httpx.HTTPStatusError)

# HTTP answers that mean "that was too much for one Apps Script execution"
# rather than "your request was wrong". 500 is in the list because an Apps
# Script run that burns its 6-minute budget surfaces as a generic 500 from
# Google, which is exactly the case this feature exists for; a genuinely broken
# script also answers 500, and the halving loop below stops at one row, so the
# worst that costs is a bounded handful of extra attempts before the same loud
# failure. (Q3: guess narrowly, fail loudly.)
_SIZE_SHAPED_STATUS = frozenset({408, 413, 500, 502, 503, 504})

# The same verdict for a funnel that answered in words instead of a status code.
_SIZE_SHAPED_WORDS = (
    "timeout", "timed out", "exceeded maximum execution", "too large",
    "too big", "request entity", "payload size",
)


def canonical_body(body: Mapping[str, object]) -> str:
    """The ONE text a signer and a verifier hash. Produced here, only here.

    Sorted keys, no whitespace, pure ASCII. It has to be a re-derivable form,
    not the bytes httpx happened to put on the wire: Apps Script hands doPost a
    parsed request, so the sheet can only rebuild what it received — and the two
    sides can only agree on a shape that neither JSON library can perturb.
    ensure_ascii keeps the hashed text 7-bit, which also removes every charset
    question from Utilities.computeHmacSha256Signature on the other side.
    """
    return json.dumps(
        {key: value for key, value in body.items() if key != SIGNATURE_FIELD},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )


def sign_body(token: str, body: Mapping[str, object]) -> str:
    """hmac-sha256(token, canonical_body(body)) as lowercase hex."""
    return hmac.new(
        token.encode("utf-8"), canonical_body(body).encode("ascii"), hashlib.sha256
    ).hexdigest()


class FunnelDeliveryError(RuntimeError):
    """Raised when a payload could not be delivered after all retries.

    `size_shaped` records whether the failure LOOKED like "that batch was too
    big for one Apps Script execution" (a timeout, a 413, a 5xx from a run that
    ran out of budget). The verdict is reached where the original exception is
    still in hand and carried here, because by the time delivery decides to
    shrink the batch the exception is gone (A9).
    """

    def __init__(self, message: str, *, size_shaped: bool = False) -> None:
        super().__init__(message)
        self.size_shaped = size_shaped


class OutboxAlarm(RuntimeError):
    """Outbox grew past OUTBOX_ALARM_THRESHOLD (A6)."""


def _looks_size_shaped(exc: Exception) -> bool:
    """Is this failure the funnel saying "too much at once"?

    A connect timeout is deliberately NOT: the request was never taken, so its
    size cannot be the reason, and treating it as one would walk the whole
    halving ladder against a funnel that is simply unreachable — turning a
    two-minute honest failure into half an hour of pointless retrying. Same for
    a pool timeout, which is this client's own plumbing, not the funnel's.
    """
    if isinstance(exc, httpx.TimeoutException):
        return not isinstance(exc, (httpx.ConnectTimeout, httpx.PoolTimeout))
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _SIZE_SHAPED_STATUS
    return False


def _refusal_is_size_shaped(ack: Mapping[str, object]) -> bool:
    """The funnel answered ok:false — did it say the batch was too big?"""
    text = str(ack.get("error") or "").lower()
    return any(word in text for word in _SIZE_SHAPED_WORDS)


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
        sign: bool = True,
    ) -> None:
        if not endpoint or not token:
            raise ValueError("funnel endpoint and token are required (A4: set via env/CLI)")
        self._endpoint = endpoint
        self._token = token
        self._outbox = Path(outbox_dir)
        self._timeout_s = timeout_s
        # Signing is on by default and needs no configuration: the signature is
        # an EXTRA body field, so a sheet running a script from before signing
        # existed keeps working unchanged. `sign=False` exists for the owner who
        # has to prove that (and for the tests that do).
        self._sign = sign

    # ---- delivery ----------------------------------------------------------

    def send(self, payload: FunnelPayload) -> int:
        """Chunk + deliver one payload. Returns the number of chunks sent.

        Spool-first (A6): the batch is written to the outbox before the first
        attempt; the spool file is removed only after EVERY piece is acked —
        including the pieces an adaptive re-plan invented along the way.
        """
        spool_file = self._spool(payload)
        pieces = self._deliver(payload)
        spool_file.unlink(missing_ok=True)
        return pieces

    def drain(self) -> tuple[int, int]:
        """Retry every spooled batch. Returns (delivered, still_pending)."""
        delivered = 0
        pending = 0
        for spool_file in sorted(self._outbox.glob("*.json")):
            payload = FunnelPayload.model_validate_json(
                spool_file.read_text(encoding="utf-8")
            )
            try:
                self._deliver(payload)
            except FunnelDeliveryError:
                pending += 1
                continue
            spool_file.unlink(missing_ok=True)
            delivered += 1
        return delivered, pending

    def call_action(self, action: str, **fields) -> dict:
        """POST one non-chunk action and return the funnel's whole answer.

        Unlike a chunk, the ANSWER is the point: staging_sync returns what the
        sheet actually wrote or refused. Failures come back as {ok: False}
        rather than raising — an older deployed script or a hiccup is a state
        to REPORT in the sync UI, never a delivery failure to retry."""
        body = {"action": action, "token": self._token, **fields}
        try:
            response = httpx.post(self._endpoint, json=self._signed(body),
                                  timeout=self._timeout_s, follow_redirects=True)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001 — reported, not raised
            return {"ok": False, "error": f"unreachable: {exc!r}"}

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

    def _signed(self, body: dict) -> dict:
        """Attach the signature, or leave the body exactly as it was.

        The token stays in the body: the signature proves nobody rewrote the
        rows in flight, it does not authenticate on its own, and removing the
        token would lock out every sheet whose script has not been re-pasted.
        The signature value is never logged, echoed or returned anywhere — the
        only place it exists is on the wire.
        """
        if not self._sign:
            return body
        return {**body, SIGNATURE_FIELD: sign_body(self._token, body)}

    def _deliver(self, payload: FunnelPayload) -> int:
        """Deliver one batch, shrinking the chunk plan when the funnel chokes.

        WHY the whole batch is re-planned instead of the one fat chunk being
        split where it stands: the consumer reassembles by (source_key,
        scraped_at) and demands indexes 1..total against ONE agreed total, so a
        chunk cannot grow a sibling after its neighbours have already gone out
        announcing the old total — that would leave a batch that can never be
        reassembled. Re-planning keeps every sequence internally consistent. The
        cost is that the abandoned attempt's chunks stay in the append-only
        inbox; the pasted script tells the attempts apart by their total and
        publishes the complete one (StagingAppScript.collectBatches_).
        """
        max_rows: int | None = None
        while True:
            chunks = split_into_chunks(payload, max_rows=max_rows)
            too_big = 0
            for chunk in chunks:
                try:
                    self._post_chunk(chunk)
                except FunnelDeliveryError as exc:
                    rows = len(chunk.rows)
                    if not exc.size_shaped or rows <= 1:
                        # Either a plain refusal (bad token, ragged rows) or the
                        # floor: one row that still cannot be delivered is a
                        # real failure, not a sizing problem to grind away at.
                        raise
                    too_big = rows
                    break
            if not too_big:
                return len(chunks)
            max_rows = too_big // 2

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
            # payload): fail loud immediately (Q3). A refusal that names size or
            # time is the exception: it is worth re-planning smaller, so the
            # verdict rides along on the error.
            raise FunnelDeliveryError(f"funnel refused chunk: {ack}",
                                      size_shaped=_refusal_is_size_shaped(ack))

    def _post_chunk(self, chunk: FunnelPayload) -> None:
        body = {
            "action": "staging_chunk",
            "token": self._token,
            "payload": json.loads(chunk.model_dump_json()),
        }
        try:
            self._post_once(self._signed(body))
        except FunnelDeliveryError:
            raise
        except _RETRYABLE as exc:
            raise FunnelDeliveryError(
                f"chunk delivery failed after retries: {exc!r}",
                size_shaped=_looks_size_shaped(exc),
            ) from exc
