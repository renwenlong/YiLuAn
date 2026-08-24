"""CI regression guards for production/development dependency separation."""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

ROOT = Path(__file__).resolve().parents[3]
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


def package_names(path: Path) -> set[str]:
    """Return normalized package names declared directly in a requirements file."""
    names = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = re.match(r"([A-Za-z0-9_.-]+)", line)
        if match:
            names.add(re.sub(r"[-_.]+", "-", match.group(1)).lower())
    return names


def test_prod_declarations_exclude_dev_only_dependencies() -> None:
    prod = package_names(BACKEND / "requirements.txt")
    assert not prod & DEV_ONLY, f"dev-only dependencies leaked into prod: {sorted(prod & DEV_ONLY)}"


def test_dev_requirements_extend_prod_and_include_tooling() -> None:
    dev_path = BACKEND / "requirements-dev.txt"
    dev = package_names(dev_path)
    assert DEV_ONLY <= dev, f"requirements-dev.txt missing: {sorted(DEV_ONLY - dev)}"
    assert "-r requirements.txt" in dev_path.read_text(encoding="utf-8")


def test_apple_jose_runtime_exemption_is_preserved() -> None:
    prod = package_names(BACKEND / "requirements.txt")
    assert "python-jose" in prod
    auth_apple = (BACKEND / "app/api/v1/auth_apple.py").read_text(encoding="utf-8")
    assert "from jose import jwt" in auth_apple


def test_production_dockerfile_installs_only_prod_requirements() -> None:
    dockerfile = (BACKEND / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY backend/requirements.txt ." in dockerfile
    assert "pip install --no-cache-dir -r requirements.txt" in dockerfile
    assert "requirements-dev.txt" not in dockerfile


def test_all_requirements_workflows_use_the_split_files() -> None:
    workflow_dir = ROOT / ".github/workflows"
    referenced = {
        path.name
        for path in workflow_dir.glob("*.yml")
        if "requirements.txt" in path.read_text(encoding="utf-8")
        or "requirements-dev.txt" in path.read_text(encoding="utf-8")
    }
    assert referenced == WORKFLOWS
    for name in WORKFLOWS:
        text = (workflow_dir / name).read_text(encoding="utf-8")
        assert "requirements-dev.txt" in text, f"{name} does not reference requirements-dev.txt"
