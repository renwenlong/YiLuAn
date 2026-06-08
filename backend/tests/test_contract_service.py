"""Tests for S3-DEV-001 ContractService CORE / EVENT-WIRING / PICKUP-CRON.

Final design (魈 08:44 UTC): single ``accept_order`` hook triggers
``ContractService.request_generation``. Payment callback does not touch
contract generation. The contract is a contract-with-companion, so
``companion_id`` is required when request_generation runs.
"""
from __future__ import annotations

import inspect
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.hospital import Hospital
from app.models.order import Order, OrderStatus, ServiceType
from app.models.service_contract import ContractStatus, ServiceContract
from app.services import contract_service as contract_service_module
from app.services.contract_service import (
    MVP_ID_CARD_PLACEHOLDER,
    ContractGenerateNowError,
    ContractRequestGenerationError,
    ContractService,
)
from app.services.contract_storage import ContractStoragePutError, ContractStorageRef
from app.services.storage_backend import StoredObject
from tests.conftest import test_session_factory


async def _create_order(
    session: AsyncSession,
    *,
    with_companion: bool = True,
    patient_name: str = "张三",
    price: Decimal = Decimal("299.00"),
) -> Order:
    hospital = Hospital(name="测试医院", level="三甲", city="上海")
    session.add(hospital)
    await session.flush()

    order = Order(
        order_number=f"O{uuid.uuid4().hex[:10].upper()}",
        patient_id=uuid.uuid4(),
        companion_id=uuid.uuid4() if with_companion else None,
        hospital_id=hospital.id,
        service_type=ServiceType.full_accompany,
        status=OrderStatus.accepted if with_companion else OrderStatus.created,
        appointment_date="2026-06-15",
        appointment_time="14:30",
        price=price,
        service_name_snapshot="全程陪诊",
        service_price_snapshot=price,
        patient_name=patient_name,
    )
    session.add(order)
    await session.flush()
    return order


@pytest.fixture
async def session():
    async with test_session_factory() as s:
        yield s


@pytest.fixture
async def order(session: AsyncSession) -> Order:
    return await _create_order(session)


@pytest.fixture(autouse=True)
def fake_service_package_resolver():
    """ContractService delegates package resolution; keep tests focused."""
    with patch.object(
        contract_service_module,
        "resolve_service_package_id",
        return_value=uuid.uuid4(),
    ) as p:
        yield p


@pytest.fixture
def fake_put_contract():
    calls: list[dict] = []

    def _stub(**kwargs):
        calls.append(kwargs)
        return ContractStorageRef(
            stored=StoredObject(scheme="mock", key="contracts/test.pdf"),
            blob_path=f"contracts/{kwargs['order_id']}_{kwargs['contract_hash']}.pdf",
            contract_hash=kwargs["contract_hash"],
            already_exists=False,
            immutability_applied=False,
        )

    with patch.object(contract_service_module, "put_contract", side_effect=_stub) as p:
        p.calls = calls
        yield p


@pytest.mark.asyncio
async def test_request_generation_creates_pending_row(session: AsyncSession, order: Order):
    svc = ContractService(session)

    result = await svc.request_generation(order.id)

    assert result.created is True
    contract = result.contract
    assert contract.order_id == order.id
    assert contract.status == ContractStatus.pending_generation
    assert contract.template_version == settings.contract_template_version == "v1.0.0"
    assert contract.contract_hash and len(contract.contract_hash) == 64
    assert contract.hash_inputs
    assert contract.storage_blob_path is None


@pytest.mark.asyncio
async def test_request_generation_idempotent_returns_existing(session: AsyncSession, order: Order):
    svc = ContractService(session)

    first = await svc.request_generation(order.id)
    second = await svc.request_generation(order.id)

    assert first.contract.id == second.contract.id
    assert first.created is True
    assert second.created is False
    rows = (await session.execute(select(ServiceContract))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_request_generation_requires_companion(session: AsyncSession):
    order = await _create_order(session, with_companion=False)
    svc = ContractService(session)

    with pytest.raises(ContractRequestGenerationError, match="no companion_id"):
        await svc.request_generation(order.id)


@pytest.mark.asyncio
async def test_id_card_last4_uses_mvp_placeholder(session: AsyncSession, order: Order):
    svc = ContractService(session)
    result = await svc.request_generation(order.id)

    assert MVP_ID_CARD_PLACEHOLDER == "0000"
    assert result.contract.contract_hash


@pytest.mark.asyncio
async def test_generate_now_success_flips_to_active(
    session: AsyncSession, order: Order, fake_put_contract
):
    svc = ContractService(session)
    result = await svc.request_generation(order.id)

    contract = await svc.generate_now(result.contract.id)

    assert contract.status == ContractStatus.active
    assert contract.storage_blob_path
    assert contract.generated_at is not None
    assert len(fake_put_contract.calls) == 1
    assert fake_put_contract.calls[0]["pdf_bytes"].startswith(b"%PDF-")


@pytest.mark.asyncio
async def test_generate_now_put_failure_marks_generation_failed(
    session: AsyncSession, order: Order
):
    svc = ContractService(session)
    result = await svc.request_generation(order.id)

    def _raise(**kwargs):
        raise ContractStoragePutError("simulated storage down", errno_label="OTHER")

    with patch.object(contract_service_module, "put_contract", side_effect=_raise):
        with pytest.raises(ContractGenerateNowError):
            await svc.generate_now(result.contract.id)

    assert result.contract.status == ContractStatus.generation_failed
    assert "simulated" in (result.contract.last_error_trace or "")


@pytest.mark.asyncio
async def test_retry_failed_retries_and_activates(
    session: AsyncSession, order: Order, fake_put_contract
):
    svc = ContractService(session)
    result = await svc.request_generation(order.id)
    result.contract.status = ContractStatus.generation_failed
    result.contract.retry_count = 0
    await session.flush()

    contract = await svc.retry_failed(result.contract.id)

    assert contract.status == ContractStatus.active
    assert contract.retry_count == 1


@pytest.mark.asyncio
async def test_pickup_cron_disabled_noops(session: AsyncSession, order: Order, fake_put_contract):
    from app.cron.contract_generate_pickup import contract_generate_pickup_job

    svc = ContractService(session)
    await svc.request_generation(order.id)

    original = settings.contract_generate_pickup_enabled
    settings.contract_generate_pickup_enabled = False
    try:
        summary = await contract_generate_pickup_job(app=None)
    finally:
        settings.contract_generate_pickup_enabled = original

    assert summary == {"status": "disabled", "processed": 0, "failed": 0}
    assert len(fake_put_contract.calls) == 0


def test_event_wiring_is_accept_order_hook_not_payment_hook():
    """Regression guard for final C2/A decision.

    The hook belongs in accept_order because contract_hash requires
    companion_id. PaymentService must not import ContractService.
    """
    from app.services import payment_service
    from app.services.order import lifecycle

    accept_src = inspect.getsource(lifecycle._OrderLifecycleMixin.accept_order)
    payment_src = inspect.getsource(payment_service.PaymentService)

    assert "ContractService" in accept_src
    assert "request_generation" in accept_src
    assert "ContractService" not in payment_src
    assert "request_generation" not in payment_src
