"""Admin Notes & Order Timeline — CS / ops collaboration surface (B).

Routes:
- /api/v1/admin/orders/{order_id}/timeline   GET    (status_history view)
- /api/v1/admin/notes                         POST   create note
- /api/v1/admin/notes                         GET    list by target
- /api/v1/admin/notes/{note_id}               PATCH  edit (author only)
- /api/v1/admin/notes/{note_id}               DELETE remove (audited)

Notes are stored via (target_type, target_id) so the same endpoint serves
orders, users, companions, etc. Every mutation also writes an AdminAuditLog
row so a security reviewer can answer "who wrote / changed / deleted what
about this user/order".
"""

from __future__ import annotations

from datetime import datetime
from typing import Sequence
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.admin_jwt import admin_operator_id, require_admin
from app.dependencies import DBSession
from app.exceptions import ForbiddenException, NotFoundException
from app.models.admin_audit_log import AdminAuditLog
from app.models.admin_note import AdminNote
from app.models.order_status_history import OrderStatusHistory


# ---------------------------------------------------------------------------
# Order timeline (read-only view on order_status_history)
# ---------------------------------------------------------------------------

timeline_router = APIRouter(
    prefix="/orders",
    tags=["admin-order-timeline"],
    dependencies=[Depends(require_admin)],
)


class TimelineEntry(BaseModel):
    id: UUID
    from_status: str | None
    to_status: str
    changed_by: UUID
    note: str | None
    created_at: datetime


class OrderTimeline(BaseModel):
    order_id: UUID
    entries: list[TimelineEntry]


@timeline_router.get(
    "/{order_id}/timeline",
    response_model=OrderTimeline,
    summary="后台：订单状态变迁时间轴",
)
async def get_order_timeline(
    order_id: UUID,
    session: DBSession,
) -> OrderTimeline:
    rows: Sequence[OrderStatusHistory] = (
        await session.execute(
            select(OrderStatusHistory)
            .where(OrderStatusHistory.order_id == order_id)
            .order_by(OrderStatusHistory.created_at.asc())
        )
    ).scalars().all()
    return OrderTimeline(
        order_id=order_id,
        entries=[
            TimelineEntry(
                id=r.id,
                from_status=r.from_status,
                to_status=r.to_status,
                changed_by=r.changed_by,
                note=r.note,
                created_at=r.created_at,
            )
            for r in rows
        ],
    )


# ---------------------------------------------------------------------------
# Notes CRUD
# ---------------------------------------------------------------------------

notes_router = APIRouter(
    prefix="/notes",
    tags=["admin-notes"],
    dependencies=[Depends(require_admin)],
)

_ALLOWED_TARGETS = {"order", "user", "companion"}


class NoteCreate(BaseModel):
    target_type: str = Field(..., min_length=1, max_length=50)
    target_id: UUID
    body: str = Field(..., min_length=1, max_length=5000)


class NotePatch(BaseModel):
    body: str = Field(..., min_length=1, max_length=5000)


class NoteItem(BaseModel):
    id: UUID
    target_type: str
    target_id: UUID
    operator: str
    body: str
    created_at: datetime
    updated_at: datetime


class NoteList(BaseModel):
    items: list[NoteItem]
    total: int


def _to_item(n: AdminNote) -> NoteItem:
    return NoteItem(
        id=n.id,
        target_type=n.target_type,
        target_id=n.target_id,
        operator=n.operator,
        body=n.body,
        created_at=n.created_at,
        updated_at=n.updated_at,
    )


@notes_router.get(
    "",
    response_model=NoteList,
    summary="后台：按 target 列出备注",
)
async def list_notes(
    session: DBSession,
    target_type: str = Query(..., min_length=1, max_length=50),
    target_id: UUID = Query(...),
    limit: int = Query(100, ge=1, le=500),
) -> NoteList:
    rows = (
        await session.execute(
            select(AdminNote)
            .where(
                AdminNote.target_type == target_type,
                AdminNote.target_id == target_id,
            )
            .order_by(AdminNote.created_at.desc())
            .limit(limit)
        )
    ).scalars().all()
    return NoteList(items=[_to_item(n) for n in rows], total=len(rows))


@notes_router.post(
    "",
    response_model=NoteItem,
    summary="后台：新增备注",
)
async def create_note(
    body: NoteCreate,
    session: DBSession,
    operator: str = Depends(admin_operator_id),
) -> NoteItem:
    if body.target_type not in _ALLOWED_TARGETS:
        raise ForbiddenException(
            f"target_type must be one of {sorted(_ALLOWED_TARGETS)}"
        )
    note = AdminNote(
        target_type=body.target_type,
        target_id=body.target_id,
        operator=operator,
        body=body.body,
    )
    session.add(note)
    session.add(
        AdminAuditLog(
            target_type=body.target_type,
            target_id=body.target_id,
            action="add_note",
            operator=operator,
            reason=body.body[:200],
        )
    )
    await session.flush()
    return _to_item(note)


@notes_router.patch(
    "/{note_id}",
    response_model=NoteItem,
    summary="后台：编辑备注（仅作者）",
)
async def update_note(
    note_id: UUID,
    body: NotePatch,
    session: DBSession,
    operator: str = Depends(admin_operator_id),
) -> NoteItem:
    note = await session.get(AdminNote, note_id)
    if note is None:
        raise NotFoundException("Note not found")
    if note.operator != operator:
        raise ForbiddenException("only the note author may edit")
    note.body = body.body
    session.add(
        AdminAuditLog(
            target_type=note.target_type,
            target_id=note.target_id,
            action="edit_note",
            operator=operator,
            reason=body.body[:200],
        )
    )
    await session.flush()
    return _to_item(note)


@notes_router.delete(
    "/{note_id}",
    summary="后台：删除备注（仅作者）",
)
async def delete_note(
    note_id: UUID,
    session: DBSession,
    operator: str = Depends(admin_operator_id),
) -> dict:
    note = await session.get(AdminNote, note_id)
    if note is None:
        raise NotFoundException("Note not found")
    if note.operator != operator:
        raise ForbiddenException("only the note author may delete")
    session.add(
        AdminAuditLog(
            target_type=note.target_type,
            target_id=note.target_id,
            action="delete_note",
            operator=operator,
            reason=f"deleted note {note.id}",
        )
    )
    await session.delete(note)
    await session.flush()
    return {"deleted": True, "id": str(note_id)}
