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
        jwt_secret_key="a-real-secret-not-the-staging-default-x" * 2,
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
    s = Settings(**_prod(cors_origins=["https://admin.example.com", "https://app.example.com"]))
    assert s.cors_origins == [
        "https://admin.example.com",
        "https://app.example.com",
    ]


def test_non_production_allows_wildcard():
    """Staging / test are unrestricted (local ergonomics)."""
    s = Settings(environment="staging", cors_origins=["*"])
    assert s.cors_origins == ["*"]


# --- Admin token guard (W1-S1) ------------------------------------------------


def test_production_rejects_default_admin_token():
    with pytest.raises(ValueError, match="ADMIN_API_TOKEN"):
        Settings(
            **_prod(
                cors_origins=["https://admin.example.com"],
                admin_api_token="dev-admin-token",
            )
        )


def test_production_rejects_empty_admin_token():
    with pytest.raises(ValueError, match="ADMIN_API_TOKEN"):
        Settings(
            **_prod(
                cors_origins=["https://admin.example.com"],
                admin_api_token="",
            )
        )


def test_production_accepts_custom_admin_token():
    s = Settings(
        **_prod(
            cors_origins=["https://admin.example.com"],
            admin_api_token="a-real-high-entropy-admin-token-xyz",
        )
    )
    assert s.admin_api_token == "a-real-high-entropy-admin-token-xyz"


def test_local_defaults_keep_dev_admin_token_for_legacy_tests():
    s = Settings()
    assert s.environment == "development"
    assert s.admin_api_token == "dev-admin-token"
    assert s.jwt_secret_key == "dev-secret-key-change-in-production"


def test_staging_can_override_admin_token_from_deploy_env():
    s = Settings(environment="staging", admin_api_token="staging-admin-token")
    assert s.admin_api_token == "staging-admin-token"


# --- S3-OPS-SALT-ENTROPY-GUARD: contract_pseudonym_salt validator -------------
#
# Triggered by PR #217 review (魈 2026-06-08 13:21Z). 4 AC#5 cases:
# 1) compliance (≥ 32 char + distinct from PII salts) -> Settings instantiates
# 2) length insufficient (<32 char) -> ValueError mentioning "entropy"
# 3) salt == PII_HASH_SALT -> ValueError mentioning "PII_HASH_SALT"
# 4) salt == PII_ENVELOPE_KEY -> ValueError mentioning "PII_ENVELOPE_KEY"
#
# The validator is env-agnostic: staging/canary/prod all enforced (since
# 'aaa' in staging is a typo too, not valid config). AC#4 grace = empty/None salt
# (staging/test fallback) goes to ContractService runtime guard, not Settings.


_COMPLIANT_CONTRACT_SALT = "a-real-contract-salt-distinct-from-pii-salts-1234567890"
_COMPLIANT_PII_HASH_SALT = "a-different-pii-hash-salt-also-high-entropy-098765"
_COMPLIANT_ENVELOPE_KEY = base64.b64encode(b"q" * 32).decode("ascii")


def test_contract_pseudonym_salt_compliant_passes():
    """AC#5 case 1 / AC#6: 32+ char distinct salt instantiates Settings."""
    s = Settings(
        environment="staging",
        contract_pseudonym_salt=_COMPLIANT_CONTRACT_SALT,
        pii_hash_salt=_COMPLIANT_PII_HASH_SALT,
        pii_envelope_key=_COMPLIANT_ENVELOPE_KEY,
    )
    assert s.contract_pseudonym_salt == _COMPLIANT_CONTRACT_SALT


def test_contract_pseudonym_salt_too_short_raises():
    """AC#5 case 2 / AC#1: salt with len < 32 raises."""
    with pytest.raises(ValueError, match="entropy"):
        Settings(
            environment="staging",
            contract_pseudonym_salt="aaa",  # 3 char
        )


def test_contract_pseudonym_salt_same_as_pii_hash_salt_raises():
    """AC#5 case 3 / AC#2: salt collides with pii_hash_salt -> raise."""
    shared = "shared-salt-that-is-long-enough-to-pass-length-check-1234"
    with pytest.raises(ValueError, match="PII_HASH_SALT"):
        Settings(
            environment="staging",
            contract_pseudonym_salt=shared,
            pii_hash_salt=shared,
        )


def test_contract_pseudonym_salt_same_as_envelope_key_raises():
    """AC#5 case 4 / AC#3: salt collides with pii_envelope_key -> raise."""
    shared_key = base64.b64encode(b"k" * 32).decode("ascii")
    # length is 44 char (base64 of 32 byte), satisfies length check
    assert len(shared_key) >= 32
    with pytest.raises(ValueError, match="PII_ENVELOPE_KEY"):
        Settings(
            environment="staging",
            contract_pseudonym_salt=shared_key,
            pii_envelope_key=shared_key,
            pii_hash_salt=_COMPLIANT_PII_HASH_SALT,
        )


def test_contract_pseudonym_salt_empty_grace_skips_validator():
    """AC#4: empty salt allowed (staging/test fallback -> runtime guard tier)."""
    s = Settings(
        environment="staging",
        contract_pseudonym_salt="",
    )
    assert s.contract_pseudonym_salt == ""


def test_contract_pseudonym_salt_validator_is_env_agnostic_production_too():
    """证 validator 在 env=production 下也 raise (与 validate_production_config 独立).

    实际 prod 下 '3 char' salt 顺取由本 validator raise (而不是
    validate_production_config), 因为两者都是 model_validator(mode='after')
    顺序跳, 本 validator entropy 检查在前. 本测证 env-agnostic 设计 (prod
    不依赖 validate_production_config 反 validator entropy 哨兵).
    """
    with pytest.raises(ValueError, match="entropy"):
        Settings(
            **_prod(
                cors_origins=["https://admin.example.com"],
                contract_pseudonym_salt="too-short",
            )
        )
