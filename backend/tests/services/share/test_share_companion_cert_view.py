"""S3-DEV-005-SHARE-CONTRACT — ``CompanionPublicCertView`` 9 字段 + service mapping unit test.

覆盖 (PRD-001 v1.4 §F8 + PM-005-1~11 + ADR-0046 §3.5):
1. ``CompanionPublicCertView`` schema 9 字段 + 3 Literal enum + ``extra="forbid"``
2. ``CompanionPublicView.cert_status`` 可挂 sub-object 或 None
3. ``ShareService.build_companion_cert_view`` mapping 三态:
   - verified  → enum=verified  + color=green  + icon=check  + work_id=PC{4}
   - pending   → enum=pending_supplement + color=yellow + icon=clock + work_id=None
   - rejected  → enum=unverified + color=gray   + icon=dash  + work_id=None
   - None profile → None sub-object
4. ABAC layer 1 红线: 不出 real_name / id_number / certification_image_url
5. ``build_share_order_view`` 加 companion_profile 参后向兼容 (不传 → cert_status=None)
"""
from __future__ import annotations

import types
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

# CompanionProfile 引入: 用 type model 而非真 DB instance (单测不连库)
from app.models.companion_profile import VerificationStatus
from app.schemas.share import (
    CompanionPublicCertView,
    CompanionPublicView,
    ShareOrderResponse,
)
from app.services.share import ShareService

# ---------------------------------------------------------------------------
# Schema 层 (9 字段 + extra=forbid + 3 enum)
# ---------------------------------------------------------------------------


class TestCompanionPublicCertViewSchema:
    """9 字段契约锁: 字段名 / required / nullable / 3 enum 严守."""

    EXPECTED_FIELDS = {
        "cert_status",
        "cert_type",
        "cert_count",
        "cert_verified_at",
        "cert_pseudonym_name",
        "cert_work_id",
        "cert_badge_color",
        "cert_badge_icon",
        "cert_detail_text",
    }

    def test_has_exactly_9_fields(self):
        actual = set(CompanionPublicCertView.model_fields.keys())
        assert actual == self.EXPECTED_FIELDS, (
            f"contract drift: got {actual ^ self.EXPECTED_FIELDS}"
        )

    def test_all_9_fields_required(self):
        """全 9 字段 required (4 个 nullable 但字段必出)."""
        for fname, info in CompanionPublicCertView.model_fields.items():
            assert info.is_required(), (
                f"{fname}: 应 required (None 允许 ≠ optional)"
            )

    def test_nullable_subset(self):
        """4 nullable: cert_type / cert_verified_at / cert_pseudonym_name / cert_work_id."""
        nullable_expected = {
            "cert_type",
            "cert_verified_at",
            "cert_pseudonym_name",
            "cert_work_id",
        }
        for fname, info in CompanionPublicCertView.model_fields.items():
            is_nullable = "None" in str(info.annotation)
            expected = fname in nullable_expected
            assert is_nullable == expected, (
                f"{fname}: nullable expected={expected}, got={is_nullable}"
            )

    def test_cert_status_3_enum(self):
        """三态 enum: verified / pending_supplement / unverified."""
        valid = {"verified", "pending_supplement", "unverified"}
        for v in valid:
            obj = self._make_valid_view(cert_status=v)
            assert obj.cert_status == v
        # 不合法值
        with pytest.raises(ValidationError):
            self._make_valid_view(cert_status="approved")

    def test_cert_badge_color_3_enum(self):
        valid = {"green", "yellow", "gray"}
        for v in valid:
            obj = self._make_valid_view(cert_badge_color=v)
            assert obj.cert_badge_color == v
        with pytest.raises(ValidationError):
            self._make_valid_view(cert_badge_color="red")

    def test_cert_badge_icon_3_enum(self):
        valid = {"check", "clock", "dash"}
        for v in valid:
            obj = self._make_valid_view(cert_badge_icon=v)
            assert obj.cert_badge_icon == v
        with pytest.raises(ValidationError):
            self._make_valid_view(cert_badge_icon="cross")

    def test_extra_forbid_rejects_unknown_field(self):
        """``extra="forbid"`` 阻止 client 漂移塞额外字段."""
        with pytest.raises(ValidationError):
            CompanionPublicCertView(
                cert_status="verified",
                cert_type="康复治疗师",
                cert_count=1,
                cert_verified_at=None,
                cert_pseudonym_name=None,
                cert_work_id="PC0042",
                cert_badge_color="green",
                cert_badge_icon="check",
                cert_detail_text="该陪诊师已完成资质认证",
                companion_real_name="李四",  # ❌ 禁字段
            )

    def test_cert_count_non_negative(self):
        with pytest.raises(ValidationError):
            self._make_valid_view(cert_count=-1)

    @staticmethod
    def _make_valid_view(**overrides):
        base = {
            "cert_status": "verified",
            "cert_type": "康复治疗师",
            "cert_count": 1,
            "cert_verified_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "cert_pseudonym_name": "陈师傅",
            "cert_work_id": "PC0042",
            "cert_badge_color": "green",
            "cert_badge_icon": "check",
            "cert_detail_text": "该陪诊师已完成资质认证",
        }
        base.update(overrides)
        return CompanionPublicCertView(**base)


