Component({
  properties: {
    value: {
      type: Number,
      value: 0
    },
    interactive: {
      type: Boolean,
      value: false
    }
  },

  data: {
    stars: [1, 2, 3, 4, 5],
    animatingStar: 0
  },

  methods: {
    onStarTap: function (e) {
      if (!this.data.interactive) return
      var val = e.currentTarget.dataset.value
      this.setData({ value: val, animatingStar: val })
      this.triggerEvent('change', { value: val })

      // Clear animation class after animation completes so it can re-trigger
      var self = this
      setTimeout(function () {
        self.setData({ animatingStar: 0 })
      }, 300)
    }
  }
})
