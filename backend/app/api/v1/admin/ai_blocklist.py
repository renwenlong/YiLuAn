"""Admin AI blocklist read-only API (S3-DEV-002-KEYWORD-FILTER).

ADR-0048 §4.1: admin-v2 ``/ai/blocklist`` 页 read-only.

# 唯一端点
GET /api/v1/admin/ai-blocklist/preview
  query: ?category=<optional category filter>
  返: {version, categories: [{category, description, patterns: [...]}]}

# 鉴权要求
- 必须 JWT principal (AdminUser); 写 admin_audit_logs 需 admin_user.id

# 设计 (ADR-0048 §4.1 前后端双层禁编辑)
- 不存在 POST/PUT/DELETE 等编辑端点 (API 层禁编辑)
- 真要编辑: 走 PR + 医疗顾问 review, 不允许 admin 后台直改
- 任何 admin 查看入 audit_log: action=ai_blocklist_viewed + admin_id + category_filter

# 审计
- 写 admin_audit_logs (target_type=ai_blocklist, target_id=_CONFIG_TARGET sentinel,
  action=ai_blocklist_viewed, operator=admin_user.id 字串, reason=category_filter or "ALL")
- 同时 incr metric ai_blocklist_viewed_total{admin_id=...}
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel, Field

from app.api.v1.openapi_meta import err
from app.dependencies import CurrentAdmin, DBSession
from app.models.admin_audit_log import AdminAuditLog
from app.services.ai_blocklist_pubsub import AI_BLOCKLIST_RELOAD_CHANNEL
from app.services.ai_prep_filter import (
    get_blocklist_snapshot,
    get_blocklist_version,
)

router = APIRouter(prefix="/ai-blocklist", tags=["admin-ai-blocklist"])

# S3-BUG-002 fix (2026-06-10): 使用 CurrentAdmin pattern 对齐 cache_invalidate.py.
# 原 _require_jwt_admin helper 假设 principal.user 取 AdminUser, 但 require_admin
# 直接返 AdminUser 实例 — 永远 403. CurrentAdmin = Annotated[AdminUser,
# Depends(get_current_admin)] 在 app/dependencies.py:152 定义, 与 require_admin_jwt
# 等价, 拒 X-Admin-Token sentinel.

# S3-BUG-002 fix (2026-06-10): admin_audit_logs.target_id 是 NOT NULL UUID.
# ai_blocklist 是配置文件 (无单条资源 UUID), 复用 orders.py:316 已有的
# sentinel pattern (UUID("00000000-0000-0000-0000-000000000000")) 标识
# "面向整体配置的操作, 非单条资源".
_CONFIG_TARGET = UUID("00000000-0000-0000-0000-000000000000")


class BlocklistCategoryItem(BaseModel):
    category: str = Field(..., description="分类标识")
    description: str = Field("", description="分类说明")
    patterns: list[str] = Field(default_factory=list, description="模式 list (大小写不敏感子串)")
    pattern_count: int = Field(0, description="该分类 pattern 数")


class BlocklistPreviewResponse(BaseModel):
    version: str = Field(..., description="yml 版本号")
    categories: list[BlocklistCategoryItem] = Field(default_factory=list)
    total_patterns: int = Field(0, description="所有分类 pattern 数总和")
    note: str = Field(
        default=(
            "此页 read-only。修改请走 PR + 医疗顾问 review approve 后合 main "
            "(ADR-0048 §4.1)。后端无 POST/PUT/DELETE endpoint。"
        ),
    )


@router.get(
    "/preview",
    response_model=BlocklistPreviewResponse,
    summary="查看 AI 双层关键词过滤 blocklist (read-only)",
    description=(
        "ADR-0048 §4.1 admin-v2 关键词查看页:\n"
        "- read-only — 不允许 admin 后台直改, 修改走 PR + 医疗顾问 review\n"
        "- 任何 admin 调用写 admin_audit_logs action=ai_blocklist_viewed\n"
        "- 同时 incr metric ai_blocklist_viewed_total{admin_id=...}\n"
        "- query category 可过滤单个分类, 不带返全部 6 大分类"
    ),
    responses={**err(401, 403, 500)},
)
async def preview_blocklist(
    session: DBSession,
    admin_user: CurrentAdmin,
    category: Optional[str] = Query(
        None,
        description="可选: 指定分类只返该分类 (e.g. diagnosis); 不指定返全部",
    ),
) -> BlocklistPreviewResponse:
    snapshot = get_blocklist_snapshot()
    version = get_blocklist_version()

    # 过滤 category
    if category:
        snapshot = tuple(e for e in snapshot if e.category == category)

    categories = [
        BlocklistCategoryItem(
            category=e.category,
            description=e.description,
            patterns=list(e.patterns),
            pattern_count=len(e.patterns),
        )
        for e in snapshot
    ]

    total = sum(c.pattern_count for c in categories)

    # 审计 admin_audit_logs (ADR-0048 §4.1 强约束)
    # S3-BUG-002 fix: target_id 用 _CONFIG_TARGET sentinel (参见模块顶 notes).
    category_filter_label = category or "ALL"
    audit = AdminAuditLog(
        target_type="ai_blocklist",
        target_id=_CONFIG_TARGET,
        action="ai_blocklist_viewed",
        operator=str(admin_user.id),
        reason=f"category_filter={category_filter_label}",
    )
    session.add(audit)
    await session.flush()
    await session.commit()

    # Metric (admin_id 不入 label cardinality 上限; admin 数 << 100)
    try:
        from app.utils.metrics import ai_blocklist_viewed_total

        ai_blocklist_viewed_total.labels(admin_id=str(admin_user.id)).inc()
    except Exception:  # pragma: no cover
        pass

    return BlocklistPreviewResponse(
        version=version,
        categories=categories,
        total_patterns=total,
    )


class BlocklistReloadResponse(BaseModel):
    accepted: bool = Field(True, description="固定 True; 实际 reload 是异步")
    channel: str = Field(..., description="Redis pub/sub channel name (供 debug)")
    triggered_by_admin_id: str = Field(..., description="触发者 admin id")
    note: str = Field(
        default=(
            "该接口仅发出 reload 事件; 各副本实际在后台 subscriber 处理, "
            "需 5s 内留意。用 /admin/ai-blocklist/debug-version 验证各副本生效。"
        ),
    )


@router.post(
    "/reload",
    response_model=BlocklistReloadResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="触发 AI 关键词黑名单 hot reload (异步, 多副本 ≤5s)",
    description=(
        "S3-DEV-002-HOT-RELOAD (ADR-0048 §4.1 + 刻晴 review #5).\n"
        "admin 修改 docs/medical-content/prohibited-keywords.yml (走 PR + 医疗顾问"
        " review approve + merge main) 后, 调此接口 publish reload 事件 → "
        "所有 backend 副本 subscriber 收事件 → load_blocklist() 重 init cache.\n"
        "“不会” 等待传播: 返 202 Accepted, 各副本 ≤5s 内生效 (PRD-003 v0.3 §7).\n"
        "审计: admin_audit_logs action=ai_blocklist_reload + admin_id; "
        "metric ai_blocklist_reload_triggered_total{admin_id} incr."
    ),
    responses={**err(401, 403, 500)},
)
async def trigger_blocklist_reload(
    request: Request,
    session: DBSession,
    admin_user: CurrentAdmin,
) -> BlocklistReloadResponse:
    # 写 admin_audit_logs
    # S3-BUG-002 fix: target_id 用 _CONFIG_TARGET sentinel (参见模块顶 notes)
    audit = AdminAuditLog(
        target_type="ai_blocklist",
        target_id=_CONFIG_TARGET,
        action="ai_blocklist_reload",
        operator=str(admin_user.id),
        reason=f"trigger reload via redis pub/sub channel={AI_BLOCKLIST_RELOAD_CHANNEL}",
    )
    session.add(audit)
    await session.flush()
    await session.commit()

    # Metric
    try:
        from app.utils.metrics import ai_blocklist_reload_triggered_total

        ai_blocklist_reload_triggered_total.labels(admin_id=str(admin_user.id)).inc()
    except Exception:  # pragma: no cover
        pass

    # Publish to redis (best-effort; 失败 不 aborts 响应, 但等于 cold fallback)
    from datetime import datetime, timezone

    payload = {
        "version": get_blocklist_version() or "unknown",
        "triggered_by_admin_id": str(admin_user.id),
        "triggered_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        rds = getattr(request.app.state, "redis", None)
        if rds is not None:
            import json as _json

            await rds.publish(AI_BLOCKLIST_RELOAD_CHANNEL, _json.dumps(payload))
    except Exception as exc:  # pragma: no cover - 不阻响应, log
        import logging

        logging.getLogger(__name__).warning(
            "ai-blocklist reload publish failed (cold fallback): %s", exc
        )

    return BlocklistReloadResponse(
        accepted=True,
        channel=AI_BLOCKLIST_RELOAD_CHANNEL,
        triggered_by_admin_id=str(admin_user.id),
    )


class BlocklistDebugVersionResponse(BaseModel):
    instance: str = Field(..., description="backend 副本标识 (HOSTNAME 或 socket.gethostname)")
    version: str = Field(..., description="当前副本读到的 yml version")
    categories: int = Field(0, description="当前副本读到的分类数")
    total_patterns: int = Field(0, description="当前副本读到的 pattern 总数")


@router.get(
    "/debug-version",
    response_model=BlocklistDebugVersionResponse,
    summary="返本副本当前读到的 blocklist version (验 reload 传播)",
    description=(
        "S3-DEV-002-HOT-RELOAD 验证端点. PRD-003 v0.3 §7 灰度监控: "
        "两副本 admin trigger reload 后 5s 内, 各调此接口均返新 version.\n"
        "不会写 audit_log (仅技术 debug 入口, 低成本调 OK)."
    ),
    responses={**err(401, 403)},
)
async def debug_blocklist_version(
    admin_user: CurrentAdmin,  # noqa: ARG001 — enforce JWT admin (S3-BUG-002 fix), debug 不写 audit
) -> BlocklistDebugVersionResponse:
    from app.services.ai_blocklist_pubsub import get_instance_id

    snap = get_blocklist_snapshot()
    return BlocklistDebugVersionResponse(
        instance=get_instance_id(),
        version=get_blocklist_version(),
        categories=len(snap),
        total_patterns=sum(len(e.patterns) for e in snap),
    )
