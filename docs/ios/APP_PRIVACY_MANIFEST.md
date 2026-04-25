# YiLuAn iOS — App Privacy Manifest（App Store Connect 字段对照）

> 用于在 App Store Connect → App Privacy 中逐项填表。本文件按 Apple 官方 14 大类
> （[App privacy details on the App Store](https://developer.apple.com/app-store/app-privacy-details/)）整理。
> 同步资产：`ios/YiLuAn/PrivacyInfo.xcprivacy`（Required Reasons API 声明）。

**版本：** v1.0  
**最近更新：** YYYY-MM-DD

---

## 0. 是否收集数据

| 项 | 选择 | 说明 |
| --- | --- | --- |
| Do you or your third-party partners collect data from this app? | **Yes** | 收集了下列若干类目 |
| 数据是否用于追踪（Tracking）？ | **No** | 不接入广告 SDK，不与第三方共享数据用于跨 App 跟踪；无 IDFA / ATT 提示 |

---

## 1. Contact Info（联系方式）

| 子类 | 是否收集 | 与用户身份关联 | 用于追踪 | 用途 |
| --- | --- | --- | --- | --- |
| Name | Yes | Linked | No | App 功能（订单履约、陪诊师认证） |
| Email Address | Yes（仅 Apple Sign-In 用户选择共享时） | Linked | No | App 功能、客服 |
| Phone Number | Yes | Linked | No | App 功能（OTP 登录、订单匹配） |
| Physical Address | No | — | — | — |
| Other User Contact Info | No | — | — | — |

## 2. Health & Fitness

| 子类 | 是否收集 |
| --- | --- |
| Health | **No** |
| Fitness | No |

> 注：用户填写的"症状描述"属于"User Content"而非健康数据；不接入 HealthKit。

## 3. Financial Info

| 子类 | 是否收集 | Linked | Tracking | 用途 |
| --- | --- | --- | --- | --- |
| Payment Info | **当前版本：No**（mock 支付，无真实交易） | — | — | 启用真实支付后改为 Yes / Linked / No / App Functionality |
| Credit Info | No | — | — | — |
| Other Financial Info | No | — | — | — |

> 真实支付走持牌支付机构，敏感卡信息不进入我们后端，因此即便启用，"Payment Info"也仅含订单号/金额。

## 4. Location

| 子类 | 是否收集 | Linked | Tracking | 用途 |
| --- | --- | --- | --- | --- |
| Coarse Location | Yes | Linked | No | App 功能（附近医院/陪诊师） |
| Precise Location | No | — | — | — |

## 5. Sensitive Info

| 子类 | 是否收集 |
| --- | --- |
| Sensitive Info（种族、宗教、性取向等） | **No** |

> 陪诊师上传的身份证号属于"Identifiers / Government ID"，在第 11 节声明。

## 6. Contacts

| 子类 | 是否收集 |
| --- | --- |
| Contacts | **No** |

## 7. User Content

| 子类 | 是否收集 | Linked | Tracking | 用途 |
| --- | --- | --- | --- | --- |
| Emails or Text Messages | Yes（站内聊天文本） | Linked | No | App 功能、客服 |
| Photos or Videos | Yes（用户主动上传的头像、凭证、聊天图片） | Linked | No | App 功能 |
| Audio Data | Yes（语音消息） | Linked | No | App 功能 |
| Gameplay Content | No | — | — | — |
| Customer Support | Yes | Linked | No | 客服 |
| Other User Content | Yes（评价、备注） | Linked | No | App 功能 |

## 8. Browsing History

| 子类 | 是否收集 |
| --- | --- |
| Browsing History | **No** |

## 9. Search History

| 子类 | 是否收集 |
| --- | --- |
| Search History | **No** |

## 10. Identifiers

| 子类 | 是否收集 | Linked | Tracking | 用途 |
| --- | --- | --- | --- | --- |
| User ID | Yes（平台 user_id、Apple sub） | Linked | No | App 功能、Analytics（仅自有，不上传第三方） |
| Device ID | Yes（APNs device token、`identifierForVendor`） | Linked | No | App 功能（推送）、防欺诈 |

> 不收集 IDFA（`ASIdentifierManager.advertisingIdentifier`）。

## 11. Purchases

| 子类 | 是否收集 |
| --- | --- |
| Purchase History | 当前版本 No；真实支付启用后 → Yes / Linked / No / App Functionality |

## 12. Usage Data

| 子类 | 是否收集 | Linked | Tracking | 用途 |
| --- | --- | --- | --- | --- |
| Product Interaction | Yes（页面停留、按钮点击聚合统计） | Linked | No | Analytics（自有后端） |
| Advertising Data | No | — | — | — |
| Other Usage Data | No | — | — | — |

## 13. Diagnostics

| 子类 | 是否收集 | Linked | Tracking | 用途 |
| --- | --- | --- | --- | --- |
| Crash Data | Yes | Linked | No | App Functionality（稳定性） |
| Performance Data | Yes | Linked | No | App Functionality |
| Other Diagnostic Data | No | — | — | — |

## 14. Surroundings / Body / Environment Scanning / Other Data

| 子类 | 是否收集 |
| --- | --- |
| Environment Scanning | **No** |
| Hands | No |
| Head | No |
| Other Data Types（Government ID 等） | **Yes**（陪诊师身份证号、资质证件）— Linked / No tracking / App Functionality（合规与资质审核） |

---

## Required Reasons API 声明（与 `PrivacyInfo.xcprivacy` 对应）

| API 类目 | 选用 reason code | 说明 |
| --- | --- | --- |
| `NSPrivacyAccessedAPICategoryUserDefaults` | `CA92.1` | 仅在 App container 内读写本 App 自身的偏好设置（语言、登录态尾号、首次启动标记等） |
| `NSPrivacyAccessedAPICategoryFileTimestamp` | `C617.1` | 用于显示用户上传/下载的文件时间戳（聊天附件、订单凭证） |
| `NSPrivacyAccessedAPICategorySystemBootTime` | `35F9.1` | 在 App 启动后用 `mach_absolute_time` 测量性能耗时，仅用于本进程内诊断 |
| `NSPrivacyAccessedAPICategoryDiskSpace` | `E174.1` | 在缓存清理与离线下载前检查可用磁盘空间，避免写入失败 |

> 选定的 reason code 均可在 [Apple Required Reasons API spec](https://developer.apple.com/documentation/bundleresources/privacy_manifest_files/describing_use_of_required_reason_api) 中查询。
> 如未来引入网络监控、键盘扩展、活动数据等，需在 manifest 中对应追加。

### 跟踪与 tracking domains

- `NSPrivacyTracking`：`false`
- `NSPrivacyTrackingDomains`：`[]`（空，无跨 App 跟踪域名）

### 收集的数据类型（`NSPrivacyCollectedDataTypes`）

详见 `PrivacyInfo.xcprivacy`，与本文 1-14 节一一对应。

---

## 演示账号与审核备注（同步给 App Privacy → App Review Information）

- 演示账号：`13800000001` / OTP `000000`（开发环境固定）
- 演示陪诊师：`13800000002` / OTP `000000`
- 审核备注（中）：医路安为陪同就医服务平台，**不提供医疗诊疗**。当前版本支付通道为 mock，仅用于演示，已在 App 内显著标识。
- Reviewer Notes（EN）：YiLuAn is a hospital-companion booking platform; we do not provide any medical consultation, diagnosis, or telemedicine. The payment flow in this build is a mock used for review demo; live payment will be enabled in a future build.

---

## 维护

- 任一收集项变化时，须**同步**：本文件 + `PrivacyInfo.xcprivacy` + App Store Connect 表单 + 隐私政策。
- 责任人：iOS Lead + DPO（占位）。
