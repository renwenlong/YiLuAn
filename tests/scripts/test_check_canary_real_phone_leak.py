"""Unit tests for scripts/qa/check_canary_real_phone_leak.py.

S2-OPS-A-REAL-LAUNCH 安全哨兵: canary real.yaml 真号意外提交 lint (凝光 Q2=a)。
真号只走 phone_env ENV, yaml 仅掩码。脚本扫 real.yaml 命中疑似真号 (1[3-9]\\d{9})
即 exit 1, 排除 sentinel 13800000000 + dry-run 1380000000X 安全段。

测试策略 (AAA + 黑盒): 临时文件构造各场景, 调 scan()/main 验 hits + exit code。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "qa" / "check_canary_real_phone_leak.py"
)
_spec = importlib.util.spec_from_file_location("check_canary_real_phone_leak", _SCRIPT)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
sys.modules["check_canary_real_phone_leak"] = mod
_spec.loader.exec_module(mod)


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "real.yaml"
    p.write_text(body, encoding="utf-8")
    return p


def test_masked_only_passes(tmp_path):
    """掩码格式 (前3****后4) 不含连续11位 → 无命中。"""
    p = _write(tmp_path, 'team:\n  - phone: "157****2719"\n    phone_env: X\n')
    assert mod.scan(p) == []


def test_real_phone_detected(tmp_path):
    """明文真号 → 命中 fail。"""
    p = _write(tmp_path, 'colleagues:\n  - phone: "13912345678"\n')
    hits = mod.scan(p)
    assert len(hits) == 1 and hits[0][1] == "13912345678"


def test_sentinel_exempt(tmp_path):
    """sentinel 13800000000 安全段豁免。"""
    p = _write(tmp_path, 'sentinels:\n  - phone: "13800000000"\n')
    assert mod.scan(p) == []


def test_dryrun_placeholder_exempt(tmp_path):
    """dry-run 占位 1380000000X (末位 1-5) 豁免。"""
    p = _write(tmp_path, 'team:\n  - phone: "13800000001"\n  - phone: "13800000005"\n')
    assert mod.scan(p) == []


def test_missing_file_ok(tmp_path):
    """文件不存在 → exit 0 (skip)。"""
    sys.argv = ["x", "--file", str(tmp_path / "nope.yaml")]
    assert mod.main() == 0


def test_real_smoke_passes():
    """真 repo real.yaml 集成 smoke: 仅掩码 → exit 0。"""
    sys.argv = ["x"]
    assert mod.main() == 0
