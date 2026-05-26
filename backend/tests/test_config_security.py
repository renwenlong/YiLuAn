"""Tests for app.config.Settings.validate_production_config (security guards)."""
from __future__ import annotations

import base64

import pytest

from app.config import Settings

_PROD_PII_KEY = base64.b64encode(b"y" * 32).decode("ascii")


def _prod(**overrides) -> dict:
    """Common 'prod-ish' settings that pass earlier guards so we can isolate
    the field under test."""
    base = dict(
        environment="production",
        debug=False,
        jwt_secret_key="a-real-secret-not-the-dev-default-x" * 2,
        payment_provider="mock",  # avoid wechat-cred branch
        pii_envelope_key=_PROD_PII_KEY,
        pii_hash_salt="a-very-long-random-prod-salt-not-the-default-value",
        # 2026-05-13: prod now rejects sms_provider=mock; supply real-looking
        # aliyun creds so unrelated tests don't trip on this guard.
        sms_provider="aliyun",
        sms_access_key="AK",
        sms_access_secret="SK",
        sms_sign_name="YL",
        sms_template_code="SMS_1",
        # W1-S1: prod now rejects default admin_api_token; supply a placeholder.
        admin_api_token="prod-admin-token-not-the-default",
    )
    base.update(overrides)
    return base


# --- CORS guard ----------------------------------------------------------------


def test_production_rejects_wildcard_cors_origins():
    """CRIT-S1: '*' + allow_credentials=True reflects Origin (any-site can call)."""
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(**_prod(cors_origins=["*"]))


def test_production_rejects_empty_cors_origins():
    """Empty list is equally dangerous (some middleware impls treat as allow-all)."""
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(**_prod(cors_origins=[]))


def test_production_rejects_wildcard_in_mixed_list():
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(**_prod(cors_origins=["https://admin.example.com", "*"]))


def test_production_accepts_explicit_origins():
    s = Settings(
        **_prod(cors_origins=["https://admin.example.com", "https://app.example.com"])
    )
    assert s.cors_origins == [
        "https://admin.example.com",
        "https://app.example.com",
    ]


def test_non_production_allows_wildcard():
    """Local / staging are unrestricted (developer ergonomics)."""
    s = Settings(environment="development", cors_origins=["*"])
    assert s.cors_origins == ["*"]


# --- Admin token guard (W1-S1) ------------------------------------------------


def test_production_rejects_default_admin_token():
    with pytest.raises(ValueError, match="ADMIN_API_TOKEN"):
        Settings(**_prod(
            cors_origins=["https://admin.example.com"],
            admin_api_token="dev-admin-token",
        ))


def test_production_rejects_empty_admin_token():
    with pytest.raises(ValueError, match="ADMIN_API_TOKEN"):
        Settings(**_prod(
            cors_origins=["https://admin.example.com"],
            admin_api_token="",
        ))


def test_production_accepts_custom_admin_token():
    s = Settings(**_prod(
        cors_origins=["https://admin.example.com"],
        admin_api_token="a-real-high-entropy-admin-token-xyz",
    ))
    assert s.admin_api_token == "a-real-high-entropy-admin-token-xyz"


def test_non_production_keeps_default_admin_token():
    s = Settings(environment="development")
    assert s.admin_api_token == "dev-admin-token"
