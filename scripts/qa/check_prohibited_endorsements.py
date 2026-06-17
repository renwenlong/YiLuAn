#!/usr/bin/env python3
"""S3-DEV-003-ADMIN-COPY AC#3 反案哨兵: 职业背书 / 效果背书禁词 lint.

实现 PRD-001 v1.5 §F8 + qa/s3-prd-001-004-pm-business-acceptance-checklist-v1.md PM-005-10
的 admin-v2 + 三端文案 lint 哨兵, 防 admin 团队加错合规风控文案漂移.

清单源 (PM 维护, 不在本脚本):
    ``docs/copy-lint/prohibited-occupational-endorsements.yml``

CI gate:
    - block 级命中 -> exit 1 (CI 阻塞 PR)
    - warn 级命中 -> 日志 + exit 0 (不阻塞)

usage:
    python scripts/qa/check_prohibited_endorsements.py
    # 自定义 yml / scan 根:
    python scripts/qa/check_prohibited_endorsements.py --yml <path> --root <dir>

exit 0 = OK (无 block 命中) / exit 1 = block 命中 (PR 必 reject) / exit 2 = 配置错误
"""

from __future__ import annotations

import argparse
import fnmatch
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

try:
    import yaml
except ImportError:
    print(
        "[lint:fatal] pyyaml 未安装. CI 用 actions/setup-python + pip install pyyaml.",
        file=sys.stderr,
    )
    sys.exit(2)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_YML = REPO_ROOT / "docs" / "copy-lint" / "prohibited-occupational-endorsements.yml"

# 实施层额外 scan_exclude (yml `tests/**` 不覆盖嵌套测试目录, 这里兜底).
# 凡测试 fixture 含用户真实证书名 (如 "护士资格证") 不应触发 lint, 否则误杀业务字段.
_IMPLICIT_EXCLUDES: tuple[str, ...] = (
    "**/*.test.ts",
    "**/*.test.tsx",
    "**/*.test.js",
    "**/*.spec.ts",
    "**/*.spec.tsx",
    "**/*.spec.js",
    "**/test_*.py",
    "**/__tests__/**",
    "**/.git/**",
)

logger = logging.getLogger("copy-lint")


@dataclass(frozen=True)
class Pattern:
    """单个禁词条目."""

    id: str
    pattern: str
    reason: str
    severity: str  # "block" | "warn"


@dataclass(frozen=True)
class LintSpec:
    """yml 中 lint_spec 段, 给 hutao 的实施约束."""

    scan_paths: tuple[str, ...]
    scan_exclude: tuple[str, ...]
    case_sensitive: bool
    fail_on: tuple[str, ...]
    warn_on: tuple[str, ...]


@dataclass(frozen=True)
class Hit:
    """一次命中."""

    file: Path
    line_no: int
    line_text: str
    pattern: Pattern


# ---------- yml 加载 ----------


def load_yml(path: Path) -> tuple[list[Pattern], list[str], LintSpec]:
    """加载禁词 yml, 返回 (patterns, allow_in_explanations, lint_spec)."""
    if not path.exists():
        print(f"[lint:fatal] yml 不存在: {path}", file=sys.stderr)
        sys.exit(2)

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        print(f"[lint:fatal] yml 解析失败: {path}: {exc}", file=sys.stderr)
        sys.exit(2)

    patterns: list[Pattern] = []
    for section in (
        "prohibited_occupational_endorsements",
        "prohibited_occupational_endorsements_extended",
        "prohibited_efficacy_endorsements",
    ):
        for item in raw.get(section, []) or []:
            patterns.append(
                Pattern(
                    id=str(item["id"]),
                    pattern=str(item["pattern"]),
                    reason=str(item.get("reason", "")),
                    severity=str(item.get("severity", "block")).lower(),
                )
            )

    allow_in_explanations = [str(s) for s in raw.get("allow_in_explanations", []) or []]

    spec_raw = raw.get("lint_spec", {}) or {}
    match_rule = spec_raw.get("match_rule", {}) or {}
    output = spec_raw.get("output", {}) or {}

    spec = LintSpec(
        scan_paths=tuple(str(p) for p in spec_raw.get("scan_paths", []) or []),
        scan_exclude=tuple(str(p) for p in spec_raw.get("scan_exclude", []) or []),
        case_sensitive=bool(match_rule.get("case_sensitive", False)),
        fail_on=tuple(str(s).lower() for s in output.get("fail_on", ["block"])),
        warn_on=tuple(str(s).lower() for s in output.get("warn_on", ["warn"])),
    )

    if not patterns:
        print(f"[lint:fatal] yml 中无任何禁词条目: {path}", file=sys.stderr)
        sys.exit(2)
    if not spec.scan_paths:
        print(f"[lint:fatal] yml lint_spec.scan_paths 为空: {path}", file=sys.stderr)
        sys.exit(2)

    return patterns, allow_in_explanations, spec


# ---------- 文件枚举 ----------


def _matches_any(path_str: str, globs: Iterable[str]) -> bool:
    return any(fnmatch.fnmatch(path_str, g) for g in globs)


