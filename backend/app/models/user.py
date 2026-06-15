import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# admin_users.id is BigInteger on PG / Integer on SQLite
# (see app.models.admin_user._ID_TYPE). Mirror the variant so the FK type
# matches across both backends and alembic check stays clean.
_ADMIN_ID_TYPE = BigInteger().with_variant(Integer(), "sqlite")


class UserRole(str, enum.Enum):
    patient = "patient"
    companion = "companion"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Partial index: only index rows where is_read_only = TRUE
        # (small subset — gray revoke / compliance / credential-leak).
        # Avoids planner overhead on the 99.9% read-write users while still
        # giving O(log n) admin scans of the read-only cohort.
        # ADR-0053 §5.1.
        Index(
            "ix_users_is_read_only",
            "is_read_only",
            postgresql_where="is_read_only = TRUE",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
    wechat_openid: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True, index=True
    )
    wechat_unionid: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True, index=True
    )
    # Apple Sign-In `sub` claim (Apple's stable user identifier).
    # Nullable + unique: only Apple-linked users have it, but each is unique.
    apple_sub: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True, index=True
    )
    # ------------------------------------------------------------------
    # role model (ADR-0055: has_role() / roles is single SoT)
    # ------------------------------------------------------------------
    # ``role`` enum is **DEPRECATED** as of ADR-0055. Kept for backward
    # compat with historical data and JWT token serialization
    # (``auth.py`` includes ``role`` in token claims), but **must not be
    # read for permission decisions**. New code uses ``has_role()`` and
    # ``add_role()`` exclusively, which work against ``roles`` only.
    role: Mapped[UserRole | None] = mapped_column(Enum(UserRole), nullable=True)
    roles: Mapped[str | None] = mapped_column(String(50), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # ------------------------------------------------------------------
    # read-only flag (ADR-0053 §5.1 / S2-DEV-016-READ-ONLY-FLAG-DB)
    # ------------------------------------------------------------------
    # Authoritative source-of-truth for whether this user's account is in
    # "read-only" mode. When TRUE, every mutating endpoint that depends on
    # ``WriteableUser`` returns 403 ``USER_READONLY``; GET endpoints stay
    # unaffected. Set by admin via ``POST /admin/users/{id}/read-only``
    # (see S2-OPS-A-READ-ONLY-FLAG-ADMIN-API) and persisted to DB so the
    # flag survives logout / token rotation / cache invalidation.
    is_read_only: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False,
        comment=(
            "read-only mode flag; TRUE → mutating endpoints (POST/PUT/DELETE)"
            " return 403 USER_READONLY. ADR-0053 §5.1."
        ),
    )
    # PRD-001 §F8 D2 enum: GRAY_REVOKE | GRAY_ANOMALY | CREDENTIAL_LEAK
    # | COMPLIANCE_REPORT. Frontend maps this to user-facing copy; backend
    # never exposes the raw admin ``reason_detail`` to the user (that lives
    # in ``admin_audit_logs.reason``).
    read_only_reason_category: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
        comment=(
            "UX category mapped by frontend per PRD-001 §F8 D2"
            " (GRAY_REVOKE / GRAY_ANOMALY / CREDENTIAL_LEAK / COMPLIANCE_REPORT)."
            " NULL when is_read_only=FALSE."
        ),
    )
    # Admin free-text reason; **NEVER returned to frontend** per PRD-001 §F8 D1
    # (禁返 detail 原文 避免泄露灰度/凭据/安全/举报方等敷感信息). For internal
    # admin audit / cust-svc query only. Pydantic response schemas MUST exclude
    # this field; only the per-event audit log row in ``admin_audit_logs.reason``
    # is the long-form source of truth (PR #238).
    # ratify 魈 08:14Z r3 + ADR-0053 §5.1 amend PR #296.
    read_only_reason_detail: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment=(
            "Admin free-text reason detail; NEVER returned to frontend per"
            " PRD-001 §F8 D1 (禁返). For internal admin audit / cust-svc query"
            " only. ratify 魈 08:14Z (r3 ADR-0053 §5.1 amend PR #296)."
        ),
    )
    read_only_set_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="UTC timestamp when an admin most recently flipped is_read_only=TRUE.",
    )
    # admin_users.id is BigInt PG / Int SQLite (see _ADMIN_ID_TYPE).
    # ON DELETE SET NULL: deleting an admin account must not orphan the
    # read-only history; the flag/timestamp stay (for audit) but the FK
    # link is cleared. AdminAuditLog still carries operator-username for
    # historical traceability (see PR #238 ``admin_audit_logs.operator``).
    read_only_set_by: Mapped[int | None] = mapped_column(
        _ADMIN_ID_TYPE,
        ForeignKey("admin_users.id", ondelete="SET NULL"),
        nullable=True,
        comment=(
            "FK → admin_users.id; admin who last toggled is_read_only=TRUE."
            " NULL after the admin row is deleted (ON DELETE SET NULL)."
        ),
    )
    # Monotonically increasing counter used to invalidate *all* outstanding
    # access tokens for this user. Bumped by logout-all / password-change /
    # admin-revoke flows. Every JWT we mint embeds the value as the ``v``
    # claim; ``get_current_user`` rejects tokens whose ``v`` is stale.
    token_version: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def has_role(self, r: "UserRole | str") -> bool:
        if not self.roles:
            return False
        val = r.value if isinstance(r, UserRole) else r
        return val in self.roles.split(",")

    def get_roles(self) -> list[str]:
        if not self.roles:
            return []
        return self.roles.split(",")

    def add_role(self, r: UserRole) -> None:
        current = set(self.get_roles())
        current.add(r.value)
        self.roles = ",".join(sorted(current))
