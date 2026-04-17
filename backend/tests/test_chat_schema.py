"""聊天消息 schema 边界测试。

保证 REST 发送接口的上限与 WebSocket 通道（/ws/chat/{order_id}）保持一致（4000 字符）。
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.chat import SendMessageRequest


def test_content_min_length_rejects_empty():
    with pytest.raises(ValidationError):
        SendMessageRequest(content="", type="text")


def test_content_exactly_4000_accepted():
    SendMessageRequest(content="x" * 4000, type="text")


def test_content_over_4000_rejected():
    with pytest.raises(ValidationError):
        SendMessageRequest(content="x" * 4001, type="text")


def test_type_must_be_allowed():
    # 白名单：text / image / system
    SendMessageRequest(content="hi", type="text")
    SendMessageRequest(content="hi", type="image")
    SendMessageRequest(content="hi", type="system")
    with pytest.raises(ValidationError):
        SendMessageRequest(content="hi", type="evil")
