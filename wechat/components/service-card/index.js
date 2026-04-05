const { SERVICE_TYPES } = require('../../utils/constants')

Component({
  properties: {
    type: {
      type: String,
      value: ''
    },
    active: {
      type: Boolean,
      value: false
    }
  },

  data: {
    info: {}
  },

  observers: {
    'type': function (val) {
      if (val && SERVICE_TYPES[val]) {
        this.setData({ info: SERVICE_TYPES[val] })
      }
    }
  }
})
