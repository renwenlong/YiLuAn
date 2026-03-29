const store = require('./store/index')
const { getAccessToken, isTokenExpired } = require('./utils/token')
const { getMe } = require('./services/user')
const { logout } = require('./services/auth')

App({
  globalData: {
    store: store,
  },

  onLaunch() {
    const accessToken = getAccessToken()
    if (accessToken && !isTokenExpired(accessToken)) {
      store.setState({ isAuthenticated: true })
      getMe().then(user => {
        store.setState({ user })
      }).catch(() => {
        logout()
      })
    }
  },
})
