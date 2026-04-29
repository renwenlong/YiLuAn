const { ORDER_STATUS } = require('./constants')
const { formatCurrency } = require('./formatCurrency')

// formatPrice
// ADR-0030: 后端金额内部为 Decimal(10,2)，但 API 出参仍为 number（299.0）以保持契约。
// Action #8: 统一金额展示为「千分位 + 两位小数」（¥1,200.00），转调 formatCurrency。
// 保持函数名向后兼容；行为变化：'¥1200.00' → '¥1,200.00'。
function formatPrice(price) {
  return formatCurrency(price)
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
