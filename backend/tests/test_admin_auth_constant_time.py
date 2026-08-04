"""S3-SEC-ADMIN-TOKEN-CONSTANT-TIME — admin token 常量时间比较测试.

验证 require_admin_token / require_admin_operator 用 secrets.compare_digest
做常量时间比对, 行为与旧 ``!=`` 明文比较等价:
  - 正确 token 通过
  - 错误 token 拒绝 (UnauthorizedException)
  - operator header 1-64 char 校验不变
"""
from __future__ import annotations

import pytest

from app.core import admin_auth
from app.core.admin_auth import (
    _admin_token_valid,
    require_admin_operator,
    require_admin_token,
)
from app.exceptions import BadRequestException, UnauthorizedException


@pytest.fixture
def _token(monkeypatch):
    monkeypatch.setattr(
        "app.core.admin_auth.settings.admin_api_token", "s3cr3t-admin-token"
    )
    return "s3cr3t-admin-token"


# --- _admin_token_valid (constant-time compare) -----------------------------


def test_admin_token_valid_true(_token):
    assert _admin_token_valid("s3cr3t-admin-token") is True


@pytest.mark.parametrize(
    "candidate",
    [
        "wrong",
        "s3cr3t-admin-toke",  # one byte short
        "s3cr3t-admin-tokenX",  # one byte long
        "",
        "S3CR3T-ADMIN-TOKEN",  # case differs
    ],
)
def test_admin_token_valid_false(_token, candidate):
    assert _admin_token_valid(candidate) is False


def test_admin_token_valid_uses_compare_digest(monkeypatch, _token):
    """Guard: implementation must route through secrets.compare_digest
    (constant-time), not a plain ==/!=."""
    calls = {}

    real = admin_auth.secrets.compare_digest

    def _spy(a, b):
        calls["hit"] = True
        return real(a, b)

    monkeypatch.setattr(admin_auth.secrets, "compare_digest", _spy)
    _admin_token_valid("s3cr3t-admin-token")
    assert calls.get("hit") is True


def test_admin_token_valid_none_expected(monkeypatch):
    """Empty/None configured token never matches a non-empty candidate
    (no crash on None)."""
    monkeypatch.setattr("app.core.admin_auth.settings.admin_api_token", None)
    assert _admin_token_valid("anything") is False


# --- require_admin_token ----------------------------------------------------


@pytest.mark.asyncio
async def test_require_admin_token_accepts(_token):
    assert await require_admin_token(x_admin_token=_token) == _token


@pytest.mark.asyncio
async def test_require_admin_token_rejects(_token):
    with pytest.raises(UnauthorizedException):
        await require_admin_token(x_admin_token="nope")


# --- require_admin_operator -------------------------------------------------


@pytest.mark.asyncio
async def test_require_admin_operator_accepts(_token):
    op = await require_admin_operator(
        x_admin_token=_token, x_admin_operator="alice"
    )
    assert op == "alice"


@pytest.mark.asyncio
async def test_require_admin_operator_rejects_bad_token(_token):
    with pytest.raises(UnauthorizedException):
        await require_admin_operator(
            x_admin_token="nope", x_admin_operator="alice"
        )


@pytest.mark.asyncio
async def test_require_admin_operator_requires_operator(_token):
    with pytest.raises(BadRequestException):
        await require_admin_operator(x_admin_token=_token, x_admin_operator="")


@pytest.mark.asyncio
async def test_require_admin_operator_operator_too_long(_token):
    with pytest.raises(BadRequestException):
        await require_admin_operator(
            x_admin_token=_token, x_admin_operator="x" * 65
        )
