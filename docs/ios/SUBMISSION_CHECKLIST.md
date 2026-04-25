# YiLuAn iOS — App Store 提交检查清单

> 真机/苹果后台逐项打勾。**红色高风险项**集中在「中国大陆备案 / 医疗类合规 / 支付」。

**版本：** v1.0  
**最近更新：** YYYY-MM-DD

---

## A. 账号与证书（Apple Developer Portal）

- [ ] A.1 已加入 Apple Developer Program（个人 $99 / 组织 $99）
- [ ] A.2 Team ID 已确认；Apple Developer 后台可访问
- [ ] A.3 创建 App ID：`com.yiluan.app`（占位）
- [ ] A.4 开启 Capabilities：
  - [ ] Sign in with Apple ✅（已实现）
  - [ ] Push Notifications（待办，发布前需上 APNs key）
  - [ ] In-App Purchase（mock 阶段不开；真实支付启用前再开）
  - [ ] Associated Domains（如启用 Universal Links）
- [ ] A.5 Distribution Certificate（Apple Distribution）已生成或已存在
- [ ] A.6 Provisioning Profile：App Store Distribution Profile 已生成
- [ ] A.7 在 App Store Connect 创建应用记录，Bundle ID 与 A.3 一致

## B. Xcode 项目配置

- [ ] B.1 `Info.plist`：所有用到的权限均含中文 `NSXxxUsageDescription`（已补全）
- [ ] B.2 `Info.plist`：`ITSAppUsesNonExemptEncryption = NO`（已补全）
- [ ] B.3 `Info.plist`：`NSAppTransportSecurity.NSAllowsArbitraryLoads = NO`（已补全）
- [ ] B.4 `PrivacyInfo.xcprivacy` 已加入 `YiLuAn` target 的 Resources（**Xcode 中需手动勾选 Target Membership**）
- [ ] B.5 `YiLuAn.entitlements` 包含 `Sign in with Apple`、（可选）`aps-environment`
- [ ] B.6 Build Configuration：Release 为 Archive 默认；DEBUG flag 不带入 Release
- [ ] B.7 Optimization Level：Release = `-O`；Strip Debug Symbols = Yes
- [ ] B.8 Bitcode：iOS 14+ 默认关闭，无需操作
- [ ] B.9 Architectures：`Standard Architectures (arm64)`
- [ ] B.10 Minimum Deployment Target：iOS 16.0（确认与代码 API 一致）
- [ ] B.11 App Icon 1024×1024（无 alpha、无圆角、PNG）
- [ ] B.12 启动屏 LaunchScreen（不含敏感信息）
- [ ] B.13 移除示例图、TODO 注释、调试 URL

## C. 代码合规

- [ ] C.1 Release build 不含 `print(...)`（用 `#if DEBUG` 包裹，参见 README "代码合规扫描"）
- [ ] C.2 所有 `URLSession` / WebSocket 走 `https://` / `wss://`
- [ ] C.3 登出时清空 Keychain + 关键 UserDefaults（已实现：`KeychainManager.clearAll()` + UserDefaults reset）
- [ ] C.4 不在日志中打印手机号、token 等敏感数据
- [ ] C.5 未使用被 Apple 拒绝的 API（如 `UIDevice.uniqueIdentifier`、IDFA 无 ATT）
- [ ] C.6 第三方 SDK 列表已盘点（见 docs/ios/APP_PRIVACY_MANIFEST.md「第十节」）
- [ ] C.7 所有第三方 SDK ≥ Apple 要求版本（提供 PrivacyInfo + 签名）

## D. App Store Connect 元数据

- [ ] D.1 App 名 / 副标题 / Keywords / 描述 已按 docs/ios/APP_STORE_METADATA.md 填写
- [ ] D.2 主语言 = 简体中文；可选添加英文本地化
- [ ] D.3 Age Rating 完成问卷（建议 17+）
- [ ] D.4 Pricing：免费；地区先勾"中国大陆"
- [ ] D.5 App Privacy 表已按 docs/ios/APP_PRIVACY_MANIFEST.md 全部勾选并保存
- [ ] D.6 隐私政策 URL（已上线）已填入
- [ ] D.7 Support URL / Marketing URL 已上线
- [ ] D.8 演示账号 + Reviewer Notes（中英）已填

## E. 截图与素材

| 尺寸 | 设备代表 | 像素 | 数量 | 必填 |
| --- | --- | --- | --- | --- |
| 6.7" | iPhone 15 Pro Max / 14 Pro Max | 1290 × 2796 | 5 | ✅ |
| 6.5" | iPhone 11 Pro Max | 1284 × 2778 / 1242 × 2688 | 5 | ✅ |
| 5.5" | iPhone 8 Plus | 1242 × 2208 | 5 | 推荐 |
| iPad 12.9" 第 6 代 | iPad Pro 12.9" | 2048 × 2732 | 5 | iPad 通用版必填 |
| App Icon | — | 1024 × 1024 PNG（无 alpha） | 1 | ✅ |

