/**
 * 登录页（S2-DEV-013 Phase 1 mock）
 *
 * Phase 1 是骨架 + 1 样板，不接后端真登录（v1 已实现 admin token 登录）。
 * 用户输入 token + 选角色 → 存 sessionStorage → 跳主页。
 *
 * Phase 6 升级：接后端 RBAC，role 由后端 JWT claim 提供，不再前端 mock。
 */
import { Card, Form, Input, Select, Button, message, Space, Alert } from 'antd'
import { useNavigate } from 'react-router-dom'

import { useAuthStore } from '../../shared/api/authStore'
import { ROLE_LABELS, type AdminRole } from '../../shared/types/role'

interface LoginFormValues {
  token: string
  role: AdminRole
}

export function LoginPage() {
  const setRoleAndToken = useAuthStore((s) => s.setRoleAndToken)
  const nav = useNavigate()
  const [form] = Form.useForm<LoginFormValues>()

  function handleFinish(values: LoginFormValues) {
    if (!values.token.trim()) {
      message.error('请输入 admin token')
      return
    }
    setRoleAndToken(values.role, values.token.trim())
    message.success(`登录成功（${ROLE_LABELS[values.role]}）`)
    nav('/', { replace: true })
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#f0f2f5',
      }}
    >
      <Card title="医路安 Admin v2 登录" style={{ width: 420 }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="Phase 1 mock 登录"
            description="角色权限前端 mock，token 与 admin-h5 v1 共用（yiluan.admin.token）"
          />
          <Form<LoginFormValues>
            form={form}
            layout="vertical"
            onFinish={handleFinish}
            initialValues={{ role: 'super' as AdminRole }}
          >
            <Form.Item
              name="token"
              label="Admin Token"
              rules={[{ required: true, message: '请输入 token' }]}
            >
              <Input.Password placeholder="请输入 X-Admin-Token" />
            </Form.Item>
            <Form.Item
              name="role"
              label="角色"
              rules={[{ required: true }]}
            >
              <Select<AdminRole>
                options={Object.entries(ROLE_LABELS).map(([value, label]) => ({
                  value: value as AdminRole,
                  label,
                }))}
              />
            </Form.Item>
            <Button type="primary" htmlType="submit" block>
              登录
            </Button>
          </Form>
        </Space>
      </Card>
    </div>
  )
}
