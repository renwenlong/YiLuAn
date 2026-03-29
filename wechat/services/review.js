const { request } = require('./api')

function submitReview(data) {
  return request({
    url: 'orders/' + data.orderId + '/review',
    method: 'POST',
    data: {
      rating: data.rating,
      content: data.content,
    },
  })
}

function getReviews(companionId, params = {}) {
  const { page = 1 } = params
  return request({
    url: 'companions/' + companionId + '/reviews?page=' + page,
    method: 'GET',
  })
}

module.exports = { submitReview, getReviews }
