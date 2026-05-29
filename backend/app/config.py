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
