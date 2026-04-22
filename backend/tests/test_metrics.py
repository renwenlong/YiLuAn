"""Tests for SP-03 metrics endpoint and business counters."""

import pytest


@pytest.mark.asyncio
class TestMetricsEndpoint:
    async def test_metrics_returns_200(self, authenticated_client):
        resp = await authenticated_client.get("/metrics/")
        assert resp.status_code == 200
        assert "outbound_call_total" in resp.text

    async def test_order_created_counter_increments(
        self, authenticated_client, seed_hospital
    ):
        hospital = await seed_hospital()

        resp = await authenticated_client.post(
            "/api/v1/orders",
            json={
                "service_type": "full_accompany",
                "hospital_id": str(hospital.id),
                "appointment_date": "2026-05-01",
                "appointment_time": "09:00",
                "description": "metrics test",
            },
        )
        assert resp.status_code == 201

        # Verify counter appears in /metrics output
        metrics_resp = await authenticated_client.get("/metrics/")
        assert metrics_resp.status_code == 200
        assert 'order_created_total{service_type="full_accompany"}' in metrics_resp.text
