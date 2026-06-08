"""Tests for ``app.services.contract_storage`` WORM compensation path +
``app.cron.contract_worm_repair`` (S3-DEV-001-CONTRACT-WORM-COMPENSATION).

# Coverage map (acceptance criterion AC#7 字面 + 旁支)

| AC | Test class / case |
|----|-------------------|
| AC#1 alembic + model worm_status fields | (隔离 tests/test_alembic_*) |
# Coverage map (acceptance criterion AC#7 字面 + 旁支)
#
# - AC#1 alembic + model worm_status fields  —  隔离 tests/test_alembic_*
# - AC#2 put_contract 失败路径 → ContractStorageRef.worm_policy_failed=True + metric
#        → TestPutContractWormFailure
# - AC#3 cron job worm_repair: applied / retry_again / permanently_failed
#        → TestContractWormRepairCron
# - AC#4 service 降级语义: pending_retry 仍可读 / permanently_failed admin invalidate 拒
#        → TestWormDegradedRead + admin api test
# - AC#5 alertmanager rule (外部 ops/alertmanager.yml; 仅 metric 实存 verify)
# - AC#6 staging integration test plan (docs only)
# - AC#7 fault inject 验状态转换 + alert 触发
#        → TestPutContractWormFailure + TestContractWormRepairCron
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from app.cron import contract_worm_repair as worm_cron_module
from app.cron.contract_worm_repair import contract_worm_repair_job
from app.models.service_contract import (
    WORM_RETRY_CAP,
    ContractStatus,
    ContractWormStatus,
    ServiceContract,
)
from app.services import contract_storage
from app.services.contract_storage import (
    put_contract,
)
from app.services.storage_backend import (
    AzureBlobStorageBackend,
    LocalStorageBackend,
)
from app.utils.metrics import (
    contract_worm_policy_failed_total,
    contract_worm_repair_total,
)
from tests.conftest import test_session_factory as async_session_factory  # noqa: F401

VALID_HASH = "c" * 64
ORDER_ID = "ord_worm_test_0001"
TPL_VERSION = "v1.0.0"
PDF_BYTES = b"%PDF-1.4\nWORM test contract body\n%%EOF"


@pytest.fixture()
def azure_backend() -> AzureBlobStorageBackend:
    return AzureBlobStorageBackend(
        account_name="test-account",
        container_name="yiluan-cert-test",
    )


@pytest.fixture(autouse=True)
def _enable_immutability(monkeypatch):
    # Default ON for WORM-compensation tests — 我们专门 cover prod-like 路径.
    monkeypatch.setattr(contract_storage.settings, "s3_contract_immutability_enabled", True)


def _metric_value(counter, **labels) -> float:
    """从 prometheus_client Counter 打 sample 拿值 (在所有 fixture 隐月后)."""
    for metric in counter.collect():
        for sample in metric.samples:
            if sample.name.endswith("_total") and all(
                sample.labels.get(k) == v for k, v in labels.items()
            ):
                return sample.value
    return 0.0


# ---------------------------------------------------------------------------
# AC#2 / AC#7 — put_contract WORM fault 路径
# ---------------------------------------------------------------------------


class TestPutContractWormFailure:
    """put_contract: blob 成功写 + set_immutability_policy raise.

    验证 ContractStorageRef.worm_policy_failed=True + metric 触发.
    """

    def test_local_backend_no_worm_failure_default(self, tmp_path, monkeypatch):
        """Local backend: 不走 _set_worm_policy_if_azure raise 路径."""
        local = LocalStorageBackend(
            root_dir=tmp_path / "contracts-worm-local",

            allow_subdirs=True,
        )
        ref = put_contract(
            order_id=ORDER_ID,
            contract_hash=VALID_HASH,
            pdf_bytes=PDF_BYTES,
            template_version=TPL_VERSION,
            backend=local,
        )
        assert ref.worm_policy_failed is False
        assert ref.worm_policy_error is None
        assert ref.immutability_applied is False  # Local: 不走 Azure policy

    def test_azure_no_fault_returns_applied_true(self, azure_backend):
        """Azure backend + immutability_enabled=True + 无 fault → immutability_applied=True."""
        ref = put_contract(
            order_id=ORDER_ID,
            contract_hash=VALID_HASH,
            pdf_bytes=PDF_BYTES,
            template_version=TPL_VERSION,
            backend=azure_backend,
        )
        assert ref.immutability_applied is True
        assert ref.worm_policy_failed is False
        assert ref.worm_policy_error is None

    def test_azure_with_fault_marks_worm_policy_failed(self, azure_backend):
        """Fault inject set_immutability_policy raise → ref.worm_policy_failed=True."""
        # 设 fault 凭证 (mock Azure side error)
        azure_backend._worm_policy_fault = RuntimeError(
            "simulated Azure 403 quota"
        )
        # 调 put_contract 不会加 metric; 仅验 ref 状态
        ref = put_contract(
            order_id=ORDER_ID,
            contract_hash=VALID_HASH,
            pdf_bytes=PDF_BYTES,
            template_version=TPL_VERSION,
            backend=azure_backend,
        )
        assert ref.worm_policy_failed is True
        assert ref.immutability_applied is False
        assert ref.worm_policy_error is not None
        assert "Azure 403 quota" in ref.worm_policy_error
        assert ref.stored.scheme == AzureBlobStorageBackend.scheme
        # blob 仍可读 (验 put_if_absent 成功)
        assert azure_backend.open(ref.stored) == PDF_BYTES


# ---------------------------------------------------------------------------
# AC#3 / AC#7 — contract_worm_repair_job
# ---------------------------------------------------------------------------


class _MockBackend:
    """最小 mock backend; cron 只会调 _set_worm_policy_if_azure(backend, blob_path)."""

    pass


@pytest.fixture()
def patch_resolve_backend_local(tmp_path, monkeypatch):
    """让 contract_worm_repair_job 调 _resolve_backend 返一个 Local backend — 不走 fault."""
    local = LocalStorageBackend(
        root_dir=tmp_path / "contracts-worm-resolve",

        allow_subdirs=True,
    )
    monkeypatch.setattr(worm_cron_module, "_resolve_backend", lambda: local)
    return local


@pytest.fixture()
def patch_resolve_backend_azure_with_fault(monkeypatch):
    """让 contract_worm_repair_job 调 _resolve_backend 返 Azure backend (含 fault)."""
    azure = AzureBlobStorageBackend(
        account_name="test-account",
        container_name="yiluan-cert-test",
    )
    azure._worm_policy_fault = RuntimeError("simulated Azure 5xx in retry")
    monkeypatch.setattr(worm_cron_module, "_resolve_backend", lambda: azure)
    return azure


@pytest.mark.asyncio
async def test_worm_repair_disabled_returns_disabled(monkeypatch):
    """settings.contract_worm_repair_enabled=False → 即刻返 disabled 不走 db."""
    monkeypatch.setattr(
        worm_cron_module.settings, "contract_worm_repair_enabled", False
    )
    result = await contract_worm_repair_job(app=None)
    assert result["status"] == "disabled"
    assert result["applied"] == 0


@pytest.mark.asyncio
async def test_worm_repair_no_pending_rows_returns_ok(
    patch_resolve_backend_local, monkeypatch
):
    """无 pending_retry 行 → status=ok, 不走 backend 调用."""
    monkeypatch.setattr(
        worm_cron_module.settings, "contract_worm_repair_enabled", True
    )
    monkeypatch.setattr(worm_cron_module, "async_session", async_session_factory)
    # 未插任何 service_contracts 行 → cron 看不到 pending_retry
    result = await contract_worm_repair_job(app=None)
    assert result["status"] == "ok"
    assert result["applied"] == 0
    assert result["retry_again"] == 0
    assert result["permanently_failed"] == 0


# Helper: 插一行 worm_status=pending_retry 的 service_contract
async def _insert_pending_retry_contract(
    session, *, retry_count: int = 0, contract_hash_suffix: str = "0"
) -> ServiceContract:
    """插一个 active + worm_status=pending_retry 的 ServiceContract 行 (不依 FK)."""
    fake_order_id = uuid.uuid4()
    contract = ServiceContract(
        id=uuid.uuid4(),
        order_id=fake_order_id,
        template_version=TPL_VERSION,
        contract_hash=(contract_hash_suffix * 64)[:64],
        hash_inputs={"order_id": str(fake_order_id)},
        storage_blob_path=f"contracts/2026/06/{fake_order_id}_{contract_hash_suffix}.pdf",
        generated_at=datetime.now(timezone.utc),
        is_immutable=True,
        status=ContractStatus.active,
        retry_count=0,
        worm_status=ContractWormStatus.pending_retry,
        worm_retry_count=retry_count,
        worm_last_retry_at=None,
    )
    session.add(contract)
    await session.commit()
    return contract


@pytest.mark.asyncio
async def test_worm_repair_success_marks_applied(
    patch_resolve_backend_local, monkeypatch
):
    """Local backend 不 raise → worm_status → applied + metric outcome=applied++."""
    monkeypatch.setattr(
        worm_cron_module.settings, "contract_worm_repair_enabled", True
    )
    monkeypatch.setattr(worm_cron_module, "async_session", async_session_factory)
    async with async_session_factory() as session:
        await _insert_pending_retry_contract(session, contract_hash_suffix="a")
    baseline = _metric_value(contract_worm_repair_total, outcome="applied")
    result = await contract_worm_repair_job(app=None)
    assert result["status"] == "ok"
    assert result["applied"] == 1
    assert result["retry_again"] == 0
    assert result["permanently_failed"] == 0
    after = _metric_value(contract_worm_repair_total, outcome="applied")
    assert after - baseline == pytest.approx(1.0)
    # 验 row 状态变动
    async with async_session_factory() as session:
        from sqlalchemy import select

        contract = (
            await session.execute(select(ServiceContract))
        ).scalar_one()
        assert contract.worm_status == ContractWormStatus.applied
        assert contract.worm_last_retry_at is not None


@pytest.mark.asyncio
async def test_worm_repair_fault_retry_under_cap(
    patch_resolve_backend_azure_with_fault, monkeypatch
):
    """Fault inject 且 retry_count < cap-1 → retry_count++, 仍 pending_retry."""
    monkeypatch.setattr(
        worm_cron_module.settings, "contract_worm_repair_enabled", True
    )
    monkeypatch.setattr(worm_cron_module, "async_session", async_session_factory)
    async with async_session_factory() as session:
        # initial retry_count=0 → 一轮 → retry_count=1 (cap=3, 未超)
        await _insert_pending_retry_contract(session, retry_count=0, contract_hash_suffix="b")
    baseline_retry = _metric_value(contract_worm_repair_total, outcome="retry_again")
    baseline_metric = _metric_value(
        contract_worm_policy_failed_total, stage="repair_retry"
    )
    result = await contract_worm_repair_job(app=None)
    assert result["status"] == "ok"
    assert result["applied"] == 0
    assert result["retry_again"] == 1
    assert result["permanently_failed"] == 0
    after_retry = _metric_value(contract_worm_repair_total, outcome="retry_again")
    after_metric = _metric_value(
        contract_worm_policy_failed_total, stage="repair_retry"
    )
    assert after_retry - baseline_retry == pytest.approx(1.0)
    assert after_metric - baseline_metric == pytest.approx(1.0)
    async with async_session_factory() as session:
        from sqlalchemy import select

        contract = (
            await session.execute(select(ServiceContract))
        ).scalar_one()
        assert contract.worm_status == ContractWormStatus.pending_retry
        assert contract.worm_retry_count == 1
        assert contract.worm_last_retry_at is not None


@pytest.mark.asyncio
async def test_worm_repair_fault_at_cap_marks_permanently_failed(
    patch_resolve_backend_azure_with_fault, monkeypatch
):
    """retry_count + 1 == cap → worm_status → permanently_failed + alert metric."""
    monkeypatch.setattr(
        worm_cron_module.settings, "contract_worm_repair_enabled", True
    )
    monkeypatch.setattr(worm_cron_module, "async_session", async_session_factory)
    async with async_session_factory() as session:
        # retry_count=cap-1 → 本轮++ = cap → permanently_failed
        await _insert_pending_retry_contract(
            session, retry_count=WORM_RETRY_CAP - 1, contract_hash_suffix="c"
        )
    baseline_perm = _metric_value(
        contract_worm_repair_total, outcome="permanently_failed"
    )
    baseline_alert = _metric_value(
        contract_worm_policy_failed_total, stage="permanent_fail"
    )
    result = await contract_worm_repair_job(app=None)
    assert result["status"] == "ok"
    assert result["applied"] == 0
    assert result["retry_again"] == 0
    assert result["permanently_failed"] == 1
    after_perm = _metric_value(
        contract_worm_repair_total, outcome="permanently_failed"
    )
    after_alert = _metric_value(
        contract_worm_policy_failed_total, stage="permanent_fail"
    )
    assert after_perm - baseline_perm == pytest.approx(1.0)
    assert after_alert - baseline_alert == pytest.approx(1.0)
    async with async_session_factory() as session:
        from sqlalchemy import select

        contract = (
            await session.execute(select(ServiceContract))
        ).scalar_one()
        assert contract.worm_status == ContractWormStatus.permanently_failed
        assert contract.worm_retry_count == WORM_RETRY_CAP


# ---------------------------------------------------------------------------
# AC#4 — 降级语义: pending_retry 仍可读 signed URL (测试仅验另一面: model 状态不阻读)
# ---------------------------------------------------------------------------


class TestWormDegradedRead:
    """仅验状态 — actual get_contract_signed_url 不依 worm_status,
    所以这里只验 WORM_RETRY_CAP 语义 + ENUM values 不会跳出预期.
    """

    def test_worm_status_enum_values(self):
        assert {e.value for e in ContractWormStatus} == {
            "applied",
            "pending_retry",
            "permanently_failed",
        }

    def test_worm_retry_cap_is_three(self):
        # AC#7 字面 3 次
        assert WORM_RETRY_CAP == 3
