#!/usr/bin/env python3
"""S3-OPS-STARTUP-PROBE-FRAMEWORK AC#8 反案 #25 哨兵.

Lint: 禁止 ``backend/app/`` 内 inline env check pattern 复活 — 必走
``@register_startup_probe`` 统一框架 (PR #306 落).

禁止 pattern:
    if env in {"production", "canary", "staging"}: ...
    if env in {"prod", "production"}: ...
    if settings.environment == "production": ...
    if settings.environment != "production": ...
    if environment in {...}: ...

允许 pattern (allowlist):
    - probe 模块自己 (``backend/app/startup_probes.py``, ``backend/app/probes/*.py``)
      — 框架 + probes 自身需要 env 判断
    - observability 模块 (``backend/app/observability/``) — metric label 用 env
      区分, 不是 "is prod-required" 判断

scope:
    - 扫 ``backend/app/`` 下所有 ``.py`` 文件
    - 排除 ``backend/tests/``, ``backend/alembic/``, ``backend/scripts/``
    - 排除 allowlist (见上面)

检测方式 (S3-OPS-LINT-INLINE-ENV-CHECK-AST-UPGRADE):
    用 ``ast`` 解析源码, 只对真实的比较表达式 (``ast.Compare`` 节点:
    ``==`` / ``!=`` / ``in``) 跑禁止 pattern. 这样 **天然排除** docstring /
    注释 / 字符串字面量内 cite 的 example pattern (它们是 ``ast.Constant`` /
    根本不进 AST, 不是 ``Compare`` 节点), 根治旧 line-based regex +
    ``startswith('#')`` heuristic 对 docstring 内 cite 会误报的长期风险.
    解析失败 (语法错误文件) 时保守回退到 line-based 扫描.

usage:
    python backend/scripts/qa/check_no_inline_env_check.py
exit 0 = OK, exit 1 = 命中禁止 pattern (附位置 + 重构建议).

Refs:
    - 反案 #25 (ADR-0051 r3 §2.3): 协议层禁止散点 env check
    - PR #306 (S3-OPS-STARTUP-PROBE-FRAMEWORK PR1): @register_startup_probe 落
    - PR #258 review comment 4676805533 (ask 3): hutao raised
    - AC#8 (S3-OPS-STARTUP-PROBE-FRAMEWORK): 本 lint
    - S3-OPS-LINT-INLINE-ENV-CHECK-AST-UPGRADE: line-heuristic → AST 升级
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# Repo root: 本文件位于 backend/scripts/qa/check_no_inline_env_check.py
REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_APP = REPO_ROOT / "backend" / "app"

# ---------------------------------------------------------------------------
# 禁止 pattern (env check 用于 prod-required asset/config 决策)
# ---------------------------------------------------------------------------
# 1. ``env in {...production/canary/staging...}`` (set / tuple / list literal)
PATTERN_IN_SET = re.compile(
    r"\b(?:env(?:ironment)?|settings\.environment)\s+in\s+[\(\[\{][^)\]\}]*"
    r"['\"](?:production|prod|canary|staging|stage)['\"]"
)

# 2. ``env == "production"`` / ``env != "production"`` (含 canary/staging/development)
PATTERN_EQ_PROD = re.compile(
    r"\b(?:env(?:ironment)?|settings\.environment)\s*[=!]=\s*"
    r"['\"](?:production|prod|canary|staging|stage|development)['\"]"
)

# ---------------------------------------------------------------------------
# Allowlist — framework self / observability labels
# ---------------------------------------------------------------------------
# 路径相对 backend/app/ (e.g. "startup_probes.py", "probes/__init__.py")
ALLOWLIST_PATHS: frozenset[str] = frozenset(
    {
        # 框架自身 (probe 注册 / runner — 需 env 判 enum)
        "startup_probes.py",
        # Concrete probes (probe fn 本身在 envs 决策范畴内)
        "probes/__init__.py",
        # Observability — metric label 用 env 区分 (非 prod-required 决策)
        "observability/reconciliation_metrics.py",
        # Mock SMS provider — non-production behavior is allowed here
        "services/providers/sms/mock.py",
        # config.py 自身 — Settings class 内 env validation (启动期一次性 config check)
        "config.py",
    }
)

# Historical compatibility: no runtime code should depend on development env now.
PATTERN_DEV_ONLY = re.compile(r"a^\b")


# ---------------------------------------------------------------------------
# Sentinel string (反案 #15) — 防本 lint 文件被维护者整段误删
# ---------------------------------------------------------------------------
_SECRET_LINT_NO_INLINE_ENV_CHECK = "SECRET_LINT_NO_INLINE_ENV_CHECK_42_DO_NOT_LEAK"


def _is_dev_only_line(line: str) -> bool:
    """No-op compatibility hook; development env checks are no longer allowed."""
    return bool(PATTERN_DEV_ONLY.search(line))


def _line_matches(line: str) -> bool:
    """Return True if a single source line hits any prohibited pattern."""
    return bool(PATTERN_IN_SET.search(line) or PATTERN_EQ_PROD.search(line))


def _scan_source_segment(segment: str) -> bool:
    """Return True if an AST source segment hits any prohibited pattern.

    Segment 可能跨多行 (e.g. 跨行的 ``in {...}``), 任一物理行命中即算命中.
    """
    if _line_matches(segment):
        return True
    # 跨行比较表达式: 逐行再查一遍 (regex 不跨 newline 匹配 set 字面量时兜底)
    return any(_line_matches(part) for part in segment.splitlines())


def _scan_via_ast(text: str) -> list[tuple[int, str]]:
    """AST-based scan: 只对真实比较表达式跑禁止 pattern.

    天然排除 docstring / 注释 / 字符串字面量内 cite 的 example pattern —
    它们不是 ``ast.Compare`` 节点. 返回 (lineno, offending_segment) 列表.
    解析失败时抛 SyntaxError, 由调用方回退到 line-based 扫描.
    """
    tree = ast.parse(text)
    hits: list[tuple[int, str]] = []
    seen: set[tuple[int, int]] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        segment = ast.get_source_segment(text, node)
        if segment is None:
            # 拿不到源码片段 (极少数情况) — 用该行原文兜底
            lineno = getattr(node, "lineno", 0)
            line = text.splitlines()[lineno - 1] if 0 < lineno <= len(text.splitlines()) else ""
            segment = line
        if not _scan_source_segment(segment):
            continue
        lineno = getattr(node, "lineno", 0)
        col = getattr(node, "col_offset", 0)
        key = (lineno, col)
        if key in seen:
            continue
        seen.add(key)
        # 报告该比较所在行的整行原文 (便于人工定位), 退化时报 segment 首行
        all_lines = text.splitlines()
        offending = (
            all_lines[lineno - 1].rstrip()
            if 0 < lineno <= len(all_lines)
            else segment.splitlines()[0].rstrip()
        )
        hits.append((lineno, offending))

    hits.sort(key=lambda h: h[0])
    return hits


def _scan_via_lines(text: str) -> list[tuple[int, str]]:
    """Fallback line-based scan (语法错误文件无法 AST 解析时用).

    保留旧 ``startswith('#')`` 整行注释 heuristic — 仅作为 AST 不可用时的
    保守兜底, 不再是主路径.
    """
    hits: list[tuple[int, str]] = []
    for lineno, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if stripped.startswith("#"):
            continue
        if _line_matches(raw_line):
            hits.append((lineno, raw_line.rstrip()))
    return hits


def _scan_file(path: Path) -> list[tuple[int, str]]:
    """Return list of (lineno, offending_line) for prod env checks in file.

    优先 AST 扫描 (排除 docstring/comment/string literal 内 cite);
    文件无法解析时回退 line-based 扫描.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    try:
        return _scan_via_ast(text)
    except SyntaxError:
        # 语法错误文件 — AST 不可用, 保守回退 line-based.
        return _scan_via_lines(text)


