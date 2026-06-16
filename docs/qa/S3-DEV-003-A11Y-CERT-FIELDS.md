# S3-DEV-003-A11Y-CERT-FIELDS 验证说明

> 面向测试员复测 `S3-TEST-003-A11Y-CERT-FIELDS` / 原 `S3-TEST-003` AC#5。范围仅限 trust precheck 的陪诊师资质（cert）字段，不扩展到其他页面。

## 验证数据

准备 3 组订单 precheck summary：

1. `verified`：`ready=true`，包含 `companion_cert_pseudonym_name`、`companion_cert_work_id`、`companion_cert_qualifications`、`companion_cert_verified_at`。
2. `pending_resubmit`：`ready=false`，至少包含 `companion_cert_pseudonym_name` 或 `companion_cert_work_id`。
3. `unverified/missing`：`ready=false`，cert 字段为空或缺失。

不得在用户端页面展示 `companion_cert_proof_image_urls` 原图或真实身份字段。

## iOS VoiceOver

入口：订单详情页 → 订单准备状态 → 陪诊师资质卡。

预期：

- VoiceOver 聚焦陪诊师资质卡时，能读出：
  - 卡片名：陪诊师资质
  - 状态：已就绪 / 未就绪
  - 姓名/化名、工号、资质、认证时间；缺失字段读“未提供”或“待核验”
  - 必要提示：已认证时提示可继续付款；未就绪时提示等待核验或重新选择陪诊师
- 状态图标旁有可见文字“已就绪/未就绪”，状态不只依赖绿色/橙色。
- 证件原图不在用户端展开；VoiceOver hint 明确“证件原图不会在用户端展示”。

## 微信小程序无障碍

入口：微信开发者工具或真机 → 患者订单详情页 → 陪诊师资质卡。

预期：

- cert-card 根节点有 `aria-label`，读出陪诊师资质、语义状态、姓名/工号/资质/认证时间。
- 状态徽章分别有无障碍文案：
  - 已认证
  - 临时证明补交中
  - 未认证
- 字段阅读顺序与视觉顺序一致：状态 → 姓名 → 工号 → 资质 → 认证时间 → 空态/提示。
- 不出现未命名的图标/按钮；cert-card 内无可点击控件，不应引入额外焦点陷阱。

## 色盲模拟 / 非颜色状态

入口：iOS 模拟器 Accessibility Inspector / macOS 色彩滤镜，或微信开发者工具截图后用色盲模拟工具检查。

预期：

- verified / pending_resubmit / unverified 不能只靠颜色区分。
- iOS 状态图标旁可见“已就绪/未就绪”；微信状态 badge 有明确文字“已认证/临时证明补交中/未认证”。
- 即使在灰阶或红绿色弱模拟下，关键状态仍可通过文字区分。

## 键盘 / 焦点路径

入口：iOS 外接键盘 / 模拟器键盘导航；微信开发者工具 focus 调试或真机读屏焦点顺序。

预期：

- cert-card 本身是只读信息组，不新增可点击控件。
- 焦点顺序遵循页面视觉顺序；进入 cert-card 后可继续移动到后续订单信息/操作按钮。
- 不出现焦点陷阱、跳焦或主要支付/取消/联系按钮不可达。

## 回归命令

```bash
cd wechat && npm test -- --runTestsByPath __tests__/components/cert-card.test.js
```

iOS 单测需 macOS/Xcode runner 执行（当前 WSL 无 `xcodebuild`）：

```bash
cd ios && xcodebuild test -scheme YiLuAn -destination 'platform=iOS Simulator,name=iPhone 16'
```
