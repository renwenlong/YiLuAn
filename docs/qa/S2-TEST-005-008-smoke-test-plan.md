# S2 联调冒烟测试计划（S2-TEST-005~008）

依据：ADR-0039 验收口径 §1~§5
环境：staging（已 healthy 跑 42h）
测试员：刻晴

## 一、范围 & 状态

| Task | 端 | 依赖 develop | 状态 | 备注 |
|------|----|--------------|------|------|
| S2-TEST-005 | 微信 | S2-INT-003 ✅ done | in-progress | 当前首轮实测中 |
| S2-TEST-006 | iOS | S2-INT-004 ❌ not-started | blocked | 等胡桃完成 S2-INT-004 |
| S2-TEST-007 | admin-h5 + 跨端契约 §4 | S2-INT-005 ❌ not-started | blocked | 等魈完成 S2-INT-005（帝君派魈接） |
| S2-TEST-008 | 三端出口冒烟报告 | 005/006/007 | blocked | 等前三个全 done |

## 二、冒烟用例矩阵

### S2-TEST-005 微信端（§1）
> 口径决议：魈 (A) — ADR-0039 不存在，按设计现状验。PaymentState/OrderStatus 解耦，支付完成不驱动业务域状态机。

| ID | 用例 | 步骤 | 期望 |
|----|------|------|------|
| W-1 | U-1 下单核心链路 | 选品→下单→wxpay 回调 | 订单创建成功；mock-pay-stub 收到 prepay 并真实回调 /payments/wechat/callback；PaymentState=paid；timeline 追加"已支付"节点 |
| W-2 | 业务状态流转 | 陪诊师 accept → start → complete | OrderStatus: created → accepted → in_progress → completed，由陪诊师动作推进，与 PaymentState 解耦 |
| W-3 | F2 静默分享落地 | 微信内点分享链接 → 落地页 | 自动 session 建立，无登录跳转 |
| W-4 | 脱敏 | 落地页查看患者信息 | 姓名/手机号按规则脱敏 |
| W-5 | WS 进度只读 | 长连接订阅订单进度 | 只读推送，无双向写 |
| W-6 | WS 断线重连 | 杀网 30s 后恢复 | 自动重连，补推丢失事件 |
| W-7 | 巨字号兼容 | iOS/Android 系统字号最大 | 关键页无溢出/截断 |

### S2-TEST-006 iOS 端（§2）
| ID | 用例 | 步骤 | 期望 |
|----|------|------|------|
| I-1 | U-1 下单（与微信逐字符比对） | iOS 下单流程 | 字段/顺序与微信一致，漂移即打回 |
| I-2 | 支付→状态 | Apple Pay/银联通道 | 与 §2.2 一致 |
| I-3 | F2 OTP 分享 | 生成 OTP→输入验证 | OTP 6 位/5min/3 次锁定 |
| I-4 | OTP 双轴频控-单 token 日上限 | 24h 内单 token 发码 ≥6 次 | 第 6 次拒绝（share_otp_token_daily_cap=5） |
| I-5 | OTP 双轴频控-单手机号 token 数上限 | 1h 内单手机号绑 ≥4 个不同 token | 第 4 个拒绝（share_otp_phone_token_cap=3） |
| I-5b | OTP TTL | 验证码生成 5min 后使用 | 拒绝（share_otp_ttl_seconds=300） |
| I-6 | 脱敏 + WS | 同 W-4/W-5 | 一致 |
| I-7 | 巨字号 | iOS Dynamic Type XXXL | 关键页无溢出 |

### S2-TEST-007 admin-h5（§3 + §4）
| ID | 用例 | 步骤 | 期望 |
|----|------|------|------|
| A-1 | token 鉴权 | 无 token 访问 /admin | 401 |
| A-2 | 订单管理 | 列表/详情/操作 | 可达，权限正确 |
| A-3 | 用户管理 | 列表/详情/状态切换 | 可达 |
| A-4 | 审计日志 | 操作后查 audit | 操作落库可查 |
| C-1 | §4 九字段契约-OpenAPI 基线 | 跑 scripts/qa/openapi_contract_diff.py（GUARDED_FIELDS=9，含 patient_name_masked） | 与基线 100% 一致 |
| C-2 | §4 d.ts 一致 | tsc check | 0 报错，9 字段全覆盖 |
| C-3 | §4 APIEndpointTests | 跑 iOS 契约测试套件 | 三端全绿，9 字段反序列化无遗漏 |

### S2-TEST-008 出口冒烟报告（§5）
出口 6 条：三端冒烟全通 / Share Token 两路换 session 通 / admin 四项达 / 契约 §4 绿 / 缺陷清单+闭环 / 报告产出确认 staging 可供 S2-TEST-004 灰度回归。

## 三、执行顺序
1. **首轮**：S2-TEST-005 微信端实测（进行中）
2. **等上游**：S2-INT-004 (胡桃) done → 启动 S2-TEST-006；S2-INT-005 (魈) done → 启动 S2-TEST-007
3. **收口**：三端全过 → S2-TEST-008 汇总出报告

## 四、Bug 流程
发现 bug → taskboard 新建 bug task（type=bug, related_to 当前 test task）→ 通知胡桃 → 当前 test 保持 in-progress。
