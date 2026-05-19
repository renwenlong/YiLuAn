// [F-07] 复诊提醒 service
// Backend:
//   POST   /orders/{order_id}/followup-reminders        创建
//   GET    /orders/me/followup-reminders                列表
//   DELETE /orders/me/followup-reminders/{reminder_id}  取消（仅 pending）
const { request } = require('./api')

function createFollowupReminder(orderId, data) {
  return request({
    url: 'orders/' + orderId + '/followup-reminders',
    method: 'POST',
    data,
  })
}

function listMyFollowupReminders() {
  return request({ url: 'orders/me/followup-reminders', method: 'GET' })
}

function cancelFollowupReminder(reminderId) {
  return request({
    url: 'orders/me/followup-reminders/' + reminderId,
    method: 'DELETE',
  })
}

module.exports = {
  createFollowupReminder,
  listMyFollowupReminders,
  cancelFollowupReminder,
}
