"""Unit tests for backend/scripts/lint_config_example_placeholders.py.

S3-OPS-CONFIG-EXAMPLE-PLACEHOLDER-LINT 反案哨兵:
    扫 deploy/env.*.example 中未替换的 __CHANGE_ME__ placeholder (docs hygiene, warn-only)。

测试策略 (AAA + 黑盒):
    用临时目录构造各种 example 文件, 调 lint() 验 exit code + hits 内容。
    不依赖真实 repo 文件 (除一条 smoke test 跑真 deploy/ 确保集成不炸)。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# 动态加载被测脚本 (它在 backend/scripts/ 不是 package)。
_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "backend"
    / "scripts"
    / "lint_config_example_placeholders.py"
)
_spec = importlib.util.spec_from_file_location("lint_config_example_placeholders", _SCRIPT)
assert _spec and _spec.loader
lint_mod = importlib.util.module_from_spec(_spec)
sys.modules["lint_config_example_placeholders"] = lint_mod
_spec.loader.exec_module(lint_mod)


def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ── AC#1/#2: 找到 placeholder → exit 1 + 列文件名/行号/变量名 ──────────────────
def test_placeholder_found_exits_1(tmp_path: Path):
    _write(
        tmp_path,
        "deploy/env.production.example",
        "ENVIRONMENT=production\n"
        "POSTGRES_PASSWORD=__CHANGE_ME__strong_db_password\n"
        "JWT_SECRET_KEY=__CHANGE_ME__\n",
    )
    code, hits = lint_mod.lint(tmp_path, lint_mod.DEFAULT_GLOBS)
    assert code == 1
    assert len(hits) == 2
    # 行号正确 (1-based)
    assert {h.lineno for h in hits} == {2, 3}
    # 变量名解析正确
    assert {h.var_name for h in hits} == {"POSTGRES_PASSWORD", "JWT_SECRET_KEY"}
    # 文件路径相对 root
    assert all(str(h.file) == "deploy/env.production.example" for h in hits)


# ── AC: 无 placeholder → exit 0 (negative, 反案 #11 双向) ─────────────────────
def test_no_placeholder_exits_0(tmp_path: Path):
    _write(
        tmp_path,
        "deploy/env.production.example",
        "ENVIRONMENT=production\nPOSTGRES_PASSWORD=actual_strong_value\n",
    )
    code, hits = lint_mod.lint(tmp_path, lint_mod.DEFAULT_GLOBS)
    assert code == 0
    assert hits == []


# ── 多个 example 文件都扫 ──────────────────────────────────────────────────
def test_multiple_example_files(tmp_path: Path):
    _write(tmp_path, "deploy/env.production.example", "A=__CHANGE_ME__\n")
    _write(tmp_path, "deploy/env.staging.local.example", "B=ok\nC=__CHANGE_ME__x\n")
    code, hits = lint_mod.lint(tmp_path, lint_mod.DEFAULT_GLOBS)
    assert code == 1
    files = {str(h.file) for h in hits}
    assert files == {"deploy/env.production.example", "deploy/env.staging.local.example"}
    assert len(hits) == 2


# ── 非 .example 文件不扫 (避免误杀真 env.production) ──────────────────────────
def test_non_example_files_ignored(tmp_path: Path):
    # 真 env.production (无 .example 后缀) 即便含 placeholder 也不该被默认 glob 扫到
    _write(tmp_path, "deploy/env.production", "X=__CHANGE_ME__leftover\n")
    _write(tmp_path, "deploy/env.staging", "Y=__CHANGE_ME__leftover\n")
    code, hits = lint_mod.lint(tmp_path, lint_mod.DEFAULT_GLOBS)
    assert code == 0
    assert hits == []


# ── export 前缀变量名解析 ──────────────────────────────────────────────────
def test_export_prefix_var_name(tmp_path: Path):
    _write(tmp_path, "deploy/env.staging.local.example", "export FOO=__CHANGE_ME__\n")
    code, hits = lint_mod.lint(tmp_path, lint_mod.DEFAULT_GLOBS)
    assert code == 1
    assert hits[0].var_name == "FOO"


# ── 空目录 / 无匹配文件 → exit 0 (不是错误) ──────────────────────────────────
def test_no_matching_files_exits_0(tmp_path: Path):
    (tmp_path / "deploy").mkdir()
    code, hits = lint_mod.lint(tmp_path, lint_mod.DEFAULT_GLOBS)
    assert code == 0
    assert hits == []


# ── 扫描根不存在 → exit 2 (配置错误) ─────────────────────────────────────────
def test_missing_root_exits_2(tmp_path: Path):
    code, hits = lint_mod.lint(tmp_path / "nonexistent", lint_mod.DEFAULT_GLOBS)
    assert code == 2
    assert hits == []


# ── 自定义 glob ────────────────────────────────────────────────────────────
def test_custom_glob(tmp_path: Path):
    _write(tmp_path, "config/sample.env.example", "K=__CHANGE_ME__\n")
    # 默认 glob (deploy/env.*.example) 抓不到
    code_default, hits_default = lint_mod.lint(tmp_path, lint_mod.DEFAULT_GLOBS)
    assert code_default == 0 and hits_default == []
    # 自定义 glob 能抓到
    code_custom, hits_custom = lint_mod.lint(tmp_path, ("config/*.env.example",))
    assert code_custom == 1
    assert len(hits_custom) == 1
    assert hits_custom[0].var_name == "K"


# ── main() 入口 exit code 贯通 (AC#2 CLI 契约) ──────────────────────────────
def test_main_returns_exit_code(tmp_path: Path, monkeypatch):
    _write(tmp_path, "deploy/env.production.example", "A=__CHANGE_ME__\n")
    rc = lint_mod.main(["--root", str(tmp_path)])
    assert rc == 1
    # 干净 root → 0
    clean = tmp_path / "clean"
    _write(clean, "deploy/env.production.example", "A=real\n")
    rc2 = lint_mod.main(["--root", str(clean)])
    assert rc2 == 0


# ── smoke: 跑真 repo deploy/ 不炸 (集成防御; exit code 不强断言) ───────────────
def test_smoke_real_repo_does_not_crash():
    repo_root = Path(__file__).resolve().parents[2]
    code, hits = lint_mod.lint(repo_root, lint_mod.DEFAULT_GLOBS)
    # 真 repo 当前 production.example 带 placeholder → 预期 1, 但只要不抛异常即可。
    assert code in (0, 1)
    assert isinstance(hits, list)
