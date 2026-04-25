const { ORDER_STATUS } = require('./constants')

// formatPrice
// ADR-0030: 后端金额内部为 Decimal(10,2)，但 API 出参仍为 number（299.0）以保持契约。
// 此函数同时兼容 number 和字符串入参（toFixed 前先 Number 转换），无需改动调用方。
function formatPrice(price) {
  const num = Number(price)
  if (isNaN(num)) return '¥0.00'
  return '¥' + num.toFixed(2)
}

function formatDate(isoString) {
  if (!isoString) return ''
  const d = new Date(isoString)
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function formatPhone(phone) {
  if (!phone || phone.length !== 11) return phone || ''
  return phone.slice(0, 3) + '****' + phone.slice(7)
}

function formatOrderStatus(status) {
  return (ORDER_STATUS[status] && ORDER_STATUS[status].label) || status || ''
}

module.exports = { formatPrice, formatDate, formatPhone, formatOrderStatus }
