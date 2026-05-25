"""Telemetry event audit log (observability — frontend funnel + error reporter).

Sink table for ``POST /api/v1/telemetry/events`` (front-end ``utils/logger.report``
channel + ``utils/analytics`` funnel events).

设计要点
--------
* **不含 PII**：``payload`` 只接业务元数据（funnel step、错误 message/stack
  hash、page route 等）。手机号 / 姓名 / 身份证类字段在写入前由 schema
  validator 拒绝（防御性，但前端约束更早）。
* **user_id 可空**：未登录态也允许上报（首页浏览埋点会出现在登录前）。
* **event_type 不做 enum**：前端 funnel + reporter 字符串持续演进，DB 层
  只做长度约束；按需在查询/聚合侧做白名单。
* **client_meta**：env / sdk version / page route 等环境元数据，方便按版本
  / 灰度切片排查。
* **created_at 索引**：admin 列表 + 漏斗按时间聚合。
* 表 TTL：与 ``sms_send_log`` 一致策略，应用层后续可填 ``now() + 30d``，
  由 TD-OPS-02 清理 job 统一回收（本表先不强制，留 ``expires_at`` 列）。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database import Base


class TelemetryEvent(Base):
    """One row per telemetry event (funnel step or warn/error report)."""

    __tablename__ = "telemetry_events"
    __table_args__ = (
        Index("ix_telemetry_events_event_type", "event_type"),
        Index("ix_telemetry_events_created_at", "created_at"),
        Index("ix_telemetry_events_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )
    client_meta: Mapped[dict] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
        default=dict,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "users.id",
            name="fk_telemetry_events_user_id_users",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    client_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debug only
        return (
            f"<TelemetryEvent id={self.id} type={self.event_type!r} "
            f"user_id={self.user_id} ts={self.client_ts}>"
        )
