"""Direct repository-level tests to push coverage of `app.repositories.*`.

These exercise raw repo methods (not API surface) on the in-memory SQLite
test database. Targets:
  - app.repositories.hospital (search/filters/region helpers)
  - app.repositories.companion_profile (search variants)
  - app.repositories.device_token (CRUD helpers)
  - app.repositories.notification (mark-read variants)
  - app.repositories.review (avg rating / count)
  - app.repositories.payment (lookup helpers)
  - app.repositories.chat_message (mark_as_read / pagination)
  - app.repositories.user (lookups)
  - app.repositories.order (status filters / available / expired)
  - app.repositories.base (delete)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_message import ChatMessage, MessageType
from app.models.companion_profile import CompanionProfile, VerificationStatus
from app.models.device_token import DeviceToken
from app.models.hospital import Hospital
from app.models.notification import Notification, NotificationType
from app.models.order import Order, OrderStatus, ServiceType
from app.models.payment import Payment
from app.models.review import Review
from app.models.user import User, UserRole
from app.repositories.chat_message import ChatMessageRepository
from app.repositories.companion_profile import CompanionProfileRepository
from app.repositories.device_token import DeviceTokenRepository
from app.repositories.hospital import HospitalRepository
from app.repositories.notification import NotificationRepository
from app.repositories.order import OrderRepository
from app.repositories.payment import OrderStatusHistoryRepository, PaymentRepository
from app.repositories.review import ReviewRepository
from app.repositories.user import UserRepository
from tests.conftest import test_session_factory


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
async def _new_session() -> AsyncSession:
    return test_session_factory()


# ---------------------------------------------------------------------------
# Hospital repo
# ---------------------------------------------------------------------------
class TestHospitalRepository:
    async def test_search_filters_combined(self):
        """Search by every supported filter combo to cover all branches."""
        async with test_session_factory() as session:
            session.add_all(
                [
                    Hospital(
                        name="北京协和医院",
                        province="北京市",
                        city="北京",
                        district="东城区",
                        level="三甲",
                        tags="综合,儿科",
                    ),
                    Hospital(
                        name="北京天坛医院",
                        province="北京市",
                        city="北京",
                        district="丰台区",
                        level="三甲",
                        tags="神经",
                    ),
                    Hospital(
                        name="上海瑞金医院",
                        province="上海市",
                        city="上海",
                        district="黄浦区",
                        level="三甲",
                    ),
                ]
            )
            await session.commit()
            repo = HospitalRepository(session)

            items, total = await repo.search(
                keyword="北京",
                province="北京市",
                city="北京",
                district="东城区",
                level="三甲",
                tag="综合",
                skip=0,
                limit=10,
            )
            assert total == 1
            assert items[0].name == "北京协和医院"

    async def test_get_filter_options_full(self):
        """get_filter_options returns province/city/district/level/tag groups."""
        async with test_session_factory() as session:
            session.add_all(
                [
                    Hospital(
                        name="A",
                        province="北京",
                        city="北京",
                        district="海淀",
                        level="三甲",
                        tags="儿科,综合",
                    ),
                    Hospital(
                        name="B",
                        province="北京",
                        city="北京",
                        district="朝阳",
                        level="二甲",
                        tags=" 综合 , ",
                    ),
                    Hospital(
                        name="C",
                        province="上海",
                        city="上海",
                        district="徐汇",
                        level="三甲",
                    ),
                ]
            )
            await session.commit()
            repo = HospitalRepository(session)

            opts = await repo.get_filter_options()
            assert "北京" in opts["provinces"]
            assert "综合" in opts["tags"]

            # province-filtered cities
            opts2 = await repo.get_filter_options(province="北京")
            assert opts2["cities"] == ["北京"]

            # city-filtered districts
            opts3 = await repo.get_filter_options(city="北京")
            assert set(opts3["districts"]) == {"海淀", "朝阳"}

            # province-only districts (else branch)
            opts4 = await repo.get_filter_options(province="上海")
            assert opts4["districts"] == ["徐汇"]

    async def test_find_nearest_region_match_and_none(self):
        """find_nearest_region returns nearest record or None when empty."""
        async with test_session_factory() as session:
            repo = HospitalRepository(session)
            # No hospitals → None
            result = await repo.find_nearest_region(latitude=39.9, longitude=116.4)
            assert result is None

            session.add(
                Hospital(
                    name="H1",
                    province="北京",
                    city="北京",
                    latitude=39.91,
                    longitude=116.41,
                )
            )
            session.add(
                Hospital(
                    name="H2",
                    province="上海",
                    city="上海",
                    latitude=31.23,
                    longitude=121.47,
                )
            )
            await session.commit()
            res = await repo.find_nearest_region(latitude=39.9, longitude=116.4)
            assert res == {"province": "北京", "city": "北京"}


# ---------------------------------------------------------------------------
# CompanionProfile repo
# ---------------------------------------------------------------------------
class TestCompanionProfileRepository:
    async def test_search_with_hospital_district_fallback(self):
        """When companion has no service_hospitals, district fallback applies."""
        async with test_session_factory() as session:
            uid1, uid2 = uuid4(), uuid4()
            session.add_all(
                [
                    User(id=uid1, phone="13800000001"),
                    User(id=uid2, phone="13800000002"),
                    CompanionProfile(
                        user_id=uid1,
                        real_name="A",
                        verification_status=VerificationStatus.verified,
                        service_hospitals="hosp-xyz",
                    ),
                    CompanionProfile(
                        user_id=uid2,
                        real_name="B",
                        verification_status=VerificationStatus.verified,
                        service_hospitals=None,
                        service_area="海淀区",
                    ),
                ]
            )
            await session.commit()
            repo = CompanionProfileRepository(session)

            results = await repo.search(
                hospital_id="hosp-xyz",
                hospital_district="海淀区",
            )
            names = sorted(p.real_name for p in results)
            assert names == ["A", "B"]

    async def test_search_with_hospital_id_only(self):
        async with test_session_factory() as session:
            uid = uuid4()
            session.add_all(
                [
                    User(id=uid, phone="13800000003"),
                    CompanionProfile(
                        user_id=uid,
                        real_name="C",
                        verification_status=VerificationStatus.verified,
                        service_hospitals="h-only",
                    ),
                ]
            )
            await session.commit()
            repo = CompanionProfileRepository(session)
            results = await repo.search(hospital_id="h-only")
            assert len(results) == 1

    async def test_search_with_area_city_service_type(self):
        async with test_session_factory() as session:
            uid = uuid4()
            session.add_all(
                [
                    User(id=uid, phone="13800000004"),
                    CompanionProfile(
                        user_id=uid,
                        real_name="D",
                        verification_status=VerificationStatus.verified,
                        service_area="朝阳区",
                        service_city="北京",
                        service_types="full_accompany,queue",
                    ),
                ]
            )
            await session.commit()
            repo = CompanionProfileRepository(session)
            results = await repo.search(
                area="朝阳", city="北京", service_type="full_accompany"
            )
            assert len(results) == 1

    async def test_list_by_status(self):
        async with test_session_factory() as session:
            uid = uuid4()
            session.add_all(
                [
                    User(id=uid, phone="13800000005"),
                    CompanionProfile(
                        user_id=uid,
                        real_name="E",
                        verification_status=VerificationStatus.pending,
                    ),
                ]
            )
            await session.commit()
            repo = CompanionProfileRepository(session)
            results = await repo.list_by_status(VerificationStatus.pending)
            assert any(p.real_name == "E" for p in results)


# ---------------------------------------------------------------------------
# DeviceToken repo
# ---------------------------------------------------------------------------
class TestDeviceTokenRepository:
    async def test_crud_helpers(self):
        """Exercise get_by_token / list_by_user / delete_by_token."""
        async with test_session_factory() as session:
            uid = uuid4()
            session.add(User(id=uid, phone="13800000010"))
            await session.commit()
            repo = DeviceTokenRepository(session)

            d = await repo.create(
                DeviceToken(user_id=uid, token="t1", device_type="ios")
            )
            assert d.id is not None

            # get_by_token
            found = await repo.get_by_token("t1")
            assert found is not None and found.id == d.id

            # list_by_user
            lst = await repo.list_by_user(uid)
            assert len(lst) == 1

            # delete missing token returns False
            assert await repo.delete_by_token(uid, "nope") is False

            # delete existing returns True
            assert await repo.delete_by_token(uid, "t1") is True

            assert await repo.get_by_token("t1") is None


# ---------------------------------------------------------------------------
# Notification repo
# ---------------------------------------------------------------------------
class TestNotificationRepository:
    async def test_mark_read_variants(self):
        async with test_session_factory() as session:
            uid = uuid4()
            session.add(User(id=uid, phone="13800000020"))
            await session.commit()
            repo = NotificationRepository(session)

            n1 = await repo.create(
                Notification(
                    user_id=uid,
                    type=NotificationType.system,
                    title="t1",
                    body="b1",
                )
            )
            n2 = await repo.create(
                Notification(
                    user_id=uid,
                    type=NotificationType.system,
                    title="t2",
                    body="b2",
                )
            )

            assert await repo.count_unread(uid) == 2

            # mark single
            assert await repo.mark_as_read(n1.id, uid) is True
            assert await repo.count_unread(uid) == 1

            # mark wrong user → False
            other = uuid4()
            assert await repo.mark_as_read(n2.id, other) is False

            # mark all
            assert await repo.mark_all_read(uid) == 1
            assert await repo.count_unread(uid) == 0

            # list pagination
            items, total = await repo.list_by_user(uid, skip=0, limit=10)
            assert total == 2 and len(items) == 2


# ---------------------------------------------------------------------------
# Review repo
# ---------------------------------------------------------------------------
class TestReviewRepository:
    async def test_aggregate_helpers(self):
        async with test_session_factory() as session:
            patient = uuid4()
            companion = uuid4()
            hospital = uuid4()
            session.add_all(
                [
                    User(id=patient, phone="13800000030"),
                    User(id=companion, phone="13800000031"),
                    Hospital(id=hospital, name="H"),
                ]
            )
            await session.commit()
            repo = ReviewRepository(session)

            # Empty: avg=0, count=0
            assert await repo.get_companion_avg_rating(companion) == 0.0
            assert await repo.count_by_companion(companion) == 0

            # Create order + review
            order_repo = OrderRepository(session)
            order = await order_repo.create(
                Order(
                    order_number="YLA0000R",
                    patient_id=patient,
                    companion_id=companion,
                    hospital_id=hospital,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.completed,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=200.0,
                )
            )
            await repo.create(
                Review(
                    order_id=order.id,
                    patient_id=patient,
                    companion_id=companion,
                    rating=4,
                    content="ok",
                )
            )
            assert await repo.get_companion_avg_rating(companion) == 4.0
            assert await repo.count_by_companion(companion) == 1

            # get_by_order_id
            r = await repo.get_by_order_id(order.id)
            assert r is not None and r.rating == 4

            # list_by_companion
            items, total = await repo.list_by_companion(companion)
            assert total == 1 and len(items) == 1


# ---------------------------------------------------------------------------
# Payment repo (incl. order_status_history)
# ---------------------------------------------------------------------------
class TestPaymentRepository:
    async def test_lookup_helpers(self):
        async with test_session_factory() as session:
            patient = uuid4()
            hospital = uuid4()
            session.add_all(
                [
                    User(id=patient, phone="13800000040"),
                    Hospital(id=hospital, name="H"),
                ]
            )
            await session.commit()
            order_repo = OrderRepository(session)
            o = await order_repo.create(
                Order(
                    order_number="YLA0000P",
                    patient_id=patient,
                    hospital_id=hospital,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.created,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=99.0,
                )
            )
            repo = PaymentRepository(session)

            pay = await repo.create(
                Payment(
                    order_id=o.id,
                    user_id=patient,
                    amount=99.0,
                    payment_type="pay",
                    status="success",
                    trade_no="TXN1",
                )
            )
            refund = await repo.create(
                Payment(
                    order_id=o.id,
                    user_id=patient,
                    amount=99.0,
                    payment_type="refund",
                    status="success",
                    refund_id="R1",
                )
            )

            assert (await repo.get_by_order_id(o.id)).id in {pay.id, refund.id}
            assert (await repo.get_by_order_and_type(o.id, "pay")).id == pay.id
            assert (await repo.get_by_trade_no("TXN1")).id == pay.id
            assert (await repo.get_by_trade_no("missing")) is None
            assert (await repo.get_by_refund_id("R1")).id == refund.id
            assert (await repo.get_by_refund_id("none")) is None

            lst = await repo.list_by_order_id(o.id)
            assert len(lst) == 2

            items, total = await repo.list_by_user(patient)
            assert total == 2 and len(items) == 2

    async def test_status_history_repo(self):
        async with test_session_factory() as session:
            from app.models.order_status_history import OrderStatusHistory

            order_id = uuid4()
            repo = OrderStatusHistoryRepository(session)
            await repo.create(
                OrderStatusHistory(
                    order_id=order_id,
                    from_status="created",
                    to_status="accepted",
                    changed_by=uuid4(),
                )
            )
            history = await repo.list_by_order_id(order_id)
            assert len(history) == 1


# ---------------------------------------------------------------------------
# ChatMessage repo
# ---------------------------------------------------------------------------
class TestChatMessageRepository:
    async def test_list_and_mark_read(self):
        async with test_session_factory() as session:
            patient = uuid4()
            companion = uuid4()
            hospital = uuid4()
            session.add_all(
                [
                    User(id=patient, phone="13800000050"),
                    User(id=companion, phone="13800000051"),
                    Hospital(id=hospital, name="H"),
                ]
            )
            await session.commit()

            order = await OrderRepository(session).create(
                Order(
                    order_number="YLA0000C",
                    patient_id=patient,
                    companion_id=companion,
                    hospital_id=hospital,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.in_progress,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            chat = ChatMessageRepository(session)
            await chat.create(
                ChatMessage(
                    order_id=order.id,
                    sender_id=patient,
                    type=MessageType.text,
                    content="hi",
                )
            )
            await chat.create(
                ChatMessage(
                    order_id=order.id,
                    sender_id=companion,
                    type=MessageType.text,
                    content="hello",
                )
            )

            items, total = await chat.list_by_order(order.id)
            assert total == 2

            # Patient marks read → only the companion message flips
            updated = await chat.mark_as_read(order.id, patient)
            assert updated == 1


# ---------------------------------------------------------------------------
# User repo
# ---------------------------------------------------------------------------
class TestUserRepository:
    async def test_lookups_and_listing(self):
        async with test_session_factory() as session:
            session.add_all(
                [
                    User(phone="13800000060"),
                    User(wechat_openid="oid_001"),
                ]
            )
            await session.commit()
            repo = UserRepository(session)

            assert (await repo.get_by_phone("13800000060")) is not None
            assert (await repo.get_by_phone("00000000000")) is None
            assert (await repo.get_by_wechat_openid("oid_001")) is not None
            assert (await repo.get_by_wechat_openid("missing")) is None

            users, total = await repo.list_all()
            assert total >= 2


# ---------------------------------------------------------------------------
# Order repo
# ---------------------------------------------------------------------------
class TestOrderRepository:
    async def _seed_basic(self, session):
        patient = uuid4()
        companion = uuid4()
        hospital = uuid4()
        session.add_all(
            [
                User(id=patient, phone=f"138{uuid4().hex[:8]}"),
                User(id=companion, phone=f"138{uuid4().hex[:8]}"),
                Hospital(id=hospital, name="H", city="北京"),
            ]
        )
        await session.commit()
        return patient, companion, hospital

    async def test_list_by_patient_status_list_and_date(self):
        async with test_session_factory() as session:
            p, c, h = await self._seed_basic(session)
            repo = OrderRepository(session)
            await repo.create(
                Order(
                    order_number="YLA00001",
                    patient_id=p,
                    hospital_id=h,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.created,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            await repo.create(
                Order(
                    order_number="YLA00002",
                    patient_id=p,
                    hospital_id=h,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.completed,
                    appointment_date="2026-04-16",
                    appointment_time="09:00",
                    price=100.0,
                )
            )

            # status_list (covers the elif branch path)
            items, total = await repo.list_by_patient(
                p, status_list=[OrderStatus.created]
            )
            assert total == 1

            # status (single)
            items, total = await repo.list_by_patient(p, status=OrderStatus.completed)
            assert total == 1

            # date filter
            items, total = await repo.list_by_patient(p, date="2026-04-15")
            assert total == 1

    async def test_list_by_companion_variants(self):
        async with test_session_factory() as session:
            p, c, h = await self._seed_basic(session)
            repo = OrderRepository(session)
            await repo.create(
                Order(
                    order_number="YLA00003",
                    patient_id=p,
                    companion_id=c,
                    hospital_id=h,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.accepted,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )

            items, total = await repo.list_by_companion(
                c, status_list=[OrderStatus.accepted]
            )
            assert total == 1

            items, total = await repo.list_by_companion(c, status=OrderStatus.accepted)
            assert total == 1

            items, total = await repo.list_by_companion(c, date="2026-04-15")
            assert total == 1

            assert await repo.count_open_by_companion(c) == 1

    async def test_sum_earnings_includes_completed(self):
        async with test_session_factory() as session:
            p, c, h = await self._seed_basic(session)
            repo = OrderRepository(session)
            await repo.create(
                Order(
                    order_number="YLA00004",
                    patient_id=p,
                    companion_id=c,
                    hospital_id=h,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.completed,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=150.0,
                )
            )
            assert await repo.sum_earnings_by_companion(c) == 150.0

    async def test_list_available_with_date_and_city(self):
        async with test_session_factory() as session:
            p, c, h = await self._seed_basic(session)
            repo = OrderRepository(session)
            await repo.create(
                Order(
                    order_number="YLA00005",
                    patient_id=p,
                    hospital_id=h,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.created,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=120.0,
                )
            )
            items, total = await repo.list_available(date="2026-04-15", city="北京")
            assert total == 1

            items, total = await repo.list_available(date="2030-01-01")
            assert total == 0

    async def test_list_expired(self):
        async with test_session_factory() as session:
            p, c, h = await self._seed_basic(session)
            repo = OrderRepository(session)
            past = datetime.now(timezone.utc) - timedelta(hours=1)
            await repo.create(
                Order(
                    order_number="YLA00006",
                    patient_id=p,
                    hospital_id=h,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.created,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                    expires_at=past,
                )
            )
            expired = await repo.list_expired(datetime.now(timezone.utc))
            assert len(expired) == 1

    async def test_has_unpaid_orders(self):
        async with test_session_factory() as session:
            p, c, h = await self._seed_basic(session)
            repo = OrderRepository(session)
            await repo.create(
                Order(
                    order_number="YLA00007",
                    patient_id=p,
                    hospital_id=h,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.created,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            assert await repo.has_unpaid_orders(p) is True

    async def test_get_by_order_number(self):
        async with test_session_factory() as session:
            p, c, h = await self._seed_basic(session)
            repo = OrderRepository(session)
            o = await repo.create(
                Order(
                    order_number="YLA00008",
                    patient_id=p,
                    hospital_id=h,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.created,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            assert (await repo.get_by_order_number("YLA00008")).id == o.id
            assert (await repo.get_by_order_number("nope")) is None

    async def test_list_all_with_filter(self):
        async with test_session_factory() as session:
            p, c, h = await self._seed_basic(session)
            repo = OrderRepository(session)
            await repo.create(
                Order(
                    order_number="YLA00009",
                    patient_id=p,
                    hospital_id=h,
                    service_type=ServiceType.full_accompany,
                    status=OrderStatus.created,
                    appointment_date="2026-04-15",
                    appointment_time="09:00",
                    price=100.0,
                )
            )
            items, total = await repo.list_all()
            assert total >= 1
            items, total = await repo.list_all(status=OrderStatus.created)
            assert total >= 1


# ---------------------------------------------------------------------------
# Base repo: delete
# ---------------------------------------------------------------------------
class TestBaseRepository:
    async def test_get_multi_and_delete(self):
        async with test_session_factory() as session:
            session.add(User(phone="13800000099"))
            await session.commit()
            repo = UserRepository(session)
            users = await repo.get_multi(limit=5)
            assert len(users) >= 1
            await repo.delete(users[0])
            again = await repo.get_by_id(users[0].id)
            assert again is None
