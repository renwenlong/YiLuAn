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
    StoragePutResult,
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


# ---------- put_if_absent (S3-DEV-000 / ADR-0046 §3.3 + ADR-0049 §5.1) ----------


class TestPutIfAbsentContract:
    """跨 backend 合同验证：put_if_absent 返回 StoragePutResult 不抛错."""

    def setup_method(self, _m):
        reset_storage_backend()

    def test_local_first_put_returns_already_exists_false(self, tmp_path: Path):
        backend = LocalStorageBackend(root_dir=tmp_path)
        result = backend.put_if_absent("new.pdf", b"first-bytes", content_type="application/pdf")
        assert isinstance(result, StoragePutResult)
        assert result.already_exists is False
        assert result.stored.scheme == "cert-image://"
        assert result.stored.key == "new.pdf"
        assert backend.open(result.stored) == b"first-bytes"

    def test_local_second_put_returns_already_exists_true(self, tmp_path: Path):
        backend = LocalStorageBackend(root_dir=tmp_path)
        backend.put_if_absent("dup.pdf", b"original", content_type="application/pdf")
        result = backend.put_if_absent(
            "dup.pdf", b"overwrite-attempt", content_type="application/pdf"
        )
        assert result.already_exists is True
        assert result.stored.key == "dup.pdf"
        # 原内容不被覆写 — WORM 保证
        assert backend.open(result.stored) == b"original"

    def test_local_does_not_raise_file_exists_error(self, tmp_path: Path):
        backend = LocalStorageBackend(root_dir=tmp_path)
        backend.put_if_absent("x.bin", b"a", content_type="application/octet-stream")
        # 调用方不需要 try/except FileExistsError
        try:
            result = backend.put_if_absent("x.bin", b"b", content_type="application/octet-stream")
        except FileExistsError:  # pragma: no cover - regression guard
            pytest.fail("put_if_absent must not raise FileExistsError")
        assert result.already_exists is True

    def test_azure_first_put_returns_already_exists_false(self):
        backend = AzureBlobStorageBackend()
        result = backend.put_if_absent(
            "contract/2026/abc.pdf",
            b"pdf-bytes",
            content_type="application/pdf",
        )
        assert result.already_exists is False
        assert result.stored.scheme == "azure-blob://"
        assert backend.open(result.stored) == b"pdf-bytes"

    def test_azure_second_put_returns_already_exists_true(self):
        backend = AzureBlobStorageBackend()
        backend.put_if_absent("dup-key", b"first", content_type="application/pdf")
        result = backend.put_if_absent("dup-key", b"second", content_type="application/pdf")
        assert result.already_exists is True
        # mock 反射真实 Azure If-None-Match: * 行为 — 不覆写
        assert backend.open(result.stored) == b"first"

    def test_azure_metadata_accepted_for_api_parity(self):
        backend = AzureBlobStorageBackend()
        # metadata 参数 Phase A 不使用但必须接受，保证 Phase B 切 SDK 时可透传
        result = backend.put_if_absent(
            "meta.bin",
            b"x",
            content_type="application/octet-stream",
            metadata={"contract_hash": "abc123", "uploader": "system"},
        )
        assert result.already_exists is False


class TestPutIfAbsentConcurrency:
    """并发 race 验证：同一 key 多线程 put_if_absent 仅 1 成功."""

    def test_local_concurrent_put_only_one_succeeds(self, tmp_path: Path):
        import threading

        backend = LocalStorageBackend(root_dir=tmp_path)
        results: list[StoragePutResult] = []
        results_lock = threading.Lock()
        barrier = threading.Barrier(8)

        def worker(idx: int) -> None:
            barrier.wait()  # 同时起跑冲撞 O_EXCL
            r = backend.put_if_absent(
                "race.pdf",
                f"worker-{idx}".encode(),
                content_type="application/pdf",
            )
            with results_lock:
                results.append(r)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 8
        winners = [r for r in results if not r.already_exists]
        losers = [r for r in results if r.already_exists]
        assert len(winners) == 1, f"O_EXCL must serialize: expected 1 winner, got {len(winners)}"
        assert len(losers) == 7
        # 胜出者写入的内容被保留
        winner_bytes = backend.open(winners[0].stored)
        assert winner_bytes.startswith(b"worker-")

    def test_azure_concurrent_put_only_one_succeeds(self):
        # Azure mock 单进程内存 dict，GIL 下顺序化十分明显；本测试保证接口一致性
        backend = AzureBlobStorageBackend()
        outcomes = [
            backend.put_if_absent(
                "single-key",
                f"call-{i}".encode(),
                content_type="application/pdf",
            )
            for i in range(5)
        ]
        winners = [r for r in outcomes if not r.already_exists]
        assert len(winners) == 1
        assert outcomes[0].already_exists is False
        assert all(r.already_exists for r in outcomes[1:])


