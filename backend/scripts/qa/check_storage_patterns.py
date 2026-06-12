#!/usr/bin/env python3
"""Storage pattern lint — ADR-0046 r4 AC-1 反例哨兵 (S2-OPS-016-PATTERN-LINT).

ADR-0046 §3 + r4 amend 字面: contract / feedback-attachment / cert-image 等
**service-module 模式** 必须不继承 ``StorageBackend`` ABC。只允许
``LocalStorageBackend`` + ``AzureBlobStorageBackend`` 两个内置 backend 子类化。

## 双检 (ADR-0046 r4 AC-1)

### Lint A: StorageBackend 子类化白名单
扫 ``backend/app/services/**/*.py`` 所有 ``class X(StorageBackend)`` /
``class X(SomeBase, StorageBackend)`` 子类定义。命中即 fail, 除非 class name
在白名单。白名单内 (内置 backend):

- ``LocalStorageBackend``
- ``AzureBlobStorageBackend``

未在白名单 ⇒ 4 层防御 (subclass + WORM + TTL + namespace 业务规则的 ABC 边界腐烂) 全失,
fail PR。

### Lint B: ``LocalStorageBackend`` funnel ``_safe_key`` 白名单
扫 ``LocalStorageBackend`` (及未来 WORM Azure backend) 的 5 个 fs 访问 method:

- ``put``
- ``put_if_absent``
- ``open``
- ``verify_sig``
- ``resolve_path``

首语句 (允许 ``del``/``del_var`` 等无意义 prelude) 必须调 ``self._safe_key(key|obj.key)``。
``sign_read_url`` 类纯字符串方法 by design 不在白名单, 不误报 (虽然现 impl 也调了
``_safe_key``, 这是 nice-to-have 不是必需).

## 设计哲学 (AC#4)

- 拒纯 grep regex (易 false positive)
- 用 ``ast.parse`` 解析 Python AST (method 边界清晰, ``self._safe_key()`` Call
  node 模式匹配, 不被 string literal / comment 干扰)
- Lint A 为主防御 (运行时 sentinel test 不能 detect 新 class 定义, 必须静态扫)
- Lint B 为 CI fallback — runtime test
  ``test_all_key_handling_methods_call_safe_key`` 已覆盖 6 method 实际调用,
  本 lint 作为静态层防御, 防 runtime test 被某次重构悄悄 skip 或 deselect 后无哨兵

## 豁免 (AC#5)

行尾加 ``# noqa: storage-pattern-lint`` 注释豁免特定 class 定义 / method
(for legit test fixture / mock backend)。

## CLI

```bash
python scripts/qa/check_storage_patterns.py [PATH ...]
# default PATH = backend/app/services/

exit 0: 全绿
exit 1: 发现违规
exit 2: usage error
```
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

# ----------------------------------------------------------------------------
# Lint A: StorageBackend subclass whitelist
# ----------------------------------------------------------------------------
#
# Whitelist内 = ADR-0046 §3 字面允许子类化 StorageBackend 的两个内置 backend.
# 新增 backend 必须先 amend ADR-0046 + 本白名单 (强制人工 review path).
SUBCLASS_WHITELIST: frozenset[str] = frozenset(
    {
        "LocalStorageBackend",
        "AzureBlobStorageBackend",
    }
)

NOQA_PRAGMA: str = "noqa: storage-pattern-lint"


# ----------------------------------------------------------------------------
# Lint B: LocalStorageBackend _safe_key funnel whitelist
# ----------------------------------------------------------------------------
#
# AC#3: 5 个 fs 访问 method 首语句 (允许 prelude del / type guard) 必须调
# self._safe_key(key)。sign_read_url 不强制 (by design 是 URL signing, key 不
# 触 fs).
SAFE_KEY_REQUIRED_METHODS: frozenset[str] = frozenset(
    {
        "put",
        "put_if_absent",
        "open",
        "verify_sig",
        "resolve_path",
    }
)

# AC#3 应用范围: 仅本地文件系统 backend (Azure backend Phase A 是 dict mock,
# Phase B 走 Azure SDK, 都无 fs traversal 风险, 不强制 funnel _safe_key).
SAFE_KEY_REQUIRED_CLASSES: frozenset[str] = frozenset(
    {
        "LocalStorageBackend",
    }
)


class Violation:
    """Single lint violation."""

    def __init__(
        self,
        *,
        rule: str,
        path: Path,
        lineno: int,
        message: str,
    ) -> None:
        self.rule = rule
        self.path = path
        self.lineno = lineno
        self.message = message

    def format(self) -> str:
        return f"{self.path}:{self.lineno}: [{self.rule}] {self.message}"


def _line_has_noqa(source_lines: list[str], lineno: int) -> bool:
    """Return True if the given line (1-indexed) has the noqa pragma."""
    if lineno < 1 or lineno > len(source_lines):
        return False
    return NOQA_PRAGMA in source_lines[lineno - 1]


def _base_class_names(class_node: ast.ClassDef) -> list[str]:
    """Extract base class name strings from a ClassDef.

    Handles:
      class X(StorageBackend)           -> ["StorageBackend"]
      class X(module.StorageBackend)    -> ["module.StorageBackend"]
      class X(Generic[T], StorageBackend) -> ["Generic", "StorageBackend"]
    """
    names: list[str] = []
    for base in class_node.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            # module.StorageBackend -> "module.StorageBackend"
            parts: list[str] = [base.attr]
            cur: ast.expr = base.value
            while isinstance(cur, ast.Attribute):
                parts.insert(0, cur.attr)
                cur = cur.value
            if isinstance(cur, ast.Name):
                parts.insert(0, cur.id)
            names.append(".".join(parts))
        elif isinstance(base, ast.Subscript):
            # Generic[T] -> Generic; ignore non-StorageBackend subscripts
            if isinstance(base.value, ast.Name):
                names.append(base.value.id)
    return names


def _is_storage_backend_base(name: str) -> bool:
    """True when a base class name refers to the StorageBackend ABC."""
    # Accept both bare "StorageBackend" and attribute-style imports
    # (e.g. "storage_backend.StorageBackend"). Reject ResultObjects like
    # "StoragePutResult" / "StorageObject".
    if name == "StorageBackend":
        return True
    return name.endswith(".StorageBackend")


def lint_a_subclass_whitelist(
    tree: ast.Module,
    *,
    path: Path,
    source_lines: list[str],
) -> list[Violation]:
    """AC#2 Lint A: StorageBackend ABC 子类化白名单."""
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = _base_class_names(node)
        if not any(_is_storage_backend_base(b) for b in bases):
            continue
        if node.name in SUBCLASS_WHITELIST:
            continue
        if _line_has_noqa(source_lines, node.lineno):
            continue
        violations.append(
            Violation(
                rule="storage-pattern-lint:A:subclass",
                path=path,
                lineno=node.lineno,
                message=(
                    f"class '{node.name}' subclasses StorageBackend but is "
                    f"not in the ADR-0046 §3 whitelist {sorted(SUBCLASS_WHITELIST)}. "
                    f"Service-module pattern (contract/feedback-attachment/"
                    f"cert-image) must compose a StorageBackend instance, "
                    f"not subclass it. If this is a legit new backend, amend "
                    f"ADR-0046 + SUBCLASS_WHITELIST first; if this is a test "
                    f"fixture, add '# {NOQA_PRAGMA}' on the class line."
                ),
            )
        )
    return violations


