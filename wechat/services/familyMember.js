// [F-05] Family members CRUD service (代他人下单)
// Backend: /api/v1/users/me/family-members
const { request } = require('./api')

function listFamilyMembers() {
  return request({ url: 'users/me/family-members', method: 'GET' })
}

function createFamilyMember(data) {
  return request({ url: 'users/me/family-members', method: 'POST', data })
}

function updateFamilyMember(id, data) {
  return request({ url: 'users/me/family-members/' + id, method: 'PATCH', data })
}

function deleteFamilyMember(id) {
  return request({ url: 'users/me/family-members/' + id, method: 'DELETE' })
}

module.exports = {
  listFamilyMembers,
  createFamilyMember,
  updateFamilyMember,
  deleteFamilyMember,
}
