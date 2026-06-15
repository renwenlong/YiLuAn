"""AC#6 verify: existing deploy env files' salts pass new validator.

Run from repo root:  backend/.venv/bin/python3 backend/scripts/verify_env_salts.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Resolve repo root + backend dir relative to this script
_SCRIPT_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPT_DIR.parent  # backend/
_REPO_ROOT = _BACKEND_DIR.parent  # repo root

sys.path.insert(0, str(_BACKEND_DIR))

from app.config import Settings  # noqa: E402  # path bootstrap required first


def read_env(path: str) -> dict[str, str]:
    """Minimal .env parser. Reads KEY=VALUE; ignores comments / blanks."""
    vars_: dict[str, str] = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        vars_[k.strip()] = v.strip().strip('"').strip("'")
    return vars_


def main() -> int:
    files = [
        _REPO_ROOT / "deploy" / "env.dev.example",
        _REPO_ROOT / "deploy" / "env.staging",
        _REPO_ROOT / "deploy" / "env.canary",
        _REPO_ROOT / "deploy" / "env.production.example",
    ]
    all_ok = True
    for f in files:
        env = read_env(f)
        salts = {
            "contract_pseudonym_salt": env.get("CONTRACT_PSEUDONYM_SALT", ""),
            "pii_hash_salt": env.get("PII_HASH_SALT", ""),
            "pii_envelope_key": env.get("PII_ENVELOPE_KEY", ""),
        }
        print(f"\n=== {f} ===")
        print(f"  contract_pseudonym_salt: len={len(salts['contract_pseudonym_salt'])}")
        print(f"  pii_hash_salt: len={len(salts['pii_hash_salt'])}")
        print(f"  pii_envelope_key: len={len(salts['pii_envelope_key'])}")
        try:
            Settings(environment="development", **salts)
            print("  PASS: validator OK")
        except Exception as exc:
            all_ok = False
            print(f"  FAIL: {exc}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