class TestPutBackwardCompatibility:
    """AC#6: 现有 put() 签名不变，调用方不感知."""

    def test_local_put_signature_unchanged(self, tmp_path: Path):
        backend = LocalStorageBackend(root_dir=tmp_path)
        # 原始 3-positional + 1-keyword 调用方式仍工作
        obj = backend.put("legacy.jpg", b"data", content_type="image/jpeg")
        assert isinstance(obj, StoredObject)
        assert obj.scheme == "cert-image://"

    def test_azure_put_signature_unchanged(self):
        backend = AzureBlobStorageBackend()
        obj = backend.put("legacy.bin", b"data", content_type="application/octet-stream")
        assert isinstance(obj, StoredObject)
        assert obj.scheme == "azure-blob://"


class TestLocalAllowSubdirs:
    """S3-DEV-001 (ADR-0046 §3.1): LocalStorageBackend opt-in subdirs.

    Default (allow_subdirs=False) preserves cert-image flat namespace.
    Opt-in (allow_subdirs=True) for contract storage enables
    ``contracts/{year}/{month}/...`` nested paths with traversal defense.
    """

    def test_default_rejects_slash_in_key(self, tmp_path: Path):
        backend = LocalStorageBackend(root_dir=tmp_path)
        with pytest.raises(BadRequestException):
            backend.put("a/b.pdf", b"x", content_type="application/pdf")

    def test_subdir_mode_allows_nested_path(self, tmp_path: Path):
        backend = LocalStorageBackend(root_dir=tmp_path, allow_subdirs=True)
        obj = backend.put(
            "contracts/2026/06/abc.pdf",
            b"data",
            content_type="application/pdf",
        )
        assert obj.key == "contracts/2026/06/abc.pdf"
        on_disk = tmp_path / "contracts" / "2026" / "06" / "abc.pdf"
        assert on_disk.exists()
        assert on_disk.read_bytes() == b"data"

    def test_subdir_mode_put_if_absent_creates_intermediate_dirs(self, tmp_path: Path):
        backend = LocalStorageBackend(root_dir=tmp_path, allow_subdirs=True)
        res = backend.put_if_absent(
            "contracts/2026/06/x.pdf",
            b"data",
            content_type="application/pdf",
        )
        assert res.already_exists is False
        # Second call -> already_exists
        res2 = backend.put_if_absent(
            "contracts/2026/06/x.pdf",
            b"other",
            content_type="application/pdf",
        )
        assert res2.already_exists is True

    @pytest.mark.parametrize(
        "bad_key",
        [
            "../etc/passwd",  # parent traversal
            "contracts/../../etc",  # mid-path traversal
            "contracts/./x.pdf",  # current-dir segment
            "/abs/path.pdf",  # absolute
            "contracts//double.pdf",  # empty segment
            "contracts/x\x00.pdf",  # NUL
            "contracts/x\nstuff",  # newline
            "contracts\\windows.pdf",  # backslash
        ],
    )
    def test_subdir_mode_rejects_traversal_and_control_chars(self, tmp_path: Path, bad_key: str):
        backend = LocalStorageBackend(root_dir=tmp_path, allow_subdirs=True)
        with pytest.raises(BadRequestException):
            backend.put(bad_key, b"x", content_type="application/pdf")

    def test_subdir_mode_still_rejects_empty_key(self, tmp_path: Path):
        backend = LocalStorageBackend(root_dir=tmp_path, allow_subdirs=True)
        with pytest.raises(BadRequestException):
            backend.put("", b"x", content_type="application/pdf")
