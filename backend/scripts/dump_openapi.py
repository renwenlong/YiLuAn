"""Dump OpenAPI schema to docs/api/openapi.json.

Usage:
    cd backend && python scripts/dump_openapi.py
    # Or specify path:
    python scripts/dump_openapi.py --out ../docs/api/openapi.json --check
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running as `python scripts/dump_openapi.py` from backend dir.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Dump FastAPI OpenAPI schema.")
    default_out = Path(__file__).resolve().parent.parent.parent / "docs" / "api" / "openapi.json"
    parser.add_argument("--out", type=Path, default=default_out, help="Output path for openapi.json")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify every endpoint has a non-empty description (CI gate).",
    )
    args = parser.parse_args()

    # Lazy import — must happen after env is set up by caller.
    from app.main import app  # noqa: E402

    schema = app.openapi()

    # Validation gate
    missing: list[str] = []
    for path, methods in schema.get("paths", {}).items():
        for method, op in methods.items():
            if method.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            desc = (op.get("description") or "").strip()
            summ = (op.get("summary") or "").strip()
            if not desc or not summ:
                missing.append(f"{method.upper()} {path}")

    if missing:
        msg = f"[dump_openapi] {len(missing)} endpoint(s) missing summary/description:\n  - " + "\n  - ".join(missing)
        if args.check:
            print(msg, file=sys.stderr)
            return 1
        print("WARNING:", msg, file=sys.stderr)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    n_paths = len(schema.get("paths", {}))
    n_ops = sum(
        1
        for methods in schema.get("paths", {}).values()
        for m in methods
        if m.lower() in {"get", "post", "put", "patch", "delete"}
    )
    n_tags = len({t for methods in schema.get("paths", {}).values() for op in methods.values() if isinstance(op, dict) for t in op.get("tags", [])})
    print(f"[dump_openapi] OK -> {args.out} | paths={n_paths} operations={n_ops} tags={n_tags}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
