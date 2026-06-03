// stepperState.test.js
// S2-INT-003 — U-1 状态机 + 回改冲突判定单测（AC#13 必测项）
// 真源：docs/design/wireframes/U1-folding-stepper/README.md §四/§五

var S = require('../../utils/stepperState')

describe('stepperState 状态机（U-1 折叠下单）', function () {
  describe('步骤数与命名（钉死 4 步互锁）', function () {
    test('步骤数固定为 4', function () {
      expect(S.TOTAL_STEPS).toBe(4)
    })
    test('步骤命名逐字符一致', function () {
      expect(S.STEP_TITLES).toEqual(['服务类型', '医院', '日期', '患者 & 陪诊师确认'])
    })
  })

  describe('isStepFilled 各步完成判定', function () {
    test('① 有 serviceType 即完成', function () {
      expect(S.isStepFilled(1, { serviceType: 'full' })).toBe(true)
      expect(S.isStepFilled(1, {})).toBe(false)
    })
    test('② 有 hospitalId 即完成（科室可选不参与）', function () {
      expect(S.isStepFilled(2, { hospitalId: 'h1' })).toBe(true)
      expect(S.isStepFilled(2, { hospitalId: 'h1', department: '' })).toBe(true)
      expect(S.isStepFilled(2, {})).toBe(false)
    })
    test('③ 需 date 且 period', function () {
      expect(S.isStepFilled(3, { date: '2026-06-03', period: '上午' })).toBe(true)
      expect(S.isStepFilled(3, { date: '2026-06-03' })).toBe(false)
      expect(S.isStepFilled(3, { period: '上午' })).toBe(false)
    })
    test('④ 确认步恒可完成', function () {
      expect(S.isStepFilled(4, {})).toBe(true)
    })
  })

  describe('computeStepStates 三态计算', function () {
    test('初始：仅第①步 active，其余 collapsed', function () {
      expect(S.computeStepStates(1, {}, 1)).toEqual(['active', 'collapsed', 'collapsed', 'collapsed'])
    })
    test('填完①进②：①done ②active', function () {
      var data = { serviceType: 'full' }
      expect(S.computeStepStates(2, data, 2)).toEqual(['done', 'active', 'collapsed', 'collapsed'])
    })
    test('填到③：①②done ③active', function () {
      var data = { serviceType: 'full', hospitalId: 'h1' }
      expect(S.computeStepStates(3, data, 3)).toEqual(['done', 'done', 'active', 'collapsed'])
    })
    test('回改：current 指回②，①done ③已填仍 done（下游保留）', function () {
      var data = { serviceType: 'full', hospitalId: 'h1', date: '2026-06-03', period: '上午' }
      // 回改到第②步，maxReached=4（曾到过第④步），③已填 → 仍 done（下游保留）
      expect(S.computeStepStates(2, data, 4)).toEqual(['done', 'active', 'done', 'done'])
    })
  })

  describe('canNavigateTo 回改可点判定', function () {
    test('已 done 步可点', function () {
      expect(S.canNavigateTo(1, { serviceType: 'full' })).toBe(true)
    })
    test('未填步不可点', function () {
      expect(S.canNavigateTo(2, {})).toBe(false)
    })
  })

  describe('canSubmit / firstIncompleteStep', function () {
    test('四步全填可提交', function () {
      var data = { serviceType: 'full', hospitalId: 'h1', date: '2026-06-03', period: '下午' }
      expect(S.canSubmit(data)).toBe(true)
      expect(S.firstIncompleteStep(data)).toBe(0)
    })
    test('缺医院 → 不可提交，第一个未完成为②', function () {
      var data = { serviceType: 'full', date: '2026-06-03', period: '下午' }
      expect(S.canSubmit(data)).toBe(false)
      expect(S.firstIncompleteStep(data)).toBe(2)
    })
    test('缺日期 → 第一个未完成为③', function () {
      var data = { serviceType: 'full', hospitalId: 'h1' }
      expect(S.firstIncompleteStep(data)).toBe(3)
    })
  })

  describe('checkDepartmentConflict 回改科室冲突（钉死）', function () {
    test('原未选科室 → 无冲突', function () {
      expect(S.checkDepartmentConflict('', ['内科', '外科'])).toEqual({ conflict: false })
      expect(S.checkDepartmentConflict(null, ['内科'])).toEqual({ conflict: false })
    })
    test('原科室在新院区仍存在 → 保留无冲突', function () {
      expect(S.checkDepartmentConflict('神经内科', ['神经内科', '外科'])).toEqual({ conflict: false })
    })
    test('原科室在新院区不存在 → 冲突需清空', function () {
      expect(S.checkDepartmentConflict('神经内科', ['内科', '外科'])).toEqual({ conflict: true, clearedDept: '神经内科' })
    })
    test('toast 文案逐字符钉死', function () {
      expect(S.departmentConflictToast('神经内科')).toBe('原科室"神经内科"在该院区不可用，已为您清空，请重新选择')
    })
  })
})