# ---------------------------------------------------------------------------
# CompanionPublicView cert_status 挂载 (sub-object | null)
# ---------------------------------------------------------------------------


class TestCompanionPublicViewCertStatus:
    def test_cert_status_can_be_null(self):
        v = CompanionPublicView(name="李四", avatar_url=None, cert_status=None)
        assert v.cert_status is None

    def test_cert_status_can_be_sub_object(self):
        sub = CompanionPublicCertView(
            cert_status="verified",
            cert_type="康复治疗师",
            cert_count=1,
            cert_verified_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            cert_pseudonym_name="陈师傅",
            cert_work_id="PC0042",
            cert_badge_color="green",
            cert_badge_icon="check",
            cert_detail_text="该陪诊师已完成资质认证",
        )
        v = CompanionPublicView(
            name="李四", avatar_url="/a.png", cert_status=sub
        )
        assert v.cert_status is not None
        assert v.cert_status.cert_status == "verified"

    def test_share_order_response_companion_optional(self):
        """ShareOrderResponse.companion 仍可 null (老订单兼容)."""
        from app.models.order_share_token import ShareScope

        r = ShareOrderResponse(
            order_id="00000000-0000-0000-0000-000000000001",
            order_number="ORD-001",
            status="confirmed",
            service_type="standard",
            appointment_date="2026-01-15",
            appointment_time="14:00",
            hospital_name=None,
            patient_name_masked="李*",
            companion=None,
            share_scope=ShareScope.FULL,
            can_view_images=True,
            can_view_ai_summary=True,
            timeline=None,
        )
        assert r.companion is None


# ---------------------------------------------------------------------------
# Service mapping (build_companion_cert_view 3 态)
# ---------------------------------------------------------------------------


class _MockProfile:
    """Mock CompanionProfile 字段 (不连 DB)."""

    def __init__(
        self,
        verification_status,
        certification_type=None,
        certification_no=None,
        certification_image_url=None,
        verification_completed_at=None,
        certified_at=None,
        real_name="李四",  # ❌ 禁出
        id_number="110101199001011234",  # ❌ 禁出
    ):
        self.verification_status = verification_status
        self.certification_type = certification_type
        self.certification_no = certification_no
        self.certification_image_url = certification_image_url
        self.verification_completed_at = verification_completed_at
        self.certified_at = certified_at
        self.real_name = real_name
        self.id_number = id_number


