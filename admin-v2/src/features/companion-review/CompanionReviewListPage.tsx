/**
 * 陪诊师审核样板（S2-DEV-013 PR-E1/E2/E3 合集 / ADR-0044 §3.1 + §4.1 + §5）
 *
 * 端点：
 * - GET  /admin/companions/                       pending list
 * - GET  /admin/companions/{id}                   audit detail (14 fields, PR-E1)
 * - POST /admin/companions/{id}/approve           approve
 * - POST /admin/companions/{id}/reject            reject (body.reason 1-500)
 * - GET  /admin/users/{user_id}?reveal=true       reveal phone (PR-E3, writes reveal_pii audit)
 * - POST /admin/companions/certification-images   Phase A cert image upload (PR-E2)
 *
 * drawer 通过 useQuery fetchDetail 拉 14 字段；
 * staleTime=0 + gcTime=0 强制每次打开重 fetch（Phase A signed URL TTL ≤ 15min，不能缓存）。
 * reveal phone 通过独立端点，backend 写 reveal_pii 审计。
 * Phase A cert image：drawer 内可点上传，上传成功后立刻用 backend 返回的 signed URL preview。
 */
import { useState } from 'react'
import {
  Table,
  Button,
  Drawer,
  Descriptions,
  message,
  Space,
  Tag,
  Modal,
  Input,
  Image,
  Empty,
  Upload,
} from 'antd'
import type { UploadProps } from 'antd'
import { UploadOutlined } from '@ant-design/icons'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'

import { apiClient } from '../../shared/api/client'

interface CompanionRow {
  id: string
  real_name: string
  id_number: string | null  // 已脱敏（backend mask_id_number）
  certifications: string | null
  created_at: string | null
}

interface CompanionDetail {
  // 与 list 重叠
  id: string
  real_name: string
  id_number: string | null
  certifications: string | null
  created_at: string | null
  // 审核字段
  bio: string | null
  verification_status: string
  certified_at: string | null
  certification_type: string | null
  certification_no: string | null
  certification_image_signed_url: string | null
  service_area: string | null
  service_city: string | null
  service_hospitals: string | null
  service_types: string | null
  avg_rating: number
  total_orders: number
  // 关联用户
  user_id: string | null
  user_phone_masked: string | null
}

interface UserReveal {
  id: string
  phone: string | null  // reveal=true 时为明文
  phone_masked: string | null
}

interface UploadCertImageResponse {
  certification_image_url: string
  certification_image_signed_url: string
}

interface ListResponse {
  items: CompanionRow[]
  total: number
  page: number
  page_size: number
}

const PAGE_SIZE = 20

async function fetchList(page: number): Promise<ListResponse> {
  const resp = await apiClient.get<ListResponse>('/admin/companions/', {
    params: { page, page_size: PAGE_SIZE },
  })
  return resp.data
}

async function fetchDetail(id: string): Promise<CompanionDetail> {
  // PR-E1 detail endpoint
  const resp = await apiClient.get<CompanionDetail>(`/admin/companions/${id}`)
  return resp.data
}

async function revealPhone(userId: string): Promise<string | null> {
  // PR-E3：复用 admin/users.py /{user_id}?reveal=true（backend 写 reveal_pii audit）
  const resp = await apiClient.get<UserReveal>(`/admin/users/${userId}`, {
    params: { reveal: true },
  })
  return resp.data.phone
}

async function approve(id: string): Promise<void> {
  await apiClient.post(`/admin/companions/${id}/approve`)
}

async function reject(id: string, reason: string): Promise<void> {
  await apiClient.post(`/admin/companions/${id}/reject`, { reason })
}

async function uploadCertificationImage(file: File): Promise<UploadCertImageResponse> {
  // PR-E2 Phase A：multipart upload → backend 存本地 cert-image:// + 返 15min signed URL
  const form = new FormData()
  form.append('file', file)
  const resp = await apiClient.post<UploadCertImageResponse>(
    '/admin/companions/certification-images',
    form,
  )
  return resp.data
}

