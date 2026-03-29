Component({
  properties: {
    companion: {
      type: Object,
      value: {}
    }
  },

  methods: {
    onTap: function () {
      this.triggerEvent('tap', { id: this.data.companion.id })
    }
  }
})
