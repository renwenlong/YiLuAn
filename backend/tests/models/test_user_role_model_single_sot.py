"""Regression: ADR-0055 user role model converge.

S3-OPS-USER-ROLE-MODEL-CONVERGE-PHASE2-IMPL — verifies the single
source-of-truth contract for user roles:

1. ``add_role(X)`` only mutates ``roles`` (deprecated ``role`` enum
   field remains untouched, per ADR-0055 \u00a73.1.3).
2. ``has_role(X)`` reads exclusively from ``roles`` (multi-role string),
   even when ``role`` enum is set.
3. ``get_current_patient`` / ``get_current_companion`` no longer use
   the dual check; legacy users with ``role=X`` but ``roles=NULL`` get
   403 unless the backfill migration has run.

Companion to migration ``a07229409127_s3_ops_user_role_model_converge_phase2_``.
"""
from __future__ import annotations

import pytest

from app.exceptions import ForbiddenException
from app.models.user import User, UserRole
from tests.conftest import test_session_factory as _session_factory


@pytest.mark.asyncio
async def test_add_role_updates_roles_field_only() -> None:
    """``add_role`` writes only to ``roles``; ``role`` enum stays NULL."""
    async with _session_factory() as session:
        user = User(phone="+8613800000001")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        assert user.role is None
        assert user.roles is None
        assert user.has_role(UserRole.patient) is False

        user.add_role(UserRole.patient)
        await session.commit()
        await session.refresh(user)

        # ADR-0055: enum field is not mutated by add_role()
        assert user.role is None
        assert user.roles == "patient"
        assert user.has_role(UserRole.patient) is True


@pytest.mark.asyncio
async def test_dual_role_supported() -> None:
    """One user can carry both patient + companion roles via has_role()."""
    async with _session_factory() as session:
        user = User(phone="+8613800000002")
        user.add_role(UserRole.patient)
        user.add_role(UserRole.companion)
        session.add(user)
        await session.commit()
        await session.refresh(user)

        assert user.has_role(UserRole.patient) is True
        assert user.has_role(UserRole.companion) is True
        assert set(user.get_roles()) == {"patient", "companion"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role_enum_val, roles_str, expect_patient_pass, expect_companion_pass",
    [
        # legacy: enum set but roles NULL.
        # Under ADR-0055 single SoT, the dependency no longer reads enum,
        # so these users would 403 until the backfill migration runs.
        (UserRole.patient, None, False, False),
        (UserRole.companion, None, False, False),
        # new: enum NULL, roles set — happy path
        (None, "patient", True, False),
        (None, "companion", False, True),
        # multi-role string
        (None, "patient,companion", True, True),
        # mixed: enum set + roles set; has_role respects roles only
        (UserRole.patient, "companion", False, True),
    ],
)
async def test_get_current_patient_companion_uses_has_role_only(
    role_enum_val: UserRole | None,
    roles_str: str | None,
    expect_patient_pass: bool,
    expect_companion_pass: bool,
) -> None:
    """``get_current_patient`` / ``get_current_companion`` read only ``roles``."""
    from app.dependencies import get_current_companion, get_current_patient

    user = User(
        phone="+861380000" + str(hash((role_enum_val, roles_str)) % 1000000).zfill(6),
        role=role_enum_val,
        roles=roles_str,
    )

    # get_current_patient
    if expect_patient_pass:
        result = await get_current_patient(current_user=user)
        assert result is user
    else:
        with pytest.raises(ForbiddenException):
            await get_current_patient(current_user=user)

    # get_current_companion
    if expect_companion_pass:
        result = await get_current_companion(current_user=user)
        assert result is user
    else:
        with pytest.raises(ForbiddenException):
            await get_current_companion(current_user=user)
