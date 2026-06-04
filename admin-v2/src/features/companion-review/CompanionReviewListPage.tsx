/**
 * 陪诊师审核样板（S2-DEV-013 / acceptance #3 ）
 *
 * 4 个 REST 端点接通：
 * - GET /admin/companions （列表分页）
 * - GET /admin/companions/{id} （详情）
 * - POST /admin/companions/{id}/approve （通过）
 * - POST /admin/companions/{id}/reject （拒绝）
 *
 * 模式标准：TanStack Query useQuery + useMutation，error boundary，loading skeleton。
 * 后续 8 项 feature 复制本模板即可（Phase 2-9 复粘式扩展）。
 */
import { useState } from 'react'
import { Table, Button, Drawer, Descriptions, message, Space, Tag, Modal, Input } from 'antd'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import { apiClient } from '../../shared/api/client'

interface CompanionRow {
  id: string
  name: string
  phone: string
  status: 'pending' | 'verified' | 'rejected'
  created_at: string
}

interface ListResponse {
  items: CompanionRow[]
  total: number
}

const PAGE_SIZE = 10

async function fetchList(page: number): Promise<ListResponse> {
  const resp = await apiClient.get<ListResponse>('/admin/companions', {
    params: { status: 'pending', page, page_size: PAGE_SIZE },
  })
  return resp.data
}

async function approve(id: string): Promise<void> {
  await apiClient.post(`/admin/companions/${id}/approve`)
}

async function reject(id: string, reason: string): Promise<void> {
  await apiClient.post(`/admin/companions/${id}/reject`, { reason })
}

async function fetchDetail(id: string): Promise<CompanionRow> {
  const resp = await apiClient.get<CompanionRow>(`/admin/companions/${id}`)
  return resp.data
}

export function CompanionReviewListPage() {
  const [page, setPage] = useState(1)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [rejectingId, setRejectingId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const qc = useQueryClient()

  const listQ = useQuery({
    queryKey: ['companion-list', page],
    queryFn: () => fetchList(page),
  })

  const detailQ = useQuery({
    queryKey: ['companion-detail', detailId],
    queryFn: () => fetchDetail(detailId!),
    enabled: !!detailId,
  })

  const approveM = useMutation({
    mutationFn: (id: string) => approve(id),
    onSuccess: () => {
      message.success('已通过')
      qc.invalidateQueries({ queryKey: ['companion-list'] })
      setDetailId(null)
    },
    onError: (err) => message.error(`通过失败：${(err as Error).message}`),
  })

  const rejectM = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) => reject(id, reason),
    onSuccess: () => {
      message.success('已拒绝')
      qc.invalidateQueries({ queryKey: ['companion-list'] })
      setRejectingId(null)
      setRejectReason('')
      setDetailId(null)
    },
    onError: (err) => message.error(`拒绝失败：${(err as Error).message}`),
  })

  return (
    <div data-test-id="companion-review-page">
      <h2>陪诊师审核</h2>
      <Table<CompanionRow>
        rowKey="id"
        loading={listQ.isLoading}
        dataSource={listQ.data?.items ?? []}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total: listQ.data?.total ?? 0,
          onChange: setPage,
        }}
        columns={[
          { title: '姓名', dataIndex: 'name' },
          { title: '手机号', dataIndex: 'phone' },
          {
            title: '状态',
            dataIndex: 'status',
            render: (s: CompanionRow['status']) => (
              <Tag color={s === 'pending' ? 'orange' : s === 'verified' ? 'green' : 'red'}>
                {s}
              </Tag>
            ),
          },
          { title: '申请时间', dataIndex: 'created_at' },
          {
            title: '操作',
            render: (_, row) => (
              <Space>
                <Button size="small" onClick={() => setDetailId(row.id)}>
                  详情
                </Button>
              </Space>
            ),
          },
        ]}
      />

      <Drawer
        title="陪诊师详情"
        open={!!detailId}
        onClose={() => setDetailId(null)}
        width={520}
        extra={
          detailQ.data?.status === 'pending' && (
            <Space>
              <Button
                type="primary"
                loading={approveM.isPending}
                onClick={() => approveM.mutate(detailId!)}
              >
                通过
              </Button>
              <Button danger onClick={() => setRejectingId(detailId)}>
                拒绝
              </Button>
            </Space>
          )
        }
      >
        {detailQ.isLoading && '加载中...'}
        {detailQ.error && (
          <div style={{ color: 'red' }}>详情加载失败：{(detailQ.error as Error).message}</div>
        )}
        {detailQ.data && (
          <Descriptions column={1}>
            <Descriptions.Item label="姓名">{detailQ.data.name}</Descriptions.Item>
            <Descriptions.Item label="手机号">{detailQ.data.phone}</Descriptions.Item>
            <Descriptions.Item label="状态">{detailQ.data.status}</Descriptions.Item>
            <Descriptions.Item label="申请时间">{detailQ.data.created_at}</Descriptions.Item>
          </Descriptions>
        )}
      </Drawer>

      <Modal
        title="拒绝理由"
        open={!!rejectingId}
        onCancel={() => {
          setRejectingId(null)
          setRejectReason('')
        }}
        onOk={() =>
          rejectingId &&
          rejectReason.trim() &&
          rejectM.mutate({ id: rejectingId, reason: rejectReason.trim() })
        }
        okButtonProps={{ disabled: !rejectReason.trim() }}
      >
        <Input.TextArea
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
          rows={3}
          placeholder="请输入拒绝理由（审计行写入）"
        />
      </Modal>
    </div>
  )
}
