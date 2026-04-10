# 2026-04-10 并行任务依赖分析

**参与角色：** Arch / Backend / Ops / PM  
**背景：** Phase 2 支付已完成，接下来有多项任务需并行推进。用户要求：并行推进的 feature 不能相互依赖。

---

## 讨论过程

**PM：**
> 当前待推进的 P0 任务有这些：
> 1. SMS 真实接入
> 2. 生产配置收口
> 3. 后台管理 MVP
> 4. 合规文档（隐私协议/用户协议）
> 5. 前端支付流程改造
> 6. 前端审核合规页面

**Arch：**
> 我来画依赖关系。先列清楚每个任务涉及哪些文件和模块。

### 任务-文件矩阵

| 任务 | 涉及文件/模块 | 依赖的前置 |
|------|-------------|-----------|
| **SMS 接入** | `services/auth.py`, `config.py`, 新增 `services/sms.py` | 无 |
| **生产配置收口** | `config.py`, `.env.production.example`, `docker-compose.yaml`, `Dockerfile` | 无（但需与 SMS/支付 的配置项协调） |
| **后台管理 MVP** | 新增 `api/v1/admin_*.py`, 新增 `services/admin.py` | 无（独立路由和服务） |
| **合规文档** | 新增 `docs/privacy-policy.md` 等纯文档 | 无 |
| **前端支付改造** | `wechat/pages/patient/*`, `wechat/services/api.js` | ✅ 依赖后端支付 API（已完成） |
| **前端审核页面** | `wechat/pages/profile/*`, 新增协议页 | ✅ 依赖合规文档内容 |

**Backend：**
> SMS 接入改的是 `services/auth.py` 和 `config.py`。生产配置也改 `config.py`。这两个有文件级冲突风险。

**Arch：**
> 对。但冲突点很小——SMS 接入是加 `sms_provider` 相关配置和一个新的 `services/sms.py`；生产配置收口是改 `debug`/`cors`/`jwt_secret` 等现有字段的默认值和环境管理方式。它们改的是 `config.py` 的**不同区域**。只要约定好：
> - SMS 只动 `# SMS` 区块
> - 生产配置只动其他区块（debug/cors/jwt/环境判断）
> 就不会冲突。

**Backend：**
> 后台管理 MVP 呢？它需要读订单、用户、陪诊师的数据，会不会和现有 Service 冲突？

**Arch：**
> 不会。后台管理走独立的路由和服务（`admin_*.py`），它**只调用**现有的 Repository 层做查询和状态修改，不改现有的 Service 接口。这是只读+受控写入，和业务流程不交叉。

**Ops：**
> 生产配置收口和部署方案有关系吗？

**Arch：**
> 有，但是单向依赖——部署方案依赖生产配置完成。所以生产配置先做，部署方案后做，不能并行。

**QA：**
> 前端支付改造和前端审核页面呢？

**Frontend：**
> 这两个改的是不同页面目录，没有文件冲突。支付改的是 `patient/create-order` 和 `patient/order-detail`；审核页面改的是 `profile/` 下新增页面。可以并行。

## 最终依赖图

```
                    ┌─────────────┐
                    │  合规文档    │ (纯文档，无代码依赖)
                    └──────┬──────┘
                           │ 内容依赖
                           ▼
┌────────────┐    ┌─────────────────┐    ┌──────────────┐
│ SMS 接入   │    │ 前端审核合规页面 │    │ 后台管理 MVP │
│            │    └─────────────────┘    │              │
│ config.py  │                           │ admin_*.py   │
│ #SMS区块   │    ┌─────────────────┐    │ (独立路由)   │
└────────────┘    │ 前端支付流程改造 │    └──────────────┘
                  │ (依赖后端支付✅) │
┌────────────┐    └─────────────────┘
│ 生产配置   │
│ config.py  │──────────────────────────▶ 部署方案
│ 非SMS区块  │                           (串行，后做)
└────────────┘
```

## 共识：可安全并行的任务组

### 🟢 并行组 A（立即开工，互不依赖）

| # | 任务 | 负责角色 | 涉及范围 | 约束 |
|---|------|---------|---------|------|
| 1 | SMS 真实接入 | Backend | `services/sms.py`(新), `services/auth.py`, `config.py#SMS区块` | 只动 SMS 相关代码 |
| 2 | 后台管理 MVP | Backend | `api/v1/admin_*.py`(新), `services/admin.py`(新) | 独立路由，只调现有 Repo |
| 3 | 合规文档 | PM | `docs/` 纯文档 | 无代码改动 |
| 4 | 前端支付流程改造 | Frontend | `wechat/pages/patient/*` | 后端支付 API 已就绪 |

### 🟡 并行组 B（组 A 部分完成后启动）

| # | 任务 | 依赖 | 原因 |
|---|------|------|------|
| 5 | 前端审核合规页面 | 合规文档(#3) | 需要协议内容才能做页面 |
| 6 | 生产配置收口 | 可与组A并行，但需在SMS完成后合并config | config.py 区域分治 |

### 🔴 串行（必须等前置完成）

| # | 任务 | 依赖 |
|---|------|------|
| 7 | 部署方案执行 | 生产配置收口(#6) |
| 8 | 小程序提审 | 前端支付(#4) + 合规页面(#5) + 部署(#7) |

## config.py 分区约定

为避免并行改 config.py 冲突，约定如下区域归属：

```python
# --- SMS 接入专属 (Backend-SMS) ---
sms_provider: str = "mock"
sms_access_key: str = ""
sms_access_secret: str = ""
sms_sign_name: str = ""
sms_template_code: str = ""

# --- Payment 专属 (已完成，不动) ---
payment_provider: str = "mock"
wechat_pay_*: ...

# --- 生产配置收口专属 (Ops) ---
debug: bool = ...
environment: str = ...
jwt_secret_key: str = ...
cors_origins: list[str] = ...
```

不同任务只改自己区域，提交前 `git diff config.py` 确认无越界。
