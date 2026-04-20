# Dead code paths that cannot be triggered via normal OrderService calls:
# - None identified; all branches appear reachable through the public API.

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import BadRequestException, ForbiddenException, NotFoundException
from app.models.companion_profile import CompanionProfile, VerificationStatus
from app.models.hospital import Hospital
from app.models.order import Order, OrderStatus, ServiceType, ORDER_TRANSITIONS
from app.models.payment import Payment
from app.models.user import User, UserRole
from app.schemas.order import CreateOrderRequest
from app.services.order import OrderService, generate_order_number

from tests.conftest import test_session_factory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_user(
    phone: str = "13800000001",
    role: UserRole = UserRole.patient,
    display_name: str | None = None,
) -> User:
    async with test_session_factory() as s:
        u = User(phone=phone, role=role, roles=role.value, display_name=display_name, is_active=True)
        s.add(u)
        await s.commit()
        await s.refresh(u)
        return u


async def _make_hospital(name: str = "测试医院") -> Hospital:
    async with test_session_factory() as s:
        h = Hospital(name=name, address="北京", level="三甲")
        s.add(h)
        await s.commit()
        await s.refresh(h)
        return h


async def _make_companion_profile(
    user_id: uuid.UUID,
    real_name: str = "陪诊师A",
    verification_status: VerificationStatus = VerificationStatus.verified,
) -> CompanionProfile:
    async with test_session_factory() as s:
        p = CompanionProfile(user_id=user_id, real_name=real_name, verification_status=verification_status)
        s.add(p)
        await s.commit()
        await s.refresh(p)
        return p


async def _make_order(
    patient_id: uuid.UUID,
    hospital_id: uuid.UUID,
    *,
    companion_id: uuid.UUID | None = None,
    status: OrderStatus = OrderStatus.created,
    price: float = 299.0,
) -> Order:
    async with test_session_factory() as s:
        o = Order(
            order_number=generate_order_number(),
            patient_id=patient_id,
            hospital_id=hospital_id,
            companion_id=companion_id,
            service_type=ServiceType.full_accompany,
            status=status,
            appointment_date="2026-05-01",
            appointment_time="09:00",
            price=price,
            hospital_name="测试医院",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=4),
        )
        s.add(o)
        await s.commit()
        await s.refresh(o)
        return o


async def _make_payment(
    order_id: uuid.UUID,
    user_id: uuid.UUID,
    *,
    amount: float = 299.0,
    payment_type: str = "pay",
    status: str = "success",
) -> Payment:
    async with test_session_factory() as s:
        p = Payment(
            order_id=order_id,
            user_id=user_id,
            amount=amount,
            payment_type=payment_type,
            status=status,
        )
        s.add(p)
        await s.commit()
        await s.refresh(p)
        return p


def _req(hospital_id: uuid.UUID, **kw) -> CreateOrderRequest:
    defaults = dict(
        service_type="full_accompany",
        hospital_id=hospital_id,
        appointment_date="2026-05-01",
        appointment_time="09:00",
    )
    defaults.update(kw)
    return CreateOrderRequest(**defaults)


# ---------------------------------------------------------------------------
# Tests — generate_order_number
# ---------------------------------------------------------------------------

class TestGenerateOrderNumber:
    def test_format(self):
        num = generate_order_number()
        assert num.startswith("YLA")
        assert len(num) > 10


# ---------------------------------------------------------------------------
# Tests — create_order
# ---------------------------------------------------------------------------

