import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Enum, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserRole(str, enum.Enum):
    patient = "patient"
    companion = "companion"


class User(Base):
    __tablename__ = "users"

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
    role: Mapped[UserRole | None] = mapped_column(Enum(UserRole), nullable=True)
    roles: Mapped[str | None] = mapped_column(String(50), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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
