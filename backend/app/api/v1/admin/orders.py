"""
Admin Orders — order management (B4).

Routes: /api/v1/admin/orders
Auth: X-Admin-Token header (token-based; v2 will migrate to JWT).

Endpoints
---------
GET    /                        list orders, filters: status / patient_id /
                                companion_id / date_from / date_to
GET    /{order_id}              order detail
POST   /{order_id}/force-status body {status, reason} — manual override
POST   /{order_id}/refund       body {amount, reason} — admin refund

Contract notes (W18 fix-admin-h5-contract)
------------------------------------------
- List/get response now includes ``patient_display_name``,
  ``patient_phone_masked`` and ``companion_display_name`` (resolved via a
  single ``SELECT user`` per page) so the admin H5 can render real names
  without secondary fetches.
- ``patient_phone_masked`` is **always** masked. Reveal-on-demand for
  full phones is implemented in :mod:`app.api.v1.admin.users`.
- Read-side audit: list/detail emit ``view_orders_list`` /
  ``view_order_detail`` rows so "who looked at which order" is traceable.
- ``force-status`` now consults a deny-list and refuses transitions that
  would leak money or revive cancelled flow (``refunded`` is terminal,
  ``completed`` cannot regress to ``created/accepted/in_progress``,
  ``cancelled_*`` cannot become ``in_progress/completed``, and
  ``reviewed`` is reachable only via the dedicated review path).
"""

from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.admin_auth import (
    require_admin_token,  # noqa: F401  (legacy import retained for downstream consumers)
)
from app.core import error_codes
from app.core.admin_jwt import admin_operator_id, require_admin
from app.core.pii import mask_phone
from app.dependencies import DBSession
from app.exceptions import BadRequestException, NotFoundException
from app.models.admin_audit_log import AdminAuditLog
from app.models.order import Order, OrderStatus
from app.models.user import User
from app.repositories.companion_profile import CompanionProfileRepository
from app.repositories.order import OrderRepository
from app.repositories.payment import PaymentRepository
from app.services.dead_letter import record_dead_letter
from app.services.notification import NotificationService
from app.services.payment_service import PaymentService

router = APIRouter(
    prefix="/orders",
    tags=["admin-orders"],
    dependencies=[Depends(require_admin)],
)


# Sentinel used for list-scoped audit rows (no single target).
_LIST_TARGET = UUID("00000000-0000-0000-0000-000000000000")


# Statuses for which a refund may be initiated. Aligns with the contract
# in docs/admin-mvp-scope.md (B4) — order must already have a successful
# pay-side Payment row, which only exists after the order moves out of
# ``created``.
# Statuses that represent an order cancellation. Used by ``force-status``
# to drive W19 side-effects (auto-refund + dual-notify).
_FORCE_CANCEL_STATUSES: set[OrderStatus] = {
    OrderStatus.cancelled_by_patient,
    OrderStatus.cancelled_by_companion,
    OrderStatus.rejected_by_companion,
    OrderStatus.expired,
}


REFUNDABLE_STATUSES: set[OrderStatus] = {
    OrderStatus.accepted,
    OrderStatus.in_progress,
    OrderStatus.completed,
    OrderStatus.reviewed,
}


