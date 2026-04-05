Component({
  properties: {
    companion: {
      type: Object,
      value: {}
    },
    showBook: {
      type: Boolean,
      value: false
    }
  },

  methods: {
    onTap: function () {
      this.triggerEvent('tap', { id: this.data.companion.id })
    },
    onBook: function () {
      this.triggerEvent('book', { id: this.data.companion.id })
    }
  }
})
