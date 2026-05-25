"""Telemetry schemas — front-end logger / funnel event ingestion + admin list."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


MAX_JSON_CHARS = 16 * 1024

#: Cheap PII heuristic — reject obvious leaks at the ingest boundary so a
#: misuse on the frontend can't accidentally pipe phone numbers / 身份证
#: into the telemetry table. Frontend has its own scrubber; this is defence
#: in depth.
_PII_PATTERNS = [
    re.compile(r"\b1[3-9]\d{9}\b"),                       # CN mobile (11 digits)
    re.compile(r"\b\d{15}\b|\b\d{17}[\dXx]\b"),           # CN 身份证 (15 / 18)
    re.compile(r"\b\d{16,19}\b"),                         # bank card / long digit runs
]

#: Allowed event_type chars: letters/digits/dot/underscore/dash, 1-64. Matches
#: our ``funnel.<step>`` and ``logger.<level>`` conventions; grep-friendly.
_EVENT_TYPE_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _check_no_pii(blob: Any, *, where: str) -> None:
    if blob is None:
        return
    if isinstance(blob, str):
        for pat in _PII_PATTERNS:
            if pat.search(blob):
                raise ValueError(
                    f"{where} contains PII-like pattern; telemetry must not collect PII"
                )
        return
    if isinstance(blob, dict):
        for k, v in blob.items():
            _check_no_pii(k, where=where)
            _check_no_pii(v, where=where)
        return
    if isinstance(blob, (list, tuple)):
        for item in blob:
            _check_no_pii(item, where=where)
        return


class TelemetryEventCreate(BaseModel):
    """Frontend -> backend telemetry write payload.

    The front-end ``utils/logger.report`` channel and ``utils/analytics``
    funnel emitter both POST this shape.

    * ``event_type``  e.g. ``funnel.order_submit`` or ``logger.error``
    * ``payload``     arbitrary JSON-able metadata (NO PII)
    * ``client_meta`` env / sdk version / page route etc.
    * ``ts``          frontend wall-clock ms; optional, defaults to server now
    """

    event_type: str = Field(
        ...,
        description="事件类型，如 `funnel.order_submit` / `logger.error`",
        examples=["funnel.order_submit"],
    )
    payload: dict[str, Any] = Field(
        default_factory=dict,
        description="业务元数据（不含 PII，size <= 16KB serialized）",
    )
    client_meta: dict[str, Any] = Field(
        default_factory=dict,
        description="客户端环境元数据（env / sdk version / page / scene 等）",
    )
    ts: int | None = Field(
        default=None,
        description="客户端 wall-clock 毫秒（Date.now()），可空 -> 服务端时间",
    )

    @field_validator("event_type")
    @classmethod
    def _validate_event_type(cls, v: str) -> str:
        if not _EVENT_TYPE_RE.match(v):
            raise ValueError("event_type must match ^[A-Za-z0-9._-]{1,64}$")
        return v

    @field_validator("payload")
    @classmethod
    def _validate_payload(cls, v: dict[str, Any]) -> dict[str, Any]:
        import json
        serialized = json.dumps(v, ensure_ascii=False, default=str)
        if len(serialized) > MAX_JSON_CHARS:
            raise ValueError(f"payload too large (> {MAX_JSON_CHARS} chars)")
        _check_no_pii(v, where="payload")
        return v

    @field_validator("client_meta")
    @classmethod
    def _validate_client_meta(cls, v: dict[str, Any]) -> dict[str, Any]:
        import json
        serialized = json.dumps(v, ensure_ascii=False, default=str)
        if len(serialized) > MAX_JSON_CHARS:
            raise ValueError(f"client_meta too large (> {MAX_JSON_CHARS} chars)")
        _check_no_pii(v, where="client_meta")
        return v

    @field_validator("ts")
    @classmethod
    def _validate_ts(cls, v: int | None) -> int | None:
        if v is None:
            return None
        if v < 0:
            raise ValueError("ts must be non-negative")
        if v > 4102444800000:  # 2100-01-01 UTC in ms
            raise ValueError("ts is implausibly large")
        return v


class TelemetryEventAccepted(BaseModel):
    accepted: bool = True


class TelemetryEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_type: str
    payload: dict[str, Any]
    client_meta: dict[str, Any]
    user_id: UUID | None
    client_ts: int | None
    created_at: datetime


class TelemetryEventListResponse(BaseModel):
    items: list[TelemetryEventRead]
    total: int
    limit: int
    offset: int
