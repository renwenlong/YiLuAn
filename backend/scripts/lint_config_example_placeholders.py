#!/usr/bin/env python3
"""S3-OPS-CONFIG-EXAMPLE-PLACEHOLDER-LINT: deploy/env.*.example placeholder hygiene lint.

设计目的 (AC#3 — docs hygiene):
    ``deploy/env.*.example`` 文件按设计带 ``__CHANGE_ME__`` placeholder, 提示运维
    部署前必须逐项替换真实值。本脚本扫描这些 example 文件, 列出所有仍是 placeholder
    的条目 (文件名 + 行号 + 变量名), 让运维 / CI 清楚知道「这些位置必须替换」。

跟 S3-OPS-SALT-ENTROPY-GUARD-CI-INTEGRATION 的关系 (AC#5 — 互补, 非重叠):
    - 那个 task (verify_env_salts.py): validator runtime 哨兵 + CI **hard fail** —
      抓真 env.* 的 salt entropy 不足 / 雷同 (运维替换后的弱值)。
    - 本 task (本脚本): docs hygiene + CI **soft warn** —
      抓 example 文件里**没替换**的 placeholder 字面 (运维忘了 cp + 改)。
    两者覆盖不同失败模式, 可并行 ship。

为何 placeholder lint 是 warn-only 而非 hard fail:
    ``__CHANGE_ME__`` 出现在 ``*.example`` 是**正确的**设计 (example 就该带提示)。
    真 prod ``env.production`` 不入库且运维会替换。即便运维忘替换直接部署,
    ``ContractService`` runtime 哨兵也会抓弱 hash。所以这里只做 advisory 提示,
    不 block merge (AC#4)。

usage:
    python backend/scripts/lint_config_example_placeholders.py
    # 自定义扫描根 (测试用):
    python backend/scripts/lint_config_example_placeholders.py --root <dir>
    # 自定义 glob:
    python backend/scripts/lint_config_example_placeholders.py --glob 'deploy/env.*.example'

exit 0 = 无 placeholder 命中 (干净)
exit 1 = 有 placeholder 命中 (列出清单; CI warn-only step 用 continue-on-error 降级为提示)
exit 2 = 配置 / 用法错误 (扫描根不存在等)
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

# 默认扫描根 = repo 根 (本脚本在 backend/scripts/ → parents[2] 是 repo 根)。
REPO_ROOT = Path(__file__).resolve().parents[2]

# placeholder 字面标记。example 文件用此前缀标注「运维必须替换」的位置。
PLACEHOLDER_MARKER = "__CHANGE_ME__"

# 默认扫描的 glob (相对扫描根)。覆盖 deploy/ 下所有 env.*.example。
DEFAULT_GLOBS: tuple[str, ...] = ("deploy/env.*.example",)


@dataclass(frozen=True)
class Hit:
    """一处 placeholder 命中。"""

    file: Path  # 相对扫描根的路径
    lineno: int  # 1-based 行号
    var_name: str  # 等号左侧的变量名 (无法解析时为 "?")
    raw_line: str  # 原始行 (strip 后), 用于上下文展示


def _extract_var_name(line: str) -> str:
    """从 ``KEY=value`` 形式的行提取 KEY; 解析不出时返回 '?'。"""
    stripped = line.strip()
    # 跳过注释行的等号 (理论上注释里也可能有 placeholder, 但变量名取不到)
    if "=" in stripped:
        key = stripped.split("=", 1)[0].strip()
        # 去掉行内可能的前导 export
        if key.startswith("export "):
            key = key[len("export ") :].strip()
        if key:
            return key
    return "?"


def scan_file(path: Path, root: Path) -> list[Hit]:
    """扫描单个文件, 返回所有含 PLACEHOLDER_MARKER 的行。"""
    hits: list[Hit] = []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:  # pragma: no cover - 防御性
        print(f"[lint:warn] 跳过无法读取的文件 {path}: {exc}", file=sys.stderr)
        return hits
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    for idx, line in enumerate(text.splitlines(), start=1):
        if PLACEHOLDER_MARKER in line:
            hits.append(
                Hit(
                    file=rel,
                    lineno=idx,
                    var_name=_extract_var_name(line),
                    raw_line=line.strip(),
                )
            )
    return hits


def collect_files(root: Path, globs: Sequence[str]) -> list[Path]:
    """按 glob 收集待扫描文件 (去重 + 排序, 稳定输出)。"""
    seen: set[Path] = set()
    for pattern in globs:
        for p in sorted(root.glob(pattern)):
            if p.is_file():
                seen.add(p)
    return sorted(seen)


def lint(root: Path, globs: Sequence[str]) -> tuple[int, list[Hit]]:
    """主逻辑。返回 (exit_code, hits)。"""
    if not root.exists():
        print(f"[lint:fatal] 扫描根不存在: {root}", file=sys.stderr)
        return 2, []

    files = collect_files(root, globs)
    if not files:
        # 没有匹配文件不是错误 (可能 repo 暂无 example), 但提示一下。
        print(
            f"[lint:info] 未匹配到任何 example 文件 (root={root}, globs={list(globs)})。",
            file=sys.stderr,
        )
        return 0, []

    all_hits: list[Hit] = []
    for f in files:
        all_hits.extend(scan_file(f, root))

    return (1 if all_hits else 0), all_hits


def _print_report(hits: Iterable[Hit]) -> None:
    """打印 hygiene 报告 (文件名 + 行号 + 变量名)。"""
    hits = list(hits)
    if not hits:
        print("[lint:ok] 所有 deploy/env.*.example 无未替换的 __CHANGE_ME__ placeholder。")
        return
    print(
        f"[lint:warn] 发现 {len(hits)} 处未替换的 __CHANGE_ME__ placeholder "
        "(example 设计预期; 部署前运维必须替换):",
        file=sys.stderr,
    )
    for h in hits:
        print(
            f"  {h.file}:{h.lineno}: {h.var_name} -> {h.raw_line}",
            file=sys.stderr,
        )
    print(
        "\n[lint:hint] 这是 docs hygiene 提示 (warn-only, 不 block merge)。"
        "\n            部署 SOP: cp env.production.example env.production 后逐项替换 "
        "__CHANGE_ME__ 真实值。"
        "\n            详见 docs/deployment.md。",
        file=sys.stderr,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "扫描 deploy/env.*.example 中未替换的 __CHANGE_ME__ placeholder "
            "(docs hygiene, warn-only)。"
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="扫描根目录 (默认 repo 根)。",
    )
    parser.add_argument(
        "--glob",
        action="append",
        dest="globs",
        default=None,
        help=f"扫描 glob (相对 root, 可多次); 默认 {list(DEFAULT_GLOBS)}。",
    )
    args = parser.parse_args(argv)

    globs = tuple(args.globs) if args.globs else DEFAULT_GLOBS
    code, hits = lint(args.root, globs)
    _print_report(hits)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
