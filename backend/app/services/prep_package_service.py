"""Role-scoped preparation package projections (ABAC Layer 3).

The key invariant is that each public method SELECTs only the columns its
corresponding API view may expose. This is intentionally stronger than
"query the ORM row then let Pydantic filter extras": forbidden fields should
not leave the database layer for that role at all.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundException
from app.models.order import Order
from app.models.preparation_package import PreparationPackage

_COMPANION_SUMMARY = "已生成携带物品摘要，请按用户端完整清单协助准备"


class PrepPackageService:
    """Read-only ABAC projections for preparation packages."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_prep_for_user(self, order_id: UUID, user_id: UUID) -> dict:
        """Return patient-visible fields for an order owned by ``user_id``."""

        stmt = (
            select(
                PreparationPackage.id,
                PreparationPackage.order_id,
                PreparationPackage.status,
                PreparationPackage.user_checked_items,
                PreparationPackage.carry_items,
                PreparationPackage.pre_visit_notes,
                PreparationPackage.possible_questions,
                PreparationPackage.companion_focus_points,
            )
            .join(Order, Order.id == PreparationPackage.order_id)
            .where(
                PreparationPackage.order_id == order_id,
                Order.patient_id == user_id,
            )
        )
        return await self._one_mapping_or_404(stmt)

    async def get_prep_for_companion(self, order_id: UUID, companion_id: UUID) -> dict:
        """Return companion-visible fields for an assigned order.

        Red-line columns deliberately absent from SELECT:
        ``pre_visit_notes``, ``possible_questions``, raw ``carry_items``,
        ``trace_id`` and every admin-only ops field.
        """

        stmt = (
            select(
                PreparationPackage.id,
                PreparationPackage.order_id,
                PreparationPackage.status,
                PreparationPackage.user_checked_items,
                PreparationPackage.companion_focus_points,
                literal(_COMPANION_SUMMARY).label("carry_items_summary"),
            )
            .join(Order, Order.id == PreparationPackage.order_id)
            .where(
                PreparationPackage.order_id == order_id,
                Order.companion_id == companion_id,
            )
        )
        return await self._one_mapping_or_404(stmt)

    async def get_prep_for_admin(self, order_id: UUID) -> dict:
        """Return the full admin projection for any order."""

        stmt = select(
            PreparationPackage.id,
            PreparationPackage.order_id,
            PreparationPackage.status,
            PreparationPackage.user_checked_items,
            PreparationPackage.carry_items,
            PreparationPackage.pre_visit_notes,
            PreparationPackage.possible_questions,
            PreparationPackage.companion_focus_points,
            PreparationPackage.trace_id,
            PreparationPackage.prompt_version_id,
            PreparationPackage.model,
            PreparationPackage.estimated_cost_yuan,
            PreparationPackage.actual_cost_yuan,
            PreparationPackage.generation_time_ms,
            PreparationPackage.fallback_reason,
        ).where(PreparationPackage.order_id == order_id)
        return await self._one_mapping_or_404(stmt)

    async def _one_mapping_or_404(self, stmt) -> dict:
        row = (await self._session.execute(stmt)).mappings().one_or_none()
        if row is None:
            raise NotFoundException("Prep package not found")
        return dict(row)
