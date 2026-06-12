"""Unit tests for ``scripts/qa/check_storage_patterns.py``.

S2-OPS-016-PATTERN-LINT — ADR-0046 r4 AC-1 反例哨兵.

Test strategy: build small in-memory Python source fixtures, write to tmp file,
run lint_file() + main(), assert violations.

Covers:
  Lint A positive: legit backend / service module not flagged
  Lint A negative: subclass StorageBackend outside whitelist flagged
  Lint A whitelist: LocalStorageBackend + AzureBlobStorageBackend never flagged
  Lint A attribute import: ``module.StorageBackend`` base also flagged
  Lint A noqa: comment exempts class
  Lint B positive: methods calling _safe_key first OK
  Lint B negative: methods skipping _safe_key flagged
  Lint B sign_read_url: by design 不强制, 不误报
  Lint B docstring/del prelude: 允许跳过 docstring + del 后再 _safe_key
  Lint B noqa: comment exempts method
  Real file scan: backend/app/services/ 当前合规 (0 violations)
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from textwrap import dedent

import pytest

# ----------------------------------------------------------------------------
# Load script as module (script not a package)
# ----------------------------------------------------------------------------

_SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "qa" / "check_storage_patterns.py"


@pytest.fixture(scope="module")
def lint_module():
    """Dynamically import the lint script as a module."""
    spec = importlib.util.spec_from_file_location("check_storage_patterns", _SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_storage_patterns"] = module
    spec.loader.exec_module(module)
    return module


def _write(tmp_path: Path, name: str, source: str) -> Path:
    """Write a fixture Python source file."""
    p = tmp_path / name
    p.write_text(dedent(source).lstrip(), encoding="utf-8")
    return p


# ----------------------------------------------------------------------------
# Lint A: subclass whitelist
# ----------------------------------------------------------------------------


class TestLintASubclassWhitelist:
    """AC#2: StorageBackend subclass whitelist enforcement."""

    def test_no_subclass_no_violations(self, tmp_path: Path, lint_module):
        """Service-module pattern (compose StorageBackend instance) → OK."""
        f = _write(
            tmp_path,
            "contract_storage.py",
            """
            from app.services.storage_backend import StorageBackend

            class ContractStorageService:
                def __init__(self, backend: StorageBackend) -> None:
                    self._backend = backend
            """,
        )
        violations = lint_module.lint_file(f)
        assert violations == []

    def test_subclass_outside_whitelist_flagged(self, tmp_path: Path, lint_module):
        """class X(StorageBackend) outside whitelist → 1 violation."""
        f = _write(
            tmp_path,
            "bad_storage.py",
            """
            from app.services.storage_backend import StorageBackend

            class CertImageStorageBackend(StorageBackend):
                pass
            """,
        )
        violations = lint_module.lint_file(f)
        assert len(violations) == 1
        v = violations[0]
        assert v.rule == "storage-pattern-lint:A:subclass"
        assert "CertImageStorageBackend" in v.message
        assert "whitelist" in v.message

    def test_whitelisted_local_backend_not_flagged(self, tmp_path: Path, lint_module):
        """LocalStorageBackend(StorageBackend) is allowed."""
        f = _write(
            tmp_path,
            "storage_backend.py",
            """
            from abc import ABC

            class StorageBackend(ABC):
                pass

            class LocalStorageBackend(StorageBackend):
                pass
            """,
        )
        # Lint A: should not flag LocalStorageBackend (whitelist)
        # Lint B: LocalStorageBackend has no put/open/etc → no violation either
        violations = [
            v for v in lint_module.lint_file(f) if v.rule.startswith("storage-pattern-lint:A")
        ]
        assert violations == []

    def test_whitelisted_azure_backend_not_flagged(self, tmp_path: Path, lint_module):
        """AzureBlobStorageBackend(StorageBackend) is allowed."""
        f = _write(
            tmp_path,
            "storage_backend.py",
            """
            from abc import ABC

            class StorageBackend(ABC):
                pass

            class AzureBlobStorageBackend(StorageBackend):
                pass
            """,
        )
        violations = lint_module.lint_file(f)
        assert violations == []

    def test_attribute_base_storage_backend_flagged(self, tmp_path: Path, lint_module):
        """class X(module.StorageBackend) also detected."""
        f = _write(
            tmp_path,
            "bad_storage.py",
            """
            from app.services import storage_backend

            class FeedbackStorageBackend(storage_backend.StorageBackend):
                pass
            """,
        )
        violations = lint_module.lint_file(f)
        assert len(violations) == 1
        assert violations[0].rule == "storage-pattern-lint:A:subclass"
        assert "FeedbackStorageBackend" in violations[0].message

    def test_noqa_pragma_exempts_class(self, tmp_path: Path, lint_module):
        """``# noqa: storage-pattern-lint`` on class line silences Lint A."""
        f = _write(
            tmp_path,
            "test_fixture.py",
            """
            from app.services.storage_backend import StorageBackend

            class MockStorageBackend(StorageBackend):  # noqa: storage-pattern-lint
                pass
            """,
        )
        violations = lint_module.lint_file(f)
        assert violations == []

    def test_unrelated_base_not_flagged(self, tmp_path: Path, lint_module):
        """class X(StoragePutResult) / class X(StoredObject) 不误报."""
        f = _write(
            tmp_path,
            "result_types.py",
            """
            from app.services.storage_backend import StoragePutResult

            class ExtendedPutResult(StoragePutResult):
                pass
            """,
        )
        violations = lint_module.lint_file(f)
        assert violations == []