class TestBuildCompanionCertView:
    def test_verified_state(self):
        verified_at = datetime(2026, 1, 15, tzinfo=timezone.utc)
        p = _MockProfile(
            verification_status=VerificationStatus.verified,
            certification_type="康复治疗师",
            certification_no="CERT0042",
            verification_completed_at=verified_at,
        )
        v = ShareService.build_companion_cert_view(p)
        assert v is not None
        assert v["cert_status"] == "verified"
        assert v["cert_type"] == "康复治疗师"
        assert v["cert_count"] == 1
        assert v["cert_verified_at"] == verified_at
        assert v["cert_work_id"] == "PC0042"
        assert v["cert_badge_color"] == "green"
        assert v["cert_badge_icon"] == "check"
        assert v["cert_detail_text"] == "该陪诊师已完成资质认证"
        # ABAC layer 1 红线: 禁字段不出
        assert "real_name" not in v
        assert "id_number" not in v
        assert "certification_image_url" not in v
        assert "companion_real_name" not in v

    def test_pending_state(self):
        p = _MockProfile(verification_status=VerificationStatus.pending)
        v = ShareService.build_companion_cert_view(p)
        assert v["cert_status"] == "pending_supplement"
        assert v["cert_badge_color"] == "yellow"
        assert v["cert_badge_icon"] == "clock"
        assert v["cert_count"] == 0
        assert v["cert_verified_at"] is None
        assert v["cert_work_id"] is None  # pending 不出 work_id
        assert v["cert_type"] is None  # pending 不出 type
        assert v["cert_detail_text"] == "该陪诊师临时证明有效，资质补交中"

    def test_rejected_state(self):
        p = _MockProfile(
            verification_status=VerificationStatus.rejected,
            certification_type="康复治疗师",  # 即使 model 有 type
        )
        v = ShareService.build_companion_cert_view(p)
        assert v["cert_status"] == "unverified"
        assert v["cert_badge_color"] == "gray"
        assert v["cert_badge_icon"] == "dash"
        assert v["cert_type"] is None  # rejected 不出
        assert v["cert_work_id"] is None
        assert v["cert_verified_at"] is None
        assert v["cert_detail_text"] == "该陪诊师尚未完成资质认证"

    def test_none_profile_returns_none(self):
        assert ShareService.build_companion_cert_view(None) is None

    def test_verified_no_cert_type_yields_zero_count(self):
        p = _MockProfile(
            verification_status=VerificationStatus.verified,
            certification_type=None,
        )
        v = ShareService.build_companion_cert_view(p)
        assert v["cert_count"] == 0
        assert v["cert_type"] is None

    def test_verified_at_fallback_to_certified_at(self):
        ts = datetime(2025, 12, 1, tzinfo=timezone.utc)
        p = _MockProfile(
            verification_status=VerificationStatus.verified,
            certification_type="康复治疗师",
            verification_completed_at=None,
            certified_at=ts,
        )
        v = ShareService.build_companion_cert_view(p)
        assert v["cert_verified_at"] == ts

    def test_work_id_short_cert_no_padded(self):
        """cert_no 短于 4 位 → 左侧 0 填充, 仍 PC 前缀."""
        p = _MockProfile(
            verification_status=VerificationStatus.verified,
            certification_type="康复治疗师",
            certification_no="42",  # 2 位
        )
        v = ShareService.build_companion_cert_view(p)
        assert v["cert_work_id"] == "PC0042"

    def test_pseudonym_never_leaks_real_name(self):
        """ABAC layer 1: pseudonym S3 始终 None, 严禁 fallback real_name."""
        p = _MockProfile(
            verification_status=VerificationStatus.verified,
            certification_type="康复治疗师",
            real_name="王五",
        )
        v = ShareService.build_companion_cert_view(p)
        assert v["cert_pseudonym_name"] is None
        # str(v) 也不能含 real_name
        assert "王五" not in str(v)


# ---------------------------------------------------------------------------
# build_share_order_view 向后兼容
# ---------------------------------------------------------------------------