class TestCreateOrder:
    async def test_create_order_success(self):
        patient = await _make_user(phone="10000000001")
        hospital = await _make_hospital()
        async with test_session_factory() as s:
            svc = OrderService(s)
            order = await svc.create_order(patient, _req(hospital.id))
            await s.commit()
        assert order.status == OrderStatus.created
        assert order.price == 299.0
        assert order.patient_id == patient.id

    async def test_create_order_has_unpaid_blocks(self):
        patient = await _make_user(phone="10000000002")
        hospital = await _make_hospital("医院2")
        # create an unpaid order directly
        await _make_order(patient.id, hospital.id, status=OrderStatus.created)
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(BadRequestException, match="未支付"):
                await svc.create_order(patient, _req(hospital.id))

    async def test_create_order_hospital_not_found(self):
        patient = await _make_user(phone="10000000003")
        fake_id = uuid.uuid4()
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(NotFoundException, match="Hospital not found"):
                await svc.create_order(patient, _req(fake_id))

    async def test_create_order_with_companion(self):
        patient = await _make_user(phone="10000000004")
        companion = await _make_user(phone="10000000005", role=UserRole.companion)
        hospital = await _make_hospital("医院3")
        profile = await _make_companion_profile(companion.id)
        async with test_session_factory() as s:
            svc = OrderService(s)
            order = await svc.create_order(patient, _req(hospital.id, companion_id=profile.id))
            await s.commit()
        assert order.companion_id == companion.id
        assert order.companion_name == "陪诊师A"

    async def test_create_order_unverified_companion_rejected(self):
        patient = await _make_user(phone="10000000006")
        companion = await _make_user(phone="10000000007", role=UserRole.companion)
        hospital = await _make_hospital("医院4")
        await _make_companion_profile(companion.id, verification_status=VerificationStatus.pending)
        async with test_session_factory() as s:
            svc = OrderService(s)
            profile = await s.execute(
                __import__("sqlalchemy").select(CompanionProfile).where(CompanionProfile.user_id == companion.id)
            )
            cp = profile.scalar_one()
            with pytest.raises(BadRequestException, match="not found or not verified"):
                await svc.create_order(patient, _req(hospital.id, companion_id=cp.id))


# ---------------------------------------------------------------------------
# Tests — get_order
# ---------------------------------------------------------------------------

class TestGetOrder:
    async def test_get_order_not_found(self):
        patient = await _make_user(phone="10000000010")
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(NotFoundException, match="Order not found"):
                await svc.get_order(uuid.uuid4(), patient)

    async def test_get_order_forbidden_for_other_patient(self):
        patient1 = await _make_user(phone="10000000011")
        patient2 = await _make_user(phone="10000000012")
        hospital = await _make_hospital("医院G")
        order = await _make_order(patient1.id, hospital.id)
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(ForbiddenException, match="Not your order"):
                await svc.get_order(order.id, patient2)


# ---------------------------------------------------------------------------
# Tests — accept_order
# ---------------------------------------------------------------------------

class TestAcceptOrder:
    async def test_accept_order_success(self):
        patient = await _make_user(phone="10000000020")
        companion = await _make_user(phone="10000000021", role=UserRole.companion)
        hospital = await _make_hospital("医院A")
        order = await _make_order(patient.id, hospital.id)
        async with test_session_factory() as s:
            svc = OrderService(s)
            result = await svc.accept_order(order.id, companion)
            await s.commit()
        assert result.status == OrderStatus.accepted
        assert result.companion_id == companion.id

    async def test_accept_order_not_companion_role(self):
        patient = await _make_user(phone="10000000022")
        hospital = await _make_hospital("医院A2")
        order = await _make_order(patient.id, hospital.id)
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(ForbiddenException, match="Only companions"):
                await svc.accept_order(order.id, patient)

    async def test_accept_already_accepted_fails(self):
        patient = await _make_user(phone="10000000023")
        companion = await _make_user(phone="10000000024", role=UserRole.companion)
        hospital = await _make_hospital("医院A3")
        order = await _make_order(patient.id, hospital.id, companion_id=companion.id, status=OrderStatus.accepted)
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(BadRequestException, match="Cannot transition"):
                await svc.accept_order(order.id, companion)


# ---------------------------------------------------------------------------
# Tests — start_order
# ---------------------------------------------------------------------------

