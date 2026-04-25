const { request } = require('./api')

function submitReview(data) {
  // F-04: support both legacy single-rating and new 4-dimension payloads.
  // Caller may pass either `rating` (legacy) or all 4 of
  // punctuality_rating / professionalism_rating / communication_rating /
  // attitude_rating. Backend accepts either shape.
  const body = {
    content: data.content,
  }
  if (
    data.punctuality_rating != null &&
    data.professionalism_rating != null &&
    data.communication_rating != null &&
    data.attitude_rating != null
  ) {
    body.punctuality_rating = data.punctuality_rating
    body.professionalism_rating = data.professionalism_rating
    body.communication_rating = data.communication_rating
    body.attitude_rating = data.attitude_rating
  }
  if (data.rating != null) {
    body.rating = data.rating
  }
  return request({
    url: 'orders/' + data.orderId + '/review',
    method: 'POST',
    data: body,
  })
}

function getReviews(companionId, params = {}) {
  const { page = 1 } = params
  return request({
    url: 'companions/' + companionId + '/reviews?page=' + page,
    method: 'GET',
  })
}

function getOrderReview(orderId) {
  return request({
    url: 'orders/' + orderId + '/review',
    method: 'GET',
  })
}

module.exports = { submitReview, getReviews, getOrderReview }
