# DEV_SETUP — 本地开发环境搭建与日常规范

> 本文档聚焦**日常开发流程**（如何跑起来、如何测试、如何避免 model/迁移脱钩）。
> 技术栈总览见根目录 [README.md](../README.md)；架构决策见 [docs/DECISION_LOG.md](DECISION_LOG.md)。

---

## 1. 快速开始

部署编排统一在 `deploy/`。本地开发推荐：`deploy/dev/` 起 db+redis 轻量栈 + 后端 uvicorn 裸跑（热重载）。

### 方式一：本地 dev（推荐，热重载）

```bash
# 1. 起 db + redis 轻量栈（宿主端口 5433 / 6380，避开 agent-squad 的 5432/6379）
cd deploy
./up.sh dev                          # 自动 cp dev/env.dev.example -> dev/env.dev

# 2. 后端虚拟环境 + 依赖 + 迁移 + 裸跑
cd ../backend
python -m venv venv && source venv/bin/activate    # Windows: venv\Scripts\activate
pip install -r requirements.txt
# backend/.env 连 5433/6380：
#   DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5433/yiluan
#   REDIS_URL=redis://127.0.0.1:6380/0
alembic upgrade head

# 3. 灌测试数据（seed.sql 现位于 deploy/dev/）
psql -h 127.0.0.1 -p 5433 -U postgres -d yiluan < ../deploy/dev/seed.sql
# Windows PowerShell:
#   Get-Content ../deploy/dev/seed.sql -Raw | psql -h 127.0.0.1 -p 5433 -U postgres -d yiluan

# 4. 启动
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 5. 验证
curl http://localhost:8000/health        # 进程活着
curl http://localhost:8000/readiness     # 依赖就绪（D-021）
```

### 方式二：全栈 staging（贴近预发，一键起）

```bash
cd deploy
./up.sh                              # api + nginx + mock-pay/sms + pg + redis, 入口 127.0.0.1:18080
./down.sh                            # 停并清数据
```

服务监听（方式一）：
- API：`http://localhost:8000`（uvicorn 裸跑）
- Postgres：`127.0.0.1:5433`（user=postgres, password=postgres, db=yiluan）
- Redis：`127.0.0.1:6380`

---

## 2. 固定测试账号（开发环境）

**登录方式**：手机号 + OTP 验证码（**不是密码**）。`sms_provider=mock` + `ENVIRONMENT=development` 时，所有手机号统一使用 OTP 码 `000000`。

| 角色 | 手机号 | 昵称 | OTP |
|---|---|---|---|
| 患者 | 13800000001 | 测试患者A（北京） | `000000` |
| 患者 | 13800000002 | 测试患者B（上海） | `000000` |
| 患者 | 13800000003 | 测试患者C（广州） | `000000` |
| 陪诊师 | 13900000001 | 测试陪诊师A（北京三甲） | `000000` |
| 陪诊师 | 13900000002 | 测试陪诊师B（上海儿童医院） | `000000` |
| 陪诊师 | 13900000003 | 测试陪诊师C（广州中山） | `000000` |
| 管理员 | 13700000001 | 系统管理员 | `000000` |

### 登录流程示例

```bash
# 1. 发 OTP（mock 环境不真发短信，日志会打印）
curl -X POST http://localhost:8000/api/v1/auth/send-otp \
  -H "Content-Type: application/json" \
  -d '{"phone":"13800000001"}'

# 2. 验证 OTP，拿 access_token
curl -X POST http://localhost:8000/api/v1/auth/verify-otp \
  -H "Content-Type: application/json" \
  -d '{"phone":"13800000001","code":"000000"}'

# 3. 用 token 调其他 API
curl http://localhost:8000/api/v1/users/me \
  -H "Authorization: Bearer <access_token>"
```

⚠️ `send-otp` 有 IP 级限流（60s 内同 IP 约 5-7 次会返回 429），批量测试脚本需 `sleep`。

---

## 3. 测试

### 3.1 单元测试（SQLite，日常开发跑）

```bash
cd backend
python -m pytest -q
```

- 走 SQLite 内存库 + `Base.metadata.create_all()`，**不依赖 PG / alembic**
- 速度快（约 30s），适合本地快速反馈
- 标记 `@pytest.mark.smoke` 的测试默认会被 deselect（需要真 PG）

### 3.2 Smoke 测试（真 PG + alembic，防脱钩）

```bash
# 先起 db+redis 轻量栈（deploy/dev/，端口 5433/6380）
cd deploy && ./up.sh dev
cd ../backend && alembic upgrade head    # 后端裸跑环境连 5433/6380

# 跑 smoke
python -m pytest -m smoke -q
```

Smoke 覆盖：
- `alembic upgrade head` 到最新 revision 能跑通
- `orderstatus` enum 含 9 个值（含 `rejected_by_companion` / `expired`）
- `payments` 表含 `trade_no` / `prepay_id` / `refund_id` / `callback_raw` 4 列
- 关键 CRUD 在真 PG 上能 insert

详见 `backend/tests/smoke/test_pg_alembic_smoke.py`。

### 3.3 CI

GitHub Actions（`.github/workflows/ci-smoke.yml`）在 push / PR 上同时跑：
- `unit-tests` job（SQLite 路径，快速反馈）
- `smoke-pg` job（services 起 postgres:15 + redis:7，跑 alembic + smoke）

---

