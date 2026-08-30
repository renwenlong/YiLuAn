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
DEV_REQUIREMENTS_WORKFLOWS = {
    "alembic-smoke.yml",
    "api-docs-check.yml",
    "azurite-ci.yml",
    "ci-smoke.yml",
    "deploy.yml",
    "openapi-diff.yml",
    "test.yml",
}
PROD_REQUIREMENTS_WORKFLOWS = {
    "deploy.yml",
    "main_wxapp-api-ren.yml",
}
PURE_PROD_REQUIREMENTS_WORKFLOWS = {
    "main_wxapp-api-ren.yml",
}
DEV_REQUIREMENTS_PATHS = {
    "backend/requirements-dev.txt",
    "requirements-dev.txt",
}
PROD_REQUIREMENTS_PATH = "backend/requirements.txt"
APPROVED_REQUIREMENTS_PATHS = DEV_REQUIREMENTS_PATHS | {PROD_REQUIREMENTS_PATH}
REQUIREMENTS_INSTALL_PATTERN = re.compile(
    r"\bpip\s+install\b[^\n#]*?(?:^|\s)-r\s+[\"']?"
    r"(?P<path>[^\"'\s|;&]*requirements(?:-dev)?\.txt)"
)


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


def workflow_requirements_references() -> dict[str, set[str]]:
    """Return every requirements file installed by each workflow."""
    workflow_dir = ROOT / ".github/workflows"
    references = {}
    for path in (*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")):
        matches = {
            match.group("path")
            for match in REQUIREMENTS_INSTALL_PATTERN.finditer(path.read_text(encoding="utf-8"))
        }
        if matches:
            references[path.name] = matches
    return references


def test_all_workflow_requirements_references_use_approved_paths() -> None:
    references = workflow_requirements_references()
    rejected = {
        name: sorted(paths - APPROVED_REQUIREMENTS_PATHS)
        for name, paths in references.items()
        if paths - APPROVED_REQUIREMENTS_PATHS
    }
    assert not rejected, f"workflows install unapproved requirements paths: {rejected}"


def test_ci_workflows_using_dev_requirements_are_accounted_for() -> None:
    references = workflow_requirements_references()
    referenced = {name for name, paths in references.items() if paths & DEV_REQUIREMENTS_PATHS}
    assert referenced == DEV_REQUIREMENTS_WORKFLOWS


def test_production_deploy_workflows_using_prod_requirements_are_accounted_for() -> None:
    references = workflow_requirements_references()
    referenced = {name for name, paths in references.items() if PROD_REQUIREMENTS_PATH in paths}
    assert referenced == PROD_REQUIREMENTS_WORKFLOWS


def test_pure_production_deploy_workflows_do_not_install_dev_requirements() -> None:
    references = workflow_requirements_references()
    for name in PURE_PROD_REQUIREMENTS_WORKFLOWS:
        assert PROD_REQUIREMENTS_PATH in references.get(name, set()), (
            f"{name} must install backend/requirements.txt"
        )
        assert not references[name] & DEV_REQUIREMENTS_PATHS, (
            f"{name} must not install requirements-dev.txt"
        )


def test_azure_app_service_workflow_packages_dependencies_and_sets_entrypoint() -> None:
    workflow = (ROOT / ".github/workflows/main_wxapp-api-ren.yml").read_text(encoding="utf-8")

    assert "--target .python_packages/lib/site-packages" in workflow
    assert "-r backend/requirements.txt" in workflow
    assert "include-hidden-files: true" in workflow
    assert "!.git/" in workflow
    assert "startup-command:" in workflow
    assert "cd /home/site/wwwroot/backend" in workflow
    assert "PYTHONPATH=/home/site/wwwroot/.python_packages/lib/site-packages" in workflow
    assert "python -m uvicorn app.main:app --host 0.0.0.0 --port 8000" in workflow
