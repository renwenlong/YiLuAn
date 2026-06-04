import { useEffect, type PropsWithChildren } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore, subscribeToSessionStorageSync } from '../api/authStore'

/**
 * RequireAuth route guard (S2-DEV-013)
 * - 未登录 → /login
 * - 注册 cross-tab storage event sync 防止 v1 logout 后 v2 仍以为登录
 */
export function RequireAuth({ children }: PropsWithChildren) {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated())

  useEffect(() => {
    return subscribeToSessionStorageSync((newToken) => {
      // 由 authStore.logout() 内部完成 state 重置
      if (!newToken && typeof window !== 'undefined') {
        window.location.assign('/admin-v2/login')
      }
    })
  }, [])

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }
  return <>{children}</>
}
