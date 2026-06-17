"""Unit tests for ``scripts/qa/check_prohibited_endorsements.py``.

S3-DEV-003-ADMIN-COPY AC#4 — 职业背书 / 效果背书禁词 lint 哨兵 unit test.

Test strategy: build tmp yml + tmp scan tree, drive run_lint() + main(), assert
exit code + hits + warn 行为. 不 hit 真 repo 文件, 全 sandbox.

Covers:
  - load_yml: yml 缺失 / 无禁词 / 无 scan_paths 报错
  - enumerate_files: scan_paths brace 展开 + scan_exclude + IMPLICIT_EXCLUDES + 去重
  - scan_file: 命中 / 大小写不敏感 / 空 pattern 跳过 / 二进制跳过
  - allow_in_explanations: 反向声明语境豁免
  - run_lint: block 命中 -> exit 1 / warn 命中 -> exit 0 + stderr / 全 OK -> exit 0
  - real repo: 当前 repo 跑全过 (回归保护)
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT_PATH = REPO_ROOT / "scripts" / "qa" / "check_prohibited_endorsements.py"


# ----------------------------------------------------------------------------
# Load script as module
# ----------------------------------------------------------------------------


@pytest.fixture(scope="module")
def lint_module():
    spec = importlib.util.spec_from_file_location(
        "check_prohibited_endorsements", str(_SCRIPT_PATH)
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


# ----------------------------------------------------------------------------
# Fixture helpers
# ----------------------------------------------------------------------------


def _write_yml(tmp_path: Path, *, with_lint_spec: bool = True, scan_paths=None, scan_exclude=None) -> Path:
    """Build a minimal but valid yml in tmp_path."""
    scan_paths = scan_paths or ["src/**/*.md"]
    scan_exclude = scan_exclude or []
    yml = tmp_path / "prohibited.yml"

    lines: list[str] = [
        "version: 0",
        "prohibited_occupational_endorsements:",
        '  - id: PO-001',
        '    pattern: "已护士"',
        '    reason: "把人=职业"',
        '    severity: block',
        '  - id: PO-002',
        '    pattern: "Doctor"',
        '    reason: "english test"',
        '    severity: block',
        "",
        "prohibited_occupational_endorsements_extended:",
        '  - id: PO-003',
        '    pattern: "执业医师"',
        '    reason: "卫健委监管"',
        '    severity: block',
        "",
        "prohibited_efficacy_endorsements:",
        '  - id: EE-001',
        '    pattern: "包治"',
        '    reason: "疗效承诺"',
        '    severity: block',
        '  - id: EE-002',
        '    pattern: "专家级"',
        '    reason: "弱化背书"',
        '    severity: warn',
        "",
        "allow_in_explanations:",
        '  - "不就职业身份背书"',
        '  - "陪诊师不等同医师"',
    ]

    if with_lint_spec:
        lines.append("")
        lines.append("lint_spec:")
        lines.append("  scan_paths:")
        for p in scan_paths:
            lines.append(f'    - "{p}"')
        if scan_exclude:
            lines.append("  scan_exclude:")
            for e in scan_exclude:
                lines.append(f'    - "{e}"')
        else:
            lines.append("  scan_exclude: []")
        lines.append("  match_rule:")
        lines.append("    case_sensitive: false")
        lines.append("    chinese_substring: true")
        lines.append("    english_word_boundary: true")
        lines.append("  output:")
        lines.append("    fail_on: [block]")
        lines.append("    warn_on: [warn]")

    yml.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return yml


def _mkfile(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ----------------------------------------------------------------------------
# load_yml
# ----------------------------------------------------------------------------


class TestLoadYml:
    def test_missing_yml_fatal(self, lint_module, tmp_path):
        with pytest.raises(SystemExit) as exc:
            lint_module.load_yml(tmp_path / "nope.yml")
        assert exc.value.code == 2

    def test_yml_no_patterns_fatal(self, lint_module, tmp_path):
        yml = tmp_path / "empty.yml"
        yml.write_text("version: 0\nlint_spec:\n  scan_paths:\n    - foo\n", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            lint_module.load_yml(yml)
        assert exc.value.code == 2

    def test_yml_no_scan_paths_fatal(self, lint_module, tmp_path):
        yml = _write_yml(tmp_path, with_lint_spec=False)
        with pytest.raises(SystemExit) as exc:
            lint_module.load_yml(yml)
        assert exc.value.code == 2

    def test_yml_invalid_yaml_fatal(self, lint_module, tmp_path):
        yml = tmp_path / "bad.yml"
        yml.write_text("version: 0\n  bad: indent: {", encoding="utf-8")
        with pytest.raises(SystemExit) as exc:
            lint_module.load_yml(yml)
        assert exc.value.code == 2

    def test_yml_full_load(self, lint_module, tmp_path):
        yml = _write_yml(tmp_path)
        patterns, allow, spec = lint_module.load_yml(yml)
        # 2 + 1 + 2 = 5 patterns
        assert len(patterns) == 5
        ids = {p.id for p in patterns}
        assert ids == {"PO-001", "PO-002", "PO-003", "EE-001", "EE-002"}
        # severities split correctly
        severities = {p.id: p.severity for p in patterns}
        assert severities["EE-002"] == "warn"
        assert severities["PO-001"] == "block"
        # allow + spec
        assert "不就职业身份背书" in allow
        assert spec.case_sensitive is False
        assert "block" in spec.fail_on
        assert "warn" in spec.warn_on


# ----------------------------------------------------------------------------
# enumerate_files
# ----------------------------------------------------------------------------


class TestEnumerateFiles:
    def test_brace_expansion(self, lint_module, tmp_path):
        _mkfile(tmp_path, "src/a.ts", "")
        _mkfile(tmp_path, "src/b.tsx", "")
        _mkfile(tmp_path, "src/c.py", "")
        yml = _write_yml(tmp_path, scan_paths=["src/**/*.{ts,tsx}"])
        _, _, spec = lint_module.load_yml(yml)
        files = lint_module.enumerate_files(tmp_path, spec)
        names = sorted(f.name for f in files)
        assert names == ["a.ts", "b.tsx"]

    def test_scan_exclude_from_yml(self, lint_module, tmp_path):
        _mkfile(tmp_path, "src/a.md", "hit")
        _mkfile(tmp_path, "src/build/b.md", "should skip")
        yml = _write_yml(tmp_path, scan_paths=["src/**/*.md"], scan_exclude=["**/build/**"])
        _, _, spec = lint_module.load_yml(yml)
        files = lint_module.enumerate_files(tmp_path, spec)
        names = sorted(f.name for f in files)
        assert names == ["a.md"]

    def test_implicit_test_file_exclude(self, lint_module, tmp_path):
        _mkfile(tmp_path, "src/page.ts", "")
        _mkfile(tmp_path, "src/page.test.ts", "")
        _mkfile(tmp_path, "src/page.spec.tsx", "")
        _mkfile(tmp_path, "src/__tests__/inner.ts", "")
        yml = _write_yml(tmp_path, scan_paths=["src/**/*.{ts,tsx}"])
        _, _, spec = lint_module.load_yml(yml)
        files = lint_module.enumerate_files(tmp_path, spec)
        names = sorted(f.relative_to(tmp_path).as_posix() for f in files)
        # 仅 page.ts 入 lint, 其余测试文件由 _IMPLICIT_EXCLUDES 排除
        assert names == ["src/page.ts"]

    def test_copy_lint_self_skipped(self, lint_module, tmp_path):
        _mkfile(tmp_path, "src/a.md", "hit")
        _mkfile(tmp_path, "docs/copy-lint/x.yml", "should skip")
        yml = _write_yml(tmp_path, scan_paths=["**/*.md", "**/*.yml"])
        _, _, spec = lint_module.load_yml(yml)
        files = lint_module.enumerate_files(tmp_path, spec)
        rels = {f.relative_to(tmp_path).as_posix() for f in files}
        assert "docs/copy-lint/x.yml" not in rels
        assert "src/a.md" in rels

    def test_dedup_across_multiple_globs(self, lint_module, tmp_path):
        _mkfile(tmp_path, "src/page.md", "")
        # Two globs both match same file
        yml = _write_yml(tmp_path, scan_paths=["src/**/*.md", "**/*.md"])
        _, _, spec = lint_module.load_yml(yml)
        files = lint_module.enumerate_files(tmp_path, spec)
        # 同一文件被多 glob 命中只出现一次
        assert len(files) == 1


# ----------------------------------------------------------------------------
# scan_file
# ----------------------------------------------------------------------------


class TestScanFile:
    def test_simple_block_hit(self, lint_module, tmp_path):
        yml = _write_yml(tmp_path)
        patterns, allow, spec = lint_module.load_yml(yml)
        f = _mkfile(tmp_path, "src/a.md", "violation: 已护士 inline\n")
        hits = lint_module.scan_file(f, patterns, allow, spec.case_sensitive)
        assert len(hits) == 1
        assert hits[0].pattern.id == "PO-001"
        assert hits[0].line_no == 1

    def test_case_insensitive_english(self, lint_module, tmp_path):
        yml = _write_yml(tmp_path)
        patterns, allow, spec = lint_module.load_yml(yml)
        f = _mkfile(tmp_path, "src/a.md", "we are professional doctor.\n")
        hits = lint_module.scan_file(f, patterns, allow, spec.case_sensitive)
        ids = {h.pattern.id for h in hits}
        # "Doctor" pattern case-insensitive match
        assert "PO-002" in ids

    def test_multi_hits_one_line(self, lint_module, tmp_path):
        yml = _write_yml(tmp_path)
        patterns, allow, spec = lint_module.load_yml(yml)
        f = _mkfile(tmp_path, "src/a.md", "已护士 + 包治 + 执业医师 三连\n")
        hits = lint_module.scan_file(f, patterns, allow, spec.case_sensitive)
        ids = sorted(h.pattern.id for h in hits)
        assert ids == ["EE-001", "PO-001", "PO-003"]

    def test_allow_in_explanations_exempts_line(self, lint_module, tmp_path):
        yml = _write_yml(tmp_path)
        patterns, allow, spec = lint_module.load_yml(yml)
        # 反向声明语境: 整段含豁免短语, 命中应被跳过
        f = _mkfile(
            tmp_path,
            "src/a.md",
            "本条款明示「不就职业身份背书」，故不出现已护士 / 执业医师 字眼\n",
        )
        hits = lint_module.scan_file(f, patterns, allow, spec.case_sensitive)
        assert hits == []

    def test_allow_in_explanations_only_per_line(self, lint_module, tmp_path):
        """豁免是 line-level, 别行的禁词仍触发."""
        yml = _write_yml(tmp_path)
        patterns, allow, spec = lint_module.load_yml(yml)
        f = _mkfile(
            tmp_path,
            "src/a.md",
            dedent(
                """\
                第一行: 不就职业身份背书 + 已护士 字眼 (本行豁免)
                第二行: 已护士 (无豁免短语, 本行 hit)
                """
            ),
        )
        hits = lint_module.scan_file(f, patterns, allow, spec.case_sensitive)
        assert len(hits) == 1
        assert hits[0].line_no == 2

    def test_binary_file_skipped(self, lint_module, tmp_path):
        yml = _write_yml(tmp_path)
        patterns, allow, spec = lint_module.load_yml(yml)
        f = tmp_path / "src" / "bin.md"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"\xff\xfe\x00\xff non-utf8\x00")
        hits = lint_module.scan_file(f, patterns, allow, spec.case_sensitive)
        assert hits == []

    def test_warn_severity_returned(self, lint_module, tmp_path):
        yml = _write_yml(tmp_path)
        patterns, allow, spec = lint_module.load_yml(yml)
        f = _mkfile(tmp_path, "src/a.md", "本服务 专家级 严选\n")
        hits = lint_module.scan_file(f, patterns, allow, spec.case_sensitive)
        assert len(hits) == 1
        assert hits[0].pattern.severity == "warn"
        assert hits[0].pattern.id == "EE-002"

    def test_no_hits_clean_file(self, lint_module, tmp_path):
        yml = _write_yml(tmp_path)
        patterns, allow, spec = lint_module.load_yml(yml)
        f = _mkfile(tmp_path, "src/a.md", "干净文案 / 资质认证 / 临时证明补交中\n")
        hits = lint_module.scan_file(f, patterns, allow, spec.case_sensitive)
        assert hits == []


# ----------------------------------------------------------------------------
# run_lint integration (exit codes)
# ----------------------------------------------------------------------------


class TestPathFormatting:
    def test_relative_or_absolute_under_root(self, lint_module, tmp_path):
        path = tmp_path / "src" / "a.md"
        path.parent.mkdir(parents=True)
        path.write_text("", encoding="utf-8")

        assert lint_module._relative_or_absolute(path, tmp_path) == "src/a.md"

    def test_relative_or_absolute_outside_root(self, lint_module, tmp_path):
        outside = tmp_path.parent / "outside.md"

        assert lint_module._relative_or_absolute(outside, tmp_path) == str(outside)


class TestPO009PO010Regression:
    """S3-DEV-003-COPY-LINT-P3-PO-009-WORD-BOUNDARY 回归锁定 (方案 a).

    PO-009/010 在 merged yml 是全短语 '在职医生'/'在职护士' (word-anchored),
    本来就不误杀 '在职状态'/'不在职' 等正常词。本类锁住当前安全行为,
    防未来被改回裸 '在职' 而造成误杀回归。
    """

    @pytest.fixture(scope="class")
    def real_yml_loaded(self, lint_module):
        yml = REPO_ROOT / "docs" / "copy-lint" / "prohibited-occupational-endorsements.yml"
        return lint_module.load_yml(yml)

    def _ids_for(self, lint_module, loaded, text):
        import tempfile

        patterns, allow, spec = loaded
        d = Path(tempfile.mkdtemp())
        f = d / "a.md"
        f.write_text(text, encoding="utf-8")
        return sorted({h.pattern.id for h in lint_module.scan_file(f, patterns, allow, spec.case_sensitive)})

    def test_po009_010_are_full_phrase_patterns(self, lint_module, real_yml_loaded):
        """AC#3: pattern 本体仍是全短语 (不是裸 '在职'), 防放宽回退."""
        patterns, _, _ = real_yml_loaded
        by_id = {p.id: p.pattern for p in patterns}
        assert by_id.get("PO-009") == "在职医生"
        assert by_id.get("PO-010") == "在职护士"

    @pytest.mark.parametrize(
        "neutral", ["在职状态", "在职期间", "不在职", "在职员工", "在职证明"]
    )
    def test_po009_010_no_false_positive(self, lint_module, real_yml_loaded, neutral):
        """AC#1: 正常用词 0 命中 PO-009/PO-010."""
        ids = self._ids_for(lint_module, real_yml_loaded, neutral)
        assert "PO-009" not in ids and "PO-010" not in ids, f"{neutral!r} should not hit PO-009/010, got {ids}"

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("在职医生", "PO-009"),
            ("三甲在职医生", "PO-009"),
            ("在职护士", "PO-010"),
            ("聘请在职护士", "PO-010"),
        ],
    )
    def test_po009_010_original_intent_still_blocks(self, lint_module, real_yml_loaded, text, expected):
        """AC#2: 原意职业身份背书仍命中对应 pattern."""
        ids = self._ids_for(lint_module, real_yml_loaded, text)
        assert expected in ids, f"{text!r} should hit {expected}, got {ids}"