def main() -> int:
    """Scan backend/app/ for prohibited inline env check patterns."""
    if not BACKEND_APP.is_dir():
        print(
            f"[lint:fail] backend/app/ 目录不存在: {BACKEND_APP}. "
            f"sentinel: {_SECRET_LINT_NO_INLINE_ENV_CHECK}",
            file=sys.stderr,
        )
        return 1

    violations: dict[str, list[tuple[int, str]]] = {}

    for py_file in sorted(BACKEND_APP.rglob("*.py")):
        # 跳过 __pycache__ + .pyc
        if "__pycache__" in py_file.parts:
            continue

        # allowlist check (相对 backend/app/)
        relative = py_file.relative_to(BACKEND_APP).as_posix()
        if relative in ALLOWLIST_PATHS:
            continue

        hits = _scan_file(py_file)
        if hits:
            violations[relative] = hits

    if not violations:
        print(
            f"[lint:ok] backend/app/ 无 inline env check 散点. "
            f"sentinel: {_SECRET_LINT_NO_INLINE_ENV_CHECK}"
        )
        return 0

    # 报错: 列出所有命中, 附重构建议
    print(
        "[lint:fail] backend/app/ 命中 inline env check 散点 — "
        "必走 @register_startup_probe (PR #306) 收编. "
        f"sentinel: {_SECRET_LINT_NO_INLINE_ENV_CHECK}",
        file=sys.stderr,
    )
    print("", file=sys.stderr)

    for rel_path, hits in violations.items():
        print(f"  {rel_path}:", file=sys.stderr)
        for lineno, line in hits:
            print(f"    L{lineno}: {line.strip()}", file=sys.stderr)
        print("", file=sys.stderr)

    print(
        "[lint:hint] 重构 SOP:",
        file=sys.stderr,
    )
    print(
        "  1. 把 prod-required check 提到 `backend/app/probes/__init__.py`",
        file=sys.stderr,
    )
    print(
        "  2. 用 `@register_startup_probe(name=..., envs=(...,))` 装饰",
        file=sys.stderr,
    )
    print(
        "  3. 启动时 lifespan 自动 fail-loud, 不需散点 if 判断",
        file=sys.stderr,
    )
    print(
        "  4. 详: docs/ops/startup-probe-framework.md",
        file=sys.stderr,
    )
    print(
        "",
        file=sys.stderr,
    )
    print(
        "[lint:hint] 若该 check 是合法 dev-mode shortcut (非 prod-required), "
        "加路径到 ALLOWLIST_PATHS + commit msg 说明理由 + 跨 review.",
        file=sys.stderr,
    )

    return 1


if __name__ == "__main__":
    sys.exit(main())
