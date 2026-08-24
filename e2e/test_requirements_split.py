#!/usr/bin/env python3
"""Regression checks for production/development dependency separation.

Run from the repository root:
    python3 e2e/test_requirements_split.py
"""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"

DEV_ONLY = {
    "pytest",
    "pytest-asyncio",
    "hypothesis",
    "schemathesis",
    "aiosqlite",
    "black",
    "ruff",
}
WORKFLOWS = {
    "alembic-smoke.yml",
    "api-docs-check.yml",
    "azurite-ci.yml",
    "ci-smoke.yml",
    "deploy.yml",
    "openapi-diff.yml",
    "test.yml",
}


def package_names(path: Path):
    names = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = re.match(r"([A-Za-z0-9_.-]+)", line)
        if match:
            names.add(match.group(1).lower())
    return names


def require(condition: bool, message: str):
    if not condition:
        raise AssertionError(message)


def main():
    prod_path = BACKEND / "requirements.txt"
    dev_path = BACKEND / "requirements-dev.txt"
    prod = package_names(prod_path)
    dev = package_names(dev_path)

    require(not (prod & DEV_ONLY), f"dev-only dependencies leaked into prod: {sorted(prod & DEV_ONLY)}")
    require(DEV_ONLY <= dev, f"requirements-dev.txt missing: {sorted(DEV_ONLY - dev)}")
    require("-r requirements.txt" in dev_path.read_text(encoding="utf-8"), "dev requirements must include prod requirements")
    require("python-jose" in prod, "Apple JWKS runtime dependency python-jose must remain in prod")

    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    require("COPY backend/requirements.txt ." in dockerfile, "Dockerfile must copy prod requirements")
    require("pip install --no-cache-dir -r requirements.txt" in dockerfile, "Dockerfile must install prod requirements")
    require("requirements-dev.txt" not in dockerfile, "production Dockerfile must not install dev requirements")

    workflow_dir = ROOT / ".github" / "workflows"
    referenced = set()
    for path in workflow_dir.glob("*.yml"):
        text = path.read_text(encoding="utf-8")
        if "requirements.txt" in text or "requirements-dev.txt" in text:
            referenced.add(path.name)
    require(referenced == WORKFLOWS, f"requirements workflow set changed: expected {sorted(WORKFLOWS)}, got {sorted(referenced)}")
    for name in WORKFLOWS:
        text = (workflow_dir / name).read_text(encoding="utf-8")
        require("requirements-dev.txt" in text, f"{name} does not reference requirements-dev.txt")

    print("PASS: production/dev dependency separation and Apple jose exemption")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
