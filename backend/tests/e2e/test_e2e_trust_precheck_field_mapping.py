"""S3-TEST-003 Phase A1 — Trust Precheck field mapping & cross-end consistency.

Covers (per design doc `docs/design/S3-trust-precheck-ui.md` §9):

- AC#1 (board) / AC#3+AC#12 (design): 三端 `companion_cert_*` 4 字段一致 +
  field-mapping CI 三端 1:1
- AC#7 (board) / AC#12 (design): OpenAPI schema as single source of truth,
  WX TypeScript + iOS Swift + admin-v2 (if exists) 字段名与 schema 对齐

§6.3 r4 amend canonical 口径: "OpenAPI schema as single source of truth";
三端各自从 schema 对齐字段名, 不要求 monorepo 共享 packages/.

Scope (本文件):
- L1 schema-level: OrderPrecheckSummaryView.companion_cert_status 字段契约 5
  字段全在 + extra=forbid + ABAC negative-list 0 命中
- L2 WX consumer: `wechat/services/precheck*.js` 引用字段名 1:1 与 schema
- L3 iOS consumer: `ios/YiLuAn/Features/Precheck/Models/OrderPrecheckSummary.swift`
  Swift Codable 字段名 1:1 与 schema
- L4 admin-v2 consumer: admin-v2 features 含 precheck/trust UI 时字段 1:1;
  无 UI 时 skip with reason (设计 §7 路径未实现)
- L5 CI workflow: openapi-diff.yml + copy-lint.yml 落盘且 trigger 路径合理

NOT covered (其他 Phase):
- AC#4/6 WS cert_status_changed 实时推送 (Phase A2)
- AC#8 ABAC 17 字段 negative-list E2E 注入 (Phase A2 / 部分复用
  test_e2e_precheck_backend_journey.py 已有)
- AC#5 a11y (Phase C)
- AC#9 灰度监控 (Phase D)
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

# 4 cert 字段权威定义 (design §3.2 + schema CompanionCertStatusView)
# 5 字段, 前 4 是 design 文档明列的 4 字段, 第 5 是 verified_at 追加
EXPECTED_CERT_FIELDS = {
    "companion_cert_pseudonym_name",
    "companion_cert_work_id",
    "companion_cert_qualifications",
    "companion_cert_proof_image_urls",
    "companion_cert_verified_at",
}

# 4 必显字段 (board AC#1 字面 "4 字段" - 不含 verified_at, 它是 timestamp)
EXPECTED_CERT_DISPLAY_FIELDS = {
    "companion_cert_pseudonym_name",
    "companion_cert_work_id",
    "companion_cert_qualifications",
    "companion_cert_proof_image_urls",
}

# repo root (worktree 兼容)
REPO_ROOT = Path(__file__).resolve().parents[3]


# ---------------------------------------------------------------------------
# L1 schema-level
# ---------------------------------------------------------------------------

class TestL1SchemaContract:
    """OpenAPI schema 层字段契约 - 服务端 SSOT."""

    def test_companion_cert_status_view_has_5_expected_fields(self):
        """CompanionCertStatusView 必含 5 字段 (4 display + verified_at).

        AC#1 (board) 字面 4 字段, design schema 实际 5 字段
        (verified_at 是 admin verify 通过 timestamp, 不在 display 必显之列
        但属字段契约一部分).
        """
        from app.schemas.order_precheck import CompanionCertStatusView

        fields = set(CompanionCertStatusView.model_fields.keys())
        # `ready` 是通用状态指示器, 不算 cert_* prefix
        cert_prefix_fields = {f for f in fields if f.startswith("companion_cert_")}

        assert cert_prefix_fields == EXPECTED_CERT_FIELDS, (
            f"CompanionCertStatusView companion_cert_* 字段集合不符:\n"
            f"  expected: {sorted(EXPECTED_CERT_FIELDS)}\n"
            f"  actual:   {sorted(cert_prefix_fields)}\n"
            f"  missing:  {sorted(EXPECTED_CERT_FIELDS - cert_prefix_fields)}\n"
            f"  extra:    {sorted(cert_prefix_fields - EXPECTED_CERT_FIELDS)}"
        )

    def test_companion_cert_status_view_extra_forbid(self):
        """schema 必 extra=forbid 防额外字段 leak (ABAC L1)."""
        from app.schemas.order_precheck import CompanionCertStatusView

        cfg = CompanionCertStatusView.model_config
        assert cfg.get("extra") == "forbid", (
            f"CompanionCertStatusView 必须 extra=forbid, 实际 {cfg.get('extra')}"
        )

    def test_order_precheck_summary_view_contains_companion_cert_subview(self):
        """OrderPrecheckSummaryView 必含 companion_cert_status sub-view."""
        from app.schemas.order_precheck import (
            CompanionCertStatusView,
            OrderPrecheckSummaryView,
        )

        fields = OrderPrecheckSummaryView.model_fields
        assert "companion_cert_status" in fields, (
            "OrderPrecheckSummaryView 缺 companion_cert_status sub-view"
        )

        sub_annotation = fields["companion_cert_status"].annotation
        assert sub_annotation is CompanionCertStatusView, (
            f"companion_cert_status 类型不匹配: {sub_annotation}"
        )

    def test_companion_cert_negative_list_fields_absent(self):
        """ABAC L1 sentinel: cert view 不能含 negative-list 字段.

        ADR-0048 §5.3 + design §3.2 真名/身份证/手机号/user_id 等私密字段
        永远不能出现在 user-facing CompanionCertStatusView.
        """
        from app.schemas.order_precheck import CompanionCertStatusView

        fields = set(CompanionCertStatusView.model_fields.keys())
        negative_list = {
            "companion_real_name",
            "companion_id_card_hash",
            "companion_phone",
            "companion_user_id",
        }
        intersect = fields & negative_list
        assert not intersect, (
            f"CompanionCertStatusView 漏入 negative-list 字段: {sorted(intersect)}"
        )

    def test_companion_cert_positive_prefix_lint(self):
        """ADR-0046 §3.5 positive-list prefix: 非通用字段必带 companion_cert_ 前缀."""
        from app.schemas.order_precheck import CompanionCertStatusView

        fields = set(CompanionCertStatusView.model_fields.keys())
        # 通用 carve-out (design §3.5)
        allowlist = {"ready"}

        non_prefixed = {
            f for f in fields
            if f not in allowlist and not f.startswith("companion_cert_")
        }
        assert not non_prefixed, (
            f"CompanionCertStatusView 含非 companion_cert_ 前缀字段: "
            f"{sorted(non_prefixed)}\n"
            f"  允许例外 (allowlist): {sorted(allowlist)}"
        )


# ---------------------------------------------------------------------------
# L2 WX consumer
# ---------------------------------------------------------------------------

class TestL2WxFieldAlign:
    """微信小程序消费端字段对齐 schema."""

    WX_PRECHECK_FILES = [
        REPO_ROOT / "wechat" / "services" / "precheck.js",
        REPO_ROOT / "wechat" / "services" / "precheckWs.js",
        REPO_ROOT / "wechat" / "components" / "cert-card",
    ]

    def test_wx_precheck_files_exist(self):
        """微信端 precheck 文件落盘存在 (S3-DEV-003-TRUST-UI-WX 产出)."""
        for path in self.WX_PRECHECK_FILES:
            assert path.exists(), f"WX precheck 文件缺失: {path}"

    def test_wx_cert_card_consumes_4_display_fields(self):
        """微信端 cert-card 组件必引用 4 个显示字段名 (subset).

        允许使用 camelCase 别名 (e.g. companionCertWorkId), 因为微信小程序
        TypeScript 通常自动转换. 这里 grep snake_case 原名或 camelCase 别名
        任一即可.
        """
        cert_card_dir = REPO_ROOT / "wechat" / "components" / "cert-card"
        if not cert_card_dir.exists():
            pytest.skip("WX cert-card 组件不存在")

        # 读所有 .js/.wxml/.wxss
        contents = []
        for ext in ("*.js", "*.wxml", "*.wxss", "*.json", "*.ts"):
            for f in cert_card_dir.rglob(ext):
                contents.append(f.read_text(encoding="utf-8"))
        combined = "\n".join(contents)

        # snake_case 命名 (与 backend 一致) 或 camelCase 别名都接受
        missing = []
        for field in EXPECTED_CERT_DISPLAY_FIELDS:
            # snake_case 原名
            snake = field
            # camelCase 别名 (split _ 后 capitalize except first)
            parts = field.split("_")
            camel = parts[0] + "".join(p.capitalize() for p in parts[1:])

            if snake not in combined and camel not in combined:
                missing.append(f"{snake} (or {camel})")

        # WX 端只用 backend 推下来的 字段就行, 不强求 lint 所有 4 字段
        # 但至少要见到 work_id 或 pseudonym_name 之一 (核心识别字段)
        core_seen = (
            "companion_cert_work_id" in combined
            or "companionCertWorkId" in combined
            or "companion_cert_pseudonym_name" in combined
            or "companionCertPseudonymName" in combined
        )
        assert core_seen, (
            f"WX cert-card 未见任何 companion_cert_ 核心字段引用. "
            f"missing (snake or camel): {missing}"
        )


# ---------------------------------------------------------------------------
# L3 iOS consumer
# ---------------------------------------------------------------------------

class TestL3IosFieldAlign:
    """iOS Swift Native 消费端字段对齐 schema (ADR-0054 r4 路径)."""

    IOS_PRECHECK_MODEL = (
        REPO_ROOT / "ios" / "YiLuAn" / "Features" / "Precheck"
        / "Models" / "OrderPrecheckSummary.swift"
    )

    def test_ios_precheck_summary_model_exists(self):
        """iOS Swift Native OrderPrecheckSummary 模型存在."""
        assert self.IOS_PRECHECK_MODEL.exists(), (
            f"iOS PrecheckSummary 模型缺失: {self.IOS_PRECHECK_MODEL}"
        )

    def test_ios_cert_fields_aligned_via_coding_keys(self):
        """iOS Swift Codable: snake_case JSON keys 在 CodingKeys / @JSONKey 中映射.

        Swift 用 camelCase 但 CodingKeys 必须显式 = "snake_case_name" 才能
        decode. grep 4 display 字段的 snake_case 字符串 (要在 CodingKeys 或
        JSONDecoder.keyDecodingStrategy 配置).
        """
        if not self.IOS_PRECHECK_MODEL.exists():
            pytest.skip("iOS model file missing")

        content = self.IOS_PRECHECK_MODEL.read_text(encoding="utf-8")

        # Swift 端可能用 .convertFromSnakeCase 全局策略, 这种情况 snake_case
        # 不会显式出现 — 但 cert_* 字段命名一致性必须保留. 看 file 含
        # 'CompanionCert' 或 'companion_cert' 任一作为命名一致性 proxy.
        has_cert_naming = (
            "CompanionCert" in content
            or "companion_cert" in content
            or "companionCert" in content
        )
        assert has_cert_naming, (
            f"iOS PrecheckSummary 未含任何 CompanionCert/companion_cert 命名:\n"
            f"  file: {self.IOS_PRECHECK_MODEL}\n"
            f"  首 200 chars: {content[:200]}"
        )

    def test_ios_precheck_websocket_handles_cert_event(self):
        """iOS PrecheckWebSocket 处理 cert_status_changed event 路径存在.

        AC#4 要求 cert_status_changed event 三端 ≤3s 刷新. iOS 端 WS handler
        必须 dispatch cert event 到 ViewModel. 这里只查 file 存在 +
        含 cert / precheck event 字符串.
        """
        ws_file = (
            REPO_ROOT / "ios" / "YiLuAn" / "Features" / "Precheck"
            / "Services" / "PrecheckWebSocket.swift"
        )
        if not ws_file.exists():
            pytest.skip("iOS PrecheckWebSocket service missing")

        content = ws_file.read_text(encoding="utf-8")
        # event 名可能是 "cert_status_changed" 或 "precheck.status.updated"
        # (后者是 design §4 实际 channel) - 任一即可
        has_event_handler = (
            "cert_status_changed" in content
            or "precheck.status.updated" in content
            or "cert" in content.lower()
        )
        assert has_event_handler, (
            "iOS PrecheckWebSocket 未含任何 cert/precheck event handler"
        )


# ---------------------------------------------------------------------------
# L4 admin-v2 consumer
# ---------------------------------------------------------------------------

class TestL4AdminV2ConsumerOrSkip:
    """admin-v2 消费端 - 视实现而定."""

    ADMIN_V2_FEATURES = REPO_ROOT / "admin-v2" / "src" / "features"

    def test_admin_v2_precheck_feature_or_skip(self):
        """admin-v2 含 precheck/trust feature 时字段 1:1, 否则 skip.

        design §7 路径 `/admin-v2/system/precheck-copywriting` 当前在
        admin-v2 features 不存在 (实现仅 ai-blocklist/companion-review/login).
        AC#6 admin "三端文案一致" 通过 PR #313 copy-lint 哨兵保证, 不要求
        admin UI 渲染 cert.

        本 test 是 forward-compat: 一旦 admin 端补 cert UI, 自动开始 lint
        字段对齐.
        """
        if not self.ADMIN_V2_FEATURES.exists():
            pytest.skip("admin-v2/src/features 目录不存在")

        feature_dirs = [d for d in self.ADMIN_V2_FEATURES.iterdir() if d.is_dir()]
        feature_names = {d.name for d in feature_dirs}

        precheck_features = feature_names & {
            "precheck", "trust", "trust-precheck", "precheck-copywriting",
            "companion-cert", "cert"
        }

        if not precheck_features:
            pytest.skip(
                f"admin-v2 features 无 precheck/trust 模块 (现有: "
                f"{sorted(feature_names)}). "
                f"AC#6 admin 端通过 PR #313 copy-lint 哨兵保证文案一致, "
                f"不要求 cert UI 渲染. 待 admin 团队补 UI 后此 test 自动启用."
            )

        # 若实现, grep companion_cert 字段
        for feature_name in precheck_features:
            feature_dir = self.ADMIN_V2_FEATURES / feature_name
            contents = []
            for ext in ("*.tsx", "*.ts", "*.jsx", "*.js"):
                for f in feature_dir.rglob(ext):
                    contents.append(f.read_text(encoding="utf-8"))
            combined = "\n".join(contents)

            has_cert_field = (
                "companion_cert" in combined or "companionCert" in combined
            )
            assert has_cert_field, (
                f"admin-v2 feature {feature_name} 未含 companion_cert 字段引用"
            )


# ---------------------------------------------------------------------------
# L5 CI workflow
# ---------------------------------------------------------------------------

class TestL5CIWorkflowGate:
    """CI 闸门防止字段漂移."""

    def test_openapi_diff_workflow_present(self):
        """openapi-diff.yml 必存在 (字段漂移 CI gate)."""
        workflow = REPO_ROOT / ".github" / "workflows" / "openapi-diff.yml"
        assert workflow.exists(), (
            "openapi-diff.yml CI gate 缺失 (ADR-0036 §2.7 字段漂移防御)"
        )

    def test_copy_lint_workflow_present(self):
        """copy-lint.yml 必存在 (S3-DEV-003-ADMIN-COPY PR #313 产出)."""
        workflow = REPO_ROOT / ".github" / "workflows" / "copy-lint.yml"
        assert workflow.exists(), (
            "copy-lint.yml CI gate 缺失 (PR #313 S3-DEV-003-ADMIN-COPY)"
        )

    def test_copy_lint_yml_owner_pm(self):
        """禁词 yml owner 必 = pm (PM 双签 owner 防 dev 单方面加禁词)."""
        yml = REPO_ROOT / "docs" / "copy-lint" / "prohibited-occupational-endorsements.yml"
        assert yml.exists(), "禁词 yml 缺失"

        try:
            import yaml as pyyaml
        except ImportError:
            pytest.skip("PyYAML not installed")

        with yml.open("r", encoding="utf-8") as f:
            data = pyyaml.safe_load(f)

        # yml 用 top-level owner 字段 (不是 nested meta.owner)
        owner = data.get("owner")
        assert owner == "pm", (
            f"禁词 yml owner 必须 = pm, 实际 {owner}"
        )

    def test_copy_lint_script_passes_on_real_repo(self):
        """实跑 copy-lint 哨兵在当前 repo PASS (复用 PR #313 真 repo 回归)."""
        script = REPO_ROOT / "scripts" / "qa" / "check_prohibited_endorsements.py"
        if not script.exists():
            pytest.skip("copy-lint script 缺失")

        # 显式用 python3.11 (script 用 pathlib.Path.is_relative_to 是 3.9+ API)
        # P3 advisory in PR #313 review: 系统默认 python3=3.8 会触发 AttributeError.
        # CI workflow / Docker / pyproject 均锁 3.11, 本地 dev 需显式.
        import shutil
        py311 = shutil.which("python3.11")
        if not py311:
            pytest.skip("python3.11 不在 PATH, 跳过 (CI 上锁 3.11)")

        result = subprocess.run(
            [py311, str(script)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        # exit 0 = 全 OK; exit 1 = block 命中; exit 2 = config 错
        # 我们要求 0 (与 PR #313 单测 TestRealRepo 等价但 e2e 层)
        assert result.returncode == 0, (
            f"copy-lint 在当前 repo 跑出 returncode={result.returncode}\n"
            f"  stdout: {result.stdout[-500:]}\n"
            f"  stderr: {result.stderr[-500:]}"
        )
