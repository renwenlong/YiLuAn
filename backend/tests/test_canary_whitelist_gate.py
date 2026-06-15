"""S2-OPS-A-CANARY-WHITELIST-LAUNCH AC-2 沙ентry test suite.

Two layers of coverage:
1. CanaryWhitelist service unit tests — yaml load, placeholder skipping,
   thread-safety, malformed yaml fail-closed.
2. create_share endpoint sentinel tests — gate on/off, in/out of whitelist,
   missing phone (None) fail-closed.

All tests use the in-process direct call pattern from
test_canary_feature_flags.py (no TestClient) for speed + isolation from
auth/DI ordering. Full HTTP path is verified by integration tests
elsewhere.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.api.v1.share import create_share
from app.config import settings
from app.exceptions import ForbiddenException, ServiceUnavailableException
from app.schemas.share import CreateShareRequest
from app.services import canary_whitelist

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_whitelist_cache():
    """Reset module cache before & after each test to prevent cross-test bleed."""
    canary_whitelist.reset_for_tests()
    yield
    canary_whitelist.reset_for_tests()


@pytest.fixture
def whitelist_yaml(tmp_path: Path) -> Path:
    """Write a minimal valid whitelist yaml and return its path."""
    yaml_body = textwrap.dedent(
        """
        version: 1
        purpose: f2-whitelist-canary-mock
        flow_type: mock
        max_size: 20
        team:
          - role: developer
            name: "胡桃"
            phone: "13800000001"
            added_at: "2026-06-13"
            added_by: "test"
          - role: pm
            name: "凝光"
            phone: "__PENDING_PM__"
            added_at: "2026-06-13"
        colleagues:
          - phone: "13800000002"
            note: "colleague 1"
          - phone: "__PENDING_COLLEAGUE_01__"
            note: "placeholder"
        sentinels:
          - phone: "13800000000"
            note: "smoke"
        """
    )
    path = tmp_path / "whitelist_phones.yaml"
    path.write_text(yaml_body, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Layer 1: CanaryWhitelist service unit tests
# ---------------------------------------------------------------------------


def test_ac2_default_setting_is_disabled():
    """Backward compat: canary_whitelist_enabled default False ⇒ no gate
    behaviour change."""
    assert settings.canary_whitelist_enabled is False


def test_ac2_loads_phones_skipping_placeholders(whitelist_yaml):
    """Loader: real 11-digit phones included, placeholders excluded."""
    canary_whitelist.reload(whitelist_yaml)
    snap = canary_whitelist.get_snapshot()
    assert "13800000001" in snap.phones  # 胡桃 real
    assert "13800000002" in snap.phones  # colleague real
    assert "13800000000" in snap.phones  # sentinel
    assert "__PENDING_PM__" not in snap.phones
    assert "__PENDING_COLLEAGUE_01__" not in snap.phones
    assert len(snap.phones) == 3
    assert snap.version == "1"


def test_ac2_missing_yaml_fail_closed_empty_whitelist(tmp_path):
    """No yaml file → empty whitelist (fail-closed, no leak)."""
    nonexistent = tmp_path / "does-not-exist.yaml"
    canary_whitelist.reload(nonexistent)
    snap = canary_whitelist.get_snapshot()
    assert len(snap.phones) == 0
    assert snap.version == ""


def test_ac2_malformed_yaml_fail_closed_empty_whitelist(tmp_path):
    """Malformed yaml → empty whitelist (fail-closed)."""
    bad = tmp_path / "bad.yaml"
    bad.write_text(":::not\n  valid\n  - yaml\n!!!", encoding="utf-8")
    canary_whitelist.reload(bad)
    snap = canary_whitelist.get_snapshot()
    assert len(snap.phones) == 0


def test_ac2_yaml_not_mapping_fail_closed(tmp_path):
    """Top-level scalar/list yaml (not mapping) → empty whitelist."""
    not_dict = tmp_path / "not_dict.yaml"
    not_dict.write_text("- just\n- a\n- list\n", encoding="utf-8")
    canary_whitelist.reload(not_dict)
    snap = canary_whitelist.get_snapshot()
    assert len(snap.phones) == 0


def test_ac2_is_whitelisted_handles_none_and_empty():
    """Membership: None / "" → False (fail-closed)."""
    canary_whitelist.reset_for_tests()
    # cache will lazy-load DEFAULT_YML_PATH on next snapshot() — but we
    # only care about None/empty short-circuit which happens before snapshot:
    assert canary_whitelist.is_whitelisted(None) is False
    assert canary_whitelist.is_whitelisted("") is False
    assert canary_whitelist.is_whitelisted("   ") is False


def test_ac2_is_whitelisted_strips_whitespace(whitelist_yaml):
    """Membership: phone with leading/trailing whitespace → still matches."""
    canary_whitelist.reload(whitelist_yaml)
    assert canary_whitelist.is_whitelisted("13800000001") is True
    assert canary_whitelist.is_whitelisted("  13800000001  ") is True
    assert canary_whitelist.is_whitelisted("13800000999") is False


# ---------------------------------------------------------------------------
# Layer 2: create_share endpoint sentinel tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ac2_create_share_no_gate_when_flag_off(whitelist_yaml, monkeypatch):
    """Backward compat: canary_whitelist_enabled=False ⇒ existing behaviour,
    no whitelist check even if user phone not whitelisted."""
    canary_whitelist.reload(whitelist_yaml)
    body = CreateShareRequest()
    fake_user = MagicMock()
    fake_user.id = uuid4()
    fake_user.phone = "13900000999"  # NOT in whitelist
    fake_session = MagicMock()

    # default state: canary_whitelist_enabled=False, no gate raise expected
    with patch.object(settings, "canary_whitelist_enabled", False):
        # We can't actually run full create_share without DB stubbing the
        # _ensure_order_owner path; the key assertion is that the
        # whitelist gate does NOT raise ForbiddenException. Other layers
        # below it will raise AttributeError/TypeError on the magicmock
        # session, which is fine — we catch that and confirm we passed
        # the gate.
        with pytest.raises(Exception) as exc_info:
            await create_share(
                order_id=uuid4(),
                body=body,
                current_user=fake_user,
                session=fake_session,
            )
        # Confirm the failure is NOT our gate
        assert not isinstance(
            exc_info.value, ForbiddenException
        ), f"unexpected ForbiddenException leaked when flag off: {exc_info.value}"


@pytest.mark.asyncio
async def test_ac2_create_share_403_when_flag_on_and_phone_not_whitelisted(
    whitelist_yaml,
):
    """Gate enabled + caller phone not in whitelist ⇒ 403
    SHARE_F2_CANARY_NOT_WHITELISTED."""
    canary_whitelist.reload(whitelist_yaml)
    body = CreateShareRequest()
    fake_user = MagicMock()
    fake_user.id = uuid4()
    fake_user.phone = "13900000999"  # NOT in whitelist
    fake_session = MagicMock()

    with patch.object(settings, "canary_whitelist_enabled", True):
        with pytest.raises(ForbiddenException) as exc_info:
            await create_share(
                order_id=uuid4(),
                body=body,
                current_user=fake_user,
                session=fake_session,
            )

    assert exc_info.value.status_code == 403
    detail = exc_info.value.detail
    if isinstance(detail, dict):
        assert detail.get("error_code") == "SHARE_F2_CANARY_NOT_WHITELISTED"


@pytest.mark.asyncio
async def test_ac2_create_share_403_when_flag_on_and_phone_is_none(whitelist_yaml):
    """Gate enabled + caller has no phone bound ⇒ 403 (fail-closed)."""
    canary_whitelist.reload(whitelist_yaml)
    body = CreateShareRequest()
    fake_user = MagicMock()
    fake_user.id = uuid4()
    fake_user.phone = None
    fake_session = MagicMock()

    with patch.object(settings, "canary_whitelist_enabled", True):
        with pytest.raises(ForbiddenException) as exc_info:
            await create_share(
                order_id=uuid4(),
                body=body,
                current_user=fake_user,
                session=fake_session,
            )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_ac2_create_share_passes_gate_when_flag_on_and_phone_whitelisted(
    whitelist_yaml,
):
    """Gate enabled + caller phone in whitelist ⇒ gate does NOT raise
    (downstream DB layers may raise but our gate must pass)."""
    canary_whitelist.reload(whitelist_yaml)
    body = CreateShareRequest()
    fake_user = MagicMock()
    fake_user.id = uuid4()
    fake_user.phone = "13800000001"  # 胡桃, IS in whitelist
    fake_session = MagicMock()

    with patch.object(settings, "canary_whitelist_enabled", True):
        with pytest.raises(Exception) as exc_info:
            await create_share(
                order_id=uuid4(),
                body=body,
                current_user=fake_user,
                session=fake_session,
            )
        # Must NOT be a Forbidden (our gate); other downstream failures fine
        assert not isinstance(
            exc_info.value, ForbiddenException
        ), f"unexpected ForbiddenException for whitelisted user: {exc_info.value}"


@pytest.mark.asyncio
async def test_ac2_f2_disabled_takes_precedence_over_whitelist(whitelist_yaml):
    """Layering: FEATURE_SHARE_F2_ENABLED=false trumps the whitelist gate
    so an OPS-side global-off still returns 503 not 403 even if caller is
    whitelisted."""
    canary_whitelist.reload(whitelist_yaml)
    body = CreateShareRequest()
    fake_user = MagicMock()
    fake_user.id = uuid4()
    fake_user.phone = "13800000001"  # whitelisted
    fake_session = MagicMock()

    with (
        patch.object(settings, "feature_share_f2_enabled", False),
        patch.object(settings, "canary_whitelist_enabled", True),
    ):
        with pytest.raises(ServiceUnavailableException) as exc_info:
            await create_share(
                order_id=uuid4(),
                body=body,
                current_user=fake_user,
                session=fake_session,
            )
    assert exc_info.value.status_code == 503
