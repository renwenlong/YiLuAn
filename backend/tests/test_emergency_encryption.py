"""ADR-0029 — 验证 emergency 写入 DB 时 phone 字段是密文 bytes，不是明文。"""
from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio


async def test_emergency_contact_phone_stored_as_ciphertext(authenticated_client):
    plaintext = "13900139999"
    r = await authenticated_client.post(
        "/api/v1/emergency/contacts",
        json={"name": "母亲", "phone": plaintext, "relationship": "母亲"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    # API 层依然返回明文（service 层包装解密）
    assert body["phone"] == plaintext

    # 直接查 DB → 必须是密文 bytes，不是明文
    from tests.conftest import test_session_factory

    async with test_session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT phone_encrypted, phone_hash FROM emergency_contacts"
                )
            )
        ).all()
    assert len(rows) == 1
    ct, h = rows[0]
    assert ct  # 非空
    # 密文里不应出现明文（base64 也不该包含连续明文）
    if isinstance(ct, (bytes, bytearray, memoryview)):
        ct_bytes = bytes(ct)
    else:
        ct_bytes = str(ct).encode()
    assert plaintext.encode() not in ct_bytes

    # phone_hash: HMAC-SHA256 64 hex
    assert isinstance(h, str)
    assert len(h) == 64

    # 一致性：同一明文 → 同一 hash
    from app.core.pii import phone_hash

    assert phone_hash(plaintext) == h


async def test_emergency_event_contact_called_encrypted(
    authenticated_client, seed_user
):
    # 先建一个紧急联系人
    r = await authenticated_client.post(
        "/api/v1/emergency/contacts",
        json={"name": "父亲", "phone": "13700137000", "relationship": "父亲"},
    )
    assert r.status_code == 201
    contact_id = r.json()["id"]

    # 触发紧急事件
    r2 = await authenticated_client.post(
        "/api/v1/emergency/events",
        json={"contact_id": contact_id, "hotline": False},
    )
    assert r2.status_code == 201, r2.text
    body = r2.json()
    assert body["phone_to_call"] == "13700137000"

    from tests.conftest import test_session_factory

    async with test_session_factory() as session:
        rows = (
            await session.execute(
                text(
                    "SELECT contact_called_encrypted, contact_called_hash "
                    "FROM emergency_events"
                )
            )
        ).all()
    assert len(rows) == 1
    ct, h = rows[0]
    if isinstance(ct, (bytes, bytearray, memoryview)):
        ct_bytes = bytes(ct)
    else:
        ct_bytes = str(ct).encode()
    assert b"13700137000" not in ct_bytes
    assert len(h) == 64
