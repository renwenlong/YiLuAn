#!/usr/bin/env python3
"""
S2-TEST-002 / PRD-001 §6.C AC#22 — OpenAPI 跨端字段契约 diff 守门人.

只守 S2-INT-002 权威表 9 字段（Top1 关键路径），不守全 OpenAPI（避免误杀正常迭代）。
- 字段名 / 类型 / 必填性任何变更 → exit 1 → CI fail
- digest_url 为幽灵字段（backend 零命中）已剔除；权威表以 backend schema 为准
- 必须先改 ADR + 改 baseline + 双签放行，禁止单独改 baseline 蒙混
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

GUARDED_FIELDS = {
    # S2-INT-002 权威表（9 字段，魈拍板 + 胡桃定 session_expires_at）
    "share_token",            # ShareTokenResponse
    "share_url",              # ShareTokenResponse
    "share_scope",            # ShareTokenResponse
    "share_expires_at",       # ShareTokenResponse
    "share_revoked_at",       # ShareTokenResponse
    "share_active_count",     # Create/ListSharesResponse
    "share_session",          # ExchangeShareSessionResponse
    "share_session_expires_at",  # Exchange（与 share_session 配对）
    "patient_name_masked",    # ShareOrderResponse（脱敏视图）
    # digest_url 已剔除：backend 代码零命中（幽灵字段）
}

REPO_ROOT = Path(__file__).resolve().parents[2]
BASELINE = REPO_ROOT / "docs" / "api" / "openapi-baseline.json"


def extract_field_signatures(spec: dict) -> dict[str, tuple[str, bool]]:
    """
    遍历 components.schemas，提取被守字段的 (type, required) 签名。
    key 为 ``schema_name::field``——按 schema 维度分别守，同一字段
    在请求体（可选）与响应体（必含）required 不同是正常设计，
    不该跨 schema 强制一致（修正之前跨 schema 全局比较的误杀 bug）。
    """
    sigs: dict[str, tuple[str, bool]] = {}
    schemas = spec.get("components", {}).get("schemas", {})
    for schema_name, schema in schemas.items():
        if not isinstance(schema, dict):
            continue
        props = schema.get("properties", {}) or {}
        required = set(schema.get("required", []) or [])
        for fname, fdef in props.items():
            if fname not in GUARDED_FIELDS:
                continue
            ftype = fdef.get("type") or fdef.get("$ref", "?ref")
            if isinstance(ftype, list):
                ftype = "|".join(sorted(ftype))
            is_required = fname in required
            sigs[f"{schema_name}::{fname}"] = (str(ftype), is_required)
    return sigs


def load_current_spec() -> dict:
    # 延迟导入 app 以避免脚本调用时的环境副作用
    sys.path.insert(0, str(REPO_ROOT / "backend"))
    from app.main import app  # type: ignore  # noqa: WPS433

    return app.openapi()


def main() -> int:
    update_mode = "--update" in sys.argv[1:]
    current = load_current_spec()
    cur_sigs = extract_field_signatures(current)

    if update_mode:
        # 重生 baseline：只存被守字段的 schema::field 签名快照（非整个 OpenAPI）。
        # 仅在 ADR 双签确认后跑；生成后必须随 ADR 修订 PR 一起提交。
        snapshot = {k: list(v) for k, v in sorted(cur_sigs.items())}
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps(
                {"_format": "guarded-field-signatures-v1", "signatures": snapshot},
                ensure_ascii=False,
                indent=2,
            )
            + "\n"
        )
        print(f"baseline updated: {len(snapshot)} guarded field signatures -> {BASELINE}")
        return 0

    if not BASELINE.exists():
        print(f"::error:: baseline missing: {BASELINE}", file=sys.stderr)
        return 2
    raw = json.loads(BASELINE.read_text())
    # 兼容两种格式：新版 signature 快照 / 旧版整 OpenAPI。
    if isinstance(raw, dict) and raw.get("_format") == "guarded-field-signatures-v1":
        base_sigs = {k: tuple(v) for k, v in raw.get("signatures", {}).items()}
    else:
        base_sigs = extract_field_signatures(raw)

    diffs: list[str] = []

    # 阶段 A：被守字段当前可能尚未在 OpenAPI 出现（S2-DEV-002 还没接入）
    # 此时只断"已在 baseline 中出现的字段不能漂移"；缺失视为 OK。
    for fname, base_sig in base_sigs.items():
        cur_sig = cur_sigs.get(fname)
        if cur_sig is None:
            diffs.append(f"REMOVED: {fname} (baseline={base_sig})")
            continue
        if cur_sig != base_sig:
            diffs.append(f"CHANGED: {fname} baseline={base_sig} current={cur_sig}")

    # S2-DEV-002 落地后字段新增：阶段 A 不阻塞；阶段 B（端点 done）后改为阻塞
    new_fields = [f for f in cur_sigs if f not in base_sigs]
    if new_fields:
        print(
            "::notice:: 新增被守字段（请同步更新 baseline + ADR 双签）：" + ",".join(new_fields)
        )

    if diffs:
        print("::error:: ADR-0036 §2.7 七字段契约漂移：", file=sys.stderr)
        for d in diffs:
            print("  - " + d, file=sys.stderr)
        print(
            "处理：必须先改 ADR-0036 + 重生成 baseline + 双签 PR，禁止单独改 baseline。",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {len(base_sigs)} guarded fields stable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
