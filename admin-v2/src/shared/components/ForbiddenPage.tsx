import { Result, Button } from 'antd'
import { useNavigate } from 'react-router-dom'

export function ForbiddenPage() {
  const nav = useNavigate()
  return (
    <Result
      status="403"
      title="403"
      subTitle="抱歉，你当前角色无权访问该页面。"
      extra={
        <Button type="primary" onClick={() => nav('/', { replace: true })}>
          回首页
        </Button>
      }
    />
  )
}
