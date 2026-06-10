"""
Cross-replica Redis pub/sub propagation E2E (S2-OPS-STAGING-MULTI-REPLICA-COMPOSE AC#3-6).

ADR-0048 §4.1 / ADR-0053 §AC#5 套路:
- qualitative phase: SOP grep + endpoint shape verify
- quantitative phase: 真 docker compose --scale=2 起双副本, 调 reload, 测 ≤5s 跨副本 version 同步

测试范围 (S2-OPS-STAGING-MULTI-REPLICA-COMPOSE AC):
- AC#1: docker compose --scale backend=2 即用
- AC#2: nginx upstream backend:8000 docker DNS round-robin 多副本
- AC#3: 跨副本 ≤5s reload propagation (poll debug-version each 250ms 上限 5s)
- AC#4: PR description cite S3-TEST-002 AC#4 + ADR-0053 §AC#5 (在 commit msg)
- AC#5: reload 失败路径 unauth/invalid/expired JWT 与 valid super JWT 对照
- AC#6: 本 E2E file in backend/tests/e2e/test_ai_blocklist_pubsub_cross_replica.py
- AC#7: 7-day SLA cron 自动 query metric (T-7) — 不在 E2E 文件

为何 docker-based 而非 in-process httpx:
- in-process FakeRedis 不支持跨进程多 subscriber, 测不了真 pub/sub
- docker --scale=2 起两 backend 容器, 各自 Redis subscriber 拥 connection, 完整模拟 prod 行为

跑法:
    # 前置: env.staging 配置好, repo 上 main HEAD merged S3-BUG-002 fix
    cd ~/repo/YiLuAn/deploy
    docker compose --env-file env.staging -p yiluan-staging --profile staging up -d \
        --scale backend=2 --no-recreate

    # 后置: mount yml (S3-BUG-003 latent bug 修前 workaround)
    docker exec yiluan-staging-backend-1 mkdir -p /docs/medical-content/
    docker cp ~/repo/YiLuAn/docs/medical-content/prohibited-keywords.yml \
        yiluan-staging-backend-1:/docs/medical-content/prohibited-keywords.yml
    # (重复 backend-2)

    cd ~/repo/YiLuAn/backend
    python -m pytest tests/e2e/test_ai_blocklist_pubsub_cross_replica.py -v -s

依赖标记:
- @pytest.mark.docker — 不在普通 CI 跑 (CI 用 in-process), 仅 staging quantitative phase 手动跑
- skip 若 docker 不可用 (in case of CI runner 无 docker)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

# 关闭普通 e2e marker, 加 docker marker (不在 CI 默认跑)
# (在 conftest.py 普通 e2e 自动 marker 之外, 再加 docker 让 -m 'docker' 才跑)
pytestmark = [pytest.mark.docker]


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEPLOY_DIR = REPO_ROOT / "deploy"
NGINX_PORT = int(os.environ.get("YILUAN_STAGING_NGINX_PORT", "18080"))
PROPAGATION_SLA_MS = 5000  # AC#3 上限


@pytest.fixture(scope="session", autouse=True)
def _require_docker_and_replicas():
    """Session-scope guard: skip all tests in this module if docker not available
    or staging compose not up with backend=2 scale.
    """
    if shutil.which("docker") is None:
        pytest.skip("docker CLI not available", allow_module_level=True)
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=15)
        if r.returncode != 0:
            pytest.skip("docker daemon not responding", allow_module_level=True)
    except subprocess.TimeoutExpired:
        pytest.skip("docker info timeout (daemon not ready)", allow_module_level=True)


def _docker_exec(container: str, *cmd: str, timeout: int = 10) -> str:
    """Run `docker exec <container> <cmd>` and return stdout text."""
    r = subprocess.run(
        ["docker", "exec", container, *cmd],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if r.returncode != 0:
        raise RuntimeError(f"docker exec {container} {cmd} failed: {r.stderr}")
    return r.stdout


def _seed_super_admin_get_jwt() -> str:
    """Seed admin id=1 if missing + return super_admin JWT (8h)."""
    py = """
import logging; logging.disable(logging.CRITICAL)
import asyncio, bcrypt
from app.database import async_session
from app.models import AdminUser
from app.models.admin_user import AdminRole
from app.core.admin_jwt import create_admin_access_token
from sqlalchemy import select

async def main():
    async with async_session() as s:
        r = await s.execute(select(AdminUser).where(AdminUser.id == 1))
        admin = r.scalar_one_or_none()
        if admin is None:
            pwh = bcrypt.hashpw(b'testpass', bcrypt.gensalt()).decode()
            admin = AdminUser(
                id=1, username='superadmin_e2e',
                password_hash=pwh, role=AdminRole.super_, is_active=True,
            )
            s.add(admin); await s.commit(); await s.refresh(admin)
        print(create_admin_access_token(admin))

asyncio.run(main())
"""
    return _docker_exec("yiluan-staging-backend-1", "python", "-c", py).strip()


def _seed_ops_admin_get_jwt() -> str:
    """Seed admin role=ops if missing + return ops_admin JWT."""
    py = """
