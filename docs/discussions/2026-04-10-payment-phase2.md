# 2026-04-10 支付架构 Phase 2 讨论记录

**参与角色：** Arch / Backend / Frontend / QA  
**背景：** Phase 1 已完成 PaymentService 骨架，用户确认暂无真实微信支付凭证，要求用 mock 凭证先写通完整链路，后续替换。

---

## 讨论过程

**Backend：**
> Phase 1 的 WechatPaymentProvider 目前是 `raise NotImplementedError`。我建议现在把它完整实现出来，但内部用 mock 数据模拟微信 v3 的请求/响应格式。这样前端可以按真实流程联调，等真实凭证到了只需改配置。

**Arch：**
> 同意。关键是要模拟出微信支付的完整时序：
> 1. 统一下单 → 返回 prepay_id
> 2. 前端签名参数 → 拉起支付
> 3. 异步回调通知 → 更新支付状态
> 4. 退款申请 → 退款回调
>
> mock 模式下回调可以同步模拟，但接口签名和参数结构要和真实一致，这样前端代码不需要二次改造。

**Frontend：**
> 小程序端需要 `wx.requestPayment` 的参数。mock 模式下没法真正拉起微信支付弹窗，我建议 mock 时直接跳过弹窗、走"支付成功"流程。但参数格式保持一致，真实接入时只需去掉 mock 判断。

**QA：**
> 需要同时写支付流程的自动化测试，覆盖：
> - 正常支付
> - 重复支付拦截
> - 支付后取消退款
> - 回调幂等
> - 回调验签失败（Phase 2 真实接入时验证）

**Arch：**
> 补充一点：Payment 模型的 UniqueConstraint `(order_id, payment_type)` 在新架构下可能有问题——同一订单取消后重新支付，会出现两条 `pay` 类型记录。建议改为允许多条记录，通过 status 字段区分。

**Backend：**
> 好点。不过 MVP 先不改约束，因为当前业务流程里取消后不能重新支付。如果后续支持重新下单再改。

**Arch：**
> 接受。先不改，记个技术债。

## 共识

1. WechatPaymentProvider 完整实现，但用 mock 数据模拟 v3 接口格式
2. 前端 mock 模式跳过 `wx.requestPayment` 弹窗，直接走成功流程
3. 回调端点完整实现验签逻辑骨架，mock 模式跳过验签
4. 新增支付流程自动化测试
5. UniqueConstraint 暂不修改，记技术债
6. 凭证到位后只需改 `.env` 中 `payment_provider=wechat` 及相关密钥
