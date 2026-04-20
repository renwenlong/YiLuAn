# Sprint Plan 2026-W17（4/21-4/26）

## 本周目标

本周是 R8 全角色 Review 后的首个执行周。目标三件事：**关闭 7 个 P0**（P0-01~P0-07）、**推进本周冲刺 5 项**（OrderService 拆分、a11y 基础、监控告警、资质认证、通知深链）、**覆盖率从 80% 提升至 82%**。4/21-4/22 集中处理已排定的 7 项 P0 快修 + OTP 防护，4/23-4/26 为本周冲刺 5 项的执行窗口。Backend 是本周瓶颈角色，如有人力建议加 1 名。

---

## 4/21（周一）

| ID | 任务 | DRI | 估时 | 依赖 | 验收 |
|----|------|-----|------|------|------|
| P0-03 | companion-detail 下单参数名统一（`companionId` → `companion_id`） | Frontend | 0.5h | — | 从陪诊师详情页点击预约，下单页正确预选陪诊师 |
| P0-04 | DEV_OTP `000000` 按环境剥离 | Frontend | 0.5h | — | production 构建中不包含 `000000` 常量 |
| P0-05 | 陪诊师通知页导航路径修正 | Frontend | 0.5h | — | 陪诊师端点击通知图标正确跳转到 `/pages/notification/index` |
| P0-07 | "进行中" tab 加入 accepted 状态 | Frontend | 0.5h | — | accepted 订单在"进行中"tab 中可见 |
| P0-01 | OTP 验证码 5 次尝试限制（开始） | Backend | 1d | — | — |
| P0-08 | B-01/B-02 凭证催办邮件+电话 | 用户/Ops | 外部 | — | 催办邮件已发出，获得回复 ETA |
| P0-09 | ICP 备案材料收集 | 用户 | 外部 | — | 备案所需材料清单确认，营业执照等文件就绪 |

---

## 4/22（周二）

| ID | 任务 | DRI | 估时 | 依赖 | 验收 |
|----|------|-----|------|------|------|
| P0-01 | OTP 暴力破解防护完成 + 测试 | Backend | 1d（续） | — | 同一手机号 5 次错误后锁定 15 分钟；覆盖率测试通过 |
| P0-06 | 电话拨打功能修复-后端（API 补充嵌套数据） | Backend | 0.5d | — | GET /orders/{id} 响应包含 companion.phone / patient.phone |
| P0-09 | ICP 备案材料提交 | 用户 | 外部 | 营业执照 | 备案申请已提交至管局，获得受理编号 |
| S-01 | API 请求 timeout 统一（15s） | Frontend | 0.5d | — | 所有 API 请求含 timeout，弱网下 15s 后正确抛错 |

---

## 4/23（周三）— 本周冲刺启动

| ID | 任务 | DRI | 估时 | 依赖 | 验收 |
|----|------|-----|------|------|------|
| P0-02 | 支付-订单过期联动修复（TD-PAY-01）：过期时关单 + 回调防御性退款 | Backend | 1d | — | 订单过期后迟到的支付回调自动触发全额退款；Payment 行标为 failed |
| P0-10 | 启用分支覆盖率 + CI 门禁 | QA | 0.5d | — | `pytest --cov-branch` 通过，CI 门禁 ≥60% 分支覆盖率 |
| SP-01 | OrderService 拆分启动：提取 RefundService | Backend | 1.5d | P0-02 | — |
| SP-02 | a11y 基础属性补全启动：可点击 view 加 `aria-role`、tab-bar `aria-current`、rating-stars `aria-label` | Frontend/Design | 1.5d | — | — |

---

## 4/24（周四）

| ID | 任务 | DRI | 估时 | 依赖 | 验收 |
|----|------|-----|------|------|------|
| SP-01 | OrderService 拆分完成：RefundService 独立 + OrderQueryService 只读查询分离 | Backend | 1.5d（续） | — | OrderService < 350 行；RefundService 独立文件 + 测试覆盖 ≥80%；所有现有测试通过 |
| SP-02 | a11y 基础属性补全继续 | Frontend/Design | 1.5d（续） | — | — |
| SP-04 | 陪诊师资质认证展示-后端：Companion 模型加 `certification_type` / `certification_no` / `certification_image_url` 字段 + API | Backend | 1d | — | — |
| P0-06 | 电话拨打功能修复-前端联调 | Frontend | 0.5d | P0-06 后端 | 患者/陪诊师端订单详情页点击电话按钮可拨打 |

