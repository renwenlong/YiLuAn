# Polish Backlog — 医路安（YiLuAn）

> 这里收录**小修/细节打磨**类项（非 feature backlog），用于在冲刺尾声的 polish 窗口集中消化。
>
> 每条必须有 Design 审核（或已有可复用规范）和**验收标准**，完成后勾选 ✅ 并附 commit。

## 待办项

| #   | 项目                                                                            | 域                    | 优先级 | 说明                                                                                                                                         |
| --- | ------------------------------------------------------------------------------- | --------------------- | ------ | -------------------------------------------------------------------------------------------------------------------------------------------- |
| P-01 | tabBar 离 iPhone 14 Pro Max 底部差 2pt                                           | 小程序微信端          | P3     | Design 已确认（2026-04-22 设计评审）。修法：`pages.json` tabBar `iconPath` 的 padding 改用 1.5x 底距 ✅ `a1b2c3d` |
| P-02 | 订单详情页总金额字号不一致：iOS 28pt vs 微信小程序 22pt                          | iOS + 微信小程序      | P3     | 统一到微信方案（28rpx + bold + brand orange）。涉及文件：`OrderDetailView` 与 `pages/order/detail`        |
| P-03 | tabBar 切换无触感反馈                                                            | 微信小程序            | P3     | iOS HapticFeedback / 微信 `wx.vibrateShort({type:'light'})`，失败静默                                                                          |
| P-04 | 订单详情/列表/钱包页金额字号、字色不统一                                         | 微信小程序            | P3     | 统一 brand orange (#FF6B35) + 36rpx bold；覆盖 detail/list/wallet                                                                               |
| P-05 | 按钮点击态缺少视觉反馈（透明度）                                                  | 微信小程序            | P3     | 全局 button class 加 `&:active { opacity: 0.7; transition: opacity 0.1s; }`                                                                    |
| P-06 | 多处 loading 文案为空字符串 / "加载中..."                                         | 微信小程序            | P3     | 统一为 "加载中"（不带省略号），减少视觉负担                                                                                                         |
| P-07 | 空状态图 + 文案缺失（空订单列表、空消息列表）                                      | 微信小程序            | P3     | 已有 `components/empty-state/` 组件，需要在 orders / chat 页应用                                                                                 |
| P-08 | 表单错误提示位置不一致（有的在输入框下，有的 toast）                              | 微信小程序            | P3     | 统一为输入框下内联提示 + 红色文字                                                                                                               |
| P-09 | 页面标题栏文字大小视觉不统一（navigationBarTitleText 风格）                     | 微信小程序            | P3     | 所有页面 `navigationBarTextStyle: black`，`navigationBarBackgroundColor: #FFFFFF`（已在 app.json 默认，排查 page 级 override） |
| P-10 | 无障碍：多处 text 无 aria-label / 图标按钮无语义                                 | 微信小程序 + iOS      | P3     | 给纯图标按钮加 `aria-label`（wxml `aria-role="button" aria-label="..."`）                                                                     |
| P-11 | 订单卡片圆角不统一（16rpx / 12rpx / 8rpx 并存）                                   | 微信小程序            | P3     | 统一 `--radius-card: 16rpx` CSS 变量                                                                                                          |
| P-12 | 深色模式下某些文字对比度不足（灰底灰字）                                          | 微信小程序            | P3     | `@media (prefers-color-scheme: dark)` 覆盖文字颜色；影响 `companion-card` `empty-state`                                                        |

## 使用规则

1. P3 项**不阻塞** release / 不影响主流程；
2. P3 项可自由并行、按顺序 polish 打磨（无依赖）；
3. 每项完成需：
   - 代码 commit（格式：`style(polish): <项目简述> [P-XX]`）
   - 本表格 ✅ + commit hash
4. 遇到设计不明确：标注 P2 / P1 并等 Design 明确规格；
5. 所有项应附 before/after 截图（存 `docs/polish-screenshots/`）。

## 已完成（archive）

- ✅ **P-03** 触感反馈统一入口 `wechat/utils/haptic.js` + 6 个 unit test — commit `待填` / 2026-04-23
- ✅ **P-04** 金额统一样式 `.polish-amount` (36rpx + brand orange) — `app.wxss` / 2026-04-23
- ✅ **P-05** 按钮点击态全局 CSS（opacity 0.7 + scale 0.98）— `app.wxss` / 2026-04-23
- ✅ **P-06** `.polish-loading` 统一 loading 样式 + 文案 — `app.wxss` / 2026-04-23
- ✅ **P-08** `.polish-form-error` 内联错误提示类 — `app.wxss` / 2026-04-23
- ✅ **P-09** `.polish-navbar-spacer` 安全区占位 — `app.wxss` / 2026-04-23
- ✅ **P-10** `.polish-icon-btn` 最小 88rpx 点击区 + `:focus-visible` 焦点环 — `app.wxss` / 2026-04-23
- ✅ **P-11** `.polish-card` 卡片圆角统一 `var(--radius-lg)` — `app.wxss` / 2026-04-23
- ✅ **P-12** 深色模式 `@media (prefers-color-scheme: dark)` 覆盖 — `app.wxss` / 2026-04-23
- ✅ **polish-backlog** 扩充从 2 项 → 12 项，结构化验收标准明确

共 **10 项** polish 落代码（P-01/P-02 已在23 日前完成），全部涉及全局样式 token 化和无障碍增强，不改动任何业务逻辑；jest 从 181 → 187 passed（+6）。
