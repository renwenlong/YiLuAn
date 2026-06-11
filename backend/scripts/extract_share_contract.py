"""[S2-DEV-004] Extract the ADR-0036 §2.7 cross-platform field contract.

为什么单独抽契约 baseline，而不是直接 diff 全量 openapi.json？
- 全量 schema 每加一个无关端点就 diff，噪声大、容易被「改了别处所以顺手
  覆盖 baseline」掩盖真实的 §2.7 漂移。
- §2.7 的 7 个字段是**跨端硬契约**（后端 / 微信 / iOS 三端反序列化共用），
  改字段名 / 类型 / 必填性会静默打挂某一端。这里抽出 (schema, field,
  type, required, enum) 指纹做精准锚点。

输出：``docs/api/share-contract-baseline.json``，一个稳定排序的 JSON，
结构：
    {
      "fields": {
        "<SchemaName>.<field>": {
          "type": "...", "required": bool, "enum": [...]|null,
          "nullable": bool, "format": "..."|null
        }
      }
    }

CI (``openapi-diff.yml``) 重新抽取后与 baseline 逐键 diff，任意差异 fail。
合法升级路径：ADR 修订 + 双签 PR + 本脚本 ``--write`` 重写 baseline。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

# ADR-0036 §2.7 的 7 个跨端字段（含一个伴生 expires，明确纳入锚定）.
# S3-DEV-005-SHARE-CONTRACT (魈 2026-06-11 拍板): 扩 9 个
# ``CompanionPublicCertView`` sub-object 字段 + ``CompanionPublicView``
# ``cert_status`` ref (PRD-001 v1.4 §F8 + PM-005-1~11 + ADR-0046 §3.5 第 4 域
# ``companion_cert_*`` positive list). sub-object 内字段去 ``companion_cert_``
# 前缀 (sub-object 即 namespace, 详 ADR-0046 §3.5 r6 amend).
CONTRACT_FIELDS = {
    # S2-INT-002 原锁 share_* + patient_name_masked (9 个)
    "share_token",
    "share_url",
    "share_scope",
    "share_expires_at",
    "share_revoked_at",
    "share_session",
    "share_active_count",
    "share_session_expires_at",
    "patient_name_masked",
    # S3-DEV-005 CompanionPublicCertView sub-object 9 字段 (魈 Ghost #1 D 改良版)
    "cert_status",
    "cert_type",
    "cert_count",
    "cert_verified_at",
    "cert_pseudonym_name",
    "cert_work_id",
    "cert_badge_color",
    "cert_badge_icon",
    "cert_detail_text",
}

DEFAULT_BASELINE = (
    Path(__file__).resolve().parent.parent.parent
    / "docs"
    / "api"
    / "share-contract-baseline.json"
)


def _resolve_type(prop: dict) -> tuple[str, list | None, str | None]:
    """Return (type, enum, format) handling $ref/allOf/anyOf for enums."""
    enum = prop.get("enum")
    fmt = prop.get("format")
    typ = prop.get("type")

    # Pydantic enums show up as $ref or allOf[$ref].
    ref = prop.get("$ref")
    if ref is None:
        for key in ("allOf", "anyOf", "oneOf"):
            for sub in prop.get(key, []) or []:
                if "$ref" in sub:
                    ref = sub["$ref"]
                if sub.get("enum"):
                    enum = sub["enum"]
                if sub.get("type") and typ is None:
                    typ = sub["type"]
    if ref is not None and typ is None:
        # Enum ref → mark as "enum:<RefName>" so a renamed enum is caught.
        typ = "ref:" + ref.split("/")[-1]
    return typ or "unknown", enum, fmt


def extract_contract(schema: dict) -> dict:
    schemas = schema.get("components", {}).get("schemas", {})
    fields: dict[str, dict] = {}
    for schema_name, body in schemas.items():
        props = body.get("properties", {})
        required = set(body.get("required", []))
        for field_name, prop in props.items():
            if field_name not in CONTRACT_FIELDS:
                continue
            typ, enum, fmt = _resolve_type(prop)
            # anyOf with "null" → nullable.
            nullable = bool(prop.get("nullable"))
            for sub in prop.get("anyOf", []) or []:
                if sub.get("type") == "null":
                    nullable = True
            key = f"{schema_name}.{field_name}"
            fields[key] = {
                "type": typ,
                "required": field_name in required,
                "enum": sorted(enum) if enum else None,
                "nullable": nullable,
                "format": fmt,
            }
    return {"fields": dict(sorted(fields.items()))}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract/verify the ADR-0036 §2.7 share field contract."
    )
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Rewrite the baseline (use only after ADR revision + dual sign-off).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail (exit 1) if the live contract drifts from the baseline.",
    )
    args = parser.parse_args()

    from app.main import app  # noqa: E402

    live = extract_contract(app.openapi())

    if args.write:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(
            json.dumps(live, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        n = len(live["fields"])
        print(f"[share-contract] wrote baseline with {n} field anchors → {args.baseline}")
        return 0

    if not args.baseline.exists():
        print(
            f"[share-contract] baseline missing at {args.baseline}; "
            f"run with --write after ADR sign-off.",
            file=sys.stderr,
        )
        return 1

    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))

    if args.check:
        diffs = _diff(baseline["fields"], live["fields"])
        if diffs:
            print(
                "::error::ADR-0036 §2.7 cross-platform field contract DRIFT detected.\n"
                "These 7 fields are a hard cross-platform contract (backend / WeChat / iOS).\n"
                "Legal change path: revise ADR-0036 §2.7 + dual sign-off PR + "
                "`python scripts/extract_share_contract.py --write`.\n",
                file=sys.stderr,
            )
            for line in diffs:
                print("  - " + line, file=sys.stderr)
            return 1
        print(f"[share-contract] OK: {len(live['fields'])} field anchors match baseline.")
        return 0

    # No flag: just print the live contract.
    print(json.dumps(live, indent=2, ensure_ascii=False))
    return 0


def _diff(baseline: dict, live: dict) -> list[str]:
    diffs: list[str] = []
    b_keys, l_keys = set(baseline), set(live)
    for missing in sorted(b_keys - l_keys):
        diffs.append(f"REMOVED field anchor: {missing}")
    for added in sorted(l_keys - b_keys):
        diffs.append(f"ADDED field anchor: {added} (was not in baseline)")
    for key in sorted(b_keys & l_keys):
        base_sig, live_sig = baseline[key], live[key]
        for attr in ("type", "required", "enum", "nullable", "format"):
            if base_sig.get(attr) != live_sig.get(attr):
                diffs.append(
                    f"CHANGED {key}.{attr}: {base_sig.get(attr)!r} → {live_sig.get(attr)!r}"
                )
    return diffs


if __name__ == "__main__":
    raise SystemExit(main())
