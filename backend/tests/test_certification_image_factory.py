"""S2-DEV-016-P2 â certification_image.py æ¹èµ° StorageBackend factory éææµè¯."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services import certification_image as cert_image
from app.services import storage_backend as _sb
from app.services.storage_backend import reset_storage_backend


class _UploadStub:
    def __init__(self, content: bytes, content_type: str = "image/jpeg"):
        self._content = content
        self.content_type = content_type

    async def read(self) -> bytes:
        return self._content


def _inject_mock_azure_backend() -> None:
    """Wire a mock-mode Azure backend into the singleton (no real creds needed).

    Phase B (S2-DEV-016-PHASE-B-PREFLIGHT-SDK) flipped the factory so that
    ``storage_backend=azure`` now calls ``_build_azure_client()`` and fails fast
    when Azure ENV is missing (AC#6 production guard). These dispatch-only tests
    verify URI/URL scheme, not real Azure IO, so we inject a mock-mode
    ``AzureBlobStorageBackend()`` (no client -> in-memory) directly into the
    singleton, bypassing the factory's ENV check while keeping the production
    fail-fast guard untouched. Authorized by PREFLIGHT AC#6 (flip downstream
    test update).
    """
    _sb._backend_singleton = _sb.AzureBlobStorageBackend()


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
        _inject_mock_azure_backend()
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
        _inject_mock_azure_backend()
        url = cert_image.sign_certification_image_url(uri)
        assert url is not None
        assert "/api/v1/admin/companions/certification-images/" in url
        reset_storage_backend()

    async def test_sign_url_for_azure_blob_uri_returns_azure_url(self, monkeypatch):
        reset_storage_backend()
        from app.config import settings as _s
        monkeypatch.setattr(_s, "storage_backend", "azure")
        _inject_mock_azure_backend()
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
