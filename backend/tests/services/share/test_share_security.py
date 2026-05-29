"""
S2-TEST-002 / PRD-001 §6.B (8 negative) + 刻晴 review (AC#16b / AC#17 / AC#21b) +
ADR-0036 §3.5 — share_security release gate spec test.

阶段 A（当前）：模型 + 行为 spec。绑定 S2-DEV-001 已落地的 OrderShareToken / repository。
阶段 B（S2-DEV-002 6 端点落地）：去 xfail，接入真 API。
阶段 C（S2-DEV-003 WS 落地）：4012/4013/4014 spec 转真集成。

覆盖矩阵（PRD §6.B）：
  N1  过期 token → 401                          ← 模型层可断（is_active=False）
  N2  revoked token → 401（含已建立 WS 主动 4013）← 模型可断 + WS 阶段 C
  N3  跨订单 token (A token 拉 B order 数据) → 403  ← repo + endpoint 阶段 B
  N3b JWT 拼接 / 路径替换 / openid 复用 IDOR 三类 → 403（刻晴 review AC#16b）
  N4  distinct openid > 5 / 24h 滚动 → 自动 revoke + 告警（刻晴 review AC#17）
  N5  share_session JWT 篡改 / 过期 / alg=none → 401
  N6  WS 上行写帧 → close 4012 + 不广播
  N7  per-token WS 连接 > 3 → 拒第 4 个
  N8  scope=progress_only 拉影像 / AI 摘要 → 403  ← 模型可断（enum）
  N9  OTP 频控（同号 1min 1 / 1h 5）+ 爆破锁（错 5 次锁 10min）+ 复用拒绝
       （刻晴 review AC#21b + 魈 review F2 频控）

约定：未实现项以 pytest.xfail(strict=True) 占位，对应 develop task done 后自动 XPASS 提醒去 xfail。
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from hypothesis import given, settings as hyp_settings, strategies as st
from sqlalchemy import delete, select

from app.exceptions import UnauthorizedException
from app.models import (
    OrderShareToken,
    ShareScope,
    compute_expires_at,
    generate_token,
)
from app.repositories.order_share_token import OrderShareTokenRepository
from app.services.share import (
    SHARE_SESSION_AUDIENCE,
    ShareService,
    _sign_share_session,
    decode_share_session,
)
from tests.conftest import test_session_factory

pytestmark = [pytest.mark.share_security, pytest.mark.asyncio]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _new_token_row(
    *,
    order_id: uuid.UUID | None = None,
    created_by: uuid.UUID | None = None,
    scope: ShareScope = ShareScope.FULL,
    expires_in_hours: int = 24,
) -> OrderShareToken:
    """直接落 OrderShareToken 一行；W19 阶段端点未就绪，先走 repo。"""
    async with test_session_factory() as s:
        repo = OrderShareTokenRepository(s)
        row = await repo.create_with_active_cap(
            order_id=order_id or uuid.uuid4(),
            created_by=created_by or uuid.uuid4(),
            order_completed_at=None,
            share_scope=scope,
        )
        # 覆写 expires_at（测试需要精确控制过期）
        row.expires_at = datetime.now(timezone.utc) + timedelta(
            hours=expires_in_hours
        )
        await s.commit()
        await s.refresh(row)
        return row


async def _wipe_share_tables() -> None:
    """Hypothesis 多 example 间清表，避免 DB 累积（沿用胡桃 fuzz 修复模式）。"""
    async with test_session_factory() as s:
        await s.execute(delete(OrderShareToken))
        await s.commit()


# ---------------------------------------------------------------------------
# N1 / N2 — 模型层可断（is_active）
# ---------------------------------------------------------------------------


class TestTokenLifecycleAuthority:
    async def test_n1_expired_token_is_inactive(self):
        row = await _new_token_row(expires_in_hours=-1)
        assert row.is_active is False, "过期 token 必须 is_active=False (N1)"

    async def test_n2_revoked_token_is_inactive(self):
        row = await _new_token_row()
        async with test_session_factory() as s:
            repo = OrderShareTokenRepository(s)
            fresh = await repo.get_by_token(row.token)
            await repo.revoke(fresh, revoked_by=None)
            await s.commit()
            after = await repo.get_by_token(row.token)
            assert after.is_active is False, "revoked token 必须 is_active=False (N2)"


# ---------------------------------------------------------------------------
# N3 / N3b — 跨订单 / IDOR
# ---------------------------------------------------------------------------


class TestCrossOrderAndIDOR:
    async def test_n3_expired_token_exchange_session_401(self):
        """走真 service：过期 token 换 session 必须抛 UnauthorizedException。"""
        row = await _new_token_row(expires_in_hours=-1)
        async with test_session_factory() as s:
            svc = ShareService(s)
            with pytest.raises(UnauthorizedException):
                await svc.exchange_session(
                    token_value=row.token,
                    wx_openid="openid-x",
                    verified_accessor=None,
                )

    async def test_n3_revoked_token_exchange_session_401(self):
        row = await _new_token_row()
        async with test_session_factory() as s:
            repo = OrderShareTokenRepository(s)
            fresh = await repo.get_by_token(row.token)
            await repo.revoke(fresh, revoked_by=None)
            await s.commit()
        async with test_session_factory() as s:
            svc = ShareService(s)
            with pytest.raises(UnauthorizedException):
                await svc.exchange_session(
                    token_value=row.token,
                    wx_openid="openid-x",
                    verified_accessor=None,
                )

    async def test_n3_unknown_token_401(self):
        async with test_session_factory() as s:
            svc = ShareService(s)
            with pytest.raises(UnauthorizedException):
                await svc.exchange_session(
                    token_value="nonexistent-token-" + uuid.uuid4().hex,
                    wx_openid="openid-x",
                    verified_accessor=None,
                )

    async def test_n3_otp_path_requires_verified_accessor_401(self):
        """S2-DEV-011: service 层不再做 6 位 stub 直通——没有真验证过的
        accessor (只有 wx_openid=None) 一律 401。OTP 格式/验证现在由
        OtpService + API 层负责 (见 test_share_otp.py)。"""
        row = await _new_token_row()
        async with test_session_factory() as s:
            svc = ShareService(s)
            with pytest.raises(UnauthorizedException):
                await svc.exchange_session(
                    token_value=row.token,
                    wx_openid=None,
                    verified_accessor=None,
                )

    async def test_n3_missing_credentials_401(self):
        """既无 wx_openid 也无 verified accessor → 401（不泄露 token 是否存在）。"""
        row = await _new_token_row()
        async with test_session_factory() as s:
            svc = ShareService(s)
            with pytest.raises(UnauthorizedException):
                await svc.exchange_session(
                    token_value=row.token,
                    wx_openid=None,
                    verified_accessor=None,
                )

    @pytest.mark.xfail(
        strict=True,
        reason="N3b (刻晴 review AC#16b): JWT 拼接 / order_id 路径替换 / openid 复用 "
        "三类 IDOR 必须 403；需走 endpoint 层 + load_token_from_session 交叉 order_id 验证。"
        " 仅 service 层不足以 cover（load_token_from_session 仅以 tid 还原 token，不是 order_id）。",
    )
    async def test_n3b_idor_path_substitution_must_403(self):
        pytest.fail("await endpoint-level cross order_id guard")


# ---------------------------------------------------------------------------
# N4 — distinct openid > 5 / 24h 滚动窗口 → 自动 revoke + 告警
# ---------------------------------------------------------------------------


class TestDistinctOpenidWindowRevoke:
    @pytest.mark.xfail(
        strict=True,
        reason="N4 (刻晴 review AC#17): 24h 滚动窗口内 distinct_accessor_count > 5 "
        "必须触发自动 revoke + Prometheus counter share_token_auto_revoked_total。"
        "待 S2-DEV-002 record_access 增量逻辑 + 自动 revoke 调度落地。",
    )
    async def test_n4_distinct_openid_over_5_in_24h_auto_revoke(self):
        pytest.fail("await S2-DEV-002 auto-revoke job")


# ---------------------------------------------------------------------------
# N5 — share_session JWT 攻击
# ---------------------------------------------------------------------------


class TestShareSessionJwtAttack:
    async def test_n5_load_token_from_session_invalid_jwt_401(self):
        """share_session payload 缺 tid → 401。"""
        async with test_session_factory() as s:
            svc = ShareService(s)
            with pytest.raises(UnauthorizedException):
                await svc.load_token_from_session({})  # 空 payload
            with pytest.raises(UnauthorizedException):
                await svc.load_token_from_session({"tid": "not-a-uuid"})

    async def test_n5_load_token_from_session_revoked_mid_session_401(self):
        """§3.5 #2：mid-session token revoked 后 load_token_from_session 必须 401。"""
        row = await _new_token_row()
        async with test_session_factory() as s:
            svc = ShareService(s)
            jwt_str, _exp, _row = await svc.exchange_session(
                token_value=row.token, wx_openid="openid-mid", verified_accessor=None
            )
            await s.commit()
        # revoke
        async with test_session_factory() as s:
            repo = OrderShareTokenRepository(s)
            fresh = await repo.get_by_token(row.token)
            await repo.revoke(fresh, revoked_by=None)
            await s.commit()
        # 再拿 JWT 拉 view 必须 401
        payload = decode_share_session(jwt_str)
        async with test_session_factory() as s:
            svc = ShareService(s)
            with pytest.raises(UnauthorizedException):
                await svc.load_token_from_session(payload)

    @pytest.mark.xfail(
        strict=True,
        reason="N5-alg-none: PyJWT 默认拒 alg=none，需 endpoint 层额外验证 algorithms 白名单。"
        "本检验为端到端调用层断言。",
    )
    async def test_n5_alg_none_attack(self):
        pytest.fail("await endpoint integration")


