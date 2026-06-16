/**
 * components/cert-card — S3-DEV-003-TRUST-UI-WX 陪诊师资质信任卡.
 *
 * 渲染后端 OrderPrecheckSummaryView.companion_cert_status 的
 * 4 个 cert 字段:
 *   - companion_cert_status (verified / pending_resubmit / unverified — 3 状态)
 *   - companion_cert_pseudonym_name (化名, 如 "陈师傅", 永不出真名)
 *   - companion_cert_work_id (工号, 如 "PC0042")
 *   - companion_cert_verified_at (admin verify 通过时刻)
 *
 * ABAC 红线 (本组件永不渲染):
 *   - companion_cert_proof_image_urls (signed URL 即使后端返回也不渲染原图,
 *     AC#2)
 *   - companion_real_name / companion_phone / companion_id_card_hash
 *     (后端 ABAC Layer 1 物理排除, 微信端也不解码)
 *
 * 文案 lint (AC#3):
 *   - 严禁 "已护士资格" / "已医生资格" / "已主任医师" 类职业背书,
 *     仅展示 qualifications 字段原文 (后端医疗顾问 review approved 词表).
 */
var STATE_VERIFIED = 'verified'
var STATE_PENDING_RESUBMIT = 'pending_resubmit'
var STATE_UNVERIFIED = 'unverified'

function _deriveState(cs) {
  if (!cs) return STATE_UNVERIFIED
  if (cs.ready === true) return STATE_VERIFIED
  // 有过 pseudonym 名 / work_id → 曾经认证过, 现 pending_resubmit (临时证明补交中)
  if (cs.companion_cert_pseudonym_name || cs.companion_cert_work_id) {
    return STATE_PENDING_RESUBMIT
  }
  return STATE_UNVERIFIED
}

function _formatVerifiedAt(iso) {
  if (!iso) return ''
  try {
    var d = new Date(iso)
    if (isNaN(d.getTime())) return ''
    var y = d.getFullYear()
    var m = String(d.getMonth() + 1).padStart(2, '0')
    var day = String(d.getDate()).padStart(2, '0')
    return y + '-' + m + '-' + day
  } catch (e) {
    return ''
  }
}

function _stateLabel(state) {
  if (state === STATE_VERIFIED) return '已认证'
  if (state === STATE_PENDING_RESUBMIT) return '临时证明补交中'
  return '未认证'
}

function _joinQualifications(cs) {
  if (!cs || !Array.isArray(cs.companion_cert_qualifications) || cs.companion_cert_qualifications.length === 0) {
    return ''
  }
  return cs.companion_cert_qualifications.filter(Boolean).join('、')
}

function _a11ySummary(cs) {
  var state = _deriveState(cs)
  var parts = [
    '状态：' + _stateLabel(state),
    cs && cs.companion_cert_pseudonym_name ? '姓名：' + cs.companion_cert_pseudonym_name : '姓名未提供',
    cs && cs.companion_cert_work_id ? '工号：' + cs.companion_cert_work_id : '工号未提供',
    _joinQualifications(cs) ? '资质：' + _joinQualifications(cs) : '资质未提供',
  ]
  var verifiedAt = _formatVerifiedAt(cs && cs.companion_cert_verified_at)
  parts.push(verifiedAt ? '认证时间：' + verifiedAt : (state === STATE_VERIFIED ? '认证时间未提供' : '认证时间待核验'))
  return parts.join('；')
}

function _a11yLabel(cs) {
  return '陪诊师资质；' + _a11ySummary(cs) + '；证件原图不会在用户端展示。'
}

// Wechat runtime registers component via global Component({...}).
// In jest (node) env, `Component` is undefined; we guard with typeof so that
// the same file is safely require()-able from a test for unit-testing the
// pure helpers (_deriveState / _formatVerifiedAt). Tests that want to
// inspect the Component definition itself can stub `global.Component`
// before require — see __tests__/components/cert-card.test.js (or pattern
// from __tests__/components/rating-stars.test.js).
if (typeof Component !== 'undefined') {
  Component({
    properties: {
      /**
       * 4 信任卡之一 — companion_cert_status sub-object.
       * Schema: backend/app/schemas/order_precheck.py::CompanionCertStatusView
       */
      certStatus: {
        type: Object,
        value: null,
        observer: function (newVal) {
          var state = _deriveState(newVal)
          this.setData({
            derivedState: state,
            verifiedAtDisplay: _formatVerifiedAt(newVal && newVal.companion_cert_verified_at),
            a11yStateLabel: _stateLabel(state),
            a11yQualifications: _joinQualifications(newVal),
            a11ySummary: _a11ySummary(newVal),
            a11yLabel: _a11yLabel(newVal),
          })
        },
      },
    },

    data: {
      derivedState: STATE_UNVERIFIED,
      verifiedAtDisplay: '',
      a11yStateLabel: _stateLabel(STATE_UNVERIFIED),
      a11yQualifications: '',
      a11ySummary: _a11ySummary(null),
      a11yLabel: _a11yLabel(null),
      // 状态字面常量给 wxml wx:if 用
      STATE_VERIFIED: STATE_VERIFIED,
      STATE_PENDING_RESUBMIT: STATE_PENDING_RESUBMIT,
      STATE_UNVERIFIED: STATE_UNVERIFIED,
    },
  })
}

// CommonJS export for jest unit test access (only when require()d outside wx
// runtime; wx Component({}) handles registration in the small-program env).
module.exports = {
  _deriveState: _deriveState,
  _formatVerifiedAt: _formatVerifiedAt,
  _stateLabel: _stateLabel,
  _joinQualifications: _joinQualifications,
  _a11ySummary: _a11ySummary,
  _a11yLabel: _a11yLabel,
  STATE_VERIFIED: STATE_VERIFIED,
  STATE_PENDING_RESUBMIT: STATE_PENDING_RESUBMIT,
  STATE_UNVERIFIED: STATE_UNVERIFIED,
}