export function CompanionReviewListPage() {
  const [page, setPage] = useState(1)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [revealedPhone, setRevealedPhone] = useState<string | null>(null)
  const [revealLoading, setRevealLoading] = useState(false)
  const [uploadedPreviewUrl, setUploadedPreviewUrl] = useState<string | null>(null)
  const [rejectingId, setRejectingId] = useState<string | null>(null)
  const [rejectReason, setRejectReason] = useState('')
  const qc = useQueryClient()

  const listQ = useQuery({
    queryKey: ['companion-list', page],
    queryFn: () => fetchList(page),
  })

  // PR-E3: fetchDetail 真调 PR-E1 detail endpoint
  // staleTime=0 + gcTime=0 强制每次 open drawer 重 fetch（signed URL TTL ≤ 15min，不缓存）
  const detailQ = useQuery({
    queryKey: ['companion-detail', detailId],
    queryFn: () => fetchDetail(detailId!),
    enabled: !!detailId,
    staleTime: 0,
    gcTime: 0,
  })

  const approveM = useMutation({
    mutationFn: (id: string) => approve(id),
    onSuccess: () => {
      message.success('已通过')
      qc.invalidateQueries({ queryKey: ['companion-list'] })
      setDetailId(null)
      setRevealedPhone(null)
      setUploadedPreviewUrl(null)
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
      setDetailId(null)
      setRevealedPhone(null)
      setUploadedPreviewUrl(null)
    },
    onError: (err) => message.error(`拒绝失败：${(err as Error).message}`),
  })

  const uploadM = useMutation({
    mutationFn: (file: File) => uploadCertificationImage(file),
    onSuccess: (data) => {
      setUploadedPreviewUrl(data.certification_image_signed_url)
      message.success('证件图已上传，可预览；提交认证时写入返回的 certification_image_url')
    },
    onError: (err) => message.error(`证件图上传失败：${(err as Error).message}`),
  })

  async function handleRevealPhone() {
    if (!detailQ.data?.user_id) return
    setRevealLoading(true)
    try {
      const phone = await revealPhone(detailQ.data.user_id)
      setRevealedPhone(phone)
      message.success('手机号已显示明文（操作已写入 reveal_pii 审计）')
    } catch (err) {
      message.error(`获取明文手机号失败：${(err as Error).message}`)
    } finally {
      setRevealLoading(false)
    }
  }

  const certPreviewUrl =
    uploadedPreviewUrl ?? detailQ.data?.certification_image_signed_url ?? null

  const uploadProps: UploadProps = {
    accept: 'image/jpeg,image/png,image/webp',
    showUploadList: false,
    customRequest: async (options) => {
      const file = options.file as File
      try {
        const data = await uploadM.mutateAsync(file)
        options.onSuccess?.(data)
      } catch (err) {
        options.onError?.(err as Error)
      }
    },
  }

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
                <Button
                  size="small"
                  onClick={() => {
                    setDetailId(row.id)
                    setRevealedPhone(null)
                    setUploadedPreviewUrl(null)
                  }}
                >
                  详情
                </Button>
              </Space>
            ),
          },
        ]}
      />

      <Drawer
        title="陪诊师审核详情"
        open={!!detailId}
        onClose={() => {
          setDetailId(null)
          setRevealedPhone(null)
          setUploadedPreviewUrl(null)
        }}
        width={720}
        extra={
          detailQ.data && (
            <Space>
              <Button
                type="primary"
                loading={approveM.isPending}
                onClick={() => detailId && approveM.mutate(detailId)}
              >
                通过
              </Button>
              <Button danger onClick={() => detailId && setRejectingId(detailId)}>
                拒绝
              </Button>
            </Space>
          )
        }
      >
        {detailQ.isLoading && '加载中...'}
        {detailQ.isError && (
          <div style={{ color: 'red' }}>
            详情加载失败：{(detailQ.error as Error).message}
          </div>
        )}
        {detailQ.data && (
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label="ID">{detailQ.data.id}</Descriptions.Item>
              <Descriptions.Item label="姓名">{detailQ.data.real_name}</Descriptions.Item>
              <Descriptions.Item label="身份证（脱敏）">
                {detailQ.data.id_number ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="手机号">
                {revealedPhone ? (
                  <span style={{ fontFamily: 'monospace' }}>{revealedPhone}</span>
                ) : (
                  <Space>
                    <span style={{ fontFamily: 'monospace' }}>
                      {detailQ.data.user_phone_masked ?? '—'}
                    </span>
                    {detailQ.data.user_id && (
                      <Button
                        size="small"
                        loading={revealLoading}
                        onClick={handleRevealPhone}
                      >
                        显示完整
                      </Button>
                    )}
                  </Space>
                )}
              </Descriptions.Item>
              <Descriptions.Item label="审核状态">
                <Tag color="orange">{detailQ.data.verification_status}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="自述 / 申请理由">
                {detailQ.data.bio ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="持证文本">
                {detailQ.data.certifications ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="证件类型">
                {detailQ.data.certification_type ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="证件编号">
                {detailQ.data.certification_no ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="服务城市">
                {detailQ.data.service_city ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="服务区域">
                {detailQ.data.service_area ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="服务医院">
                {detailQ.data.service_hospitals ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="服务类型">
                {detailQ.data.service_types ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="历史评分">
                {detailQ.data.avg_rating.toFixed(1)} 分（共 {detailQ.data.total_orders} 单）
              </Descriptions.Item>
              <Descriptions.Item label="申请时间">
                {detailQ.data.created_at ?? '—'}
              </Descriptions.Item>
              <Descriptions.Item label="认证时间">
                {detailQ.data.certified_at ?? '—'}
              </Descriptions.Item>
            </Descriptions>

            <div>
              <Space style={{ marginBottom: 12 }}>
                <strong>证件图预览（Phase A signed URL TTL ≤ 15min）</strong>
                <Upload {...uploadProps}>
                  <Button icon={<UploadOutlined />} loading={uploadM.isPending}>
                    上传证件图（Phase A）
                  </Button>
                </Upload>
              </Space>
              {certPreviewUrl ? (
                <Image
                  src={certPreviewUrl}
                  alt="陪诊师证件图预览"
                  width={360}
                  style={{ maxHeight: 260, objectFit: 'contain' }}
                />
              ) : (
                <Empty
                  description="暂无证件图（可点上方按钮上传后立刻预览）"
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                />
              )}
            </div>
          </Space>
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
