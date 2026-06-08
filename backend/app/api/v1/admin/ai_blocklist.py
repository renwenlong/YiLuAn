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
- 写 admin_audit_logs (target_type=ai_blocklist, target_id=None,
  action=ai_blocklist_viewed, operator=admin_user.id 字串, reason=category_filter or "ALL")
- 同时 incr metric ai_blocklist_viewed_total{admin_id=...}
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.v1.openapi_meta import err
from app.core.admin_jwt import require_admin
from app.dependencies import DBSession
from app.models.admin_audit_log import AdminAuditLog
from app.models.admin_user import AdminUser
from app.services.ai_prep_filter import (
    get_blocklist_snapshot,
    get_blocklist_version,
)

router = APIRouter(prefix="/ai-blocklist", tags=["admin-ai-blocklist"])


def _require_jwt_admin(principal) -> AdminUser:
    """Reject legacy X-Admin-Token sentinel; need admin_user.id for audit_log."""
    admin_user = getattr(principal, "user", None)
    if admin_user is None or getattr(admin_user, "id", None) is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "ai blocklist preview requires admin JWT login "
                "(legacy X-Admin-Token sentinel rejected — audit_log needs admin_user.id)"
            ),
        )
    return admin_user


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
    category: Optional[str] = Query(
        None,
        description="可选: 指定分类只返该分类 (e.g. diagnosis); 不指定返全部",
    ),
    principal=Depends(require_admin),
) -> BlocklistPreviewResponse:
    admin_user = _require_jwt_admin(principal)

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
    category_filter_label = category or "ALL"
    audit = AdminAuditLog(
        target_type="ai_blocklist",
        target_id=None,  # 不指向单条记录 (blocklist 是配置文件)
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
