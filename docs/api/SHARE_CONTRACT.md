# ADR-0036 §2.7 跨端字段契约闸门 (S2-DEV-004)

家属共享（Top1）引入 **7 个跨端字段**，由后端 / 微信小程序 / iOS 三端共享反序列化。
任何一端静默改字段名 / 类型 / 必填性，会在运行时打挂另一端。本文档说明闸门机制与
**合法升级路径**。

## 1. 七字段（权威定义见 ADR-0036 §2.7）

| 字段 | 类型 | 必填 | 出现 schema |
|---|---|---|---|
| `share_token` | string | ✅ | CreateShareResponse / ShareTokenResponse |
| `share_url` | string | ✅ | 同上 |
| `share_scope` | enum `ShareScope`(`full`/`progress_only`) | ✅ | 多处 |
| `share_expires_at` | datetime(ISO8601) | ✅ | 同上 |
| `share_revoked_at` | datetime? (nullable) | ❌ | 同上 |
| `share_session` | string(JWT) | ✅ | ExchangeSessionResponse |
| `share_active_count` | int | ✅ | CreateShareResponse / ListSharesResponse |

> 伴生字段 `share_session_expires_at`（datetime，必填）一并锚定，避免 TTL 字段被悄悄改类型。

权威指纹冻结在 [`share-contract-baseline.json`](./share-contract-baseline.json)（17 个
`<Schema>.<field>` 锚点，含 type / required / enum / nullable / format）。

## 2. 三端闸门（`.github/workflows/openapi-diff.yml`）

| 端 | 检查 | 失败条件 |
|---|---|---|
| **backend** | `python scripts/extract_share_contract.py --check` 重新抽取 §2.7 契约 → diff baseline | 任意字段名/类型/必填/enum/nullable 漂移 |
| **wechat** | `npm run typecheck`（tsc）校验 `services/*.js` 对字段的引用 | d.ts ↔ 业务代码字段误用 |
| **iOS** | `ShareEndpointContractTests` 反序列化断言（经 `ios-tests.yml`，受 `IOS_CI_ENABLED` 门控 D-039） | 任一字段缺失/类型不符 |

三端任一漂移 → CI fail → develop task 流程兜底打回 in-progress（ADR-0036 §3.6）。

## 3. 合法升级路径（**无人工 force-merge 口**）

字段契约要变（加字段 / 改类型 / 改必填）时：

1. **先改 ADR-0036 §2.7** 字段表，写清动机；
2. PR 需 **双签放行**（产品 + 架构，对齐 Top1 跨端契约红线）；
3. 在**同一个 PR** 内运行：
   ```bash
   cd backend && python scripts/extract_share_contract.py --write
   ```
   重写 `docs/api/share-contract-baseline.json`，把新指纹一并提交；
4. 三端同步更新（微信 d.ts / iOS model）并让各自 CI 绿。

> ⚠️ baseline 必须在 PR 内随 schema 一起移动 —— 不存在「CI 红了手动合」的旁路。
> reviewer 看到 baseline diff 即知契约变更，强制走双签。

## 4. 本地自检

```bash
cd backend
python scripts/extract_share_contract.py            # 打印当前活契约
python scripts/extract_share_contract.py --check    # diff baseline（CI 同款）
python -m pytest tests/test_share_contract_baseline.py -q
```
