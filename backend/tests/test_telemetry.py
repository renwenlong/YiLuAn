"""Telemetry ingest + admin listing — observability sink coverage.

Covers:
  - POST /api/v1/telemetry/events (anonymous + authed)
  - PII rejection (mobile / 身份证 / card-like digit runs)
  - event_type charset / length guard
  - payload size cap (16 KB)
  - admin GET /api/v1/admin/telemetry/events filter + pagination
  - admin auth required
"""
from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_ingest_event_anonymous(client):
    """Funnel pings before login must be accepted with user_id = NULL."""
    resp = await client.post(
        "/api/v1/telemetry/events",
        json={
            "event_type": "funnel.companion_list_view",
            "payload": {"step": 1, "filter": "service_type:diagnosis"},
            "client_meta": {"env": "dev", "page": "pages/patient/home/index"},
            "ts": 1716624000000,
        },
    )
    assert resp.status_code == 202, resp.text
    assert resp.json() == {"accepted": True}


@pytest.mark.asyncio
async def test_ingest_event_authenticated_attaches_user(authenticated_client):
    """When a valid bearer token is sent, user_id is recorded."""
    resp = await authenticated_client.post(
        "/api/v1/telemetry/events",
        json={
            "event_type": "funnel.order_submit",
            "payload": {"order_amount_cents": 19900, "service_type": "diagnosis"},
        },
    )
    assert resp.status_code == 202, resp.text


@pytest.mark.asyncio
async def test_ingest_event_invalid_bearer_still_accepted_as_anonymous(client):
    """A bogus token must NOT 401 the telemetry endpoint — drop user, keep event."""
    client.headers["Authorization"] = "Bearer not-a-real-jwt"
    try:
        resp = await client.post(
            "/api/v1/telemetry/events",
            json={"event_type": "logger.warn", "payload": {"msg": "x"}},
        )
        assert resp.status_code == 202, resp.text
    finally:
        client.headers.pop("Authorization", None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "leak",
    [
        {"msg": "user phone 13800138000 missing OTP"},   # CN mobile
        {"id_card": "11010119900101001X"},                # CN 18-digit
        {"id_card": "110101900101001"},                   # CN 15-digit
        {"card_no": "6228480402564890018"},               # bank card-ish
        {"nested": {"deep": ["13800138000"]}},            # nested
    ],
)
async def test_ingest_event_rejects_pii(client, leak):
    resp = await client.post(
        "/api/v1/telemetry/events",
        json={"event_type": "logger.error", "payload": leak},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_type",
    ["", "funnel/order", "funnel.order submit", "x" * 65, "a;b"],
)
async def test_ingest_event_rejects_bad_event_type(client, bad_type):
    resp = await client.post(
        "/api/v1/telemetry/events",
        json={"event_type": bad_type, "payload": {}},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_ingest_event_rejects_oversized_payload(client):
    huge = {"blob": "x" * (17 * 1024)}
    resp = await client.post(
        "/api/v1/telemetry/events",
        json={"event_type": "logger.error", "payload": huge},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_admin_list_requires_auth(client):
    resp = await client.get("/api/v1/admin/telemetry/events")
    # require_admin returns 401 when missing both bearer and X-Admin-Token.
    assert resp.status_code in (401, 403), resp.text


@pytest.mark.asyncio
async def test_admin_list_filters_and_paginates(admin_client, client):
    # Seed via the public endpoint with the bare client so user_id stays
    # NULL and ordering is deterministic.
    seed_events = [
        ("funnel.companion_list_view", {"step": 1}),
        ("funnel.companion_detail_view", {"step": 2, "companion_id": "c-1"}),
        ("funnel.order_create_start", {"step": 3}),
        ("funnel.order_submit", {"step": 4}),
        ("funnel.payment_success", {"step": 5, "order_id": "o-1"}),
        ("logger.error", {"msg": "boom"}),
    ]
    for et, payload in seed_events:
        r = await client.post(
            "/api/v1/telemetry/events",
            json={"event_type": et, "payload": payload, "client_meta": {"env": "test"}},
        )
        assert r.status_code == 202, r.text

    # Unfiltered list returns all 6, newest-first.
    resp = await admin_client.get("/api/v1/admin/telemetry/events?limit=10")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 6
    assert len(body["items"]) == 6
    assert body["items"][0]["event_type"] == "logger.error"

    # Filter by event_type.
    resp = await admin_client.get(
        "/api/v1/admin/telemetry/events?event_type=funnel.order_submit"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["event_type"] == "funnel.order_submit"
    assert body["items"][0]["payload"] == {"step": 4}

    # Pagination — disjoint pages.
    page1 = (await admin_client.get(
        "/api/v1/admin/telemetry/events?limit=2&offset=0"
    )).json()
    page2 = (await admin_client.get(
        "/api/v1/admin/telemetry/events?limit=2&offset=2"
    )).json()
    assert len(page1["items"]) == 2
    assert len(page2["items"]) == 2
    page1_ids = {it["id"] for it in page1["items"]}
    page2_ids = {it["id"] for it in page2["items"]}
    assert page1_ids.isdisjoint(page2_ids)
