# YiLuAn — App Store Connect 元数据模板

> 本文件用于 App Store Connect 的 App Information / Pricing / Version Information / App Review Information 等表单填写。所有字段均按 Apple 字符上限设计。

**版本：** v1.0  
**最近更新：** YYYY-MM-DD

---

## 1. App Information（App 全局信息，所有版本共用）

| 字段 | 中文（zh-Hans，主语言） | English (US, 备用) |
| --- | --- | --- |
| App Name（≤30） | 医路安 — 专业陪诊 | YiLuAn — Hospital Companion |
| Subtitle（≤30） | 陪同就医 安心放心 | Trusted hospital companion |
| Bundle ID | `com.yiluan.app`（占位，以 ASC 实际为准） | — |
| SKU | `YILUAN-IOS-2026` | — |
| Primary Language | Simplified Chinese | — |
| Primary Category | Medical | Medical |
| Secondary Category | Health & Fitness | Health & Fitness |
| Content Rights | Does not contain third-party content | — |
| Age Rating | **17+**（参考下方"年龄分级问卷"） | 17+ |

> **年龄分级注意：** 医疗类 App 在 Apple "Medical/Treatment Information" 维度通常会被推到 17+；如最终仅做"非医疗陪诊撮合"则可能 12+。最稳妥按 17+ 报，避免后续重提。

### 年龄分级问卷参考答案

| 维度 | 答案 |
| --- | --- |
| Cartoon or Fantasy Violence | None |
| Realistic Violence | None |
| Sexual Content or Nudity | None |
| Profanity or Crude Humor | None |
| Alcohol, Tobacco, or Drug Use | None |
| Mature/Suggestive Themes | None |
| Simulated Gambling | None |
| Horror/Fear | None |
| Medical/Treatment Information | **Infrequent/Mild**（陪诊场景下可能涉及就医描述；不提供诊疗信息） |
| Unrestricted Web Access | No |
| User-Generated Content | **Yes — Infrequent/Mild**（聊天 + 评价；具备举报与屏蔽机制） |

---

## 2. Version Information（每个版本单独填）

### 2.1 Promotional Text（≤170，可不重新提审更新）

> 新版"医路安"上线啦！预约更快、陪诊师匹配更精准；新增订单状态实时推送、Apple Sign-In 一键登录；让每一次就医都安心、有人陪。

### 2.2 Description（≤4000）

> 医路安是一款专注于"医疗陪诊"撮合服务的 iOS 应用。当您或家人需要前往医院就诊，却面临挂号难、流程不熟、独自就医不安心等问题时，医路安帮助您快速匹配到专业的陪诊师，全程陪同、答疑、记录、转达，让就医不再孤单。
>
> 【核心服务】
> · 陪同就医：从挂号、候诊、检查到取药，全程陪同
> · 流程协助：熟悉医院流程，少走冤枉路
> · 沟通协助：协助记录医嘱、转达医生意见
> · 情绪支持：让独自就医的您不再焦虑
>
> 【特色功能】
> · 一键定位附近医院与陪诊师，距离一目了然
> · 在线下单、实时聊天、订单状态推送
> · 陪诊师实名 + 资质双重认证，服务更安心
> · 服务结束后可评价与反馈，平台严格质控
> · Apple ID / 手机号双登录方式，注重隐私
>
> 【适用人群】
> · 老年人独自就医
> · 异地就医、不熟悉当地医院
> · 上班族无法陪同家人就医
> · 孕妇、术后康复者、行动不便者
> · 需要专业沟通协助的患者
>
> 【关于我们】
> · 医路安严格遵循《个人信息保护法》《互联网信息服务管理办法》等法律法规，采取传输加密、存储加密、最小化收集等多重措施保护您的隐私。
> · 医路安提供的是非医疗性陪诊服务，不构成诊断、治疗或用药意见，所有医疗决策请遵医嘱。
>
> 隐私政策：https://yiluan.example/privacy （占位）
> 服务条款：https://yiluan.example/terms   （占位）
> 客服邮箱：support@yiluan.example          （占位）
>
> 期待与您一起，让就医这件事，多一份安心。

### 2.3 Keywords（≤100，逗号分隔，不留空格）

```
陪诊,陪诊师,陪诊服务,陪同就医,医院,挂号,老人陪诊,异地就医,陪诊预约,健康
```