import logging; logging.disable(logging.CRITICAL)
import asyncio, bcrypt
from app.database import async_session
from app.models import AdminUser
from app.models.admin_user import AdminRole
from app.core.admin_jwt import create_admin_access_token
from sqlalchemy import select

async def main():
    async with async_session() as s:
        r = await s.execute(select(AdminUser).where(AdminUser.username == 'ops_e2e'))
        ops = r.scalar_one_or_none()
        if ops is None:
            pwh = bcrypt.hashpw(b'ops', bcrypt.gensalt()).decode()
            ops = AdminUser(
                username='ops_e2e', password_hash=pwh,
                role=AdminRole.ops, is_active=True,
            )
            s.add(ops); await s.commit(); await s.refresh(ops)
        print(create_admin_access_token(ops))

asyncio.run(main())
"""
    return _docker_exec("yiluan-staging-backend-1", "python", "-c", py).strip()


def _get_debug_version(container: str, jwt: str) -> dict[str, Any]:
    """Call /api/v1/admin/ai-blocklist/debug-version on a container's internal port 8000."""
    py = f"""
import urllib.request, json
req = urllib.request.Request(
    'http://localhost:8000/api/v1/admin/ai-blocklist/debug-version',
    headers={{'Authorization': 'Bearer {jwt}'}},
)
resp = urllib.request.urlopen(req, timeout=3)
print(json.dumps(json.loads(resp.read())))
"""
    return json.loads(_docker_exec(container, "python", "-c", py).strip())


def _trigger_reload_via_nginx(jwt: str) -> dict[str, Any]:
    """POST /api/v1/admin/ai-blocklist/reload via host nginx port."""
    r = subprocess.run(
        [
            "curl", "-s", "-X", "POST",
            "-H", f"Authorization: Bearer {jwt}",
            f"http://localhost:{NGINX_PORT}/api/v1/admin/ai-blocklist/reload",
        ],
        capture_output=True, text=True, timeout=10,
    )
    return json.loads(r.stdout)


def _verify_replicas_running() -> tuple[str, str]:
    """Returns (replica_1, replica_2) container names, raise if not running."""
    r = subprocess.run(
        ["docker", "ps", "--filter", "name=yiluan-staging-backend",
         "--format", "{{.Names}}"],
        capture_output=True, text=True, timeout=5,
    )
    names = [n for n in r.stdout.strip().split("\n") if n]
    if len(names) < 2:
        pytest.skip(f"Need 2+ backend replicas, got {len(names)}: {names}. "
                    "Run: docker compose ... --scale backend=2 first")
    return names[0], names[1]


def _verify_yml_mounted(container: str) -> None:
    """Verify prohibited-keywords.yml accessible (S3-BUG-003 workaround)."""
    try:
        _docker_exec(container, "ls", "/docs/medical-content/prohibited-keywords.yml")
    except RuntimeError:
        pytest.skip(
            f"prohibited-keywords.yml not mounted in {container}. "
            "S3-BUG-003 (Docker missing medical-content) blocks this. "
            "Workaround: docker cp ~/repo/YiLuAn/docs/medical-content/prohibited-keywords.yml "
            f"{container}:/docs/medical-content/"
        )


# ---------------------------------------------------------------------------
# AC#3: cross-replica propagation timing
# ---------------------------------------------------------------------------
def test_ac3_reload_propagates_to_both_replicas_within_5s():
    """AC#3 — trigger reload, verify both replicas converge to same version ≤5s."""
    r1, r2 = _verify_replicas_running()
    _verify_yml_mounted(r1)
    _verify_yml_mounted(r2)

    jwt = _seed_super_admin_get_jwt()
    assert jwt, "JWT seed failed"

    # trigger reload
    t0_ns = time.time_ns()
    resp = _trigger_reload_via_nginx(jwt)
    assert resp.get("accepted") is True, f"reload not accepted: {resp}"
    assert resp.get("channel") == "yiluan:ai-blocklist:reload"

    # poll both replicas every 250ms
    converged_at_ms = None
    for _ in range(20):  # 20 × 250ms = 5s
        time.sleep(0.25)
        v1 = _get_debug_version(r1, jwt)
        v2 = _get_debug_version(r2, jwt)
        if (v1.get("version") == "1.0.0" and v2.get("version") == "1.0.0"
                and v1.get("total_patterns", 0) > 0 and v2.get("total_patterns", 0) > 0):
            converged_at_ms = (time.time_ns() - t0_ns) // 1_000_000
            break

    assert converged_at_ms is not None, (
        f"Replicas did NOT converge in {PROPAGATION_SLA_MS}ms: "
        f"r1={v1}, r2={v2}"
    )
    assert converged_at_ms <= PROPAGATION_SLA_MS, (
        f"Convergence took {converged_at_ms}ms > SLA {PROPAGATION_SLA_MS}ms"
    )
    print(
        f"\n✅ AC#3 PASS: replicas converged in {converged_at_ms}ms "
        f"(SLA: {PROPAGATION_SLA_MS}ms)"
    )


