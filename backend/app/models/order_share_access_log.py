"""OrderShareAccessLog model (S2-DEV-006, ADR-0036 §2.4).

Per-access append-only audit row for family-share tokens. Powers the
**24h rolling-window distinct-accessor** anomaly detector — the aggregate
columns on ``OrderShareToken`` (``distinct_accessor_count``) are a cheap
MVP approximation; this table is the precise source of truth the scanner
queries with ``COUNT(DISTINCT accessor_openid) WHERE accessed_at > now-24h``.

Why a separate table (vs more columns on the token row)?
- Rolling-window distinct can't be expressed as a single counter — you
  need the individual (openid, timestamp) tuples to age entries out.
- Append-only writes don't contend with the token row's hot path.
- Doubles as the family-side access audit trail (PRD §F2 compliance).

Retention: rows older than 7d are pruned by the same scanner pass (a
token's hard cap is created_at + 7d, so nothing older can matter).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OrderShareAccessLog(Base):
    """One row per family-view access (REST session bootstrap or WS connect)."""

    __tablename__ = "order_share_access_logs"
    __table_args__ = (
        # Hot query: distinct accessors for a token within a time window.
        Index(
            "ix_share_access_token_time",
            "token_id",
            "accessed_at",
        ),
        # Retention prune scans by time.
        Index("ix_share_access_accessed_at", "accessed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    token_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("order_share_tokens.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    # WeChat openid (or SMS-derived pseudo-openid). The unit of "distinct
    # accessor" — same openid revisiting does NOT count again.
    accessor_openid: Mapped[str] = mapped_column(String(64), nullable=False)
    accessed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