def _function_calls_safe_key_first(func_node: ast.FunctionDef) -> bool:
    """Return True if the function's body contains self._safe_key(...) call
    in its head (prelude).

    Prelude = consecutive leading statements that are docstring / del / pass
    / type-annotation-only. The first 'real' statement (Assign / Call /
    Return / etc.) must contain a self._safe_key(...) call somewhere in its
    expression tree.

    Why "somewhere in expression tree" not "must be `safe = self._safe_key(...)`":
    存在 ``self._safe_key(obj.key)`` 用作 path component 内联调用的合法 pattern
    (e.g. ``return self.root / self._safe_key(obj.key)``)。AC#3 字面 = "首句调",
    我解释为 "首句的表达式 tree 中存在 self._safe_key 调用"。
    """
    body = func_node.body
    # Skip docstring
    start = 0
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        start = 1
    # Skip prelude (del / pass / annotation-only)
    while start < len(body):
        stmt = body[start]
        if isinstance(stmt, (ast.Delete, ast.Pass)):
            start += 1
            continue
        if isinstance(stmt, ast.AnnAssign) and stmt.value is None:
            start += 1
            continue
        break
    if start >= len(body):
        return False
    first_real = body[start]
    # Walk expression tree of the first real statement, search for
    # self._safe_key(...) Call node.
    for child in ast.walk(first_real):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        if not isinstance(func, ast.Attribute):
            continue
        if func.attr != "_safe_key":
            continue
        # Ensure callee is self.* (defensive: ignore unrelated foo._safe_key)
        if isinstance(func.value, ast.Name) and func.value.id == "self":
            return True
    return False


