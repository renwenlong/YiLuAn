# 测试出网防线

`tests/network_guard.py` 在根 `conftest.py` 导入时安装进程级 socket/DNS
拦截。pytest Python 进程默认只能连接：

- `localhost`
- `127.0.0.0/8`
- `::1`
- Unix domain socket（不出主机）

非 loopback DNS/TCP/UDP 会抛 `OutboundNetworkBlockedError`，提示
“该用例需 mock 外部调用”。防线在测试模块 collection/import 前安装，并由
`pytest_runtest_protocol` 覆盖 session/function fixture setup、test body 和
teardown。只构造 `httpx.Request(...)` 不会创建 socket，不受影响。

## 豁免机制

仅在测试确实需要访问真实外网、且 mock 无法满足验收时使用：

```python
@pytest.mark.allow_network
def test_explicit_external_integration():
    ...
```

申请豁免必须在本文件“当前豁免清单”登记：完整 nodeid、目标域名/IP、理由、
owner、PM 审核记录。未登记的 marker 使用视为违规。

### 当前豁免清单

**空。** 当前仓库没有允许真实外网的 pytest 用例。

## subprocess 边界（AC#7）

该防线是 Python 进程内 monkeypatch，**不会跨 `exec` 继承到** `curl`、`wget`、
另一个 Python 或容器进程，不能宣称已覆盖 subprocess。现有测试树通过
`test_no_external_url_or_curl_in_test_subprocess_commands` 静态扫描直接写入
`subprocess.*` 调用的 `curl` / `wget` / 非 loopback URL；当前扫描结果为空。
动态拼接命令无法被静态分析完全证明，新增 subprocess 测试仍须 code review。

`test_curl_subprocess_boundary_is_explicit_and_loopback_still_works` 仅让 curl 访问
测试进程临时监听的 `127.0.0.1`，用于证明这条边界，不是外网豁免。

## 验证矩阵

- `tests/test_network_guard.py`：function body、module collection/import、session
  fixture setup、fixture teardown、DNS、IPv4/IPv6 loopback、httpx Request 构造、
  subprocess/curl 边界及空豁免清单守卫。
- `tests/test_coverage_boost_w18.py`、`tests/test_wechatpay_outbound_classify.py`、
  `tests/test_wechatpay_query_close.py`：外部 provider mock 与安全 Request 构造。
- 默认测试集、真 PostgreSQL smoke、Azurite、docker marker 和 required CI 必须
  分开报告；默认 `pytest` 排除了后三类，不能用它冒充全覆盖。
