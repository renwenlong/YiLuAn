"""UserAuditService — 用户侧合同/保险审计 service (ADR-0047 §3.5)

3 actions:
- record_contract_acceptance_clicked(user_id, order_id, request, template_version)
- record_contract_viewed(user_id, order_id, request)
- record_insurance_terms_viewed(user_id, order_id, request)

PIPL/民法典电子合同取证:
- user_agent + client_ip 必填
- 缺失 IP 写 "0.0.0.0" + metadata 加 missing_ip=True
- 反代提取真实 IP (X-Forwarded-For / X-Real-IP)
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_audit_log import UserAuditAction, UserAuditLog

# IP 提取兜底值 (PIPL/民法典取证: 缺失也必须写库, 标记 missing_ip=True)
FALLBACK_CLIENT_IP = "0.0.0.0"
FALLBACK_USER_AGENT = "unknown"


def extract_real_client_ip(request: Request) -> tuple[str, bool]:
    """从 FastAPI Request 提取真实客户端 IP (反代支持)

    优先级 (ADR-0047 §3.5):
    1. X-Forwarded-For 首个 IP (反代 chain 左起第一个 = 真实 client)
    2. X-Real-IP (nginx/traefik 单跳反代)
    3. request.client.host (直连)
    4. FALLBACK_CLIENT_IP (兜底, missing_ip=True)

    Returns:
        (client_ip, missing_ip_flag)
    """
    # 1. X-Forwarded-For: 反代 chain (取第一个非空)
    xff = request.headers.get("X-Forwarded-For", "").strip()
    if xff:
        # XFF 格式: "client, proxy1, proxy2" → 取第一个
        first_ip = xff.split(",")[0].strip()
        if first_ip:
            return first_ip, False

    # 2. X-Real-IP: 单跳反代
    xri = request.headers.get("X-Real-IP", "").strip()
    if xri:
        return xri, False

    # 3. 直连 request.client.host
    if request.client and request.client.host:
        return request.client.host, False

    # 4. 兜底 (PIPL 取证仍必须写库, metadata 标记 missing_ip=True)
    return FALLBACK_CLIENT_IP, True


def extract_user_agent(request: Request) -> str:
    """从 Request 提取 User-Agent (缺失兜底 'unknown')"""
    ua = request.headers.get("User-Agent", "").strip()
    return ua if ua else FALLBACK_USER_AGENT


class UserAuditService:
    """用户侧合同/保险审计 service (ADR-0047 §3.5)

    所有 3 actions 必须经此 service 入库,确保:
    - user_agent + client_ip 必填 (反代提取真实 IP)
    - 缺失 IP 不阻断,写 "0.0.0.0" + metadata 加 missing_ip=True
    - admin 操作不进此 service (走 AdminAuditService)
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def _record(
        self,
        *,
        user_id: uuid.UUID,
        order_id: uuid.UUID | None,
        action: UserAuditAction,
        request: Request,
        extra_metadata: dict[str, Any] | None = None,
    ) -> UserAuditLog:
        """内部统一入库点"""
        client_ip, missing_ip = extract_real_client_ip(request)
        user_agent = extract_user_agent(request)

        metadata: dict[str, Any] = dict(extra_metadata or {})
        if missing_ip:
            metadata["missing_ip"] = True

        log = UserAuditLog(
            user_id=user_id,
            order_id=order_id,
            action=action.value,
            audit_metadata=metadata,
            user_agent=user_agent,
            client_ip=client_ip,
        )
        self.session.add(log)
        await self.session.flush()
        return log

    async def record_contract_acceptance_clicked(
        self,
        *,
        user_id: uuid.UUID,
        order_id: uuid.UUID,
        request: Request,
        template_version: str | None = None,
    ) -> UserAuditLog:
        """用户勾选合同同意 (核心取证事件)"""
        extra = {"template_version": template_version} if template_version else {}
        return await self._record(
            user_id=user_id,
            order_id=order_id,
            action=UserAuditAction.contract_acceptance_clicked,
            request=request,
            extra_metadata=extra,
        )

    async def record_contract_viewed(
        self,
        *,
        user_id: uuid.UUID,
        order_id: uuid.UUID,
        request: Request,
    ) -> UserAuditLog:
        """用户查看合同 PDF"""
        return await self._record(
            user_id=user_id,
            order_id=order_id,
            action=UserAuditAction.contract_viewed,
            request=request,
        )

    async def record_insurance_terms_viewed(
        self,
        *,
        user_id: uuid.UUID,
        order_id: uuid.UUID | None,
        request: Request,
    ) -> UserAuditLog:
        """用户查看保障条款 (order_id 可选, 营销页场景无 order)"""
        return await self._record(
            user_id=user_id,
            order_id=order_id,
            action=UserAuditAction.insurance_terms_viewed,
            request=request,
        )