class TestBuildShareOrderViewBackwardCompat:
    def _mock_order(self):
        o = types.SimpleNamespace()
        o.id = "00000000-0000-0000-0000-000000000001"
        o.order_number = "ORD-001"
        o.status = "confirmed"
        o.service_type = "standard"
        o.appointment_date = "2026-01-15"
        o.appointment_time = "14:00"
        o.hospital_name = "三甲医院"
        o.patient_name = "张三"
        o.companion_id = None
        return o

    def _mock_user(self):
        u = types.SimpleNamespace()
        # S3-BUG-004: User model 只有 ``display_name``, 0 ``real_name`` / ``nickname``.
        # 老 test 写死 ``u.real_name = "李四"`` 是 mock 故意 set, 模型实际 0 该字段.
        # 新版用真实模型字段 ``display_name``.
        u.display_name = "张医生"
        u.avatar_url = "/a.png"
        return u

    def test_no_companion_no_cert_status(self):
        from app.models.order_share_token import ShareScope

        view = ShareService.build_share_order_view(
            order=self._mock_order(),
            share_scope=ShareScope.FULL,
            companion=None,
        )
        assert view["companion"] is None

    def test_companion_without_profile_cert_status_null(self):
        """老订单 companion 有但无 profile → cert_status=None (向后兼容)."""
        from app.models.order_share_token import ShareScope

        view = ShareService.build_share_order_view(
            order=self._mock_order(),
            share_scope=ShareScope.FULL,
            companion=self._mock_user(),
            companion_profile=None,
        )
        assert view["companion"]["cert_status"] is None

    def test_companion_with_verified_profile(self):
        from app.models.order_share_token import ShareScope

        p = _MockProfile(
            verification_status=VerificationStatus.verified,
            certification_type="康复治疗师",
            certification_no="CERT0042",
            verification_completed_at=datetime(
                2026, 1, 1, tzinfo=timezone.utc
            ),
        )
        view = ShareService.build_share_order_view(
            order=self._mock_order(),
            share_scope=ShareScope.FULL,
            companion=self._mock_user(),
            companion_profile=p,
        )
        cs = view["companion"]["cert_status"]
        assert cs["cert_status"] == "verified"
        assert cs["cert_badge_color"] == "green"
        # Pydantic 验证整 view 通过
        from app.schemas.share import ShareOrderResponse

        resp = ShareOrderResponse(**view)
        assert resp.companion.cert_status.cert_status == "verified"

    def test_kwargs_only(self):
        """build_share_order_view 强制 keyword-only, 防 positional drift."""
        from app.models.order_share_token import ShareScope

        with pytest.raises(TypeError):
            ShareService.build_share_order_view(
                self._mock_order(), ShareScope.FULL  # type: ignore[misc]
            )


# ---------------------------------------------------------------------------
# S3-BUG-004-SHARE-COMPANION-NAME-PII-LEAK: companion.name display_name-first +
# 通名 fallback (非 real_name / nickname)
# ---------------------------------------------------------------------------


