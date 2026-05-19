const {
  listFamilyMembers,
  createFamilyMember,
  updateFamilyMember,
  deleteFamilyMember,
} = require('../../services/familyMember')

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
})

describe('services/familyMember', () => {
  test('listFamilyMembers GET /users/me/family-members', async () => {
    __mockWxRequest(200, {
      items: [{ id: 'f1', name: '王芳', relation: 'spouse' }],
      total: 1,
    })
    const result = await listFamilyMembers()
    const args = wx.request.mock.calls[0][0]
    expect(args.url).toContain('users/me/family-members')
    expect(args.method).toBe('GET')
    expect(result.items).toHaveLength(1)
    expect(result.total).toBe(1)
  })

  test('createFamilyMember POST /users/me/family-members', async () => {
    __mockWxRequest(201, {
      id: 'f1',
      name: '王芳',
      relation: 'spouse',
      phone: '13900139000',
    })
    const data = { name: '王芳', relation: 'spouse', phone: '13900139000' }
    const result = await createFamilyMember(data)
    const args = wx.request.mock.calls[0][0]
    expect(args.url).toContain('users/me/family-members')
    expect(args.method).toBe('POST')
    expect(args.data).toEqual(data)
    expect(result.id).toBe('f1')
  })

  test('updateFamilyMember PATCH /users/me/family-members/:id', async () => {
    __mockWxRequest(200, { id: 'f1', name: '王芳芳' })
    const result = await updateFamilyMember('f1', { name: '王芳芳' })
    const args = wx.request.mock.calls[0][0]
    expect(args.url).toContain('users/me/family-members/f1')
    expect(args.method).toBe('PATCH')
    expect(result.name).toBe('王芳芳')
  })

  test('deleteFamilyMember DELETE /users/me/family-members/:id', async () => {
    __mockWxRequest(204, '')
    await deleteFamilyMember('f1')
    const args = wx.request.mock.calls[0][0]
    expect(args.url).toContain('users/me/family-members/f1')
    expect(args.method).toBe('DELETE')
  })
})