## 4. Pre-commit（强烈推荐安装）

**防止 model 改动与 alembic 迁移脱钩**（2026-04-17 事故，详见 [MIGRATION_AUDIT_2026-04-17.md](MIGRATION_AUDIT_2026-04-17.md)）。

### 安装

```bash
pip install pre-commit
pre-commit install
```

### 已配置的 hook

| hook | 触发 | 做什么 |
|---|---|---|
| `alembic-check` | 修改 `backend/app/models/*` 或 `backend/alembic/versions/*` 或 `backend/alembic/env.py` 时 | 用 throwaway SQLite 跑 `alembic upgrade head` + `alembic check`，检测 model 与最新迁移是否有未同步 diff |

如果 hook 报 **"Target database is not up to date" / "New upgrade operations detected"**，说明你改了 model 但没写对应 alembic migration。**必须先生成迁移**再 commit。

### 生成新迁移（model 改动后必做）

```bash
cd backend

# 自动生成（注意：autogenerate 对 PG enum ADD VALUE 支持很弱，enum 改动请手写）
alembic revision --autogenerate -m "your message"

# 手写（enum 值改动 / 精细控制场景）
alembic revision -m "your message"
# 然后编辑 alembic/versions/<new_revision>.py 的 upgrade() / downgrade()
```

⚠️ **PG enum 专用规则**（坑多，务必注意）：
- `ALTER TYPE <enum> ADD VALUE 'xxx'` **不能在事务里执行**，需在迁移里包 autocommit 块：
  ```python
  with op.get_context().autocommit_block():
      op.execute("ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'rejected_by_companion'")
  ```
- PG 不支持 `DROP VALUE`，downgrade 里枚举值**只能保留**不能删
- autogenerate 对 enum ADD VALUE 几乎不生成正确 DDL，**务必手写**并跑 smoke 测试验证

---

## 5. Schema 变更 Checklist

每次你打算改 `backend/app/models/` 下任何内容时，按顺序确认：

- [ ] 修改 model 字段/枚举值
- [ ] `alembic revision -m "..."` 生成迁移文件
- [ ] 手写 `upgrade()`（尤其是 enum 改动）和 `downgrade()`
- [ ] 本地 PG 容器跑 `alembic upgrade head`，**无错**
- [ ] 跑 `alembic check`，返回 "No new upgrade operations detected."
- [ ] 跑 `pytest -m smoke`，全绿
- [ ] 跑 `pytest -q`（常规测试），全绿
- [ ] 如有 seed 数据依赖新字段/枚举，同步更新 `deploy/dev/seed.sql`
- [ ] commit：model 变更 + 迁移文件**一起** commit，message 说明改了什么

跳过任一步 → 参考 2026-04-17 事故（pytest 全绿 / PG 部署炸）。

---

## 6. 调度任务（APScheduler）

- 默认启动；开关环境变量 `SCHEDULER_ENABLED=true`
- 详见 [docs/scheduler.md](scheduler.md)：任务清单、分布式锁（D-018）、多副本部署、故障排查

---

## 7. 常用命令速查

```bash
# 重置 DB（清卷 → 重建 → 迁移 → 灌 seed）—— dev 轻量栈
cd deploy
./down.sh dev                # 清卷
docker compose -p yiluan-dev --env-file dev/env.dev -f dev/docker-compose.yml up -d
cd ../backend && alembic upgrade head
psql -h 127.0.0.1 -p 5433 -U postgres -d yiluan < ../deploy/dev/seed.sql
# Windows: Get-Content ../deploy/dev/seed.sql -Raw | psql -h 127.0.0.1 -p 5433 -U postgres -d yiluan

# alembic（后端裸跑环境直接跑，无需进容器）
alembic current
alembic heads
alembic history

# 直连 PG
psql -h 127.0.0.1 -p 5433 -U postgres -d yiluan

# 看 enum 实际值
psql -h 127.0.0.1 -p 5433 -U postgres -d yiluan -c "SELECT enum_range(NULL::orderstatus);"

# 看某表 schema
psql -h 127.0.0.1 -p 5433 -U postgres -d yiluan -c "\d payments"

# 看后端日志（uvicorn 裸跑，直接看终端输出；全栈 staging 看：docker compose -p yiluan-staging logs -f backend）
```

---

## 8. 相关文档

- [README.md](../README.md) — 项目总览与技术栈
- [docs/DECISION_LOG.md](DECISION_LOG.md) — 架构决策历史
- [docs/TECH_DEBT.md](TECH_DEBT.md) — 技术债登记
- [docs/MIGRATION_AUDIT_2026-04-17.md](MIGRATION_AUDIT_2026-04-17.md) — 迁移脱钩事故与修复
- [docs/scheduler.md](scheduler.md) — APScheduler 部署与运维
- [docs/MESSAGE_LINK_AUDIT_2026-04-17.md](MESSAGE_LINK_AUDIT_2026-04-17.md) — 消息链路全链审计

---

## 9. 提审准备

小程序提审材料、测试账号说明、域名白名单、隐私协议接入、提审备注模板、文案禁词、截图要求等全部收口在：

- [docs/wechat-submission-checklist.md](wechat-submission-checklist.md)

审核员可直接对照该文件的 §6（测试账号）和 §7（提审备注模板）使用本文档第 2 节的固定测试账号 + 万能 OTP `000000` 完整体验主流程。

---

_最后更新：2026-04-18_
