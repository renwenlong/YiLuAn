# admin-v2 Testing Guide

> 测试 jsdom / happy-dom + Vitest + React Testing Library + AntD 5 组件的实战指南。
>
> 来源：S2-DEV-013 PR-D follow-up 调通 3 skip case 时发现的根因（PR #171 commit `8d494ef`）。
>
> 对后续 Phase 2-9 所有 admin-v2 feature page 单测可直接复用。

---

## 1. 基础栈

```
vitest + happy-dom (or jsdom)
@testing-library/react      → render / screen / waitFor / fireEvent / cleanup
@testing-library/jest-dom   → toBeInTheDocument / toBeDisabled
vi.mock                     → axios apiClient mock
```

setup 在 `src/test-setup.ts`（极简，仅 import jest-dom）。

---

## 2. 必须遵守的 4 条 setup 模板

### 2.1 用 `vi.mock` mock `apiClient` 整体

```ts
vi.mock('../../shared/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    // axios.create() 实例自带 interceptors，mock 必须包含否则 import 时崩
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
}))

const mockGet = vi.mocked(apiClient.get)
const mockPost = vi.mocked(apiClient.post)
```

### 2.2 `renderWithProviders` 每次新建 QueryClient

```tsx
function renderWithProviders(ui: React.ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <BrowserRouter>
      <ConfigProvider>
        <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
      </ConfigProvider>
    </BrowserRouter>,
  )
}
```

`retry: false` 关键：默认 react-query 失败重试 3 次，单测里 mockRejectedValue 触发等不到错误态。

### 2.3 必须 `afterEach` cleanup + 清 portal 残留

```ts
beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  sessionStorage.clear()
})

afterEach(() => {
  cleanup()
  // AntD Drawer / Modal portal 残留 document.body 直接挂的 div，必须显式清
  document.body.innerHTML = ''
})
```

**⚠️ 缺这条会导致跨 test DOM 残留**：case N 的 `getByText('张三')` 会命中 case N-1 还没卸载的 row，selector `.closest('button')` 拿到错的 button → click 后什么都不发生 → 看起来像"drawer 不响应"，实际是 click 了不该 click 的元素。

### 2.4 mock list + detail + 子资源 三段式

PR-E2 后 drawer 走 `useQuery(['companion-detail', id])` 真请求 detail endpoint。一个完整的"点击详情 → drawer 展开"流程涉及：

```ts
mockGet
  .mockResolvedValueOnce({ data: { items: [...], total: 1 } })   // 1) list
  .mockResolvedValueOnce({ data: { id, ...14 fields } })          // 2) detail
  .mockResolvedValueOnce({ data: new Blob([...], {...}) })        // 3) (optional) cert image blob
```

顺序不能错。少一段 → 该次 axios call 返回 undefined → `.data` 解构崩。

---

## 3. AntD 组件 5 个常见坑（必读）

### 3.1 中文 2 字按钮自动加空格

```tsx
<Button>通过</Button>
```

渲染为：

```html
<button><span>通 过</span></button>
```

这是 AntD `<Button>` 内置 chinese-2 space behavior（不是 CSS letter-spacing 是真插入半角空格）。

**错误**：
```ts
screen.getByRole('button', { name: /通过/ })  // ❌ 不匹配 "通 过"
```

**正确**：
```ts
screen.getByRole('button', { name: /通\s*过/ })  // ✅ 容忍空格
screen.getByRole('button', { name: /拒\s*绝/ })
```

### 3.2 Drawer / Modal 是 portal — 不在测试 container 里

`render()` 返回的 `container` 只是 list 那部分。Drawer mount 在 `document.body` 下另一个 sibling div。

- 用 `screen.*` 全局查询（不要 `container.querySelector`）
- `findByText` / `findByRole` 默认在 `document.body` 找，OK
- afterEach 必须清 `document.body.innerHTML`（见 2.3）

### 3.3 Drawer extra slot 渲染条件

```tsx
extra={detailQ.data && (<Space><Button>通过</Button>...</Space>)}
```

extra 只在 detailQ.data 就绪后才渲染。测试要：

```ts
fireEvent.click(detailButton)
await waitFor(() => expect(mockGet).toHaveBeenCalledWith('/admin/companions/1'))
// 再 findByRole 等 detail 加载完 + extra mount
const approveBtn = await screen.findByRole('button', { name: /通\s*过/ }, { timeout: 3000 })
```

直接 `getByRole` 会立即抛（drawer 还没 mount extras）。用 `findByRole` 自带 waitFor + 加 timeout。

### 3.4 Modal OK button 用 `okButtonProps.disabled`

```tsx
<Modal okButtonProps={{ disabled: !reason.trim() }}>
```

测试拿 Modal OK button（不是抽屉里的"拒绝"按钮）：

```ts
const candidates = screen.getAllByRole('button').filter((btn) => {
  const txt = btn.textContent?.replace(/\s/g, '') ?? ''
  return txt === '确定' || txt === 'OK'
})
const modalOk = candidates.find((btn) => btn.closest('.ant-modal'))
expect(modalOk).toBeDisabled()
```

