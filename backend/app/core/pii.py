"""PII 加密 / 脱敏 / 哈希辅助模块（ADR-0029 实现）。

本模块汇集三类能力：

1. **AES-256-GCM Envelope 加密**（``encrypt_phone`` / ``decrypt_phone``）
   - 用于将紧急联系人手机号、紧急事件被叫号码等强 PII **密文落库**。
   - 当前阶段使用 envelope key（从 ``settings.pii_envelope_key``
     base64 32 字节读取），W19+ 接 KMS（见 ``EnvelopeKey`` 类的占位）。
   - 密文格式：``base64(version || nonce || ciphertext || tag)``，version
     固定 0x01 用于将来支持 key 轮换/算法升级。

2. **HMAC-SHA256 phone hash**（``phone_hash``）
   - 输入：明文手机号 + ``settings.pii_hash_salt``。
   - 用于在不暴露明文的前提下做"按手机号查询"（如紧急联系人去重检查、
     运营按号检索 sms_send_log）。
   - 与历史 ``hash_phone(phone, salt)`` 的差异：``phone_hash`` 强制走
     HMAC-SHA256，且自动从 ``settings.pii_hash_salt`` 取 salt；旧的
     ``hash_phone`` 仍保留以保持向后兼容（A21-02b / D-033 已落地的
     SmsSendLog 沿用）。

3. **日志脱敏**（``mask_phone`` / ``mask_id_card``）
   - 用于日志、调试、审计明文展示场景。

使用示例：

    from app.core.pii import encrypt_phone, decrypt_phone, phone_hash

    ciphertext = encrypt_phone("13800138000")     # bytes，存 LargeBinary
    plaintext  = decrypt_phone(ciphertext)         # "13800138000"
    h          = phone_hash("13800138000")         # 64 char hex
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from typing import Iterable

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# Version byte 嵌在密文最前，方便 W19+ 接 KMS 时区分密文格式 / key id。
_CURRENT_VERSION: int = 0x01
_NONCE_LEN: int = 12  # AES-GCM 推荐 96-bit nonce


# ---------------------------------------------------------------------------
# Envelope Key 抽象（占位，W19 接 KMS）
# ---------------------------------------------------------------------------
class EnvelopeKey:
    """信封密钥占位实现。

    当前阶段：从 ``settings.pii_envelope_key``（base64 编码 32 字节）加载，
    在进程内常驻；W19+ 替换为真正的 KMS data-key 流程（每次加密向 KMS
    申请 data-key，密文与 wrapped-key 一并落库）。

    本类目前只实现：

    - ``load_from_env()``：从 settings 加载当前 key。
    - ``rotate(new_key, old_ciphertexts)``：占位接口，返回需要重新加密的
      条数；真实轮换工具会走 batch SELECT/UPDATE 流程。
    """

    def __init__(self, key_bytes: bytes, key_id: str = "envelope-v1") -> None:
        if len(key_bytes) != 32:
            raise ValueError(
                "EnvelopeKey requires exactly 32 bytes (AES-256), "
                f"got {len(key_bytes)}"
            )
        self._key = key_bytes
        self.key_id = key_id

    @property
    def key_bytes(self) -> bytes:
        return self._key

    @classmethod
    def load_from_env(cls) -> "EnvelopeKey":
        """从 ``settings.pii_envelope_key`` 加载当前 envelope key。"""
        # 延迟 import 以避免与 config 形成循环依赖
        from app.config import settings

        raw = settings.pii_envelope_key
        if not raw:
            raise ValueError(
                "PII_ENVELOPE_KEY is empty; refusing to start without an "
                "envelope key. In dev set it to base64.b64encode(b'x'*32)."
            )
        try:
            decoded = base64.b64decode(raw, validate=True)
        except Exception as exc:  # pragma: no cover - 配置错误
            raise ValueError(
                "PII_ENVELOPE_KEY must be valid base64 of a 32-byte key"
            ) from exc
        return cls(decoded)

    def rotate(
        self,
        new_key: "EnvelopeKey",
        old_ciphertexts: Iterable[bytes],
    ) -> int:
        """占位：批量重新加密旧密文（W19+ 实现真实 KMS 轮换）。

        当前实现：读出明文 → 用 new_key 重新加密 → 返回处理条数。
        生产轮换工具会基于此函数 + 数据库 UPDATE 完成 batch 重写。
        """
        count = 0
        for ct in old_ciphertexts:
            plaintext = _decrypt_with_key(self, ct)
            _ = _encrypt_with_key(new_key, plaintext)
            count += 1
        return count


# 进程内单例缓存：避免每次加密都重新 base64 解码
_cached_key: EnvelopeKey | None = None


def _get_envelope_key() -> EnvelopeKey:
    global _cached_key
    if _cached_key is None:
        _cached_key = EnvelopeKey.load_from_env()
    return _cached_key


def _reset_cached_envelope_key() -> None:
    """测试 / key 轮换时清空缓存。"""
    global _cached_key
    _cached_key = None


# ---------------------------------------------------------------------------
# 低层加解密（直接使用某把 key，不读 settings）
# ---------------------------------------------------------------------------
def _encrypt_with_key(key: EnvelopeKey, plaintext: str) -> bytes:
    if plaintext is None:
        raise ValueError("plaintext must not be None")
    if not isinstance(plaintext, str):
        raise TypeError("plaintext must be str")
    aesgcm = AESGCM(key.key_bytes)
    nonce = os.urandom(_NONCE_LEN)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    blob = bytes([_CURRENT_VERSION]) + nonce + ct
    return base64.b64encode(blob)


def _decrypt_with_key(key: EnvelopeKey, ciphertext: bytes) -> str:
    if ciphertext is None:
        raise ValueError("ciphertext must not be None")
    if isinstance(ciphertext, str):
        ciphertext = ciphertext.encode("ascii")
    try:
        blob = base64.b64decode(ciphertext, validate=True)
    except Exception as exc:
        raise ValueError("ciphertext is not valid base64") from exc
    if len(blob) < 1 + _NONCE_LEN + 16:  # version + nonce + min tag
        raise ValueError("ciphertext too short")
    version = blob[0]
    if version != _CURRENT_VERSION:
        raise ValueError(f"Unsupported PII ciphertext version: {version}")
    nonce = blob[1 : 1 + _NONCE_LEN]
    body = blob[1 + _NONCE_LEN :]
    aesgcm = AESGCM(key.key_bytes)
    pt = aesgcm.decrypt(nonce, body, associated_data=None)
    return pt.decode("utf-8")


# ---------------------------------------------------------------------------
# 高层 API（推荐使用）
# ---------------------------------------------------------------------------
def encrypt_phone(plaintext: str) -> bytes:
    """AES-256-GCM 加密手机号 → base64 字节，可直接存 ``LargeBinary`` 列。

    - 当前 envelope key 从 ``settings.pii_envelope_key`` 加载（base64 32 bytes）。
    - 同一明文每次加密结果不同（nonce 随机），符合 GCM 推荐做法。
    """
    return _encrypt_with_key(_get_envelope_key(), plaintext)


def decrypt_phone(ciphertext: bytes) -> str:
    """解密 ``encrypt_phone`` 产生的密文，返回明文手机号。"""
    return _decrypt_with_key(_get_envelope_key(), ciphertext)


def phone_hash(phone: str | None) -> str:
    """HMAC-SHA256(salt, phone) → 64 字符 hex。

    - salt 来自 ``settings.pii_hash_salt``，**生产必须 override**。
    - 用于按手机号查询时不暴露明文（如紧急联系人去重 / sms 检索）。
    - ``None`` / 空串返回空串，方便上层条件查询。
    """
    if not phone:
        return ""
    from app.config import settings

    salt = settings.pii_hash_salt
    if not salt:
        raise ValueError("phone_hash requires settings.pii_hash_salt to be set")
    mac = hmac.new(
        salt.encode("utf-8"),
        msg=phone.encode("utf-8"),
        digestmod=hashlib.sha256,
    )
    return mac.hexdigest()


# ---------------------------------------------------------------------------
# 历史 API（保持向后兼容）
# ---------------------------------------------------------------------------
def hash_phone(phone: str | None, salt: str) -> str:
    """[Legacy] SHA256(salt + phone) hex，A21-02b / D-033 SmsSendLog 沿用。

    新代码请优先使用 ``phone_hash`` (HMAC-SHA256)。本函数保留以兼容
    历史 sms_send_log 数据。
    """
    if not phone:
        return ""
    if not salt:
        raise ValueError("hash_phone requires a non-empty salt")
    return hashlib.sha256(f"{salt}{phone}".encode("utf-8")).hexdigest()


def mask_phone(phone: str | None) -> str:
    """掩码手机号：保留前 3 + 后 2，中间替换为 *。

    - `13812345678` → `138******78`
    - `+8613812345678` → `+861******78`
    - 短号或无效输入：原样部分遮蔽
    - None / 空字符串：返回空字符串
    """
    if not phone:
        return ""
    s = str(phone)
    n = len(s)
    if n <= 4:
        return "*" * n
    if n <= 8:
        return s[:2] + "*" * (n - 4) + s[-2:]
    prefix_len = 3
    if s.startswith("+"):
        prefix_len = min(4, n - 3)
    suffix_len = 2
    middle = n - prefix_len - suffix_len
    return s[:prefix_len] + "*" * middle + s[-suffix_len:]


def mask_id_card(id_card: str | None) -> str:
    """掩码身份证号：保留前 4 + 后 4，中间全部 *。"""
    if not id_card:
        return ""
    s = str(id_card)
    n = len(s)
    if n <= 8:
        return "*" * n
    return s[:4] + "*" * (n - 8) + s[-4:]
