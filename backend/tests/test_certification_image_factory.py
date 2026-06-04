"""S2-DEV-016-P2 â certification_image.py æ¹èµ° StorageBackend factory éææµè¯."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services import certification_image as cert_image
from app.services.storage_backend import reset_storage_backend


class _UploadStub:
    def __init__(self, content: bytes, content_type: str = "image/jpeg"):
        self._content = content
        self.content_type = content_type

    async def read(self) -> bytes:
        return self._content


@pytest.mark.asyncio
class TestCertificationImageFactoryIntegration:
    async def test_save_uses_local_backend_when_storage_backend_local(
        self, tmp_path: Path, monkeypatch
    ):
        reset_storage_backend()
        monkeypatch.setattr(cert_image, "CERT_IMAGE_DIR", tmp_path)
        from app.config import settings as _s
        monkeypatch.setattr(_s, "storage_backend", "local")
        uri = await cert_image.save_certification_image(_UploadStub(b"x" * 100))
        assert uri.startswith("cert-image://")
        # File landed under tmp_path
        files = list(tmp_path.iterdir())
        assert len(files) == 1
        assert files[0].read_bytes() == b"x" * 100

    async def test_save_uses_azure_backend_when_storage_backend_azure(
        self, monkeypatch
    ):
        reset_storage_backend()
        from app.config import settings as _s
        monkeypatch.setattr(_s, "storage_backend", "azure")
        uri = await cert_image.save_certification_image(_UploadStub(b"y" * 50))
        assert uri.startswith("azure-blob://")
        reset_storage_backend()

    async def test_sign_url_for_legacy_cert_image_works_when_backend_azure(
        self, tmp_path: Path, monkeypatch
    ):
        """legacy cert-image URL 切 azure 后仍可 sign."""
        reset_storage_backend()
        monkeypatch.setattr(cert_image, "CERT_IMAGE_DIR", tmp_path)
        from app.config import settings as _s
        # 先 local backend save
        monkeypatch.setattr(_s, "storage_backend", "local")
        uri = await cert_image.save_certification_image(_UploadStub(b"z" * 10))
        reset_storage_backend()
        # 切口 azure 再 sign，仍可走本地 backend (cert-image:// dispatch)
        monkeypatch.setattr(_s, "storage_backend", "azure")
        url = cert_image.sign_certification_image_url(uri)
        assert url is not None
        assert "/api/v1/admin/companions/certification-images/" in url
        reset_storage_backend()

    async def test_sign_url_for_azure_blob_uri_returns_azure_url(self, monkeypatch):
        reset_storage_backend()
        from app.config import settings as _s
        monkeypatch.setattr(_s, "storage_backend", "azure")
        uri = await cert_image.save_certification_image(_UploadStub(b"a" * 20))
        url = cert_image.sign_certification_image_url(uri)
        assert url is not None
        assert "blob.core.chinacloudapi.cn" in url
        reset_storage_backend()

    async def test_sign_external_https_url_returns_none(self):
        url = cert_image.sign_certification_image_url(
            "https://legacy.example.com/foo.jpg"
        )
        assert url is None
