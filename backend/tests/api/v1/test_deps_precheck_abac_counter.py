"""Unit tests for ABAC Layer 2.5 owner-gate Prometheus counter.

Task: `S3-DEV-003-PRECHECK-ABAC-COUNTER` (AC#4)
Metric: ``precheck_abac_filtered_total{endpoint, user_role, filter_reason}``
Counter file: ``backend/app/observability/precheck_abac_metrics.py``
Production site: ``backend/app/api/v1/deps_precheck.py``
  :func:`assert_order_owner_or_404` 2 deny 分支:
    1. ``OwnerCheckFailure`` (order not found) → ``filter_reason=order_not_found``
    2. ``patient_id != user_id`` (ABAC mismatch) → ``filter_reason=abac_owner_mismatch``

测试 3 场景 (cover 全部 deny 分支 + 通过 path):
  1. 通过 path (order 存在 + owner 匹配) → counter NOT increment
  2. order not found → counter +1 with reason=order_not_found
  3. ABAC owner mismatch → counter +1 with reason=abac_owner_mismatch

依赖: prometheus_client Counter 全局 REGISTRY 在 import 时注册一次,
重复 import 复用同一实例 (_get_or_create_counter 防护).
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException

from app.api.v1.deps_precheck import (
    OwnerCheckFailure,
    assert_order_owner_or_404,
)
from app.observability.precheck_abac_metrics import (
    ENDPOINT_PRECHECK_STATUS,
    FILTER_REASON_ABAC_OWNER_MISMATCH,
    FILTER_REASON_ORDER_NOT_FOUND,
    PRECHECK_ABAC_FILTERED_TOTAL,
    USER_ROLE_PATIENT,
)

pytestmark = pytest.mark.asyncio


def _counter_value(counter: Any, **labels: str) -> float:
    """Read a Counter labelset value (works with `prometheus_client` Counter).

    Same pattern as ``backend/tests/cron/test_readonly_flag_real_gate.py``.
    """
    metric = counter.labels(**labels)
    return metric._value.get()  # type: ignore[no-any-return]


def _patch_loader(monkeypatch: pytest.MonkeyPatch, return_value: UUID | None) -> None:
    """Patch ``load_order_owner_id`` to either return a patient_id or raise.

    ``return_value=None`` → raise OwnerCheckFailure (simulate order missing).
    """
    if return_value is None:
        mock_loader = AsyncMock(side_effect=OwnerCheckFailure("order not found"))
    else:
        mock_loader = AsyncMock(return_value=return_value)
    monkeypatch.setattr(
        "app.api.v1.deps_precheck.load_order_owner_id",
        mock_loader,
    )


# ---------------------------------------------------------------------------
# Scenario 1: 通过 path — counter NOT incremented
# ---------------------------------------------------------------------------


async def test_owner_check_pass_does_not_increment_counter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """owner check pass (patient_id == user_id) → no counter increment.

    Either filter_reason label set should stay at the baseline.
    """
    user_id = uuid4()
    order_id = uuid4()

    # patient_id == user_id → owner gate pass
    _patch_loader(monkeypatch, return_value=user_id)

    before_not_found = _counter_value(
        PRECHECK_ABAC_FILTERED_TOTAL,
        endpoint=ENDPOINT_PRECHECK_STATUS,
        user_role=USER_ROLE_PATIENT,
        filter_reason=FILTER_REASON_ORDER_NOT_FOUND,
    )
    before_mismatch = _counter_value(
        PRECHECK_ABAC_FILTERED_TOTAL,
        endpoint=ENDPOINT_PRECHECK_STATUS,
        user_role=USER_ROLE_PATIENT,
        filter_reason=FILTER_REASON_ABAC_OWNER_MISMATCH,
    )

    # Should not raise (pass path).
    await assert_order_owner_or_404(
        session=AsyncMock(),  # loader is patched; raw session unused
        order_id=order_id,
        user_id=user_id,
    )

    after_not_found = _counter_value(
        PRECHECK_ABAC_FILTERED_TOTAL,
        endpoint=ENDPOINT_PRECHECK_STATUS,
        user_role=USER_ROLE_PATIENT,
        filter_reason=FILTER_REASON_ORDER_NOT_FOUND,
    )
    after_mismatch = _counter_value(
        PRECHECK_ABAC_FILTERED_TOTAL,
        endpoint=ENDPOINT_PRECHECK_STATUS,
        user_role=USER_ROLE_PATIENT,
        filter_reason=FILTER_REASON_ABAC_OWNER_MISMATCH,
    )

    assert after_not_found == before_not_found, (
        "pass path 不应 increment order_not_found"
    )
    assert after_mismatch == before_mismatch, (
        "pass path 不应 increment abac_owner_mismatch"
    )


# ---------------------------------------------------------------------------
# Scenario 2: order not found — counter +1 with reason=order_not_found
# ---------------------------------------------------------------------------


async def test_order_not_found_increments_counter_with_correct_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OwnerCheckFailure raised → 404 + counter +1 (order_not_found).

    Other filter_reason label should NOT increment (label isolation).
    """
    user_id = uuid4()
    order_id = uuid4()

    _patch_loader(monkeypatch, return_value=None)  # raise OwnerCheckFailure

    before_not_found = _counter_value(
        PRECHECK_ABAC_FILTERED_TOTAL,
        endpoint=ENDPOINT_PRECHECK_STATUS,
        user_role=USER_ROLE_PATIENT,
        filter_reason=FILTER_REASON_ORDER_NOT_FOUND,
    )
    before_mismatch = _counter_value(
        PRECHECK_ABAC_FILTERED_TOTAL,
        endpoint=ENDPOINT_PRECHECK_STATUS,
        user_role=USER_ROLE_PATIENT,
        filter_reason=FILTER_REASON_ABAC_OWNER_MISMATCH,
    )

    with pytest.raises(HTTPException) as exc:
        await assert_order_owner_or_404(
            session=AsyncMock(),
            order_id=order_id,
            user_id=user_id,
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "order not found"

    after_not_found = _counter_value(
        PRECHECK_ABAC_FILTERED_TOTAL,
        endpoint=ENDPOINT_PRECHECK_STATUS,
        user_role=USER_ROLE_PATIENT,
        filter_reason=FILTER_REASON_ORDER_NOT_FOUND,
    )
    after_mismatch = _counter_value(
        PRECHECK_ABAC_FILTERED_TOTAL,
        endpoint=ENDPOINT_PRECHECK_STATUS,
        user_role=USER_ROLE_PATIENT,
        filter_reason=FILTER_REASON_ABAC_OWNER_MISMATCH,
    )

    assert after_not_found == before_not_found + 1.0, (
        "order_not_found 应 +1"
    )
    assert after_mismatch == before_mismatch, (
        "abac_owner_mismatch 不应 +1 (label 隔离)"
    )


# ---------------------------------------------------------------------------
# Scenario 3: ABAC owner mismatch — counter +1 with reason=abac_owner_mismatch
# ---------------------------------------------------------------------------


async def test_owner_mismatch_increments_counter_with_correct_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """patient_id != user_id → 404 + counter +1 (abac_owner_mismatch).

    Other filter_reason label should NOT increment (label isolation).
    """
    user_id = uuid4()
    other_patient_id = uuid4()
    assert user_id != other_patient_id, "uuid 冲突极小, sanity check"
    order_id = uuid4()

    _patch_loader(monkeypatch, return_value=other_patient_id)

    before_not_found = _counter_value(
        PRECHECK_ABAC_FILTERED_TOTAL,
        endpoint=ENDPOINT_PRECHECK_STATUS,
        user_role=USER_ROLE_PATIENT,
        filter_reason=FILTER_REASON_ORDER_NOT_FOUND,
    )
    before_mismatch = _counter_value(
        PRECHECK_ABAC_FILTERED_TOTAL,
        endpoint=ENDPOINT_PRECHECK_STATUS,
        user_role=USER_ROLE_PATIENT,
        filter_reason=FILTER_REASON_ABAC_OWNER_MISMATCH,
    )

    with pytest.raises(HTTPException) as exc:
        await assert_order_owner_or_404(
            session=AsyncMock(),
            order_id=order_id,
            user_id=user_id,
        )

    assert exc.value.status_code == 404
    assert exc.value.detail == "order not found"

    after_not_found = _counter_value(
        PRECHECK_ABAC_FILTERED_TOTAL,
        endpoint=ENDPOINT_PRECHECK_STATUS,
        user_role=USER_ROLE_PATIENT,
        filter_reason=FILTER_REASON_ORDER_NOT_FOUND,
    )
    after_mismatch = _counter_value(
        PRECHECK_ABAC_FILTERED_TOTAL,
        endpoint=ENDPOINT_PRECHECK_STATUS,
        user_role=USER_ROLE_PATIENT,
        filter_reason=FILTER_REASON_ABAC_OWNER_MISMATCH,
    )

    assert after_mismatch == before_mismatch + 1.0, (
        "abac_owner_mismatch 应 +1"
    )
    assert after_not_found == before_not_found, (
        "order_not_found 不应 +1 (label 隔离)"
    )
