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

    # CORS
    cors_origins: list[str] = ["*"]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
