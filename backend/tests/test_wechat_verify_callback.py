"""
Tests for WechatPaymentProvider verify_callback — RSA-SHA256 signature
verification and AES-256-GCM decryption.
"""

import base64
import json
import datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.x509.oid import NameOID

from app.exceptions import BadRequestException
from app.services.payment_service import (
    MockPaymentProvider,
    WechatPaymentProvider,
    _platform_cert_cache,
)


# ---------------------------------------------------------------------------
# Helpers: generate test RSA key pair + self-signed cert  (per-session)
# ---------------------------------------------------------------------------

def _generate_rsa_key_pair():
    """Generate a 2048-bit RSA private key."""
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _generate_self_signed_cert(private_key):
    """Create a self-signed X.509 certificate from the private key."""
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "WeChatPay Test Cert"),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.now(datetime.UTC))
        .not_valid_after(datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=365))
        .sign(private_key, hashes.SHA256())
    )
    return cert


def _sign_callback(private_key, timestamp: str, nonce: str, body: str) -> str:
    """Produce base64 RSA-SHA256 signature over the WeChat verify string."""
    verify_str = f"{timestamp}\n{nonce}\n{body}\n"
    sig = private_key.sign(
        verify_str.encode("utf-8"),
        padding.PKCS1v15(),
        hashes.SHA256(),
    )
    return base64.b64encode(sig).decode("utf-8")


def _encrypt_resource(api_key_v3: str, nonce: str, associated_data: str, plaintext: str) -> str:
    """AES-256-GCM encrypt and return base64 ciphertext."""
    aesgcm = AESGCM(api_key_v3.encode("utf-8"))
    ct = aesgcm.encrypt(
        nonce.encode("utf-8"),
        plaintext.encode("utf-8"),
        associated_data.encode("utf-8") if associated_data else None,
    )
    return base64.b64encode(ct).decode("utf-8")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_cert_cache():
    """Ensure cert cache is clean between tests."""
    _platform_cert_cache.clear()
    yield
    _platform_cert_cache.clear()


@pytest.fixture()
def rsa_key():
    return _generate_rsa_key_pair()


@pytest.fixture()
def cert_pem_path(rsa_key, tmp_path):
    """Write a self-signed PEM cert to a temp file and return its path."""
    cert = _generate_self_signed_cert(rsa_key)
    path = tmp_path / "platform_cert.pem"
    path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return str(path)


API_KEY_V3 = "a]b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"  # exactly 32 bytes


@pytest.fixture()
def wechat_provider(cert_pem_path, monkeypatch):
    """Create a WechatPaymentProvider with test credentials."""
    monkeypatch.setattr("app.services.payment_service.settings.payment_provider", "wechat")
    monkeypatch.setattr("app.services.payment_service.settings.wechat_pay_mch_id", "1234567890")
    monkeypatch.setattr("app.services.payment_service.settings.wechat_pay_api_key_v3", API_KEY_V3)
    monkeypatch.setattr("app.services.payment_service.settings.wechat_pay_cert_serial", "SERIAL001")
    monkeypatch.setattr("app.services.payment_service.settings.wechat_pay_private_key_path", "")
    monkeypatch.setattr("app.services.payment_service.settings.wechat_pay_notify_url", "")
    monkeypatch.setattr("app.services.payment_service.settings.wechat_app_id", "wx_test")
    monkeypatch.setattr("app.services.payment_service.settings.wechat_pay_platform_cert_path", cert_pem_path)
    return WechatPaymentProvider()


# ===========================================================================
# Test cases
# ===========================================================================


@pytest.mark.asyncio
class TestVerifySignature:
    """RSA-SHA256 signature verification."""

    async def test_valid_signature_passes(self, wechat_provider, rsa_key):
        """A correctly signed callback should be verified successfully."""
        timestamp = "1688000000"
        nonce = "testnonce123"
        body_dict = {"id": "evt_001", "event_type": "TRANSACTION.SUCCESS"}
        body_str = json.dumps(body_dict)

        sig = _sign_callback(rsa_key, timestamp, nonce, body_str)

        headers = {
            "wechatpay-timestamp": timestamp,
            "wechatpay-nonce": nonce,
            "wechatpay-signature": sig,
            "wechatpay-serial": "SERIAL001",
        }

        result = await wechat_provider.verify_callback(headers, body_str.encode())
        assert result["id"] == "evt_001"

    async def test_tampered_signature_fails(self, wechat_provider, rsa_key):
        """A tampered/invalid signature must raise BadRequestException."""
        timestamp = "1688000000"
        nonce = "testnonce123"
        body_str = '{"id": "evt_002"}'

        # Sign the real body, then tamper the signature
        sig = _sign_callback(rsa_key, timestamp, nonce, body_str)
        # Flip several characters to ensure it's actually invalid base64-decodable but wrong
        bad_sig = sig[:-8] + "XXXXXXXX"

        headers = {
            "wechatpay-timestamp": timestamp,
            "wechatpay-nonce": nonce,
            "wechatpay-signature": bad_sig,
            "wechatpay-serial": "SERIAL001",
        }

        with pytest.raises(BadRequestException, match="签名验证失败"):
            await wechat_provider.verify_callback(headers, body_str.encode())

    async def test_missing_headers_fails(self, wechat_provider):
        """Missing required Wechatpay-* headers should raise BadRequestException."""
        headers = {
            "wechatpay-timestamp": "1688000000",
            # missing nonce, signature, serial
        }

        with pytest.raises(BadRequestException, match="缺少必要 header"):
            await wechat_provider.verify_callback(headers, b'{"test": true}')

    async def test_missing_single_header_reports_name(self, wechat_provider):
        """Error message should name the specific missing header."""
        headers = {
            "wechatpay-timestamp": "1688000000",
            "wechatpay-nonce": "abc",
            "wechatpay-signature": "sig",
            # missing serial
        }

        with pytest.raises(BadRequestException, match="Wechatpay-Serial"):
            await wechat_provider.verify_callback(headers, b'{}')


