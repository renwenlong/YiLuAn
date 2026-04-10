# ADR-0001 微信支付接入方案

- 日期：2026-04-10
- 状态：Accepted
- 参与角色：Arch / Backend / Frontend / QA

## 背景

当前 `pay_order()` 方法直接创建一条 `status="success"` 的 Payment 记录，属于模拟支付。
上线必须接入微信支付 JSAPI（小程序端）和微信支付 Native/H5（iOS 端后续）。

微信支付 v3 API 使用 RSA 签名，回调需要验签。

## 备选方案

### A. 在 OrderService 内直接调用微信支付 SDK
- 优点：改动最小
- 缺点：OrderService 进一步膨胀，支付逻辑与订单逻辑耦合

### B. 抽出独立 PaymentService，作为支付领域的入口
- 优点：边界清晰，支付策略可替换（mock / wechat / stripe）
- 缺点：需要新增文件和改造调用关系

### C. 引入第三方聚合支付平台
- 优点：多支付渠道统一
- 缺点：MVP 阶段过度设计，增加外部依赖

## 决策

**选择方案 B：抽出独立 PaymentService**

## 原因

1. OrderService 已经 450+ 行，继续叠加支付逻辑会失控
2. mock 模式必须保留给测试和开发环境
3. 后续可能扩展到支付宝/Apple Pay，独立服务更易扩展
4. 回调验签、幂等、退款是独立的领域逻辑，不应混入订单状态机

## 设计

### 新增文件
- `backend/app/services/payment_service.py` — 支付服务主入口
- `backend/app/services/payment_wechat.py` — 微信支付 v3 SDK 封装
- `backend/app/api/v1/payment_callback.py` — 支付/退款回调端点（无需 JWT）

### Payment 模型扩展
在 `Payment` 模型增加字段：
- `trade_no` — 微信支付交易号
- `prepay_id` — 预支付交易会话标识
- `refund_id` — 退款单号（退款时）
- `callback_raw` — 回调原始数据（审计用）
- `idempotency_key` — 幂等键

### 流程

#### 下单支付
```
患者点击支付
  → 前端调用 POST /api/v1/orders/{id}/pay
  → PaymentService.create_prepay()
    → 环境=development? → mock 模式，直接返回成功
    → 环境=production? → 调用微信统一下单 API
    → 返回 prepay_id + 签名参数给前端
  → 前端拉起微信支付
  → 用户完成支付
  → 微信回调 POST /api/v1/payments/wechat/callback
  → PaymentService.handle_callback()
    → 验签
    → 幂等检查（trade_no 是否已处理）
    → 更新 Payment 状态
    → 不改变 Order 状态（支付成功只是 "已付款"，不驱动状态机）
```

#### 退款
```
取消订单触发退款
  → PaymentService.create_refund()
    → 环境=development? → mock 模式，直接记录
    → 环境=production? → 调用微信退款 API
  → 微信退款回调
  → PaymentService.handle_refund_callback()
    → 验签 + 幂等 + 更新状态
```

### 关键设计点
1. **环境隔离**：`config.payment_provider` = `mock` / `wechat`，开发和测试走 mock
2. **幂等**：以 `order_id + payment_type` 为幂等键，回调以 `trade_no` 去重
3. **回调端点不需要 JWT**：使用微信签名验证
4. **金额以分为单位**：微信要求整数分，内部统一转换

## 影响

- `OrderService.pay_order()` 改为调用 `PaymentService`
- `OrderService.cancel_order()` 中退款逻辑改为调用 `PaymentService`
- Payment 模型需要 migration 加字段
- 前端需改造支付调用流程
- 需要新增 `wechatpay` Python 依赖

## 后续动作

1. ✅ Phase 1：创建 PaymentService 骨架 + mock provider（本次提交）
2. Phase 2：接入微信支付 v3 SDK（需要商户号等凭证）
3. Phase 3：前端支付流程改造
4. Phase 4：回调联调与测试
