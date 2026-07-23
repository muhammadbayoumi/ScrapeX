"""A6/S1: funnel client — spool-first durability, chunk delivery, loud refusals.

The endpoint is mocked at the httpx layer (no network, T1-compatible); the REAL
Apps Script consumer is covered by the shared contract fixtures (T8).
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from scrapex.funnel import (
    OUTBOX_ALARM_THRESHOLD,
    SIGNATURE_FIELD,
    FunnelClient,
    FunnelDeliveryError,
    OutboxAlarm,
    canonical_body,
    sign_body,
)
from scrapex.payload import PAYLOAD_VERSION, FunnelPayload


@pytest.fixture(autouse=True)
def no_retry_backoff(monkeypatch):
    """Skip tenacity's real waiting, not its retrying.

    The adaptive path (A9) deliberately provokes several failed chunks, and each
    one costs 1+2+4 seconds of genuine sleep. What these tests assert is the
    number of attempts and what arrived; the wall-clock cost of the backoff is
    the transport's business, not theirs.
    """
    monkeypatch.setattr(FunnelClient._post_once.retry, "sleep", lambda _seconds: None)


def make_payload(rows: int = 2) -> FunnelPayload:
    return FunnelPayload(
        payload_version=PAYLOAD_VERSION,
        source_key="MADAR",
        kind="product_prices",
        client="cli",
        scraped_at="2026-07-16T10:00:00Z",
        source_url="https://www.madar.com/graphql",
        header=["id", "price"],
        rows=[[str(i), "168.78"] for i in range(rows)],
    )


@pytest.fixture()
def received() -> list[dict]:
    return []


@pytest.fixture()
def ok_transport(received, monkeypatch):
    """Mock endpoint that acks every chunk and records what it got."""

    def fake_post(url, json=None, **kwargs):
        received.append(json)
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)


def test_send_delivers_and_clears_spool(tmp_path: Path, ok_transport, received):
    client = FunnelClient("https://funnel.example/exec", "tok", outbox_dir=tmp_path)
    sent = client.send(make_payload())
    assert sent == 1
    assert received[0]["action"] == "staging_chunk"
    assert received[0]["token"] == "tok"
    assert received[0]["payload"]["source_key"] == "MADAR"
    assert client.outbox_count() == 0  # spool removed after full delivery


def test_transport_failure_leaves_spool_then_drain_recovers(tmp_path: Path, monkeypatch):
    calls = {"n": 0}

    def failing_post(url, json=None, **kwargs):
        calls["n"] += 1
        raise httpx.ConnectError("down", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", failing_post)
    client = FunnelClient("https://funnel.example/exec", "tok", outbox_dir=tmp_path)
    with pytest.raises(FunnelDeliveryError):
        client.send(make_payload())
    assert client.outbox_count() == 1  # batch survived the outage (A6)
    assert calls["n"] == 4  # 1 + 3 retries

    # Funnel comes back: drain() delivers the leftover batch.
    delivered_bodies: list[dict] = []

    def ok_post(url, json=None, **kwargs):
        delivered_bodies.append(json)
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", ok_post)
    delivered, pending = client.drain()
    assert (delivered, pending) == (1, 0)
    assert client.outbox_count() == 0
    assert delivered_bodies[0]["payload"]["source_key"] == "MADAR"


def test_funnel_refusal_is_not_retried(tmp_path: Path, monkeypatch):
    """ok:false (bad token / bad payload) must fail immediately — retrying a
    refusal would hammer the funnel with garbage (Q3)."""
    calls = {"n": 0}

    def refusing_post(url, json=None, **kwargs):
        calls["n"] += 1
        return httpx.Response(200, json={"ok": False, "error": "unauthorized"},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", refusing_post)
    client = FunnelClient("https://funnel.example/exec", "tok", outbox_dir=tmp_path)
    with pytest.raises(FunnelDeliveryError, match="refused"):
        client.send(make_payload())
    assert calls["n"] == 1  # no retry on refusal


def test_outbox_alarm_fires_at_threshold(tmp_path: Path):
    client = FunnelClient("https://funnel.example/exec", "tok", outbox_dir=tmp_path)
    for i in range(OUTBOX_ALARM_THRESHOLD):
        (tmp_path / f"stale_{i}.json").write_text(
            make_payload().model_dump_json(), encoding="utf-8"
        )
    with pytest.raises(OutboxAlarm, match="undelivered"):
        client.send(make_payload())


def test_missing_endpoint_or_token_fails_fast():
    with pytest.raises(ValueError, match="required"):
        FunnelClient("", "tok")
    with pytest.raises(ValueError, match="required"):
        FunnelClient("https://funnel.example/exec", "")


def test_signed_body_matches_a_known_vector():
    """Pins the WIRE FORM of a signature, not the helper that makes one.

    The Apps Script verifier rebuilds this exact text from the request it parsed
    (StagingAppScript.canonicalJson_), so key order, spacing and the escaping of
    non-ASCII are part of the contract: change any of them here and every signed
    send stops verifying on the sheet. The Arabic cell is in the vector on
    purpose — it is what the real sources carry, and it is where two JSON
    libraries most easily disagree.
    """
    body = {
        "action": "staging_chunk",
        "token": "shared-token",
        "payload": {"source_key": "MADAR", "rows": [["منتج", "168.78"]],
                    "chunk": {"index": 1, "total": 2}},
    }
    assert canonical_body(body) == (
        '{"action":"staging_chunk","payload":{"chunk":{"index":1,"total":2},'
        '"rows":[["\\u0645\\u0646\\u062a\\u062c","168.78"]],"source_key":"MADAR"},'
        '"token":"shared-token"}'
    )
    assert sign_body("shared-token", body) == \
        "e93b097f367901661114c15c23d99e46783141ae43b02c77b6e0507157282009"


def test_the_signature_covers_the_body_but_never_itself():
    body = {"action": "staging_sync", "token": "tok"}
    # The field a verifier has to strip before hashing must not change the hash.
    assert sign_body("tok", {**body, SIGNATURE_FIELD: "anything"}) == sign_body("tok", body)
    assert sign_body("tok", {**body, "action": "run_log"}) != sign_body("tok", body)
    assert sign_body("other-token", body) != sign_body("tok", body)


def test_every_chunk_goes_out_signed_over_exactly_what_was_sent(
        tmp_path: Path, ok_transport, received):
    client = FunnelClient("https://funnel.example/exec", "tok", outbox_dir=tmp_path)
    client.send(make_payload())
    body = received[0]
    assert body[SIGNATURE_FIELD] == sign_body("tok", body)  # verifies as received
    assert "tok" not in body[SIGNATURE_FIELD]               # the key never rides along

    # Rewriting one cell in flight is exactly what this is for.
    tampered = json.loads(json.dumps(body))
    tampered["payload"]["rows"][0][1] = "0.01"
    assert tampered[SIGNATURE_FIELD] != sign_body("tok", tampered)


def test_an_unsigned_client_still_delivers(tmp_path: Path, ok_transport, received):
    """Signing off must change nothing else: the token is still what authorises
    the request, and a sheet whose script predates signing still gets a body it
    understands."""
    client = FunnelClient("https://funnel.example/exec", "tok",
                          outbox_dir=tmp_path, sign=False)
    assert client.send(make_payload()) == 1
    assert SIGNATURE_FIELD not in received[0]
    assert received[0]["token"] == "tok" and received[0]["action"] == "staging_chunk"


def test_a_non_chunk_action_is_signed_too(tmp_path: Path, ok_transport, received):
    client = FunnelClient("https://funnel.example/exec", "tok", outbox_dir=tmp_path)
    client.call_action("staging_sync")
    assert received[0][SIGNATURE_FIELD] == sign_body("tok", received[0])


def test_an_oversized_chunk_is_halved_until_the_funnel_swallows_it(
        tmp_path: Path, monkeypatch, received):
    """The gap this closes: a batch too big for one Apps Script execution used
    to come back as a timeout and stay undelivered forever. Now the plan shrinks
    until it fits — and every row still arrives exactly once, in order, under
    ONE agreed chunk total (the sheet reassembles by that total)."""
    def picky_post(url, json=None, **kwargs):
        if len(json["payload"]["rows"]) > 3:
            raise httpx.ReadTimeout("exceeded maximum execution time",
                                    request=httpx.Request("POST", url))
        received.append(json)
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", picky_post)
    payload = make_payload(rows=8)
    client = FunnelClient("https://funnel.example/exec", "tok", outbox_dir=tmp_path)
    pieces = client.send(payload)

    assert pieces == len(received) == 4          # 8 rows -> 4 -> 2 rows per chunk
    assert all(len(body["payload"]["rows"]) <= 3 for body in received)
    assert [row for body in received for row in body["payload"]["rows"]] == payload.rows
    envelopes = [body["payload"]["chunk"] for body in received]
    assert [c["index"] for c in envelopes] == [1, 2, 3, 4]
    assert {c["total"] for c in envelopes} == {4}, \
        "the delivered sequence must be internally consistent, or it can never reassemble"
    assert client.outbox_count() == 0             # cleared only now, with every piece acked


def test_a_refusal_that_names_the_time_budget_is_re_planned_not_given_up_on(
        tmp_path: Path, monkeypatch, received):
    """Apps Script sometimes answers in words rather than a status code."""
    def wordy_post(url, json=None, **kwargs):
        if len(json["payload"]["rows"]) > 1:
            return httpx.Response(200, request=httpx.Request("POST", url),
                                  json={"ok": False, "error": "Exceeded maximum execution time"})
        received.append(json)
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", wordy_post)
    client = FunnelClient("https://funnel.example/exec", "tok", outbox_dir=tmp_path)
    assert client.send(make_payload(rows=4)) == 4
    assert client.outbox_count() == 0


def test_a_single_row_that_still_cannot_be_sent_is_a_loud_failure(
        tmp_path: Path, monkeypatch):
    """The floor. Shrinking is a way to deliver, never a way to stop trying
    quietly: when one row alone times out, the send fails and the batch stays."""
    calls = {"n": 0}

    def always_timeout(url, json=None, **kwargs):
        calls["n"] += 1
        raise httpx.ReadTimeout("gone", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", always_timeout)
    client = FunnelClient("https://funnel.example/exec", "tok", outbox_dir=tmp_path)
    with pytest.raises(FunnelDeliveryError):
        client.send(make_payload(rows=4))
    assert client.outbox_count() == 1
    # Bounded, and the bound is the halving ladder: plans of 4, 2 and 1 rows per
    # chunk, each failing on its first chunk after 1 + 3 retries.
    assert calls["n"] == 12


def test_an_unreachable_funnel_is_not_mistaken_for_an_oversized_batch(
        tmp_path: Path, monkeypatch):
    """A connect timeout means the request was never taken, so its size cannot
    be the reason. Halving here would grind the whole ladder against a funnel
    that is simply down and turn a two-minute failure into half an hour."""
    calls = {"n": 0}

    def never_connects(url, json=None, **kwargs):
        calls["n"] += 1
        raise httpx.ConnectTimeout("no route", request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", never_connects)
    client = FunnelClient("https://funnel.example/exec", "tok", outbox_dir=tmp_path)
    with pytest.raises(FunnelDeliveryError):
        client.send(make_payload(rows=4))
    assert calls["n"] == 4          # 1 + 3 retries, and no second plan
    assert client.outbox_count() == 1


def test_the_spool_survives_a_partial_delivery_and_clears_only_on_a_whole_one(
        tmp_path: Path, monkeypatch):
    """Spool-first (A6) has to hold for the adaptive path too. A failure that is
    NOT about size (the network went away mid-batch) is not halved — it is
    raised — and the whole batch, including the chunks that did land, is still
    in the outbox for drain() to send again."""
    bodies: list[dict] = []

    def dies_after_one(url, json=None, **kwargs):
        if bodies:
            raise httpx.ConnectError("network went away", request=httpx.Request("POST", url))
        bodies.append(json)
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", dies_after_one)
    wide = make_payload().model_copy(
        update={"rows": [["cell-" + "x" * 300, "cell-" + "y" * 300] for _ in range(120)]})
    client = FunnelClient("https://funnel.example/exec", "tok", outbox_dir=tmp_path)
    with pytest.raises(FunnelDeliveryError):
        client.send(wide)
    assert len(bodies) == 1                  # one chunk did land
    assert client.outbox_count() == 1        # and the batch is kept whole anyway

    delivered: list[dict] = []

    def ok_post(url, json=None, **kwargs):
        delivered.append(json)
        return httpx.Response(200, json={"ok": True}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", ok_post)
    assert client.drain() == (1, 0)
    assert client.outbox_count() == 0
    # drain() re-sends the WHOLE batch, first chunk included: the funnel's inbox
    # is append-only and the pasted script keeps the last copy of each index,
    # which is why re-sending is safe and remembering half a batch is not.
    assert sum(len(body["payload"]["rows"]) for body in delivered) == len(wide.rows)


def test_multichunk_payload_sends_every_chunk(tmp_path: Path, ok_transport, received):
    wide_rows = [["cell-" + "x" * 300, "cell-" + "y" * 300] for _ in range(120)]
    payload = make_payload().model_copy(update={"rows": wide_rows})
    client = FunnelClient("https://funnel.example/exec", "tok", outbox_dir=tmp_path)
    sent = client.send(payload)
    assert sent == len(received) > 1
    indexes = [body["payload"]["chunk"]["index"] for body in received]
    assert indexes == list(range(1, sent + 1))
    # Reassembled row count must equal the original (no row lost in chunking):
    total_rows = sum(len(body["payload"]["rows"]) for body in received)
    assert total_rows == len(wide_rows)
