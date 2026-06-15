/**
 * Admin 角色定义 + menu 可见性规则（S2-DEV-013 / ADR-0042）
 * Phase 1 范围：前端 mock RBAC，未接后端真权限；后端 RBAC 留 Phase 6。
 */

export type AdminRole = 'super' | 'finance' | 'support' | 'bd'

export const ROLE_LABELS: Record<AdminRole, string> = {
  super: '超管',
  finance: '财务',
  support: '客服',
  bd: 'BD',
}

/** 每个 feature 路径可见的角色集合（mock 真源） */
export const MENU_VISIBILITY: Record<string, AdminRole[]> = {
  'companion-review': ['super', 'support'],
  'ai/blocklist': ['super', 'support'],
  'orders': ['super', 'support', 'finance'],
  'users': ['super', 'support'],
  'audit': ['super'],
  'refund-review': ['super', 'finance'],
  'dashboard': ['super', 'finance', 'support', 'bd'],
}

export function canSeeMenu(path: string, role: AdminRole): boolean {
  const allowed = MENU_VISIBILITY[path]
  if (!allowed) return false
  return allowed.includes(role)
}
