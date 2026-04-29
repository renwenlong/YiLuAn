"""
Admin Companions search endpoint tests (Action #6 — wallet filter dropdown).
"""
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.companion_profile import CompanionProfile, VerificationStatus
from app.models.user import User, UserRole
from tests.conftest import test_session_factory

ADMIN_HEADERS = {"X-Admin-Token": "dev-admin-token"}
SEARCH = "/api/v1/admin/companions/search"


async def _seed(
    real_name: str,
    phone: str,
    status: VerificationStatus = VerificationStatus.verified,
) -> uuid.UUID:
    async with test_session_factory() as session:
        uid = uuid.uuid4()
        session.add(User(id=uid, phone=phone, role=UserRole.companion))
        session.add(CompanionProfile(user_id=uid, real_name=real_name, verification_status=status))
        await session.commit()
        return uid


@pytest.mark.asyncio
async def test_search_returns_phone_last4_and_user_id(client: AsyncClient):
    uid = await _seed("张三", "13800001234")
    r = await client.get(SEARCH, headers=ADMIN_HEADERS, params={"q": "张"})
    assert r.status_code == 200, r.text
    data = r.json()
    items = data["items"]
    assert any(it["user_id"] == str(uid) for it in items)
    found = next(it for it in items if it["user_id"] == str(uid))
    assert found["name"] == "张三"
    assert found["phone_last4"] == "1234"


@pytest.mark.asyncio
async def test_search_default_excludes_pending(client: AsyncClient):
    pending_uid = await _seed("李四", "13800005678", status=VerificationStatus.pending)
    verified_uid = await _seed("王五", "13900001111", status=VerificationStatus.verified)
    r = await client.get(SEARCH, headers=ADMIN_HEADERS)
    assert r.status_code == 200
    ids = {it["user_id"] for it in r.json()["items"]}
    assert str(verified_uid) in ids
    assert str(pending_uid) not in ids


@pytest.mark.asyncio
async def test_search_status_all_includes_pending(client: AsyncClient):
    pending_uid = await _seed("赵六", "13700009999", status=VerificationStatus.pending)
    r = await client.get(SEARCH, headers=ADMIN_HEADERS, params={"status": "all", "q": "赵"})
    assert r.status_code == 200
    ids = {it["user_id"] for it in r.json()["items"]}
    assert str(pending_uid) in ids


@pytest.mark.asyncio
async def test_search_by_phone_substring(client: AsyncClient):
    uid = await _seed("孙七", "13612345678")
    r = await client.get(SEARCH, headers=ADMIN_HEADERS, params={"q": "5678"})
    assert r.status_code == 200
    ids = {it["user_id"] for it in r.json()["items"]}
    assert str(uid) in ids


@pytest.mark.asyncio
async def test_search_requires_admin_token(client: AsyncClient):
    r = await client.get(SEARCH)
    assert r.status_code in (401, 422)


@pytest.mark.asyncio
async def test_wallet_ledger_accepts_companion_id_query(client: AsyncClient):
    """Ensure backend tolerates the new `companion_id` query param."""
    uid = await _seed("钱八", "13511112222")
    r = await client.get(
        f"/api/v1/admin/wallet-ledger/{uid}",
        headers=ADMIN_HEADERS,
        params={"companion_id": str(uid)},
    )
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 0


@pytest.mark.asyncio
async def test_wallet_ledger_rejects_mismatched_companion_id(client: AsyncClient):
    uid = await _seed("周九", "13522223333")
    other = uuid.uuid4()
    r = await client.get(
        f"/api/v1/admin/wallet-ledger/{uid}",
        headers=ADMIN_HEADERS,
        params={"companion_id": str(other)},
    )
    assert r.status_code == 422