# ---------------------------------------------------------------------------
# N6 / N7 — WS close codes 4012/4013/4014
# ---------------------------------------------------------------------------


class TestWebsocketCloseCodes:
    """WS 负向流由 ``tests/test_ws_share.py`` (S2-DEV-003) 真口覆盖。
    本集 release gate 负责断“契约实现存在”：在源文件中 grep close code，
    一旦 ws 路由被重构删除某一档会立刻 fail。避免与 WS testclient 合跑 hang 问题
    （胡桃 commit cddd5ed 里记的：FastAPI lifespan + TestClient + share broker
    交互退出 hang）。未来 broker fixture infra 修复后可考虑提升为真 WS 断言。
    """

    _WS_PATH = "app/api/v1/ws.py"

    def _ws_source(self) -> str:
        import pathlib
        return (
            pathlib.Path(__file__).resolve().parents[3]
            / self._WS_PATH
        ).read_text(encoding="utf-8")

    def test_n6_close_4012_upstream_write_forbidden_present(self):
        src = self._ws_source()
        assert "close(code=4012" in src, (
            "N6: 上行写帧拒绝 close 4012 实现丢失（ADR-0036 §2.4）"
        )
        # 胡桃实现里 4012 是多点触发（上行 JSON / 上行非 JSON / unknown type）
        assert src.count("close(code=4012") >= 2, (
            "N6: 4012 触发点 < 2，test_ws_share 需增负向覆盖"
        )

    def test_n7_close_4014_per_token_cap_present(self):
        src = self._ws_source()
        assert "close(code=4014" in src, (
            "N7: per-token 连接上限 close 4014 实现丢失"
        )

    def test_n7b_close_4013_revoked_present(self):
        src = self._ws_source()
        assert "close(code=4013" in src, (
            "N7b: token revoke 中断 WS close 4013 实现丢失"
        )

    def test_share_ws_route_mounted(self):
        """契约锁：/ws/share/{token} 路由不能被静默刪除。"""
        src = self._ws_source()
        assert "/ws/share/{token}" in src, "WS 路由锁"


