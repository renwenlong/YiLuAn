import { Layout, Menu, Tooltip, Spin, message } from 'antd'
import {
  AuditOutlined,
  TeamOutlined,
  ShoppingOutlined,
  DashboardOutlined,
  UserOutlined,
  DollarOutlined,
  LogoutOutlined,
  FileSearchOutlined,
} from '@ant-design/icons'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useState } from 'react'

import { useAuthStore } from '../api/authStore'
import { ROLE_LABELS, MENU_VISIBILITY, type AdminRole } from '../types/role'

const { Header, Sider, Content } = Layout

/**
 * admin-v2 主 layout（S2-DEV-013）
 *
 * 关键设计：
 * - menu 项加 `data-role-{role}` 属性给 Playwright E2E selector 用（acceptance #5）
 * - v1-only menu 项点击用 `window.location.assign('/admin/#/...')` 跳回 v1
 *   （acceptance #6 ，避免 SPA history 栈污染，刻晴 review 建议）
 * - 跳转前显示 tooltip + loading 提示用户感知（胡桃 review §5.1 第 3 项）
 */

// v2 已实现的 feature path
const V2_IMPLEMENTED = new Set(['companion-review', 'ai/blocklist'])

interface MenuItemDef {
  key: string
  label: string
  icon: React.ReactNode
}

const MENU_ITEMS: MenuItemDef[] = [
  { key: 'companion-review', label: '陪诊师审核', icon: <AuditOutlined /> },
  { key: 'ai/blocklist', label: 'AI 关键词黑名单', icon: <FileSearchOutlined /> },
  { key: 'orders', label: '订单管理', icon: <ShoppingOutlined /> },
  { key: 'users', label: '用户管理', icon: <UserOutlined /> },
  { key: 'refund-review', label: '退款审批', icon: <DollarOutlined /> },
  { key: 'audit', label: '审计日志', icon: <TeamOutlined /> },
  { key: 'dashboard', label: '仪表盘', icon: <DashboardOutlined /> },
]

export function AppLayout() {
  const role = useAuthStore((s) => s.role)
  const logout = useAuthStore((s) => s.logout)
  const nav = useNavigate()
  const loc = useLocation()
  const [jumpingV1, setJumpingV1] = useState(false)

  if (!role) {
    return <Spin tip="加载中..." />
  }

  // 按角色 + Phase 1 已实现状态过滤可见 menu
  const visibleItems = MENU_ITEMS.filter((m) => {
    const allowed: AdminRole[] = MENU_VISIBILITY[m.key] ?? []
    return allowed.includes(role)
  })

  function handleClickMenu(key: string) {
    if (V2_IMPLEMENTED.has(key)) {
      nav(`/${key}`)
      return
    }
    // v1-only feature → 跳回 v1（acceptance #6）
    setJumpingV1(true)
    message.info({
      content: `「${MENU_ITEMS.find((m) => m.key === key)?.label}」暂在旧版 admin，将跳转`,
      duration: 1.2,
      onClose: () => {
        window.location.assign(`/admin/#/${key}`)
      },
    })
  }

  const currentKey = (() => {
    const path = loc.pathname.replace(/^\//, '')
    if (!path) return 'companion-review'
    // 优先匹配两段 (e.g. ai/blocklist), 否则取首段
    const twoParts = path.split('/').slice(0, 2).join('/')
    if (V2_IMPLEMENTED.has(twoParts)) return twoParts
    return path.split('/')[0]
  })()

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider width={220} theme="dark">
        <div
          style={{
            color: '#fff',
            padding: '16px 24px',
            fontSize: 18,
            fontWeight: 600,
          }}
        >
          医路安 Admin v2
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[currentKey]}
          items={visibleItems.map((m) => ({
            key: m.key,
            icon: m.icon,
            label: V2_IMPLEMENTED.has(m.key) ? (
              m.label
            ) : (
              <Tooltip title="旧版功能，点击跳回 admin-h5">{m.label}</Tooltip>
            ),
            // Playwright E2E selector hook（acceptance #5）
            'data-role': role,
            'data-impl': V2_IMPLEMENTED.has(m.key) ? 'v2' : 'v1',
          }))}
          onClick={({ key }) => handleClickMenu(key)}
        />
      </Sider>
      <Layout>
        <Header
          style={{
            background: '#fff',
            padding: '0 24px',
            display: 'flex',
            justifyContent: 'flex-end',
            alignItems: 'center',
            gap: 12,
          }}
        >
          <span data-test-id="current-role">
            当前角色：{ROLE_LABELS[role]}
          </span>
          <LogoutOutlined
            onClick={() => {
              logout()
              nav('/login', { replace: true })
            }}
            style={{ cursor: 'pointer' }}
          />
        </Header>
        <Content style={{ margin: 16, background: '#fff', padding: 16 }}>
          {jumpingV1 ? <Spin tip="跳转旧版..." /> : <Outlet />}
        </Content>
      </Layout>
    </Layout>
  )
}
