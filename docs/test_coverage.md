# 后端测试覆盖率报告

## 本次更新（B1-B4 后）

| 模块 | 旧覆盖率 | 新覆盖率 | 提升 |
|------|----------|----------|------|
| `app/services/order.py` | 34% | 88% | +54pp |
| `app/api/v1/ws.py` | 15% | 73% | +58pp |
| `app/services/admin_audit.py` | 0% | 40% | +40pp |
| **总覆盖率** | **71.9%** | **80.0%** | **+8.1pp** |

测试总数从 470 → 539（+69 个测试用例，来自 B1-B4 批次）。

## 元信息

| 项目 | 值 |
|------|-----|
| 报告生成时间 | 2026-04-20 |
| Python 版本 | 3.12.10 |
| 测试框架 | pytest + pytest-asyncio |
| 测试总数 | 539 passed + 5 deselected + 1 xfailed = 545 collected |
| 运行耗时 | ~68s |

## 总览

| 指标 | 值 |
|------|-----|
| 总语句数 (Statements) | 3,872 |
| 未覆盖语句 (Missed) | 782 |
| **总覆盖率** | **80.0%** |

> 注：本次仅统计行覆盖率（line coverage），未启用分支覆盖率。

## 模块覆盖率排名

### Top 5 覆盖率最高（>10 语句）

| 模块 | 语句数 | 未覆盖 | 覆盖率 |
|------|--------|--------|--------|
| `app/api/v1/companions.py` | 31 | 0 | 100% |
| `app/api/v1/patients.py` | 13 | 0 | 100% |
| `app/api/v1/router.py` | 33 | 0 | 100% |
| `app/core/pii.py` | 24 | 0 | 100% |
| `app/core/security.py` | 20 | 0 | 100% |

### Top 5 覆盖率最低

| 模块 | 语句数 | 未覆盖 | 覆盖率 |
|------|--------|--------|--------|
| `app/repositories/hospital.py` | 72 | 49 | 32% |
| `app/services/admin_audit.py` | 42 | 25 | 40% |
| `app/services/sms.py` | 108 | 62 | 43% |
| `app/services/review.py` | 53 | 28 | 47% |
| `app/services/wechat.py` | 15 | 8 | 47% |

## 覆盖空白：完全未覆盖的文件

无。所有文件均已有部分覆盖。

## 改进建议

1. **`app/repositories/hospital.py`（32% → 目标 70%）** — 最低覆盖模块（72 语句，49 未覆盖）。医院搜索、分页、筛选等查询路径未测试，建议补充搜索关键词、空结果、分页边界用例。

2. **`app/services/admin_audit.py`（40% → 目标 80%）** — B1 已覆盖基本 token 鉴权和审计日志创建，但仍有 25 条语句未覆盖。建议补充查询审计日志列表、筛选条件、分页等场景。

3. **`app/services/sms.py`（43% → 目标 75%）** — 短信服务的错误处理路径（发送失败、频率限制触发、provider 切换）需要更多测试。

4. **`app/services/review.py`（47% → 目标 75%）** — 评价服务的边界条件（重复评价、无效订单评价、评分范围校验）需补充测试。

5. **`app/services/wechat.py`（47% → 目标 80%）** — 微信服务代码量小（15 语句）但覆盖率低，建议补充 code2session 调用的成功与失败场景。

## 附录

- HTML 覆盖率报告：`backend/.coverage_html/index.html`（本地浏览器打开查看详细行级覆盖）
- JSON 数据文件：`backend/.coverage.json`
