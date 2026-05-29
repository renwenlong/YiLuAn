"""Repository for :class:`OrderShareToken` (ADR-0036 §2.3).

Single source of truth for the *cap-3 active tokens per order* invariant.
The helper :meth:`create_with_active_cap` revokes the oldest active token
before inserting the new one so the cap is enforced atomically.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Sequence
from uuid import UUID

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_share_token import (
    ACTIVE_TOKEN_CAP_PER_ORDER,
    OrderShareToken,
    ShareScope,
    compute_expires_at,
    generate_token,
)
from app.repositories.base import BaseRepository


class OrderShareTokenRepository(BaseRepository[OrderShareToken]):
    def __init__(self, session: AsyncSession):
        super().__init__(OrderShareToken, session)

    # -- queries ------------------------------------------------------------

    async def get_by_token(self, token: str) -> OrderShareToken | None:
        stmt = select(OrderShareToken).where(OrderShareToken.token == token)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active_for_order(
        self, order_id: UUID
    ) -> Sequence[OrderShareToken]:
        """Return non-revoked, non-expired tokens for an order, oldest first."""
        now = datetime.now(timezone.utc)
        stmt = (
            select(OrderShareToken)
            .where(
                and_(
                    OrderShareToken.order_id == order_id,
                    OrderShareToken.revoked_at.is_(None),
                    OrderShareToken.expires_at > now,
                )
            )
            .order_by(OrderShareToken.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()

    # -- mutations ----------------------------------------------------------

    async def revoke(
        self,
        token_row: OrderShareToken,
        *,
        revoked_by: UUID | None,
    ) -> OrderShareToken:
        token_row.revoked_at = datetime.now(timezone.utc)
        token_row.revoked_by = revoked_by
        await self.session.flush()
        return token_row

    async def revoke_by_id(
        self,
        token_id: UUID,
        *,
        revoked_by: UUID | None,
    ) -> int:
        """Bulk-revoke a token by id. Returns row-count (0 or 1)."""
        now = datetime.now(timezone.utc)
        stmt = (
            update(OrderShareToken)
            .where(
                OrderShareToken.id == token_id,
                OrderShareToken.revoked_at.is_(None),
            )
            .values(revoked_at=now, revoked_by=revoked_by)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount or 0

    async def create_with_active_cap(
        self,
        *,
        order_id: UUID,
        created_by: UUID,
        order_completed_at: datetime | None,
        share_scope: ShareScope = ShareScope.FULL,
        cap: int = ACTIVE_TOKEN_CAP_PER_ORDER,
    ) -> OrderShareToken:
        """Create a new token; auto-revoke the oldest active when cap is hit.

        ADR-0036 §2.3 invariant: at most ``cap`` (default 3) active tokens
        per order. We *revoke* (not delete) excess tokens so audit / WS
        close-on-revoke (close code 4013) machinery still sees them.
        """
        active = list(await self.list_active_for_order(order_id))
        # Revoke oldest first until we leave exactly cap-1 slots open for
        # the new token.
        to_revoke = max(0, (len(active) + 1) - cap)
        for stale in active[:to_revoke]:
            await self.revoke(stale, revoked_by=created_by)

        now = datetime.now(timezone.utc)
        token = OrderShareToken(
            order_id=order_id,
            created_by=created_by,
            token=generate_token(),
            share_scope=share_scope,
            expires_at=compute_expires_at(
                created_at=now,
                order_completed_at=order_completed_at,
            ),
            created_at=now,
            updated_at=now,
        )
        self.session.add(token)
        await self.session.flush()
        await self.session.refresh(token)
        return token

    async def record_access(
        self,
        token_row: OrderShareToken,
        *,
        accessor_openid: str,
    ) -> OrderShareToken:
        """Update the access aggregate columns on a share-session bootstrap.

        Increments ``distinct_accessor_count`` only when ``accessor_openid``
        differs from previously seen accessors. For MVP we approximate that
        with a single ``first_accessor_openid`` comparison; the precise
        24h-rolling-window distinct count belongs to the S2-DEV-006 scanner
        (which has the bandwidth to scan WS-access logs properly).
        """
        now = datetime.now(timezone.utc)
        if token_row.first_accessed_at is None:
            token_row.first_accessed_at = now
            token_row.first_accessor_openid = accessor_openid
            token_row.distinct_accessor_count = 1
        elif (
            token_row.first_accessor_openid is not None
            and accessor_openid != token_row.first_accessor_openid
        ):
            token_row.distinct_accessor_count = (
                token_row.distinct_accessor_count or 0
            ) + 1
        token_row.last_accessed_at = now
        await self.session.flush()
        return token_row