class TestStartOrder:
    async def test_start_order_success(self):
        patient = await _make_user(phone="10000000030")
        companion = await _make_user(phone="10000000031", role=UserRole.companion)
        hospital = await _make_hospital("医院S")
        order = await _make_order(patient.id, hospital.id, companion_id=companion.id, status=OrderStatus.accepted)
        async with test_session_factory() as s:
            svc = OrderService(s)
            result = await svc.start_order(order.id, companion)
            await s.commit()
        assert result.status == OrderStatus.in_progress

    async def test_start_order_wrong_companion(self):
        patient = await _make_user(phone="10000000032")
        companion = await _make_user(phone="10000000033", role=UserRole.companion)
        other = await _make_user(phone="10000000034", role=UserRole.companion)
        hospital = await _make_hospital("医院S2")
        order = await _make_order(patient.id, hospital.id, companion_id=companion.id, status=OrderStatus.accepted)
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(ForbiddenException, match="Not your order"):
                await svc.start_order(order.id, other)

    async def test_start_cancelled_order_fails(self):
        patient = await _make_user(phone="10000000035")
        companion = await _make_user(phone="10000000036", role=UserRole.companion)
        hospital = await _make_hospital("医院S3")
        order = await _make_order(patient.id, hospital.id, companion_id=companion.id, status=OrderStatus.cancelled_by_patient)
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(BadRequestException, match="Cannot transition"):
                await svc.start_order(order.id, companion)


# ---------------------------------------------------------------------------
# Tests — complete_order
# ---------------------------------------------------------------------------

class TestCompleteOrder:
    async def test_complete_order_success(self):
        patient = await _make_user(phone="10000000040")
        companion = await _make_user(phone="10000000041", role=UserRole.companion)
        hospital = await _make_hospital("医院C")
        order = await _make_order(patient.id, hospital.id, companion_id=companion.id, status=OrderStatus.in_progress)
        async with test_session_factory() as s:
            svc = OrderService(s)
            result = await svc.complete_order(order.id, companion)
            await s.commit()
        assert result.status == OrderStatus.completed

    async def test_complete_completed_order_fails(self):
        patient = await _make_user(phone="10000000042")
        companion = await _make_user(phone="10000000043", role=UserRole.companion)
        hospital = await _make_hospital("医院C2")
        order = await _make_order(patient.id, hospital.id, companion_id=companion.id, status=OrderStatus.completed)
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(BadRequestException, match="Cannot transition"):
                await svc.complete_order(order.id, companion)


# ---------------------------------------------------------------------------
# Tests — cancel_order
# ---------------------------------------------------------------------------

class TestCancelOrder:
    async def test_cancel_by_patient_created(self):
        patient = await _make_user(phone="10000000050")
        hospital = await _make_hospital("医院X1")
        order = await _make_order(patient.id, hospital.id)
        async with test_session_factory() as s:
            svc = OrderService(s)
            result = await svc.cancel_order(order.id, patient)
            await s.commit()
        assert result.status == OrderStatus.cancelled_by_patient

    async def test_cancel_by_companion_accepted(self):
        patient = await _make_user(phone="10000000051")
        companion = await _make_user(phone="10000000052", role=UserRole.companion)
        hospital = await _make_hospital("医院X2")
        order = await _make_order(patient.id, hospital.id, companion_id=companion.id, status=OrderStatus.accepted)
        async with test_session_factory() as s:
            svc = OrderService(s)
            result = await svc.cancel_order(order.id, companion)
            await s.commit()
        assert result.status == OrderStatus.cancelled_by_companion

    async def test_cancel_completed_order_fails(self):
        patient = await _make_user(phone="10000000053")
        companion = await _make_user(phone="10000000054", role=UserRole.companion)
        hospital = await _make_hospital("医院X3")
        order = await _make_order(patient.id, hospital.id, companion_id=companion.id, status=OrderStatus.completed)
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(BadRequestException, match="Cannot transition"):
                await svc.cancel_order(order.id, patient)

    async def test_cancel_with_payment_triggers_refund(self):
        """Cancel a paid+accepted order → 100% refund created."""
        patient = await _make_user(phone="10000000055")
        companion = await _make_user(phone="10000000056", role=UserRole.companion)
        hospital = await _make_hospital("医院X4")
        order = await _make_order(patient.id, hospital.id, companion_id=companion.id, status=OrderStatus.accepted)
        await _make_payment(order.id, patient.id, amount=299.0)
        async with test_session_factory() as s:
            svc = OrderService(s)
            result = await svc.cancel_order(order.id, patient)
            await s.commit()
        assert result.status == OrderStatus.cancelled_by_patient
        # Verify refund payment was created
        async with test_session_factory() as s:
            from sqlalchemy import select
            refund = (await s.execute(
                select(Payment).where(Payment.order_id == order.id, Payment.payment_type == "refund")
            )).scalar_one_or_none()
            assert refund is not None
            assert refund.amount == 299.0

    async def test_cancel_in_progress_with_payment_half_refund(self):
        """Cancel in_progress paid order → 50% refund."""
        patient = await _make_user(phone="10000000057")
        companion = await _make_user(phone="10000000058", role=UserRole.companion)
        hospital = await _make_hospital("医院X5")
        order = await _make_order(patient.id, hospital.id, companion_id=companion.id, status=OrderStatus.in_progress)
        await _make_payment(order.id, patient.id, amount=299.0)
        async with test_session_factory() as s:
            svc = OrderService(s)
            result = await svc.cancel_order(order.id, patient)
            await s.commit()
        assert result.status == OrderStatus.cancelled_by_patient
        async with test_session_factory() as s:
            from sqlalchemy import select
            refund = (await s.execute(
                select(Payment).where(Payment.order_id == order.id, Payment.payment_type == "refund")
            )).scalar_one_or_none()
            assert refund is not None
            assert refund.amount == 149.5  # 50% of 299

    async def test_cancel_other_patients_order_forbidden(self):
        patient1 = await _make_user(phone="10000000059")
        patient2 = await _make_user(phone="10000000060")
        hospital = await _make_hospital("医院X6")
        order = await _make_order(patient1.id, hospital.id)
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(ForbiddenException, match="Not your order"):
                await svc.cancel_order(order.id, patient2)


