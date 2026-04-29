# Provider 抽象接口冻结清单（D-052）

> **冻结起算时间**：2026-04-29
> **冻结依据**：D-052（DECISION_LOG.md）
> **解锁条件**：B-01（微信支付商户号正式接入）或 B-02（阿里云短信正式接入）任一解锁，由 Arch 触发冻结审查
> **变更门槛**：本清单内任何方法签名（参数列表、返回类型、异常约定）的变更，须 **Arch + Backend 双签**，并新增 D-0xx 决议条目

本清单仅约束 **公共抽象方法签名**。具体 provider（`wechat.py`、`mock.py`、`aliyun.py`、`logging_wrapper.py` 等）的内部实现逻辑不受冻结约束。

---

## 1. PaymentProvider —— `backend/app/services/providers/payment/base.py`

冻结起算时间：2026-04-29

### 1.1 高层 API（new high-level API，子类应优先 override）

| # | 方法签名 | 备注 |
| --- | --- | --- |
| 1 | `async def create_order(self, order: OrderDTO) -> dict[str, Any]` | 向 PSP 发起预下单 / 创建交易 |
| 2 | `async def verify_callback(self, headers: dict, body: bytes) -> dict[str, Any]` | 验证并解密回调通知 |
| 3 | `async def refund(self, refund: RefundDTO) -> dict[str, Any]` | 提交退款 |
| 4 | `async def query(self, order: OrderDTO) -> dict[str, Any]` | 查询交易最新状态 |
| 5 | `async def close_order(self, out_trade_no: str) -> dict[str, Any]` | 关闭预下单 |

### 1.2 Legacy API（保留给现有 PaymentService 与测试，签名同样冻结）

| # | 方法签名 | 备注 |
| --- | --- | --- |
| 6 | `async def create_prepay(self, order_number: str, amount_yuan: Decimal, description: str, openid: str \| None = None) -> dict[str, Any]` | 默认委托至 `create_order` |
| 7 | `async def create_refund(self, trade_no: str, refund_id: str, total_yuan: Decimal, refund_yuan: Decimal) -> dict[str, Any]` | 默认委托至 `refund` |

### 1.3 配套 DTO（同纳入冻结，新增字段视为不兼容变更）

- `OrderDTO(order_number: str, amount_yuan: Decimal, description: str = "医路安陪诊服务", openid: str | None = None)`
- `RefundDTO(trade_no: str, refund_id: str, total_yuan: Decimal, refund_yuan: Decimal)`

---

## 2. SMSProvider —— `backend/app/services/providers/sms/base.py`

冻结起算时间：2026-04-29

| # | 方法签名 | 备注 |
| --- | --- | --- |
| 1 | `async def send_otp(self, phone: str, code: str, template_id: str \| None = None) -> SMSResult` | OTP 短信下发，PII 由调用方 / provider 负责脱敏 |
| 2 | `async def send_notification(self, phone: str, template_id: str, params: dict[str, Any] \| None = None) -> SMSResult` | 模板事务 / 通知短信 |

### 2.1 配套 DTO（同纳入冻结）

- `SMSResult(ok: bool, code: str = "ok", message: str = "", provider: str = "", extra: dict[str, Any] = field(default_factory=dict))`

### 2.2 类属性

- `SMSProvider.name: str`（默认 `"base"`，子类按惯例覆盖）

---

## 3. 不在冻结范围内（可自由迭代）

- `backend/app/services/providers/payment/wechat.py` 内部实现
- `backend/app/services/providers/payment/mock.py`、`factory.py`
- `backend/app/services/providers/sms/aliyun.py`、`mock.py`、`factory.py`、`logging_wrapper.py`、`rate_limit.py`
- 调用方（`PaymentService`、SMS 业务层）的内部逻辑
- 新增 provider（在不修改基类签名的前提下）

---

## 4. 变更流程

1. 提出变更 → 在 PR 描述中注明 "影响 D-052 冻结接口"
2. Arch + Backend 双签评审
3. 评审通过后在 `docs/DECISION_LOG.md` 追加 D-0xx 条目，引用 D-052
4. 同步更新本清单与 ADR-0028（如需）
5. 合并并通知所有 Provider 调用方

---

_本清单与 D-052 同生命周期；解锁条件触发后由 Arch 主导整体复审。_