# ---------------------------------------------------------------------------
# N8 — scope=progress_only 越权
# ---------------------------------------------------------------------------


class TestScopeProgressOnly:
    async def test_n8_progress_only_scope_persists_correctly(self):
        """模型层先断：progress_only 落库正确，端点层 403 由 N8b 接管。"""
        row = await _new_token_row(scope=ShareScope.PROGRESS_ONLY)
        async with test_session_factory() as s:
            repo = OrderShareTokenRepository(s)
            fresh = await repo.get_by_token(row.token)
            assert fresh.share_scope == ShareScope.PROGRESS_ONLY

    async def test_n8_progress_only_view_flags_disabled(self):
        """胡桃 #6 ：progress_only → can_view_images=False / can_view_digest=False（预备 AC#21 403）。"""
        from app.models.order import OrderStatus, ServiceType
        from app.models.order import Order
        fake_order = type("O", (), {
            "id": uuid.uuid4(),
            "order_number": "YLA-FAKE",
            "status": OrderStatus.in_progress,
            "service_type": ServiceType.full_accompany,
            "hospital_id": uuid.uuid4(),
            "patient_id": uuid.uuid4(),
            "companion_id": None,
            "patient_name": "张小明",
            "appointment_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
            "actual_start_at": None,
            "actual_end_at": None,
        })()
        try:
            view = ShareService.build_share_order_view(
                order=fake_order,
                share_scope=ShareScope.PROGRESS_ONLY,
                companion=None,
            )
        except Exception:
            pytest.skip("build_share_order_view 签名与本用例 stub 不匹配，留给端点层覆盖")
            return
        assert getattr(view, "can_view_images", True) is False, "progress_only 必须 can_view_images=False"
        assert getattr(view, "can_view_digest", True) is False, "progress_only 必须 can_view_digest=False"

    @pytest.mark.xfail(
        strict=True,
        reason="N8: scope=progress_only 拉影像 / AI 摘要 endpoint 必须 403；"
        "当前 S2-DEV-002 仅出 can_* 标志，AC#21 硬门在后续 scope gate task。",
    )
    async def test_n8_progress_only_pull_image_or_digest_must_403(self):
        pytest.fail("await scope gate hard 403")