# ----------------------------------------------------------------------------
# Lint B: _safe_key funnel whitelist
# ----------------------------------------------------------------------------


class TestLintBSafeKeyFunnel:
    """AC#3: LocalStorageBackend 5 method must call _safe_key in prelude."""

    def test_all_methods_call_safe_key_ok(self, tmp_path: Path, lint_module):
        """All 5 methods call self._safe_key first → no violations."""
        f = _write(
            tmp_path,
            "storage_backend.py",
            """
            class LocalStorageBackend:
                def _safe_key(self, key):
                    return key

                def put(self, key, content, *, content_type):
                    safe = self._safe_key(key)
                    return safe

                def put_if_absent(self, key, content, *, content_type, metadata=None):
                    safe = self._safe_key(key)
                    return safe

                def open(self, obj):
                    safe = self._safe_key(obj.key)
                    return safe

                def verify_sig(self, key, expires, sig):
                    safe = self._safe_key(key)
                    return safe

                def resolve_path(self, obj):
                    safe = self._safe_key(obj.key)
                    return safe
            """,
        )
        violations = [
            v for v in lint_module.lint_file(f) if v.rule.startswith("storage-pattern-lint:B")
        ]
        assert violations == []

    def test_method_skips_safe_key_flagged(self, tmp_path: Path, lint_module):
        """``put`` 不调 _safe_key → 1 Lint B violation."""
        f = _write(
            tmp_path,
            "storage_backend.py",
            """
            class LocalStorageBackend:
                def _safe_key(self, key):
                    return key

                def put(self, key, content, *, content_type):
                    return key  # bad: skip _safe_key

                def put_if_absent(self, key, content, *, content_type, metadata=None):
                    safe = self._safe_key(key)
                    return safe

                def open(self, obj):
                    safe = self._safe_key(obj.key)
                    return safe

                def verify_sig(self, key, expires, sig):
                    safe = self._safe_key(key)
                    return safe

                def resolve_path(self, obj):
                    safe = self._safe_key(obj.key)
                    return safe
            """,
        )
        violations = [
            v for v in lint_module.lint_file(f) if v.rule.startswith("storage-pattern-lint:B")
        ]
        assert len(violations) == 1
        assert "LocalStorageBackend.put" in violations[0].message

    def test_sign_read_url_not_required(self, tmp_path: Path, lint_module):
        """``sign_read_url`` 不调 _safe_key → 不误报 (by design)."""
        f = _write(
            tmp_path,
            "storage_backend.py",
            """
            class LocalStorageBackend:
                def _safe_key(self, key):
                    return key

                def put(self, key, content, *, content_type):
                    safe = self._safe_key(key)
                    return safe

                def sign_read_url(self, obj, *, ttl_seconds, now=None):
                    # 不强制 — by design, URL signing 是字符串操作不触 fs
                    return f"http://{obj.key}?ttl={ttl_seconds}"
            """,
        )
        violations = [
            v for v in lint_module.lint_file(f) if v.rule.startswith("storage-pattern-lint:B")
        ]
        assert violations == []

    def test_docstring_then_safe_key_ok(self, tmp_path: Path, lint_module):
        """方法 docstring 后第一句调 _safe_key → OK."""
        f = _write(
            tmp_path,
            "storage_backend.py",
            """
            class LocalStorageBackend:
                def _safe_key(self, key):
                    return key

                def put(self, key, content, *, content_type):
                    \"\"\"Put with docstring prelude.\"\"\"
                    safe = self._safe_key(key)
                    return safe
            """,
        )
        violations = [
            v for v in lint_module.lint_file(f) if v.rule.startswith("storage-pattern-lint:B")
        ]
        assert violations == []

    def test_del_prelude_then_safe_key_ok(self, tmp_path: Path, lint_module):
        """方法 ``del foo`` prelude 后调 _safe_key → OK (Azure metadata pattern)."""
        f = _write(
            tmp_path,
            "storage_backend.py",
            """
            class LocalStorageBackend:
                def _safe_key(self, key):
                    return key

                def put_if_absent(self, key, content, *, content_type, metadata=None):
                    del metadata  # legit prelude
                    safe = self._safe_key(key)
                    return safe
            """,
        )
        violations = [
            v for v in lint_module.lint_file(f) if v.rule.startswith("storage-pattern-lint:B")
        ]
        assert violations == []

    def test_inline_safe_key_call_ok(self, tmp_path: Path, lint_module):
        """``return self.root / self._safe_key(key)`` 内联调 → OK."""
        f = _write(
            tmp_path,
            "storage_backend.py",
            """
            class LocalStorageBackend:
                def _safe_key(self, key):
                    return key

                def resolve_path(self, obj):
                    return f"/root/{self._safe_key(obj.key)}"
            """,
        )
        violations = [
            v for v in lint_module.lint_file(f) if v.rule.startswith("storage-pattern-lint:B")
        ]
        assert violations == []

    def test_noqa_pragma_exempts_method(self, tmp_path: Path, lint_module):
        """``# noqa: storage-pattern-lint`` on def line silences Lint B."""
        f = _write(
            tmp_path,
            "storage_backend.py",
            """
            class LocalStorageBackend:
                def _safe_key(self, key):
                    return key

                def put(self, key, content, *, content_type):  # noqa: storage-pattern-lint
                    return key
            """,
        )
        violations = [
            v for v in lint_module.lint_file(f) if v.rule.startswith("storage-pattern-lint:B")
        ]
        assert violations == []

    def test_lint_b_skipped_for_non_local_backend(self, tmp_path: Path, lint_module):
        """``AzureBlobStorageBackend`` 不触 Lint B (mock dict / SDK 无 fs)."""
        f = _write(
            tmp_path,
            "storage_backend.py",
            """
            class AzureBlobStorageBackend:
                def put(self, key, content, *, content_type):
                    # Phase A mock: dict store, no _safe_key needed
                    return None
            """,
        )
        violations = [
            v for v in lint_module.lint_file(f) if v.rule.startswith("storage-pattern-lint:B")
        ]
        assert violations == []


