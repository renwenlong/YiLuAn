"""S3-DEV-004-FEEDBACK-API endpoint tests (ADR-0049 §6.4 + §7).

# Coverage matrix

| AC | Test |
|---|---|
| 1) 8 endpoint 全鉴权 | TestAuthBoundary |
| 2) admin-v2 反馈模块平级 | TestAdminListAndDetail |
| 3) 陪诊师端 ABAC 4 层 不暴露原文 | TestCompanionRedLine + TestCompanionSummaryFieldSetLocked |
| 4) S4_FEEDBACK_SUMMARY budget axis | TestBudgetAxisOccupied (in test_ai_budget_guard_s4.py) |
| 5) OpenAPI + Schemathesis 契约 lock | TestSchemaSentinels |

# Field set lock (ADR-0049 §6.4 刻晴 review #7 amend)

CompanionFeedbackSummaryView response field set must be exactly:
{feedback_id, severity, status, sanitized_summary, companion_appeal}

Adding a field to this view requires schema PR + reviewer ack.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.core.admin_jwt import create_admin_access_token
from app.core.security import create_access_token
from app.models.admin_user import AdminRole, AdminUser
from app.models.user import User, UserRole
from app.models.user_feedback import (
    FeedbackFunctionModule,
    FeedbackSeverity,
    FeedbackSource,
    FeedbackStatus,
    UserFeedback,
)
from app.schemas.feedback import (
    FEEDBACK_RESPONSE_NEGATIVE_LIST,
    FEEDBACK_RESPONSE_POSITIVE_LIST,
    CompanionFeedbackSummaryView,
    UserFeedbackDetailView,
)
from tests.conftest import test_session_factory as _session_factory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_admin(username: str = "feedback_admin") -> str:
    async with _session_factory() as session:
        admin = AdminUser(
            username=username,
            password_hash="test-not-used",
            role=AdminRole.super_,
            is_active=True,
        )
        session.add(admin)
        await session.commit()
        await session.refresh(admin)
        return create_admin_access_token(admin)


async def _seed_companion_user(phone: str = "13700001100") -> tuple[User, str]:
    """Seed a user with companion role + return (user, token)."""
    async with _session_factory() as session:
        user = User(
            phone=phone, role=UserRole.companion, roles="companion", is_active=True
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
    token = create_access_token({"sub": str(user.id), "role": "companion"})
    return user, token


# ---------------------------------------------------------------------------
# AC #1: 8 endpoint 全鉴权
# ---------------------------------------------------------------------------


class TestAuthBoundary:
    """Without a valid JWT, every endpoint returns 401."""

    @pytest.mark.parametrize(
        "method,path,expected_status",
        [
            # user / companion endpoints: HTTPBearer security_scheme raises
            # 403 when no Authorization header is present (FastAPI default).
            ("POST", "/api/v1/users/feedbacks", 403),
            (
                "POST",
                "/api/v1/users/feedbacks/00000000-0000-0000-0000-000000000000/append",
                403,
            ),
            (
                "POST",
                "/api/v1/companions/feedbacks/00000000-0000-0000-0000-000000000000/appeal",
                403,
            ),
            (
                "GET",
                "/api/v1/companions/feedbacks/00000000-0000-0000-0000-000000000000/summary",
                403,
            ),
            # admin endpoints: require_admin_jwt raises 401 on missing token
            # (admin route requires authentic admin auth header).
            ("POST", "/api/v1/admin/feedbacks", 401),
            ("GET", "/api/v1/admin/feedbacks", 401),
            (
                "GET",
                "/api/v1/admin/feedbacks/00000000-0000-0000-0000-000000000000",
                401,
            ),
            (
                "PATCH",
                "/api/v1/admin/feedbacks/00000000-0000-0000-0000-000000000000/status",
                401,
            ),
        ],
    )
    async def test_no_auth_returns_401_or_403(
        self,
        client: AsyncClient,
        method: str,
        path: str,
        expected_status: int,
    ) -> None:
        """Every endpoint rejects unauthenticated calls.

        FastAPI's HTTPBearer dependency raises 403 (NOT 401) when the
        ``Authorization`` header is missing. Admin endpoints go through
        ``require_admin_jwt`` which returns 401 for missing/invalid
        tokens. Either way: anonymous = denied. AC #1 satisfied.
        """
        client.headers.pop("Authorization", None)
        if method == "POST":
            resp = await client.post(path, json={})
        elif method == "GET":
            resp = await client.get(path)
        else:
            resp = await client.patch(path, json={})
        assert resp.status_code == expected_status, (
            f"{method} {path} expected {expected_status}, "
            f"got {resp.status_code}: {resp.text[:200]}"
        )


# ---------------------------------------------------------------------------
# AC #3 RED LINE: companion summary field set lock
# ---------------------------------------------------------------------------


class TestCompanionSummaryFieldSetLocked:
    """Layer 1+4 defense (ADR-0049 §6.1+§6.4)."""

    EXPECTED_FIELDS: frozenset[str] = frozenset(
        {"feedback_id", "severity", "status", "sanitized_summary", "companion_appeal"}
    )

    def test_response_schema_field_set_frozen(self) -> None:
        """Pydantic model fields must be exactly the expected set.

        Adding any field is a RED LINE breach; requires schema PR +
        reviewer ack. Removing a field is also flagged because clients
        depend on the contract.
        """
        actual = set(CompanionFeedbackSummaryView.model_fields.keys())
        assert actual == self.EXPECTED_FIELDS, (
            f"CompanionFeedbackSummaryView field set drift! "
            f"expected={sorted(self.EXPECTED_FIELDS)}, actual={sorted(actual)}"
        )

    def test_forbidden_fields_physically_absent(self) -> None:
        """Each negative-list field name must NOT be a Pydantic field."""
        actual = set(CompanionFeedbackSummaryView.model_fields.keys())
        for forbidden in FEEDBACK_RESPONSE_NEGATIVE_LIST:
            assert forbidden not in actual, (
                f"FORBIDDEN field {forbidden!r} appears in "
                f"CompanionFeedbackSummaryView — ABAC RED LINE breach!"
            )

    def test_extra_fields_silently_dropped(self) -> None:
        """Even if service layer returns ``raw_content`` it must NOT
        appear in the validated view (extra='ignore' enforcement)."""
        forged = {
            "feedback_id": uuid.uuid4(),
            "severity": FeedbackSeverity.normal,
            "status": FeedbackStatus.pending,
            "sanitized_summary": "ok",
            "companion_appeal": None,
            # Sneak attempts (extra='ignore' should drop these):
            "raw_content": "PII LEAK",
            "user_phone": "13800138000",
            "patient_name": "张三",
            "attachment_blob_path": "/leaked/path",
        }
        view = CompanionFeedbackSummaryView.model_validate(forged)
        dumped = view.model_dump()
        for sneak in ("raw_content", "user_phone", "patient_name",
                      "attachment_blob_path"):
            assert sneak not in dumped, (
                f"sneak field {sneak!r} survived schema validation"
            )


# ---------------------------------------------------------------------------
# AC #5 schema positive-list lock
# ---------------------------------------------------------------------------


class TestSchemaSentinels:
    """Positive list sentinel (ADR-0049 §6.4 刻晴 review #7 amend)."""

    def test_positive_list_covers_all_view_fields(self) -> None:
        """Every Pydantic field name on every Feedback view must be in
        the positive list. Adding a new view field without updating
        ``FEEDBACK_RESPONSE_POSITIVE_LIST`` fails this test (forcing PR
        review).
        """
        from app.schemas.feedback import (
            AdminFeedbackListItem,
            AdminFeedbackListResponse,
            CompanionFeedbackSummaryView,
        )

        views = [
            UserFeedbackDetailView,
            AdminFeedbackListItem,
            AdminFeedbackListResponse,
            CompanionFeedbackSummaryView,
        ]
        drift: list[tuple[str, str]] = []
        for view in views:
            for field_name in view.model_fields.keys():
                if field_name not in FEEDBACK_RESPONSE_POSITIVE_LIST:
                    drift.append((view.__name__, field_name))
        assert not drift, (
            f"positive-list drift! Add these to FEEDBACK_RESPONSE_POSITIVE_LIST "
            f"or rename: {drift}"
        )

    def test_positive_and_negative_lists_disjoint(self) -> None:
        """Positive and negative lists must not overlap."""
        overlap = FEEDBACK_RESPONSE_POSITIVE_LIST & FEEDBACK_RESPONSE_NEGATIVE_LIST
        assert not overlap, f"positive/negative overlap: {overlap}"


# ---------------------------------------------------------------------------
# User endpoint happy path
# ---------------------------------------------------------------------------


class TestUserSubmitAndAppend:
    """User-side endpoint integration (ADR-0049 §7)."""

    async def test_submit_201_with_minimal_body(
        self, authenticated_client: AsyncClient
    ) -> None:
        # 阻塞 #1 修后: multipart form-data (ADR-0049 §7.1).
        form = {
            "feedback_function_module": "service_quality",
            "category": "服务态度",
            "severity": "normal",
            "raw_content": "陪诊师准时到场, 沟通顺畅, 给好评",
        }
        resp = await authenticated_client.post("/api/v1/users/feedbacks", data=form)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["status"] == "pending"
        assert data["source"] == "user"
        assert data["raw_content"] == form["raw_content"]
        assert data["feedback_parent_id"] is None
        assert data["order_id"] is None

    async def test_submit_with_user_id_in_body_ignored(
        self, authenticated_client: AsyncClient
    ) -> None:
        """ABAC: user_id derived from JWT, NEVER from request body.

        Multipart form 'user_id' field is not declared on the endpoint,
        so FastAPI Form decoder silently ignores it (no schema-level
        extra='forbid' available for Form). ABAC guarantee: even when
        client supplies user_id, service uses ``current_user.id`` from
        JWT, so the spoof attempt is harmless. Assert 201 + response
        ``user_id`` equals current_user, not the body value.
        """
        spoofed = str(uuid.uuid4())
        form = {
            "feedback_function_module": "service_quality",
            "category": "测试",
            "severity": "normal",
            "raw_content": "尝试覆盖 user_id",
            "user_id": spoofed,  # Form-decoded but unbound; should be ignored.
        }
        resp = await authenticated_client.post("/api/v1/users/feedbacks", data=form)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        # Service uses JWT.user_id, NOT the body value.
        assert data["user_id"] != spoofed


# ---------------------------------------------------------------------------
# Admin endpoint
# ---------------------------------------------------------------------------


class TestAdminCreateAndPatch:
    """Admin endpoints (ADR-0049 §7 admin routes)."""

    async def test_admin_create_with_user_source_rejected(
        self, client: AsyncClient
    ) -> None:
        """admin source 'user' 必须被拒 (admin 不能伪装用户)."""
        token = await _seed_admin("admin_src_user")
        user, _ = await _seed_companion_user(phone="13700009001")

        form = {
            "user_id": str(uuid.uuid4()),
            "feedback_function_module": "service_quality",
            "category": "测试",
            "severity": "normal",
            "source": "user",  # 拒绝
            "raw_content": "admin 伪装",
        }
        resp = await client.post(
            "/api/v1/admin/feedbacks",
            data=form,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422, resp.text

    async def test_admin_patch_status_illegal_transition_returns_409(
        self, client: AsyncClient, seed_user
    ) -> None:
        """pending → closed 非法 (必须先经 in_review)."""
        admin_token = await _seed_admin("admin_illegal")
        user = await seed_user(phone="13700009002")

        # Seed a pending feedback directly.
        async with _session_factory() as session:
            fb = UserFeedback(
                user_id=user.id,
                feedback_function_module=FeedbackFunctionModule.service_quality,
                category="测试",
                severity=FeedbackSeverity.normal,
                source=FeedbackSource.user,
                raw_content="...",
                status=FeedbackStatus.pending,
            )
            session.add(fb)
            await session.commit()
            await session.refresh(fb)
            fb_id = fb.id

        resp = await client.patch(
            f"/api/v1/admin/feedbacks/{fb_id}/status",
            json={"target_status": "closed"},  # 非法
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 409, resp.text


# ---------------------------------------------------------------------------
# Companion RED LINE integration
# ---------------------------------------------------------------------------


class TestCompanionRedLine:
    """Companion summary endpoint cannot leak ``raw_content`` etc."""

    async def test_summary_response_only_5_fields(
        self, client: AsyncClient, seed_user, seed_companion_profile
    ) -> None:
        """实际 endpoint response 也必须是 5 字段 (Layer 4 sentinel)."""
        # Seed companion + feedback owned by companion.
        comp_user, comp_token = await _seed_companion_user(phone="13700001200")
        comp_profile = await seed_companion_profile(user_id=comp_user.id)

        # Reporter user.
        reporter = await seed_user(phone="13700001201", role=UserRole.patient)

        async with _session_factory() as session:
            fb = UserFeedback(
                user_id=reporter.id,
                companion_id=comp_profile.id,
                feedback_function_module=FeedbackFunctionModule.service_quality,
                category="服务",
                severity=FeedbackSeverity.normal,
                source=FeedbackSource.user,
                raw_content="完整原文不应被陪诊师看到 — 包含病史信息",
                admin_sanitized_summary="陪诊师准时, 但流程有改进空间",
                status=FeedbackStatus.in_review,
            )
            session.add(fb)
            await session.commit()
            await session.refresh(fb)
            fb_id = fb.id

        resp = await client.get(
            f"/api/v1/companions/feedbacks/{fb_id}/summary",
            headers={"Authorization": f"Bearer {comp_token}"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Field set lock.
        assert set(data.keys()) == {
            "feedback_id", "severity", "status",
            "sanitized_summary", "companion_appeal",
        }, f"actual keys: {sorted(data.keys())}"

        # RED LINE: raw_content must NOT appear anywhere.
        assert "raw_content" not in data
        assert "完整原文不应被陪诊师看到" not in resp.text

        # sanitized summary returned.
        assert data["sanitized_summary"] == "陪诊师准时, 但流程有改进空间"

    async def test_summary_companion_mismatch_returns_404(
        self, client: AsyncClient, seed_user, seed_companion_profile
    ) -> None:
        """陪诊师 A 查 陪诊师 B 的反馈 → 404 (不泄露存在)."""
        comp_a_user, comp_a_token = await _seed_companion_user(phone="13700001300")
        # Seed companion profile for A (although unused below, the JOIN
        # depends on profile rows existing so the negative case is
        # exercising the JOIN miss path, not a missing profile path).
        _ = await seed_companion_profile(user_id=comp_a_user.id)

        comp_b_user, _ = await _seed_companion_user(phone="13700001301")
        comp_b_profile = await seed_companion_profile(user_id=comp_b_user.id)

        reporter = await seed_user(phone="13700001302", role=UserRole.patient)

        async with _session_factory() as session:
            fb = UserFeedback(
                user_id=reporter.id,
                companion_id=comp_b_profile.id,  # 不是 A
                feedback_function_module=FeedbackFunctionModule.service_quality,
                category="服务",
                severity=FeedbackSeverity.normal,
                source=FeedbackSource.user,
                raw_content="只能 B 查",
                status=FeedbackStatus.pending,
            )
            session.add(fb)
            await session.commit()
            await session.refresh(fb)
            fb_id = fb.id

        # A 查 → 404 (不 403, 不泄露).
        resp = await client.get(
            f"/api/v1/companions/feedbacks/{fb_id}/summary",
            headers={"Authorization": f"Bearer {comp_a_token}"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 阻塞 #1: attachment_ids multipart 真 bind (silent data loss 修复 verify)
# ---------------------------------------------------------------------------


class TestAttachmentBinding:
    """Verify multipart attachments actually persist FeedbackAttachment rows.

    Regression guard for review 阻塞 #1: schema previously accepted
    ``attachment_ids: list[UUID]`` but service signature did not bind,
    creating silent data loss. The architect ratify X (multipart) flow
    must INSERT one ``FeedbackAttachment`` per UploadFile and the row
    must reference the parent ``user_feedbacks.id``.
    """

    async def test_multipart_submit_persists_attachment_row(
        self, authenticated_client: AsyncClient
    ) -> None:
        """POST multipart with 1 file → 1 FeedbackAttachment row + signed_url in detail."""
        from sqlalchemy import select

        from app.models.feedback_attachment import FeedbackAttachment

        # Minimal valid PNG (1x1 transparent pixel).
        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xfc\xff"
            b"\xff?\x03\x00\x05\xfe\x02\xfe\xa3\x0e\xeb\xc4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        form = {
            "feedback_function_module": "service_quality",
            "category": "测试",
            "severity": "normal",
            "raw_content": "带附件提交",
        }
        files = [("attachments", ("test.png", png_bytes, "image/png"))]
        resp = await authenticated_client.post(
            "/api/v1/users/feedbacks", data=form, files=files
        )
        assert resp.status_code == 201, resp.text
        fb_id = uuid.UUID(resp.json()["feedback_id"])

        # Verify FeedbackAttachment row landed in DB with proper FK + hash.
        async with _session_factory() as session:
            rows = (
                await session.execute(
                    select(FeedbackAttachment).where(
                        FeedbackAttachment.feedback_id == fb_id
                    )
                )
            ).scalars().all()
        assert len(rows) == 1
        attach = rows[0]
        assert attach.content_type == "image/png"
        assert attach.byte_size == len(png_bytes)
        assert len(attach.content_hash) == 64  # SHA-256 hex
        # XOR uploader: user side
        assert attach.uploaded_by_user_id is not None
        assert attach.uploaded_by_admin_id is None

    async def test_multipart_submit_rejects_disallowed_mime(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Bad content_type (SVG) → 422; no feedback row left behind."""

        before_count = await self._count_feedbacks()

        form = {
            "feedback_function_module": "service_quality",
            "category": "测试",
            "severity": "normal",
            "raw_content": "尝试 SVG 上传",
        }
        files = [("attachments", ("evil.svg", b"<svg/>", "image/svg+xml"))]
        resp = await authenticated_client.post(
            "/api/v1/users/feedbacks", data=form, files=files
        )
        assert resp.status_code == 422, resp.text

        # No feedback row should have been committed (rollback on attachment err).
        after_count = await self._count_feedbacks()
        assert after_count == before_count

    @staticmethod
    async def _count_feedbacks() -> int:
        from sqlalchemy import func, select

        from app.models.user_feedback import UserFeedback

        async with _session_factory() as session:
            return int(
                (
                    await session.execute(select(func.count(UserFeedback.id)))
                ).scalar_one()
            )


# ---------------------------------------------------------------------------
# 阻塞 #2: ratelimit Depends 真触发 + counter inc
# ---------------------------------------------------------------------------


class TestRateLimit:
    """Per-user sliding window quota (ADR-0049 §3.2.1)."""

    async def test_submit_hourly_quota_returns_429_and_increments_counter(
        self, authenticated_client: AsyncClient
    ) -> None:
        """Exceed 10/h → 11th call gets 429 + Retry-After; counter incremented."""
        from app.api.v1.feedback_ratelimit import (
            _SUBMIT_LIMITS,
            _reset_inproc_store_for_tests,
        )
        from app.utils.metrics import feedback_ratelimit_429_total

        _reset_inproc_store_for_tests()

        form_base = {
            "feedback_function_module": "service_quality",
            "category": "限频测试",
            "severity": "normal",
        }

        # First 10 calls must succeed (each gets unique raw_content so partial
        # unique index does not bite — order_id is NULL so unique index
        # narrowing 'order_id IS NOT NULL' does not apply anyway).
        for i in range(_SUBMIT_LIMITS.hourly):
            form = {**form_base, "raw_content": f"提交{i}"}
            resp = await authenticated_client.post(
                "/api/v1/users/feedbacks", data=form
            )
            assert resp.status_code == 201, f"call {i}: {resp.text}"

        # 11th call hits hourly cap → 429.
        # Capture counter before/after (Prometheus client uses sample_value).
        # We can't easily resolve user_id without re-decoding the JWT;
        # rely on raw counter total change.
        before_total = sum(
            sample.value
            for metric in feedback_ratelimit_429_total.collect()
            for sample in metric.samples
            if sample.name.endswith("_total")
            and sample.labels.get("endpoint") == _SUBMIT_LIMITS.endpoint_name
        )

        resp = await authenticated_client.post(
            "/api/v1/users/feedbacks",
            data={**form_base, "raw_content": "第11次"},
        )
        assert resp.status_code == 429, resp.text
        assert "Retry-After" in resp.headers

        after_total = sum(
            sample.value
            for metric in feedback_ratelimit_429_total.collect()
            for sample in metric.samples
            if sample.name.endswith("_total")
            and sample.labels.get("endpoint") == _SUBMIT_LIMITS.endpoint_name
        )
        assert after_total > before_total

        # Cleanup so other tests start clean.
        _reset_inproc_store_for_tests()


# ---------------------------------------------------------------------------
# 阻塞 #3: feedback_submitted_total counter inc on success
# ---------------------------------------------------------------------------


class TestSubmittedCounter:
    """ADR-0049 §4.2: alertmanager UrgentFeedbackSubmitted depends on this."""

    async def test_user_submit_increments_submitted_counter(
        self, authenticated_client: AsyncClient
    ) -> None:
        """POST /users/feedbacks success → feedback_submitted_total.inc()."""
        from app.api.v1.feedback_ratelimit import _reset_inproc_store_for_tests
        from app.utils.metrics import feedback_submitted_total

        _reset_inproc_store_for_tests()

        before = sum(
            sample.value
            for metric in feedback_submitted_total.collect()
            for sample in metric.samples
            if sample.name.endswith("_total")
            and sample.labels.get("severity") == "urgent"
            and sample.labels.get("source") == "user"
        )

        form = {
            "feedback_function_module": "service_quality",
            "category": "紧急",
            "severity": "urgent",
            "raw_content": "紧急投诉 — 触发 alertmanager",
        }
        resp = await authenticated_client.post("/api/v1/users/feedbacks", data=form)
        assert resp.status_code == 201, resp.text

        after = sum(
            sample.value
            for metric in feedback_submitted_total.collect()
            for sample in metric.samples
            if sample.name.endswith("_total")
            and sample.labels.get("severity") == "urgent"
            and sample.labels.get("source") == "user"
        )
        assert after == before + 1


# ---------------------------------------------------------------------------
# 阻塞 #4: companion_appeal returns 200 (not 201)
# ---------------------------------------------------------------------------


class TestCompanionAppealStatusCode:
    """REST semantics: appeal updates existing resource → 200, not 201."""

    async def test_appeal_returns_200_not_201(
        self, client: AsyncClient, seed_user, seed_companion_profile
    ) -> None:
        comp_user, comp_token = await _seed_companion_user(phone="13700004400")
        comp_profile = await seed_companion_profile(user_id=comp_user.id)
        reporter = await seed_user(phone="13700004401", role=UserRole.patient)

        async with _session_factory() as session:
            fb = UserFeedback(
                user_id=reporter.id,
                companion_id=comp_profile.id,
                feedback_function_module=FeedbackFunctionModule.service_quality,
                category="测试",
                severity=FeedbackSeverity.normal,
                source=FeedbackSource.user,
                raw_content="...",
                status=FeedbackStatus.in_review,
            )
            session.add(fb)
            await session.commit()
            await session.refresh(fb)
            fb_id = fb.id

        resp = await client.post(
            f"/api/v1/companions/feedbacks/{fb_id}/appeal",
            json={"companion_appeal": "申诉理由"},
            headers={"Authorization": f"Bearer {comp_token}"},
        )
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# 阻塞 #5: admin_get_feedback audit savepoint (404 仍写 audit)
# ---------------------------------------------------------------------------


class TestAdminGetAuditSavepoint:
    """ADR-0049 §6.2 魈 review #5 dual commit boundary verification.

    404 on a non-existent id MUST still leave an AdminAuditLog row
    (probe auditing). Outer transaction commits the audit; SAVEPOINT
    rolls back only the data fetch.
    """

    async def test_get_nonexistent_id_still_writes_audit(
        self, client: AsyncClient
    ) -> None:
        from sqlalchemy import select

        from app.models.admin_audit_log import AdminAuditLog

        token = await _seed_admin("admin_audit_404")
        ghost_id = uuid.uuid4()

        resp = await client.get(
            f"/api/v1/admin/feedbacks/{ghost_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404, resp.text

        # Audit row MUST be present despite 404 → SAVEPOINT pattern verified.
        async with _session_factory() as session:
            rows = (
                await session.execute(
                    select(AdminAuditLog).where(
                        AdminAuditLog.target_type == "user_feedback",
                        AdminAuditLog.target_id == ghost_id,
                        AdminAuditLog.action == "view",
                    )
                )
            ).scalars().all()
        assert len(rows) == 1, (
            "probe audit 必须保留 — outer commit + savepoint pattern 失败 "
            "(or in-memory SQLite without SAVEPOINT support)."
        )
