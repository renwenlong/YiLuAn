const { SERVICE_TYPES } = require('../../utils/constants')

Component({
  properties: {
    type: {
      type: String,
      value: ''
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