# ---------------------------------------------------------------------------
# Tests — pay_order
# ---------------------------------------------------------------------------

class TestPayOrder:
    async def test_pay_order_success(self):
        patient = await _make_user(phone="10000000070")
        hospital = await _make_hospital("医院P")
        order = await _make_order(patient.id, hospital.id)
        async with test_session_factory() as s:
            svc = OrderService(s)
            result = await svc.pay_order(order.id, patient)
            await s.commit()
        assert result.mock_success is True

    async def test_pay_cancelled_order_fails(self):
        patient = await _make_user(phone="10000000071")
        hospital = await _make_hospital("医院P2")
        order = await _make_order(patient.id, hospital.id, status=OrderStatus.cancelled_by_patient)
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(BadRequestException, match="Cannot pay"):
                await svc.pay_order(order.id, patient)

    async def test_pay_other_patients_order_forbidden(self):
        patient1 = await _make_user(phone="10000000072")
        patient2 = await _make_user(phone="10000000073")
        hospital = await _make_hospital("医院P3")
        order = await _make_order(patient1.id, hospital.id)
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(ForbiddenException, match="Not your order"):
                await svc.pay_order(order.id, patient2)


# ---------------------------------------------------------------------------
# Tests — refund_order
# ---------------------------------------------------------------------------

class TestRefundOrder:
    async def test_refund_cancelled_order_success(self):
        patient = await _make_user(phone="10000000080")
        hospital = await _make_hospital("医院R")
        order = await _make_order(patient.id, hospital.id, status=OrderStatus.cancelled_by_patient)
        await _make_payment(order.id, patient.id)
        async with test_session_factory() as s:
            svc = OrderService(s)
            refund = await svc.refund_order(order.id, patient)
            await s.commit()
        assert refund.payment_type == "refund"

    async def test_refund_non_cancelled_order_fails(self):
        patient = await _make_user(phone="10000000081")
        hospital = await _make_hospital("医院R2")
        order = await _make_order(patient.id, hospital.id, status=OrderStatus.created)
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(BadRequestException, match="Only cancelled orders"):
                await svc.refund_order(order.id, patient)

    async def test_refund_other_patients_order_forbidden(self):
        patient1 = await _make_user(phone="10000000082")
        patient2 = await _make_user(phone="10000000083")
        hospital = await _make_hospital("医院R3")
        order = await _make_order(patient1.id, hospital.id, status=OrderStatus.cancelled_by_patient)
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(ForbiddenException, match="Not your order"):
                await svc.refund_order(order.id, patient2)


# ---------------------------------------------------------------------------
# Tests — reject_order
# ---------------------------------------------------------------------------