### 2.4 What's New in This Version（≤4000）

```
v1.0.0 首次发布
· 手机号 + Apple ID 登录
· 陪诊师列表、详情、下单、聊天、评价完整闭环
· 订单状态实时推送
· 隐私合规：完整隐私政策与权限说明
```

> 后续版本模板：
> ```
> · 修复了 XXX 已知问题
> · 优化了 XXX 体验
> · 新增 XXX 功能
> ```

### 2.5 Support URL / Marketing URL / Privacy Policy URL

| 类型 | URL（占位） |
| --- | --- |
| Support URL | https://yiluan.example/support |
| Marketing URL | https://yiluan.example |
| Privacy Policy URL | https://yiluan.example/privacy |
| Terms of Use URL（IAP 启用后必填） | https://yiluan.example/terms |

---

## 3. App Review Information（审核信息）

### 3.1 Sign-in required: **Yes**

| 角色 | 账号 | 验证码 |
| --- | --- | --- |
| 患者 | `13800000001` | OTP `000000`（开发环境固定） |
| 陪诊师 | `13800000002` | OTP `000000` |

### 3.2 演示步骤（中文）

1. 启动 App，阅读并同意"隐私政策"与"服务条款"。
2. 在登录页选择"手机号登录"，输入 `13800000001`，点击"获取验证码"。
3. 输入 `000000`，进入患者主页。
4. 浏览"附近医院/陪诊师"，点击下单。
5. 体验聊天、查看订单详情。
6. 在"我的 → 设置"中可查看权限说明、注销账号等。

> 切换陪诊师视角：登出后用 `13800000002 / 000000` 登录，可看到"待接单"列表。

### 3.3 Reviewer Notes（中英）

```
中文：
1. 医路安为陪同就医撮合平台，不提供诊疗、用药建议、远程问诊或互联网医院服务。
2. 当前版本支付通道为 mock（演示），实际不会发生扣款；点击"立即支付"将直接跳转到"支付成功"演示页。
   未来版本接入微信支付/Apple In-App Purchase 后将通过版本更新提交审核。
3. App 中所有医院/陪诊师为示例数据，便于审核体验完整流程。
4. 演示账号 OTP 固定为 000000，仅开发/审核环境生效。
5. 我们已设置 ITSAppUsesNonExemptEncryption=NO（仅使用 HTTPS/TLS 标准加密，未含自定义加密）。

English:
1. YiLuAn is a hospital-companion booking marketplace. It does NOT provide medical diagnosis,
   treatment, telemedicine, or any internet hospital service.
2. The payment flow in this build is a MOCK used purely for demo / review. Tapping "Pay" jumps
   to the "payment success" demo screen; no real charge happens. Live payment (WeChat Pay /
   Apple IAP) will be enabled in a later build with a fresh review submission.
3. Hospital and companion data shown are sample data for the reviewer to walk through the flow.
4. Demo OTP 000000 only works in the dev/review environment.
5. ITSAppUsesNonExemptEncryption=NO; the app uses only standard HTTPS/TLS, no custom crypto.
```

### 3.4 Contact Information

| 字段 | 值 |
| --- | --- |
| First Name | 文龙 |
| Last Name | 任 |
| Phone | +86-xxx-xxxx-xxxx（占位） |
| Email | review@yiluan.example（占位） |

---

## 4. Pricing & Availability

| 字段 | 值 |
| --- | --- |
| Price | Free |
| Availability | China mainland 上线（首发）；其他地区暂不上线（需备案/合规另行评估） |
| Pre-order | No |
| Distribution | App Store + TestFlight（内部 + 外部测试） |

---

## 5. App Store 截图与媒体清单（具体尺寸见 SUBMISSION_CHECKLIST.md）

- iPhone 6.7"（1290×2796）— 必填，5 张
- iPhone 6.5"（1284×2778）— 必填，5 张
- iPhone 5.5"（1242×2208）— 推荐，5 张
- iPad 12.9" 第三代+（2048×2732）— 仅当 iPad 通用版必填
- App Preview Video（可选，每个尺寸最多 3 个，15-30 秒）

---

## 6. 上线后

- 灰度发布：使用 Phased Release（7 天分阶段放量）
- 监控：Crash-free 用户率、Apple App Analytics、自有埋点
- 评价响应：客服在 24h 内回复 1-3 星评价
