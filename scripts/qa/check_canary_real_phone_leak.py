#!/usr/bin/env python3
"""S2-OPS-A-REAL-LAUNCH 安全哨兵: canary real.yaml 真号意外提交 lint.

凝光 Q2=a (2026-06-29): canary 真实灰度白名单只在 yaml 存掩码 (前3****后4),
真号走 phone_env 注入的 encrypted secret + runtime ENV, 绝不入 git。本脚本
CI grep 防真号意外明文落 yaml: 扫 deploy/canary/whitelist_phones.real.yaml,
命中疑似真手机号 (1[3-9]\\d{9}) 即 fail, 排除安全号段:
  - sentinel 13800000000 (e2e/smoke 永久保留, 与 seed_canary 对齐)
  - dry-run 占位 1380000000X (138 + 8 个 0 + 1 位, 明示非真号)

掩码格式 (157****2719 等) 不含连续 11 位数字 -> 不会命中。

usage:
    python scripts/qa/check_canary_real_phone_leak.py
    python scripts/qa/check_canary_real_phone_leak.py --file <path>

exit 0 = OK (无真号) / exit 1 = 命中疑似真号 (PR 必 reject) / exit 2 = 配置错误
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FILE = REPO_ROOT / "deploy" / "canary" / "whitelist_phones.real.yaml"

# 中国大陆手机号: 1 + 3-9 + 9 位
PHONE_RE = re.compile(r"1[3-9]\d{9}")
# 安全号段白名单: sentinel + dry-run 占位 (138 + 0000000 + 末位), 明示非真号
SAFE_RE = re.compile(r"^1380000000\d$")


def scan(path: Path) -> list[tuple[int, str]]:
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        for m in PHONE_RE.findall(line):
            if SAFE_RE.match(m):
                continue
            hits.append((lineno, m))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="canary real.yaml 真号泄漏哨兵")
    ap.add_argument("--file", default=str(DEFAULT_FILE), help="real.yaml 路径")
    args = ap.parse_args()
    p = Path(args.file)
    if not p.exists():
        print(f"[phone-lint:ok] {p} 不存在, skip", file=sys.stderr)
        return 0
    hits = scan(p)
    if hits:
        print(f"[phone-lint:fail] {p} 命中疑似真手机号, 真号必须走 phone_env ENV:")
        for lineno, num in hits:
            masked = num[:3] + "****" + num[-4:]
            print(f"  line {lineno}: {masked} (真号不可入 git, 用掩码+phone_env)")
        return 1
    print(f"[phone-lint:ok] {p} 无真号 (仅掩码/安全段)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