def enumerate_files(root: Path, spec: LintSpec) -> list[Path]:
    """枚举 spec.scan_paths 下满足 glob 的文件, 应用 scan_exclude + _IMPLICIT_EXCLUDES."""
    excludes = tuple(spec.scan_exclude) + _IMPLICIT_EXCLUDES
    out: list[Path] = []
    seen: set[Path] = set()
    for glob_pat in spec.scan_paths:
        # glob 含 `{ts,tsx,vue,json}` 这类 brace 扩展, Path.glob 不支持, 手动展开.
        for expanded in _expand_braces(glob_pat):
            for p in root.glob(expanded):
                if not p.is_file():
                    continue
                rel = p.relative_to(root).as_posix()
                if _matches_any(rel, excludes):
                    continue
                # 自身配置目录跳过 (yml 中 scan_exclude 已含 docs/copy-lint/**, 这里冗余兜底)
                if rel.startswith("docs/copy-lint/"):
                    continue
                if p not in seen:
                    seen.add(p)
                    out.append(p)
    return sorted(out)


def _expand_braces(glob_pat: str) -> list[str]:
    """展开 `foo/**/*.{ts,tsx}` -> [`foo/**/*.ts`, `foo/**/*.tsx`].

    仅支持单层 brace + 逗号分隔; 复杂情况退回原 pattern.
    """
    if "{" not in glob_pat or "}" not in glob_pat:
        return [glob_pat]
    start = glob_pat.index("{")
    end = glob_pat.index("}", start)
    if end <= start:
        return [glob_pat]
    prefix = glob_pat[:start]
    suffix = glob_pat[end + 1 :]
    body = glob_pat[start + 1 : end]
    alternatives = [a.strip() for a in body.split(",") if a.strip()]
    if not alternatives:
        return [glob_pat]
    return [f"{prefix}{alt}{suffix}" for alt in alternatives]


# ---------- 匹配 ----------


def _normalize(text: str, case_sensitive: bool) -> str:
    return text if case_sensitive else text.lower()


def _line_is_exempt(line: str, allow_in_explanations: Sequence[str], case_sensitive: bool) -> bool:
    """line 是否落在「反向声明 / 引用语境」豁免."""
    haystack = _normalize(line, case_sensitive)
    for phrase in allow_in_explanations:
        needle = _normalize(phrase, case_sensitive)
        if needle and needle in haystack:
            return True
    return False


def scan_file(
    file: Path,
    patterns: Sequence[Pattern],
    allow_in_explanations: Sequence[str],
    case_sensitive: bool,
) -> list[Hit]:
    """扫一个文件, 返回所有命中 (block + warn)."""
    try:
        text = file.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        # 二进制 / 编码异常文件跳过
        return []
    hits: list[Hit] = []
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        if _line_is_exempt(raw_line, allow_in_explanations, case_sensitive):
            continue
        norm_line = _normalize(raw_line, case_sensitive)
        for pat in patterns:
            needle = _normalize(pat.pattern, case_sensitive)
            if not needle:
                continue
            if needle in norm_line:
                hits.append(Hit(file=file, line_no=line_no, line_text=raw_line.rstrip(), pattern=pat))
    return hits


# ---------- 主流程 ----------


def _relative_or_absolute(path: Path, root: Path) -> str:
    """Return ``path`` relative to ``root`` when possible, without Py3.9-only APIs."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _format_hit(hit: Hit, root: Path) -> str:
    rel = _relative_or_absolute(hit.file, root)
    txt = hit.line_text[:160] + ("..." if len(hit.line_text) > 160 else "")
    return (
        f"  [{hit.pattern.severity.upper()}] {hit.pattern.id} '{hit.pattern.pattern}'"
        f" @ {rel}:{hit.line_no}\n"
        f"      {txt}\n"
        f"      理由: {hit.pattern.reason}"
    )


def run_lint(yml_path: Path, root: Path) -> int:
    """主流程. 返回 exit code (0/1/2)."""
    patterns, allow, spec = load_yml(yml_path)
    files = enumerate_files(root, spec)

    print(
        f"[lint:info] yml={_relative_or_absolute(yml_path, root)}"
        f" 禁词={len(patterns)} 豁免短语={len(allow)} 扫描文件={len(files)}"
    )

    all_hits: list[Hit] = []
    for f in files:
        all_hits.extend(scan_file(f, patterns, allow, spec.case_sensitive))

    block_hits = [h for h in all_hits if h.pattern.severity in spec.fail_on]
    warn_hits = [h for h in all_hits if h.pattern.severity in spec.warn_on]

    if warn_hits:
        print(f"[lint:warn] 命中 warn 级 {len(warn_hits)} 处 (不阻塞, 仅日志):", file=sys.stderr)
        for h in warn_hits:
            print(_format_hit(h, root), file=sys.stderr)

    if block_hits:
        print(
            f"[lint:fail] 命中 block 级 {len(block_hits)} 处 (CI 阻塞 PR):",
            file=sys.stderr,
        )
        for h in block_hits:
            print(_format_hit(h, root), file=sys.stderr)
        print(
            "\n[lint:hint] 修改建议:\n"
            "  1) 用 yml 中 'suggest' 字段替换 (e.g. 资格 -> 资质)\n"
            "  2) 若属合规说明语境, 在 yml `allow_in_explanations` 加豁免短语 (需 PM 批)\n"
            "  3) 不要直接删 yml 条目 (PM + Owner 双签)\n",
            file=sys.stderr,
        )
        return 1

    print(f"[lint:ok] 全部 {len(files)} 文件无 block 命中. warn 命中 {len(warn_hits)} 处 (见 stderr).")
    return 0


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="职业背书 / 效果背书禁词 lint 哨兵.")
    parser.add_argument(
        "--yml",
        type=Path,
        default=DEFAULT_YML,
        help=f"禁词 yml 路径, 默认 {DEFAULT_YML.relative_to(REPO_ROOT)}",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help=f"repo 根目录, 默认 {REPO_ROOT}",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    return run_lint(args.yml, args.root)


if __name__ == "__main__":
    sys.exit(main())
