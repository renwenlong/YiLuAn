# 魈 — S1-REQ-001 Review 意见

**结论**：✅ **通过**。产出质量超预期，建议直接进入 Owner 验收。

---

## 一、整体评价

汇总稿不是拼接稿，凝光做了实质性的视角统一和分级归并——38 项建议跨 UI/产品/架构/测试四个域，按"产品价值 × 紧急度"重排序，Top3 战略推荐 + Sprint 排期到位。**这是 PM 应该交的活，不是材料的二次搬运**。

特别认可两点：
- **品牌色笔误纠正（`#1890FF` 而非橙色）+ polish-backlog 虚假完成审计**——这两项是流程信任问题，不查出来会让团队继续在"以为做了"的状态下迭代
- **三个 P0 架构 bug 没有被产品视角稀释掉**——P0-04/05/06 显式保留，且明确"任何战略迭代都不能跳过这三项"

---

## 二、Sprint 排期评审（重点请审项之一）

**结论**：W19-W23 五个 Sprint 排期**基本合理**，1 项调整建议。

| Sprint | 凝光排期 | 我的意见 |
|---|---|---|
| W19 稳生产+启战略 | 11 项 P0 全并行 + 三战略 PRD/ADR | ⚠️ **调整**：11 项 P0 全并行不现实。建议拆为「W19A 安全收口」+「W19B 战略启动」并行两条线，详见下方 |
| W20 战略 Round 1 | Top1 + Top3 MVP 上线 | ✅ 合理 |
| W21 战略 Round 2 + 测试 | Top2 保险 + P1 测试体系 | ✅ 合理 |
| W22 B 端启动 + UI 系统化 | P1-02/03 + UI 系统化 | ✅ 合理 |
| W23+ P2 backlog | — | ✅ 合理 |

**W19 拆分建议**（不改总工作量，只重排优先级）：

```
W19 必须出口（hard stop）：
  线 A（稳生产，胡桃+刻晴）：
    P0-04 outbound 熔断修复 + 测试重写
    P0-05 iOS APIClient Task 缓存
    P0-06 record_callback_or_skip 空 tx_id 拒收
    P0-07 资金 contract test 入 release gate
    P0-11 admin-h5 默认 token 删除
  线 B（启战略，凝光+我+胡桃）：
    Top1/Top2/Top3 PRD + ADR
    
W19 可顺延到 W20（不阻塞上线）：
    P0-08 iOS CreateOrderView 迁 DesignSystem
    P0-09 微信组件层 token 化
    P0-10 polish-backlog 真采纳
```

**理由**：UI 类 P0（08/09/10）严重度是"品牌一致性"和"流程信任"，**不构成上线安全风险**，可让线 A 全力收口，避免战线过宽导致都没收住。

---

## 三、Top3 战略项技术可行性评审（重点请审项之二）

### Top1 家庭陪诊家属端
- ✅ **技术可行**。WS Pub/Sub 已落地（ADR-0031）、OrderService 状态机干净，加一个 `OrderShareToken` 模型 + 只读 WS 通道即可。
- ⚠️ **需 ADR**：分享链接的鉴权模型（无注册访客 vs 微信静默授权）、AI 摘要的隐私边界（处方/检查单上传是否需要患者二次确认）。我来起 **ADR-0036 家庭陪诊共享授权模型**。
- 工作量评估：MVP 1 个 Sprint **可达成**（后端 ~3d / 小程序 ~3d / iOS ~3d 并行）。

### Top2 双向保险 + 电子合同
- ✅ **技术可行，但商务依赖关键路径**。保险 API 对接技术成本低（webhook + 保单号字段），核心瓶颈在众安/平安产险商务谈判 2-4 周。
- ⚠️ **需 ADR**：保单失败时订单是否阻塞？建议"先下单后投保 + 投保失败异步重试 + 失败告警人工介入"，不阻塞主流程。我来起 **ADR-0037 保险投保异步化与失败补偿**。
- ⚠️ **新 outbound 通道**：保险 API 调用必须走修复后的 `outbound_call` 装饰器（这就是为什么 P0-04 必须先修——保险接入会把熔断器问题放大到金钱路径）。

### Top3 AI 就诊准备包
- ✅ **技术可行**。最简单的一项，纯异步任务 + DeepSeek API + PDF 生成。
- ⚠️ **需 ADR**：AI 输出的医疗合规边界——"报告解读"必须显性免责声明 + 禁止给出诊断/用药建议。我来起 **ADR-0038 AI 输出医疗合规护栏**。
- 成本控制建议：Token 用量按订单/天双维度做 Prometheus counter + 日预算硬上限，防 API 滥用。

---

## 四、架构 P0 三项纳入 W19 必修

✅ **完全同意**。我已独立验证 `utils/outbound.py:128-178`：
- half-open 一次 success 即 closed —— 真 bug
- httpx.HTTPError/RequestError 不在 retry 白名单 —— 真 bug
- CB open 后 retry loop 抛 RetryableError 但**未 record_failure**，attempt#1#2 退化为无 sleep 空转，浪费 2 个 retry slot —— 真 bug

修复路径（给胡桃）：
1. `CircuitBreaker` 增加 `_half_open_success_count`，要求连续 N 次（建议 N=3）成功才回 CLOSED；half-open 期间任何一次失败立即 OPEN 并 reset 计时
2. `outbound_call` retry 循环中 `cb.allow_request() == False` 时**直接 raise，不进入下一次 attempt**，避免空转
3. except 白名单加 `httpx.HTTPError`，并按 4xx（NonRetryable）/ 5xx + 网络错（Retryable）分流
4. 配套测试：half-open 行为、httpx 错路径、CB 状态机全转换

这三处修完单独走一个 **ADR-0026 修订版**（或新建 ADR-0039 outbound 装饰器修订），把状态机和 retry/CB 交互写清楚。

---

## 五、产品视角小建议（非阻塞）

- **Top1 落地页文案建议**："让在外地的你，也在妈妈的诊室里"——这种家庭情绪锚定，比"实时同步"功能描述转化率更高（凝光自己定）
- **Top2 保险卖点**：建议在下单页显示"本次服务包含 ¥50 万意外险（保费由平台承担）"，不展示"保费 ¥3-5"成本——把成本转化为信任溢价
- **P2-08 admin-h5 重构**：建议尽快决策长期投入与否。当前纯 HTML/JS 加 token 暴露问题（P0-11 只是创可贴），真正运营起来会被审计/合规反复追问。建议 Q3 启动 admin-v2（Next.js + RBAC）

---

## 六、不采纳/调整项

无。全部采纳。

---

**Review 完成时间**：2026-05-28
**Reviewer**：魈（架构师）
**下一步**：等刻晴的测试视角 review，齐意见后凝光 → Owner 验收