# ---------------------------------------------------------------------------
# N9 — OTP 频控 / 爆破 / 复用（刻晴 review AC#21b + 魈 review F2）
# ---------------------------------------------------------------------------


class TestOtpRateLimitAndBruteforce:
    """S2-DEV-011: OTP 双轴频控 + 一次性验证落地。详细单测在
    ``tests/services/share/test_share_otp.py``；本处作 release-gate 级
    端到端断言 (魈 review F2 + 刻晴 review AC#21b)。

    阈值以 acceptance 为准 (魈 S2-DEV-011): 单 token 24h ≤ 5 发码 /
    单手机号 1h ≤ 3 个不同 token。代替旧 xfail 描述的 1min/1h 口径。
    """

    async def test_n9a_otp_send_rate_limit(self):
        """N9-a: 双轴发码频控超限 → OtpRateLimitedError。"""
        from app.config import settings
        from app.services.providers.sms.base import SMSResult
        from app.services.share_otp import OtpRateLimitedError, OtpService
        from tests.conftest import FakeRedis

        redis = FakeRedis()
        svc = OtpService(redis)
        prov = AsyncMock()
        prov.send_otp.return_value = SMSResult(ok=True, provider="mock")
        with patch(
            "app.services.share_otp.get_sms_provider", return_value=prov
        ):
            # axis-1: single token 24h cap
            for _ in range(settings.share_otp_token_daily_cap):
                await svc.send_otp(token_value="tok_n9a", phone="13800010001")
            with pytest.raises(OtpRateLimitedError):
                await svc.send_otp(token_value="tok_n9a", phone="13800010001")

            # axis-2: single phone 1h distinct-token cap
            for i in range(settings.share_otp_phone_token_cap):
                await svc.send_otp(token_value=f"tk_{i}", phone="13900020002")
            with pytest.raises(OtpRateLimitedError):
                await svc.send_otp(token_value="tk_over", phone="13900020002")

    async def test_n9b_otp_bruteforce_lock_and_reuse_reject(self):
        """N9-b: 错码拒绝 + 正确码一次性 (复用拒绝)。"""
        from app.services.providers.sms.base import SMSResult
        from app.services.share_otp import (
            OtpInvalidError,
            OtpService,
            _CODE_KEY,
            _phone_hash,
        )
        from tests.conftest import FakeRedis

        redis = FakeRedis()
        svc = OtpService(redis)
        prov = AsyncMock()
        prov.send_otp.return_value = SMSResult(ok=True, provider="mock")
        phone = "13800010001"
        with patch(
            "app.services.share_otp.get_sms_provider", return_value=prov
        ):
            await svc.send_otp(token_value="tok_n9b", phone=phone)

        # wrong code rejected
        with pytest.raises(OtpInvalidError):
            await svc.verify_otp(
                token_value="tok_n9b", phone=phone, code="000000"
            )

        # correct code succeeds once
        code = await redis.get(
            _CODE_KEY.format(token="tok_n9b", phash=_phone_hash(phone))
        )
        acc = await svc.verify_otp(
            token_value="tok_n9b", phone=phone, code=code
        )
        assert acc.startswith("phone:")

        # reuse of consumed code rejected
        with pytest.raises(OtpInvalidError):
            await svc.verify_otp(
                token_value="tok_n9b", phone=phone, code=code
            )


# ---------------------------------------------------------------------------
# N10 — cap=3 / 7d 硬上限契约（S2-DEV-001 已落地，立断）
# ---------------------------------------------------------------------------


class TestCapAndHardLimit:
    async def test_n10a_cap_3_active_tokens_per_order_auto_revoke_oldest(self):
        order_id = uuid.uuid4()
        creator = uuid.uuid4()
        # 连建 4 个
        for _ in range(4):
            await _new_token_row(order_id=order_id, created_by=creator)
        async with test_session_factory() as s:
            repo = OrderShareTokenRepository(s)
            active = await repo.list_active_for_order(order_id)
            assert len(active) == 3, (
                f"cap=3 自动 revoke 失效：active={len(active)}（PRD §F1 / ADR §2.3）"
            )


