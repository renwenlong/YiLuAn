# AI Blocklist YML Deployment & On-Call Checklist

> 任务: S3-BUG-003-DOCKER-MISSING-MEDICAL-CONTENT-YML
> 关联: ADR-0048 §4.1 (L1 input filter) + §4.3 (L2 output filter)

## 背景

`docs/medical-content/prohibited-keywords.yml` 是 ADR-0048 双层 AI 关键词
过滤的**Source of Truth (SoT)**, 内含 6 类 (`diagnosis` / `dosage` /
`prescription` / `treatment_plan` / `lab_results` / `billing`) 72 条
pattern。任何更新都走 git PR + 医疗顾问 review approve, admin-v2 关键词页
read-only 不允许后台直改 (ADR-0048 §4 决定).

YML 必须随 backend image 一起 ship 到容器内的 `/docs/medical-content/`
路径 (`backend/app/services/ai_prep_filter.py::_DEFAULT_YML_PATH` 写死).

## S3-BUG-003 修复机制

**Build 端**:
- `backend/Dockerfile` 的 `COPY docs/medical-content/ /docs/medical-content/` 把 yml
  打进 image (基础 image WORKDIR=/app; `parents[3]` 落在 `/`, 故 yml
  必须放 `/docs/medical-content/`)
- `deploy/docker-compose.yml` 把 backend 服务的 `build.context` 调到 repo
  根 (`context: ..` + `dockerfile: backend/Dockerfile`), 否则 Dockerfile
  COPY 跨不出 backend/ 子目录
- 与 SoT (`docs/medical-content/prohibited-keywords.yml`) 1:1 映射, 不引入
  yml 副本, 避免双 source of truth

**Runtime 端**:
- `ai_prep_filter._cache.load()` 在 module import 时自动跑 (`ai_prep_filter.py` 末尾)
- 加载失败保持 fail-open (`snapshot=()`, `version=""`), **不 raise**, 以让
  dev 本地 / unit test fixture 不依赖 yml 也能跑

**Fail-loud Probe**:
- `app/main.py` lifespan startup 调 `assert_blocklist_loaded_or_raise(strict=...)`
- `strict` 取自 `settings.ai_blocklist_strict_load` (env `AI_BLOCKLIST_STRICT_LOAD`,
  默认 `false`)
- `env.staging` / `env.canary` / `env.production` 都设 `AI_BLOCKLIST_STRICT_LOAD=true`
- 严格模式下: snapshot 空 / version 空 / yml 文件缺失任一条件
  → raise `BlocklistStartupError` → FastAPI 拒启
- test/local 不设 (默认 false) 跳 probe, 保留原 fail-open 体验

**为什么不看 `ENVIRONMENT`**：
`env.staging` / `env.canary` 都是 `ENVIRONMENT=staging`，
用 `settings.environment` 判别 prod-like 会误判. 独立 `AI_BLOCKLIST_STRICT_LOAD`
使运维意志与 debug 模式解耦, 仁智制宜.

## CI 防回归

`backend/tests/integration/test_blocklist_yml_present.py`:
- `_DEFAULT_YML_PATH.exists() is True` (不 mock)
- `_FALLBACK_TEMPLATE_PATH.exists() is True` (同目录 prep-fallback-template.yml 同 bug 模式)
- module singleton load 后 `snapshot` + `version` 非空
- categories ≥ 6 + total patterns ≥ 50 (基线 sanity)

CI 不带 marker exclude, push 时 pre-push gate 必跑。

`backend/tests/test_ai_prep_filter.py::TestStartupProbe`:
- probe pass in production-like env with loaded blocklist
- probe skip in dev / test env (保留 fail-open)
- probe raise in staging/canary/production with empty snapshot
- probe raise when yml file missing

## On-Call 检查清单

### 部署前 (Pre-Deploy)

- [ ] 确认 `docs/medical-content/prohibited-keywords.yml` 存在
- [ ] 确认 `docs/medical-content/prep-fallback-template.yml` 存在
- [ ] `git log -1 docs/medical-content/` 看最近一次更新有医疗顾问 review 痕迹
- [ ] CI test green (含 `test_blocklist_yml_present.py` 7 case + `TestStartupProbe` 4 case)
- [ ] `backend/Dockerfile` 含 `COPY docs/medical-content/ /docs/medical-content/`
- [ ] `deploy/docker-compose.yml` backend `context: ..` + `dockerfile: backend/Dockerfile`

