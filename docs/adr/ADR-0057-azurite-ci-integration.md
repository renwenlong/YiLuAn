# ADR-0057: Azurite CI 集成（PREFLIGHT azurite marker 测试上 CI）

- **状态**: Accepted
- **日期**: 2026-06-25
- **决策者**: 魈（架构师），帝君授权改 test.yml
- **关联**: S3-OPS-CI-AZURITE-CONTAINER（develop/P3）/ S3-OPS-CI-AZURITE-CONTAINER-TEST（test/P3）/ S2-DEV-016-PHASE-B-PREFLIGHT-SDK（#357 已 merge，azurite marker 测试已在 main）/ OPS-014（required check 防锁死）

---

## 1. 背景

`S2-DEV-016-PHASE-B-PREFLIGHT-SDK`（PR #357）已 merge，`backend/tests/test_storage_backend_azurite.py` 用真 `azure-storage-blob` SDK 跑 `AzureBlobStorageBackend`，打 `@pytest.mark.azurite`，默认排除（`addopts = -m 'not smoke and not docker and not azurite'`），需 azurite 容器（端口 10000）才跑。

**问题**：这些测试现在**在 main 但 CI 从不跑它们**——default test run 排除 azurite marker，无专门 job 起 azurite 容器。真 SDK 路径回归只能靠本地手动 `pytest -m azurite`，CI 无防护网。

帝君已授权改 `test.yml`（动 CI 配置），触发条件全满足（#357 merged + 授权到位）。

---

## 2. 决策点与方案对比

### 决策点 A：azurite job 该不该纳入 required status check？

| 方案 | 做法 | 优 | 劣 |
|---|---|---|---|
| **A1 纳 required** | azurite job 加进 branch protection 4→5 required | 强制每 PR 验真 SDK 路径 | ❌ **撞 OPS-014 锁死陷阱**：docs-only PR 也得起 azurite 容器；若用 path filter 则 docs PR 变 missing 永久 pending；azurite WORM 不支持（Issue#2648）真验证本就归 REAL smoke，纳 required 是假闸 |
| **A2 不纳 required（informational）** ✅ | azurite 独立 job，PR 可见结果但不阻塞合并 | 不破 OPS-014；docs PR 不受累；真 SDK 回归有 CI 防护网；与"真 WORM 验证归 REAL smoke"分层一致 | azurite job 红了不硬阻断 merge（靠 reviewer 看结果把关） |

**决定：A2**。azurite 是**辅助验证层**（真 SDK 调用 shape 回归），非发布闸。真正的 Azure WORM/immutability 闸是 `S2-DEV-016-PHASE-B-REAL` creds 后的 smoke。把 azurite 纳 required = 用假闸冒充真闸 + 重蹈 OPS-014 覆辙。

### 决策点 B：azurite job 独立 workflow 还是挂 test.yml backend job？

| 方案 | 做法 | 优 | 劣 |
|---|---|---|---|
| **B1 挂 test.yml backend job** | 在现有 backend job 加 service container + azurite step | 复用 backend job 的 checkout/python setup | ❌ backend job 是 required；加 azurite service container 让**所有** backend PR（含不碰 storage 的）都起 azurite 容器；service container 是 job 级，无法 step 级 if 守 → 违 OPS-014「job 永远跑但内部 if 守」精神（service container 起不起没法按 changes 守） |
| **B2 独立 workflow `azurite-ci.yml`** ✅ | 新 workflow，path filter 只在 storage 相关改动触发，job 级起 azurite service container | 隔离干净；只在碰 `storage_backend.py`/azurite 测试时跑；不污染 required job；service container 随 job 起无 OPS-014 矛盾（因为本就不是 required，missing 无害） | 新增一个 workflow 文件 |

**决定：B2**。独立 `azurite-ci.yml`，**因为它不纳 required，可以放心用 path filter**（OPS-014 锁死陷阱只对 required check 成立——non-required job missing 不阻塞合并）。这正是 A2 决策带来的额外好处：不 required → path filter 自由用 → 只在相关改动跑。

