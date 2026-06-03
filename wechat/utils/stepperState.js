// stepperState.js
// S2-INT-003 — U-1 折叠式分步下单「状态机 + 回改冲突判定」纯逻辑真源
//
// 真源：docs/design/wireframes/U1-folding-stepper/README.md §四 状态机 / §五 边界态
// UI 无关，可独立单测。微信端与 iOS 端规则同源。
//
// 步骤（钉死 4 步，不可拆分/合并）：
//   1 服务类型  2 医院  3 日期  4 患者&陪诊师确认
//
// 步骤三态：
//   'collapsed' 未到（点击无响应，除非已 done）
//   'active'    当前展开编辑
//   'done'      已完成，显摘要，可点回改

var TOTAL_STEPS = 4

var STEP_TITLES = ['服务类型', '医院', '日期', '患者 & 陪诊师确认']

// 各步骤「是否已填」判定。data 为页面 data 快照。
// 注意：科室(department)为可选，不参与第②步完成判定。
function isStepFilled(step, data) {
  switch (step) {
    case 1:
      return !!data.serviceType
    case 2:
      return !!data.hospitalId
    case 3:
      return !!data.date && !!data.period // period: '上午' | '下午'
    case 4:
      // 患者(本人或家人均可)恒成立；陪诊师可选。第④步「确认」即完成。
      return true
    default:
      return false
  }
}

// 计算每个步骤的三态。
// currentStep   = 当前 active 的步骤序号(1..4)。
// maxReachedStep= 用户曾到达的最大步序(1..4)，决定哪些步已「访问过」。
//                 省略时默认等于 currentStep（首次线性前进场景）。
// 规则：
//   = current                         → active
//   已访问过(s <= maxReached) 且已填  → done
//   其余                              → collapsed
// 回改场景：current 指回某 done 步，maxReached 不回退，下游已填步保持 done。
function computeStepStates(currentStep, data, maxReachedStep) {
  var maxReached = maxReachedStep || currentStep
  var states = []
  for (var s = 1; s <= TOTAL_STEPS; s++) {
    if (s === currentStep) {
      states.push('active')
    } else if (s <= maxReached && isStepFilled(s, data)) {
      // 已访问过且已填 → done（回改时下游保留）
      states.push('done')
    } else {
      states.push('collapsed')
    }
  }
  return states
}

// 是否可点击进入某步（回改）：该步已 done 才可点。
function canNavigateTo(step, data) {
  return step !== 0 && isStepFilled(step, data)
}

// 全部 4 步是否都已填（可提交）。
function canSubmit(data) {
  for (var s = 1; s <= TOTAL_STEPS; s++) {
    if (!isStepFilled(s, data)) return false
  }
  return true
}

// 第一个未完成步（用于置灰提交时滚动定位）。返回 1..4，全完成返回 0。
function firstIncompleteStep(data) {
  for (var s = 1; s <= TOTAL_STEPS; s++) {
    if (!isStepFilled(s, data)) return s
  }
  return 0
}

// 回改医院后科室冲突判定（钉死规则，§四 回改冲突判定）。
//   oldDepartment: 原选科室名（可空）
//   newDeptList:   新院区科室名数组
// 返回：
//   { conflict: false }                          无冲突（未选 or 仍存在）
//   { conflict: true, clearedDept: '神经内科' }  冲突，需清空 + toast
function checkDepartmentConflict(oldDepartment, newDeptList) {
  var dept = oldDepartment ? String(oldDepartment).trim() : ''
  if (!dept) return { conflict: false } // 原未选科室 → 无冲突
  var list = Array.isArray(newDeptList) ? newDeptList : []
  if (list.indexOf(dept) !== -1) return { conflict: false } // 仍存在 → 保留
  return { conflict: true, clearedDept: dept } // 不存在 → 清空
}

// 科室冲突 toast 文案（钉死 · §五）。
function departmentConflictToast(clearedDept) {
  return '原科室"' + clearedDept + '"在该院区不可用，已为您清空，请重新选择'
}

module.exports = {
  TOTAL_STEPS: TOTAL_STEPS,
  STEP_TITLES: STEP_TITLES,
  isStepFilled: isStepFilled,
  computeStepStates: computeStepStates,
  canNavigateTo: canNavigateTo,
  canSubmit: canSubmit,
  firstIncompleteStep: firstIncompleteStep,
  checkDepartmentConflict: checkDepartmentConflict,
  departmentConflictToast: departmentConflictToast
}
