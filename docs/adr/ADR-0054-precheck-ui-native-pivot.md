# ADR-0054 信任前置卡 iOS 端从 H5+WKWebView 转向 Swift Native

- **Status**: Accepted
- **Date**: 2026-06-11
- **Decider**: 帝君 (隐式拍板 — 通过 task acceptance 已写定 Swift native), 魈 architect (主动修正 spec drift)
- **Tags**: ui, ios, cross-platform, scope

## Context

S3-DEV-003 信任前置卡设计阶段 (`docs/design/S3-trust-precheck-ui.md` §6.2/6.3) 押了 "iOS = H5+WKWebView 壳 + `packages/precheck-card` 跨端 React 共享代码库" 方案。

胡桃 dev 接 `S3-DEV-003-TRUST-UI-IOS` task 时, 发现 task acceptance 5 条全是 Swift native 口径 (SwiftUI 显示 4 cert 字段 / WS / 不暴露原图 URL / E2E), 跟 design doc §6.2 直接 spec drift, 06:49Z ping 架构师拍板 A/B/C。

### 物理证据 (魈 grep main `21ee9a7`)

| 项 | 实测 |
|---|---|
| `./packages/` | ✗ `ls: cannot access 'packages/'` |
| `./ios/YiLuAn/Features/` | 13 features 全 Swift Native (Auth/Chat/Companion/Legal/Notifications/Order/Patient/Payment/Profile/Review/Settings/Share) |
| design doc §6.2 依赖项 | `packages/precheck-card` (不存在) + WKWebView 壳 (repo 无其他 use case) |
| design doc §6.3 依赖项 | 全部 `packages/precheck-card/__tests__/*.ts` (不存在) |
| 已合 PR 现状 | PR #237-#262 全 backend, 无任何 cross-package / WKWebView 引用 |

design doc 描述的世界与 repo 现状完全不符。

## Decision

iOS 端 precheck UI 实施口径定为 **Swift Native**, 与 `./ios/YiLuAn/Features/` 现有 13 features 模式一致。

废弃方案: H5+WKWebView 壳 + `packages/precheck-card` 跨端 React 共享代码库 + macOS runner 新增 CI E2E job。

跨端字段一致性口径改为 **OpenAPI schema as single source of truth**, 三端各自从 schema 同步字段名/类型, 通过 backend 已有 `OpenAPI drift` CI 闸 + 已有 ABAC schema-level test (`test_view_schema_excludes_15_named_negative_list_fields`) 双管。

## Alternatives Considered

### 方案 A: 拆 task (维持 design doc) — ❌ 不选

- 拆出 `S3-INFRA-PACKAGES-MONOREPO` (起 `./packages/` + pnpm workspace + 构建工具链) + `S3-DEV-003-PRECHECK-CARD-SHARED` (写 React 跨端组件库) + `S3-DEV-003-TRUST-UI-IOS-WKWEBVIEW-SHELL` (写 WKWebView 壳 + JSBridge) + macOS runner CI job 配置
- **理由不选**: scope 爆炸, 不是单个 task 能 cover; 新建 monorepo 架构是 repo-wide 基础设施变更, 需要重新走 RFC; H5+WKWebView 跨端模式在 repo 全无其他 use case (iOS 已有 13 features 全 native), 为单个 precheck 卡引入是反向架构
- 风险: 拖 S3-DEV-003-TRUST-UI-IOS 至少 2 周, 阻塞 S3 trust 链上线

### 方案 B: 闷头按 task acceptance 写 Swift Native — ✅ 选

- 胡桃直接在 `./ios/YiLuAn/Features/Precheck/` 起新 feature 子模块, 4 SwiftUI View + WS 接入 + URLSession polling fallback + UIApplication lifecycle hook
- iOS CI E2E 复用现有 `Build & Test (iOS Simulator)` workflow (branch protection required check), 覆盖 task acceptance AC#5 (3 状态切换) + AC#3 (WS 推送 → UI 刷新)
- design doc §6.2/6.3 r4 amend 同步更新, ADR (本文件) 落 pivot 理由
- **优**: 跟 repo 现状对齐 (单体仓 + native iOS); scope 单 task 内可控; 无新 CI 成本; ABAC 由 backend L1 锁定, client 不渲染敏感字段即可
- **劣**: 三端共享字段映射需要各自手写 (但 OpenAPI 生成器可降本); client-side 文案 lint 失去 (改由 backend 字符串下发, 实际更合理 — 文案是业务字段, 不是 UI 字段)

### 方案 C: 重写整个 design doc r4 — ❌ 不选

- 推翻 design doc, 重新走 awaiting-approval review 链
- **理由不选**: 重 review 拖时间; design doc r1-r3 amend 已经 review 多轮, §3-§5 / §7-§10 部分仍正确, 没必要全推; r4 amend 补章节 + ADR 落 pivot 理由的方式已是标准做法 (反案 #5/#6 教训: 流程闭环必须落字, 但不需要重 review 闸)

## Consequences

### 立即收益

- 胡桃 unblock, 可立即按 task acceptance 起 Swift native code
- 无新 CI workflow 需要配置 (复用已有 `Build & Test (iOS Simulator)`)
- 跨端字段同步从"维护共享 npm package"降为"各自从 OpenAPI schema 生成或对齐", 降低实施 + 维护成本
- ABAC 模型简化: client-side ABAC test 全部下线 (PR #253 schema-level test + PR #262 E2E layer 已是双管, 不需要 client 第三管)

### 长期影响

- iOS / WX / admin-v2 三端 client 代码物理隔离, 不耦合 (本来就该这样, design doc 原方案是反向耦合)
- 若未来真有 4+ 端需共享 UI 逻辑 (例如 RN 接入), 再考虑起 `./packages/` monorepo + 跨端组件库, 但那是 repo-wide 架构变更, 需要独立 ADR
- 文案管理由 admin-v2 `S3-DEV-003-ADMIN-COPY` 维护, backend 下发为字符串, 三端直读 — 这是干净的设计 (文案是业务关心物, 不是 UI 关心物)

### 风险与缓解

- **风险**: design doc r1-r3 review 时刻晴 / 胡桃在 §6.2 已 review 过 H5+WKWebView 方案, 现 r4 推翻是否回头看
  - **缓解**: r4 amend 标注清楚 spec drift 触发 + 物理证据, 胡桃已 ack (06:49Z ping 拍板 B); 刻晴在 PR review 时 cross-check 即可
- **风险**: iOS 端 client-side ABAC test 下线后是否有漏暴露字段风险
  - **缓解**: backend ABAC L1 (PR #253 c2) + E2E schema layer (PR #262) 已是 trust boundary; client 不渲染 = 不显示, 即使后端误传也只显示空白, 不暴露
- **风险**: 三端字段同步漂移
  - **缓解**: backend `OpenAPI drift` CI 闸已存在 (PR #255 / PR #237 复用), `docs/api/openapi.json` 改动必 commit; 三端从 schema 同步只需 ad-hoc 检查

## Compliance

- ADR-0048 §5.3 (ABAC 17 字段 negative list): backend 锁定不变, client 不渲染即合规
- ADR-0050 (worktree owner metadata): 无影响
- ADR-0051 (evidence-first 协议): 本 ADR 拍板基于 grep 物理证据, 非 design doc 想象
- design doc §6.2 / §6.3 r4 amend: 跟本 ADR 同步落地, 互相引用