### 决策点 C：azurite 不可达时 job 行为？

azurite 测试 module fixture 已自带 skip（不可达时 skip 不 fail）。但 CI job 里我们**主动起 azurite service container**，正常应可达。

**决定**：job 内显式起 azurite service container（GitHub Actions `services:` 块）+ 健康检查等容器就绪 + 跑 `pytest -m azurite`。容器起不来 → job fail（CI 基础设施问题应暴露，非静默 skip）。但因 **non-required**，job fail 不阻塞合并，reviewer 看到红会跟进。

---

## 3. 实施方案（给 developer）

### 3.1 新建 `.github/workflows/azurite-ci.yml`

```yaml
name: Azurite Integration Tests

# 只在 storage 相关改动触发 (non-required, 可安全用 path filter — 不会锁死任何 PR)
on:
  pull_request:
    paths:
      - 'backend/app/services/storage_backend.py'
      - 'backend/tests/test_storage_backend_azurite.py'
      - 'backend/tests/test_storage_backend.py'
      - '.github/workflows/azurite-ci.yml'
  push:
    branches: [main]
    paths:
      - 'backend/app/services/storage_backend.py'
      - 'backend/tests/test_storage_backend_azurite.py'

jobs:
  azurite-integration:
    name: Azurite Integration (informational, non-required)
    runs-on: ubuntu-latest
    services:
      azurite:
        image: mcr.microsoft.com/azure-storage/azurite
        ports:
          - 10000:10000
        # azurite-blob --blobHost 0.0.0.0 让容器外可连
        options: >-
          --health-cmd "nc -z 127.0.0.1 10000 || exit 1"
          --health-interval 5s
          --health-timeout 3s
          --health-retries 10
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: |
          pip install -r backend/requirements.txt
          pip install pytest pytest-asyncio
      - name: Run azurite integration tests
        run: cd backend && python -m pytest -m azurite -v --tb=short
        timeout-minutes: 5
```

> ⚠️ azurite 默认 `azurite-blob` 监听 127.0.0.1，GitHub service container 需 `--blobHost 0.0.0.0` 才能被 job runner 连。若官方 image 默认 entrypoint 不带该参数，需在 `services.azurite` 加 `args` 或换显式 `command`。实施时 developer 验证容器实际可连（连接串 BlobEndpoint=http://127.0.0.1:10000，service container 在 runner 网络里映射到 localhost:10000）。

### 3.2 不动 branch protection

**不**把 `Azurite Integration` 加进 required status checks。保持 4 required（Backend Tests / Docker Build Verification / WeChat Mini Program Tests / Build & Test (iOS Simulator)）不变。

### 3.3 OPS-014 不破验证

- docs-only PR：path filter 不匹配 → `azurite-ci.yml` 不触发 → 因 **non-required**，missing 无害（不阻塞合并）。✅ 不重蹈 OPS-014（OPS-014 陷阱专对 required check）。
- 4 required check 不受任何影响（azurite 是独立 workflow，不进 test.yml 的 needs chain）。

---

## 4. 后果

### 正面
- 真 azure-storage-blob SDK 路径有 CI 回归防护网（之前只本地手动跑）
- 不破 OPS-014，不增 required check，docs PR 零影响
- 与"真 WORM 验证归 REAL smoke"分层清晰：azurite=SDK shape 回归，REAL smoke=真 WORM/immutability

### 负面 / 权衡
- azurite job non-required → 红了不硬阻断 merge，靠 reviewer 看结果把关（可接受：azurite 是辅助层，真闸在 REAL smoke）
- azurite WORM 不支持（Issue#2648），immutability 部分 azurite 测不了（已知，归 REAL smoke）

### 后续
- `S2-DEV-016-PHASE-B-REAL`（creds 后）落地时，与 azurite CI 一起验：azurite 验 SDK shape + REAL smoke 验真 WORM。两层互补。
- 若未来团队判 azurite 回归足够关键要纳 required，需重新评估 OPS-014 兼容（届时要改成 job-永远跑 + step if 守模式，但 service container 起不起的矛盾需先解）。本期决策 non-required。