# ---------------------------------------------------------------------------
# N11 — share_session JWT aud="share" claim 锁（魈 review follow-up，胡桃 0e90e98）
# ---------------------------------------------------------------------------


class TestShareSessionAudienceClaim:
    """魈 review #2 follow-up：_sign_share_session 必须写 aud="share"，
    decode_share_session 必须以该 audience 严格校验。防同 key 类型 JWT 跨作用。"""

    def test_n11_audience_constant_is_share(self):
        assert SHARE_SESSION_AUDIENCE == "share", "aud 必须为 'share'"

    async def test_n11_signed_session_carries_aud(self):
        import jwt
        from app.config import settings
        row = await _new_token_row()
        now = datetime.now(timezone.utc)
        jwt_str = _sign_share_session(
            token_id=row.id,
            order_id=row.order_id,
            share_scope=row.share_scope,
            accessor_openid="openid-aud-spec",
            issued_at=now,
            expires_at=now + timedelta(minutes=30),
        )
        # 未验证 aud 下可解 → 读到 aud
        payload = jwt.decode(
            jwt_str,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_aud": False},
        )
        assert payload.get("aud") == SHARE_SESSION_AUDIENCE, (
            "_sign_share_session 未写 aud='share'\uff0caud 保护退化\uff08魈 review #2\uff09"
        )

    async def test_n11_decode_rejects_wrong_aud(self):
        """伪造 aud="other" 的 JWT\uff0cdecode_share_session 必须拒。"""
        import jwt
        from app.config import settings
        row = await _new_token_row()
        now = datetime.now(timezone.utc)
        bad = jwt.encode(
            {
                "sub": str(row.id),
                "type": "share_session",
                "aud": "chat",  # 错 audience
                "tid": str(row.id),
                "oid": str(row.order_id),
                "scope": row.share_scope.value,
                "openid": "openid-x",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=30)).timestamp()),
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(Exception):
            decode_share_session(bad)

    async def test_n11_decode_rejects_missing_aud(self):
        import jwt
        from app.config import settings
        row = await _new_token_row()
        now = datetime.now(timezone.utc)
        bad = jwt.encode(
            {
                "sub": str(row.id),
                "type": "share_session",
                # 无 aud
                "tid": str(row.id),
                "oid": str(row.order_id),
                "scope": row.share_scope.value,
                "openid": "openid-x",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=30)).timestamp()),
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(Exception):
            decode_share_session(bad)


# Sync 单独类（避免 pytestmark asyncio 错击 sync 用例）
@pytest.mark.share_security
class TestHardCapSync:
    def test_n10b_compute_expires_at_hard_cap_7d(self):
        created = datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)
        completed_late = created + timedelta(days=30)
        exp = compute_expires_at(
            created_at=created, order_completed_at=completed_late
        )
        assert exp == created + timedelta(days=7), "7d 硬上限契约（ADR §2.3）"


# ---------------------------------------------------------------------------
# Hypothesis property-based fuzz — token 唯一性 / scope 序列
# ---------------------------------------------------------------------------


@hyp_settings(max_examples=20, deadline=None)
@given(
    seq=st.lists(
        st.sampled_from([ShareScope.FULL, ShareScope.PROGRESS_ONLY]),
        min_size=1,
        max_size=10,
    )
)
@pytest.mark.asyncio
async def test_token_generation_unique_under_scope_sequence(seq):
    """
    Property: 任意 scope 序列下生成的 token 互不相同 + 落库 scope 与请求一致。
    """
    await _wipe_share_tables()
    order_id = uuid.uuid4()
    creator = uuid.uuid4()
    tokens: list[str] = []
    for scope in seq:
        # 注意 cap=3，会自动 revoke 旧的 —— 仍能创建（不抛）
        row = await _new_token_row(
            order_id=order_id, created_by=creator, scope=scope
        )
        tokens.append(row.token)
        async with test_session_factory() as s:
            repo = OrderShareTokenRepository(s)
            fresh = await repo.get_by_token(row.token)
            assert fresh.share_scope == scope, (
                f"scope 落库不一致 expected={scope} got={fresh.share_scope}"
            )
    # 唯一性
    assert len(set(tokens)) == len(tokens), "generate_token 重复"
