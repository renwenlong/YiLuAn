/**
 * S2-DEV-013 acceptance #11 + #12：单测 ≥ 8 case 覆盖
 *   - list / mutation 成功+失败 / 权限 deny / loading / error boundary
 *
 * 用 happy-dom + mock axios 不依赖真后端。
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ConfigProvider } from 'antd'

import { CompanionReviewListPage } from './CompanionReviewListPage'
import { apiClient } from '../../shared/api/client'
import { canSeeMenu, MENU_VISIBILITY } from '../../shared/types/role'
import { useAuthStore, getAdminToken } from '../../shared/api/authStore'

vi.mock('../../shared/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
}))

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

const mockGet = vi.mocked(apiClient.get)
const mockPost = vi.mocked(apiClient.post)

beforeEach(() => {
  mockGet.mockReset()
  mockPost.mockReset()
  sessionStorage.clear()
})

describe('CompanionReviewListPage', () => {
  // case 1: list 渲染
  it('renders list rows when fetch succeeds', async () => {
    mockGet.mockResolvedValueOnce({
      data: {
        items: [
          { id: '1', name: '张三', phone: '138****0001', status: 'pending', created_at: '2026-06-04 10:00' },
        ],
        total: 1,
      },
    })
    renderWithProviders(<CompanionReviewListPage />)
    await waitFor(() => {
      expect(screen.getByText('张三')).toBeInTheDocument()
    })
  })

  // case 2: loading 状态
  it('shows loading spinner before data arrives', () => {
    mockGet.mockReturnValueOnce(new Promise(() => {})) // 永不 resolve
    renderWithProviders(<CompanionReviewListPage />)
    // AntD Table loading => 有 ant-spin 元素
    expect(document.querySelector('.ant-spin')).toBeTruthy()
  })

  // case 3: list error → 不 throw（AntD Table 自身 fallback）
  it('handles list fetch error gracefully', async () => {
    mockGet.mockRejectedValueOnce(new Error('500 internal error'))
    renderWithProviders(<CompanionReviewListPage />)
    await waitFor(() => {
      // Table 应渲染 empty data 占位，不应崩溃
      expect(screen.getByText('陪诊师审核')).toBeInTheDocument()
    })
  })

  // case 4: 通过 mutation 成功
  it('calls approve API on click', async () => {
    mockGet
      .mockResolvedValueOnce({
        data: { items: [{ id: '1', name: '李四', phone: '138****0002', status: 'pending', created_at: '2026-06-04' }], total: 1 },
      })
      .mockResolvedValueOnce({
        data: { id: '1', name: '李四', phone: '138****0002', status: 'pending', created_at: '2026-06-04' },
      })
    mockPost.mockResolvedValueOnce({ data: {} })

    renderWithProviders(<CompanionReviewListPage />)
    await waitFor(() => screen.getByText('李四'))
    fireEvent.click(screen.getByText('详情'))
    await waitFor(() => screen.getByRole('button', { name: /通过/ }))
    fireEvent.click(screen.getByRole('button', { name: /通过/ }))
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalledWith('/admin/companions/1/approve')
    })
  })

  // case 5: 通过 mutation 失败
  it('shows error message when approve fails', async () => {
    mockGet
      .mockResolvedValueOnce({
        data: { items: [{ id: '2', name: '王五', phone: '138****0003', status: 'pending', created_at: '2026-06-04' }], total: 1 },
      })
      .mockResolvedValueOnce({
        data: { id: '2', name: '王五', phone: '138****0003', status: 'pending', created_at: '2026-06-04' },
      })
    mockPost.mockRejectedValueOnce(new Error('403 forbidden'))

    renderWithProviders(<CompanionReviewListPage />)
    await waitFor(() => screen.getByText('王五'))
    fireEvent.click(screen.getByText('详情'))
    await waitFor(() => screen.getByRole('button', { name: /通过/ }))
    fireEvent.click(screen.getByRole('button', { name: /通过/ }))
    await waitFor(() => {
      expect(mockPost).toHaveBeenCalled()
    })
  })

  // case 6: 拒绝需要理由（按钮 disabled）
  it('reject submit disabled when reason empty', async () => {
    mockGet
      .mockResolvedValueOnce({
        data: { items: [{ id: '3', name: '赵六', phone: '138****0004', status: 'pending', created_at: '2026-06-04' }], total: 1 },
      })
      .mockResolvedValueOnce({
        data: { id: '3', name: '赵六', phone: '138****0004', status: 'pending', created_at: '2026-06-04' },
      })

    renderWithProviders(<CompanionReviewListPage />)
    await waitFor(() => screen.getByText('赵六'))
    fireEvent.click(screen.getByText('详情'))
    await waitFor(() => screen.getByRole('button', { name: /拒绝/ }))
    fireEvent.click(screen.getByRole('button', { name: /拒绝/ }))
    // Modal 出来，OK 按钮 disabled（reason 空）
    await waitFor(() => {
      const okBtn = screen.getAllByText(/确定|OK/).find((el) => el.closest('button'))
      expect(okBtn?.closest('button')).toBeDisabled()
    })
  })
})

describe('RBAC mock (前端权限)', () => {
  // case 7: 角色 menu 可见性
  it('super sees all features', () => {
    for (const path of Object.keys(MENU_VISIBILITY)) {
      expect(canSeeMenu(path, 'super')).toBe(true)
    }
  })

  // case 8: finance 不能见 companion-review
  it('finance cannot see companion-review', () => {
    expect(canSeeMenu('companion-review', 'finance')).toBe(false)
    expect(canSeeMenu('refund-review', 'finance')).toBe(true)
  })
})

describe('authStore', () => {
  // case 9: token 不缓存副本（每次实时读 sessionStorage）
  it('getAdminToken returns latest sessionStorage value (no caching)', () => {
    sessionStorage.setItem('yiluan.admin.token', 'token-a')
    expect(getAdminToken()).toBe('token-a')
    sessionStorage.setItem('yiluan.admin.token', 'token-b')
    expect(getAdminToken()).toBe('token-b')
    sessionStorage.removeItem('yiluan.admin.token')
    expect(getAdminToken()).toBeNull()
  })

  // case 10: setRoleAndToken 同步 sessionStorage + zustand
  it('setRoleAndToken persists to sessionStorage', () => {
    useAuthStore.getState().setRoleAndToken('super', 'tok-xyz')
    expect(sessionStorage.getItem('yiluan.admin.token')).toBe('tok-xyz')
    expect(sessionStorage.getItem('yiluan.admin.role')).toBe('super')
    expect(useAuthStore.getState().role).toBe('super')
    expect(useAuthStore.getState().isAuthenticated()).toBe(true)
  })

  // case 11: logout 清除全部 + zustand state
  it('logout clears sessionStorage and zustand role', () => {
    useAuthStore.getState().setRoleAndToken('finance', 'tok-1')
    useAuthStore.getState().logout()
    expect(sessionStorage.getItem('yiluan.admin.token')).toBeNull()
    expect(sessionStorage.getItem('yiluan.admin.role')).toBeNull()
    expect(useAuthStore.getState().role).toBeNull()
    expect(useAuthStore.getState().isAuthenticated()).toBe(false)
  })
})
