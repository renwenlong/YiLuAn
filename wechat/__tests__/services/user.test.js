const { getMe, updateMe, getPatientProfile, updatePatientProfile, uploadAvatar } = require('../../services/user')

beforeEach(() => {
  jest.clearAllMocks()
  __resetWxStorage()
  wx.setStorageSync('yiluan_access_token', 'test_token')
})

describe('services/user', () => {
  // Test 14: getMe calls GET /users/me
  test('getMe fetches current user', async () => {
    __mockWxRequest(200, { id: 'u1', phone: '138', role: 'patient' })

    const user = await getMe()
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('users/me')
    expect(callArgs.method).toBe('GET')
    expect(user.id).toBe('u1')
  })

  // Test 15: updateMe calls PUT /users/me
  test('updateMe sends user data', async () => {
    __mockWxRequest(200, { id: 'u1', role: 'patient' })

    const result = await updateMe({ nickname: 'Test' })
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.method).toBe('PUT')
    expect(callArgs.data).toEqual({ nickname: 'Test' })
    expect(result.id).toBe('u1')
  })

  // Test 16: updateMe with role
  test('updateMe can set role', async () => {
    __mockWxRequest(200, { id: 'u1', role: 'companion' })

    const result = await updateMe({ role: 'companion' })
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.data).toEqual({ role: 'companion' })
    expect(result.role).toBe('companion')
  })

  // Test 17: getPatientProfile calls GET /users/me/patient-profile
  test('getPatientProfile fetches patient profile', async () => {
    __mockWxRequest(200, { emergency_contact: 'John', emergency_phone: '139', medical_notes: 'None' })

    const profile = await getPatientProfile()
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('users/me/patient-profile')
    expect(callArgs.method).toBe('GET')
    expect(profile.emergency_contact).toBe('John')
  })

  // Test 18: updatePatientProfile calls PUT /users/me/patient-profile
  test('updatePatientProfile sends patient data', async () => {
    __mockWxRequest(200, { emergency_contact: 'Jane', emergency_phone: '138', medical_notes: 'Allergy' })

    const data = { emergency_contact: 'Jane', emergency_phone: '138', medical_notes: 'Allergy' }
    const result = await updatePatientProfile(data)
    const callArgs = wx.request.mock.calls[0][0]
    expect(callArgs.url).toContain('users/me/patient-profile')
    expect(callArgs.method).toBe('PUT')
    expect(callArgs.data).toEqual(data)
    expect(result.emergency_contact).toBe('Jane')
  })

  // Test 19: uploadAvatar uses wx.uploadFile
  test('uploadAvatar uploads file via wx.uploadFile', async () => {
    __mockWxUploadFile(200, { avatar_url: 'https://cdn.example.com/avatar.jpg' })

    const result = await uploadAvatar('/tmp/photo.jpg')
    const callArgs = wx.uploadFile.mock.calls[0][0]
    expect(callArgs.url).toContain('users/me/avatar')
    expect(callArgs.filePath).toBe('/tmp/photo.jpg')
    expect(callArgs.name).toBe('file')
    expect(callArgs.header['Authorization']).toBe('Bearer test_token')
    expect(result.avatar_url).toBe('https://cdn.example.com/avatar.jpg')
  })
})