# ----------------------------------------------------------------------------
# Real-file integration: services/ 当前合规
# ----------------------------------------------------------------------------


class TestRealServicesDirectoryClean:
    """Sanity sentinel: backend/app/services/ 当前必合规 (no violations)."""

    def test_services_dir_clean(self, lint_module):
        """Scan backend/app/services/ — 当前实施合 ADR-0046 §3."""
        services_dir = Path(__file__).resolve().parents[2] / "app" / "services"
        assert services_dir.is_dir(), f"services dir not found: {services_dir}"
        files = lint_module.iter_python_files([services_dir])
        all_violations = []
        for f in files:
            all_violations.extend(lint_module.lint_file(f))
        assert all_violations == [], (
            "Real services dir 出现违规! 修代码或加 # noqa:\n"
            + "\n".join(v.format() for v in all_violations)
        )


# ----------------------------------------------------------------------------
# CLI main()
# ----------------------------------------------------------------------------


class TestCLIMain:
    """exit code contract: 0 OK / 1 violations / 2 usage."""

    def test_main_exit_0_on_clean(self, tmp_path: Path, lint_module, capsys):
        f = _write(
            tmp_path,
            "ok.py",
            """
            class Foo:
                pass
            """,
        )
        rc = lint_module.main([str(f)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "OK" in out

    def test_main_exit_1_on_violations(self, tmp_path: Path, lint_module, capsys):
        f = _write(
            tmp_path,
            "bad.py",
            """
            from app.services.storage_backend import StorageBackend

            class Evil(StorageBackend):
                pass
            """,
        )
        rc = lint_module.main([str(f)])
        assert rc == 1
        out = capsys.readouterr().out
        assert "FAIL" in out
        assert "Evil" in out
