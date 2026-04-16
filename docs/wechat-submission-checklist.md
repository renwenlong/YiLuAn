# 微信小程序提审清单

**项目**: 医路安 (YiLuAn)
**日期**: 2026-04-16

## 1. 基本信息（必填）

| 项目 | 状态 | 说明 |
|------|------|------|
| AppID | ⚠️ 待替换 | 当前为占位值 `wx0000000000000000`，需替换为正式AppID |
| 版本号 | ✅ | 在 project.config.json 中维护 |
| 项目描述 | ✅ | "医路安 - 陪诊服务平台" |
| 类目选择 | 📝 待确认 | 建议：生活服务 > 家政/生活服务，或 医疗 > 其他医学服务 |

## 2. 配置检查

| 配置项 | 状态 | 说明 |
|--------|------|------|
| pages 注册 | ✅ | 32个页面全部注册于 app.json |
| `__usePrivacyCheck__` | ✅ | 已启用 |
| permission 声明 | ✅ | `scope.userFuzzyLocation` 已声明 |
| requiredPrivateInfos | ✅ | `getFuzzyLocation` 已声明 |
| sitemap.json | ✅ | 已配置，允许所有页面被索引 |
| project.config.json | ✅ | 编译配置完整 |
| ext.json | ⚠️ 无 | 非第三方平台小程序，无需配置 |
| lazyCodeLoading | ✅ | 已启用 `requiredComponents` |
| style v2 | ✅ | 已启用 |

## 3. 隐私与协议

| 项目 | 状态 | 路径 |
|------|------|------|
| 隐私政策页面 | ✅ | `pages/legal/privacy/index` |
| 用户协议页面 | ✅ | `pages/legal/terms/index` |
| 账号注销 | ✅ | `pages/settings/delete-account/index` |
| 隐私弹窗 | ✅ | `__usePrivacyCheck__: true` |

## 4. 功能页面截图清单

提审时需准备以下页面截图：

1. **登录页** - `pages/login/index`
2. **角色选择页** - `pages/role-select/index`
3. **患者首页** - `pages/patient/home/index`
4. **下单页** - `pages/patient/create-order/index`
5. **订单详情页** - `pages/patient/order-detail/index`
6. **支付结果页** - `pages/patient/pay-result/index`
7. **陪诊师首页** - `pages/companion/home/index`
8. **可接单列表** - `pages/companion/available-orders/index`
9. **聊天房间** - `pages/chat/room/index`
10. **评价页** - `pages/review/write/index`
11. **个人中心** - `pages/profile/index`
12. **钱包页** - `pages/profile/wallet/index`
13. **隐私政策** - `pages/legal/privacy/index`
14. **用户协议** - `pages/legal/terms/index`

## 5. 测试账号准备

| 角色 | 手机号 | 验证码 | 说明 |
|------|--------|--------|------|
| 患者 | 待配置 | 000000（开发环境） | 用于审核员体验患者流程 |
| 陪诊师 | 待配置 | 000000（开发环境） | 用于审核员体验陪诊师流程 |

> 注意：正式提审需在后台配置审核专用测试号，验证码走真实短信或配置固定验证码白名单。

## 6. 审核风险点及规避

### 高风险

| 风险 | 描述 | 规避措施 |
|------|------|----------|
| 医疗类目资质 | 涉及医疗相关服务，可能需特殊资质 | 确认类目为"生活服务"而非"医疗"，文案避免使用"诊断、治疗"等医疗术语，强调"陪伴"性质 |
| 支付功能 | Mock 支付不可上线 | 提审前对接微信支付，或提交时说明"支付功能待接入" |
| 真实数据 | 审核员看不到实际服务内容 | 提前灌入种子数据：医院列表、模拟陪诊师、示例订单 |

### 中风险

| 风险 | 描述 | 规避措施 |
|------|------|----------|
| AppID 占位符 | 当前为测试ID | 提审前必须替换为正式 AppID |
| 位置权限 | 申请了模糊定位 | 确保使用场景合理（推荐附近医院），首次使用时弹窗说明用途 |
| 用户生成内容 | 聊天、评价功能 | 确保有内容安全审核机制（可对接微信内容安全API） |

### 低风险

| 风险 | 描述 | 规避措施 |
|------|------|----------|
| 页面加载慢 | 接口异常可能导致白屏 | 添加 loading 态和异常兜底页面 |
| tabBar 自定义 | 使用自定义 tabBar | 确保切换流畅，无闪屏 |

## 7. 提审前 TODO

- [ ] 替换正式 AppID（当前 `wx0000000000000000`）
- [ ] 对接微信支付（替代 Mock 支付）
- [ ] 灌入种子数据（医院、陪诊师）
- [ ] 配置审核测试账号
- [ ] 准备 14 张功能页面截图
- [ ] 确认小程序类目并上传对应资质
- [ ] 内容安全 API 接入（聊天/评价内容审核）
- [ ] `urlCheck` 确认为 true，API 域名已在后台配置
- [ ] 测试所有核心流程：注册→下单→支付→陪诊→完成→评价
