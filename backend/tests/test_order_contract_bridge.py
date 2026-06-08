"""S3-CONTRACT-API-BRIDGE: OrderResponse 暴露 contract_id + insurance_id.

# 背景

S3 P0 CONTRACT-API (PR #206 merged) 落了 3 endpoint:
- POST /api/v1/contracts/{contract_id}/accept
- GET /api/v1/contracts/{contract_id}
- POST /api/v1/admin/contracts/{contract_id}/invalidate

但前端 (微信 / iOS) 拿不到 contract_id — OrderResponse schema 漏 contract_id +
insurance_id 字段 (虽然 Order ORM 已加列, S3-DEV-001-CONTRACT-DOMAIN PR #200
+ INSURANCE-DOMAIN PR #199)。

本 PR 补 schema 暴露, 是 CONTRACT-UI 起手的前置 bridge。

# AC

1. GET /api/v1/orders/{id} 返回 body 含 contract_id 字段 (null 或 UUID)
2. GET /api/v1/orders/{id} 返回 body 含 insurance_id 字段 (null 或 UUID)
3. 历史订单 (Order.contract_id IS NULL) → contract_id = null (非缺字段)
4. ORM 写了 contract_id 的 Order → 透传到 OrderResponse
5. OpenAPI schema 自动含两个新字段 (FastAPI 自动生成)
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.order import Order
from app.models.service_contract import ContractStatus, ServiceContract
from tests.conftest import test_session_factory


@pytest.mark.asyncio
class TestOrderResponseContractIdField:
    """AC#1+#3+#4: OrderResponse 含 contract_id (null 或 UUID)."""

    async def test_legacy_order_returns_null_contract_id(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """历史 Order (无 contract_id) → API 返回 contract_id=null, 非缺字段."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        resp = await authenticated_client.get(f"/api/v1/orders/{order.id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # 字段存在 (key 在 response) 但值为 null
        assert "contract_id" in body, "OrderResponse 必须含 contract_id 字段 (AC#1)"
        assert body["contract_id"] is None, "无 contract 时应为 null (AC#3)"

    async def test_order_with_contract_returns_uuid(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        """ORM 写了 contract_id → API 透传 UUID 字符串."""
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        # Seed a contract + 回写 order.contract_id
        async with test_session_factory() as session:
            contract = ServiceContract(
                order_id=order.id,
                template_version="v1.0.0",
                contract_hash=("a" * 64),
                hash_inputs={"order_id": str(order.id)},
                status=ContractStatus.active,
            )
            session.add(contract)
            await session.commit()
            await session.refresh(contract)

            # 回写 Order.contract_id (生产路径由 ContractService 做, 这里直接 mutate ORM)
            stored_order = await session.scalar(
                select(Order).where(Order.id == order.id)
            )
            stored_order.contract_id = contract.id
            await session.commit()

        resp = await authenticated_client.get(f"/api/v1/orders/{order.id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["contract_id"] == str(contract.id), (
            "OrderResponse.contract_id 应等于 ORM Order.contract_id (AC#4)"
        )


@pytest.mark.asyncio
class TestOrderResponseInsuranceIdField:
    """AC#2: OrderResponse 含 insurance_id (null 或 UUID)."""

    async def test_legacy_order_returns_null_insurance_id(
        self, authenticated_client: AsyncClient, seed_hospital, seed_order
    ):
        user = authenticated_client._test_user
        hospital = await seed_hospital()
        order = await seed_order(user.id, hospital.id)

        resp = await authenticated_client.get(f"/api/v1/orders/{order.id}")
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert "insurance_id" in body, "OrderResponse 必须含 insurance_id 字段 (AC#2)"
        assert body["insurance_id"] is None


@pytest.mark.asyncio
class TestOpenAPISchemaIncludesNewFields:
    """AC#5: FastAPI 自动生成 OpenAPI schema 含 contract_id + insurance_id."""

    async def test_openapi_orderresponse_has_contract_id(self, client: AsyncClient):
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        spec = resp.json()
        order_schema = spec["components"]["schemas"]["OrderResponse"]
        props = order_schema["properties"]
        assert "contract_id" in props, "OpenAPI OrderResponse 漏 contract_id (AC#5)"
        assert "insurance_id" in props, "OpenAPI OrderResponse 漏 insurance_id (AC#5)"
        # 字段类型应允许 null (nullable / anyOf with null)
        contract_field = props["contract_id"]
        # Pydantic v2 → openapi 3.x 用 anyOf [{type: string, format: uuid}, {type: null}]
        # 简单断言: nullable
        is_nullable = (
            contract_field.get("nullable") is True
            or any(
                opt.get("type") == "null" for opt in contract_field.get("anyOf", [])
            )
        )
        assert is_nullable, "contract_id 必须 nullable (历史订单为 null)"
