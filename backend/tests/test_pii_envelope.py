"""ADR-0029 — PII envelope encryption / phone_hash 单元测试。"""
from __future__ import annotations

import base64

import pytest

from app.core import pii
from app.core.pii import (
    EnvelopeKey,
    decrypt_phone,
    encrypt_phone,
    hash_phone,
    mask_phone,
    phone_hash,
)


class TestEncryptDecryptRoundTrip:
    def test_encrypt_then_decrypt_returns_plaintext(self):
        ct = encrypt_phone("13800138000")
        assert isinstance(ct, bytes)
        # 密文是 base64 编码 → ASCII bytes，**绝不能** 等于明文
        assert b"13800138000" not in ct
        assert decrypt_phone(ct) == "13800138000"

    def test_encrypt_is_non_deterministic(self):
        """AES-GCM nonce 随机，相同明文每次密文不同（防字典攻击）。"""
        a = encrypt_phone("13800138000")
        b = encrypt_phone("13800138000")
        assert a != b
        assert decrypt_phone(a) == decrypt_phone(b) == "13800138000"

    def test_decrypt_corrupted_raises(self):
        ct = encrypt_phone("13800138000")
        # 翻转最后 1 字节 → tag 校验失败
        bad = bytearray(base64.b64decode(ct))
        bad[-1] ^= 0xFF
        bad_b64 = base64.b64encode(bytes(bad))
        with pytest.raises(Exception):
            decrypt_phone(bad_b64)

    def test_unicode_plaintext(self):
        ct = encrypt_phone("+86-138-0013-8000")
        assert decrypt_phone(ct) == "+86-138-0013-8000"


class TestPhoneHash:
    def test_deterministic(self):
        assert phone_hash("13800138000") == phone_hash("13800138000")

    def test_different_phones_different_hashes(self):
        assert phone_hash("13800138000") != phone_hash("13800138001")

    def test_64_char_hex(self):
        h = phone_hash("13800138000")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_empty_returns_empty(self):
        assert phone_hash("") == ""
        assert phone_hash(None) == ""

    def test_legacy_hash_phone_still_works(self):
        # 历史 SmsSendLog 仍然走 SHA256(salt+phone)
        assert hash_phone("13800138000", "salt") != phone_hash("13800138000")
        assert len(hash_phone("13800138000", "salt")) == 64


class TestEnvelopeKey:
    def test_load_from_env_uses_settings(self):
        key = EnvelopeKey.load_from_env()
        assert isinstance(key, EnvelopeKey)
        assert len(key.key_bytes) == 32

    def test_short_key_rejected(self):
        with pytest.raises(ValueError):
            EnvelopeKey(b"short")

    def test_rotate_returns_count(self):
        old = EnvelopeKey.load_from_env()
        # 用旧 key 加密一些 ciphertext
        cts = [encrypt_phone(f"1380013800{i}") for i in range(3)]
        new_raw = b"y" * 32
        new_key = EnvelopeKey(new_raw, key_id="envelope-v2")
        n = old.rotate(new_key, cts)
        assert n == 3


class TestMaskPhone:
    def test_basic(self):
        assert mask_phone("13812345678") == "138******78"

    def test_empty(self):
        assert mask_phone("") == ""
        assert mask_phone(None) == ""