class TestRejectOrder:
    async def test_reject_order_success(self):
        patient = await _make_user(phone="10000000090")
        companion = await _make_user(phone="10000000091", role=UserRole.companion)
        hospital = await _make_hospital("医院J")
        order = await _make_order(patient.id, hospital.id, companion_id=companion.id)
        async with test_session_factory() as s:
            svc = OrderService(s)
            result = await svc.reject_order(order.id, companion)
            await s.commit()
        assert result.status == OrderStatus.rejected_by_companion

    async def test_reject_by_patient_forbidden(self):
        patient = await _make_user(phone="10000000092")
        hospital = await _make_hospital("医院J2")
        order = await _make_order(patient.id, hospital.id)
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(ForbiddenException, match="Only companions"):
                await svc.reject_order(order.id, patient)

    async def test_reject_broadcast_order_fails(self):
        """Broadcast order (no companion_id) cannot be rejected."""
        patient = await _make_user(phone="10000000093")
        companion = await _make_user(phone="10000000094", role=UserRole.companion)
        hospital = await _make_hospital("医院J3")
        order = await _make_order(patient.id, hospital.id, companion_id=None)
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(BadRequestException, match="广播订单"):
                await svc.reject_order(order.id, companion)

    async def test_reject_accepted_order_fails(self):
        patient = await _make_user(phone="10000000095")
        companion = await _make_user(phone="10000000096", role=UserRole.companion)
        hospital = await _make_hospital("医院J4")
        order = await _make_order(patient.id, hospital.id, companion_id=companion.id, status=OrderStatus.accepted)
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(BadRequestException, match="Can only reject"):
                await svc.reject_order(order.id, companion)

    async def test_reject_with_payment_triggers_refund(self):
        patient = await _make_user(phone="10000000097")
        companion = await _make_user(phone="10000000098", role=UserRole.companion)
        hospital = await _make_hospital("医院J5")
        order = await _make_order(patient.id, hospital.id, companion_id=companion.id)
        await _make_payment(order.id, patient.id)
        async with test_session_factory() as s:
            svc = OrderService(s)
            result = await svc.reject_order(order.id, companion)
            await s.commit()
        assert result.status == OrderStatus.rejected_by_companion
        async with test_session_factory() as s:
            from sqlalchemy import select
            refund = (await s.execute(
                select(Payment).where(Payment.order_id == order.id, Payment.payment_type == "refund")
            )).scalar_one_or_none()
            assert refund is not None


# ---------------------------------------------------------------------------
# Tests — check_expired_orders
# ---------------------------------------------------------------------------

class TestCheckExpiredOrders:
    async def test_expire_unpaid_order(self):
        patient = await _make_user(phone="10000000100")
        hospital = await _make_hospital("医院E")
        async with test_session_factory() as s:
            o = Order(
                order_number=generate_order_number(),
                patient_id=patient.id,
                hospital_id=hospital.id,
                service_type=ServiceType.full_accompany,
                status=OrderStatus.created,
                appointment_date="2026-05-01",
                appointment_time="09:00",
                price=299.0,
                expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # already expired
            )
            s.add(o)
            await s.commit()
            await s.refresh(o)
            order_id = o.id

        async with test_session_factory() as s:
            svc = OrderService(s)
            cancelled = await svc.check_expired_orders()
            await s.commit()
        assert len(cancelled) >= 1
        assert any(c.id == order_id for c in cancelled)
        assert all(c.status == OrderStatus.expired for c in cancelled)

    async def test_expire_paid_order_triggers_refund(self):
        patient = await _make_user(phone="10000000101")
        hospital = await _make_hospital("医院E2")
        async with test_session_factory() as s:
            o = Order(
                order_number=generate_order_number(),
                patient_id=patient.id,
                hospital_id=hospital.id,
                service_type=ServiceType.full_accompany,
                status=OrderStatus.created,
                appointment_date="2026-05-01",
                appointment_time="09:00",
                price=299.0,
                expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
            )
            s.add(o)
            await s.commit()
            await s.refresh(o)
            order_id = o.id

        await _make_payment(order_id, patient.id)

        async with test_session_factory() as s:
            svc = OrderService(s)
            cancelled = await svc.check_expired_orders()
            await s.commit()

        async with test_session_factory() as s:
            from sqlalchemy import select
            refund = (await s.execute(
                select(Payment).where(Payment.order_id == order_id, Payment.payment_type == "refund")
            )).scalar_one_or_none()
            assert refund is not None


