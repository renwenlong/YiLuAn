/**
 * AI 关键词黑名单查看页 (S3-DEV-002-KEYWORD-FILTER-FRONTEND-PAGE / ADR-0048 §4.1)
 *
 * UI 设计:
 * - Antd Table read-only 展示 version + 6 大分类 × patterns (每行: category / description / patterns / pattern_count)
 * - 禁 edit/save 按钮 (前端层禁编辑, 后端无 POST/PUT/DELETE endpoint)
 * - 顶栏 Alert 说明 "修改请走 PR + 医疗顾问 review", 链接 docs/medical-content/prohibited-keywords.yml
 * - query category 下拉过滤 (6 大分类 + ALL)
 *
 * 端点:
 * - GET /admin/ai-blocklist/preview?category=<optional>
 * - response: {version, total_patterns, categories: [{category, description, patterns, pattern_count}], note}
 *
 * 审计 (后端自动):
 * - admin_audit_logs: target_type=ai_blocklist, action=ai_blocklist_viewed
 * - metric: ai_blocklist_viewed_total{admin_id=...}
 *
 * 鉴权:
 * - require admin JWT (RequireAuth route guard 已挡未登录)
 * - 401 → axios interceptor 自动跳 /login
 */
import { useState } from 'react'
import { Table, Alert, Select, Space, Tag, Typography } from 'antd'
import { useQuery } from '@tanstack/react-query'

import { apiClient } from '../../shared/api/client'

const { Link, Text } = Typography

interface BlocklistCategory {
  category: string
  description: string
  patterns: string[]
  pattern_count: number
}

interface BlocklistPreviewResponse {
  version: string
  categories: BlocklistCategory[]
  total_patterns: number
  note: string
}

/**
 * 6 大分类映射 (固定枚举, 后端 prohibited-keywords.yml 已锁定).
 * 列出 ALL 选项让 query 不带 category.
 */
const CATEGORY_OPTIONS = [
  { value: 'ALL', label: '全部分类' },
  { value: 'diagnosis', label: '诊断 (diagnosis)' },
  { value: 'treatment', label: '治疗 (treatment)' },
  { value: 'medication', label: '用药 (medication)' },
  { value: 'symptom', label: '症状 (symptom)' },
  { value: 'examination', label: '检查 (examination)' },
  { value: 'other', label: '其他 (other)' },
]

async function fetchBlocklist(category: string): Promise<BlocklistPreviewResponse> {
  const params = category === 'ALL' ? {} : { category }
  const resp = await apiClient.get<BlocklistPreviewResponse>(
    '/admin/ai-blocklist/preview',
    { params },
  )
  return resp.data
}

export function AiBlocklistPage() {
  const [category, setCategory] = useState<string>('ALL')

  const q = useQuery({
    queryKey: ['ai-blocklist', category],
    queryFn: () => fetchBlocklist(category),
    // 查看页可缓存; admin 短时间内反复点不必每次写 audit
    // (但后端每次调都写 audit, staleTime 仅影响前端 cache)
    staleTime: 30_000,
  })

  return (
    <div data-test-id="ai-blocklist-page">
      <h2>AI 关键词黑名单 (read-only)</h2>

      <Alert
        type="warning"
        showIcon
        style={{ marginBottom: 16 }}
        message="此页为 read-only 查看页"
        description={
          <Space direction="vertical" size="small">
            <Text>
              不允许 admin 后台直接编辑 (ADR-0048 §4.1). 修改 AI 关键词黑名单请走 PR + 医疗顾问 review approve 后合 main:
            </Text>
            <Link
              href="https://github.com/renwenlong/YiLuAn/blob/main/docs/medical-content/prohibited-keywords.yml"
              target="_blank"
              rel="noopener noreferrer"
            >
              docs/medical-content/prohibited-keywords.yml ↗
            </Link>
            <Text type="secondary">
              每次查看会写入 admin_audit_logs (action=ai_blocklist_viewed); 后端无 POST/PUT/DELETE endpoint.
            </Text>
          </Space>
        }
      />

      <Space style={{ marginBottom: 16 }}>
        <Text strong>分类过滤:</Text>
        <Select
          data-test-id="category-filter"
          value={category}
          onChange={setCategory}
          style={{ width: 220 }}
          options={CATEGORY_OPTIONS}
        />
        {q.data && (
          <Space>
            <Tag color="blue">version: {q.data.version}</Tag>
            <Tag color="green">total patterns: {q.data.total_patterns}</Tag>
          </Space>
        )}
      </Space>

      {q.isError && (
        <Alert
          type="error"
          showIcon
          message="加载失败"
          description={(q.error as Error).message}
          style={{ marginBottom: 16 }}
        />
      )}

      <Table<BlocklistCategory>
        rowKey="category"
        loading={q.isLoading}
        dataSource={q.data?.categories ?? []}
        pagination={false}
        expandable={{
          // patterns 太多默认折叠, 展开看完整 list
          expandedRowRender: (row) => (
            <div data-test-id={`patterns-${row.category}`}>
              <Text strong>所有 pattern ({row.pattern_count}):</Text>
              <div style={{ marginTop: 8 }}>
                {row.patterns.map((p) => (
                  <Tag key={p} style={{ marginBottom: 4 }}>
                    {p}
                  </Tag>
                ))}
              </div>
            </div>
          ),
        }}
        columns={[
          {
            title: '分类',
            dataIndex: 'category',
            width: 160,
            render: (v: string) => <Text code>{v}</Text>,
          },
          {
            title: '说明',
            dataIndex: 'description',
            render: (v: string) => v || <Text type="secondary">—</Text>,
          },
          {
            title: 'pattern 数',
            dataIndex: 'pattern_count',
            width: 120,
            render: (v: number) => <Tag color="geekblue">{v}</Tag>,
          },
          {
            title: '示例 pattern (前 3 个)',
            dataIndex: 'patterns',
            render: (patterns: string[]) => (
              <Space wrap>
                {patterns.slice(0, 3).map((p) => (
                  <Tag key={p}>{p}</Tag>
                ))}
                {patterns.length > 3 && (
                  <Text type="secondary">+{patterns.length - 3} 更多 (点行展开)</Text>
                )}
              </Space>
            ),
          },
        ]}
      />
    </div>
  )
}