### 部署中 (Build)

```bash
cd deploy
# build with context at repo root
./up.sh staging  # 或 canary / production
```

build 失败常见原因:
- `failed to compute cache key: docs/medical-content`: docs 目录被 .dockerignore 排除 (默认无 .dockerignore, 但若新增需检查)
- `COPY failed: file not found`: context 还是 `../backend`, docker-compose.yml 没改

### 部署后 (Post-Deploy Verify)

```bash
# 1. yml 进了 image
docker exec <backend-container> ls -la /docs/medical-content/
# 预期: prohibited-keywords.yml + prep-fallback-template.yml

# 2. startup 日志含 "S3-BUG-003 startup probe OK ..."
docker logs <backend-container> --since=5m | grep -E "S3-BUG-003|blocklist loaded"
# 预期:
#   ai_prep_filter: blocklist loaded version=1.0.0 categories=6 patterns=72 path=/...
#   S3-BUG-003 startup probe OK in env=staging: yml=/docs/... categories=6 version=1.0.0

# 3. admin debug-version endpoint 返实际数据
curl -H "Authorization: Bearer <super_admin_jwt>" \
  http://127.0.0.1:18080/api/v1/admin/ai-blocklist/debug-version
# 预期: {"version":"1.0.0","total_categories":6,"total_patterns":72,...}
```

任一步异常 → 立即回滚 (上一个 known-good image), 看 startup log 找根因.

### 异常 Triage

| 症状 | 可能原因 | 修复 |
|------|---------|------|
| backend 启动 raise `BlocklistStartupError: yml file missing` | Dockerfile 没 COPY / build context 错 | rebuild image + 看 §部署前 checklist |
| backend 启动 raise `BlocklistStartupError: snapshot is empty` | yml 存在但 categories 字段非 dict / parse 失败 | 看 backend log 上一行 `ai_prep_filter: ...` warning, fix yml |
| backend 启动 raise `BlocklistStartupError: version is empty string` | yml 缺 version 顶层字段 | 加 `version: 1.x.x` 进 yml |
| backend 启动 OK 但 `blocklist empty (fail-open)` warning | env 在白名单外 (dev/local) | 正常 dev 行为, prod env 设 `ENVIRONMENT=staging/canary/production` 后会 fail-loud |
| 部署成功但 `/admin/ai-blocklist/debug-version` 返 version='' | 已 docker cp yml 进容器但 module cache 没 reload | 触发 redis pub/sub 事件 `ai_blocklist_reload` 或重启 backend |

## Rotation / Hot-Reload

YML 内容改动后:
1. PR 走 git workflow + 医疗顾问 review
2. PR merge → CI rebuild image
3. 滚动部署 (rolling deploy) → 新 pod startup 跑 probe, yml 自动加载
4. 在线 hot-reload: `POST /api/v1/admin/ai-blocklist/reload` (super_admin only)
   → publish `ai_blocklist_reload` 事件 → 所有副本 subscriber 收事件 →
   调 `ai_prep_filter.load_blocklist()` 重 init

热 reload 失败 / 部分副本未 reload → admin-v2 关键词页会出现版本号不一致,
on-call 用 `debug-version` endpoint per-replica 排查.

## 相关 reference

- ADR-0048 §4 双层 AI 关键词过滤设计
- `backend/app/services/ai_prep_filter.py` 实现 + `_DEFAULT_YML_PATH` / `assert_blocklist_loaded_or_raise`
- `backend/app/services/prep_generate_service.py::_FALLBACK_TEMPLATE_PATH` 同 bug 修复
- `backend/tests/integration/test_blocklist_yml_present.py` regression
- `backend/tests/test_ai_prep_filter.py::TestStartupProbe` probe 单元
- S3-BUG-002 (admin-v2 调试 endpoint 403) — same-day 双 latent bug pattern
