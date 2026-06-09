"""Prep package schema contract placeholders (ADR-0048 §7).

The migration task introduces the DB-backed contract names so downstream
ABAC / PREP-API tasks can import them. Field-level role projections are
filled by S3-DEV-002-ABAC-4LAYER.
"""

from __future__ import annotations

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PrepStatus(str, Enum):
    pending = "pending"
    generating = "generating"
    active = "active"
    active_fallback_template = "active_fallback_template"
    generation_failed = "generation_failed"


class _BasePrepFields(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")

    id: UUID
    order_id: UUID
    status: PrepStatus
    user_checked_items: list[str] = Field(default_factory=list)


class UserPrepPackageView(_BasePrepFields):
    """Patient view — detailed fields filled by ABAC-4LAYER task."""


class CompanionPrepPackageView(_BasePrepFields):
    """Companion view — red-line projection filled by ABAC-4LAYER task."""


class AdminPrepPackageView(_BasePrepFields):
    """Admin view — ops metadata fields filled by ABAC-4LAYER task."""
