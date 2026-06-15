/**
 * admin-v2 路由 + 4 角色守卫骨架（S2-DEV-013 / ADR-0042）
 *
 * 角色：超管 / 财务 / 客服 / BD（前端 mock，未接后端 RBAC）
 * 路由守卫：未登录 → /login；已登录访问无权 menu → /403
 *
 * v1↔v2 跳转：v1 only menu 项点击用 window.location.assign('/admin/#/...')
 * 避免 SPA history 栈污染（acceptance #6 ，刻晴 review 建议）
 */
import { Routes, Route, Navigate } from 'react-router-dom'

import { LoginPage } from './features/login/LoginPage'
import { ForbiddenPage } from './shared/components/ForbiddenPage'
import { CompanionReviewListPage } from './features/companion-review/CompanionReviewListPage'
import { AiBlocklistPage } from './features/ai-blocklist/AiBlocklistPage'
import { AppLayout } from './shared/layout/AppLayout'
import { RequireAuth } from './shared/components/RequireAuth'

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/403" element={<ForbiddenPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <AppLayout />
          </RequireAuth>
        }
      >
        <Route index element={<Navigate to="companion-review" replace />} />
        <Route path="companion-review" element={<CompanionReviewListPage />} />
        <Route path="ai/blocklist" element={<AiBlocklistPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