---

## 4/25（周五）

| ID | 任务 | DRI | 估时 | 依赖 | 验收 |
|----|------|-----|------|------|------|
| SP-03 | 监控落地：5 条告警规则配置 + Prometheus exporter `/metrics` 端点 | Ops/Backend | 1d | — | `/metrics` 端点返回 Prometheus 格式指标；5 条告警规则 YAML 文件就绪（告警通道等 B-03 到位后接入） |
| SP-05 | 通知深链跳转-后端：Notification 模型加 `target_type` / `target_id` 字段 + API 返回深链参数 | Backend | 1d | — | GET /notifications 响应包含 target_type + target_id |
| SP-02 | a11y 基础属性补全完成 | Frontend/Design | 1.5d（续） | — | 所有可交互元素有 role 属性；rating-stars 有 aria-label；loading-overlay 有 aria-busy；tab-bar 有 aria-current |
| P0-13 | hospital.py 测试覆盖 32%→70%（开始） | QA | 1d | — | — |

---

## 4/26（周六）— 冲刺收尾 + 缓冲

| ID | 任务 | DRI | 估时 | 依赖 | 验收 |
|----|------|-----|------|------|------|
| SP-04 | 陪诊师资质认证展示-前端：详情页展示认证徽章 + 证书图片弹窗 | Frontend | 1d | SP-04 后端 | 陪诊师详情页展示"已认证"徽章，点击可查看证书图片 |
| SP-05 | 通知深链跳转-前端：通知列表项点击跳转到对应订单详情 | Frontend | 1d | SP-05 后端 | 点击通知跳转到 `/pages/patient/order-detail/index?id={order_id}` |
| P0-13 | hospital.py 测试覆盖完成 70% | QA | 1d（续） | — | hospital.py 行覆盖率 ≥70% |
| — | 本周 P0 未关闭项兜底 | 各 Owner | — | — | 7 个 P0 全部关闭 |
| — | 覆盖率检查 + 冲刺 5 项交付确认 | QA/Tech Lead | 0.5d | — | 覆盖率 ≥82%；5 项冲刺全部 merge |

---

## 4/27（周日）— 休息

---

## KPI 跟踪

### 覆盖率
- 后端行覆盖率：现 80% → 目标 **82%**（+2pp）
- 后端分支覆盖率：建立基线 ≥ **60%**
- hospital.py：32% → **70%**

### P0 关闭（本周必关 7 个）
- P0-01（OTP 限制）
- P0-02（支付联动）
- P0-03（参数名统一）
- P0-04（DEV_OTP 剥离）
- P0-05（通知路径修正）
- P0-06（电话拨打修复）
- P0-07（进行中 tab 修复）

### 本周冲刺 5 项交付
- SP-01 OrderService 拆分（RefundService + OrderQueryService）
- SP-02 a11y 基础属性补全（28 页面 + 9 组件）
- SP-03 监控落地（5 告警规则 + Prometheus exporter）
- SP-04 陪诊师资质认证展示（后端 + 前端）
- SP-05 通知深链跳转（后端 + 前端）

---

## 风险预警

1. **B-04 ICP 备案**：4/22 必须提交，否则 5 月铁定滑期。备案周期 10-20 工作日，越早提交越好。
2. **Backend 瓶颈**：4/21-4/26 Backend 承担 P0-01、P0-02、P0-06、SP-01、SP-04、SP-05 共 6 项，排满无余量。如有人力建议加 1 名后端。
3. **SP-03 监控告警通道**：5 条告警规则本周可写好 YAML，但告警通道（钉钉/短信）依赖 B-03 Azure 资源到位。本周先完成规则配置 + exporter 端点，通道接入顺延。
4. **SP-01 与 P0-02 冲突**：OrderService 拆分和支付联动修复都改 `order.py` 核心文件，建议 P0-02 先 merge 再启动 SP-01。
5. **凭证进度**：B-01~B-04 全部 Pending，用户需每日跟进外部流程。4/25 周五做凭证进度 check。
