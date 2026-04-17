"""
SMS Service — pluggable SMS provider.

Supports:
  - mock   : print to console (dev/test)
  - aliyun : Alibaba Cloud SMS (China)
  - tencent: Tencent Cloud SMS (China)

Provider is selected by ``settings.sms_provider``.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import settings
from app.core.pii import mask_phone

logger = logging.getLogger(__name__)


class SMSProvider:
    """Abstract base for SMS providers."""

    async def send(self, phone: str, code: str) -> bool:
        raise NotImplementedError


class MockSMSProvider(SMSProvider):
    """Prints OTP to console. For development and testing only."""

    async def send(self, phone: str, code: str) -> bool:
        logger.info("[MOCK SMS] OTP for %s: ******", mask_phone(phone))
        # DEV 屏幕打印保留明文以方便本地联调；生产用真实提供商不会走到这里
        print(f"[DEV] OTP for {phone}: {code}")
        return True


class AliyunSMSProvider(SMSProvider):
    """
    Alibaba Cloud SMS provider.

    Requires settings:
      - sms_access_key
      - sms_access_secret
      - sms_sign_name
      - sms_template_code
    """

    def __init__(self):
        self.access_key = settings.sms_access_key
        self.access_secret = settings.sms_access_secret
        self.sign_name = settings.sms_sign_name
        self.template_code = settings.sms_template_code
        self._has_credentials = bool(self.access_key and self.access_secret)

    async def send(self, phone: str, code: str) -> bool:
        if not self._has_credentials:
            logger.warning(
                "Aliyun SMS credentials not configured, falling back to mock"
            )
            print(f"[DEV-FALLBACK] OTP for {phone}: {code}")
            return True

        try:
            import httpx
            import hashlib
            import hmac
            import base64
            import time
            import uuid
            from urllib.parse import quote_plus

            # Alibaba Cloud SMS API (SendSms)
            params: dict[str, Any] = {
                "AccessKeyId": self.access_key,
                "Action": "SendSms",
                "Format": "JSON",
                "PhoneNumbers": phone,
                "RegionId": "cn-hangzhou",
                "SignName": self.sign_name,
                "SignatureMethod": "HMAC-SHA1",
                "SignatureNonce": str(uuid.uuid4()),
                "SignatureVersion": "1.0",
                "TemplateCode": self.template_code,
                "TemplateParam": f'{{"code":"{code}"}}',
                "Timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "Version": "2017-05-25",
            }

            # Build signature
            sorted_params = sorted(params.items())
            query_string = "&".join(
                f"{quote_plus(k)}={quote_plus(v)}" for k, v in sorted_params
            )
            sign_str = f"GET&{quote_plus('/')}&{quote_plus(query_string)}"
            signature = base64.b64encode(
                hmac.new(
                    f"{self.access_secret}&".encode("utf-8"),
                    sign_str.encode("utf-8"),
                    hashlib.sha1,
                ).digest()
            ).decode("utf-8")
            params["Signature"] = signature

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://dysmsapi.aliyuncs.com/",
                    params=params,
                    timeout=10,
                )

            data = resp.json()
            if data.get("Code") == "OK":
                logger.info("SMS sent to %s via Aliyun", mask_phone(phone))
                return True
            else:
                logger.error(
                    "Aliyun SMS failed for %s: %s %s",
                    mask_phone(phone),
                    data.get("Code"),
                    data.get("Message"),
                )
                return False

        except Exception as e:
            logger.error("Aliyun SMS exception: %s", e, exc_info=True)
            return False


class TencentSMSProvider(SMSProvider):
    """
    Tencent Cloud SMS provider.

    Requires settings:
      - sms_access_key (SecretId)
      - sms_access_secret (SecretKey)
      - sms_sign_name
      - sms_template_code
      - sms_sdk_app_id
    """

    def __init__(self):
        self.secret_id = settings.sms_access_key
        self.secret_key = settings.sms_access_secret
        self.sign_name = settings.sms_sign_name
        self.template_id = settings.sms_template_code
        self.sdk_app_id = getattr(settings, "sms_sdk_app_id", "")
        self._has_credentials = bool(self.secret_id and self.secret_key)

    async def send(self, phone: str, code: str) -> bool:
        if not self._has_credentials:
            logger.warning(
                "Tencent SMS credentials not configured, falling back to mock"
            )
            print(f"[DEV-FALLBACK] OTP for {phone}: {code}")
            return True

        try:
            import httpx
            import hashlib
            import hmac
            import json
            import time

            # Tencent Cloud SMS API v3
            timestamp = int(time.time())
            date = time.strftime("%Y-%m-%d", time.gmtime(timestamp))
            service = "sms"
            host = "sms.tencentcloudapi.com"

            # Ensure phone has country code
            if not phone.startswith("+"):
                phone = f"+86{phone}"

            payload = json.dumps({
                "SmsSdkAppId": self.sdk_app_id,
                "SignName": self.sign_name,
                "TemplateId": self.template_id,
                "TemplateParamSet": [code],
                "PhoneNumberSet": [phone],
            })

            # TC3-HMAC-SHA256 signing
            def _sign(key: bytes, msg: str) -> bytes:
                return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

            hashed_payload = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            http_request = f"POST\n/\n\ncontent-type:application/json\nhost:{host}\n\ncontent-type;host\n{hashed_payload}"
            credential_scope = f"{date}/{service}/tc3_request"
            string_to_sign = f"TC3-HMAC-SHA256\n{timestamp}\n{credential_scope}\n{hashlib.sha256(http_request.encode('utf-8')).hexdigest()}"

            secret_date = _sign(f"TC3{self.secret_key}".encode("utf-8"), date)
            secret_service = _sign(secret_date, service)
            secret_signing = _sign(secret_service, "tc3_request")
            signature = hmac.new(
                secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256
            ).hexdigest()

            authorization = (
                f"TC3-HMAC-SHA256 "
                f"Credential={self.secret_id}/{credential_scope}, "
                f"SignedHeaders=content-type;host, "
                f"Signature={signature}"
            )

            headers = {
                "Authorization": authorization,
                "Content-Type": "application/json",
                "Host": host,
                "X-TC-Action": "SendSms",
                "X-TC-Version": "2021-01-11",
                "X-TC-Timestamp": str(timestamp),
            }

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"https://{host}",
                    content=payload,
                    headers=headers,
                    timeout=10,
                )

            data = resp.json()
            send_status = (
                data.get("Response", {})
                .get("SendStatusSet", [{}])[0]
                .get("Code", "")
            )
            if send_status == "Ok":
                logger.info("SMS sent to %s via Tencent", mask_phone(phone))
                return True
            else:
                logger.error(
                    "Tencent SMS failed for %s: %s", mask_phone(phone), data
                )
                return False

        except Exception as e:
            logger.error("Tencent SMS exception: %s", e, exc_info=True)
            return False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_sms_provider() -> SMSProvider:
    name = settings.sms_provider
    if name == "aliyun":
        return AliyunSMSProvider()
    elif name == "tencent":
        return TencentSMSProvider()
    return MockSMSProvider()
