/**
 * F-01: Companion certification badge rendering snapshot.
 *
 * The wechat layer is native (no DOM), so this test verifies that
 * (a) page data is shaped to drive the WXML badge, and
 * (b) tapping the badge previews the certificate image via wx.previewImage.
 *
 * **S3-DEV-003-TRUST-UI-WX AC#3 update (2026-06-11, 胡桃)**:
 * 原 F-01 测 certification-badge 节点存在 + 绑 onPreviewCertification +
 * 用 hasCertification 条件 — 但 wxml 原 badge 文案 '已认证·{{certificationType}}'
 * 在 cert_type='护士证' / '医师执业证' 时渲染 = '已认证·护士证' 等
 * 职业背书文案, 违 ADR-0046 §3.5 / S3-DEV-003-TRUST-UI §AC#3.
 *
 * 现 wxml 已删 certification-badge 节点 (仅保 'is_verified' 中性徽章),
 * 详细资质信息走 patient/order-detail 页 <cert-card> 组件 (仅后端
 * positive-list 过 ABAC 的 companion_cert_qualifications 表取不拼 已X资格).
 *
 * 本测试保留 page.data shape + onPreviewCertification handler 原状,
 * 另加反向 lint 防回归 (源件不得重新引入 certification-badge / certificationType wxml 渲染).
 */

jest.mock('../../services/companion', () => ({
  getCompanionDetail: jest.fn(),
  getCompanionReviews: jest.fn(),
  getCompanions: jest.fn(),
}))

jest.mock('../../store/index', () => ({
  getState: jest.fn(() => ({})),
  setState: jest.fn(),
  subscribe: jest.fn(),
}))

const fs = require('fs')
const path = require('path')

var companionService = require('../../services/companion')

// Capture Page config once
var detailConfig
;(function () {
  var configs = []
  global.Page = function (config) { configs.push(config) }
  jest.isolateModules(function () {
    require('../../pages/companion-detail/index')
  })
  detailConfig = configs[0]
})()

function createPage(pageConfig) {
  var page = Object.assign({}, pageConfig, { data: Object.assign({}, pageConfig.data) })
  page.setData = function (obj) { Object.assign(this.data, obj) }
  return page
}

beforeEach(function () {
  jest.clearAllMocks()
  __resetWxStorage()
})

describe('F-01 companion-detail certification badge', function () {
  test('loadData maps certification fields onto companion view-model', async function () {
    companionService.getCompanionDetail.mockResolvedValue({
      id: 'c1',
      real_name: '张护士',
      avg_rating: 4.9,
      total_orders: 200,
      verification_status: 'verified',
      certification_type: '护士证',
      certification_no: 'NO.20231234',
      certification_image_url: 'https://oss.example.com/cert/abc.jpg',
      certified_at: '2026-04-25T12:00:00+08:00',
    })
    companionService.getCompanionReviews.mockResolvedValue({ items: [] })

    var page = createPage(detailConfig)
    page.companionId = 'c1'
    page.loadData = detailConfig.loadData.bind(page)
    await page.loadData()

    expect(page.data.companion).toMatchObject({
      hasCertification: true,
      certificationType: '护士证',
      certificationNo: 'NO.20231234',
      certificationImageUrl: 'https://oss.example.com/cert/abc.jpg',
    })
    // Snapshot of derived shape
    expect({
      hasCertification: page.data.companion.hasCertification,
      certificationType: page.data.companion.certificationType,
      certificationNo: page.data.companion.certificationNo,
    }).toMatchSnapshot()
  })

  test('hasCertification is false when image_url missing', async function () {
    companionService.getCompanionDetail.mockResolvedValue({
      id: 'c2',
      real_name: '李陪诊',
      avg_rating: 0,
      total_orders: 0,
      verification_status: 'verified',
      certification_type: '健康管理师',
      certification_no: 'HM-1',
      certification_image_url: null,
    })
    companionService.getCompanionReviews.mockResolvedValue({ items: [] })

    var page = createPage(detailConfig)
    page.companionId = 'c2'
    page.loadData = detailConfig.loadData.bind(page)
    await page.loadData()

    expect(page.data.companion.hasCertification).toBe(false)
  })

  test('onPreviewCertification calls wx.previewImage with cert URL', function () {
    var page = createPage(detailConfig)
    page.onPreviewCertification = detailConfig.onPreviewCertification.bind(page)
    page.data.companion = {
      certificationImageUrl: 'https://oss.example.com/cert/abc.jpg',
    }

    page.onPreviewCertification()

    expect(wx.previewImage).toHaveBeenCalledTimes(1)
    expect(wx.previewImage).toHaveBeenCalledWith({
      urls: ['https://oss.example.com/cert/abc.jpg'],
      current: 'https://oss.example.com/cert/abc.jpg',
    })
  })

  test('onPreviewCertification is a no-op when no cert image', function () {
    var page = createPage(detailConfig)
    page.onPreviewCertification = detailConfig.onPreviewCertification.bind(page)
    page.data.companion = { certificationImageUrl: '' }
    page.onPreviewCertification()
    expect(wx.previewImage).not.toHaveBeenCalled()
  })

  test('S3-DEV-003-TRUST-UI-WX AC#3: WXML 不含 certification-badge / certificationType 渲染 (反向 lint)', function () {
    var wxmlPath = path.join(__dirname, '..', '..', 'pages', 'companion-detail', 'index.wxml')
    var wxml = fs.readFileSync(wxmlPath, 'utf8')
    // certification-badge 类名 不应出现在活 wxml (主名节点 已删).
    // 注释里提 'S3-DEV-003-TRUST-UI-WX AC#3: 删除 ...' 是 OK 的 lint reminder.
    // 简化: 扫仅 wxml 渲染式 (去掉 <!-- --> 注释 block).
    var stripped = wxml.replace(/<!--[\s\S]*?-->/g, '')
    expect(stripped).not.toContain('certification-badge')
    expect(stripped).not.toContain('{{companion.certificationType}}')
    expect(stripped).not.toContain('hasCertification')
  })
})
