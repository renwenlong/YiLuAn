# YiLuAn Design Tokens — Single Source of Truth (AI-10)

> 跨端尺寸 token 统一：iOS（pt）+ 微信小程序（rpx）。
> **`design/tokens.json` 是唯一事实源**。两端实现必须从它派生。

---

## 背景

晨会盘点发现两端尺寸已经漂移：

| 元素 | iOS（pt） | 小程序（rpx） | 折算后差异 |
| --- | --- | --- | --- |
| 主按钮高度 | 32pt | 28rpx ≈ 14pt | **18pt 偏差** |
| 导航栏高度 | 50pt | 88rpx ≈ 44pt | **6pt 偏差** |

继续放任会导致：① 视觉验收两端各自一套基准 → 设计稿被绕过；② 两端对外宣传同一产品但观感不同。

**AI-10 决议：以 iOS HIG 为事实基准，把小程序的尺寸追平到 iOS。**

---

## 单位换算约定

**`1pt = 2rpx`**（DPR2 假设，覆盖 iPhone 6/7/8/SE/X/11/12/13/14/15 standard）。

| 设备 | 实际 DPR | rpx 换算 |
| --- | --- | --- |
| iPhone SE/standard 系列 | DPR2 | 1pt = 2rpx ✅ 直接换算 |
| iPhone Pro Max / Plus | DPR3 | 由微信运行时自动按屏宽缩放，**无需我们手算** |
| Android 各机型 | 0.5x ~ 4x | 同上 |

> 设计稿里所有尺寸先用 pt 思考，再用 `1pt = 2rpx` 落到小程序。**这是约定，不是真相** —— 真相是 token 表。

---

## 目录

```
design/
├── tokens.json        # ✨ 事实源
├── README.md          # 本文档
└── generate.py        # 生成脚本：tokens.json → wechat 两端实现

wechat/styles/tokens.wxss   # 由 generate.py 生成（CSS variables）
wechat/utils/tokens.js      # 由 generate.py 生成（JS 常量）

ios/YiLuAn/Core/Extensions/DesignSystem.swift
                            # 手工同步（避免动 Xcode 工程文件）
```

---

## 修改流程（**硬规则**）

1. 改 `design/tokens.json`
2. `python design/generate.py` → 自动生成 `wechat/styles/tokens.wxss` 和 `wechat/utils/tokens.js`
3. **手工**把变更同步到 `ios/YiLuAn/Core/Extensions/DesignSystem.swift`（保持现有命名不变，只补缺失项）
4. 在 PR 描述里粘贴 `tokens.json` 的 diff，让 reviewer 看清"事实源"层面的变化
5. **禁止**直接改两端实现文件而不改 tokens.json —— CI 会在后续接入 lint 校验

---

## 命名约定

| 维度 | iOS 命名（事实基准） | 小程序对应（CSS var） |
| --- | --- | --- |
| Spacing | `Spacing.xxs / xs / sm / md / lg / xl / xxl / xxxl` | `--spacing-xxs / xs / sm / md / lg / xl / xxl / xxxl` |
| Radius | `CornerRadius.xs / sm / md / lg / xl / full` | `--radius-xs / sm / md / lg / xl / full` |
| Typography | `Font.dsSmall / dsCaption / dsBody / dsHeadline / dsTitle / dsH1 / dsHero` | `--font-size-small / caption / body / headline / title / h1 / hero` |
| Color | `Color.brand / success / danger / textPrimary / ...` | `--color-brand / success / danger / text-primary / ...` |
| Component | `Button.heightPrimary / Navbar.height / ...` | `--btn-height-primary / --navbar-height / ...` |

> ⚠️ 小程序原 `wechat/styles/variables.wxss` **保留不动**（旧页面仍在用它）。新文件 `tokens.wxss` 是跨端对齐版，新页面/重构页面应优先 import `tokens.wxss`。

---

## Migration Backlog（W19+ 重构清单）

本任务（AI-10）**只产出 token 体系，不改任何现有页面**，避免与 AI-9 冲突。

下列页面计划在 W19 起按优先级迁移到新 token：

### 🔴 P0（视觉差异最显眼）
- `wechat/pages/index/index` —— 首页主按钮、导航栏
- `wechat/pages/profile/profile` —— 个人页 list-item 高度
- `ios/YiLuAn/Features/Home/HomeView.swift` —— 与小程序首页对齐验收

### 🟡 P1（中等优先级）
- `wechat/pages/services/*` —— 卡片 padding & radius 全部走 `--card-*`
- `wechat/components/btn-primary/*` —— 高度从 28rpx → 96rpx（=48pt）
- `wechat/components/navbar/*` —— 高度统一 88rpx
- `ios/YiLuAn/Features/Services/*` —— 同步 button 高度

### 🟢 P2（机会式迁移）
- `wechat/pages/feedback/*`
- `wechat/pages/about/*`
- 各 detail 页

> 重构 PR 一律带 `chore(ui-migration)` 前缀，便于聚合追踪。

---

## 与 `wechat/styles/variables.wxss` 的关系

| 文件 | 状态 | 用途 |
| --- | --- | --- |
| `wechat/styles/variables.wxss` | **冻结**（不删，不改） | 旧页面继续 import |
| `wechat/styles/tokens.wxss` | **新建**（本 PR） | 新页面 + 重构页面 import |

待 Migration Backlog 全部清空后，删除 `variables.wxss`、把 `tokens.wxss` 重命名为 `variables.wxss`。

---

## FAQ

**Q：iOS 端为什么不写生成脚本？**
A：避免动 Xcode 工程（pbxproj 合并冲突血案）。手工同步 + PR review 卡点已经够用。

**Q：以后能不能加 Android / RN？**
A：可以。新增端只需写一个 `generate.py` 的输出器即可，事实源不变。

**Q：颜色为什么也放进 token？**
A：因为颜色 + 尺寸 + 字号是设计系统的三大支柱，分开维护一定漂移。
