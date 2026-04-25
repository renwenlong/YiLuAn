const { request } = require('./api')

function listEmergencyContacts() {
  return request({ url: 'emergency/contacts', method: 'GET' })
}

function createEmergencyContact(data) {
  return request({ url: 'emergency/contacts', method: 'POST', data })
}

function updateEmergencyContact(id, data) {
  return request({ url: 'emergency/contacts/' + id, method: 'PUT', data })
}

function deleteEmergencyContact(id) {
  return request({ url: 'emergency/contacts/' + id, method: 'DELETE' })
}

function getEmergencyHotline() {
  return request({ url: 'emergency/hotline', method: 'GET' })
}

function triggerEmergencyEvent(data) {
  return request({ url: 'emergency/events', method: 'POST', data: data })
}

module.exports = {
  listEmergencyContacts,
  createEmergencyContact,
  updateEmergencyContact,
  deleteEmergencyContact,
  getEmergencyHotline,
  triggerEmergencyEvent,
}
