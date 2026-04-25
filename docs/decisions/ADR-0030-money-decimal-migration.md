# ADR-0030: 金额字段全链路 Decimal 迁移 (TD-ARCH-03)

- **状态**：Accepted
- **日期**：2026-04-25
- **决策上下文**：R8 Review C-10 / TECH_DEBT TD-ARCH-03 / SP-01 排期外延伸
- **关联**：ADR-0001 (微信支付)、ADR-0029 (订单过期支付收尾)、SPRINT_PLAN_2026-04-21 P0-2

## 背景

当前所有金额字段使用 SQLAlchemy `Float` + Python `float`：

| 位置 | 字段 | 类型 |
|---|---|---|
| `app/models/order.py` | `Order.price` | `Float` |
| `app/models/payment.py` | `Payment.amount` | `Float` |
| `app/models/order.py` | `SERVICE_PRICES` 常量 | `dict[ServiceType, float]` |
| `app/services/payment_service.py` | refund/prepay 金额参数 | `float` |
| `app/services/providers/payment/base.py` | `PrepayRequest.amount_yuan` / `RefundRequest.{total,refund}_yuan` | `float` |
| `app/schemas/order.py:60` | `PrepayResult.amount` | `float` |

IEEE 754 误差在以下场景已构成实际风险：

1. **退款金额比对**：`refund_amount == order.price` 在某些链路是字符串化后比较，未来若改成数值比较，`299.0 != 298.99999...`。
2. **对账**：和微信支付 `amount.total/refund` (`int` 分) 双向换算 `int(round(x * 100))`，组合金额（套餐、优惠券）一旦累加多次，舍入误差会冒出来。
3. **Wallet 流水**：当前 wallet 余额仅由 orders 即时聚合得出（无独立 Wallet 表），但 `total_income = sum(o.price for o in completed)` 会随订单数线性放大误差。
4. **未来阻塞**：F-08 多次卡 / F-10 优惠券会员体系需要精确金额运算。

## 决策

### 范围（只迁"钱"，不迁"度量"）

✅ **必迁**：
- `Order.price` → `Numeric(10, 2)`
- `Payment.amount` → `Numeric(10, 2)`
- `SERVICE_PRICES` 值 → `Decimal`
- 所有 service / repository / schema 层金额参数与字段 → `Decimal`
- Provider 抽象层 `amount_yuan` / `total_yuan` / `refund_yuan` → `Decimal`

❌ **保持 Float**（非金额）：
- `Hospital.latitude` / `longitude`：地理坐标
- `CompanionProfile.avg_rating`：评分（非货币）
- 限流模块时间戳

### Schema 约束

- 列定义：`Numeric(10, 2)`，最大支持 99,999,999.99，精度 2 位足够（陪诊客单价 < ¥10,000）
- Pydantic：`condecimal(max_digits=10, decimal_places=2, ge=Decimal("0"))`，序列化为 JSON 字符串保留精度（`json_encoders` / `model_config`）
- Decimal 模式：`getcontext().prec` 沿用默认 28；金额运算前显式 `Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`

### Alembic 迁移策略

- 单一 revision：`xxxx_money_to_numeric.py`
- `op.alter_column(... type_=Numeric(10, 2), existing_type=Float, postgresql_using="price::numeric(10,2)")`
- 三张表：`orders.price` / `payments.amount`
- **回滚分支**：downgrade 用 `Float` + `postgresql_using="price::double precision"`；理论上无损（Numeric → Float 可能丢精度但生产数据均为 .00 / .99 这类两位小数）
- 数据回填：不需要——Float 在物理层本就能容纳现有的两位小数值；ALTER 仅更类型

### Provider 边界

- `WechatPaymentProvider` 内部仍按 fen (int) 运算，入参从 Decimal 接：
  ```python
  amount_fen = int((order.amount_yuan * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
  ```
- Mock provider 同步改 Decimal

### 三端协议

JSON 上金额统一以**字符串**传输（`"299.00"`），避免 JS Number 精度被 17-digit 截断 + iOS `Decimal` 反序列化失真。

| 端 | 接收 | 渲染 |
|---|---|---|
| WeChat | `String` → `utils/format.js#parseMoney` 返回 `Number` 仅用于展示 | `formatMoney("299.00") → "¥299.00"` |
| iOS | `Decimal` (Codable via `Decimal.init(string:)`) | `Order.priceText: String` 直接展示 |
| Backend | `Decimal` | Pydantic 序列化 `mode="str"` |

### 兼容性窗口

为不破坏已发布的 iOS / 小程序版本（当前金额都是 number），本次迁移 schema 序列化默认仍输出 number（FastAPI 会把 Decimal 序列化为 number），**只是后端运算与 DB 存储用 Decimal**。下一个 minor 客户端版本（v1.1）切到 string 协议；本 ADR 标记该兼容期为 30 天。

`PrepayResult.amount` / Order 列表响应继续返回 number，但用 Decimal 计算后再 `float()` 输出，**确保进 DB / 进 PSP 之前已是精确值**。

## 备选方案

| 方案 | 否决原因 |
|---|---|
| 全用 int 存 fen | 牵涉所有客户端模型、展示、ts 类型，工作量翻倍；Decimal 已够精确 |
| 仅迁 DB 类型，service 层继续 float | 解决不了运算误差，本质未变 |
| 引入 `py-money` / `dinero` 库 | 抽象成本高，MVP 阶段过度设计 |

## 影响

- 影响文件：~12 后端文件 + 1 alembic 迁移 + 1 wechat 工具方法 + 2 iOS 模型字段
- 测试新增：~8 个 Decimal 边界用例（精度、舍入、序列化、加减、与 fen 互转）
- 全量回归：539 后端 + 146 wechat
- DB 迁移：单 revision，向前向后兼容，无数据回填

## 验收

- [ ] alembic upgrade / downgrade 双向通过 smoke test
- [ ] `pytest` 539+ 全绿，新增 Decimal 用例覆盖 `Order.price` 加减、舍入、Pydantic 序列化
- [ ] `app/services/order.py`、`payment_service.py` 中 grep 不到裸 `float`（数学运算上下文）
- [ ] WeChat `formatMoney` 单测覆盖
- [ ] 文档：`TECH_DEBT.md` TD-ARCH-03 移到 "已解决"

## 后续

- iOS 协议切 string 在下一个 minor（v1.1）；本 ADR 不阻塞
- F-08 多次卡 / F-10 优惠券依赖本 ADR 完成
