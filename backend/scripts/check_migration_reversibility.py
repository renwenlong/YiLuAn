"""Audit alembic migrations for downgrade reversibility.

Scans every revision file under `backend/alembic/versions/`, parses the
`downgrade()` body and classifies it as one of:

  - reversible       : downgrade contains real DDL (op.* / op.execute(...))
  - irreversible     : downgrade body is empty / pass / `raise NotImplementedError`
  - manual           : downgrade is non-trivial but contains comments suggesting
                       human intervention (e.g. enum DROP VALUE, data backfill)

Writes a Markdown report to `docs/MIGRATION_REVERSIBILITY_REPORT.md`.

Used by ADR-0028 (canary release & rollback) §4.5 as a CI-time gate.

Usage::

    cd backend && python scripts/check_migration_reversibility.py

Exit code:
  0 : audit completed (report written) -- caller decides whether
      `irreversible` count is acceptable; this script does NOT fail CI by
      itself, so it can be wired into pre-commit / CI separately.
  2 : I/O error or no revisions found.
"""
from __future__ import annotations

import ast
import datetime as dt
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List


REPO_ROOT = Path(__file__).resolve().parents[2]   # backend/scripts -> repo root
VERSIONS_DIR = REPO_ROOT / "backend" / "alembic" / "versions"
REPORT_PATH = REPO_ROOT / "docs" / "MIGRATION_REVERSIBILITY_REPORT.md"


# Heuristic markers for "manual" classification (case-insensitive substring on body source).
MANUAL_MARKERS = (
    "drop value",          # PG enum DROP VALUE 不被原生支持
    "no rollback",         # 注释里明确说不要回滚
    "data loss",
    "backfill",
    "manual",
    "irreversible",
    "cannot downgrade",
    "not supported",
)


@dataclass
class RevisionAudit:
    file: str
    revision: str
    down_revision: str
    classification: str    # reversible | irreversible | manual
    reason: str
    downgrade_lines: int


def _module_ast(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _extract_str_assign(tree: ast.Module, name: str) -> str:
    """Return the string value of a top-level `name = "..."` assignment, or ''."""
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                return node.value.value
            if node.value is None:
                return ""
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == name:
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        return node.value.value
    return ""


def _find_function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def _classify_downgrade(func: ast.FunctionDef | None, source: str) -> tuple[str, str, int]:
    if func is None:
        return "irreversible", "no downgrade() function defined", 0

    body = [n for n in func.body if not (isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant))]
    line_count = len(body)

    # empty / pass / raise NotImplementedError -> irreversible
    if not body:
        return "irreversible", "downgrade() body is empty (only docstring)", 0
    if all(isinstance(n, ast.Pass) for n in body):
        return "irreversible", "downgrade() is just `pass`", line_count
    for n in body:
        if isinstance(n, ast.Raise):
            exc = n.exc
            exc_name = ""
            if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
                exc_name = exc.func.id
            elif isinstance(exc, ast.Name):
                exc_name = exc.id
            if exc_name in {"NotImplementedError", "RuntimeError"}:
                return "irreversible", f"downgrade() raises {exc_name}", line_count

    # detect any op.* call
    has_op_call = False
    for n in ast.walk(func):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "op":
                has_op_call = True
                break

    # heuristic markers in raw source
    func_src = ast.get_source_segment(source, func) or ""
    lower = func_src.lower()
    matched_markers = [m for m in MANUAL_MARKERS if m in lower]

    if matched_markers and not has_op_call:
        return "manual", f"downgrade() has manual markers (no op.*): {matched_markers}", line_count
    if matched_markers and has_op_call:
        return "manual", f"downgrade() has op.* AND manual markers (review needed): {matched_markers}", line_count
    if has_op_call:
        return "reversible", "downgrade() contains op.* DDL calls", line_count

    return "manual", "downgrade() has body but no op.* calls (review needed)", line_count


def audit() -> List[RevisionAudit]:
    if not VERSIONS_DIR.exists():
        print(f"ERROR: versions dir not found: {VERSIONS_DIR}", file=sys.stderr)
        sys.exit(2)

    results: List[RevisionAudit] = []
    files = sorted(p for p in VERSIONS_DIR.glob("*.py") if not p.name.startswith("_"))
    if not files:
        print(f"ERROR: no revision files in {VERSIONS_DIR}", file=sys.stderr)
        sys.exit(2)

    for f in files:
        source = f.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(f))
        revision = _extract_str_assign(tree, "revision")
        down_rev = _extract_str_assign(tree, "down_revision")
        downgrade_fn = _find_function(tree, "downgrade")
        classification, reason, lc = _classify_downgrade(downgrade_fn, source)
        results.append(
            RevisionAudit(
                file=f.name,
                revision=revision or "?",
                down_revision=down_rev or "?",
                classification=classification,
                reason=reason,
                downgrade_lines=lc,
            )
        )
    return results