# ---------------------------------------------------------------------------
# AC#5: failure paths
# ---------------------------------------------------------------------------
class TestAc5FailurePaths:
    """AC#5 — verify negative auth paths return 401, not 500/silent accept."""

    def test_unauthenticated_returns_401(self):
        r = subprocess.run(
            ["curl", "-s", "-w", "%{http_code}", "-o", "/dev/null",
             "-X", "POST", f"http://localhost:{NGINX_PORT}/api/v1/admin/ai-blocklist/reload"],
            capture_output=True, text=True, timeout=10,
        )
        assert r.stdout == "401", f"Expected 401, got {r.stdout}"

    def test_invalid_jwt_returns_401(self):
        r = subprocess.run(
            ["curl", "-s", "-w", "%{http_code}", "-o", "/dev/null",
             "-X", "POST",
             "-H", "Authorization: Bearer invalid.token.xyz",
             f"http://localhost:{NGINX_PORT}/api/v1/admin/ai-blocklist/reload"],
            capture_output=True, text=True, timeout=10,
        )
        assert r.stdout == "401", f"Expected 401, got {r.stdout}"

    def test_expired_jwt_returns_401(self):
        """JWT with exp in past should be rejected as invalid (not 500)."""
        py = (
            "import jwt; "
            "from datetime import datetime, timezone, timedelta; "
            "from app.config import settings; "
            "exp_time = datetime.now(timezone.utc) - timedelta(hours=1); "
            "print(jwt.encode({'sub':'1','role':'super','username':'admin',"
            "'type':'admin_access','exp':int(exp_time.timestamp())},"
            "settings.jwt_secret_key, algorithm=settings.jwt_algorithm))"
        )
        expired = _docker_exec("yiluan-staging-backend-1", "python", "-c", py).strip()

        r = subprocess.run(
            ["curl", "-s", "-w", "%{http_code}", "-o", "/dev/null",
             "-X", "POST",
             "-H", f"Authorization: Bearer {expired}",
             f"http://localhost:{NGINX_PORT}/api/v1/admin/ai-blocklist/reload"],
            capture_output=True, text=True, timeout=10,
        )
        assert r.stdout == "401", f"Expected 401, got {r.stdout}"

    def test_super_admin_returns_202(self):
        """Happy path control — verify a valid super_admin JWT does succeed."""
        jwt = _seed_super_admin_get_jwt()
        resp = _trigger_reload_via_nginx(jwt)
        assert resp.get("accepted") is True
        assert resp.get("triggered_by_admin_id") == "1"

    def test_ops_admin_can_reload_by_design(self):
        """ops admin (non-super) CAN trigger reload by design — it's a maintenance op.

        ai_blocklist.py has NO role check, only require_admin_jwt. Both super and ops
        admin can reload. This is intentional: hot reload is an ops task.

        (Patient/anonymous JWT 不在此覆盖 — admin auth chain 已先 reject 在 require_admin_jwt
        步骤, 测过 invalid_jwt_returns_401 已涵盖 wrong-type token 路径.)
        """
        ops_jwt = _seed_ops_admin_get_jwt()
        resp = _trigger_reload_via_nginx(ops_jwt)
        assert resp.get("accepted") is True, f"ops_admin should be allowed to reload: {resp}"


# ---------------------------------------------------------------------------
# AC#1/2: smoke control — verify the multi-replica skeleton itself works
# ---------------------------------------------------------------------------
class TestSkeletonSmoke:
    """AC#1/2 — verify docker compose --scale=2 setup + nginx round-robin work."""

    def test_two_backend_replicas_running_and_healthy(self):
        r1, r2 = _verify_replicas_running()
        # check inspect health status
        for name in (r1, r2):
            r = subprocess.run(
                ["docker", "inspect", name, "--format", "{{.State.Health.Status}}"],
                capture_output=True, text=True, timeout=5,
            )
            assert r.stdout.strip() == "healthy", f"{name} not healthy: {r.stdout}"

    def test_nginx_proxies_healthz_to_backend(self):
        r = subprocess.run(
            ["curl", "-s", f"http://localhost:{NGINX_PORT}/healthz"],
            capture_output=True, text=True, timeout=5,
        )
        # 后端 /healthz 直接返 "yiluan-staging" plain text
        assert "yiluan-staging" in r.stdout, f"Unexpected /healthz body: {r.stdout!r}"

    def test_each_replica_reports_distinct_instance_id(self):
        r1, r2 = _verify_replicas_running()
        jwt = _seed_super_admin_get_jwt()
        v1 = _get_debug_version(r1, jwt)
        v2 = _get_debug_version(r2, jwt)
        # instance 是容器 hostname (短 ID), 两个应不同
        assert v1.get("instance") != v2.get("instance"), (
            f"Replicas reported same instance id (subscriber wiring broken): "
            f"r1={v1}, r2={v2}"
        )
