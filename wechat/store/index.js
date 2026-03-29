let _state = {
  isAuthenticated: false,
  user: null,
}

let _listeners = []

function getState() {
  return { ..._state }
}

function setState(partial) {
  _state = { ..._state, ...partial }
  _listeners.forEach(fn => fn(_state))
}

function subscribe(fn) {
  _listeners.push(fn)
  return function unsubscribe() {
    _listeners = _listeners.filter(l => l !== fn)
  }
}

function reset() {
  _state = { isAuthenticated: false, user: null }
  _listeners.forEach(fn => fn(_state))
}

module.exports = { getState, setState, subscribe, reset }
