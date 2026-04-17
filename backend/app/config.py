from pydantic import model_validator
from pydantic_settings import BaseSettings


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

    # CORS
    cors_origins: list[str] = ["*"]

    # Scheduler (D-018)
    scheduler_enabled: bool = True  # 生产开启；测试/CLI 可关闭

    # WebSocket Pub/Sub (D-019)
    ws_pubsub_enabled: bool = True  # 生产多副本必开；本地/测试可关
    ws_pubsub_channel: str = "yiluan:ws:notifications"

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

        # SMS 凭证完整性检查
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
