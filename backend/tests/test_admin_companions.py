"""
Placeholder tests for admin companions audit scaffold (A6).
"""

import pytest


@pytest.mark.asyncio
async def test_list_pending_companions_returns_200(admin_client):
    """GET /api/v1/admin/companions/ returns 200 with paginated structure."""
    resp = await admin_client.get("/api/v1/admin/companions/")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