key：用 `.closest('.ant-modal')` 区分 modal footer 的 OK 和页面其他同名 button。

### 3.5 AntD Table column render 里的 Button selector

Table cell 里的 `<Button>` 也会 chinese-2 加空格。`getByText` 用函数 matcher 兜底：

```ts
fireEvent.click(
  screen.getByText((text) => text.replace(/\s/g, '') === '详情').closest('button')!,
)
```

---

## 4. fireEvent vs userEvent — 不用 userEvent

| | fireEvent | userEvent |
|---|---|---|
| 速度 | 快 | 慢 5-10x |
| 真实性 | 直接 dispatch event | 模拟键盘 + 焦点 + delay |
| AntD 适配 | ✅ 实测 OK | ⚠️ happy-dom 下偶发 race |
| 单测目标 | 验 click 后 mutation 触发 | 验真实用户输入流程 |

**结论**：单测用 `fireEvent.click`。E2E 才用 userEvent。

PR-D 调试期间试过 userEvent，反而 race 更多。

---

## 5. happy-dom vs jsdom — 都行

| | happy-dom | jsdom |
|---|---|---|
| 速度 | 1.5-2x 快 | baseline |
| AntD Drawer/Modal | ✅ | ✅ |
| AntD Image preview | ⚠️ 需 `URL.createObjectURL` stub | 同 |

PR-D 调试**实测两者都能跑通**所有 12 case。当前 admin-v2 用 happy-dom（vite.config.ts `test.environment = 'happy-dom'`），不需要升级 jsdom，也不需要换 jsdom → happy-dom。

**根因复盘**：S2-DEV-013 PR-A 留 skip case 时的 TODO 写"可能需 happy-dom 升级 / fireEvent.click 换 userEvent"，**实际根因不是 dom 引擎**，是：
1. 缺 `cleanup()` 跨 test DOM 残留（§2.3）
2. AntD Button 中文 2 字加空格 selector 不匹配（§3.1）

**经验**：碰到测试"按钮找不到"，先 dump 完整 DOM（`DEBUG_PRINT_LIMIT=100000 npm test`）确认是 selector 问题还是 mount 问题，再决定要不要换 dom 引擎。

---

## 6. URL.createObjectURL stub（cert image blob 类）

happy-dom 不实现 `URL.createObjectURL`。fetch + blob URL 流程（ADR-0044 r1 §4.2 双闸）需要 stub：

```ts
if (typeof URL.createObjectURL !== 'function') {
  (URL as unknown as { createObjectURL: (b: Blob) => string }).createObjectURL = () =>
    'blob:mock-cert-image'
}
if (typeof URL.revokeObjectURL !== 'function') {
  (URL as unknown as { revokeObjectURL: (u: string) => void }).revokeObjectURL = () => {}
}
```

然后断言：

```ts
const img = screen.getByAltText('陪诊师证件图预览') as HTMLImageElement
expect(img.src).toMatch(/^blob:/)
```

---

## 7. CI 集成

`Build & Test (admin-v2)` GitHub Actions job（`.github/workflows/test.yml`）：

```yaml
- run: npm ci
- run: npm test -- --run    # vitest run mode
- run: npm run build         # tsc + vite build, 验产物
```

pre-push hook（仓库根）也跑 `npm test --run` admin-v2 子项。**本机 npm 环境必须可用**，否则 push 会被 hook 拦。

---

## 8. 复用清单（Phase 2-9 feature page checklist）

新 feature page 写单测 copy-paste：

- [ ] `vi.mock('../../shared/api/client', ...)` 含 `interceptors`
- [ ] `renderWithProviders` 含 `BrowserRouter + ConfigProvider + QueryClientProvider`
- [ ] `beforeEach { mockReset + sessionStorage.clear }` + `afterEach { cleanup + document.body.innerHTML = '' }`
- [ ] mock 三段式：list → detail → 子资源
- [ ] selector 用 `/通\s*过/`、`/拒\s*绝/` 容忍 AntD 2 字按钮空格
- [ ] drawer extra 等 `findByRole` + `timeout: 3000`
- [ ] Modal OK button 用 `.closest('.ant-modal')` 限定
- [ ] cert/avatar image blob 流加 `URL.createObjectURL` stub
- [ ] `npm test --run` 12+ case 全过 + 0 skipped
- [ ] `npm run build` PASS

---

## 9. 出处

- S2-DEV-013 PR-A 单测骨架（8 RBAC + authStore case）
- S2-DEV-013 PR-E2 cert image fetch+blob URL 双闸（case 4）
- **S2-DEV-013-FOLLOWUP PR-D 3 skip case 调通 + 根因复盘** ← 本文档源
  - PR #171 commit `8d494ef`
  - 魈 review approve `4620283021` 评价："根因分析价值大于 acceptance 本身"

---

## 10. 维护

后续 feature page 单测发现新的 AntD 坑或 happy-dom 限制，追加到 §3 / §6。
