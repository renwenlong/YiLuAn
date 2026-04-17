# DEV_SETUP.md — 本地开发环境

> 面向新加入 YiLuAn 后端开发的工程师；已部署 Python 3.12 + Docker。

## 1. 启动依赖（Postgres + Redis）

```bash
cd backend
docker compose up -d db redis
# 等待 healthy
docker compose ps
```

默认端口：PG 5432、Redis 6379。用户名/密码/库 = postgres/postgres/yiluan。

## 2. 安装 Python 依赖

```bash
cd backend
python -m pip install -r requirements.txt
python -m pip install pytest pytest-asyncio aiosqlite pre-commit
```

## 3. 跑 Alembic 迁移（真 PG）

```bash
cd backend
alembic upgrade head          # 应到 head=b7c8d9e0f1a2（截至 2026-04-17）
alembic current
```

alembic `env.py` 支持 env 覆盖 URL：

| env var | 用途 |
|---|---|
| `ALEMBIC_DATABASE_URL` | 最高优先级（CI / smoke / pre-commit 常用） |
| `DATABASE_URL` | 12-factor 标准；应用运行也读它 |
| `settings.database_url` | pydantic-settings 默认回退 |

## 4. 跑测试

### 4.1 默认（SQLite 路径，快）

```bash
cd backend
pytest -q
# → 394 passed, 5 deselected（smoke 自动跳过）
```

### 4.2 Smoke 测试（需要真 PG）

```bash
cd backend
# 需先 docker compose up -d db
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/yiluan
pytest -m smoke -q
# → 5 passed, 394 deselected
```

Windows PowerShell 下：

```powershell
$env:DATABASE_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/yiluan"
pytest -m smoke -q
```

Smoke 用途：防止 model / alembic 迁移脱钩（2026-04-17 事故详见 `docs/MIGRATION_AUDIT_2026-04-17.md`）。

## 5. pre-commit（推荐）

```bash
pip install pre-commit
pre-commit install          # 在仓库根执行
```

每次 commit 触发前会跑：

- **alembic-check**：对本地 PG（默认 docker-compose db）跑 `alembic check`，检测 SQLAlchemy model 与最新 migration 是否有 drift。PG 不可达时会打印警告但不阻塞 commit（CI 兜底强制）。

手动跑一次：

```bash
python scripts/alembic_check_hook.py
# 正常输出：No new upgrade operations detected.
```

## 6. 启动 API

```bash
cd backend
# 全栈 docker
docker compose up -d --build

# 或本地（需要 db/redis 容器跑着）
uvicorn app.main:app --reload --port 8000
```

健康检查：

| 路径 | 语义 | 期望 |
|---|---|---|
| `GET /health` | liveness（进程活着） | 200 `{"status":"healthy",...}` |
| `GET /api/v1/health` | liveness（API 路由活着） | 200 `{"status":"ok",...}` |
| `GET /readiness` | readiness（DB + Redis 就绪） | 200 / 503 |
| `GET /api/v1/readiness` | readiness（同上，API 前缀版） | 200 / 503 |

## 7. 新增 model 字段 / 枚举值的 checklist

**2026-04-17 事故教训**（TD-CI-01）：改了 model 不加 migration → 测试全绿但 Docker 部署失败。

必做步骤：

1. 改 `app/models/*.py`
2. **立刻**生成迁移：

   ```bash
   cd backend
   alembic revision --autogenerate -m "描述"
   ```

3. **autogenerate 对 Enum ADD VALUE 支持弱**，手写 `op.execute("ALTER TYPE ... ADD VALUE IF NOT EXISTS ...")` 并包进 autocommit block（Postgres 要求）
4. 跑 `alembic upgrade head` + `alembic check` 确认无 drift
5. 跑 `pytest -m smoke`（真 PG）确认 CRUD OK
6. commit 触发 pre-commit → 自动再跑一次 `alembic check` 兜底

## 8. CI 一览

`.github/workflows/`：

| workflow | 触发 | 用途 |
|---|---|---|
| `test.yml` | push/PR main,develop | 后端 unit（SQLite） + docker build + wechat |
| `ci-smoke.yml` | push/PR main | 后端 unit + PG-alembic smoke（真 PG + alembic check） |
| `deploy.yml` | 手动 / tag | ACA 部署 |

## 9. 排障

- **pre-commit 卡在 alembic check 但本地没 PG**：启动 `docker compose up -d db`，或临时 `--no-verify` 跳过（不推荐）。
- **smoke 跑不起来 / `alembic_version` 冲突**：smoke 默认复用现有 PG；如果 schema 脏，`docker compose down -v db && docker compose up -d db` 重来。
- **fakeredis / FakeRedis ping()**：`backend/tests/conftest.py::FakeRedis` 2026-04-17 补了 `ping()` 方法以支持 readiness 测试。
