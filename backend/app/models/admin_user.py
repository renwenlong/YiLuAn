"""Admin v2 — operator entity (B2 / ADR-0034).

Backed by the ``admin_users`` table; rows here are the source of truth
for ``admin_audit_logs.operator`` once a request is authenticated via
JWT (``require_admin_jwt``). The legacy ``X-Admin-Token`` path keeps
writing ``operator="admin-token"`` for the duration of the W19 double-
track window.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AdminRole(str, enum.Enum):
    super_ = "super"  # python ``super`` is reserved; expose value as "super"
    ops = "ops"
    finance = "finance"


class AdminUser(Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    # bcrypt hash; never logged.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[AdminRole] = mapped_column(
        Enum(
            AdminRole,
            name="admin_role",
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return (
            f"<AdminUser id={self.id} username={self.username!r} "
            f"role={self.role.value} active={self.is_active}>"
        )
