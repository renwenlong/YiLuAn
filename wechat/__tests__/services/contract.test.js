/**
 * S3-DEV-001-CONTRACT-UI service tests.
 *
 * 覆盖 wechat/services/contract.js 2 API:
 * - acceptContract (POST /contracts/{id}/accept)
 * - getContract    (GET /contracts/{id})
 *
 * 5 AC 中 service 层负责 AC#3 (勾选立即调 /accept) + AC#4 (signed URL view).
 * AC#1 (默认 unchecked) + AC#2 (按钮 disabled until checked) + AC#5 (E2E)
 * 在 page 层逻辑, 不在 service 层 (需 Page mock framework, 本仓库目前无).
 */

const { acceptContract, getContract } = require('../../services/contract')

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
})

describe('services/contract', () => {
  // ---------------------------------------------------------------------
  // acceptContract (POST /contracts/{id}/accept)
  // ---------------------------------------------------------------------

  test('acceptContract POSTs to /contracts/{id}/accept', async () => {
    const contractId = 'c-uuid-1'
    __mockWxRequest(200, {
      contract_id: contractId,
      order_id: 'o-uuid-1',
      accepted_at: '2026-06-08T07:00:00Z',
      audit_log_id: 'log-uuid-1',
    })

    const result = await acceptContract(contractId)
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('contracts/' + contractId + '/accept')
    expect(callArgs.method).toBe('POST')
    expect(callArgs.data).toEqual({})  // empty body — backend extracts user + IP/UA
    expect(result.contract_id).toBe(contractId)
    expect(result.audit_log_id).toBeDefined()
  })

  test('acceptContract sends Authorization header', async () => {
    __mockWxRequest(200, {
      contract_id: 'c1',
      order_id: 'o1',
      accepted_at: '2026-06-08T07:00:00Z',
      audit_log_id: 'log1',
    })

    await acceptContract('c1')
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.header.Authorization).toBe('Bearer test_token')
  })

  test('acceptContract propagates 4xx as rejection (page layer toasts)', async () => {
    __mockWxRequest(404, { detail: 'contract not found' })

    await expect(acceptContract('nonexistent')).rejects.toMatchObject({
      statusCode: 404,
    })
  })

  // ---------------------------------------------------------------------
  // getContract (GET /contracts/{id})
  // ---------------------------------------------------------------------

  test('getContract GETs /contracts/{id} and returns signed URL when active', async () => {
    const contractId = 'c-uuid-2'
    __mockWxRequest(200, {
      contract_id: contractId,
      order_id: 'o-uuid-2',
      template_version: 'v1.0.0',
      status: 'active',
      signed_url: 'https://storage.example/contracts/2026/06/abc.pdf?sig=xxx',
      signed_url_expires_at: '2026-06-08T07:15:00Z',
      generated_at: '2026-06-08T06:55:00Z',
    })

    const result = await getContract(contractId)
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('contracts/' + contractId)
    expect(callArgs.method).toBe('GET')
    expect(result.status).toBe('active')
    expect(result.signed_url).toContain('https://')
    expect(result.template_version).toBe('v1.0.0')
  })

  test('getContract returns null signed_url when status pending_generation', async () => {
    __mockWxRequest(200, {
      contract_id: 'c3',
      order_id: 'o3',
      template_version: 'v1.0.0',
      status: 'pending_generation',
      signed_url: null,
      signed_url_expires_at: null,
      generated_at: null,
    })

    const result = await getContract('c3')
    expect(result.signed_url).toBeNull()
    expect(result.status).toBe('pending_generation')
  })

  test('getContract returns null signed_url when status manually_invalidated', async () => {
    __mockWxRequest(200, {
      contract_id: 'c4',
      order_id: 'o4',
      template_version: 'v1.0.0',
      status: 'manually_invalidated',
      signed_url: null,
      signed_url_expires_at: null,
      generated_at: '2026-06-07T10:00:00Z',
    })

    const result = await getContract('c4')
    expect(result.signed_url).toBeNull()
    expect(result.status).toBe('manually_invalidated')
  })

  test('getContract 404 for non-owner (IDOR防御; 服务端隐藏存在性)', async () => {
    __mockWxRequest(404, { detail: 'contract not found' })

    await expect(getContract('other-user-contract')).rejects.toMatchObject({
      statusCode: 404,
    })
  })
})