class TestRunLint:
    def test_block_hit_exit_1(self, lint_module, tmp_path, capsys):
        yml = _write_yml(tmp_path)
        _mkfile(tmp_path, "src/violate.md", "本平台 已护士\n")
        code = lint_module.run_lint(yml, tmp_path)
        assert code == 1
        captured = capsys.readouterr()
        assert "block" in captured.err.lower()
        assert "PO-001" in captured.err

    def test_warn_only_exit_0(self, lint_module, tmp_path, capsys):
        yml = _write_yml(tmp_path)
        _mkfile(tmp_path, "src/warn.md", "本服务 专家级 严选\n")
        code = lint_module.run_lint(yml, tmp_path)
        assert code == 0  # warn 不阻塞
        captured = capsys.readouterr()
        # warn 命中应在 stderr 输出
        assert "warn" in captured.err.lower()
        assert "EE-002" in captured.err

    def test_all_clean_exit_0(self, lint_module, tmp_path, capsys):
        yml = _write_yml(tmp_path)
        _mkfile(tmp_path, "src/ok.md", "干净文案 / 资质认证\n")
        code = lint_module.run_lint(yml, tmp_path)
        assert code == 0
        captured = capsys.readouterr()
        assert "ok" in captured.out.lower() or "无 block 命中" in captured.out

    def test_explanation_exempts_block(self, lint_module, tmp_path):
        yml = _write_yml(tmp_path)
        _mkfile(
            tmp_path,
            "src/explain.md",
            "本条款 不就职业身份背书 + 不出现已护士 字眼\n",
        )
        code = lint_module.run_lint(yml, tmp_path)
        assert code == 0


# ----------------------------------------------------------------------------
# CLI smoke (subprocess)
# ----------------------------------------------------------------------------


class TestCliMain:
    def test_main_exit_code_propagates(self, tmp_path):
        """run as `python script.py --yml tmp --root tmp` propagates exit code."""
        yml = _write_yml(tmp_path)
        _mkfile(tmp_path, "src/violate.md", "本平台 已护士\n")
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH), "--yml", str(yml), "--root", str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 1
        assert "PO-001" in result.stderr


# ----------------------------------------------------------------------------
# Real repo regression
# ----------------------------------------------------------------------------


class TestRealRepo:
    def test_repo_currently_passes(self):
        """回归保护: 当前 repo 跑 lint 不应报 block 命中.

        若本测试 fail, 说明有人 push 了违规 copy 但没修 yml allow_in_explanations.
        """
        result = subprocess.run(
            [sys.executable, str(_SCRIPT_PATH)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        assert result.returncode == 0, (
            f"repo lint should pass with exit 0, got {result.returncode}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
