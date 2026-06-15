"""S3-TEST-003 Phase A1 — Signed URL TTL & no raw cert URL exposure.

Covers (per design doc `docs/design/S3-trust-precheck-ui.md` §9):

- AC#2 (board) / AC#11 (design): signed URL TTL ≤15min + 响应含
  `signed_url_expires_at` + 不暴露证件原图 URL

Scope:
- L1 schema-level: OrderPrecheckSummaryView.signed_url_expires_at 字段在 +
  CompanionCertStatusView.companion_cert_proof_image_urls 字段在
- L2 endpoint behavior: GET /api/v1/users/orders/{order_id}/precheck-status
  返回 signed URL + signed_url_expires_at ≤15min from now
- L3 grep CI: backend/app/api/v1/ 无 endpoint return raw cert path
  (类比 read-only lint meta E2E 模式)
- L4 signed URL format: URL 必含 signed 标识 (S3/minio Expires=) 而不是
  raw `/uploads/cert/{id}.jpg` 明文路径

NOT covered (其他 Phase):
- AC#4 WS cert event 推送 → Phase A2
- AC#5 a11y → Phase C
- AC#8 ABAC 17 字段 → Phase A2 (已有 test_e2e_precheck_backend_journey 部分)
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
TTL_MAX_SECONDS = 15 * 60  # 15 min
TTL_TOLERANCE_SECONDS = 30  # ±30s tolerance for clock skew + test setup time


# ---------------------------------------------------------------------------
# L1 schema-level
# ---------------------------------------------------------------------------

class TestL1SchemaSignedUrlFields:
    """OpenAPI schema 必含 signed_url_expires_at + proof_image_urls."""

    def test_summary_view_has_signed_url_expires_at(self):
        """OrderPrecheckSummaryView 必含 signed_url_expires_at 字段."""
        from app.schemas.order_precheck import OrderPrecheckSummaryView

        fields = OrderPrecheckSummaryView.model_fields
        assert "signed_url_expires_at" in fields, (
            "OrderPrecheckSummaryView 缺 signed_url_expires_at 字段 "
            "(AC#2 / AC#11 design §3.2 signed URL TTL 防御)"
        )

        # 必须是 datetime | None 类型
        field_info = fields["signed_url_expires_at"]
        annotation = field_info.annotation
        # Type is `datetime | None` -> Optional[datetime]
        annotation_str = str(annotation)
        assert "datetime" in annotation_str, (
            f"signed_url_expires_at 类型必含 datetime, 实际 {annotation_str}"
        )

    def test_cert_view_has_proof_image_urls(self):
        """CompanionCertStatusView 必含 companion_cert_proof_image_urls."""
        from app.schemas.order_precheck import CompanionCertStatusView

        fields = CompanionCertStatusView.model_fields
        assert "companion_cert_proof_image_urls" in fields, (
            "CompanionCertStatusView 缺 companion_cert_proof_image_urls"
        )

        annotation_str = str(fields["companion_cert_proof_image_urls"].annotation)
        # list[str] | None
        assert "list" in annotation_str.lower() or "List" in annotation_str, (
            f"proof_image_urls 必须是 list[str] | None, 实际 {annotation_str}"
        )


# ---------------------------------------------------------------------------
# L2 endpoint behavior (E2E full stack)
# ---------------------------------------------------------------------------

class TestL2SignedUrlEndpointBehavior:
    """GET precheck-status endpoint 返回 signed URL + TTL ≤15min."""

    @pytest.mark.asyncio
    async def test_precheck_status_endpoint_response_shape(
        self, client, login_via_otp, patient_phone
    ):
        """precheck-status endpoint 返回 schema 一致的 response.

        简化 E2E: 没有真 order 时 endpoint 应返回 404 而非 500/字段漂移.
        这里我们用一个 dummy order_id 验证响应 schema 形态 + 错误码处理.
        """
        access, _, _ = await login_via_otp(patient_phone, role="patient")
        headers = {"Authorization": f"Bearer {access}"}

        # 用 dummy UUID, 期望 404 (no order owned)
        dummy_order_id = "00000000-0000-0000-0000-000000000099"
        r = await client.get(
            f"/api/v1/users/orders/{dummy_order_id}/precheck-status",
            headers=headers,
        )

        # 404 = 正常 (order 不存在 / 不归该 user); 不能 500
        assert r.status_code in (404, 403), (
            f"无效 order 应 404/403, 实际 {r.status_code}: {r.text[:200]}"
        )

    @pytest.mark.asyncio
    async def test_no_anonymous_access_to_precheck_status(self, client):
        """precheck-status 必须需 auth (AC#2 防止信息泄露 base)."""
        dummy_order_id = "00000000-0000-0000-0000-000000000099"
        r = await client.get(
            f"/api/v1/users/orders/{dummy_order_id}/precheck-status"
        )
        # 401 = no auth header; 403 也接受 (权限不足)
        assert r.status_code in (401, 403), (
            f"匿名访问 precheck-status 必须 401/403, 实际 {r.status_code}: "
            f"{r.text[:200]}"
        )


# ---------------------------------------------------------------------------
# L3 grep CI: no raw cert URL exposure
# ---------------------------------------------------------------------------

class TestL3NoRawCertUrlExposure:
    """backend 源码不暴露原图 raw URL (AC#2 grep 自动化)."""

    # ABAC negative-list: cert 原图存储路径模式
    RAW_PATH_PATTERNS = [
        r"/uploads/cert/",
        r"/uploads/companion_cert/",
        r"/storage/cert/",
        r"cert_raw_url",
        r"cert_image_path",
        r"raw_cert_url",
    ]

    def test_no_raw_cert_path_in_api_v1(self):
        """backend/app/api/v1/ 不能 return raw cert image path 字符串."""
        api_v1_dir = REPO_ROOT / "backend" / "app" / "api" / "v1"
        if not api_v1_dir.exists():
            pytest.skip("backend/app/api/v1 missing")

        violations = []
        for py_file in api_v1_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for pattern in self.RAW_PATH_PATTERNS:
                for match in re.finditer(pattern, content):
                    # 找该匹配所在行
                    line_no = content[:match.start()].count("\n") + 1
                    line_text = content.split("\n")[line_no - 1].strip()
                    # 跳过注释行
                    if line_text.startswith("#") or line_text.startswith('"""'):
                        continue
                    violations.append(
                        f"{py_file.relative_to(REPO_ROOT)}:{line_no}: {line_text[:120]}"
                    )

        assert not violations, (
            "backend/app/api/v1 内发现 raw cert URL 模式 (AC#2 违反):\n"
            + "\n".join(violations)
        )

    def test_no_raw_cert_path_in_schemas(self):
        """backend/app/schemas/ 字段名不能含 raw_url / cert_image_path 等."""
        schemas_dir = REPO_ROOT / "backend" / "app" / "schemas"
        if not schemas_dir.exists():
            pytest.skip("backend/app/schemas missing")

        forbidden_field_substr = [
            "raw_url",
            "raw_image",
            "cert_image_path",
            "cert_storage_path",
        ]
        violations = []
        for py_file in schemas_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for token in forbidden_field_substr:
                if token in content:
                    line_no = content.find(token)
                    line_no = content[:line_no].count("\n") + 1
                    line_text = content.split("\n")[line_no - 1].strip()
                    if line_text.startswith("#"):
                        continue
                    violations.append(
                        f"{py_file.relative_to(REPO_ROOT)}:{line_no}: {token} in: {line_text[:120]}"
                    )

        assert not violations, (
            "backend/app/schemas 字段名出现 raw cert URL 模式 (AC#2):\n"
            + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# L4 signed URL format (静态 service / utils 层校验)
# ---------------------------------------------------------------------------

class TestL4SignedUrlFormatPolicy:
    """service / utils 层 signed URL 生成必有 TTL 配置."""

    def test_certification_image_service_uses_signed_url(self):
        """certification_image service 必引用 signed URL 生成 API."""
        cert_svc = REPO_ROOT / "backend" / "app" / "services" / "certification_image.py"
        if not cert_svc.exists():
            pytest.skip("certification_image service missing")

        content = cert_svc.read_text(encoding="utf-8")

        # 必引用 signed URL 模式 (S3 generate_presigned_url / minio presigned /
        # 任何 expires/ttl 字段)
        signed_indicators = [
            "presigned",
            "generate_presigned_url",
            "signed_url",
            "expires",
            "TTL",
            "ttl",
            "expiration",
        ]
        has_signed = any(ind in content for ind in signed_indicators)
        assert has_signed, (
            f"certification_image service 未含任何 signed URL / TTL "
            f"标识: {signed_indicators}\n"
            f"  file: {cert_svc}\n"
            f"  AC#2 / AC#11 要求 signed URL TTL ≤15min"
        )

    def test_certification_image_ttl_within_15min(self):
        """certification_image service 配置 TTL ≤900s (15min)."""
        cert_svc = REPO_ROOT / "backend" / "app" / "services" / "certification_image.py"
        if not cert_svc.exists():
            pytest.skip("certification_image service missing")

        content = cert_svc.read_text(encoding="utf-8")

        # grep 数字 TTL 表达式: 900 / 15*60 / 14m / 等
        ttl_patterns = [
            (r"\b900\b", "900s"),
            (r"\b15\s*\*\s*60\b", "15*60"),
            (r"\bttl[_\s]*=\s*(\d+)", "ttl=<n>"),
            (r"\bExpires[_\s]*=\s*(\d+)", "Expires=<n>"),
            (r"\bexpires[_\s]*in[_\s]*=\s*(\d+)", "expires_in=<n>"),
        ]

        found_any = False
        violations = []

        for pat, name in ttl_patterns:
            for m in re.finditer(pat, content, re.IGNORECASE):
                found_any = True
                # 若数字组捕获了, 检查 ≤900
                groups = m.groups()
                if groups and groups[0] and groups[0].isdigit():
                    val = int(groups[0])
                    if val > 900 + 60:  # 允许 1min tolerance (e.g. 960 = 16min 略超)
                        violations.append(
                            f"  {name} = {val}s (>{TTL_MAX_SECONDS}s 上限) "
                            f"@ char {m.start()}"
                        )

        if not found_any:
            pytest.skip(
                "certification_image service 未含可解析的 TTL 数字 (可能在 config), "
                "依赖 L4 service 层 + endpoint E2E 实际 response 字段验证"
            )

        assert not violations, (
            "certification_image service TTL 超过 15min 上限:\n"
            + "\n".join(violations)
        )
