"""S2-DEV-016 / ADR-0045 §3 P1 StorageBackend ABC + impls 单测.

\u8986\u76d6:
  - LocalStorageBackend: put / sign_read_url / verify_sig / open + tamper/expire/path 防御
  - AzureBlobStorageBackend (Phase A mock): put / sign_read_url / verify_sig / open
  - Factory: STORAGE_BACKEND=local|azure 切换 + singleton + reset
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.exceptions import (
    BadRequestException,
    ForbiddenException,
    NotFoundException,
)
from app.services.storage_backend import (
    AzureBlobStorageBackend,
    LocalStorageBackend,
    StoredObject,
    get_storage_backend,
    reset_storage_backend,
)

# ---------- LocalStorageBackend ----------


class TestLocalStorageBackend:
    def setup_method(self, _m):
        reset_storage_backend()

    def test_put_and_sign_and_open_round_trip(self, tmp_path: Path):
        backend = LocalStorageBackend(root_dir=tmp_path)
        obj = backend.put("a1.jpg", b"hello", content_type="image/jpeg")
        assert obj.scheme == "cert-image://"
        assert obj.key == "a1.jpg"
        assert obj.uri == "cert-image://a1.jpg"
        signed = backend.sign_read_url(obj, ttl_seconds=60)
        assert "expires=" in signed.url and "sig=" in signed.url
        # verify_sig 通过 query 参数还原
        from urllib.parse import parse_qs, urlparse
        qs = parse_qs(urlparse(signed.url).query)
        expires = int(qs["expires"][0])
        sig = qs["sig"][0]
        ref = backend.verify_sig("a1.jpg", expires, sig)
        assert ref == obj
        assert backend.open(obj) == b"hello"

    def test_expired_signature_rejected(self, tmp_path: Path):
        backend = LocalStorageBackend(root_dir=tmp_path)
        obj = backend.put("e.jpg", b"x", content_type="image/jpeg")
        # 故意算过去的时间
        past = int(time.time()) - 3600
        sig = backend._signature(obj.key, past)  # noqa: SLF001
        with pytest.raises(ForbiddenException, match="expired"):
            backend.verify_sig(obj.key, past, sig)

    def test_tampered_signature_rejected(self, tmp_path: Path):
        backend = LocalStorageBackend(root_dir=tmp_path)
        backend.put("t.jpg", b"x", content_type="image/jpeg")
        with pytest.raises(ForbiddenException, match="signature"):
            backend.verify_sig("t.jpg", int(time.time()) + 60, "deadbeef")

    def test_path_traversal_rejected(self, tmp_path: Path):
        backend = LocalStorageBackend(root_dir=tmp_path)
        for bad in ("../etc/passwd", "a/b.jpg", "..\\\\b", ""):
            with pytest.raises(BadRequestException):
                backend.put(bad, b"x", content_type="image/jpeg")

    def test_open_missing_object(self, tmp_path: Path):
        backend = LocalStorageBackend(root_dir=tmp_path)
        with pytest.raises(NotFoundException):
            backend.open(StoredObject(scheme="cert-image://", key="ghost.jpg"))

    def test_parse_uri_returns_none_for_other_scheme(self, tmp_path: Path):
        backend = LocalStorageBackend(root_dir=tmp_path)
        assert backend.parse_uri("azure-blob://x.jpg") is None
        ref = backend.parse_uri("cert-image://x.jpg")
        assert ref is not None and ref.key == "x.jpg"


# ---------- AzureBlobStorageBackend (Phase A mock) ----------


class TestAzureBlobStorageBackendMock:
    def setup_method(self, _m):
        reset_storage_backend()

    def test_put_and_sign_and_open_round_trip(self):
        backend = AzureBlobStorageBackend()
        obj = backend.put("a.jpg", b"hello-azure", content_type="image/jpeg")
        assert obj.uri == "azure-blob://a.jpg"
        signed = backend.sign_read_url(obj, ttl_seconds=60)
        assert "blob.core.chinacloudapi.cn" in signed.url
        assert "_mock_sig=" in signed.url
        # 重建签名验
        sig = backend._signature(obj.key, signed.expires_at)  # noqa: SLF001
        ref = backend.verify_sig(obj.key, signed.expires_at, sig)
        assert ref == obj
        assert backend.open(obj) == b"hello-azure"

    def test_expired_signature_rejected(self):
        backend = AzureBlobStorageBackend()
        backend.put("e.jpg", b"x", content_type="image/jpeg")
        past = int(time.time()) - 3600
        sig = backend._signature("e.jpg", past)  # noqa: SLF001
        with pytest.raises(ForbiddenException, match="expired"):
            backend.verify_sig("e.jpg", past, sig)

    def test_tampered_signature_rejected(self):
        backend = AzureBlobStorageBackend()
        backend.put("t.jpg", b"x", content_type="image/jpeg")
        with pytest.raises(ForbiddenException, match="signature"):
            backend.verify_sig("t.jpg", int(time.time()) + 60, "deadbeef")

    def test_open_missing_object(self):
        backend = AzureBlobStorageBackend()
        with pytest.raises(NotFoundException):
            backend.open(StoredObject(scheme="azure-blob://", key="ghost.jpg"))


# ---------- Factory ----------


class TestStorageBackendFactory:
    def setup_method(self, _m):
        reset_storage_backend()

    def teardown_method(self, _m):
        reset_storage_backend()

    def test_factory_default_local(self, monkeypatch):
        from app.config import settings as _s
        monkeypatch.setattr(_s, "storage_backend", "local")
        b = get_storage_backend()
        assert isinstance(b, LocalStorageBackend)

    def test_factory_azure_picked(self, monkeypatch):
        from app.config import settings as _s
        monkeypatch.setattr(_s, "storage_backend", "azure")
        b = get_storage_backend()
        assert isinstance(b, AzureBlobStorageBackend)

    def test_factory_is_singleton(self, monkeypatch):
        from app.config import settings as _s
        monkeypatch.setattr(_s, "storage_backend", "local")
        b1 = get_storage_backend()
        b2 = get_storage_backend()
        assert b1 is b2

    def test_reset_drops_singleton(self, monkeypatch):
        from app.config import settings as _s
        monkeypatch.setattr(_s, "storage_backend", "local")
        b1 = get_storage_backend()
        reset_storage_backend()
        b2 = get_storage_backend()
        assert b1 is not b2

    def test_factory_unknown_value_falls_back_to_local(self, monkeypatch):
        from app.config import settings as _s
        monkeypatch.setattr(_s, "storage_backend", "garbage")
        b = get_storage_backend()
        assert isinstance(b, LocalStorageBackend)