@pytest.mark.asyncio
class TestDecryptResource:
    """AES-256-GCM decryption of callback resource."""

    async def test_decrypt_success(self, wechat_provider, rsa_key):
        """Correctly encrypted resource should be decrypted to original JSON."""
        nonce_aes = "unique_nonce1"
        associated_data = "transaction"
        plaintext = json.dumps({"out_trade_no": "YLA123", "trade_state": "SUCCESS"})
        ciphertext_b64 = _encrypt_resource(API_KEY_V3, nonce_aes, associated_data, plaintext)

        body_dict = {
            "id": "notify_001",
            "event_type": "TRANSACTION.SUCCESS",
            "resource": {
                "ciphertext": ciphertext_b64,
                "nonce": nonce_aes,
                "associated_data": associated_data,
            },
        }
        body_str = json.dumps(body_dict)

        # Sign so _verify_signature passes
        timestamp = "1688000000"
        nonce_sig = "nonce_for_sig"
        sig = _sign_callback(rsa_key, timestamp, nonce_sig, body_str)

        headers = {
            "wechatpay-timestamp": timestamp,
            "wechatpay-nonce": nonce_sig,
            "wechatpay-signature": sig,
            "wechatpay-serial": "SERIAL001",
        }

        result = await wechat_provider.verify_callback(headers, body_str.encode())
        # resource should now be the decrypted dict
        assert result["resource"]["out_trade_no"] == "YLA123"
        assert result["resource"]["trade_state"] == "SUCCESS"

    async def test_wrong_key_fails(self, wechat_provider, rsa_key, monkeypatch):
        """Decryption with wrong api_key_v3 should fail."""
        correct_key = API_KEY_V3
        wrong_key = "ZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZZ"

        nonce_aes = "wrong_key_nce"
        plaintext = json.dumps({"out_trade_no": "YLA999"})
        # Encrypt with the WRONG key
        ciphertext_b64 = _encrypt_resource(wrong_key, nonce_aes, "", plaintext)

        body_dict = {
            "id": "notify_bad",
            "resource": {
                "ciphertext": ciphertext_b64,
                "nonce": nonce_aes,
                "associated_data": "",
            },
        }
        body_str = json.dumps(body_dict)

        timestamp = "1688000000"
        nonce_sig = "signonceXYZ"
        sig = _sign_callback(rsa_key, timestamp, nonce_sig, body_str)

        headers = {
            "wechatpay-timestamp": timestamp,
            "wechatpay-nonce": nonce_sig,
            "wechatpay-signature": sig,
            "wechatpay-serial": "SERIAL001",
        }

        with pytest.raises(BadRequestException, match="解密失败"):
            await wechat_provider.verify_callback(headers, body_str.encode())


@pytest.mark.asyncio
class TestMockModeSkipsVerification:
    """When payment_provider=mock (no credentials), verification is skipped."""

    async def test_mock_provider_skips_verification(self):
        """MockPaymentProvider.verify_callback should return without signature check."""
        provider = MockPaymentProvider()
        body = json.dumps({"out_trade_no": "YLA100", "trade_state": "SUCCESS"}).encode()

        result = await provider.verify_callback({}, body)
        assert result["verified"] is True

    async def test_wechat_no_credentials_skips_verification(self, monkeypatch):
        """WechatPaymentProvider with empty credentials should behave like mock."""
        monkeypatch.setattr("app.services.payment_service.settings.wechat_pay_mch_id", "")
        monkeypatch.setattr("app.services.payment_service.settings.wechat_pay_api_key_v3", "")
        monkeypatch.setattr("app.services.payment_service.settings.wechat_pay_cert_serial", "")
        monkeypatch.setattr("app.services.payment_service.settings.wechat_pay_private_key_path", "")
        monkeypatch.setattr("app.services.payment_service.settings.wechat_pay_notify_url", "")
        monkeypatch.setattr("app.services.payment_service.settings.wechat_app_id", "")
        monkeypatch.setattr("app.services.payment_service.settings.wechat_pay_platform_cert_path", "")
        provider = WechatPaymentProvider()

        body = json.dumps({"out_trade_no": "YLA200"}).encode()
        result = await provider.verify_callback({}, body)
        assert result["out_trade_no"] == "YLA200"


@pytest.mark.asyncio
class TestCertificateCache:
    """Platform certificate cache behaviour."""

    async def test_cert_is_cached_after_first_load(self, wechat_provider, rsa_key, cert_pem_path):
        """After one successful verify, the cert should be in cache."""
        assert len(_platform_cert_cache) == 0

        timestamp = "1688000000"
        nonce = "cache_test_n"
        body_str = '{"id": "cache_test"}'
        sig = _sign_callback(rsa_key, timestamp, nonce, body_str)

        headers = {
            "wechatpay-timestamp": timestamp,
            "wechatpay-nonce": nonce,
            "wechatpay-signature": sig,
            "wechatpay-serial": "SERIAL001",
        }

        await wechat_provider.verify_callback(headers, body_str.encode())

        cache_key = f"{cert_pem_path}:SERIAL001"
        assert cache_key in _platform_cert_cache
