// S2-REQ-003-P5b — servicePackages service 单测 (Jest)

const path = require('path')

const apiPath = path.resolve(__dirname, '../../services/api.js')
const servicePath = path.resolve(__dirname, '../../services/servicePackages.js')

function loadServiceWithMock(resolveValue, rejectValue) {
  jest.resetModules()
  jest.doMock(apiPath, () => ({
    request: jest.fn(() => {
      if (rejectValue) return Promise.reject(rejectValue)
      return Promise.resolve(resolveValue)
    })
  }))
  return require(servicePath)
}

describe('S2-REQ-003-P5b servicePackages service', () => {
  afterEach(() => { jest.resetModules() })

  test('API 200 返归一化 items 并按 sort_order 排序', async () => {
    const svc = loadServiceWithMock([
      { code: 'errand', name: '代办跑腿', price: '149.00', sort_order: 30 },
      { code: 'full_accompany', name: '全程陪诊', price: 299, sort_order: 10 }
    ])
    const items = await svc.listPublicServicePackages()
    expect(items).toHaveLength(2)
    expect(items[0].code).toBe('full_accompany')
    expect(items[0].price).toBe(299)
    expect(items[0]._fallback).toBe(false)
    expect(items[1].code).toBe('errand')
    expect(items[1].price).toBe(149)
  })

  test('API reject 降级 FALLBACK_PACKAGES', async () => {
    const svc = loadServiceWithMock(null, { statusCode: 503 })
    const items = await svc.listPublicServicePackages()
    expect(items).toHaveLength(3)
    expect(items.map((i) => i.code)).toEqual([
      'full_accompany', 'half_accompany', 'errand'
    ])
    items.forEach((it) => expect(it._fallback).toBe(true))
  })

  test('API 返空 array 也降级', async () => {
    const svc = loadServiceWithMock([])
    const items = await svc.listPublicServicePackages()
    expect(items).toHaveLength(3)
    expect(items[0]._fallback).toBe(true)
  })

  test('FALLBACK_PACKAGES 三档与 utils/constants SERVICE_TYPES 一致', () => {
    const svc = require(servicePath)
    const { SERVICE_TYPES } = require('../../utils/constants')
    svc.FALLBACK_PACKAGES.forEach((it) => {
      const ref = SERVICE_TYPES[it.code]
      expect(ref).toBeDefined()
      expect(it.name).toBe(ref.label)
      expect(it.price).toBe(ref.price)
    })
  })
})

// S2-REQ-003-P5b follow-up: 4 review fix
describe('S2-REQ-003-P5b review fix #2 #3', () => {
  test('fix #3: FALLBACK_PACKAGES 长度断言 = 3 (防漂移)', () => {
    const svc = require(servicePath)
    expect(svc.FALLBACK_PACKAGES).toHaveLength(3)
  })

  test('fix #3: FALLBACK_PACKAGES 顺序 = [full, half, errand] (sort_order 升序)', () => {
    const svc = require(servicePath)
    const codes = svc.FALLBACK_PACKAGES.map((p) => p.code)
    expect(codes).toEqual(['full_accompany', 'half_accompany', 'errand'])
  })

  test('fix #2: API timeout (Promise reject mock) 降级 fallback', async () => {
    // jest 不真等 5s; mock 直接 reject 模拟 timeout 行为
    const svc = loadServiceWithMock(null, { errMsg: 'request:fail timeout' })
    const items = await svc.listPublicServicePackages()
    expect(items).toHaveLength(3)
    expect(items[0]._fallback).toBe(true)
  })
})
