function isValidPhone(phone) {
  return /^1[3-9]\d{9}$/.test(phone)
}

function isValidOTP(code) {
  return /^\d{6}$/.test(code)
}

module.exports = { isValidPhone, isValidOTP }
