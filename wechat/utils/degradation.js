// Local degradation flag for weak-network fallback.
//
// Why: on flaky 4G / hospital wifi, key flows (order submit / pay) sometimes
// fail repeatedly with timeout or 5xx. We don't want to keep slamming the
// backend or leave the user staring at silent spinners. When the failure
// rate crosses a threshold we flip a local "degraded" flag, surface a
// "网络不稳定" banner globally, and callers can choose to skip non-critical
// calls or show inline hints.
//
// The flag is reset by `clearDegraded()` (called on any successful key call)
// or expires automatically after DEGRADE_TTL_MS to avoid sticky banners
// after the network recovers but the user hasn't retried the trigger.
//
// Storage layout (wx.setStorageSync):
//   yiluan_degraded_state: { degraded: bool, reason: str, ts: number }
//   yiluan_degraded_counters: { [scope]: { failures: number, lastFailTs } }

const STATE_KEY = 'yiluan_degraded_state'
const COUNTERS_KEY = 'yiluan_degraded_counters'

// Trip threshold: 3 consecutive failures on the same scope within window.
const FAILURE_THRESHOLD = 3
// Counter window: failures older than this are ignored.
const COUNTER_WINDOW_MS = 60 * 1000
// Auto-expiry: degraded state self-clears after this long with no refresh.
const DEGRADE_TTL_MS = 5 * 60 * 1000

// In-memory subscribers for UI banner reactivity (app.js wires this).
const _subscribers = []

function _readState() {
  try {
    const raw = wx.getStorageSync(STATE_KEY)
    if (!raw) return null
    return typeof raw === 'string' ? JSON.parse(raw) : raw
  } catch (e) {
    return null
  }
}

function _writeState(state) {
  try {
    wx.setStorageSync(STATE_KEY, state)
  } catch (e) {
    // storage full / disabled — degrade silently
  }
}

function _readCounters() {
  try {
    const raw = wx.getStorageSync(COUNTERS_KEY)
    if (!raw) return {}
    return typeof raw === 'string' ? JSON.parse(raw) : raw
  } catch (e) {
    return {}
  }
}

function _writeCounters(counters) {
  try {
    wx.setStorageSync(COUNTERS_KEY, counters)
  } catch (e) {
    // ignore
  }
}

function _notify() {
  const degraded = isDegraded()
  _subscribers.forEach(function (cb) {
    try {
      cb(degraded)
    } catch (e) {
      // single subscriber error must not break others
    }
  })
}

// True if degraded state is set and not expired.
function isDegraded() {
  const state = _readState()
  if (!state || !state.degraded) return false
  if (Date.now() - (state.ts || 0) > DEGRADE_TTL_MS) {
    // expired — auto-clear
    _writeState(null)
    return false
  }
  return true
}

// Read the current reason string (or null).
function getDegradedReason() {
  const state = _readState()
  if (!state || !state.degraded) return null
  return state.reason || null
}

// Force-enable degraded mode. `reason` is a short human label
// ('order_submit_timeout', 'pay_5xx', etc.) used for logging.
function setDegraded(reason) {
  _writeState({ degraded: true, reason: reason || 'manual', ts: Date.now() })
  _notify()
}

// Clear degraded mode (e.g. after a successful critical call).
function clearDegraded() {
  const prev = _readState()
  if (!prev || !prev.degraded) return
  _writeState(null)
  // also reset counters so a single hiccup doesn't immediately re-trip
  _writeCounters({})
  _notify()
}

// Decide whether a failure object should count toward degradation.
// We trip on: transport failure (statusCode 0 — timeout / DNS / TLS),
// 5xx server errors. We do NOT trip on 4xx (those are app-level errors,
// not network instability).
function _shouldCount(err) {
  if (!err) return false
  // wx fail-style: { errMsg: 'request:fail timeout' }
  if (err.errMsg && /timeout|fail/i.test(err.errMsg)) return true
  // our request() wrapper: { statusCode, data, requestId }
  const sc = err.statusCode
  if (sc === 0) return true
  if (typeof sc === 'number' && sc >= 500 && sc < 600) return true
  return false
}

// Record a failure for a named scope ('order_submit' | 'pay' | ...).
// Returns true if this failure tripped degraded mode.
function recordFailure(scope, err) {
  if (!_shouldCount(err)) return false
  const counters = _readCounters()
  const now = Date.now()
  const prev = counters[scope]
  let failures = 1
  if (prev && now - (prev.lastFailTs || 0) <= COUNTER_WINDOW_MS) {
    failures = (prev.failures || 0) + 1
  }
  counters[scope] = { failures: failures, lastFailTs: now }
  _writeCounters(counters)
  if (failures >= FAILURE_THRESHOLD && !isDegraded()) {
    setDegraded(scope + '_threshold')
    return true
  }
  return false
}

// Record a success — clears counter for that scope and, if degraded,
// clears the global flag (network came back).
function recordSuccess(scope) {
  const counters = _readCounters()
  if (counters[scope]) {
    delete counters[scope]
    _writeCounters(counters)
  }
  if (isDegraded()) {
    clearDegraded()
  }
}

// Subscribe to degraded state changes. Returns unsubscribe fn.
function subscribe(cb) {
  if (typeof cb !== 'function') return function () {}
  _subscribers.push(cb)
  return function unsubscribe() {
    const i = _subscribers.indexOf(cb)
    if (i >= 0) _subscribers.splice(i, 1)
  }
}

// Convenience wrapper: pass a promise-returning fn, and the scope label.
// Auto-records success / failure. Returns the original promise.
function track(scope, promiseFactory) {
  return Promise.resolve()
    .then(function () { return promiseFactory() })
    .then(function (res) {
      recordSuccess(scope)
      return res
    })
    .catch(function (err) {
      recordFailure(scope, err)
      throw err
    })
}

module.exports = {
  isDegraded: isDegraded,
  getDegradedReason: getDegradedReason,
  setDegraded: setDegraded,
  clearDegraded: clearDegraded,
  recordFailure: recordFailure,
  recordSuccess: recordSuccess,
  subscribe: subscribe,
  track: track,
  // exported for tests
  _internal: {
    STATE_KEY: STATE_KEY,
    COUNTERS_KEY: COUNTERS_KEY,
    FAILURE_THRESHOLD: FAILURE_THRESHOLD,
    DEGRADE_TTL_MS: DEGRADE_TTL_MS,
  },
}
