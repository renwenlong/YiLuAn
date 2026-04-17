#!/usr/bin/env python
"""pre-commit hook: 对真 Postgres 执行 `alembic check` 防止 model/migration drift。

URL 解析优先级:
  1. ALEMBIC_DATABASE_URL env
  2. DATABASE_URL env
  3. 默认 postgresql+asyncpg://postgres:postgres@localhost:5432/yiluan
     （docker-compose up -d db 的默认配置）

若 PG 不可达 → 打印警告并跳过（exit 0），不阻塞本地 commit；CI 会在 ci-smoke.yml
的 smoke-pg job 里强制跑真 alembic check（无法绕过）。
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import urllib.parse
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"

DEFAULT_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/yiluan"


def _host_port(url: str) -> tuple[str, int] | None:
    try:
        parsed = urllib.parse.urlparse(url.replace("+asyncpg", "").replace("+psycopg", ""))
        if parsed.hostname and parsed.port:
            return parsed.hostname, parsed.port
    except Exception:
        return None
    return None


def _reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> int:
    url = os.environ.get("ALEMBIC_DATABASE_URL") or os.environ.get("DATABASE_URL") or DEFAULT_URL

    hp = _host_port(url)
    if hp and not _reachable(*hp):
        sys.stderr.write(
            f"[alembic-check hook] Postgres {hp[0]}:{hp[1]} unreachable — skipping.\n"
            "  Start it with: docker compose -f backend/docker-compose.yaml up -d db\n"
            "  Or set ALEMBIC_DATABASE_URL to a reachable DB.\n"
            "  CI (ci-smoke.yml) will still enforce alembic check against real PG.\n"
        )
        return 0

    env = os.environ.copy()
    env["ALEMBIC_DATABASE_URL"] = url

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        sys.stderr.write(
            "\n[alembic-check hook] Drift detected between models and migrations.\n"
            "  Generate a migration: cd backend && alembic revision --autogenerate -m '<msg>'\n"
        )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
