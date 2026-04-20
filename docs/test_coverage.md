# 后端测试覆盖率报告

## 元信息

| 项目 | 值 |
|------|-----|
| 报告生成时间 | 2026-04-20 |
| Python 版本 | 3.12.10 |
| 测试框架 | pytest + pytest-asyncio |
| 测试总数 | 470 passed + 5 deselected + 1 xfailed = 476 collected |
| 运行耗时 | ~54s |

## 总览

| 指标 | 值 |
|------|-----|
| 总语句数 (Statements) | 3,835 |
| 未覆盖语句 (Missed) | 1,078 |
| **总覆盖率** | **71.9%** |

> 注：本次仅统计行覆盖率（line coverage），未启用分支覆盖率。

## 模块覆盖率排名

### Top 5 覆盖率最高（>10 语句）

| 模块 | 语句数 | 未覆盖 | 覆盖率 |
|------|--------|--------|--------|
| `app/api/v1/companions.py` | 31 | 0 | 100.0% |
| `app/api/v1/patients.py` | 13 | 0 | 100.0% |
| `app/api/v1/router.py` | 33 | 0 | 100.0% |
| `app/core/pii.py` | 24 | 0 | 100.0% |
| `app/core/security.py` | 20 | 0 | 100.0% |

### Top 5 覆盖率最低

| 模块 | 语句数 | 未覆盖 | 覆盖率 |
|------|--------|--------|--------|
| `app/services/admin_audit.py` | 11 | 11 | 0.0% |
| `app/api/v1/ws.py` | 144 | 123 | 14.6% |
| `app/repositories/hospital.py` | 72 | 49 | 31.9% |
| `app/services/order.py` | 290 | 192 | 33.8% |
| `app/services/sms.py` | 108 | 62 | 42.6% |

## 覆盖空白：完全未覆盖的文件

| 文件 | 语句数 |
|------|--------|
| `app/services/admin_audit.py` | 11 |

## 改进建议

1. **`app/services/order.py`（34% → 目标 70%）** — 这是最大的低覆盖文件（290 语句，192 未覆盖）。应补充订单取消、退款、超时过期等状态转换的测试用例，以及边界条件（重复操作、无效状态转换）。

2. **`app/api/v1/ws.py`（15% → 目标 50%）** — WebSocket 端点几乎无覆盖。建议使用 `httpx` 或 `websockets` 测试客户端模拟连接、消息收发、心跳超时、异常断开等场景。

3. **`app/repositories/hospital.py`（32% → 目标 70%）** — 医院仓库的搜索、分页、筛选等查询路径未测试。补充搜索关键词、空结果、分页边界的用例。

4. **`app/services/sms.py`（43% → 目标 75%）** — 短信服务的错误处理路径（发送失败、频率限制触发、provider 切换）需要更多测试。

5. **`app/services/admin_audit.py`（0% → 目标 80%）** — 完全无覆盖。虽然代码量小（11 语句），但作为审计功能应确保正确性，建议补充基本的单元测试。

## 附录

- HTML 覆盖率报告：`backend/.coverage_html/index.html`（本地浏览器打开查看详细行级覆盖）
- JSON 数据文件：`backend/.coverage.json`
