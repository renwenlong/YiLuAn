/**
 * Admin auth store (S2-DEV-013 / ADR-0042)
 *
 * 关键设计（胡桃 ADR-0042 review §5.1 第 2 项落实）：
 * - **不缓存 token 副本**：每次 API request 现读 sessionStorage
 *   （getter 实时返回，不存进 zustand state）
 * - 监听 storage event 同步 v1 logout（v1 改 sessionStorage 时 v2 React Query 失效）
 * - sessionStorage key 与 v1 同源：`yiluan.admin.token`
 */
import { create } from 'zustand'

import { AdminRole } from '../types/role'

const TOKEN_KEY = 'yiluan.admin.token'
const ROLE_KEY = 'yiluan.admin.role'  // v2 新增（v1 没有，单独维护）

export interface AuthState {
  /** 当前角色（v2 mock，前端选）。token 不存这里 — 实时读 sessionStorage。 */
  role: AdminRole | null
  setRoleAndToken: (role: AdminRole, token: string) => void
  logout: () => void
  /** 实时检查（每次调用现读 sessionStorage，不缓存副本） */
  isAuthenticated: () => boolean
}

export const useAuthStore = create<AuthState>((set) => ({
  role: (sessionStorage.getItem(ROLE_KEY) as AdminRole | null) ?? null,

  setRoleAndToken: (role, token) => {
    sessionStorage.setItem(TOKEN_KEY, token)
    sessionStorage.setItem(ROLE_KEY, role)
    set({ role })
  },

  logout: () => {
    sessionStorage.removeItem(TOKEN_KEY)
    sessionStorage.removeItem(ROLE_KEY)
    set({ role: null })
  },

  isAuthenticated: () => !!sessionStorage.getItem(TOKEN_KEY),
}))

/**
 * sessionStorage cross-tab sync (acceptance #9 第二项)
 *
 * 当 v1 admin-h5 在同源 tab 改了 yiluan.admin.token （比如 logout），
 * v2 React tree 通过 storage event 监听到 → 重新 hydrate role + 失效 React Query
 *
 * 调用方：App 顶层 useEffect 注册一次。
 */
export function subscribeToSessionStorageSync(
  onTokenChange: (newToken: string | null) => void,
): () => void {
  function handler(e: StorageEvent) {
    if (e.key === TOKEN_KEY) {
      onTokenChange(e.newValue)
      // 同步 zustand state（role 跟着 token 走）
      if (!e.newValue) {
        useAuthStore.getState().logout()
      }
    }
  }
  window.addEventListener('storage', handler)
  return () => window.removeEventListener('storage', handler)
}

/** 读 token（API client / axios interceptor 用）。每次现读，不缓存。 */
export function getAdminToken(): string | null {
  return sessionStorage.getItem(TOKEN_KEY)
}
