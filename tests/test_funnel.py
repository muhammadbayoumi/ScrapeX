"""A6/S1: funnel client — spool-first durability, chunk delivery, loud refusals.

The endpoint is mocked at the httpx layer (no network, T1-compatible); the REAL
Apps Script consumer is covered by the shared contract fixtures (T8).
"""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from scrapex.funnel import FunnelClient, FunnelDeliveryError, OutboxAlarm, OUTBOX_ALARM_THRESHOLD
from scrapex.payload import PAYLOAD_VERSION, FunnelPayload


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
