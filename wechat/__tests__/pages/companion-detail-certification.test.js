/**
 * F-01: Companion certification badge rendering snapshot.
 *
 * The wechat layer is native (no DOM), so this test verifies that
 * (a) page data is shaped to drive the WXML badge, and
 * (b) tapping the badge previews the certificate image via wx.previewImage.
 *
 * The WXML snippet itself is asserted inline as a snapshot string so that
 * accidental removal of the badge is caught by `npm test`.
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

  test('WXML contains certification-badge node bound to onPreviewCertification', function () {
    var wxmlPath = path.join(__dirname, '..', '..', 'pages', 'companion-detail', 'index.wxml')
    var wxml = fs.readFileSync(wxmlPath, 'utf8')
    expect(wxml).toContain('certification-badge')
    expect(wxml).toContain('bindtap="onPreviewCertification"')
    expect(wxml).toContain('wx:if="{{companion.hasCertification}}"')
  })
})