class TestBuildShareOrderViewCompanionName:
    """S3-BUG-004 修法 AC#1 + AC#2 全 case 覆盖.

    现 share.py:333-336 旧实现 ``getattr(real_name) or getattr(nickname)``
    实际永返 None (User model 0 那俩字段, fact check 见 task description).
    新实现 display_name-first + "陪诊师" 通名 fallback.
    AC#4 顺便 verify 即使 mock 故意 set ``real_name``, view name 也绝不出实姓.
    """

    def _mock_order(self):
        o = types.SimpleNamespace()
        o.id = "00000000-0000-0000-0000-000000000001"
        o.order_number = "ORD-001"
        o.status = "confirmed"
        o.service_type = "standard"
        o.appointment_date = "2026-01-15"
        o.appointment_time = "14:00"
        o.hospital_name = "三甲医院"
        o.patient_name = "张三"
        o.companion_id = None
        return o

    def test_case_a_display_name_present(self):
        """AC#2 case A: display_name='张医生' → view name == '张医生'."""
        from app.models.order_share_token import ShareScope

        u = types.SimpleNamespace()
        u.display_name = "张医生"
        u.avatar_url = "/a.png"

        view = ShareService.build_share_order_view(
            order=self._mock_order(),
            share_scope=ShareScope.FULL,
            companion=u,
        )
        assert view["companion"]["name"] == "张医生"

    def test_case_b_display_name_none_fallback_generic(self):
        """AC#2 case B: display_name=None → view name == '陪诊师' 通名."""
        from app.models.order_share_token import ShareScope

        u = types.SimpleNamespace()
        u.display_name = None
        u.avatar_url = "/a.png"

        view = ShareService.build_share_order_view(
            order=self._mock_order(),
            share_scope=ShareScope.FULL,
            companion=u,
        )
        assert view["companion"]["name"] == "陪诊师"

    def test_case_c_companion_none(self):
        """AC#2 case C: companion=None → view['companion'] is None (向后兼容)."""
        from app.models.order_share_token import ShareScope

        view = ShareService.build_share_order_view(
            order=self._mock_order(),
            share_scope=ShareScope.FULL,
            companion=None,
        )
        assert view["companion"] is None

    def test_case_d_abac_layer_1_real_name_attr_ignored(self):
        """AC#1 + AC#4 红线: 即使 SimpleNamespace 故意 set ``real_name`` + ``nickname``,
        view name 也绝不出实姓, 只走 display_name 通道.

        防御未来 User model 加 ``real_name`` 字段时 silent fallback 立刻泄漏.
        """
        from app.models.order_share_token import ShareScope

        u = types.SimpleNamespace()
        u.real_name = "李实姓"  # 故意 set (模型 0 字段, 测试不能依赖)
        u.nickname = "lishishi"  # 故意 set (模型 0 字段, 测试不能依赖)
        u.display_name = "李医生"
        u.avatar_url = "/a.png"

        view = ShareService.build_share_order_view(
            order=self._mock_order(),
            share_scope=ShareScope.FULL,
            companion=u,
        )
        # 必须走 display_name, 0 走 real_name / nickname
        assert view["companion"]["name"] == "李医生"
        assert view["companion"]["name"] != "李实姓"  # PII 绝不出
        assert view["companion"]["name"] != "lishishi"  # nickname 不在路径

    def test_case_e_abac_real_name_only_no_display_falls_to_generic(self):
        """AC#4 极端: User 既无 display_name 也无 real_name 字段时 fallback 通名,
        而非空 string (空 string 会 truthy fail or 渲染空白)."""
        from app.models.order_share_token import ShareScope

        u = types.SimpleNamespace()
        # 故意 set real_name 但 0 display_name — 验证 "绝不 real_name fallback"
        u.real_name = "陈实姓"
        u.avatar_url = "/a.png"
        # display_name 不 set (SimpleNamespace getattr 返 None)

        view = ShareService.build_share_order_view(
            order=self._mock_order(),
            share_scope=ShareScope.FULL,
            companion=u,
        )
        assert view["companion"]["name"] == "陪诊师"  # 通名 fallback
        assert view["companion"]["name"] != "陈实姓"  # real_name 绝不漏

    def test_case_f_display_name_empty_string_falls_to_generic(self):
        """AC#4 边: display_name='' (空 string) → fallback '陪诊师' (因 truthy fail).

        防 UI 渲染空白. ``or`` 短路依赖 truthy, 空 string falsy → 走 fallback.
        """
        from app.models.order_share_token import ShareScope

        u = types.SimpleNamespace()
        u.display_name = ""  # 空 string
        u.avatar_url = "/a.png"

        view = ShareService.build_share_order_view(
            order=self._mock_order(),
            share_scope=ShareScope.FULL,
            companion=u,
        )
        assert view["companion"]["name"] == "陪诊师"

    def test_case_g_cert_status_orthogonal_to_name(self):
        """verify name 改法不影响 cert_status sub-object (S3-DEV-005 PR #270 0 regression)."""
        from app.models.order_share_token import ShareScope

        u = types.SimpleNamespace()
        u.display_name = "张医生"
        u.avatar_url = "/a.png"

        p = _MockProfile(
            verification_status=VerificationStatus.verified,
            certification_type="康复治疗师",
            certification_no="CERT0042",
            verification_completed_at=datetime(
                2026, 1, 1, tzinfo=timezone.utc
            ),
        )
        view = ShareService.build_share_order_view(
            order=self._mock_order(),
            share_scope=ShareScope.FULL,
            companion=u,
            companion_profile=p,
        )
        # name 修 + cert_status 不受影响
        assert view["companion"]["name"] == "张医生"
        assert view["companion"]["cert_status"]["cert_status"] == "verified"
        assert view["companion"]["cert_status"]["cert_work_id"] == "PC0042"