# Force-status deny-list (W18 audit). The state machine is intentionally
# bypassed by ``force-status``; this guard only blocks transitions that
# *cannot* be reconciled later without manual money / notification work.
# Any allowed transition still files a TODO so W19 can implement the
# follow-up (refund / notify / stats counter).
def _is_forbidden_force_transition(old: OrderStatus, new: OrderStatus) -> str | None:
    """Return None if allowed, otherwise a human-readable reason string."""
    if old == new:
        return f"already in status '{old.value}'"
    # ``reviewed`` has its own endpoint (review submission). Force-status is
    # never the right path to land there.
    if new == OrderStatus.reviewed:
        return "use review submission flow, not force-status, to enter 'reviewed'"
    # ``refunded`` is not even an OrderStatus member today; if a future
    # migration adds it, keep this guard so accountants don't re-open it.
    if old.value == "refunded":
        return "refunded is terminal; cannot transition further via force-status"
    if old == OrderStatus.completed and new in {
        OrderStatus.created,
        OrderStatus.accepted,
        OrderStatus.in_progress,
    }:
        return "completed cannot regress to created/accepted/in_progress"
    if old in {
        OrderStatus.cancelled_by_patient,
        OrderStatus.cancelled_by_companion,
        OrderStatus.rejected_by_companion,
        OrderStatus.expired,
    } and new in {OrderStatus.in_progress, OrderStatus.completed}:
        return f"{old.value} cannot be force-revived to {new.value}"
    return None


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class OrderItem(BaseModel):
    id: str = Field(..., description="订单 UUID")
    order_number: str = Field(..., description="订单号")
    patient_id: str = Field(..., description="患者 UUID")
    patient_display_name: str | None = Field(
        None, description="患者昵称（来自 User.display_name 或 Order.patient_name 兜底）"
    )
    patient_phone_masked: str | None = Field(
        None, description="患者脱敏手机号（永远脱敏）"
    )
    companion_id: str | None = Field(None, description="陪诊师 UUID")
    companion_display_name: str | None = Field(
        None, description="陪诊师昵称（来自 User.display_name 或 Order.companion_name 兜底）"
    )
    hospital_id: str = Field(..., description="医院 UUID")
    status: str = Field(..., description="订单状态（OrderStatus 枚举值）")
    appointment_date: str = Field(..., description="预约日期 YYYY-MM-DD")
    appointment_time: str = Field(..., description="预约时间 HH:MM")
    price: str = Field(..., description="订单金额（元，字符串保两位小数）")
    service_name_snapshot: str | None = Field(
        None,
        description="下单时 service_packages.name 快照 (S2-REQ-003-P3, admin 改价不影响历史订单显示)",  # noqa: E501
        examples=["全程陪诊"],
    )
    service_price_snapshot: str | None = Field(
        None,
        description="下单时 service_packages.price 快照 (支付/退款以此为准, S2-REQ-003-P3)",
        examples=["299.00"],
    )
    created_at: str | None = Field(None, description="创建时间 ISO8601")


class PaginatedOrders(BaseModel):
    items: list[OrderItem]
    total: int
    page: int
    page_size: int


class ForceStatusBody(BaseModel):
    status: str = Field(..., description="目标状态值（OrderStatus 之一）")
    reason: str = Field(..., min_length=1, max_length=500, description="操作原因")


class RefundBody(BaseModel):
    amount: Decimal = Field(..., gt=0, description="退款金额（元）")
    reason: str = Field(..., min_length=1, max_length=500, description="退款原因")


class ForceStatusResponse(BaseModel):
    order_id: str
    old_status: str
    new_status: str


class RefundResponse(BaseModel):
    order_id: str
    refund_amount: str
    refund_id: str | None
    payment_id: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_item(o: Order, users_by_id: dict[UUID, User]) -> dict:
    patient = users_by_id.get(o.patient_id)
    companion = users_by_id.get(o.companion_id) if o.companion_id else None
    patient_name = (
        (patient.display_name if patient else None) or o.patient_name or None
    )
    patient_phone = patient.phone if patient else None
    companion_name = (
        (companion.display_name if companion else None) or o.companion_name or None
    )
    return {
        "id": str(o.id),
        "order_number": o.order_number,
        "patient_id": str(o.patient_id),
        "patient_display_name": patient_name,
        "patient_phone_masked": mask_phone(patient_phone) if patient_phone else None,
        "companion_id": str(o.companion_id) if o.companion_id else None,
        "companion_display_name": companion_name,
        "hospital_id": str(o.hospital_id),
        "status": o.status.value,
        "appointment_date": o.appointment_date,
        "appointment_time": o.appointment_time,
        "price": str(Decimal(str(o.price)).quantize(Decimal("0.01"))),
        "service_name_snapshot": o.service_name_snapshot,
        "service_price_snapshot": (
            str(Decimal(str(o.service_price_snapshot)).quantize(Decimal("0.01")))
            if o.service_price_snapshot is not None
            else None
        ),
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }


