"""Admin companion certification-image storage + signed access.

S2-DEV-013 PR-E2 Phase A → S2-DEV-016-P2: 改走 StorageBackend factory.

历史 cert-image:// 路径继续 work (LocalStorageBackend 复刻原逻辑)。
切 STORAGE_BACKEND=azure 后新上传走 azure-blob://，旧 cert-image:// 仍可读取。

dispatcher (P3 §3.4 双前缀) 留 S2-DEV-016-P3 PR。
"""

from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path

from fastapi import UploadFile

from app.exceptions import (
    PayloadTooLargeException,
    UnsupportedMediaTypeException,
)
from app.services.storage_backend import (
    LocalStorageBackend,
    SignedReadURL,
    StoredObject,
    get_storage_backend,
)

ALLOWED_CERT_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
MAX_CERT_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB
SIGNED_URL_TTL_SECONDS = 15 * 60

# Legacy constant kept for callers that still import it.
CERT_IMAGE_PREFIX = "cert-image://"

# Backwards-compat: tests monkeypatch this to redirect filesystem root.
# When set (default Path under backend/private/), local-backend uploads land here.
CERT_IMAGE_DIR = (
    Path(__file__).parent.parent.parent / "private" / "certification-images"
)


def _local_backend_with_dir() -> LocalStorageBackend:
    """Helper: build a LocalStorageBackend pointed at the current CERT_IMAGE_DIR.

    This ensures test monkeypatch on ``CERT_IMAGE_DIR`` keeps working without
    coupling tests to the factory singleton.
    """
    return LocalStorageBackend(root_dir=CERT_IMAGE_DIR)


def sign_certification_image_url(
    certification_image_url: str | None,
    *,
    now: int | None = None,
) -> str | None:
    """Return a signed URL for a stored certification image.

    Supports any scheme owned by the configured backend (cert-image:// for
    local, azure-blob:// for Azure). External legacy https:// URLs return None
    (no proxying in Phase A; migration handled by P4 cron).
    """
    if not certification_image_url:
        return None
    # cert-image:// 始终走本地 backend (动态读 CERT_IMAGE_DIR 以兼容 test monkeypatch)
    if certification_image_url.startswith(CERT_IMAGE_PREFIX):
        local = _local_backend_with_dir()
        obj = local.parse_uri(certification_image_url)
        if obj is None:
            return None
        return local.sign_read_url(
            obj, ttl_seconds=SIGNED_URL_TTL_SECONDS, now=now
        ).url
    # 其他 scheme 走 factory 设置的 backend (如 azure-blob://)
    backend = get_storage_backend()
    obj = backend.parse_uri(certification_image_url)
    if obj is None:
        return None
    signed: SignedReadURL = backend.sign_read_url(
        obj, ttl_seconds=SIGNED_URL_TTL_SECONDS, now=now
    )
    return signed.url


def verify_signed_certification_image(
    filename: str, expires: int, sig: str
) -> Path:
    """Verify a local cert-image:// signed URL and return its filesystem path.

    Only meaningful for LocalStorageBackend (FastAPI serves the file).
    Azure backend objects are served via Azure SAS URLs directly (no proxy).
    """
    local = _local_backend_with_dir()
    local.verify_sig(filename, expires, sig)
    return local.resolve_path(StoredObject(scheme=CERT_IMAGE_PREFIX, key=filename))


async def save_certification_image(file: UploadFile) -> str:
    """Save uploaded cert image to the configured backend; return its URI."""
    if file.content_type not in ALLOWED_CERT_IMAGE_TYPES:
        raise UnsupportedMediaTypeException(
            "Invalid file type. Only jpg/jpeg/png/webp are allowed"
        )

    content = await file.read()
    if len(content) > MAX_CERT_IMAGE_SIZE:
        raise PayloadTooLargeException("File too large. Maximum size is 5MB")

    ext = ALLOWED_CERT_IMAGE_TYPES[file.content_type]
    filename = f"{uuid.uuid4().hex}{ext}"
    # 记住: STORAGE_BACKEND=local (默认) 走下面 _local_backend_with_dir 豪不难能能上 CERT_IMAGE_DIR
    # monkeypatch; STORAGE_BACKEND=azure 走 factory singleton (Azure mock or real).
    from app.config import settings as _s
    if (getattr(_s, "storage_backend", "local") or "local").lower() == "azure":
        backend = get_storage_backend()
    else:
        backend = _local_backend_with_dir()
    obj = backend.put(filename, content, content_type=file.content_type)
    return obj.uri


def content_type_for(path: Path) -> str:
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"