- [ ] E.1 截图已用真机/模拟器在 Light Mode 拍摄（5 张分别覆盖：登录、首页、陪诊师详情、下单、聊天）
- [ ] E.2 截图无状态栏遮挡敏感信息
- [ ] E.3 截图文字均为中文（主语言一致）
- [ ] E.4 ico 1024 通过 `pngcheck` 验证无 alpha 通道

## F. TestFlight

- [ ] F.1 上传第一个 Build（Xcode → Product → Archive → Distribute App）
- [ ] F.2 等待处理完成（通常 10-30 分钟）
- [ ] F.3 内部测试组（最多 100 名团队成员）邀请加入
- [ ] F.4 外部测试组：补充 Test Information（中英），等待 Beta App Review（24-48h）
- [ ] F.5 在多机型 + iOS 16 / 17 / 18 上跑核心路径
- [ ] F.6 验证 Apple Sign-In 在 TestFlight 环境真机可登录
- [ ] F.7 验证推送（如启用）

## G. 提交审核

- [ ] G.1 Version Information 完整，截图齐
- [ ] G.2 Build 已选定
- [ ] G.3 Export Compliance：已声明 `ITSAppUsesNonExemptEncryption=NO`，无需 ERN
- [ ] G.4 Content Rights 已勾选
- [ ] G.5 Advertising Identifier (IDFA)：选 **Does not use IDFA**
- [ ] G.6 选择 "Manually release" 或 Phased Release
- [ ] G.7 点击 Submit for Review

## H. 中国大陆合规（医疗类，**高风险**）

> 自 2023-09 起 China App Store 必填 ICP 备案号；医疗类还会触发额外资质要求。

- [ ] H.1 **ICP 备案**：已在工信部 https://beian.miit.gov.cn 完成域名备案，拿到备案号 `京ICP备XXXXXXXX号`
- [ ] H.2 **App 备案（工信部 App 备案）**：自 2024-03 起新增要求；通过云服务商或自助通道提交
- [ ] H.3 **互联网信息服务备案号**：填入 App Store Connect "App Information → 中国大陆" 字段
- [ ] H.4 **互联网医疗信息服务**：医疗类 App **强烈建议**取得"互联网药品信息服务资格证书"或"医疗机构执业许可证"链接，否则极易因 4.0 / 5.1.1 / 1.4.1 拒审
- [ ] H.5 **公司主体（必备）**：纯个人开发者无法在中国大陆上架医疗类 App，需公司主体 + 营业执照 + 法人身份证
- [ ] H.6 **医疗免责声明**：App 内显著位置（启动页 / 设置页）声明"本平台不提供诊疗服务"

## I. 第三方 SDK & SKAdNetwork

- [ ] I.1 SDK 列表（Apple Sign-In SDK 内置；不接入广告 SDK） ✅
- [ ] I.2 如未来接入 SDK：
  - [ ] 提供 `PrivacyInfo.xcprivacy`
  - [ ] 提供数字签名
  - [ ] 加入 Apple "commonly used SDKs" 名单的须特别处理
- [ ] I.3 `Info.plist > SKAdNetworkItems`：当前为空（无广告归因），无需配置

## J. 审核拒绝高频原因预警

| 拒绝条款 | 风险点 | 缓解 |
| --- | --- | --- |
| **2.1 App Completeness** | mock 支付被识别为占位/未完成功能 | Reviewer Notes 中**显式说明** mock 用途；mock 跳转页有"演示模式"水印 |
| **2.3.10 Accurate Metadata** | 截图、描述与实际功能不符 | 截图必须为真实 UI |
| **3.1.1 In-App Purchase** | 数字商品/虚拟服务未走 IAP | 陪诊为线下服务，**不**适用 IAP（属"Person-to-Person Services" 例外）；如审核质疑，引用 3.1.3(d) |
| **4.0 Design / 4.2.6 Spam** | 模板化或重复内容 | 强调差异化（陪诊师认证、聊天闭环） |
| **4.3 Spam / Duplicate** | 与已上架同类 App 雷同 | 准备品牌差异说明 |
| **5.1.1 Data Collection** | 权限请求过宽、未与功能挂钩 | 已逐项最小化（见 Info.plist） |
| **5.1.2 Data Use & Sharing** | 未声明第三方共享 | 隐私政策已列；App Privacy 表 4.1 共享方已勾 |
| **5.1.5 Location Services** | 在不必要时请求定位 | 已用 `WhenInUse`；首次进入"附近"页面时弹 |
| **5.2.1 Intellectual Property** | 医院 Logo 使用未授权 | 用通用图标 + 医院名文字 |
| **1.1.6 / 5.6.1 Sign in with Apple** | 提供其他第三方登录但未提供 Apple Sign-In | 已实现 Apple Sign-In ✅ |
| **5.6.2 Account Deletion** | 无 App 内注销账号入口 | 已实现 `DeleteAccountView` ✅；确认走通 |
| **China 4.0** | 医疗类无资质 | 见 H.4 |

---

## 完成

- [ ] 所有 ✅ 项已通过
- [ ] 高风险项 H.4 已与法务确认
- [ ] 提交日期：YYYY-MM-DD
- [ ] 审核结果：[ ] Approved [ ] Rejected — 拒绝原因：____________

> 上线后：监测 Crash-free 用户率 ≥ 99.5%；评价 1-3 星 24h 内回复。
