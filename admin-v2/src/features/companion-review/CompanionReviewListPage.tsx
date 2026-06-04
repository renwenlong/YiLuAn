/**
 * 陪诊师审核样板（S2-DEV-013 PR-B / acceptance #3 ）
 *
 * 4 个 REST 端点接通：
 * - GET /admin/companions          （分页列表，强制 status=pending）
 * - POST /admin/companions/{id}/approve （通过）
 * - POST /admin/companions/{id}/reject  （拒绝，body.reason 1-500 字）
 *
 * 注：后端无 GET /admin/companions/{id} detail 端点（PR-A 假设错误）。
 * Drawer 直接复用 list row 数据，无需额外 fetch（详 PR-B description 契约对照表）。
 *
 * 后续 8 项 feature 复制本模板即可（Phase 2-9 复粘式扩展）。
 */
import { useState } from 'react'
import { Table, Button, Drawer, Descriptions, message, Space, Tag, Modal, Input } from 'antd'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import { apiClient } from '../../shared/api/client'

interface CompanionRow {
  id: string
  real_name: string
  id_number: string | null  // 已脱敏（backend mask_id_number）
  certifications: string | null
  created_at: string | null
}

interface ListResponse {
  items: CompanionRow[]
  total: number
  page: number
  page_size: number
}

const PAGE_SIZE = 20

async function fetchList(page: number): Promise<ListResponse> {
  // backend GET /admin/companions 强制 status=pending（不需前端传）
  const resp = await apiClient.get<ListResponse>('/admin/companions/', {
    params: { page, page_size: PAGE_SIZE },
  })
  return resp.data
}

async function approve(id: string): Promise<void> {
  await apiClient.post(`/admin/companions/${id}/approve`)
}

async function reject(id: string, reason: string): Promise<void> {
  await apiClient.post(`/admin/companions/${id}/reject`, { reason })
}

export function CompanionReviewListPage() {
  const [page, setPage] = useState(1)
  const [detail, setDetail] = useState<CompanionRow | null>(null)
  const [rejectingId, setRejectingId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const qc = useQueryClient()

  const listQ = useQuery({
    queryKey: ['companion-list', page],
    queryFn: () => fetchList(page),
  })

  const approveM = useMutation({
    mutationFn: (id: string) => approve(id),
    onSuccess: () => {
      message.success('已通过')
      qc.invalidateQueries({ queryKey: ['companion-list'] })
      setDetail(null)
    },
    onError: (err) => message.error(`通过失败：${(err as Error).message}`),
  })

  const rejectM = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      reject(id, reason),
    onSuccess: () => {
      message.success('已拒绝')
      qc.invalidateQueries({ queryKey: ['companion-list'] })
      setRejectingId(null)
      setRejectReason('')
      setDetail(null)
    },
    onError: (err) => message.error(`拒绝失败：${(err as Error).message}`),
  })

  return (
    <div data-test-id="companion-review-page">
      <h2>陪诊师审核（待审核）</h2>
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
          { title: '姓名', dataIndex: 'real_name' },
          {
            title: '身份证（脱敏）',
            dataIndex: 'id_number',
            render: (v: string | null) => v ?? '—',
          },
          {
            title: '持证',
            dataIndex: 'certifications',
            render: (v: string | null) => v ?? '—',
          },
          {
            title: '状态',
            render: () => <Tag color="orange">pending</Tag>,
          },
          {
            title: '申请时间',
            dataIndex: 'created_at',
            render: (v: string | null) => v ?? '—',
          },
          {
            title: '操作',
            render: (_, row) => (
              <Space>
                <Button size="small" onClick={() => setDetail(row)}>
                  详情
                </Button>
              </Space>
            ),
          },
        ]}
      />

      <Drawer
        title="陪诊师详情"
        open={!!detail}
        onClose={() => setDetail(null)}
        width={520}
        extra={
          detail && (
            <Space>
              <Button
                type="primary"
                loading={approveM.isPending}
                onClick={() => approveM.mutate(detail.id)}
              >
                通过
              </Button>
              <Button danger onClick={() => setRejectingId(detail.id)}>
                拒绝
              </Button>
            </Space>
          )
        }
      >
        {detail && (
          <Descriptions column={1}>
            <Descriptions.Item label="ID">{detail.id}</Descriptions.Item>
            <Descriptions.Item label="姓名">{detail.real_name}</Descriptions.Item>
            <Descriptions.Item label="身份证（脱敏）">
              {detail.id_number ?? '—'}
            </Descriptions.Item>
            <Descriptions.Item label="持证">
              {detail.certifications ?? '—'}
            </Descriptions.Item>
            <Descriptions.Item label="状态">pending</Descriptions.Item>
            <Descriptions.Item label="申请时间">
              {detail.created_at ?? '—'}
            </Descriptions.Item>
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
          maxLength={500}
          showCount
          placeholder="请输入拒绝理由（1~500 字，审计行写入）"
        />
      </Modal>
    </div>
  )
}