async def _fetch_users(session, ids: set[UUID]) -> dict[UUID, User]:
    if not ids:
        return {}
    rows = (
        await session.execute(select(User).where(User.id.in_(ids)))
    ).scalars().all()
    return {u.id: u for u in rows}


def _audit(
    session,
    *,
    target_type: str,
    target_id: UUID,
    action: str,
    operator: str,
    reason: str | None = None,
) -> None:
    session.add(
        AdminAuditLog(
            target_type=target_type,
            target_id=target_id,
            action=action,
            operator=operator,
            reason=reason,
        )
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=PaginatedOrders,
    summary="后台：订单列表",
    description="按状态 / 患者 / 陪诊师 / 预约日期范围分页查询订单。",
)
async def list_orders(
    session: DBSession,
    operator: str = Depends(admin_operator_id),
    status: str | None = Query(None, description="OrderStatus 之一"),
    patient_id: UUID | None = Query(None),
    companion_id: UUID | None = Query(None),
    date_from: str | None = Query(None, description="预约开始日期 YYYY-MM-DD"),
    date_to: str | None = Query(None, description="预约结束日期 YYYY-MM-DD"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    repo = OrderRepository(session)
    skip = (page - 1) * page_size
    order_status: OrderStatus | None
    if status:
        try:
            order_status = OrderStatus(status)
        except ValueError as exc:
            raise BadRequestException(f"Invalid status: {status}") from exc
    else:
        order_status = None

    items, total = await repo.list_all(
        status=order_status,
        patient_id=patient_id,
        companion_id=companion_id,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=page_size,
    )

    user_ids: set[UUID] = set()
    for o in items:
        user_ids.add(o.patient_id)
        if o.companion_id:
            user_ids.add(o.companion_id)
    users_by_id = await _fetch_users(session, user_ids)

    payload_items = [_build_item(o, users_by_id) for o in items]

    summary = (
        f"status={status} patient_id={patient_id} companion_id={companion_id} "
        f"date_from={date_from} date_to={date_to} page={page} "
        f"limit={page_size} returned={len(payload_items)}"
    )
    _audit(
        session,
        target_type="order",
        target_id=_LIST_TARGET,
        action="view_orders_list",
        operator=operator,
        reason=summary,
    )
    await session.flush()

    return {
        "items": payload_items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(
    "/{order_id}",
    response_model=OrderItem,
    summary="后台：订单详情",
    description="返回单个订单的完整字段（含 patient_display_name / companion_display_name / patient_phone_masked / price），并写入 view_order_detail 审计行。",  # noqa: E501
)
async def get_order(
    order_id: UUID,
    session: DBSession,
    operator: str = Depends(admin_operator_id),
):
    repo = OrderRepository(session)
    order = await repo.get_by_id(order_id)
    if order is None:
        raise NotFoundException("Order not found")

    ids: set[UUID] = {order.patient_id}
    if order.companion_id:
        ids.add(order.companion_id)
    users_by_id = await _fetch_users(session, ids)

    _audit(
        session,
        target_type="order",
        target_id=order_id,
        action="view_order_detail",
        operator=operator,
    )
    await session.flush()

    return _build_item(order, users_by_id)


@router.post(
    "/{order_id}/force-status",
    response_model=ForceStatusResponse,
    summary="后台：强制修改订单状态",
    description=(
        "管理员手动覆盖订单状态，**绕过业务状态机**，仅用于运营干预。"
        " 必须提供原因；进入禁止转换会 400 + 写 force_status_denied 审计。"
    ),
)
async def force_order_status(
    order_id: UUID,
    body: ForceStatusBody,
    session: DBSession,
    operator: str = Depends(admin_operator_id),
):
    repo = OrderRepository(session)
    order = await repo.get_by_id(order_id)
    if order is None:
        raise NotFoundException("Order not found")

    try:
        new_status = OrderStatus(body.status)
    except ValueError as exc:
        raise BadRequestException(f"Invalid status: {body.status}") from exc

    old_status = order.status

    forbidden = _is_forbidden_force_transition(old_status, new_status)
    if forbidden is not None:
        # Persist the deny audit *before* raising; otherwise the
        # BadRequestException would trigger ``get_db``'s rollback and the
        # audit row would be lost.
        _audit(
            session,
            target_type="order",
            target_id=order_id,
            action="force_status_denied",
            operator=operator,
            reason=(
                f"{old_status.value}->{new_status.value}: {forbidden} "
                f"(reason={body.reason})"
            ),
        )
        await session.commit()
        raise BadRequestException(
            f"Forbidden force-status transition "
            f"{old_status.value} -> {new_status.value}: {forbidden}"
        )

    order.status = new_status

    # ---- W19: side-effects driven by the forced transition ---------------
    side_effects: dict[str, str] = {}

    # (1) Force-cancel → issue automatic refund if order was paid.
    #     We mirror the policy used by the standard cancel flow but always
    #     refund 100% (operator override == platform-side fault-handling).
    refund_required = new_status in _FORCE_CANCEL_STATUSES
    if refund_required:
        pay_repo = PaymentRepository(session)
        original_pay = await pay_repo.get_by_order_and_type(order_id, "pay")
        if original_pay and original_pay.status == "success":
            existing_refund = await pay_repo.get_by_order_and_type(
                order_id, "refund"
            )
            if existing_refund is None:
                paid_amount = Decimal(str(original_pay.amount)).quantize(
                    Decimal("0.01")
                )
                payment_svc = PaymentService(session)
                try:
                    await payment_svc.create_refund(
                        order_id=order_id,
                        user_id=order.patient_id,
                        original_amount=paid_amount,
                        refund_amount=paid_amount,
                    )
                    side_effects["refund"] = "issued"
                except BadRequestException as exc:
                    # Don't block the force transition — record dead_letter
                    # so ops can replay/compensate via the queue.
                    # PaymentService raises BadRequest *before* dirtying the
                    # session for provider/network failures, but if it ever
                    # left rows in flight, the outer ``get_db`` rollback
                    # would clean them up. We deliberately use a *fresh*
                    # session for the dead_letter write to survive that.
                    from app.database import async_session as _async_session

                    try:
                        async with _async_session() as _dl_session:
                            await record_dead_letter(
                                _dl_session,
                                channel="order_refund",
                                reason="force_status_refund_failed",
                                target_type="order",
                                target_id=order_id,
                                payload={
                                    "trigger": "admin_force_status",
                                    "operator": operator,
                                    "old_status": old_status.value,
                                    "new_status": new_status.value,
                                    "amount": str(paid_amount),
                                    "error": str(exc.detail),
                                },
                            )
                            await _dl_session.commit()
                    except Exception:  # noqa: BLE001
                        pass
                    side_effects["refund"] = f"dead_letter:{exc.detail}"
            else:
                side_effects["refund"] = "already_refunded"
        else:
            side_effects["refund"] = "unpaid"

        # (2) Notify *both* parties about the admin-driven cancellation
        #     (the patient always exists; companion may be unassigned for
        #     broadcast orders that never got accepted).
        notif_svc = NotificationService(session)
        try:
            await notif_svc.notify_order_status_changed(
                order, new_status.value, order.patient_id
            )
            if order.companion_id is not None:
                await notif_svc.notify_order_status_changed(
                    order, new_status.value, order.companion_id
                )
            side_effects["notify"] = (
                "patient+companion" if order.companion_id else "patient_only"
            )
        except Exception as exc:  # noqa: BLE001
            # Notification failures must never block the state change.
            from app.database import async_session as _async_session

            try:
                async with _async_session() as _dl_session:
                    await record_dead_letter(
                        _dl_session,
                        channel="notification",
                        reason="force_status_notify_failed",
                        target_type="order",
                        target_id=order_id,
                        payload={
                            "trigger": "admin_force_status",
                            "operator": operator,
                            "new_status": new_status.value,
                            "error": str(exc),
                        },
                    )
                    await _dl_session.commit()
            except Exception:  # noqa: BLE001
                pass
            side_effects["notify"] = f"dead_letter:{exc}"

    # (3) Force-complete → bump companion ``total_orders`` counter so the
    #     companion's profile stats stay in sync with manual completions.
    if (
        new_status == OrderStatus.completed
        and order.companion_id is not None
        and old_status != OrderStatus.completed
    ):
        try:
            companion_repo = CompanionProfileRepository(session)
            profile = await companion_repo.get_by_user_id(order.companion_id)
            if profile is not None:
                await companion_repo.update(
                    profile, {"total_orders": profile.total_orders + 1}
                )
                side_effects["total_orders"] = str(profile.total_orders)
        except Exception as exc:  # noqa: BLE001
            side_effects["total_orders"] = f"skipped:{exc}"

    audit_reason = f"{old_status.value}->{new_status.value}: {body.reason}"
    if side_effects:
        audit_reason += " | side_effects=" + ",".join(
            f"{k}={v}" for k, v in side_effects.items()
        )
    log = AdminAuditLog(
        target_type="order",
        target_id=order_id,
        action="force_status",
        operator=operator,
        reason=audit_reason,
    )
    session.add(log)
    await session.flush()

    return {
        "order_id": str(order_id),
        "old_status": old_status.value,
        "new_status": new_status.value,
    }


@router.post(
    "/{order_id}/refund",
    response_model=RefundResponse,
    summary="后台：管理员退款",
    description=(
        "管理员发起退款。约束："
        " (1) 订单状态需为 accepted / in_progress / completed / reviewed；"
        " (2) 退款金额 ≤ 已支付金额；"
        " (3) 同一订单已存在 success 退款时拒绝（依赖 PaymentService 唯一约束）。"
    ),
)
async def refund_order(
    order_id: UUID,
    body: RefundBody,
    session: DBSession,
    operator: str = Depends(admin_operator_id),
):
    repo = OrderRepository(session)
    order = await repo.get_by_id(order_id)
    if order is None:
        raise NotFoundException("Order not found")

    if order.status not in REFUNDABLE_STATUSES:
        raise BadRequestException(
            f"Order status '{order.status.value}' is not refundable"
        )

    pay_repo = PaymentRepository(session)
    original_pay = await pay_repo.get_by_order_and_type(order_id, "pay")
    if original_pay is None or original_pay.status != "success":
        raise BadRequestException(
            "原订单未支付成功，无法退款",
            error_code=error_codes.REFUND_ORDER_NOT_PAID,
        )

    try:
        refund_amount = Decimal(body.amount).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise BadRequestException("Invalid refund amount") from exc

    paid_amount = Decimal(str(original_pay.amount)).quantize(Decimal("0.01"))
    if refund_amount > paid_amount:
        raise BadRequestException(
            f"退款金额 {refund_amount} 超过原支付金额 {paid_amount}"
        )

    payment_svc = PaymentService(session)
    result = await payment_svc.create_refund(
        order_id=order_id,
        user_id=order.patient_id,
        original_amount=paid_amount,
        refund_amount=refund_amount,
    )

    log = AdminAuditLog(
        target_type="order",
        target_id=order_id,
        action="refund",
        operator=operator,
        reason=f"amount={refund_amount}: {body.reason}",
    )
    session.add(log)
    await session.flush()

    return {
        "order_id": str(order_id),
        "refund_amount": str(refund_amount),
        "refund_id": result.refund_id,
        "payment_id": str(result.payment_id),
    }