def lint_b_safe_key_funnel(
    tree: ast.Module,
    *,
    path: Path,
    source_lines: list[str],
) -> list[Violation]:
    """AC#3 Lint B: LocalStorageBackend funnel _safe_key 白名单."""
    violations: list[Violation] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        if node.name not in SAFE_KEY_REQUIRED_CLASSES:
            continue
        # Iterate direct method definitions
        for item in node.body:
            if not isinstance(item, ast.FunctionDef):
                continue
            if item.name not in SAFE_KEY_REQUIRED_METHODS:
                continue
            if _line_has_noqa(source_lines, item.lineno):
                continue
            if not _function_calls_safe_key_first(item):
                violations.append(
                    Violation(
                        rule="storage-pattern-lint:B:safe_key_funnel",
                        path=path,
                        lineno=item.lineno,
                        message=(
                            f"method '{node.name}.{item.name}' does not call "
                            f"self._safe_key(...) in its prelude. Per "
                            f"ADR-0046 §3 + AC#3, all 5 fs-access methods "
                            f"({sorted(SAFE_KEY_REQUIRED_METHODS)}) on "
                            f"LocalStorageBackend must funnel through "
                            f"_safe_key for path-traversal defense. If this "
                            f"method is intentionally exempt, add "
                            f"'# {NOQA_PRAGMA}' on the def line and explain."
                        ),
                    )
                )
    return violations


def lint_file(path: Path) -> list[Violation]:
    """Run both lints on a single file. Skips non-Python / unreadable files."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        # Read failure is not a lint violation; print warning to stderr
        # but do not fail the run.
        print(f"warning: cannot read {path}: {exc}", file=sys.stderr)
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        # Syntax error means file is broken — fail loudly so we don't silently
        # skip a real storage file.
        return [
            Violation(
                rule="storage-pattern-lint:syntax",
                path=path,
                lineno=exc.lineno or 0,
                message=f"SyntaxError parsing file: {exc.msg}",
            )
        ]
    source_lines = source.splitlines()
    return [
        *lint_a_subclass_whitelist(tree, path=path, source_lines=source_lines),
        *lint_b_safe_key_funnel(tree, path=path, source_lines=source_lines),
    ]


def iter_python_files(targets: list[Path]) -> list[Path]:
    """Expand a list of file / directory targets into Python files."""
    out: list[Path] = []
    for target in targets:
        if target.is_file():
            if target.suffix == ".py":
                out.append(target)
        elif target.is_dir():
            out.extend(sorted(target.rglob("*.py")))
        else:
            print(
                f"warning: path does not exist or unsupported: {target}",
                file=sys.stderr,
            )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_storage_patterns",
        description=(
            "Lint StorageBackend ABC usage per ADR-0046 r4 AC-1 " "(S2-OPS-016-PATTERN-LINT)."
        ),
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help=("Files or directories to scan. Default: backend/app/services/"),
    )
    parser.add_argument(
        "--list-files",
        action="store_true",
        help="Print scanned files to stderr (debug).",
    )
    args = parser.parse_args(argv)

    targets = args.paths or [Path("backend/app/services")]
    files = iter_python_files(targets)
    if args.list_files:
        for f in files:
            print(f"scan: {f}", file=sys.stderr)

    all_violations: list[Violation] = []
    for f in files:
        all_violations.extend(lint_file(f))

    if not all_violations:
        print(f"storage-pattern-lint: OK ({len(files)} files scanned, " f"0 violations)")
        return 0

    print(f"storage-pattern-lint: FAIL ({len(all_violations)} violations)\n")
    for v in all_violations:
        print(v.format())
        print()
    print(f"\nSummary: {len(all_violations)} violation(s) across {len(files)} " f"file(s) scanned.")
    print("ADR ref: docs/architecture/ADR-0046-contract-storage-pattern.md §3")
    return 1


if __name__ == "__main__":
    sys.exit(main())
