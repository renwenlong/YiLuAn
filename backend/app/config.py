import base64

from pydantic import model_validator
from pydantic_settings import BaseSettings

# ADR-0029: dev 环境用的 envelope key 默认值（32 字节全 'x'，base64 编码）。
# 生产**必须** override（见 model_validator）。
_DEV_PII_ENVELOPE_KEY = base64.b64encode(b"x" * 32).decode("ascii")


class Settings(BaseSettings):
    # App
    app_name: str = "YiLuAn API"
    app_version: str = "0.1.0"
    debug: bool = True
    environment: str = "development"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/yiluan"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # JWT
    jwt_secret_key: str = "dev-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Azure Storage
    azure_storage_connection_string: str = ""
    azure_storage_container_avatars: str = "avatars"
    azure_storage_container_chat: str = "chat-images"

    # S2-DEV-016 / ADR-0045: Storage backend selector (local | azure)
    # Phase A: local (default, filesystem + HMAC signed URL).
    # Phase B: azure (mock until 21Vianet account + ENV ready, real azure-storage-blob SDK).
    storage_backend: str = "local"
    # Azure cert image container (used when storage_backend=azure).
    azure_storage_account_name: str = ""
    azure_storage_container_cert: str = "yiluan-cert-dev"

    # S3-DEV-001 / ADR-0046 §3.3: Contract storage WORM policy switch.
    # prod=true (Azure Blob immutability Locked 7y), staging=false (避免测试数据 7y 占用).
    # 默认 false 安全 default; 部署时 prod env 必须显式置 true。
    s3_contract_immutability_enabled: bool = False

    # S3-DEV-001 / ADR-0046 §3.2: Contract patient pseudonym salt (与 cert image salt 独立).
    contract_pseudonym_salt: str = ""  # 必须在 prod env 显式设置

    # S3-DEV-001-CONTRACT-SERVICE-CORE / ADR-0046 r5 §3 amend (gap 3):
    # Contract template version, MVP 阶段写死 v1.0.0 (ContractTemplate 表
    # 不立, 后续 admin 多模板需求出现时立独立 ADR + 表). hash 公式 +
    # _render_pdf 读同一个 settings, single source of truth.
    contract_template_version: str = "v1.0.0"

    # S3-BUG-003: AI blocklist startup probe 严格加载开关.
    # True 时, lifespan startup 检 prohibited-keywords.yml 未加载 → raise
    # BlocklistStartupError, FastAPI 拒启. 默认 False (dev/test 保 fail-open).
    # 运维语义: env.staging / env.canary / env.production 都设 True
    # (不仅依靠 environment 字段—— env.staging/env.canary 现在是
    # ENVIRONMENT=development 以便 dev-OTP, 不能用 settings.environment
    # 判别 prod-like). 详见 docs/ops/blocklist-yml-deployment.md.
    ai_blocklist_strict_load: bool = False

    # S3-DEV-001-CONTRACT-PICKUP-CRON / 魈 EVENT-WIRING 拍板:
    # Contract generate pickup cron 启用开关。默认 False — CORE PR 合并后
    # cron 仍 disabled (因 _render_pdf 目前只产出最小合法 PDF stub,
    # 不应写入真实合同 storage). PDF-RENDER task (uuid 33ac1174)
    # 实装 PDF 渲染后, 通过 env 改 True 开启.
    contract_generate_pickup_enabled: bool = False

    # Pickup cron 单轮处理批量 (避免锁占用过久).
    contract_generate_pickup_batch_size: int = 20

    # Pickup cron 触发间隔 (秒). 默认 60s (与 ai_summary worker 同节奏).
    contract_generate_pickup_interval_seconds: int = 60

    # S3-DEV-001-CONTRACT-WORM-COMPENSATION: WORM repair cron
    # 默认 True — 只 set policy 是幂等 no-op-on-success, 不会产生空合同副作用.
    # 生产如需强制暂停 (e.g. Azure 全面 outage 避免重起 retry storm) 才设 False.
    contract_worm_repair_enabled: bool = True

    # WORM repair cron 单轮批量 (避免锁占用过久).
    contract_worm_repair_batch_size: int = 50

    # WORM repair cron 触发间隔 (秒). 默认 3600s (每小时) — acceptance criterion #3.
    contract_worm_repair_interval_seconds: int = 3600

    # S3-DEV-002-HOT-RELOAD: AI blocklist Redis pub/sub hot reload
    # 默认 True (与 KEYWORD-FILTER 一起灰度, prod 多副本需要秒级生效);
    # 设 False 仅在开发/CI 环境 (单进程 cold reload 足够).
    ai_blocklist_pubsub_enabled: bool = True

    # S3-DEV-002-PREP-GENERATE-WITH-BUDGETGUARD / ADR-0048 §8 P4:
    # Preparation package generate cron (每 1min tick).
    # 默认 True — 生产用需; 测试/CI 可设 False 避免 AsyncIOScheduler 启动后
    # 后台跳 LLM 调用.
    prep_generate_enabled: bool = True

    # Prep generate cron 单轮处理批量 (避免锁占用过久).
    prep_generate_batch_size: int = 10

    # Apple Sign-In (W18-A)
    # TODO(PM): supply real values for production. See `placeholders` doc.
    apple_team_id: str = ""  # TODO: 10-char Apple Developer Team ID
    apple_client_id: str = ""  # TODO: Service ID (web) or Bundle ID (iOS), used as JWT `aud`
    apple_jwks_url: str = "https://appleid.apple.com/auth/keys"
    apple_issuer: str = "https://appleid.apple.com"
    # When true (dev/test), skip JWKS signature verification but still validate claims.
    apple_mock_verify: bool = False

    # APNs
    apns_key_id: str = ""
    apns_team_id: str = ""
    apns_bundle_id: str = "com.yiluan.app"

    # WeChat Mini Program
    wechat_app_id: str = ""
    wechat_app_secret: str = ""

    # SMS
    sms_provider: str = "mock"  # mock / aliyun / tencent
    sms_access_key: str = ""
    sms_access_secret: str = ""
    sms_sign_name: str = ""
    sms_template_code: str = ""
    sms_sdk_app_id: str = ""  # Tencent Cloud only

    # Payment
    payment_provider: str = "mock"  # mock / wechat
    wechat_pay_mch_id: str = ""  # 微信支付商户号
    wechat_pay_api_key_v3: str = ""  # v3 API 密钥
    wechat_pay_cert_serial: str = ""  # 证书序列号
    wechat_pay_private_key_path: str = ""  # 商户私钥路径
    wechat_pay_notify_url: str = ""  # 回调通知 URL
    wechat_pay_platform_cert_path: str = ""  # 微信平台证书路径（用于验签）

    # Admin
    admin_api_token: str = "dev-admin-token"

    # PII (A21-02b / D-033)
    # 用于 hash_phone() 等 PII 字段的 salt。
    # ⚠️ 生产必须覆盖此值（通过 PII_HASH_SALT 环境变量）。
    # 默认值仅供开发 / 测试，**绝不可在生产环境使用**。
    # 如需未来轮换，请保留旧 salt 兼容历史 hash 数据。
    pii_hash_salt: str = "yiluan-dev-salt-do-not-use-in-prod"

    # ADR-0029: emergency PII 落库加密 envelope key（base64 编码 32 字节 / AES-256）。
    # dev 默认值仅用于本地 / CI；生产环境必须 override，且应来自 KMS / Secret Manager。
    pii_envelope_key: str = _DEV_PII_ENVELOPE_KEY

    # CORS
    cors_origins: list[str] = ["*"]

    # [F-03] Emergency / 客服热线
    # 当患者点击紧急呼叫且未配置紧急联系人时使用此号码（占位，由运维注入）。
    emergency_hotline: str = "4001234567"

    # Scheduler (D-018)
    scheduler_enabled: bool = True  # 生产开启；测试/CLI 可关闭

    # WebSocket 同用户最大并发连接数 (D-020)
    # 超限时「踢最老」：关闭该用户最早建立的那条连接，放新连接进来。
    # 默认 3：手机 + Pad + 桌面；0 表示不限制（调试用）。
    ws_max_connections_per_user: int = 3

    # WebSocket Pub/Sub (D-019)
    ws_pubsub_enabled: bool = True  # 生产多副本必开；本地/测试可关
    ws_pubsub_channel: str = "yiluan:ws:notifications"

    # WebSocket 聊天 Pub/Sub (D-019 Update / 聊天通道迁移)
    ws_chat_pubsub_enabled: bool = True  # 生产多副本必开；本地/测试可关
    ws_chat_pubsub_channel: str = "yiluan:ws:chat"
    # ADR-0036 §2.4 family-share broker；独立 channel 隔离, key_field=order_id
    ws_share_pubsub_enabled: bool = True
    ws_share_pubsub_channel: str = "yiluan:ws:share"
    # ADR-0036 §2.4 per-token 连接数硬上限（防 token 泄露后 idle 占资源）
    ws_share_max_connections_per_token: int = 3
    # ADR-0036 §2.4 位置 cache TTL；用于断线重连首帧补偿
    ws_share_loc_cache_ttl_seconds: int = 60

    # ---- S2-DEV-005: AI summary job (DeepSeek + cost caps) ----
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    # 价格表（元/千 token）——仅用于成本估算，与代理货币实际报价同步调整。
    deepseek_price_input_per_1k_yuan: float = 0.001
    deepseek_price_output_per_1k_yuan: float = 0.002
    # 单单费用上限（¥）——超限截断已生成部分，不重试。
    ai_per_order_budget_yuan: float = 0.05
    # 全平台日预算上限（¥）——超限后直接降级模板文案。
    ai_daily_budget_yuan: float = 50.0

    # ─────────── [S3-DEV-002] AI 就诊准备包 budget (ADR-0048 §3) ───────────
    # 单订单成本上限（¥）——内容更长，单价 2x S2 摘要。
    s3_prep_cost_per_order_yuan: float = 0.10
    # 全平台日预算上限（¥）——独立 2x S2 摘要日预算。
    s3_prep_daily_budget_yuan: float = 100.0
    # 是否启用 S3 准备包 AI 调用（false → 全走 template fallback）。
    s3_prep_enabled: bool = True
    # 软门限百分比（90 = 日预算用到 90% 时 fire warn alert，仍允许调用）。
    s3_prep_fallback_threshold_pct: int = 90

    # ─────────── [S3-DEV-004] S4_FEEDBACK_SUMMARY budget axis 占位 (ADR-0049 §10.1) ───────────
    # PRD-004 v0.3 §安全边界：S3 阶段反馈摘要必走 admin 人工脱敏，不作 AI 自动。
    # S4 阶段启用 AI 自动脱敏。本配置在 S3 阶段强制 enabled=false 。
    s4_feedback_summary_enabled: bool = False  # S3 阶段强制 false; startup healthcheck 拒 true
    s4_feedback_summary_daily_budget_yuan: float = 0.0  # 0 = 全 fallback 人工
    s4_feedback_summary_cost_per_call_yuan: float = 0.0  # S4 填
    s4_feedback_summary_fallback_to_manual: bool = True  # S4 启用后仍保留人工 fallback

    # S3 启动守护（ADR-0049 §10.1 刻晴 r2 amend）。production/staging 必 true；
    # dev/test 仅 warning。strict=true 时 healthcheck 失败 → 进程 exit 1 拒启动。
    s3_startup_healthcheck_strict: bool = False

    # ─────────── [S3-DEV-004] feedback 限频（ADR-0049 §3.2.1 胡桃 Gap 3 amend）───────────
    feedback_submit_per_user_hourly: int = 10
    feedback_submit_per_user_daily: int = 50
    feedback_append_per_user_hourly: int = 30
    feedback_append_per_user_daily: int = 100
    # S3-DEV-002-PROMPT-VERSIONING AC#3: 启动时校验 DB-active prompt 与 git 端
    # 文件存在 + commit hash 匹配。production 必开，dev/test 可关。
    prompt_versions_validate_on_startup: bool = True
    # 启动校验的 git 仓库根（绝对路径或 None → 自动从 backend/ 向上找 .git）。
    prompt_versions_repo_root: str | None = None
    # DeepSeek 调用的 outbound timeout / retry / circuit breaker 参数。
    deepseek_timeout_seconds: float = 15.0
    deepseek_max_retries: int = 2
    # S2-DEV-006: 家属分享 token 24h 滚动窗口 distinct openid 阈值，
    # 超过则 scanner 自动 revoke（防 token 泄露）。
    share_distinct_accessor_threshold: int = 5
    # S2-DEV-011 OTP 双轴频控 (魈+刻晴双 review 红线)
    share_otp_token_daily_cap: int = 5  # 单 token / 24h 发码次数上限
    share_otp_phone_token_cap: int = 3  # 单手机号 / 1h 绑定不同 token 上限
    share_otp_ttl_seconds: int = 300  # OTP 码有效期 5min
    share_otp_code_length: int = 6

    # S2-OPS-011 火度门 feature flags（火度回滚 runbook 中可热切）。
    # FEATURE_SHARE_F2_ENABLED=false 后患者端不能新建 share_token
    # （已发的不受影响，仅不炭毒火度入口）。
    # 默认 True，指南火度闭闸全量 F2 时 OPS 手动切 False。
    feature_share_f2_enabled: bool = True

    # READONLY_SHARE_SESSIONS=true 后已发以 share_session 可读视图，
    # 但不可生新会话（POST /shares/{token}/session 拒 503）
    # 且不可走 WS（升级拒 503）。
    # 默认 False，指南火度异常时 OPS 手动切 True 冻结新会话。
    readonly_share_sessions: bool = False

    # ADR-0032 / D-044 Q3: 资金对账历史豁免 cutoff。
    # 早于该时刻产生的 amount_mismatch diff 视为已豁免，guard 不阻断订单
    # 状态机迁移。默认值 = ADR-0032 Accepted 的 UTC 时刻；生产部署可通过
    # ``RECONCILIATION_CUTOFF`` 环境变量覆盖（ISO-8601 字符串）。
    reconciliation_cutoff: str = "2026-04-28T00:00:00+00:00"

    # F-04 多维度评分权重（守时 / 专业 / 沟通 / 态度），默认等权 0.25。
    # 如需运营调整可通过环境变量覆盖；服务层会按权重重算总评分。
    review_weight_punctuality: float = 0.25
    review_weight_professionalism: float = 0.25
    review_weight_communication: float = 0.25
    review_weight_attitude: float = 0.25

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    @model_validator(mode="after")
    def validate_production_config(self):
        if self.environment != "production":
            return self

        # JWT 密钥不能是开发默认值
        if self.jwt_secret_key == "dev-secret-key-change-in-production":
            raise ValueError(
                "生产环境禁止使用默认 JWT 密钥，请设置 JWT_SECRET_KEY"
            )

        # 生产环境必须关闭 debug
        if self.debug:
            raise ValueError("生产环境必须设置 DEBUG=false")

        # CORS 安全：生产环境禁止通配源 + credentials 组合
        # 背景：Starlette CORSMiddleware 当 allow_origins 含 '*' 且
        # allow_credentials=True 时，会把 Access-Control-Allow-Origin 反射为
        # 请求 Origin，等价于「任意源 + 可带凭证」。即便我们目前用的是
        # bearer token（不在浏览器 credentials 范畴），也禁止此默认配置。
        if not self.cors_origins or "*" in self.cors_origins:
            raise ValueError(
                "生产环境 CORS_ORIGINS 不能为空或包含 '*'，请显式列出可信源"
                "（如 CORS_ORIGINS='https://admin.example.com,https://app.example.com'）"
            )

        # 微信支付凭证完整性检查
        if self.payment_provider == "wechat":
            missing = [
                name
                for name, val in [
                    ("WECHAT_PAY_MCH_ID", self.wechat_pay_mch_id),
                    ("WECHAT_PAY_API_KEY_V3", self.wechat_pay_api_key_v3),
                    ("WECHAT_PAY_CERT_SERIAL", self.wechat_pay_cert_serial),
                    ("WECHAT_PAY_PRIVATE_KEY_PATH", self.wechat_pay_private_key_path),
                ]
                if not val
            ]
            if missing:
                raise ValueError(
                    f"生产环境微信支付缺少凭证: {', '.join(missing)}"
                )

        # ADR-0029: PII 加密 / hash 密钥不得使用 dev 默认值
        if self.pii_envelope_key == _DEV_PII_ENVELOPE_KEY:
            raise ValueError(
                "生产环境禁止使用默认 PII_ENVELOPE_KEY，请从 KMS / Secret "
                "Manager 注入 base64 编码的 32 字节密钥"
            )
        if self.pii_hash_salt == "yiluan-dev-salt-do-not-use-in-prod":
            raise ValueError(
                "生产环境禁止使用默认 PII_HASH_SALT，请设置高熵随机串"
            )

        # W1-S1: 运维管理后台 / 定时任务回调使用的 admin token 不得为开发默认值或空串。
        # `require_admin_token` 拿这个值做常量时间比对；若不强制 override，
        # 任何知道默认值的人都能触发 /orders/check-expired 等运维端点。
        if self.admin_api_token in ("dev-admin-token", "", None):
            raise ValueError(
                "生产环境禁止使用默认 ADMIN_API_TOKEN，请设置高熵随机串"
            )

        # SMS 凭证完整性检查
        # 先拒绝 mock provider：生产环境上 mock = 什么也不发但谎报成功，用户收不到
        # 验证码还以为是运营问题。上古遗留 app/services/sms.py 的 silent
        # fallback 已被移除，这里是 defense-in-depth。
        if self.sms_provider == "mock":
            raise ValueError(
                "生产环境禁止 SMS_PROVIDER=mock，请设为 aliyun / tencent"
            )
        if self.sms_provider != "mock":
            missing = [
                name
                for name, val in [
                    ("SMS_ACCESS_KEY", self.sms_access_key),
                    ("SMS_ACCESS_SECRET", self.sms_access_secret),
                    ("SMS_SIGN_NAME", self.sms_sign_name),
                    ("SMS_TEMPLATE_CODE", self.sms_template_code),
                ]
                if not val
            ]
            if missing:
                raise ValueError(
                    f"生产环境 SMS ({self.sms_provider}) 缺少凭证: {', '.join(missing)}"
                )

        return self


settings = Settings()
