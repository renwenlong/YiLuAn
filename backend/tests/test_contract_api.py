"""S3-DEV-001-CONTRACT-API tests — 3 endpoints + 5 AC.

ADR-0047 §6.2 + §6.3 acceptance:
1) POST /api/v1/contracts/{id}/accept — user 勾选 + audit log
2) GET /api/v1/contracts/{id} — user 查看 + signed URL (15min TTL)
3) POST /api/v1/admin/contracts/{id}/invalidate — admin 作废 + admin_audit_logs
4) OpenAPI 同步 — verified via FastAPI app.openapi() inclusion
5) 单测覆盖: 鉴权 + audit 双向 (user vs admin 分表) + IDOR 防御
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import bcrypt
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.core.admin_jwt import create_admin_access_token
from app.models.admin_audit_log import AdminAuditLog
from app.models.admin_user import AdminRole, AdminUser
from app.models.hospital import Hospital
from app.models.order import OrderStatus
from app.models.service_contract import ContractStatus, ServiceContract
from app.models.user_audit_log import UserAuditAction, UserAuditLog
from tests.conftest import test_session_factory

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


async def _seed_admin_jwt(
    *,
    username: str = "neo_contract",
    role: AdminRole = AdminRole.super_,
) -> tuple[AdminUser, str]:
    pw_hash = bcrypt.hashpw(b"hunter2A!", bcrypt.gensalt(rounds=4))
    async with test_session_factory() as session:
        admin = AdminUser(
            username=username,
            password_hash=pw_hash.decode("utf-8"),
            role=role,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
    token = create_admin_access_token(admin)
    return admin, token


async def _seed_hospital() -> Hospital:
    async with test_session_factory() as session:
        h = Hospital(
            name=f"Hospital {uuid.uuid4().hex[:6]}",
            city="北京",
            address="测试地址",
        )
        session.add(h)
        await session.commit()
        await session.refresh(h)
        return h


async def _seed_contract(
    *,
    order_id: uuid.UUID,
    status: ContractStatus = ContractStatus.active,
    storage_blob_path: str | None = "contracts/2026/06/test_a.pdf",
    contract_hash: str | None = None,
) -> ServiceContract:
    async with test_session_factory() as session:
        contract = ServiceContract(
            order_id=order_id,
            template_version="v1.0.0",
            contract_hash=contract_hash or (uuid.uuid4().hex + uuid.uuid4().hex)[:64],
            hash_inputs={
                "order_id": str(order_id),
                "template_version": "v1.0.0",
                "amount_cny": 29900,
                "service_package_id": str(uuid.uuid4()),
                "scheduled_at": "2026-06-10T09:00:00+00:00",
                "patient_pseudonym_hash": "0" * 64,
                "companion_id": str(uuid.uuid4()),
            },
            storage_blob_path=storage_blob_path,
            status=status,
            generated_at=datetime.now(timezone.utc) if status == ContractStatus.active else None,
        )
        session.add(contract)
        await session.commit()
        await session.refresh(contract)
        return contract


# ---------------------------------------------------------------------------
# AC#1: POST /api/v1/contracts/{id}/accept
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAcceptContract:
    """User accepts a contract → write user_audit_logs.contract_acceptance_clicked."""

    async def test_accept_writes_audit_log(
        self, authenticated_client: AsyncClient, seed_order
    ):
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        hospital = await _seed_hospital()
        order = await seed_order(
            patient_id=user.id,
            hospital_id=hospital.id,
            status=OrderStatus.created,
        )
        contract = await _seed_contract(order_id=order.id)

        resp = await authenticated_client.post(
            f"/api/v1/contracts/{contract.id}/accept",
            json={},
            headers={
                "X-Forwarded-For": "203.0.113.7",
                "User-Agent": "iOS/17 (test)",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["contract_id"] == str(contract.id)
        assert body["order_id"] == str(order.id)
        assert "audit_log_id" in body
        assert "accepted_at" in body

        # Verify audit log written
        async with test_session_factory() as session:
            log = await session.scalar(
                select(UserAuditLog).where(UserAuditLog.id == uuid.UUID(body["audit_log_id"]))
            )
        assert log is not None
        assert log.action == UserAuditAction.contract_acceptance_clicked.value
        assert log.user_id == user.id
        assert log.order_id == order.id
        assert log.client_ip == "203.0.113.7"
        assert "iOS/17" in log.user_agent
        # template_version captured in metadata
        assert log.audit_metadata.get("template_version") == "v1.0.0"

    async def test_accept_unauthenticated_rejected(self, client: AsyncClient):
        contract_id = uuid.uuid4()
        resp = await client.post(
            f"/api/v1/contracts/{contract_id}/accept",
            json={},
        )
        assert resp.status_code in (401, 403)  # framework returns 403 when bearer missing

    async def test_accept_not_owner_returns_404(
        self, authenticated_client: AsyncClient, seed_order, seed_user
    ):
        # Other user owns the contract
        other = await seed_user(phone="13500135000")
        hospital = await _seed_hospital()
        order = await seed_order(
            patient_id=other.id,
            hospital_id=hospital.id,
            status=OrderStatus.created,
        )
        contract = await _seed_contract(order_id=order.id)

        resp = await authenticated_client.post(
            f"/api/v1/contracts/{contract.id}/accept",
            json={},
        )
        # Non-owner: 404 (not 403) — IDOR 防御
        assert resp.status_code == 404

    async def test_accept_nonexistent_contract_returns_404(
        self, authenticated_client: AsyncClient
    ):
        resp = await authenticated_client.post(
            f"/api/v1/contracts/{uuid.uuid4()}/accept",
            json={},
        )
        assert resp.status_code == 404

    async def test_accept_repeated_writes_multiple_audit_logs(
        self, authenticated_client: AsyncClient, seed_order
    ):
        """Repeated acceptance is OK (legal) and creates one audit log each time.

        ADR-0047 §3.5: 取证需保留所有勾选时点，不去重。
        """
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        hospital = await _seed_hospital()
        order = await seed_order(
            patient_id=user.id,
            hospital_id=hospital.id,
            status=OrderStatus.created,
        )
        contract = await _seed_contract(order_id=order.id)

        for _ in range(3):
            resp = await authenticated_client.post(
                f"/api/v1/contracts/{contract.id}/accept",
                json={},
            )
            assert resp.status_code == 200

        async with test_session_factory() as session:
            logs = (
                await session.scalars(
                    select(UserAuditLog).where(
                        UserAuditLog.user_id == user.id,
                        UserAuditLog.action
                        == UserAuditAction.contract_acceptance_clicked.value,
                    )
                )
            ).all()
        assert len(logs) == 3


# ---------------------------------------------------------------------------
# AC#2: GET /api/v1/contracts/{id}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetContract:
    """User views contract → returns signed URL (TTL=15min) + writes view audit."""

    async def test_get_active_returns_signed_url(
        self, authenticated_client: AsyncClient, seed_order
    ):
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        hospital = await _seed_hospital()
        order = await seed_order(
            patient_id=user.id,
            hospital_id=hospital.id,
            status=OrderStatus.created,
        )
        contract = await _seed_contract(order_id=order.id, status=ContractStatus.active)

        resp = await authenticated_client.get(
            f"/api/v1/contracts/{contract.id}",
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["contract_id"] == str(contract.id)
        assert body["order_id"] == str(order.id)
        assert body["status"] == ContractStatus.active.value
        assert body["signed_url"] is not None
        assert body["signed_url_expires_at"] is not None
        assert body["generated_at"] is not None

        # Verify view audit log written
        async with test_session_factory() as session:
            log = await session.scalar(
                select(UserAuditLog).where(
                    UserAuditLog.user_id == user.id,
                    UserAuditLog.action == UserAuditAction.contract_viewed.value,
                )
            )
        assert log is not None
        assert log.order_id == order.id

    async def test_get_pending_status_no_signed_url(
        self, authenticated_client: AsyncClient, seed_order
    ):
        """status != active → signed_url = null, but audit still written."""
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        hospital = await _seed_hospital()
        order = await seed_order(
            patient_id=user.id,
            hospital_id=hospital.id,
            status=OrderStatus.created,
        )
        contract = await _seed_contract(
            order_id=order.id,
            status=ContractStatus.pending_generation,
            storage_blob_path=None,
        )

        resp = await authenticated_client.get(
            f"/api/v1/contracts/{contract.id}",
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == ContractStatus.pending_generation.value
        assert body["signed_url"] is None
        assert body["signed_url_expires_at"] is None
        assert body["generated_at"] is None

        # Audit log still written
        async with test_session_factory() as session:
            log = await session.scalar(
                select(UserAuditLog).where(
                    UserAuditLog.user_id == user.id,
                    UserAuditLog.action == UserAuditAction.contract_viewed.value,
                )
            )
        assert log is not None

    async def test_get_unauthenticated_rejected(self, client: AsyncClient):
        resp = await client.get(f"/api/v1/contracts/{uuid.uuid4()}")
        assert resp.status_code in (401, 403)  # framework returns 403 when bearer missing

    async def test_get_not_owner_returns_404(
        self, authenticated_client: AsyncClient, seed_order, seed_user
    ):
        other = await seed_user(phone="13500135001")
        hospital = await _seed_hospital()
        order = await seed_order(
            patient_id=other.id,
            hospital_id=hospital.id,
            status=OrderStatus.created,
        )
        contract = await _seed_contract(order_id=order.id)

        resp = await authenticated_client.get(f"/api/v1/contracts/{contract.id}")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AC#3: POST /api/v1/admin/contracts/{id}/invalidate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAdminInvalidateContract:
    """Admin invalidates → updates status + writes admin_audit_logs (NOT user_audit_logs)."""

    async def test_invalidate_active_contract(
        self, client: AsyncClient, seed_order, seed_user
    ):
        admin, admin_token = await _seed_admin_jwt(username="neo_inv_1")
        patient = await seed_user(phone="13400134000")
        hospital = await _seed_hospital()
        order = await seed_order(
            patient_id=patient.id,
            hospital_id=hospital.id,
            status=OrderStatus.created,
        )
        contract = await _seed_contract(order_id=order.id, status=ContractStatus.active)

        resp = await client.post(
            f"/api/v1/admin/contracts/{contract.id}/invalidate",
            json={"reason": "客服 #12 申诉作废"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["contract_id"] == str(contract.id)
        assert body["status"] == ContractStatus.manually_invalidated.value
        assert body["invalidated_by_admin_id"] == admin.id
        assert body["invalidation_reason"] == "客服 #12 申诉作废"

        # Verify contract row updated
        async with test_session_factory() as session:
            updated = await session.scalar(
                select(ServiceContract).where(ServiceContract.id == contract.id)
            )
        assert updated.status == ContractStatus.manually_invalidated
        assert updated.invalidation_reason == "客服 #12 申诉作废"
        assert updated.invalidated_by_admin_id == admin.id
        assert updated.invalidated_at is not None

        # Verify admin_audit_logs written (NOT user_audit_logs)
        async with test_session_factory() as session:
            audit = await session.scalar(
                select(AdminAuditLog).where(
                    AdminAuditLog.target_id == contract.id,
                    AdminAuditLog.action == "invalidate",
                )
            )
        assert audit is not None
        assert audit.target_type == "service_contract"
        assert audit.operator == str(admin.id)
        assert audit.reason == "客服 #12 申诉作废"

        # Verify NO user_audit_logs written for invalidate
        async with test_session_factory() as session:
            user_logs = (
                await session.scalars(
                    select(UserAuditLog).where(UserAuditLog.order_id == order.id)
                )
            ).all()
        assert user_logs == [], "invalidate must not write user_audit_logs (AC#5)"

    async def test_invalidate_empty_reason_rejected(
        self, client: AsyncClient, seed_order, seed_user
    ):
        _, admin_token = await _seed_admin_jwt(username="neo_inv_2")
        patient = await seed_user(phone="13400134001")
        hospital = await _seed_hospital()
        order = await seed_order(
            patient_id=patient.id,
            hospital_id=hospital.id,
            status=OrderStatus.created,
        )
        contract = await _seed_contract(order_id=order.id)

        resp = await client.post(
            f"/api/v1/admin/contracts/{contract.id}/invalidate",
            json={"reason": ""},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Pydantic min_length=1 → 422
        assert resp.status_code == 422

    async def test_invalidate_whitespace_reason_rejected_by_service(
        self, client: AsyncClient, seed_order, seed_user
    ):
        """Pydantic passes whitespace-only (length > 0); service-layer
        assert_invalidation_metadata catches it.
        """
        _, admin_token = await _seed_admin_jwt(username="neo_inv_3")
        patient = await seed_user(phone="13400134002")
        hospital = await _seed_hospital()
        order = await seed_order(
            patient_id=patient.id,
            hospital_id=hospital.id,
            status=OrderStatus.created,
        )
        contract = await _seed_contract(order_id=order.id)

        resp = await client.post(
            f"/api/v1/admin/contracts/{contract.id}/invalidate",
            json={"reason": "   "},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        # Service-level catches whitespace-only as missing reason
        assert resp.status_code == 422

    async def test_invalidate_unauthenticated_rejected(self, client: AsyncClient):
        resp = await client.post(
            f"/api/v1/admin/contracts/{uuid.uuid4()}/invalidate",
            json={"reason": "test"},
        )
        # 401 because no Authorization header
        assert resp.status_code in (401, 403)  # framework returns 403 when bearer missing

    async def test_invalidate_legacy_admin_token_rejected(
        self, client: AsyncClient, seed_order, seed_user
    ):
        """Legacy X-Admin-Token does NOT satisfy invalidate (need admin_user.id).

        Designed by ADR-0047 §3.1 invalidated_by_admin_id BigInt FK + AC#3
        assert_invalidation_metadata NOT NULL guard. Legacy sentinel has no .id.
        """
        patient = await seed_user(phone="13400134003")
        hospital = await _seed_hospital()
        order = await seed_order(
            patient_id=patient.id,
            hospital_id=hospital.id,
            status=OrderStatus.created,
        )
        contract = await _seed_contract(order_id=order.id)

        resp = await client.post(
            f"/api/v1/admin/contracts/{contract.id}/invalidate",
            json={"reason": "should be rejected"},
            headers={"X-Admin-Token": "dev-admin-token"},
        )
        # 403 — legacy sentinel rejected for this operation
        assert resp.status_code == 403
        assert "JWT" in resp.json()["detail"]

    async def test_invalidate_already_invalidated_returns_409(
        self, client: AsyncClient, seed_order, seed_user
    ):
        """Repeat invalidate hits terminal state machine guard → 409."""
        admin, admin_token = await _seed_admin_jwt(username="neo_inv_4")
        patient = await seed_user(phone="13400134004")
        hospital = await _seed_hospital()
        order = await seed_order(
            patient_id=patient.id,
            hospital_id=hospital.id,
            status=OrderStatus.created,
        )
        # Seed already-invalidated contract
        contract = await _seed_contract(
            order_id=order.id,
            status=ContractStatus.manually_invalidated,
        )

        resp = await client.post(
            f"/api/v1/admin/contracts/{contract.id}/invalidate",
            json={"reason": "second attempt"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 409

    async def test_invalidate_nonexistent_contract_returns_404(
        self, client: AsyncClient
    ):
        _, admin_token = await _seed_admin_jwt(username="neo_inv_5")
        resp = await client.post(
            f"/api/v1/admin/contracts/{uuid.uuid4()}/invalidate",
            json={"reason": "test"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# AC#4: OpenAPI 同步 — endpoints visible in /openapi.json
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestOpenAPIInclusion:
    """3 endpoints 必须出现在 OpenAPI schema (FastAPI auto-generates)."""

    async def test_openapi_includes_three_endpoints(self, client: AsyncClient):
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        spec = resp.json()
        paths = spec["paths"]
        assert "/api/v1/contracts/{contract_id}/accept" in paths
        assert "post" in paths["/api/v1/contracts/{contract_id}/accept"]
        assert "/api/v1/contracts/{contract_id}" in paths
        assert "get" in paths["/api/v1/contracts/{contract_id}"]
        assert "/api/v1/admin/contracts/{contract_id}/invalidate" in paths
        assert "post" in paths["/api/v1/admin/contracts/{contract_id}/invalidate"]


# ---------------------------------------------------------------------------
# AC#5: audit 双向 — user vs admin 分表的硬隔离
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAuditTableSeparation:
    """user 操作进 user_audit_logs, admin 操作进 admin_audit_logs, 互不混入."""

    async def test_user_accept_only_writes_user_audit(
        self, authenticated_client: AsyncClient, seed_order
    ):
        user = authenticated_client._test_user  # type: ignore[attr-defined]
        hospital = await _seed_hospital()
        order = await seed_order(
            patient_id=user.id,
            hospital_id=hospital.id,
            status=OrderStatus.created,
        )
        contract = await _seed_contract(order_id=order.id)

        resp = await authenticated_client.post(
            f"/api/v1/contracts/{contract.id}/accept",
            json={},
        )
        assert resp.status_code == 200

        async with test_session_factory() as session:
            user_count = len(
                (
                    await session.scalars(
                        select(UserAuditLog).where(UserAuditLog.user_id == user.id)
                    )
                ).all()
            )
            admin_count = len(
                (
                    await session.scalars(
                        select(AdminAuditLog).where(
                            AdminAuditLog.target_id == contract.id
                        )
                    )
                ).all()
            )
        assert user_count == 1, "user accept → 1 user_audit_logs row"
        assert admin_count == 0, "user accept → 0 admin_audit_logs rows"

    async def test_admin_invalidate_only_writes_admin_audit(
        self, client: AsyncClient, seed_order, seed_user
    ):
        admin, admin_token = await _seed_admin_jwt(username="neo_split_1")
        patient = await seed_user(phone="13400134010")
        hospital = await _seed_hospital()
        order = await seed_order(
            patient_id=patient.id,
            hospital_id=hospital.id,
            status=OrderStatus.created,
        )
        contract = await _seed_contract(order_id=order.id)

        resp = await client.post(
            f"/api/v1/admin/contracts/{contract.id}/invalidate",
            json={"reason": "split-table test"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200

        async with test_session_factory() as session:
            user_count = len(
                (
                    await session.scalars(
                        select(UserAuditLog).where(UserAuditLog.order_id == order.id)
                    )
                ).all()
            )
            admin_count = len(
                (
                    await session.scalars(
                        select(AdminAuditLog).where(
                            AdminAuditLog.target_id == contract.id
                        )
                    )
                ).all()
            )
        assert user_count == 0, "admin invalidate → 0 user_audit_logs rows"
        assert admin_count == 1, "admin invalidate → 1 admin_audit_logs row"
