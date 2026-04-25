"""[F-02] Notification deep-link navigation tests.

Covers:
- 模型新增 target_type / target_id 字段
- create_notification 默认行为不破坏旧调用
- notify_* 系列回填 target_type / target_id
- GET /notifications 列表项含两字段
- POST /notifications/{id}/read 返回 target 信息
- admin 审核通过/驳回 给陪诊师推 companion 类深链通知
- review 提交给陪诊师推 review 类深链通知
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.models.notification import (
    Notification,
    NotificationTargetType,
    NotificationType,
)
from app.models.order import OrderStatus
from app.models.user import UserRole
from app.services.notification import NotificationService
from tests.conftest import test_session_factory

pytestmark = pytest.mark.asyncio


async def _svc():
    """辅助：在独立 session 上运行 NotificationService 调用。"""
    return test_session_factory()


# ---------------------------------------------------------------------------
# Service-level
# ---------------------------------------------------------------------------
class TestNotificationServiceTargets:
    async def test_create_notification_defaults_target_to_null(self, seed_user):
        user = await seed_user(phone="13900139000", role=UserRole.patient)
        async with test_session_factory() as session:
            svc = NotificationService(session)
            n = await svc.create_notification(
                user_id=user.id,
                type=NotificationType.system,
                title="hi",
                body="body",
            )
            assert n.target_type is None
            assert n.target_id is None

    async def test_create_notification_with_explicit_target(self, seed_user):
        user = await seed_user(phone="13900139001", role=UserRole.patient)
        order_id = uuid.uuid4()
        async with test_session_factory() as session:
            svc = NotificationService(session)
            n = await svc.create_notification(
                user_id=user.id,
                type=NotificationType.order_status_changed,
                title="hi",
                body="body",
                reference_id=str(order_id),
                target_type=NotificationTargetType.order,
                target_id=str(order_id),
            )
            assert n.target_type == NotificationTargetType.order
            assert n.target_id == str(order_id)

    async def test_notify_order_status_changed_backfills_order_target(
        self, seed_user, seed_hospital, seed_order
    ):
        patient = await seed_user(phone="13900139002", role=UserRole.patient)
        hospital = await seed_hospital()
        order = await seed_order(patient.id, hospital.id, status=OrderStatus.created)
        async with test_session_factory() as session:
            svc = NotificationService(session)
            n = await svc.notify_order_status_changed(order, "accepted", patient.id)
            assert n.target_type == NotificationTargetType.order
            assert n.target_id == str(order.id)

    async def test_notify_review_received_backfills_review_target(self, seed_user):
        companion = await seed_user(phone="13700137000", role=UserRole.companion)
        order_id = uuid.uuid4()
        review_id = uuid.uuid4()
        async with test_session_factory() as session:
            svc = NotificationService(session)
            n = await svc.notify_review_received(
                companion_id=companion.id,
                patient_name="李四",
                order_id=order_id,
                rating=5,
                review_id=review_id,
            )
            assert n.target_type == NotificationTargetType.review
            assert n.target_id == str(review_id)

    async def test_notify_review_received_falls_back_to_order_id(self, seed_user):
        companion = await seed_user(phone="13700137001", role=UserRole.companion)
        order_id = uuid.uuid4()
        async with test_session_factory() as session:
            svc = NotificationService(session)
            n = await svc.notify_review_received(
                companion_id=companion.id,
                patient_name="李四",
                order_id=order_id,
                rating=4,
            )
            assert n.target_type == NotificationTargetType.review
            assert n.target_id == str(order_id)

    async def test_notify_companion_audit_result_targets_companion(self, seed_user):
        companion = await seed_user(phone="13700137002", role=UserRole.companion)
        profile_id = uuid.uuid4()
        async with test_session_factory() as session:
            svc = NotificationService(session)
            n_ok = await svc.notify_companion_audit_result(
                companion_user_id=companion.id,
                companion_profile_id=profile_id,
                approved=True,
            )
            n_no = await svc.notify_companion_audit_result(
                companion_user_id=companion.id,
                companion_profile_id=profile_id,
                approved=False,
                reason="资料不全",
            )
        for n in (n_ok, n_no):
            assert n.target_type == NotificationTargetType.companion
            assert n.target_id == str(profile_id)
        assert "未通过" in n_no.title
        assert "已通过" in n_ok.title


# ---------------------------------------------------------------------------
# API-level
# ---------------------------------------------------------------------------
class TestNotificationAPITargets:
    async def test_list_includes_target_fields(
        self, authenticated_client, seed_notification
    ):
        user = authenticated_client._test_user
        order_id = uuid.uuid4()
        await seed_notification(
            user.id,
            type=NotificationType.order_status_changed,
            title="订单已接单",
            body="详情",
            reference_id=str(order_id),
            target_type=NotificationTargetType.order,
            target_id=str(order_id),
        )

        resp = await authenticated_client.get("/api/v1/notifications")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["target_type"] == "order"
        assert items[0]["target_id"] == str(order_id)

    async def test_list_legacy_rows_have_null_targets(
        self, authenticated_client, seed_notification
    ):
        user = authenticated_client._test_user
        await seed_notification(user.id, title="legacy", body="b")
        resp = await authenticated_client.get("/api/v1/notifications")
        item = resp.json()["items"][0]
        assert item["target_type"] is None
        assert item["target_id"] is None

    async def test_mark_read_returns_target(
        self, authenticated_client, seed_notification
    ):
        user = authenticated_client._test_user
        order_id = uuid.uuid4()
        n = await seed_notification(
            user.id,
            type=NotificationType.order_status_changed,
            title="订单已接单",
            body="详情",
            reference_id=str(order_id),
            target_type=NotificationTargetType.order,
            target_id=str(order_id),
        )
        resp = await authenticated_client.post(
            f"/api/v1/notifications/{n.id}/read"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["notification"]["target_type"] == "order"
        assert body["notification"]["target_id"] == str(order_id)
        assert body["notification"]["is_read"] is True

    async def test_mark_read_missing_returns_null_notification(
        self, authenticated_client
    ):
        resp = await authenticated_client.post(
            f"/api/v1/notifications/{uuid.uuid4()}/read"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["notification"] is None