def render_report(results: List[RevisionAudit]) -> str:
    counts = {"reversible": 0, "irreversible": 0, "manual": 0}
    for r in results:
        counts[r.classification] += 1
    total = len(results)

    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: List[str] = []
    lines.append("# Alembic Migration Reversibility Report")
    lines.append("")
    lines.append(f"- Generated: {now}")
    lines.append(f"- Source: `backend/alembic/versions/`")
    lines.append(f"- Tool: `backend/scripts/check_migration_reversibility.py`")
    lines.append(f"- 关联 ADR: [`ADR-0028`](decisions/ADR-0028-canary-release-and-rollback.md) §4.5")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total revisions: **{total}**")
    lines.append(f"- ✅ Reversible:    **{counts['reversible']}**")
    lines.append(f"- ⚠️  Manual:        **{counts['manual']}** (人工 review)")
    lines.append(f"- ❌ Irreversible:  **{counts['irreversible']}** (downgrade 缺失/raise/pass)")
    lines.append("")
    lines.append("## 评级标准")
    lines.append("")
    lines.append("- **reversible**: `downgrade()` 内含 `op.*` DDL 调用, 且无人工标记。")
    lines.append("- **manual**: `downgrade()` 含 `op.*` 但带有 `drop value` / `backfill` / `manual` 等标记;")
    lines.append("  或 body 非空但完全没有 `op.*` 调用。需要 DBA + 架构师人工 review 后确认是否可回滚。")
    lines.append("- **irreversible**: `downgrade()` 缺失、为 `pass`、或 `raise NotImplementedError`。")
    lines.append("  在 ADR-0028 灰度发布场景下, 该 revision **不允许**通过 alembic downgrade 回滚, 必须走")
    lines.append("  前向修复 + 数据补偿 (见 `docs/RUNBOOK_ROLLBACK.md` 场景 C)。")
    lines.append("")
    lines.append("## Per-revision detail")
    lines.append("")
    lines.append("| File | Revision | Down | Class | Lines | Reason |")
    lines.append("|---|---|---|---|---:|---|")
    for r in results:
        cls_icon = {"reversible": "✅", "manual": "⚠️", "irreversible": "❌"}[r.classification]
        lines.append(
            f"| `{r.file}` | `{r.revision}` | `{r.down_revision}` | "
            f"{cls_icon} {r.classification} | {r.downgrade_lines} | {r.reason} |"
        )
    lines.append("")
    if counts["irreversible"] > 0 or counts["manual"] > 0:
        lines.append("## Action items")
        lines.append("")
        if counts["irreversible"] > 0:
            lines.append(f"- ❌ {counts['irreversible']} 个 irreversible revision: 在 ADR-0028 §4.5 ")
            lines.append("  Expand-Contract 框架下, 任何 irreversible revision 都应被视为 *破坏性变更*, ")
            lines.append("  必须放在独立的 contract 阶段单独发布, **绝不能与 expand 合并**。")
        if counts["manual"] > 0:
            lines.append(f"- ⚠️  {counts['manual']} 个 manual revision: 在 `docs/RUNBOOK_ROLLBACK.md` 场景 C ")
            lines.append("  执行前必须由 DBA + 架构师双签确认。")
        lines.append("")
    lines.append("## CI integration (TODO, W18)")
    lines.append("")
    lines.append("```yaml")
    lines.append("- name: Migration reversibility audit")
    lines.append("  run: python backend/scripts/check_migration_reversibility.py")
    lines.append("  # 后续可加: 若 irreversible count 较 baseline 增加 -> fail")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    results = audit()
    report = render_report(results)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Wrote {REPORT_PATH}")
    print(
        "Counts: "
        f"reversible={sum(1 for r in results if r.classification == 'reversible')}, "
        f"manual={sum(1 for r in results if r.classification == 'manual')}, "
        f"irreversible={sum(1 for r in results if r.classification == 'irreversible')}, "
        f"total={len(results)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