# ---------------------------------------------------------------------------
# Tests — request_start_service / confirm_start_service
# ---------------------------------------------------------------------------

class TestStartServiceFlow:
    async def test_request_start_service_success(self):
        patient = await _make_user(phone="10000000110")
        companion = await _make_user(phone="10000000111", role=UserRole.companion)
        hospital = await _make_hospital("医院F")
        order = await _make_order(patient.id, hospital.id, companion_id=companion.id, status=OrderStatus.accepted)
        async with test_session_factory() as s:
            svc = OrderService(s)
            result = await svc.request_start_service(order.id, companion)
        # Status should remain accepted (just a notification, no state change)
        assert result.status == OrderStatus.accepted

    async def test_request_start_wrong_status(self):
        patient = await _make_user(phone="10000000112")
        companion = await _make_user(phone="10000000113", role=UserRole.companion)
        hospital = await _make_hospital("医院F2")
        order = await _make_order(patient.id, hospital.id, companion_id=companion.id, status=OrderStatus.in_progress)
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(BadRequestException, match="订单状态不允许"):
                await svc.request_start_service(order.id, companion)

    async def test_confirm_start_service_success(self):
        patient = await _make_user(phone="10000000114")
        companion = await _make_user(phone="10000000115", role=UserRole.companion)
        hospital = await _make_hospital("医院F3")
        order = await _make_order(patient.id, hospital.id, companion_id=companion.id, status=OrderStatus.accepted)
        async with test_session_factory() as s:
            svc = OrderService(s)
            result = await svc.confirm_start_service(order.id, patient)
            await s.commit()
        assert result.status == OrderStatus.in_progress

    async def test_confirm_start_wrong_patient(self):
        patient1 = await _make_user(phone="10000000116")
        patient2 = await _make_user(phone="10000000117")
        companion = await _make_user(phone="10000000118", role=UserRole.companion)
        hospital = await _make_hospital("医院F4")
        order = await _make_order(patient1.id, hospital.id, companion_id=companion.id, status=OrderStatus.accepted)
        async with test_session_factory() as s:
            svc = OrderService(s)
            with pytest.raises(ForbiddenException, match="Not your order"):
                await svc.confirm_start_service(order.id, patient2)


# ---------------------------------------------------------------------------
# Tests — _validate_transition (via public methods)
# ---------------------------------------------------------------------------

class TestStateTransitions:
    async def test_all_terminal_states_reject_further_transitions(self):
        """Expired/cancelled/rejected orders cannot transition further."""
        patient = await _make_user(phone="10000000120")
        companion = await _make_user(phone="10000000121", role=UserRole.companion)
        hospital = await _make_hospital("医院T")
        terminal_statuses = [
            OrderStatus.cancelled_by_patient,
            OrderStatus.cancelled_by_companion,
            OrderStatus.rejected_by_companion,
            OrderStatus.expired,
        ]
        for i, status in enumerate(terminal_statuses):
            order = await _make_order(
                patient.id, hospital.id,
                companion_id=companion.id,
                status=status,
            )
            async with test_session_factory() as s:
                svc = OrderService(s)
                with pytest.raises(BadRequestException, match="Cannot transition"):
                    await svc.start_order(order.id, companion)


# ---------------------------------------------------------------------------
# Tests — _fill_timeline (via get_order)
# ---------------------------------------------------------------------------

class TestFillTimeline:
    async def test_synthetic_timeline_for_created_order(self):
        patient = await _make_user(phone="10000000130")
        hospital = await _make_hospital("医院TL")
        order = await _make_order(patient.id, hospital.id)
        async with test_session_factory() as s:
            svc = OrderService(s)
            result = await svc.get_order(order.id, patient)
        assert hasattr(result, "timeline")
        assert len(result.timeline) >= 1
        assert result.timeline[0]["title"] == "订单已创建"

    async def test_synthetic_timeline_for_cancelled_order(self):
        patient = await _make_user(phone="10000000131")
        hospital = await _make_hospital("医院TL2")
        order = await _make_order(patient.id, hospital.id, status=OrderStatus.cancelled_by_patient)
        async with test_session_factory() as s:
            svc = OrderService(s)
            result = await svc.get_order(order.id, patient)
        # Should include cancellation label at the end
        assert result.timeline[-1]["title"] == "患者已取消"
