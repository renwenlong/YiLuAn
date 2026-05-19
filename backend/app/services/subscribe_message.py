"""F-07: SubscribeMessageProvider abstraction.

本项目所有微信订阅消息 / iOS APNs / SMS 派送都应走 Provider 接口。

今天只交付 ``StubSubscribeMessageProvider`` — 实现为“写日志 +
返回 success”，以便 cron 与 tests 可以走通。

微信模板审批通过后，``WechatSubscribeMessageProvider`` 会到
``backend/app/services/wechat_subscribe.py`` 下实现并在启动时按
``settings.WECHAT_SUBSCRIBE_PROVIDER`` 选择接入。

返回类型：
* ``ProviderResult.success`` + ``message_id`` → 标记提醒 sent
* ``ProviderResult.failure`` + ``error`` → 计入 attempts，达到 MAX_ATTEMPTS
  后锁定为 failed
"""

from __future__ import annotations

import abc
import logging
import uuid
from dataclasses import dataclass


logger = logging.getLogger(__name__)


@dataclass
class ProviderResult:
    success: bool
    message_id: str | None = None
    error: str | None = None


@dataclass
class FollowupReminderPayload:
    """Provider-agnostic payload for a follow-up reminder send."""

    user_id: uuid.UUID
    order_id: uuid.UUID
    note: str | None
    # 预留：后续接 wechat 时 hospital_name / appointment_date 可以加进来


class SubscribeMessageProvider(abc.ABC):
    name: str = "abstract"

    @abc.abstractmethod
    async def send(self, payload: FollowupReminderPayload) -> ProviderResult: ...


class StubSubscribeMessageProvider(SubscribeMessageProvider):
    """默认 provider — 打日志，返回静态 message_id。

    适用于本地开发 / CI 及“微信模板未批”阶段。
    """

    name = "stub"

    async def send(self, payload: FollowupReminderPayload) -> ProviderResult:
        logger.info(
            "stub-subscribe-send order=%s user=%s note=%s",
            payload.order_id,
            payload.user_id,
            payload.note or "",
        )
        return ProviderResult(success=True, message_id=f"stub:{payload.order_id}")


# 运行时单例：在 cron / API 中直接 import 该变量使用。
_current_provider: SubscribeMessageProvider = StubSubscribeMessageProvider()


def get_subscribe_provider() -> SubscribeMessageProvider:
    return _current_provider


def set_subscribe_provider(provider: SubscribeMessageProvider) -> None:
    """测试/启动时可注入替代实现（如 在微信模板审批后切到 Wechat impl）。"""
    global _current_provider
    _current_provider = provider
