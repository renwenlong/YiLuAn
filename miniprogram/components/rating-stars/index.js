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
    stars: [1, 2, 3, 4, 5]
  },

  methods: {
    onStarTap: function (e) {
      if (!this.data.interactive) return
      var val = e.currentTarget.dataset.value
      this.setData({ value: val })
      this.triggerEvent('change', { value: val })
    }
  }
})
